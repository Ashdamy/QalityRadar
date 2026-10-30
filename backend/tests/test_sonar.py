"""Importacion de metricas de SonarCloud.

Ninguna prueba sale a internet: `httpx.get` se sustituye por respuestas
simuladas con la misma forma que las de verdad (comprobada contra
sonarcloud.io sin token el 29/10/2026).
"""

import httpx
import pytest

from app.services import sonar_service
from app.services.scoring_service import score_dimension, subcharacteristics
from app.services.sonar_service import SONARCLOUD_URL, SonarError, clave_valida, obtener_metricas

CLAVE = "mi-organizacion_mi-proyecto"

RESPUESTA_OK = {
    "component": {
        "key": CLAVE,
        "name": "Mi proyecto",
        "qualifier": "TRK",
        "measures": [
            {"metric": "coverage", "value": "93.4", "bestValue": False},
            {"metric": "duplicated_lines_density", "value": "0.5", "bestValue": False},
            {"metric": "cognitive_complexity", "value": "2021", "bestValue": False},
            {"metric": "sqale_index", "value": "3793", "bestValue": False},
            {"metric": "sqale_rating", "value": "1.0", "bestValue": True},
            {"metric": "ncloc", "value": "17664"},
        ],
    }
}


def _simular(monkeypatch, *, status=200, json=None, error=None):
    """Sustituye la llamada a SonarCloud y apunta con que se hizo."""
    llamadas = []

    def falso_get(url, **kwargs):
        llamadas.append((url, kwargs))
        if error is not None:
            raise error
        return httpx.Response(status, json=json if json is not None else {}, request=httpx.Request("GET", url))

    monkeypatch.setattr(sonar_service.httpx, "get", falso_get)
    return llamadas


# -- Servicio -----------------------------------------------------------------


def test_lee_las_metricas_de_un_proyecto_publico(monkeypatch):
    llamadas = _simular(monkeypatch, json=RESPUESTA_OK)

    metricas = obtener_metricas(CLAVE)

    assert metricas == {
        "coverage": 93.4, "duplicated_lines_density": 0.5, "cognitive_complexity": 2021.0,
        "sqale_index": 3793.0, "sqale_rating": 1.0, "ncloc": 17664.0,
    }
    url, opciones = llamadas[0]
    assert url == SONARCLOUD_URL == "https://sonarcloud.io/api/measures/component"
    assert opciones["params"]["component"] == CLAVE
    assert opciones["follow_redirects"] is False
    assert opciones["timeout"] == sonar_service.TIMEOUT_SEGUNDOS
    # Sin token: nada de cabeceras de autorizacion.
    assert "headers" not in opciones and "auth" not in opciones


def test_ignora_metricas_que_no_pidio_y_valores_que_no_son_numeros(monkeypatch):
    _simular(monkeypatch, json={"component": {"measures": [
        {"metric": "coverage", "value": "80"},
        {"metric": "bugs", "value": "3"},
        {"metric": "sqale_rating", "value": "<script>"},
    ]}})

    assert obtener_metricas(CLAVE) == {"coverage": 80.0}


@pytest.mark.parametrize(
    "status, codigo, fragmento",
    [
        (404, 404, "no encuentra ese proyecto"),
        (401, 403, "privado"),
        (403, 403, "privado"),
        (429, 503, "limitando las peticiones"),
        (500, 502, "no está disponible"),
        (302, 502, "no está disponible"),
    ],
)
def test_cada_fallo_de_sonarcloud_tiene_su_mensaje(monkeypatch, status, codigo, fragmento):
    _simular(monkeypatch, status=status)

    with pytest.raises(SonarError) as error:
        obtener_metricas(CLAVE)

    assert error.value.status_code == codigo
    assert fragmento in error.value.mensaje


def test_si_sonarcloud_no_responde_a_tiempo(monkeypatch):
    _simular(monkeypatch, error=httpx.ReadTimeout("lento"))

    with pytest.raises(SonarError) as error:
        obtener_metricas(CLAVE)
    assert error.value.status_code == 504
    assert "tardó demasiado" in error.value.mensaje


def test_si_sonarcloud_esta_caido(monkeypatch):
    _simular(monkeypatch, error=httpx.ConnectError("sin red"))

    with pytest.raises(SonarError) as error:
        obtener_metricas(CLAVE)
    assert error.value.status_code == 502


def test_proyecto_sin_metricas_todavia(monkeypatch):
    _simular(monkeypatch, json={"component": {"measures": [{"metric": "ncloc", "value": "10"}]}})

    with pytest.raises(SonarError) as error:
        obtener_metricas(CLAVE)
    assert error.value.status_code == 422


def test_respuesta_con_forma_inesperada(monkeypatch):
    _simular(monkeypatch, json={"otra": "cosa"})

    with pytest.raises(SonarError) as error:
        obtener_metricas(CLAVE)
    assert error.value.status_code == 502


@pytest.mark.parametrize(
    "clave",
    [
        "", "123", "https://evil.example/x", "a b", "../../etc", "clave?x=1", "clave&metricKeys=x",
        "-empieza-con-guion", "a" * 401, "clave\n", "proyecto/sub",
    ],
)
def test_claves_que_no_salen_de_aqui(monkeypatch, clave):
    llamadas = _simular(monkeypatch, json=RESPUESTA_OK)

    assert not clave_valida(clave)
    with pytest.raises(SonarError) as error:
        obtener_metricas(clave)
    assert error.value.status_code == 422
    assert llamadas == []


@pytest.mark.parametrize("clave", [CLAVE, "org:proyecto", "Proyecto.Con-Puntos_1", "a" * 400])
def test_claves_validas(clave):
    assert clave_valida(clave)


# -- Puntuacion ---------------------------------------------------------------

PROPIAS = {
    "code_file_count": 40, "average_file_lines": 120, "largest_file_lines": 500,
    "average_function_lines": 25, "top_level_directory_count": 3, "project_shape": "app",
    "comment_ratio": 0.0, "function_documentation_ratio": 0.0, "max_nesting_depth": 9,
    "has_linter_config": False, "has_gitignore": True, "has_dependency_manifest": True,
}
SONAR = {"coverage": 93.4, "duplicated_lines_density": 0.5, "cognitive_complexity": 2021.0,
         "sqale_index": 3793.0, "sqale_rating": 1.0, "ncloc": 17664.0}


def _por_nombre(metricas):
    return {s["name"]: s for s in subcharacteristics("maintainability", metricas)}


def test_sin_sonarcloud_la_rubrica_no_cambia_y_dice_que_es_estimada():
    subs = _por_nombre(PROPIAS)

    assert subs["Modularidad"]["origin"] == "qalitiradar"
    assert subs["Analizabilidad"]["origin"] == "estimado"
    assert subs["Modificabilidad"]["origin"] == "estimado"
    assert subs["Capacidad de prueba"]["origin"] == "sin_medir"
    assert subs["Capacidad de prueba"]["earned"] is None
    assert [subs[n]["max"] for n in ("Modularidad", "Analizabilidad", "Modificabilidad")] == [38, 30, 32]


def test_con_sonarcloud_sustituye_lo_estimado():
    subs = _por_nombre({**PROPIAS, "sonar": SONAR})

    assert subs["Analizabilidad"]["origin"] == "sonarcloud"
    assert subs["Modificabilidad"]["origin"] == "sonarcloud"
    assert subs["Capacidad de prueba"]["origin"] == "sonarcloud"
    assert subs["Modularidad"]["origin"] == "qalitiradar"
    # Deuda A y 0,5 % de duplicacion: modificabilidad completa.
    assert subs["Modificabilidad"]["earned"] == subs["Modificabilidad"]["max"]
    # 93,4 % de cobertura: los 20 puntos.
    assert subs["Capacidad de prueba"]["earned"] == 20
    medidas = [s for s in subs.values() if s["measured"]]
    assert round(sum(s["max"] for s in medidas), 2) == 100
    assert round(sum(s["earned"] for s in medidas), 2) == score_dimension("maintainability", {**PROPIAS, "sonar": SONAR}, [])


def test_mejores_metricas_de_sonarcloud_dan_mas_nota():
    malo = {**SONAR, "sqale_rating": 5.0, "duplicated_lines_density": 25.0, "coverage": 5.0,
            "cognitive_complexity": 9000.0}
    assert score_dimension("maintainability", {**PROPIAS, "sonar": SONAR}, []) > score_dimension(
        "maintainability", {**PROPIAS, "sonar": malo}, []
    )


def test_sin_cobertura_en_sonarcloud_la_capacidad_de_prueba_sigue_sin_medir():
    sin_cobertura = {k: v for k, v in SONAR.items() if k != "coverage"}
    subs = _por_nombre({**PROPIAS, "sonar": sin_cobertura})

    assert subs["Capacidad de prueba"]["measured"] is False
    assert subs["Analizabilidad"]["max"] == 30


def test_una_metrica_suelta_no_sustituye_un_grupo_entero():
    """Con la deuda pero sin la duplicacion, la modificabilidad sigue estimada."""
    subs = _por_nombre({**PROPIAS, "sonar": {"sqale_rating": 1.0}})

    assert subs["Modificabilidad"]["origin"] == "estimado"


# -- API ----------------------------------------------------------------------


@pytest.fixture
def analisis_de_repositorio():
    import uuid

    from fastapi.testclient import TestClient
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.main import app
    from app.models.analysis import Analysis, Dimension
    from app.models.deployed_app import DeployedApp
    from app.models.repository import Repository
    from app.models.user import User
    from app.services import rate_limit_service as limites

    email = "sonar@example.com"

    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == email))
            db.commit()
        finally:
            db.close()
        for clave in limites._client().scan_iter("ratelimit:sonar:*"):
            limites._client().delete(clave)

    _borrar()
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": email, "password": "s3cur3-passw0rd"})
    navegador.post("/api/auth/login", json={"email": email, "password": "s3cur3-passw0rd"})
    db = SessionLocal()
    try:
        usuario = db.query(User).filter_by(email=email).one()
        repo = Repository(id=uuid.uuid4(), user_id=usuario.id, github_id=987654321, name="r", full_name="o/r")
        app_web = DeployedApp(id=uuid.uuid4(), user_id=usuario.id, url="https://example.com")
        db.add_all([repo, app_web])
        db.flush()
        analisis = Analysis(id=uuid.uuid4(), user_id=usuario.id, repository_id=repo.id,
                            analysis_type="repository", status="completed", overall_score=50, confidence_level=90)
        de_url = Analysis(id=uuid.uuid4(), user_id=usuario.id, app_id=app_web.id,
                          analysis_type="url", status="completed", overall_score=50)
        db.add_all([analisis, de_url])
        db.flush()
        db.add_all([
            Dimension(id=uuid.uuid4(), analysis_id=analisis.id, name="maintainability",
                      score=score_dimension("maintainability", PROPIAS, []), weight=0.235,
                      raw_metrics=PROPIAS, subcharacteristics=subcharacteristics("maintainability", PROPIAS)),
            Dimension(id=uuid.uuid4(), analysis_id=analisis.id, name="security", score=50, weight=0.235,
                      raw_metrics={}),
        ])
        db.commit()
        datos = (navegador, analisis.id, de_url.id)
    finally:
        db.close()
    yield datos
    _borrar()


def test_importar_repuntua_mantenibilidad_y_la_nota_global(monkeypatch, analisis_de_repositorio):
    navegador, analisis, _ = analisis_de_repositorio
    antes = navegador.get(f"/api/analyses/{analisis}").json()
    _simular(monkeypatch, json=RESPUESTA_OK)

    respuesta = navegador.post(f"/api/analyses/{analisis}/sonar", json={"project_key": f"  {CLAVE} "})

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["sonar"]["project_key"] == CLAVE
    assert datos["sonar"]["metrics"]["sqale_index"] == 3793
    assert datos["sonar"]["imported_at"]
    mant = next(d for d in datos["dimensions"] if d["name"] == "maintainability")
    mant_antes = next(d for d in antes["dimensions"] if d["name"] == "maintainability")
    assert mant["score"] > mant_antes["score"]
    assert {s["name"]: s["origin"] for s in mant["subcharacteristics"]}["Analizabilidad"] == "sonarcloud"
    assert datos["overall_score"] != antes["overall_score"]
    # Y queda guardado: una lectura posterior lo trae igual.
    assert navegador.get(f"/api/analyses/{analisis}").json()["sonar"]["project_key"] == CLAVE


@pytest.mark.parametrize(
    "simulacion, codigo, fragmento",
    [
        ({"status": 404}, 404, "no encuentra ese proyecto"),
        ({"status": 403}, 403, "privado"),
        ({"status": 429}, 503, "limitando"),
        ({"error": httpx.ConnectTimeout("lento")}, 504, "tardó demasiado"),
    ],
)
def test_los_fallos_llegan_al_usuario_en_espanol_y_no_tocan_nada(
    monkeypatch, analisis_de_repositorio, simulacion, codigo, fragmento
):
    navegador, analisis, _ = analisis_de_repositorio
    antes = navegador.get(f"/api/analyses/{analisis}").json()
    _simular(monkeypatch, **simulacion)

    respuesta = navegador.post(f"/api/analyses/{analisis}/sonar", json={"project_key": CLAVE})

    assert respuesta.status_code == codigo
    assert fragmento in respuesta.json()["detail"]
    despues = navegador.get(f"/api/analyses/{analisis}").json()
    assert despues["sonar"] is None
    assert despues["overall_score"] == antes["overall_score"]


def test_una_clave_invalida_ni_sale_ni_gasta_cupo(monkeypatch, analisis_de_repositorio):
    navegador, analisis, _ = analisis_de_repositorio
    llamadas = _simular(monkeypatch, json=RESPUESTA_OK)

    respuesta = navegador.post(f"/api/analyses/{analisis}/sonar", json={"project_key": "https://evil.example"})

    assert respuesta.status_code == 422
    assert llamadas == []


def test_hay_un_tope_de_importaciones_por_hora(monkeypatch, analisis_de_repositorio):
    from app.services.rate_limit_service import MAX_SONAR_IMPORTS_PER_HOUR

    navegador, analisis, _ = analisis_de_repositorio
    _simular(monkeypatch, json=RESPUESTA_OK)
    for _ in range(MAX_SONAR_IMPORTS_PER_HOUR):
        assert navegador.post(f"/api/analyses/{analisis}/sonar", json={"project_key": CLAVE}).status_code == 200

    assert navegador.post(f"/api/analyses/{analisis}/sonar", json={"project_key": CLAVE}).status_code == 429


def test_solo_en_analisis_de_repositorio(monkeypatch, analisis_de_repositorio):
    navegador, _, de_url = analisis_de_repositorio
    llamadas = _simular(monkeypatch, json=RESPUESTA_OK)

    assert navegador.post(f"/api/analyses/{de_url}/sonar", json={"project_key": CLAVE}).status_code == 409
    assert llamadas == []


def test_no_se_importa_en_analisis_ajenos(monkeypatch, analisis_de_repositorio):
    from fastapi.testclient import TestClient

    from app.main import app

    _, analisis, _ = analisis_de_repositorio
    llamadas = _simular(monkeypatch, json=RESPUESTA_OK)

    assert TestClient(app).post(f"/api/analyses/{analisis}/sonar", json={"project_key": CLAVE}).status_code == 401
    assert llamadas == []
