"""Insignia de calidad para el README.

Es la unica parte del sistema pensada para que la vea gente sin cuenta aqui, y
la unica cuyo token no caduca. Lo que se prueba es justo eso: que no expone mas
que la cifra, que sobrevive al tiempo, y que no se rompe la portada de nadie.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.main import app
from app.models.analysis import Analysis
from app.models.repository import Repository
from app.models.user import User
from app.services import badge_service

client = TestClient(app)

_EMAIL = "insignia-fixture@example.com"
_PASSWORD = "una-contrasena-larga-123"


@pytest.fixture
def sesion_con_repositorio():
    """Cuenta con un repositorio y un analisis terminado."""

    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.commit()
        finally:
            db.close()

        cliente = __import__(
            "app.services.rate_limit_service", fromlist=["_client"]
        )._client()
        for patron in ("ratelimit:registrations:*", "ratelimit:login:*"):
            for clave in cliente.scan_iter(patron):
                cliente.delete(clave)

    _borrar()
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})
    navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

    db = SessionLocal()
    try:
        usuario = db.scalar(select(User).where(User.email == _EMAIL))
        repo = Repository(
            id=uuid.uuid4(),
            user_id=usuario.id,
            github_id=987654321,
            name="proyecto",
            full_name="alguien/proyecto",
        )
        db.add(repo)
        db.flush()
        db.add(
            Analysis(
                id=uuid.uuid4(),
                user_id=usuario.id,
                repository_id=repo.id,
                analysis_type="repository",
                status="completed",
                overall_score=64.25,
            )
        )
        db.commit()
        repo_id = repo.id
    finally:
        db.close()

    yield navegador, repo_id
    _borrar()


def test_la_insignia_muestra_la_nota_del_ultimo_analisis(sesion_con_repositorio):
    navegador, repo_id = sesion_con_repositorio

    creada = navegador.post(f"/api/repositories/{repo_id}/badge")
    assert creada.status_code == 201
    token = creada.json()["token"]

    # Sin sesion: lo pide el navegador de cualquiera que visite el README.
    anonimo = TestClient(app)
    imagen = anonimo.get(f"/api/badge/{token}.svg")

    assert imagen.status_code == 200
    assert imagen.headers["content-type"].startswith("image/svg+xml")
    assert "64/100" in imagen.text


def test_el_markdown_viene_listo_para_pegar(sesion_con_repositorio):
    navegador, repo_id = sesion_con_repositorio

    cuerpo = navegador.post(f"/api/repositories/{repo_id}/badge").json()

    assert cuerpo["markdown"].startswith("[![Calidad](")
    assert cuerpo["token"] in cuerpo["markdown"]


def test_pedirla_dos_veces_da_el_mismo_token(sesion_con_repositorio):
    """Si cambiara, la insignia ya pegada en un README dejaria de funcionar sin
    que nadie la tocara."""
    navegador, repo_id = sesion_con_repositorio

    primera = navegador.post(f"/api/repositories/{repo_id}/badge").json()["token"]
    segunda = navegador.post(f"/api/repositories/{repo_id}/badge").json()["token"]

    assert primera == segunda


def test_la_insignia_no_dice_nada_mas_que_la_cifra(sesion_con_repositorio):
    """Si el token se filtrara antes de publicarlo, lo que se lleva quien lo
    tenga es un numero: ni el nombre del repositorio ni los hallazgos."""
    navegador, repo_id = sesion_con_repositorio
    token = navegador.post(f"/api/repositories/{repo_id}/badge").json()["token"]

    svg = TestClient(app).get(f"/api/badge/{token}.svg").text

    assert "alguien/proyecto" not in svg
    assert "proyecto" not in svg
    assert str(repo_id) not in svg


def test_un_token_inventado_no_rompe_la_portada_de_nadie():
    """Un 404 dejaria una imagen rota en el README. Y da la misma respuesta que
    uno revocado, para que no sirva de oraculo."""
    respuesta = TestClient(app).get("/api/badge/este-token-no-existe.svg")

    assert respuesta.status_code == 200
    assert "sin analizar" in respuesta.text


def test_revocarla_la_apaga_pero_deja_imagen(sesion_con_repositorio):
    navegador, repo_id = sesion_con_repositorio
    token = navegador.post(f"/api/repositories/{repo_id}/badge").json()["token"]

    assert navegador.delete(f"/api/repositories/{repo_id}/badge").status_code == 204

    imagen = TestClient(app).get(f"/api/badge/{token}.svg")
    assert imagen.status_code == 200
    assert "sin analizar" in imagen.text


def test_la_insignia_de_otro_no_se_toca(sesion_con_repositorio):
    """404 y no 403: un 403 confirmaria que ese repositorio existe."""
    _, repo_id = sesion_con_repositorio

    ajeno = TestClient(app)
    ajeno.post("/api/auth/register", json={"accept_privacy": True, "email": "otro-insignia@example.com", "password": _PASSWORD})
    ajeno.post("/api/auth/login", json={"email": "otro-insignia@example.com", "password": _PASSWORD})
    try:
        assert ajeno.post(f"/api/repositories/{repo_id}/badge").status_code == 404
    finally:
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == "otro-insignia@example.com"))
            db.commit()
        finally:
            db.close()


def test_sin_sesion_no_se_puede_encender(sesion_con_repositorio):
    _, repo_id = sesion_con_repositorio

    assert TestClient(app).post(f"/api/repositories/{repo_id}/badge").status_code == 401


def test_se_le_dice_al_navegador_cada_cuanto_volver_a_preguntar(sesion_con_repositorio):
    """GitHub sirve las imagenes del README por su propia cache; sin esto, cada
    visita al repositorio seria una consulta a la base de datos."""
    navegador, repo_id = sesion_con_repositorio
    token = navegador.post(f"/api/repositories/{repo_id}/badge").json()["token"]

    respuesta = TestClient(app).get(f"/api/badge/{token}.svg")

    assert f"max-age={badge_service.CACHE_SECONDS}" in respuesta.headers["cache-control"]


@pytest.mark.parametrize(
    "nota,esperado",
    [(91.0, "#2f8f4e"), (64.0, "#8a9a2b"), (45.0, "#c8811a"), (12.0, "#c0392b"), (None, "#8a8f98")],
)
def test_el_color_sigue_los_tramos_de_la_nota(nota, esperado):
    assert esperado in badge_service.render_badge(nota)
