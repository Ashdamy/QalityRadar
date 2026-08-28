"""Análisis de aplicaciones desplegadas (Modo 2)."""

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.analyzers.url.page_quality import (
    AccessibilityAnalyzer,
    CompatibilityAnalyzer,
    PerformanceAnalyzer,
    UsabilityAnalyzer,
)
from app.analyzers.url.security_headers import SecurityHeadersAnalyzer
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.analysis import Analysis, Dimension
from app.models.deployed_app import DeployedApp
from app.models.user import User
from app.services.scoring_service import URL_WEIGHTS, score_url_dimension
from app.utils.safe_http import FetchResult
from app.utils.url_validation import UnsafeUrlError

client = TestClient(app)

TEST_EMAIL = "url-analisis@example.com"


def _fetched(*, url="https://ejemplo.test/", headers=None, html="", seconds=0.4, size=1000,
             chain=None, status=200) -> FetchResult:
    return FetchResult(
        url=url,
        status_code=status,
        headers=headers or {},
        text=html,
        elapsed_seconds=seconds,
        content_bytes=size,
        redirect_chain=chain or [url],
    )


def _limpiar() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == TEST_EMAIL))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean():
    _limpiar()
    yield
    _limpiar()


# --- Cabeceras de seguridad --------------------------------------------------


def test_http_without_tls_is_critical():
    r = SecurityHeadersAnalyzer().analyze(_fetched(url="http://ejemplo.test/"))
    assert r.metrics["uses_https"] is False
    assert any(f.severity == "critical" for f in r.findings)
    # Sin cifrado la nota se hunde por mucho que hubiera otras cabeceras.
    assert score_url_dimension("security", r.metrics) <= 10


def test_a_fully_hardened_site_scores_full_security():
    headers = {
        "strict-transport-security": "max-age=31536000; includeSubDomains",
        "content-security-policy": (
            "default-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        ),
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
        "referrer-policy": "no-referrer",
        "permissions-policy": "geolocation=()",
        "cross-origin-opener-policy": "same-origin",
    }
    r = SecurityHeadersAnalyzer().analyze(_fetched(headers=headers))
    assert r.findings == []
    assert score_url_dimension("security", r.metrics) == 100.0


def test_a_partial_csp_is_flagged_without_being_treated_as_missing():
    r = SecurityHeadersAnalyzer().analyze(
        _fetched(headers={"content-security-policy": "script-src 'self'"})
    )
    assert r.metrics["has_csp"] is True
    titulos = [f.title for f in r.findings]
    assert any("directivas importantes" in x for x in titulos)
    assert not any("Falta la pol" in x for x in titulos)


def test_a_report_only_csp_does_not_count_as_protection():
    r = SecurityHeadersAnalyzer().analyze(
        _fetched(headers={"content-security-policy-report-only": "default-src 'self'"})
    )
    assert r.metrics["csp_is_report_only"] is True
    assert any("solo informe" in f.title for f in r.findings)


def test_cookies_without_protective_flags_are_reported():
    r = SecurityHeadersAnalyzer().analyze(
        _fetched(headers={"set-cookie": "sesion=abc123; Path=/"})
    )
    assert r.metrics["cookie_count"] == 1
    assert r.metrics["cookies_without_httponly"] == 1
    assert r.metrics["cookies_without_secure"] == 1
    assert r.metrics["cookies_without_samesite"] == 1
    titulos = " ".join(f.title for f in r.findings)
    assert "JavaScript" in titulos
    assert "SameSite" in titulos


def test_fully_protected_cookies_produce_no_cookie_findings():
    r = SecurityHeadersAnalyzer().analyze(
        _fetched(headers={"set-cookie": "sesion=abc; Secure; HttpOnly; SameSite=Lax"})
    )
    assert r.metrics["cookies_without_httponly"] == 0
    assert not any("cookies" in f.title.lower() for f in r.findings)


def test_mixed_content_on_an_https_page_is_reported():
    html = '<html><body><img src="http://inseguro.test/a.png"></body></html>'
    r = SecurityHeadersAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["mixed_content_count"] == 1
    assert any("HTTP en una p" in f.title for f in r.findings)


def test_external_scripts_without_integrity_are_reported():
    html = (
        '<html><head>'
        '<script src="https://cdn.ajeno.test/a.js"></script>'
        '<script src="https://cdn.ajeno.test/b.js" integrity="sha384-x"></script>'
        '<script src="/propio.js"></script>'
        "</head></html>"
    )
    r = SecurityHeadersAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["external_script_count"] == 2
    assert r.metrics["external_scripts_without_sri"] == 1


def test_a_form_posting_over_http_is_critical():
    html = '<html><body><form action="http://inseguro.test/login"></form></body></html>'
    r = SecurityHeadersAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["form_posts_over_http"] is True
    assert any(f.severity == "critical" for f in r.findings)


def test_a_wildcard_cors_header_is_reported():
    r = SecurityHeadersAnalyzer().analyze(
        _fetched(headers={"access-control-allow-origin": "*"})
    )
    assert r.metrics["cors_allows_any_origin"] is True


def test_unsafe_inline_in_the_csp_is_reported():
    r = SecurityHeadersAnalyzer().analyze(
        _fetched(headers={"content-security-policy": "script-src 'unsafe-inline'"})
    )
    assert r.metrics["csp_allows_unsafe_inline"] is True
    assert any("línea" in f.title for f in r.findings)


def test_a_short_hsts_is_flagged_but_not_as_missing():
    r = SecurityHeadersAnalyzer().analyze(
        _fetched(headers={"strict-transport-security": "max-age=3600"})
    )
    assert r.metrics["hsts_max_age"] == 3600
    titulos = [f.title for f in r.findings]
    assert any("duración corta" in t for t in titulos)
    assert not any("Falta la cabecera HSTS" in t for t in titulos)


def test_a_server_version_banner_is_reported():
    r = SecurityHeadersAnalyzer().analyze(_fetched(headers={"server": "nginx/1.18.0"}))
    assert r.metrics["leaks_server_version"] is True


# --- Rendimiento -------------------------------------------------------------


def test_a_slow_response_is_reported():
    r = PerformanceAnalyzer().analyze(_fetched(seconds=3.5))
    assert any(f.severity == "high" for f in r.findings)


def test_compression_and_cache_raise_the_performance_score():
    lento = PerformanceAnalyzer().analyze(_fetched(seconds=1.5))
    rapido = PerformanceAnalyzer().analyze(
        _fetched(seconds=0.2, headers={"content-encoding": "br", "cache-control": "max-age=600"})
    )
    assert score_url_dimension("performance", rapido.metrics) > score_url_dimension(
        "performance", lento.metrics
    )


# --- Accesibilidad -----------------------------------------------------------


def test_images_without_alt_are_reported():
    html = '<html lang="es"><body><img src="a.png"><img src="b.png" alt="b"><h1>t</h1></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["image_count"] == 2
    assert r.metrics["images_without_alt"] == 1


def test_an_input_labelled_by_a_label_for_is_not_reported():
    html = (
        '<html lang="es"><body><h1>t</h1>'
        '<label for="correo">Correo</label><input id="correo" type="email">'
        "</body></html>"
    )
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["inputs_without_label"] == 0


def test_an_unlabelled_input_is_reported_as_high():
    html = '<html lang="es"><body><h1>t</h1><input type="text"></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["inputs_without_label"] == 1
    assert any(f.severity == "high" for f in r.findings)


def test_hidden_and_submit_inputs_do_not_need_a_label():
    html = '<html lang="es"><body><h1>t</h1><input type="hidden" name="csrf"><input type="submit"></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["inputs_without_label"] == 0
    assert r.findings == []


def test_a_missing_lang_attribute_is_reported():
    r = AccessibilityAnalyzer().analyze(_fetched(html="<html><body><h1>t</h1></body></html>"))
    assert r.metrics["declares_language"] is False


# --- SEO y compatibilidad ----------------------------------------------------


def test_a_page_without_viewport_is_flagged_as_high():
    r = CompatibilityAnalyzer().analyze(_fetched(html="<html><title>t</title></html>"))
    assert r.metrics["has_viewport"] is False
    assert any(f.severity == "high" for f in r.findings)


def test_a_page_without_doctype_or_charset_is_reported():
    r = CompatibilityAnalyzer().analyze(
        _fetched(html='<html><meta name="viewport" content="width=device-width"></html>')
    )
    assert r.metrics["has_doctype"] is False
    assert r.metrics["declares_charset"] is False
    titulos = " ".join(f.title for f in r.findings)
    assert "tipo de documento" in titulos
    assert "codificaci" in titulos


def test_deprecated_html_tags_are_reported():
    r = CompatibilityAnalyzer().analyze(
        _fetched(html="<html><body><center><font>hola</font></center></body></html>")
    )
    assert set(r.metrics["deprecated_tags"]) == {"center", "font"}
    assert any("obsoletas" in f.title for f in r.findings)


def test_a_standards_compliant_page_scores_full_compatibility():
    html = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link rel="manifest" href="/m.json"></head>'
        "<body><picture><img src=a.png alt=a></picture></body></html>"
    )
    r = CompatibilityAnalyzer().analyze(_fetched(html=html))
    assert r.findings == []
    assert score_url_dimension("compatibility", r.metrics) == 100.0


# --- Usabilidad --------------------------------------------------------------


def test_a_page_without_favicon_or_social_metadata_is_reported():
    r = UsabilityAnalyzer().analyze(_fetched(html="<html><title>Un titulo valido</title></html>"))
    assert r.metrics["has_favicon"] is False
    assert r.metrics["has_open_graph"] is False
    titulos = " ".join(f.title for f in r.findings)
    assert "icono" in titulos
    assert "redes" in titulos


def test_a_well_presented_page_scores_full_usability():
    html = (
        "<html><head><title>Un titulo perfectamente razonable</title>"
        '<meta name="description" content="d"><meta name="theme-color" content="#000">'
        '<link rel="icon" href="/f.ico"><link rel="canonical" href="https://x.test/">'
        '<meta property="og:title" content="t"></head>'
        "<body><nav></nav><main><h1>t</h1></main></body></html>"
    )
    r = UsabilityAnalyzer().analyze(_fetched(html=html))
    assert r.findings == []
    assert score_url_dimension("usability", r.metrics) == 100.0


# --- Accesibilidad ampliada --------------------------------------------------


def test_blocking_zoom_is_reported_as_high():
    html = '<html lang="es"><head><meta name="viewport" content="width=device-width, user-scalable=no"></head><body><h1>t</h1></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["blocks_zoom"] is True
    assert any(f.severity == "high" and "ampliar" in f.title for f in r.findings)


def test_skipping_heading_levels_is_reported():
    html = '<html lang="es"><body><h1>a</h1><h4>b</h4></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["heading_level_skips"] == 1
    assert any("jerarqu" in f.title for f in r.findings)


def test_duplicate_ids_are_reported():
    html = '<html lang="es"><body><h1>t</h1><div id="x"></div><span id="x"></span></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["duplicate_id_count"] == 1
    assert any("duplicados" in f.title for f in r.findings)


def test_iframes_without_a_title_are_reported():
    html = '<html lang="es"><body><h1>t</h1><iframe src="/a"></iframe></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["iframes_without_title"] == 1


def test_positive_tabindex_is_reported():
    html = '<html lang="es"><body><h1>t</h1><div tabindex="3"></div></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["positive_tabindex_count"] == 1


def test_autoplay_media_is_reported():
    html = '<html lang="es"><body><h1>t</h1><video autoplay src="a.mp4"></video></body></html>'
    r = AccessibilityAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["has_autoplay_media"] is True


# --- Rendimiento ampliado ----------------------------------------------------


def test_render_blocking_scripts_are_reported():
    html = "<html><head><script src=\"/a.js\"></script></head><body></body></html>"
    r = PerformanceAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["render_blocking_scripts"] == 1
    assert any("bloquean el dibujado" in f.title for f in r.findings)


def test_deferred_scripts_do_not_block_rendering():
    html = "<html><head><script src=\"/a.js\" defer></script></head><body></body></html>"
    r = PerformanceAnalyzer().analyze(_fetched(html=html))
    assert r.metrics["render_blocking_scripts"] == 0


def test_images_without_dimensions_are_reported():
    imgs = "".join(f'<img src="{i}.png" alt="a">' for i in range(6))
    r = PerformanceAnalyzer().analyze(_fetched(html=f"<html><body>{imgs}</body></html>"))
    assert r.metrics["images_without_dimensions"] == 6
    assert any("dimensiones" in f.title for f in r.findings)


# --- Pesos -------------------------------------------------------------------


def test_url_weights_match_the_spec():
    assert URL_WEIGHTS["performance"] == 0.25
    assert URL_WEIGHTS["security"] == 0.25
    assert URL_WEIGHTS["usability"] == 0.20
    assert URL_WEIGHTS["accessibility"] == 0.15
    assert URL_WEIGHTS["compatibility"] == 0.15
    assert sum(URL_WEIGHTS.values()) == pytest.approx(1.0)


# --- Endpoint ----------------------------------------------------------------


@pytest.fixture
def usuario():
    db = SessionLocal()
    try:
        user = User(id=uuid.uuid4(), email=TEST_EMAIL, github_id=960000001)
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def test_analyze_url_queues_an_analysis(usuario, monkeypatch):
    from app.api import apps as apps_module

    encolado = {}
    monkeypatch.setattr(
        apps_module, "queue_url_analysis", lambda aid: encolado.setdefault("id", aid)
    )

    r = client.post(
        "/api/apps/analyze",
        json={"url": "https://example.com", "name": "mi app"},
        headers={"Authorization": f"Bearer {create_access_token(usuario)}"},
    )

    assert r.status_code == 202
    analysis_id = r.json()["analysis_id"]
    assert encolado["id"] == analysis_id

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        assert analysis.analysis_type == "url"
        assert analysis.app_id is not None
    finally:
        db.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:8000/",
        "http://10.0.0.5/",
        "file:///etc/passwd",
    ],
)
def test_internal_addresses_are_rejected_before_anything_is_stored(usuario, url):
    r = client.post(
        "/api/apps/analyze",
        json={"url": url},
        headers={"Authorization": f"Bearer {create_access_token(usuario)}"},
    )
    assert r.status_code == 400

    # No debe quedar registrada una aplicacion que no vamos a analizar.
    db = SessionLocal()
    try:
        assert db.scalars(select(DeployedApp).where(DeployedApp.url == url)).first() is None
    finally:
        db.close()


def test_analyze_url_without_a_token_is_rejected():
    r = client.post("/api/apps/analyze", json={"url": "https://example.com"})
    assert r.status_code == 401


def test_a_failed_fetch_marks_the_analysis_failed(usuario, monkeypatch):
    from app.services import url_analysis_service

    def _explota(url):
        raise httpx.ConnectError("sin conexion")

    monkeypatch.setattr(url_analysis_service, "fetch_public_page", _explota)

    db = SessionLocal()
    try:
        app_row = DeployedApp(id=uuid.uuid4(), user_id=usuario, name="x", url="https://example.com")
        db.add(app_row)
        db.flush()
        analysis = Analysis(
            id=uuid.uuid4(), user_id=usuario, app_id=app_row.id,
            analysis_type="url", status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    url_analysis_service.run_url_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.status == "failed"
        assert "no se pudo conectar" in analysis.error_message
    finally:
        db.close()


def test_an_ssrf_redirect_marks_the_analysis_failed_with_the_reason(usuario, monkeypatch):
    """Si la URL redirige a una direccion interna, el motivo se muestra."""
    from app.services import url_analysis_service

    def _inseguro(url):
        raise UnsafeUrlError("la direccion apunta a 169.254.169.254, que es una IP interna")

    monkeypatch.setattr(url_analysis_service, "fetch_public_page", _inseguro)

    db = SessionLocal()
    try:
        app_row = DeployedApp(id=uuid.uuid4(), user_id=usuario, name="x", url="https://example.com")
        db.add(app_row)
        db.flush()
        analysis = Analysis(
            id=uuid.uuid4(), user_id=usuario, app_id=app_row.id,
            analysis_type="url", status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    url_analysis_service.run_url_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.status == "failed"
        assert "interna" in analysis.error_message
    finally:
        db.close()


def test_a_full_url_analysis_persists_five_dimensions(usuario, monkeypatch):
    from app.services import url_analysis_service

    html = (
        '<html lang="es"><head><title>Una pagina de prueba</title>'
        '<meta name="description" content="d"><meta name="viewport" content="width=device-width">'
        "</head><body><main><h1>Hola</h1><img src='a.png' alt='a'></main></body></html>"
    )
    monkeypatch.setattr(
        url_analysis_service,
        "fetch_public_page",
        lambda url: _fetched(
            url=url,
            html=html,
            headers={"content-encoding": "gzip", "cache-control": "max-age=60"},
        ),
    )

    db = SessionLocal()
    try:
        app_row = DeployedApp(id=uuid.uuid4(), user_id=usuario, name="x", url="https://example.com")
        db.add(app_row)
        db.flush()
        analysis = Analysis(
            id=uuid.uuid4(), user_id=usuario, app_id=app_row.id,
            analysis_type="url", status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    url_analysis_service.run_url_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.status == "completed", analysis.error_message
        assert 0 <= float(analysis.overall_score) <= 100

        dims = db.scalars(select(Dimension).where(Dimension.analysis_id == analysis_id)).all()
        assert {d.name for d in dims} == set(URL_WEIGHTS)
    finally:
        db.close()
