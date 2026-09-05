import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuthEvent(Base):
    """Rastro de lo que le pasa a una cuenta: entradas, salidas y fallos.

    No guarda que consulto cada quien, sino que le paso a su cuenta. Es la
    diferencia entre un registro que sirve despues de un incidente y uno que
    crece sin parar y no contesta la unica pregunta que se le hace: se metio
    alguien donde no debia.
    """

    __tablename__ = "auth_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # Nulo cuando el intento no llego a identificar a nadie: probar una
    # contrasena contra un correo que no existe tambien deja rastro, y ahi no
    # hay cuenta a la que colgarselo.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    # Detras de segun que proxy no llega, y se guarda nulo antes que inventarla.
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
