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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # El cliente lo guarda para renovar el acceso sin volver a pedir
    # credenciales. Ausente en la respuesta de /refresh, que no lo rota.
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
