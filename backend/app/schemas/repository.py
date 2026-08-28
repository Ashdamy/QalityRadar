from pydantic import BaseModel


class RepositoryOut(BaseModel):
    id: str
    name: str
    full_name: str
    is_private: bool
    # Fecha del ultimo analisis completado, o None si nunca se analizo.
    last_analyzed_at: str | None = None
