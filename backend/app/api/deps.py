from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.database import get_db as _get_db

get_db = _get_db  # re-exportado para que los routers importen solo desde app.api.deps
