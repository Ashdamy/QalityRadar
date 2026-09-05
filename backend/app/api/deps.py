from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db as _get_db
from app.core.security import COOKIE_ACCESS, decode_access_token
from app.models.user import User

get_db = _get_db  # re-exportado para que los routers importen solo desde app.api.deps


def get_current_user(
    authorization: str | None = Header(default=None),
    acceso_en_cookie: str | None = Cookie(default=None, alias=COOKIE_ACCESS),
    db: Session = Depends(get_db),
) -> User:
    """Acepta la sesion de dos sitios, en este orden.

    La cabecera primero: quien la manda lo hace a proposito (un script, una
    prueba), y una cookie olvidada en el navegador no debe pisar una peticion
    explicita.

    La cookie despues, que es como viaja la sesion en el navegador. Es
    httpOnly: JavaScript no puede leerla, asi que un XSS no puede robarla.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
    elif acceso_en_cookie:
        token = acceso_en_cookie

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    try:
        user_id = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user
