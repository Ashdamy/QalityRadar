import httpx
from fastapi import HTTPException, status

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"


def _github_request(method: str, url: str, **kwargs) -> httpx.Response:
    """Perform an HTTP call to GitHub, translating any failure into a safe,
    fixed-message HTTPException. Never echoes GitHub's raw response body,
    the authorization code, or any token into the error detail."""

    try:
        response = httpx.request(method, url, timeout=10, **kwargs)
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="GitHub is unavailable"
        ) from exc
    return response


def exchange_code_for_token(code: str) -> str:
    from app.core.config import get_settings

    settings = get_settings()
    response = _github_request(
        "POST",
        GITHUB_OAUTH_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.github_oauth_redirect_uri,
        },
    )
    # GitHub's token endpoint returns HTTP 200 even for a bad/expired/reused
    # `code`, with an error body such as {"error": "bad_verification_code"}
    # instead of an "access_token" field. raise_for_status() above does not
    # catch this, so it must be checked explicitly.
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid or expired GitHub authorization code",
        )
    return token


def fetch_github_user(token: str) -> dict:
    response = _github_request(
        "GET", f"{GITHUB_API_BASE}/user", headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()


def fetch_github_primary_email(token: str) -> str:
    response = _github_request(
        "GET", f"{GITHUB_API_BASE}/user/emails", headers={"Authorization": f"Bearer {token}"}
    )
    emails = response.json()
    primary = next((e for e in emails if e.get("primary")), emails[0])
    return primary["email"]


def list_public_repos(token: str) -> list[dict]:
    response = _github_request(
        "GET",
        f"{GITHUB_API_BASE}/user/repos",
        headers={"Authorization": f"Bearer {token}"},
        params={"visibility": "public", "per_page": 100},
    )
    return response.json()
