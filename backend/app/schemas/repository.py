from pydantic import BaseModel


class RepositoryOut(BaseModel):
    id: str
    name: str
    full_name: str
    is_private: bool
