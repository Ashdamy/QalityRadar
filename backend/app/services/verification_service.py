"""Verificacion del correo de las cuentas con contrasena.

Los limites de uso son por cuenta. Sin esto, crear cuentas era escribir correos
inventados, y saltarse los limites era crear cuentas. Ahora cada cuenta cuesta
un buzon de verdad.

Las cuentas de GitHub no pasan por aqui: GitHub solo entrega correos que el ya
ha verificado.
"""

import logging
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import EMAIL_VERIFICATION_HOURS, create_email_verification_token
from app.models.user import User

logger = logging.getLogger(__name__)

# Una cuenta sin verificar no sirve para nada y bloquea el correo: quien lo
# registro con una direccion ajena impediria a su dueno registrarse. A los
# siete dias se borra y el correo queda libre.
UNVERIFIED_RETENTION_DAYS = 7


def build_link(user_id: uuid.UUID) -> str:
    # El token va en el fragmento (#), no en la consulta (?): el navegador no
    # manda el fragmento al servidor, asi que no acaba en ningun log de acceso
    # ni en la cabecera Referer.
    token = create_email_verification_token(user_id)
    return f"{get_settings().frontend_base_url}/verificar-email#token={token}"


def send_verification_email(destinatario: str, enlace: str) -> None:
    """Envia el enlace. Se llama en segundo plano, despues de responder.

    Asi el registro no tarda lo que tarde el SMTP, y un fallo del correo no
    tumba la peticion: queda en el log y el usuario puede pedir otro enlace
    volviendo a iniciar sesion.
    """
    ajustes = get_settings()
    if not ajustes.smtp_host:
        logger.error("SMTP_HOST sin configurar: no se envia el correo de verificacion")
        return

    mensaje = EmailMessage()
    mensaje["Subject"] = "Confirma tu correo en QalitiRadar"
    mensaje["From"] = ajustes.mail_from
    mensaje["To"] = destinatario
    mensaje.set_content(
        "Hola:\n\n"
        "Para activar tu cuenta de QalitiRadar, abre este enlace:\n\n"
        f"{enlace}\n\n"
        f"Caduca en {EMAIL_VERIFICATION_HOURS} horas. Si caduca, inicia sesion y te "
        "enviaremos otro.\n\n"
        "Si no has creado tu esta cuenta, no abras el enlace: ignora este correo y "
        f"la cuenta se borrara sola en {UNVERIFIED_RETENTION_DAYS} dias.\n"
    )

    try:
        with smtplib.SMTP(ajustes.smtp_host, ajustes.smtp_port, timeout=15) as smtp:
            if ajustes.smtp_starttls:
                smtp.starttls()
            if ajustes.smtp_user:
                smtp.login(ajustes.smtp_user, ajustes.smtp_password)
            smtp.send_message(mensaje)
    except (smtplib.SMTPException, OSError):
        logger.exception("no se pudo enviar el correo de verificacion")


def purge_unverified_accounts(db: Session) -> int:
    """Borra las cuentas que llevan una semana sin verificar. No confirma."""
    corte = datetime.now(timezone.utc) - timedelta(days=UNVERIFIED_RETENTION_DAYS)
    resultado = db.execute(
        delete(User).where(User.email_verified_at.is_(None), User.created_at < corte)
    )
    return resultado.rowcount or 0
