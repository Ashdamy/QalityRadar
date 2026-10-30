"""Medicion en navegador real (Lighthouse + axe-core).

Ninguna prueba lanza un navegador ni Docker: la salida del contenedor se
simula con la misma forma que escribe `navegador/medir.mjs`. Lo que si corre
de verdad es el proxy de salida, sobre sockets locales, con un resolvedor
de DNS falso.
"""

import asyncio
import json
import subprocess
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.analysis import Analysis, Dimension, Finding
from app.models.deployed_app import DeployedApp
from app.models.user import User
from app.services import medicion_navegador_service as servicio
from app.services.scoring_service import (
    HIGH_FINDING_SCORE_CAP,
    calculate_url_overall_score,
    score_url_dimension,
    subcharacteristics,
)
from app.utils import navegador
from app.utils.navegador import Contenedor, MedicionFallida, calificar, comando, interpretar, medir
from app.utils.proxy_navegador import PUERTOS_BLOQUEADOS, Bloqueado, Proxy, abrir_destino, elegir_ip, servir
from app.utils.url_validation import BLOCKED_PORTS, UnsafeUrlError

PUBLICA = "93.184.216.34"
CONTENEDOR = Contenedor("qaliti/navegador:latest", "qalitiradar-navegador")

SALIDA_BUENA = {
    "lcp_ms": 1800.0, "tbt_ms": 120.0, "cls": 0.02,
    "axe": {"violations": [], "passes": 40},
}
SALIDA_MALA = {
    "lcp_ms": 6200.0, "tbt_ms": 900.0, "cls": 0.4,
    "axe": {
        "violations": [
            {"id": "image-alt", "impact": "critical", "nodes": 7, "help": "Las imágenes tienen texto alternativo"},
            {"id": "color-contrast", "impact": "serious", "nodes": 12, "help": "Contraste suficiente"},
            {"id": "region", "impact": "moderate", "nodes": 3, "help": "Contenido en regiones"},
            {"id": "meta-viewport-large", "impact": "minor", "nodes": 1, "help": "Zoom permitido"},
        ],
        "passes": 20,
    },
}


# -- Proxy: la defensa principal ----------------------------------------------


@pytest.mark.parametrize(
    "ip",
    ["10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1", "172.17.0.1", "100.64.0.1",
     "::1", "fd00:ec2::254", "fe80::1", "::ffff:127.0.0.1", "0.0.0.0"],
)
def test_el_proxy_bloquea_ips_internas_y_de_metadatos(ip):
    with pytest.raises(Bloqueado):
        elegir_ip(ip, 80, resolver=lambda h, p: pytest.fail("un literal no se resuelve"))


def test_el_proxy_bloquea_un_dominio_que_resuelve_a_una_ip_interna():
    with pytest.raises(Bloqueado):
        elegir_ip("metadatos.example", 80, resolver=lambda h, p: ["169.254.169.254"])


def test_basta_una_ip_interna_entre_varias_para_bloquear():
    with pytest.raises(Bloqueado):
        elegir_ip("mixto.example", 443, resolver=lambda h, p: [PUBLICA, "10.0.0.1"])


@pytest.mark.parametrize("puerto", sorted(BLOCKED_PORTS))
def test_el_proxy_bloquea_los_puertos_de_servicios_internos(puerto):
    with pytest.raises(Bloqueado):
        elegir_ip(PUBLICA, puerto)


def test_el_proxy_usa_los_mismos_puertos_que_la_validacion_de_urls():
    """El proxy no puede importar `app` (va solo en la imagen): que no se separen."""
    assert PUERTOS_BLOQUEADOS == BLOCKED_PORTS


def test_si_el_dns_falla_se_bloquea():
    def falla(h, p):
        raise OSError("sin DNS")

    with pytest.raises(Bloqueado):
        elegir_ip("no-existe.example", 443, resolver=falla)


def test_dns_rebinding_resuelve_una_vez_y_conecta_a_esa_misma_ip():
    """Un dominio que responde una IP publica y luego una privada.

    La primera conexion resuelve UNA vez y conecta a la IP publica que se
    comprobo, por numero: no hay segunda resolucion que pueda devolver la
    privada. La siguiente conexion, cuando el DNS ya da la privada, se bloquea
    sin llegar a conectar.
    """
    respuestas = iter([[PUBLICA], ["10.0.0.7"]])
    resoluciones, conexiones = [], []

    def resolver(host, puerto):
        resoluciones.append(host)
        return next(respuestas)

    async def conectar(ip, puerto):
        conexiones.append((ip, puerto))
        return "lector", "escritor"

    async def escenario():
        await abrir_destino("cambiante.example", 443, resolver=resolver, conectar=conectar)
        assert resoluciones == ["cambiante.example"]
        assert conexiones == [(PUBLICA, 443)]

        with pytest.raises(Bloqueado):
            await abrir_destino("cambiante.example", 443, resolver=resolver, conectar=conectar)
        assert len(resoluciones) == 2
        assert conexiones == [(PUBLICA, 443)]

    asyncio.run(escenario())


async def _peticion(puerto: int, texto: bytes) -> bytes:
    lector, escritor = await asyncio.open_connection("127.0.0.1", puerto)
    escritor.write(texto)
    await escritor.drain()
    respuesta = await asyncio.wait_for(lector.read(4096), 5)
    escritor.close()
    return respuesta


def _con_proxy(resolver, prueba, conectar=None):
    async def escenario():
        proxy = Proxy(resolver=resolver, **({"conectar": conectar} if conectar else {}))
        servidor = await servir("127.0.0.1", 0, proxy)
        puerto = servidor.sockets[0].getsockname()[1]
        try:
            return await prueba(puerto, proxy)
        finally:
            servidor.close()
            await servidor.wait_closed()

    return asyncio.run(escenario())


@pytest.mark.parametrize(
    "peticion",
    [
        b"CONNECT interno.example:443 HTTP/1.1\r\nHost: interno.example:443\r\n\r\n",
        b"GET http://interno.example/ HTTP/1.1\r\nHost: interno.example\r\n\r\n",
        # Lo que pediria la pagina tras una redireccion a los metadatos.
        b"GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\nHost: 169.254.169.254\r\n\r\n",
        b"CONNECT [::1]:443 HTTP/1.1\r\n\r\n",
        b"CONNECT 127.0.0.1:3128 HTTP/1.1\r\n\r\n",
    ],
)
def test_el_proxy_de_verdad_responde_403_a_lo_interno(peticion):
    async def prueba(puerto, proxy):
        respuesta = await _peticion(puerto, peticion)
        assert respuesta.startswith(b"HTTP/1.1 403")
        assert proxy.bloqueados

    _con_proxy(lambda h, p: ["10.0.0.5"], prueba)


def test_el_proxy_de_verdad_deja_pasar_lo_publico_y_conecta_a_la_ip_comprobada():
    destinos = []

    async def prueba(puerto, proxy):
        async def eco(lector, escritor):
            escritor.write(await lector.read(100))
            await escritor.drain()
            escritor.close()

        servidor_eco = await asyncio.start_server(eco, "127.0.0.1", 0)
        puerto_eco = servidor_eco.sockets[0].getsockname()[1]

        async def conectar(ip, p):
            destinos.append((ip, p))
            # En la prueba, la IP publica se sustituye por el eco local.
            return await asyncio.open_connection("127.0.0.1", puerto_eco)

        proxy.conectar = conectar
        lector, escritor = await asyncio.open_connection("127.0.0.1", puerto)
        escritor.write(b"CONNECT publico.example:443 HTTP/1.1\r\n\r\n")
        await escritor.drain()
        assert (await lector.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
        escritor.write(b"hola")
        await escritor.drain()
        assert await asyncio.wait_for(lector.read(4), 5) == b"hola"
        escritor.close()
        servidor_eco.close()

    _con_proxy(lambda h, p: [PUBLICA], prueba)
    assert destinos == [(PUBLICA, 443)]


# -- Lanzar el contenedor -----------------------------------------------------


def test_el_comando_lleva_los_limites_y_la_url_al_final():
    cmd = comando("https://example.com/", CONTENEDOR, "qr-navegador-x")

    for flag in ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=1g",
                 "--cpus=1", "--pids-limit=256", "--rm"):
        assert flag in cmd
    assert cmd[cmd.index("--user") + 1] == "65534:65534"
    assert cmd[cmd.index("--network") + 1] == "qalitiradar-navegador"
    # Nada de docker.sock ni de volumenes: el contenedor no ve el host.
    assert not any("docker.sock" in parte or parte in ("-v", "--volume") for parte in cmd)
    assert cmd[-3:] == ["--", "qaliti/navegador:latest", "https://example.com/"]


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.1/", "file:///etc/passwd"]
)
def test_una_url_interna_no_llega_a_lanzar_el_contenedor(url):
    lanzado = []
    with pytest.raises(UnsafeUrlError):
        medir(url, CONTENEDOR, ejecutar=lambda *a, **k: lanzado.append(a))
    assert lanzado == []


def _resultado(stdout="", codigo=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=codigo)


@pytest.fixture
def dns_publico(monkeypatch):
    monkeypatch.setattr(navegador, "validate_public_url", lambda url: None)


def test_medicion_simulada_correcta(dns_publico):
    resultado = medir("https://example.com/", CONTENEDOR, ejecutar=lambda *a, **k: _resultado(json.dumps(SALIDA_BUENA)))
    assert resultado["lcp_ms"] == 1800.0
    assert resultado["axe"] == {"violations": [], "passes": 40}


def test_si_el_contenedor_se_pasa_de_tiempo_se_mata_por_su_nombre(dns_publico):
    llamadas = []

    def ejecutar(cmd, **kwargs):
        llamadas.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        return _resultado()

    with pytest.raises(MedicionFallida, match="tardó demasiado"):
        medir("https://example.com/", CONTENEDOR, ejecutar=ejecutar)
    nombre = llamadas[0][llamadas[0].index("--name") + 1]
    assert llamadas[1] == ["docker", "rm", "-f", nombre]


def test_si_docker_no_esta_instalado(dns_publico):
    def ejecutar(*a, **k):
        raise FileNotFoundError("docker")

    with pytest.raises(MedicionFallida, match="no está disponible"):
        medir("https://example.com/", CONTENEDOR, ejecutar=ejecutar)


def test_si_el_contenedor_falla(dns_publico):
    with pytest.raises(MedicionFallida):
        medir("https://example.com/", CONTENEDOR, ejecutar=lambda *a, **k: _resultado("", 1))


# -- Interpretar la salida (dato hostil) --------------------------------------


@pytest.mark.parametrize("salida", ["", "no es json", "[1, 2]", "null", json.dumps({"otra": "cosa"})])
def test_salidas_que_no_valen(salida):
    with pytest.raises(MedicionFallida):
        interpretar(salida)


def test_solo_se_toma_lo_esperado_y_acotado():
    salida = json.dumps({
        "lcp_ms": -5, "tbt_ms": "rapido", "cls": 0.05, "extra": "<script>",
        "axe": {"passes": 10, "violations": [
            {"id": "x" * 500, "impact": "critical", "nodes": 2, "help": "h" * 900, "html": "<b>"},
            {"id": "inventado", "impact": "apocaliptico", "nodes": 1, "help": ""},
            "no es un dict",
        ]},
    })
    resultado = interpretar("log del navegador\n" + salida)

    assert "lcp_ms" not in resultado and "tbt_ms" not in resultado
    assert resultado["cls"] == 0.05
    assert "extra" not in resultado
    assert len(resultado["axe"]["violations"]) == 1
    v = resultado["axe"]["violations"][0]
    assert len(v["id"]) == 80 and len(v["help"]) == 200 and set(v) == {"id", "impact", "nodes", "help"}


@pytest.mark.parametrize(
    "clave, valor, esperada",
    [
        ("lcp_ms", 2500, "bueno"), ("lcp_ms", 2501, "mejorable"), ("lcp_ms", 4000, "mejorable"), ("lcp_ms", 4001, "malo"),
        ("tbt_ms", 200, "bueno"), ("tbt_ms", 600, "mejorable"), ("tbt_ms", 601, "malo"),
        ("cls", 0.1, "bueno"), ("cls", 0.25, "mejorable"), ("cls", 0.26, "malo"),
    ],
)
def test_bueno_mejorable_malo_en_los_bordes(clave, valor, esperada):
    assert calificar(clave, valor) == esperada


# -- Puntuacion ---------------------------------------------------------------

ESTATICO_DESEMPENO = {"response_seconds": 0.2, "uses_compression": True, "has_cache_control": True,
                      "render_blocking_scripts": 0, "image_count": 0}
ESTATICO_ACCESIBILIDAD = {"image_count": 0, "declares_language": True, "has_h1": True}


def test_la_medicion_real_sustituye_el_comportamiento_temporal():
    sin = {s["name"]: s for s in subcharacteristics("performance", ESTATICO_DESEMPENO, url=True)}
    con = {s["name"]: s for s in subcharacteristics("performance", {**ESTATICO_DESEMPENO, "browser": SALIDA_BUENA}, url=True)}

    assert sin["Comportamiento temporal"]["origin"] == "qalitiradar"
    assert con["Comportamiento temporal"]["origin"] == "lighthouse"
    assert con["Comportamiento temporal"]["earned"] == 34
    # Lo que no mide el navegador sigue siendo analisis estatico.
    assert con["Utilización de recursos"]["origin"] == "qalitiradar"
    assert con["Utilización de recursos"]["earned"] == sin["Utilización de recursos"]["earned"]


def test_una_pagina_lenta_en_navegador_puntua_menos_aunque_el_servidor_responda_rapido():
    rapida = score_url_dimension("performance", {**ESTATICO_DESEMPENO, "browser": SALIDA_BUENA})
    lenta = score_url_dimension("performance", {**ESTATICO_DESEMPENO, "browser": SALIDA_MALA})
    assert lenta < rapida


def test_con_axe_la_accesibilidad_sale_de_axe_y_suma_cien_como_maximo():
    subs = subcharacteristics("accessibility", {**ESTATICO_ACCESIBILIDAD, "browser": SALIDA_BUENA}, url=True)

    assert {s["origin"] for s in subs if s["measured"]} == {"axe-core"}
    assert sum(s["max"] for s in subs if s["measured"]) == 100
    assert sum(s["earned"] for s in subs if s["measured"]) == 100
    assert score_url_dimension("accessibility", {**ESTATICO_ACCESIBILIDAD, "browser": SALIDA_MALA}) < 100


def test_sin_medicion_la_accesibilidad_es_la_estatica_de_siempre():
    subs = subcharacteristics("accessibility", ESTATICO_ACCESIBILIDAD, url=True)
    assert {s["origin"] for s in subs if s["measured"]} == {"qalitiradar"}
    assert "Perceptible (WCAG)" in {s["name"] for s in subs}


def test_severidad_de_axe_critica_alta_seria_media_y_el_resto_informativo():
    severidades = {f.title.split(": ", 1)[1]: f.severity for f in servicio.hallazgos_de_axe(SALIDA_MALA["axe"]["violations"], None)}

    assert severidades == {
        "Las imágenes tienen texto alternativo": "high",
        "Contraste suficiente": "medium",
        "Contenido en regiones": "info",
        "Zoom permitido": "info",
    }


def test_una_sola_violacion_critica_no_hunde_la_nota_hasta_no_apto():
    """Critica en axe se guarda como ALTA: el techo es el de un hallazgo alto
    (70), no el de uno critico (40). El veredicto "No apto" exige un hallazgo
    critico o una nota por debajo de 40; con esto queda, como mucho, en
    "Apto condicionado"."""
    hallazgos = servicio.hallazgos_de_axe(
        [{"id": "image-alt", "impact": "critical", "nodes": 1, "help": "Texto alternativo"}], None
    )

    assert [h.severity for h in hallazgos] == ["high"]
    assert not any(h.severity == "critical" for h in hallazgos)
    assert calculate_url_overall_score({"performance": 95, "accessibility": 95}, hallazgos) == HIGH_FINDING_SCORE_CAP


# -- Dos tiempos: el estatico ya, la medicion despues --------------------------

EMAIL = "navegador@example.com"


@pytest.fixture
def analisis_de_url():
    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == EMAIL))
            db.commit()
        finally:
            db.close()

    _borrar()
    db = SessionLocal()
    try:
        usuario = User(id=uuid.uuid4(), email=EMAIL, password_hash="x")
        db.add(usuario)
        db.flush()
        app_row = DeployedApp(id=uuid.uuid4(), user_id=usuario.id, url="https://example.com/")
        db.add(app_row)
        db.flush()
        analisis = Analysis(id=uuid.uuid4(), user_id=usuario.id, app_id=app_row.id,
                            analysis_type="url", status="pending")
        db.add(analisis)
        db.commit()
        datos = (usuario.id, analisis.id)
    finally:
        db.close()
    yield datos
    _borrar()


HTML = (
    "<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Una pagina de prueba</title>"
    "<meta name='viewport' content='width=device-width'></head><body><main><h1>Hola</h1>"
    "<img src='a.png'></main></body></html>"
)


def _analisis_estatico(monkeypatch, analisis_id, *, activado=True):
    from app.services import url_analysis_service
    from app.tasks import analyze_repository
    from app.utils.safe_http import FetchResult

    encoladas = []
    monkeypatch.setattr(url_analysis_service, "fetch_public_page", lambda url: FetchResult(
        url=url, status_code=200, headers={"content-type": "text/html"}, text=HTML,
        elapsed_seconds=0.3, content_bytes=len(HTML), redirect_chain=[url],
    ))
    monkeypatch.setattr(url_analysis_service, "get_settings",
                        lambda: SimpleNamespace(navegador_real=activado, huggingface_api_key=""))
    monkeypatch.setattr(analyze_repository, "queue_medicion_navegador", encoladas.append)
    url_analysis_service.run_url_analysis(str(analisis_id))
    return encoladas


def _leer(analisis_id):
    db = SessionLocal()
    try:
        a = db.get(Analysis, analisis_id)
        dims = {d.name: float(d.score) for d in db.scalars(select(Dimension).where(Dimension.analysis_id == analisis_id))}
        hallazgos = db.scalars(select(Finding).where(Finding.analysis_id == analisis_id)).all()
        return a, dims, [(h.severity, h.title) for h in hallazgos]
    finally:
        db.close()


def test_el_estatico_se_entrega_ya_y_la_medicion_queda_pendiente(monkeypatch, analisis_de_url):
    _, analisis_id = analisis_de_url

    encoladas = _analisis_estatico(monkeypatch, analisis_id)

    analisis, dims, _ = _leer(analisis_id)
    assert analisis.status == "completed"
    assert analisis.overall_score is not None
    assert analisis.raw_data["browser"] == {"status": "pending"}
    assert encoladas == [str(analisis_id)]


def test_desactivada_no_se_encola_ni_se_marca_nada(monkeypatch, analisis_de_url):
    _, analisis_id = analisis_de_url

    encoladas = _analisis_estatico(monkeypatch, analisis_id, activado=False)

    analisis, _, _ = _leer(analisis_id)
    assert analisis.status == "completed"
    assert "browser" not in analisis.raw_data
    assert encoladas == []


def test_la_medicion_se_anexa_y_repuntua(monkeypatch, analisis_de_url):
    _, analisis_id = analisis_de_url
    _analisis_estatico(monkeypatch, analisis_id)
    antes, dims_antes, _ = _leer(analisis_id)

    servicio.medir_y_anexar(str(analisis_id), medir_fn=lambda url, c: interpretar(json.dumps(SALIDA_MALA)))

    despues, dims_despues, hallazgos = _leer(analisis_id)
    navegador_ = despues.raw_data["browser"]
    assert navegador_["status"] == "ok"
    assert navegador_["ratings"] == {"lcp_ms": "malo", "tbt_ms": "malo", "cls": "malo"}
    assert dims_despues["performance"] < dims_antes["performance"]
    assert dims_despues["accessibility"] != dims_antes["accessibility"]
    de_axe = [h for h in hallazgos if h[1].startswith(servicio.PREFIJO_HALLAZGO)]
    assert sorted(s for s, _ in de_axe) == ["high", "info", "info", "medium"]
    assert float(despues.overall_score) <= HIGH_FINDING_SCORE_CAP
    # Las metricas estaticas siguen ahi.
    assert "performance" in despues.raw_data

    # Medir otra vez sustituye los hallazgos, no los duplica.
    servicio.medir_y_anexar(str(analisis_id), medir_fn=lambda url, c: interpretar(json.dumps(SALIDA_MALA)))
    _, _, otra_vez = _leer(analisis_id)
    assert len([h for h in otra_vez if h[1].startswith(servicio.PREFIJO_HALLAZGO)]) == 4


@pytest.mark.parametrize(
    "error", [MedicionFallida("La medición en navegador tardó demasiado."), UnsafeUrlError("apunta a 10.0.0.1"), RuntimeError("x")]
)
def test_si_la_medicion_falla_el_analisis_queda_como_estaba(monkeypatch, analisis_de_url, error):
    _, analisis_id = analisis_de_url
    _analisis_estatico(monkeypatch, analisis_id)
    antes, dims_antes, hallazgos_antes = _leer(analisis_id)

    def falla(url, c):
        raise error

    servicio.medir_y_anexar(str(analisis_id), medir_fn=falla)

    despues, dims_despues, hallazgos_despues = _leer(analisis_id)
    assert despues.status == "completed"
    assert despues.raw_data["browser"]["status"] == "failed"
    assert despues.raw_data["browser"]["reason"]
    assert dims_despues == dims_antes
    assert despues.overall_score == antes.overall_score
    assert hallazgos_despues == hallazgos_antes


def test_la_api_devuelve_el_estado_de_la_medicion(monkeypatch, analisis_de_url):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.main import app

    usuario_id, analisis_id = analisis_de_url
    _analisis_estatico(monkeypatch, analisis_id)
    navegador_api = TestClient(app, headers={"Authorization": f"Bearer {create_access_token(usuario_id)}"})

    assert navegador_api.get(f"/api/analyses/{analisis_id}").json()["browser"] == {
        "status": "pending", "reason": None, "measured_at": None, "lcp_ms": None, "tbt_ms": None, "cls": None,
        "ratings": {}, "axe_violations": [], "axe_passes": None,
    }

    servicio.medir_y_anexar(str(analisis_id), medir_fn=lambda url, c: interpretar(json.dumps(SALIDA_MALA)))
    datos = navegador_api.get(f"/api/analyses/{analisis_id}").json()
    assert datos["browser"]["status"] == "ok"
    assert datos["browser"]["ratings"]["lcp_ms"] == "malo"
    assert {v["impact"] for v in datos["browser"]["axe_violations"]} == {"critical", "serious", "moderate", "minor"}
    perf = next(d for d in datos["dimensions"] if d["name"] == "performance")
    assert {s["name"]: s["origin"] for s in perf["subcharacteristics"]}["Comportamiento temporal"] == "lighthouse"


def test_nan_e_infinito_no_cuelan():
    """`json.loads` acepta NaN e Infinity; una comparacion con NaN siempre da
    falso y puntuaria como si fuera buena."""
    resultado = interpretar('{"lcp_ms": NaN, "tbt_ms": Infinity, "cls": 0.1}')
    assert resultado == {"cls": 0.1}
