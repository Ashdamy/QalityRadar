from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analyses import router as analyses_router
from app.api.auth import router as auth_router
from app.api.repositories import router as repositories_router
from app.core.config import get_settings

app = FastAPI(title="QalitiRadar API")

# Sin esto el navegador bloquea toda llamada del frontend a la API: son
# origenes distintos (localhost:3000 -> localhost:8000). La lista de origenes
# es explicita, nunca "*", porque las peticiones llevan el token de sesion.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(repositories_router)
app.include_router(analyses_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
