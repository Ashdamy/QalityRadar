"""Rastro de lo que le pasa a una cuenta.

La pregunta que tiene que contestar es una sola: si alguien entro donde no
debia, cuando, y desde donde. Lo que no contesta esa pregunta no se guarda.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.main import app
from app.models.auth_event import AuthEvent
from app.models.user import User
from app.services import audit_service
from app.services import rate_limit_service as limites

_EMAIL = "auditoria-fixture@example.com"
_PASSWORD = "una-contrasena-larga-123"


@pytest.fixture(autouse=True)
def _limpieza():
    def _borrar():
        db = SessionLocal()
        try:
            # Los eventos de la cuenta caen con ella (ON DELETE CASCADE); los
            # que no tienen cuenta hay que barrerlos aparte.
            db.execute(delete(User).where(User.email == _EMAIL))
            db.execute(delete(AuthEvent).where(AuthEvent.user_id.is_(None)))
            db.commit()
        finally:
            db.close()

        cliente = limites._client()
        for patron in ("ratelimit:registrations:*", "ratelimit:login:*"):
            for clave in cliente.scan_iter(patron):
                cliente.delete(clave)

    _borrar()
    yield
    _borrar()


def _eventos(user_id=None):
    db = SessionLocal()
    try:
        consulta = select(AuthEvent).order_by(AuthEvent.created_at)
        if user_id is not None:
            consulta = consulta.where(AuthEvent.user_id == user_id)
        return [(f.event, f.user_id, f.ip) for f in db.scalars(consulta).all()]
    finally:
        db.close()


def _crear_cuenta(cliente):
    respuesta = cliente.post(
        "/api/auth/register", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert respuesta.status_code == 201
    return uuid.UUID(respuesta.json()["id"])


def test_entrar_deja_rastro():
    cliente = TestClient(app)
    user_id = _crear_cuenta(cliente)

    cliente.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

    eventos = [e for e, _, _ in _eventos(user_id)]
    assert eventos == [audit_service.REGISTRO, audit_service.ENTRADA]


def test_una_contrasena_equivocada_deja_rastro_en_la_cuenta():
    """Es el patron que importa: varios fallos seguidos contra la misma
    cuenta, y despues una entrada."""
    cliente = TestClient(app)
    user_id = _crear_cuenta(cliente)

    cliente.post("/api/auth/login", json={"email": _EMAIL, "password": "no-es-esta"})

    assert audit_service.ENTRADA_FALLIDA in [e for e, _, _ in _eventos(user_id)]


def test_un_intento_contra_una_cuenta_inexistente_no_guarda_el_correo():
    """Guardarlo seria ir construyendo la lista de correos que alguien prueba,
    que es justo lo que no hace falta tener."""
    cliente = TestClient(app)

    cliente.post(
        "/api/auth/login",
        json={"email": "esta-cuenta-no-existe@example.com", "password": "loquesea"},
    )

    sin_cuenta = [(e, u, ip) for e, u, ip in _eventos() if u is None]
    assert any(e == audit_service.ENTRADA_FALLIDA for e, _, _ in sin_cuenta)
    db = SessionLocal()
    try:
        filas = db.scalars(select(AuthEvent).where(AuthEvent.user_id.is_(None))).all()
        assert not any("esta-cuenta-no-existe" in str(vars(f)) for f in filas)
    finally:
        db.close()


def test_quedarse_sin_intentos_tambien_deja_rastro():
    """Sin esto, una tanda de fuerza bruta se ve como unos cuantos fallos y
    luego silencio, que es indistinguible de que el atacante se aburriera."""
    cliente = TestClient(app)
    _crear_cuenta(cliente)

    for _ in range(limites.MAX_LOGIN_FAILURES_PER_EMAIL_HOUR + 1):
        cliente.post("/api/auth/login", json={"email": _EMAIL, "password": "no-es-esta"})

    assert audit_service.ENTRADA_BLOQUEADA in [e for e, _, _ in _eventos()]


def test_cerrar_sesion_deja_rastro():
    cliente = TestClient(app)
    user_id = _crear_cuenta(cliente)
    cliente.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

    cliente.post("/api/auth/logout")

    assert audit_service.SALIDA in [e for e, _, _ in _eventos(user_id)]


def test_el_rastro_no_puede_tumbar_el_inicio_de_sesion(monkeypatch):
    """Si un problema del registro arrastrara la peticion, dejaria a la gente
    sin poder entrar. Un rastro incompleto es peor que uno completo y mejor
    que un servicio caido."""
    cliente = TestClient(app)
    _crear_cuenta(cliente)

    def _revienta(*_args, **_kwargs):
        raise RuntimeError("la tabla no esta")

    monkeypatch.setattr(audit_service, "registrar", _revienta)

    with pytest.raises(RuntimeError):
        audit_service.registrar(None, "x")
    # Y con el registro real, un fallo dentro no se propaga:
    monkeypatch.undo()
    db = SessionLocal()
    try:
        monkeypatch.setattr(db, "add", _revienta)
        audit_service.registrar(db, audit_service.ENTRADA)  # no debe lanzar
    finally:
        db.close()


def test_los_eventos_viejos_se_purgan():
    """Una IP es un dato personal: guardarla para siempre no ayuda a nadie."""
    db = SessionLocal()
    try:
        viejo = AuthEvent(id=uuid.uuid4(), event=audit_service.ENTRADA_FALLIDA)
        db.add(viejo)
        db.flush()
        viejo.created_at = datetime.now(timezone.utc) - timedelta(
            days=audit_service.RETENTION_DAYS + 1
        )
        reciente = AuthEvent(id=uuid.uuid4(), event=audit_service.ENTRADA_FALLIDA)
        db.add(reciente)
        db.commit()
        # Los ids se leen antes de purgar: despues, la fila borrada ya no se
        # puede consultar desde su objeto.
        id_viejo, id_reciente = viejo.id, reciente.id

        borrados = audit_service.purge_old_events(db)
        db.commit()

        assert borrados == 1
        quedan = db.scalars(select(AuthEvent.id).where(AuthEvent.user_id.is_(None))).all()
        assert id_reciente in quedan
        assert id_viejo not in quedan
    finally:
        db.close()
