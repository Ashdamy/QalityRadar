from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analyses import router as analyses_router
from app.api.apps import router as apps_router
from app.api.auth import router as auth_router
from app.api.history import router as history_router
from app.api.monitors import router as monitors_router
from app.api.notifications import router as notifications_router
from app.api.repositories import router as repositories_router
from app.api.share import router as share_router
from app.core.config import get_settings

_settings = get_settings()

app = FastAPI(
    title="QalitiRadar API",
    # Ver `enable_api_docs` en la configuracion: en produccion se apagan.
    docs_url="/docs" if _settings.enable_api_docs else None,
    redoc_url="/redoc" if _settings.enable_api_docs else None,
    openapi_url="/openapi.json" if _settings.enable_api_docs else None,
)


# Ningun cuerpo legitimo de esta API se acerca: lo mas grande que se recibe es
# un JSON con una URL y un nombre. Sin tope, una sola peticion puede reservar
# toda la memoria del proceso antes de que nadie mire lo que trae.
MAX_REQUEST_BYTES = 64 * 1024


@app.middleware("http")
async def limitar_tamano_del_cuerpo(request: Request, call_next):
    """Rechaza cuerpos desmedidos por lo que declaran, antes de leerlos.

    Se mira `Content-Length` porque es lo unico que se sabe antes de gastar
    memoria. Quien no lo declare (`Transfer-Encoding: chunked`) se cuela de
    esta comprobacion; ese caso lo corta el proxy inverso, que es quien puede
    hacerlo sin haber leido nada.
    """
    declarado = request.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > MAX_REQUEST_BYTES:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "el cuerpo de la peticion es demasiado grande"},
        )
    return await call_next(request)


@app.middleware("http")
async def cabeceras_de_seguridad(request, call_next):
    """Cabeceras que el navegador necesita para no confiar de mas en la API.

    Resulta que QalitiRadar penalizaba a otros sitios por no enviarlas y la
    propia API no enviaba ninguna.

    HSTS no se pone aqui: la termina el proxy inverso, que es quien sabe si la
    conexion es realmente HTTPS. Emitirla desde la aplicacion en local, por
    HTTP, dejaria el dominio inaccesible en el navegador.
    """
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    # La API no se muestra en ninguna pagina, asi que nadie deberia poder
    # incrustarla.
    respuesta.headers["X-Frame-Options"] = "DENY"
    # Que la URL completa no viaje a terceros al seguir un enlace.
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    # La API devuelve JSON: no necesita camara, microfono ni ubicacion.
    respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Nada de lo que sirve la API deberia ejecutarse ni incrustarse.
    respuesta.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return respuesta

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
app.include_router(history_router)
app.include_router(apps_router)
app.include_router(share_router)
app.include_router(notifications_router)
app.include_router(monitors_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
