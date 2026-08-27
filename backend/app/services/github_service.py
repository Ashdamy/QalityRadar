import httpx

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"


def exchange_code_for_token(code: str) -> str:
    from app.core.config import get_settings

    settings = get_settings()
    response = httpx.post(
        GITHUB_OAUTH_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.github_oauth_redirect_uri,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_github_user(token: str) -> dict:
    response = httpx.get(
        f"{GITHUB_API_BASE}/user", headers={"Authorization": f"Bearer {token}"}, timeout=10
    )
    response.raise_for_status()
    return response.json()


def fetch_github_primary_email(token: str) -> str:
    response = httpx.get(
        f"{GITHUB_API_BASE}/user/emails", headers={"Authorization": f"Bearer {token}"}, timeout=10
    )
    response.raise_for_status()
    emails = response.json()
    primary = next((e for e in emails if e.get("primary")), emails[0])
    return primary["email"]
