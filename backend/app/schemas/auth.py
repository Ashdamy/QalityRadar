from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    # bcrypt (4.x) raises on passwords over 72 bytes, which would otherwise
    # surface as a 500 from /register. Reject too-long passwords at the
    # validation layer instead.
    password: str = Field(max_length=72)


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
