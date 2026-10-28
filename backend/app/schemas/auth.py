from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    # El maximo lo impone bcrypt, que lanza por encima de 72 bytes y eso
    # llegaria como un 500. El minimo es una decision nuestra: sin el se podia
    # registrar una cuenta con una contrasena de un solo caracter.
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(max_length=2048)


class TokenResponse(BaseModel):
    """Los tokens van siempre en cookies httpOnly; en el cuerpo, solo a veces.

    Estan ausentes cuando la peticion llego con la sesion en cookies. Si
    `/refresh` los devolviera tambien en ese caso, un XSS podria llamarlo
    —el navegador adjunta la cookie solo— y leer la respuesta: las cookies
    httpOnly no habrian servido de nada.

    Se siguen devolviendo a quien manda el token de refresco en el cuerpo, que
    por definicion no es un navegador y ya lo tenia.
    """

    access_token: str | None = None
    token_type: str = "bearer"
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    # Opcional: un navegador no lo manda, lo lleva en la cookie.
    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class DeleteAccountRequest(BaseModel):
    # Obligatoria si la cuenta tiene contrasena. Borrar es irreversible, y una
    # sesion abierta en un ordenador prestado no deberia bastar.
    password: str | None = None
