import uuid

from cryptography.fernet import InvalidToken
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api import repositories as repositories_module
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import github_service

client = TestClient(app)

# Fixed email so this file's own extra fixture (a user without a GitHub
# token) is cleaned up deterministically, same pattern as every other test
# module in this suite.
NO_GITHUB_TOKEN_EMAIL = "repo-list-no-github@example.com"


def _delete_no_github_token_user():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == NO_GITHUB_TOKEN_EMAIL))
        db.commit()
    finally:
        db.close()


def test_list_repositories_maps_is_private_field_through_faithfully(monkeypatch, db_session_with_github_user):
    user = db_session_with_github_user
    # Includes one private repo so the assertion below actually exercises
    # the is_private mapping instead of passing vacuously (this endpoint
    # delegates "public only" filtering to GitHub's visibility=public param
    # rather than filtering locally -- see list_public_repos -- so the
    # response should faithfully pass through whatever GitHub returns).
    monkeypatch.setattr(
        github_service, "list_public_repos",
        lambda token: [
            {"id": 1, "name": "qaliti-radar", "full_name": "juan/qaliti-radar", "private": False},
            {"id": 2, "name": "side-project", "full_name": "juan/side-project", "private": False},
            {"id": 3, "name": "secret-project", "full_name": "juan/secret-project", "private": True},
        ],
    )

    token = create_access_token(user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    # El endpoint devuelve NUESTRO identificador (el repositorio se persiste al
    # listarlo, para poder analizarlo despues), no el numerico de GitHub, asi
    # que la correspondencia se comprueba por full_name.
    by_full_name = {repo["full_name"]: repo for repo in body}
    assert by_full_name["juan/qaliti-radar"]["is_private"] is False
    assert by_full_name["juan/side-project"]["is_private"] is False
    assert by_full_name["juan/secret-project"]["is_private"] is True
    # Cada id devuelto debe ser un UUID nuestro, utilizable en /analyze.
    for repo in body:
        uuid.UUID(repo["id"])


def test_list_repositories_without_token_returns_401():
    response = client.get("/api/repositories")
    assert response.status_code == 401


def test_list_repositories_with_malformed_header_returns_401():
    response = client.get("/api/repositories", headers={"Authorization": "not-a-bearer-header"})
    assert response.status_code == 401


def test_list_repositories_with_invalid_token_returns_401():
    response = client.get("/api/repositories", headers={"Authorization": "Bearer this.is.not-a-valid-jwt"})
    assert response.status_code == 401


def test_list_repositories_with_token_for_nonexistent_user_returns_401():
    # Valid JWT, correctly signed, but for a user id that has no row in the
    # database (e.g. deleted after the token was issued).
    token = create_access_token(uuid.uuid4())
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_list_repositories_with_undecryptable_token_returns_400(monkeypatch, db_session_with_github_user):
    """If ENCRYPTION_KEY was rotated (or the stored value is otherwise
    corrupt), decrypt_token raises cryptography.fernet.InvalidToken. This
    must not surface as an unhandled 500 -- it should be the same 400 the
    "no token at all" case returns, so the client's remedy (reconnect
    GitHub) is identical either way."""

    user = db_session_with_github_user

    def _raise_invalid_token(_encrypted):
        raise InvalidToken()

    monkeypatch.setattr(repositories_module, "decrypt_token", _raise_invalid_token)

    token = create_access_token(user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 400
    assert response.json()["detail"] == "GitHub account not connected"


def test_list_repositories_for_user_without_github_token_returns_400():
    _delete_no_github_token_user()
    db = SessionLocal()
    try:
        user = User(
            id=uuid.uuid4(),
            email=NO_GITHUB_TOKEN_EMAIL,
            password_hash="not-a-real-hash",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    try:
        token = create_access_token(user_id)
        response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 400
        assert response.json()["detail"] == "GitHub account not connected"
    finally:
        _delete_no_github_token_user()


def test_an_expired_github_token_asks_to_reconnect_not_github_unavailable(
    monkeypatch, db_session_with_github_user
):
    """GitHub invalida los tokens al regenerar el client secret o al revocar
    la autorizacion. Eso no es una caida de GitHub: decir "no disponible"
    dejaria al usuario sin saber que hacer, cuando la salida es reconectar.
    """
    import httpx

    from app.services import github_service

    def _token_invalido(method, url, **kwargs):
        return httpx.Response(
            401,
            json={"message": "Bad credentials"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(github_service.httpx, "request", _token_invalido)

    token = create_access_token(db_session_with_github_user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 400
    assert response.json()["detail"] == "GitHub account not connected"


def test_a_real_github_outage_is_still_reported_as_unavailable(
    monkeypatch, db_session_with_github_user
):
    import httpx

    from app.services import github_service

    def _caido(method, url, **kwargs):
        return httpx.Response(503, text="down", request=httpx.Request(method, url))

    monkeypatch.setattr(github_service.httpx, "request", _caido)

    token = create_access_token(db_session_with_github_user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 502


def test_the_listing_reports_when_each_repository_was_last_analyzed(
    monkeypatch, db_session_with_github_user
):
    """La columna de "ultimo analisis" se alimenta de este campo. Estuvo
    escrita a mano en la interfaz porque el dato no se exponia, y mostraba
    siempre "Nunca analizado" aunque el repositorio si se hubiera analizado.
    """
    from datetime import datetime, timezone

    from app.models.repository import Repository

    user = db_session_with_github_user
    monkeypatch.setattr(
        github_service,
        "list_public_repos",
        lambda token: [
            {"id": 4001, "name": "sin-analizar", "full_name": "juan/sin-analizar", "private": False},
            {"id": 4002, "name": "analizado", "full_name": "juan/analizado", "private": False},
        ],
    )

    token = create_access_token(user.id)
    # Primer listado: ninguno se ha analizado todavia.
    primero = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"}).json()
    assert all(r["last_analyzed_at"] is None for r in primero)

    # Se marca uno como analizado, igual que hace el pipeline al terminar.
    momento = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        repo = db.scalars(
            select_repository_by_full_name("juan/analizado")
        ).one()
        repo.last_analyzed_at = momento
        db.commit()
    finally:
        db.close()

    segundo = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"}).json()
    por_nombre = {r["full_name"]: r for r in segundo}
    assert por_nombre["juan/sin-analizar"]["last_analyzed_at"] is None
    assert por_nombre["juan/analizado"]["last_analyzed_at"] is not None
    assert por_nombre["juan/analizado"]["last_analyzed_at"].startswith(
        momento.strftime("%Y-%m-%d")
    )


def select_repository_by_full_name(full_name: str):
    from sqlalchemy import select

    from app.models.repository import Repository

    return select(Repository).where(Repository.full_name == full_name)
