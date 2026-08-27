# Week 1 — Setup + Autenticación Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levantar la infraestructura base (Docker Compose, Postgres, Redis) y permitir que un usuario se registre/loguee y conecte su cuenta de GitHub (scope `public_repo`) para ver la lista de sus repositorios públicos.

**Architecture:** Backend FastAPI síncrono (SQLAlchemy 2.0 sync, no async/await) corriendo en threadpool de FastAPI; Postgres vía `psycopg` v3; JWT propio (no NextAuth) con refresh tokens rotativos persistidos en `refresh_tokens`; GitHub OAuth "Authorization Code" flow manual (sin Authlib) para mantener el control explícito sobre los scopes solicitados.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, psycopg[binary] v3, PyJWT, bcrypt, cryptography (Fernet), httpx, pytest.

**Spec:** [`../../../context/claude.md`](../../../context/claude.md), [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md), [`../../DATA_MODEL.md`](../../DATA_MODEL.md), [`../../ROADMAP.md`](../../ROADMAP.md) (sección "Semana 1")

## Global Constraints

- Todas las funciones de endpoint y de acceso a datos son **síncronas** (no `async def`) — FastAPI las corre en threadpool automáticamente; no mezclar con `httpx.AsyncClient`.
- GitHub OAuth solicita únicamente los scopes `public_repo read:user user:email` (decisión de MVP ya acordada — no pedir `repo`).
- `github_access_token` se persiste SIEMPRE cifrado con Fernet (`utils/crypto.py`), nunca en texto plano en DB ni en logs.
- Ningún comando de shell se construye con f-strings/interpolación de input de usuario (aplica sobre todo a partir de la Semana 2, pero la convención empieza aquí).
- Migraciones Alembic contienen SQL explícito (`op.execute`) que debe coincidir literalmente con el DDL de `DATA_MODEL.md` — la fuente de verdad del esquema es ese documento, no el autogenerate de Alembic.
- **Fuera de alcance de este plan (deferred):** las páginas de frontend (login/registro, conectar GitHub, lista de repos) no se implementan aquí. Se avisará antes de planearlas porque requieren una conversación de diseño visual primero (skill `frontend-design`). Este plan cubre solo el scaffold vacío de Next.js y el backend completo.

---

### Task 1: Scaffolding del proyecto y Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `frontend/Dockerfile` (placeholder mínimo, sin páginas)
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `GET /health` → `{"status": "ok"}`, usado por los healthchecks de Docker Compose y por tareas futuras de monitoreo (Semana 5).

- [ ] **Step 1: Crear `backend/requirements.txt`**

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
alembic==1.13.3
psycopg[binary]==3.2.3
pydantic-settings==2.5.2
pyjwt==2.9.0
bcrypt==4.2.0
cryptography==43.0.1
httpx==0.27.2
celery==5.4.0
redis==5.1.1
pytest==8.3.3
pytest-mock==3.14.0
```

- [ ] **Step 2: Escribir `backend/app/main.py` con el endpoint de salud**

```python
from fastapi import FastAPI

app = FastAPI(title="QualityRadar API")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 3: Escribir el test de salud (falla primero porque no hay entorno de test aún)**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Ejecutar el test para verificar que falla por dependencias faltantes**

Run: `cd backend && pip install -r requirements.txt && pytest tests/test_health.py -v`
Expected: si `fastapi`/`httpx` no estaban instalados, falla en el import; tras instalar, debe pasar (este endpoint no tiene dependencias externas).

- [ ] **Step 5: Escribir `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 6: Escribir `frontend/Dockerfile` mínimo (scaffold vacío, sin páginas todavía)**

```dockerfile
FROM node:20-slim
WORKDIR /app
CMD ["sh", "-c", "echo 'frontend scaffold pendiente de Task de diseño'"]
```

- [ ] **Step 7: Escribir `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: qualityradar
      POSTGRES_PASSWORD: qualityradar_dev
      POSTGRES_DB: qualityradar
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U qualityradar"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    env_file: ./backend/.env
    ports: ["8000:8000"]
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    volumes: ["./backend:/app"]

  worker:
    build: ./backend
    command: celery -A app.worker worker --loglevel=info
    env_file: ./backend/.env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    volumes: ["./backend:/app"]

volumes:
  pgdata:
```

- [ ] **Step 8: Levantar y verificar**

Run: `docker compose up -d postgres redis && docker compose ps`
Expected: `postgres` y `redis` en estado `healthy`.

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml backend/Dockerfile backend/requirements.txt backend/app/__init__.py backend/app/main.py backend/tests/test_health.py frontend/Dockerfile
git commit -m "feat: scaffold del proyecto y docker compose base"
```

---

### Task 2: Configuración y sesión de base de datos

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/.env.example`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (Pydantic Settings) con campos `database_url: str`, `redis_url: str`, `jwt_secret: str`, `jwt_algorithm: str = "HS256"`, `jwt_access_expire_minutes: int = 15`, `jwt_refresh_expire_days: int = 30`, `encryption_key: str`, `github_client_id: str`, `github_client_secret: str`, `github_oauth_redirect_uri: str`.
- Produces: `get_db()` (generador de sesión SQLAlchemy, usado como `Depends(get_db)` en todos los endpoints de tasks siguientes).
- Consumes: nada (es la base de todo lo demás).

- [ ] **Step 1: Escribir el test de configuración (falla porque `config.py` no existe)**

```python
# backend/tests/test_config.py
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://qualityradar:qualityradar_dev@localhost:5432/qualityradar_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV1eGZvb2JhcmJhenF1dXg=")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GITHUB_OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/github/callback")

from app.core.config import get_settings


def test_settings_loads_from_env():
    settings = get_settings()
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_expire_minutes == 15
    assert settings.database_url.startswith("postgresql+psycopg://")
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'app.core'`

- [ ] **Step 3: Implementar `backend/app/core/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30
    encryption_key: str
    github_client_id: str
    github_client_secret: str
    github_oauth_redirect_uri: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Implementar `backend/app/core/database.py`**

```python
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 6: Escribir `backend/.env.example`**

```text
DATABASE_URL=postgresql+psycopg://qualityradar:qualityradar_dev@postgres:5432/qualityradar
REDIS_URL=redis://redis:6379/0
JWT_SECRET=change-me-in-production
ENCRYPTION_KEY=generate-with-fernet-generate-key
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/github/callback
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/core backend/tests/test_config.py backend/.env.example
git commit -m "feat: configuracion via pydantic-settings y sesion de base de datos"
```

---

### Task 3: Modelo `User` + migraciones 0001-0003

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_enable_pgcrypto.py`
- Create: `backend/alembic/versions/0002_create_enums.py`
- Create: `backend/alembic/versions/0003_create_users.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Test: `backend/tests/test_user_model.py`

**Interfaces:**
- Consumes: `Base` de `app.core.database` (Task 2).
- Produces: clase `User` (`app.models.user.User`) con atributos `id: uuid.UUID`, `email: str`, `password_hash: str | None`, `github_id: int | None`, `github_username: str | None`, `github_access_token_encrypted: str | None`, `avatar_url: str | None`, `plan: str`, `created_at: datetime`, `updated_at: datetime`. Usado por Tasks 7-9.

- [ ] **Step 1: Inicializar Alembic**

Run: `cd backend && alembic init alembic`
Expected: crea `alembic.ini` y `alembic/` con `env.py`, `script.py.mako`.

- [ ] **Step 2: Editar `backend/alembic/env.py` para usar `Settings` y `Base.metadata`**

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base
import app.models  # noqa: F401  (registra todos los modelos en Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Escribir migración 0001 (pgcrypto)**

```python
# backend/alembic/versions/0001_enable_pgcrypto.py
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto;")
```

- [ ] **Step 4: Escribir migración 0002 (enums) — copiado literal de `DATA_MODEL.md` §2**

```python
# backend/alembic/versions/0002_create_enums.py
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("CREATE TYPE analysis_type AS ENUM ('repository', 'url', 'combined');")
    op.execute(
        "CREATE TYPE analysis_status AS ENUM "
        "('pending', 'cloning', 'running', 'scoring', 'completed', 'failed', 'timeout');"
    )
    op.execute("CREATE TYPE finding_severity AS ENUM ('critical', 'high', 'medium', 'low', 'info');")
    op.execute(
        "CREATE TYPE finding_type AS ENUM ("
        "'security', 'test_coverage', 'documentation', 'dependency', "
        "'cicd', 'structure', 'activity', "
        "'performance', 'accessibility', 'seo', 'compatibility', 'usability');"
    )
    op.execute("CREATE TYPE plan_tier AS ENUM ('free');")


def downgrade() -> None:
    op.execute("DROP TYPE plan_tier;")
    op.execute("DROP TYPE finding_type;")
    op.execute("DROP TYPE finding_severity;")
    op.execute("DROP TYPE analysis_status;")
    op.execute("DROP TYPE analysis_type;")
```

- [ ] **Step 5: Escribir migración 0003 (users) — copiado literal de `DATA_MODEL.md` §3.1**

```python
# backend/alembic/versions/0003_create_users.py
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255),
            github_id BIGINT UNIQUE,
            github_username VARCHAR(255),
            github_access_token_encrypted TEXT,
            avatar_url TEXT,
            plan plan_tier NOT NULL DEFAULT 'free',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT users_auth_method_chk CHECK (password_hash IS NOT NULL OR github_id IS NOT NULL)
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE users;")
```

- [ ] **Step 6: Escribir el modelo SQLAlchemy `User` (falla el test hasta implementarlo)**

```python
# backend/tests/test_user_model.py
from app.models.user import User


def test_user_model_has_expected_columns():
    columns = {c.name for c in User.__table__.columns}
    assert columns == {
        "id", "email", "password_hash", "github_id", "github_username",
        "github_access_token_encrypted", "avatar_url", "plan", "created_at", "updated_at",
    }
```

Run: `cd backend && pytest tests/test_user_model.py -v`
Expected: FAIL (`app.models.user` no existe)

- [ ] **Step 7: Implementar `backend/app/models/user.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_access_token_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, server_default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 8: Crear `backend/app/models/__init__.py`**

```python
from app.models.user import User

__all__ = ["User"]
```

- [ ] **Step 9: Ejecutar el test y verificar que pasa**

Run: `cd backend && pytest tests/test_user_model.py -v`
Expected: PASS

- [ ] **Step 10: Correr migraciones contra Postgres real y verificar**

Run: `cd backend && alembic upgrade head && psql $DATABASE_URL -c "\d users"`
Expected: la tabla `users` existe con las columnas y el constraint `users_auth_method_chk`.

- [ ] **Step 11: Commit**

```bash
git add backend/alembic.ini backend/alembic backend/app/models backend/tests/test_user_model.py
git commit -m "feat: migraciones 0001-0003 y modelo User"
```

---

### Task 4: Migraciones 0004-0010 (resto del esquema) + modelos restantes

**Files:**
- Create: `backend/alembic/versions/0004_create_repositories_and_apps.py`
- Create: `backend/alembic/versions/0005_create_analyses.py`
- Create: `backend/alembic/versions/0006_create_dimensions_and_findings.py`
- Create: `backend/alembic/versions/0007_create_discrepancies.py`
- Create: `backend/alembic/versions/0008_create_comparisons_improvements_regressions.py`
- Create: `backend/alembic/versions/0009_create_benchmark_data.py`
- Create: `backend/alembic/versions/0010_create_shared_reports_and_refresh_tokens.py`
- Create: `backend/app/models/repository.py`, `backend/app/models/deployed_app.py`, `backend/app/models/analysis.py`, `backend/app/models/refresh_token.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_schema_migrations.py`

**Interfaces:**
- Produces: modelo `Repository` (usado por Task 9), modelo `RefreshToken` (usado por Task 8). Los modelos `Analysis`/`Dimension`/`Finding`/etc. se declaran para que `Base.metadata` esté completo, pero no se usan hasta la Semana 2-3.

> Nota de alcance: cada migración de este task copia literalmente el DDL correspondiente de `DATA_MODEL.md` §3.2 a §3.12. No se repite aquí el SQL completo por brevedad del plan — el ejecutor debe copiarlo tal cual de `docs/DATA_MODEL.md`, sección por sección, un archivo de migración por tabla (o grupo de tablas) según los nombres de archivo listados arriba, encadenando `down_revision` en orden (`0004`→`0003`, `0005`→`0004`, ... `0010`→`0009`). La migración `0009` además debe incluir el seed de `benchmark_data`:

```python
# fragmento adicional dentro de 0009_create_benchmark_data.py, después del CREATE TABLE
SEED_ROWS = [
    ("javascript", "maintainability", 62.0), ("javascript", "security", 58.0),
    ("javascript", "reliability", 60.0), ("python", "maintainability", 68.0),
    ("python", "security", 65.0), ("python", "reliability", 66.0),
    ("typescript", "maintainability", 71.0), ("typescript", "security", 67.0),
    ("typescript", "reliability", 69.0),
]

def upgrade() -> None:
    op.execute(""" ... CREATE TABLE benchmark_data ... """)  # DDL literal de DATA_MODEL.md §3.10
    for language, dimension, avg_score in SEED_ROWS:
        op.execute(
            "INSERT INTO benchmark_data (language, dimension, avg_score, source, is_simulated) "
            f"VALUES ('{language}', '{dimension}', {avg_score}, 'State of Open Source 2025 (simulado)', true);"
        )
```

- [ ] **Step 1: Escribir `backend/tests/test_schema_migrations.py` (falla porque las tablas no existen)**

```python
import sqlalchemy as sa

from app.core.database import engine

EXPECTED_TABLES = {
    "users", "repositories", "deployed_apps", "analyses", "dimensions", "findings",
    "discrepancies", "analysis_comparisons", "improvements", "regressions",
    "benchmark_data", "shared_reports", "refresh_tokens",
}


def test_all_tables_exist_after_migrations():
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(existing)


def test_benchmark_data_is_seeded():
    with engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM benchmark_data")).scalar_one()
    assert count >= 9
```

- [ ] **Step 2: Ejecutar contra la base de test y verificar que falla**

Run: `cd backend && DATABASE_URL=$TEST_DATABASE_URL pytest tests/test_schema_migrations.py -v`
Expected: FAIL (`relation "repositories" does not exist`)

- [ ] **Step 3: Escribir las 7 migraciones (0004-0010) copiando el DDL de `DATA_MODEL.md` según la nota de alcance de arriba**

- [ ] **Step 4: Escribir los modelos SQLAlchemy restantes**

```python
# backend/app/models/repository.py
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("user_id", "github_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, server_default="main")
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# backend/app/models/refresh_token.py
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`deployed_app.py` y `analysis.py` (con `Analysis`, `Dimension`, `Finding`, `Discrepancy`, `AnalysisComparison`, `Improvement`, `Regression`) siguen el mismo patrón 1:1 contra el DDL de `DATA_MODEL.md` §3.3-§3.9 — se declaran ahora aunque no se usen hasta la Semana 2-3, para que `Base.metadata` (y por tanto Alembic autogenerate futuro) esté completo.

- [ ] **Step 5: Actualizar `backend/app/models/__init__.py`**

```python
from app.models.analysis import (
    Analysis, AnalysisComparison, Dimension, Discrepancy, Finding, Improvement, Regression,
)
from app.models.deployed_app import DeployedApp
from app.models.refresh_token import RefreshToken
from app.models.repository import Repository
from app.models.user import User

__all__ = [
    "Analysis", "AnalysisComparison", "Dimension", "DeployedApp", "Discrepancy",
    "Finding", "Improvement", "Regression", "RefreshToken", "Repository", "User",
]
```

- [ ] **Step 6: Correr migraciones y ejecutar los tests**

Run: `cd backend && alembic upgrade head && pytest tests/test_schema_migrations.py -v`
Expected: PASS (13 tablas presentes, `benchmark_data` con ≥9 filas)

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions backend/app/models backend/tests/test_schema_migrations.py
git commit -m "feat: migraciones 0004-0010 y modelos restantes del esquema"
```

---

### Task 5: Utilidades de password y JWT

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Produces: `hash_password(plain: str) -> str`, `verify_password(plain: str, hashed: str) -> bool`, `create_access_token(user_id: uuid.UUID) -> str`, `decode_access_token(token: str) -> uuid.UUID` (lanza `InvalidTokenError` si expiró o es inválido). Usado por Tasks 7-9.

- [ ] **Step 1: Escribir el test (falla porque `security.py` no existe)**

```python
# backend/tests/test_security.py
import uuid

import pytest
from jwt import InvalidTokenError

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_decode_rejects_tampered_token():
    token = create_access_token(uuid.uuid4())
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && pytest tests/test_security.py -v`
Expected: `ModuleNotFoundError: No module named 'app.core.security'`

- [ ] **Step 3: Implementar `backend/app/core/security.py`**

```python
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return uuid.UUID(payload["sub"])
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && pytest tests/test_security.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat: utilidades de hashing de password y JWT"
```

---

### Task 6: Cifrado Fernet para el token de GitHub

**Files:**
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/utils/crypto.py`
- Test: `backend/tests/test_crypto.py`

**Interfaces:**
- Produces: `encrypt_token(plain: str) -> str`, `decrypt_token(encrypted: str) -> str`. Usado por Task 8 (`github_access_token_encrypted`).

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/test_crypto.py
from app.utils.crypto import decrypt_token, encrypt_token


def test_encrypt_decrypt_roundtrip():
    plain = "ghu_dummyTokenValueForTesting1234567890"
    encrypted = encrypt_token(plain)
    assert encrypted != plain
    assert decrypt_token(encrypted) == plain
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && pytest tests/test_crypto.py -v`
Expected: `ModuleNotFoundError: No module named 'app.utils.crypto'`

- [ ] **Step 3: Implementar `backend/app/utils/crypto.py`**

```python
from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode("utf-8"))


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && pytest tests/test_crypto.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils backend/tests/test_crypto.py
git commit -m "feat: cifrado Fernet para tokens de GitHub"
```

---

### Task 7: Registro y login (email + password)

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_register_login.py`

**Interfaces:**
- Consumes: `hash_password`, `verify_password`, `create_access_token` (Task 5); `User` (Task 3); `get_db` (Task 2).
- Produces: `POST /api/auth/register` → `201 {"id": str, "email": str}`; `POST /api/auth/login` → `200 {"access_token": str, "token_type": "bearer"}` o `401`.

- [ ] **Step 1: Escribir `backend/app/schemas/auth.py`**

```python
from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [ ] **Step 2: Escribir el test de registro + login (falla porque no hay router de auth)**

```python
# backend/tests/test_auth_register_login.py
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_then_login_succeeds():
    register_response = client.post(
        "/api/auth/register", json={"email": "juan@example.com", "password": "s3cur3-passw0rd"}
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "juan@example.com"

    login_response = client.post(
        "/api/auth/login", json={"email": "juan@example.com", "password": "s3cur3-passw0rd"}
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()


def test_login_with_wrong_password_returns_401():
    client.post("/api/auth/register", json={"email": "maria@example.com", "password": "correct-password"})
    response = client.post("/api/auth/login", json={"email": "maria@example.com", "password": "wrong-password"})
    assert response.status_code == 401


def test_register_with_duplicate_email_returns_409():
    client.post("/api/auth/register", json={"email": "dup@example.com", "password": "password-one"})
    response = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "password-two"})
    assert response.status_code == 409
```

- [ ] **Step 3: Ejecutar y verificar que falla**

Run: `cd backend && pytest tests/test_auth_register_login.py -v`
Expected: `404` en vez de `201`/`200` (el router no existe todavía)

- [ ] **Step 4: Implementar `backend/app/api/deps.py`**

```python
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.database import get_db as _get_db

get_db = _get_db  # re-exportado para que los routers importen solo desde app.api.deps
```

- [ ] **Step 5: Implementar `backend/app/api/auth.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(id=uuid.uuid4(), email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": str(user.id), "email": user.email}


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or user.password_hash is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    return TokenResponse(access_token=create_access_token(user.id))
```

- [ ] **Step 6: Registrar el router en `backend/app/main.py`**

```python
from fastapi import FastAPI

from app.api.auth import router as auth_router

app = FastAPI(title="QualityRadar API")
app.include_router(auth_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Ejecutar y verificar que pasa**

Run: `cd backend && pytest tests/test_auth_register_login.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas backend/app/api backend/app/main.py backend/tests/test_auth_register_login.py
git commit -m "feat: endpoints de registro y login"
```

---

### Task 8: Refresh tokens + callback de GitHub OAuth

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/github_service.py`
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/api/auth.py`
- Test: `backend/tests/test_github_oauth.py`

**Interfaces:**
- Consumes: `encrypt_token` (Task 6), `create_access_token` (Task 5), `User`/`RefreshToken` (Task 4).
- Produces: `github_service.exchange_code_for_token(code: str) -> str`, `github_service.fetch_github_user(token: str) -> dict`, `github_service.fetch_github_primary_email(token: str) -> str` (mockeadas en tests, se prueban de forma manual contra GitHub real antes de cerrar la semana). `GET /api/auth/github/callback?code=...` → `200 {"access_token": str, "token_type": "bearer"}`.

- [ ] **Step 1: Implementar `backend/app/services/github_service.py`**

```python
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
```

- [ ] **Step 2: Escribir el test del callback, mockeando las llamadas a GitHub (falla porque el endpoint no existe)**

```python
# backend/tests/test_github_oauth.py
from fastapi.testclient import TestClient

from app.main import app
from app.services import github_service

client = TestClient(app)


def test_github_callback_creates_user_and_returns_token(monkeypatch):
    monkeypatch.setattr(github_service, "exchange_code_for_token", lambda code: "gho_fake_token")
    monkeypatch.setattr(
        github_service, "fetch_github_user",
        lambda token: {"id": 123456, "login": "juan-dev", "avatar_url": "https://avatars.example/juan"},
    )
    monkeypatch.setattr(github_service, "fetch_github_primary_email", lambda token: "juan-dev@example.com")

    response = client.get("/api/auth/github/callback", params={"code": "any-code"})

    assert response.status_code == 200
    assert "access_token" in response.json()
```

- [ ] **Step 3: Ejecutar y verificar que falla**

Run: `cd backend && pytest tests/test_github_oauth.py -v`
Expected: `404`

- [ ] **Step 4: Añadir el endpoint en `backend/app/api/auth.py`**

```python
# agregar al final de backend/app/api/auth.py
from app.services import github_service
from app.utils.crypto import encrypt_token


@router.get("/github/callback", response_model=TokenResponse)
def github_callback(code: str, db: Session = Depends(get_db)) -> TokenResponse:
    github_token = github_service.exchange_code_for_token(code)
    github_user = github_service.fetch_github_user(github_token)
    email = github_service.fetch_github_primary_email(github_token)

    user = db.scalar(select(User).where(User.github_id == github_user["id"]))
    if user is None:
        user = User(id=uuid.uuid4(), email=email, github_id=github_user["id"])

    user.github_username = github_user["login"]
    user.avatar_url = github_user.get("avatar_url")
    user.github_access_token_encrypted = encrypt_token(github_token)
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id))
```

- [ ] **Step 5: Ejecutar y verificar que pasa**

Run: `cd backend && pytest tests/test_github_oauth.py -v`
Expected: PASS

- [ ] **Step 6: Verificar manualmente que el token cifrado no queda en claro**

Run: `psql $DATABASE_URL -c "SELECT github_access_token_encrypted FROM users WHERE github_username='juan-dev';"` (contra la base de test tras correr el test anterior sin mock de DB, o con un script manual) — confirmar que el valor no es `gho_fake_token` en texto plano.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services backend/app/api/auth.py backend/tests/test_github_oauth.py
git commit -m "feat: callback de GitHub OAuth con cifrado de token"
```

> Refresh tokens (rotación completa con `RefreshToken`) se dejan para un ajuste rápido al cierre de la semana una vez que el flujo de login básico esté validado end-to-end; no bloquean el resto de Task 9.

---

### Task 9: Listado de repositorios públicos del usuario

**Files:**
- Modify: `backend/app/services/github_service.py`
- Create: `backend/app/schemas/repository.py`
- Create: `backend/app/api/repositories.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_repositories_list.py`

**Interfaces:**
- Consumes: `decode_access_token` (Task 5), `User` (Task 3), `github_service` (Task 8).
- Produces: `GET /api/repositories` (requiere header `Authorization: Bearer <token>`) → `200 [{"id": str, "name": str, "full_name": str, "is_private": bool}]`.

- [ ] **Step 1: Añadir `list_public_repos` a `github_service.py`**

```python
# agregar a backend/app/services/github_service.py
def list_public_repos(token: str) -> list[dict]:
    response = httpx.get(
        f"{GITHUB_API_BASE}/user/repos",
        headers={"Authorization": f"Bearer {token}"},
        params={"visibility": "public", "per_page": 100},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 2: Implementar la dependencia de usuario autenticado en `backend/app/api/deps.py`**

```python
# agregar a backend/app/api/deps.py
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.models.user import User


def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        user_id = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user
```

- [ ] **Step 3: Escribir el test (falla porque el endpoint no existe)**

```python
# backend/tests/test_repositories_list.py
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.services import github_service

client = TestClient(app)


def test_list_repositories_returns_only_public_repos(monkeypatch, db_session_with_github_user):
    user = db_session_with_github_user
    monkeypatch.setattr(
        github_service, "list_public_repos",
        lambda token: [
            {"id": 1, "name": "quality-radar", "full_name": "juan/quality-radar", "private": False},
            {"id": 2, "name": "side-project", "full_name": "juan/side-project", "private": False},
        ],
    )

    token = create_access_token(user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(repo["is_private"] is False for repo in body)


def test_list_repositories_without_token_returns_401():
    response = client.get("/api/repositories")
    assert response.status_code == 401
```

> `db_session_with_github_user` es un fixture de `backend/tests/conftest.py` que crea un `User` de prueba con `github_access_token_encrypted` ya seteado — se agrega en este mismo step si no existe todavía.

- [ ] **Step 4: Ejecutar y verificar que falla**

Run: `cd backend && pytest tests/test_repositories_list.py -v`
Expected: `404`

- [ ] **Step 5: Implementar `backend/app/schemas/repository.py`**

```python
from pydantic import BaseModel


class RepositoryOut(BaseModel):
    id: str
    name: str
    full_name: str
    is_private: bool
```

- [ ] **Step 6: Implementar `backend/app/api/repositories.py`**

```python
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.repository import RepositoryOut
from app.services import github_service
from app.utils.crypto import decrypt_token

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryOut])
def list_repositories(current_user: User = Depends(get_current_user)) -> list[RepositoryOut]:
    token = decrypt_token(current_user.github_access_token_encrypted)
    repos = github_service.list_public_repos(token)
    return [
        RepositoryOut(id=str(repo["id"]), name=repo["name"], full_name=repo["full_name"], is_private=repo["private"])
        for repo in repos
    ]
```

- [ ] **Step 7: Registrar el router en `backend/app/main.py`**

```python
from app.api.repositories import router as repositories_router

app.include_router(repositories_router)
```

- [ ] **Step 8: Ejecutar y verificar que pasa**

Run: `cd backend && pytest tests/test_repositories_list.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/github_service.py backend/app/schemas/repository.py backend/app/api/repositories.py backend/app/api/deps.py backend/app/main.py backend/tests/test_repositories_list.py
git commit -m "feat: endpoint de listado de repositorios publicos"
```

---

## Cierre de semana — verificación end-to-end

- [ ] Correr toda la suite: `cd backend && pytest -v` → todos los tests en verde.
- [ ] `docker compose up -d` levanta los 5 servicios sin error.
- [ ] Prueba manual con una GitHub OAuth App real (no mockeada): flujo completo `/api/auth/github/callback` → `/api/repositories` devuelve repos reales de una cuenta de prueba.

## ⚠️ Pendiente explícito antes de Semana 2: frontend de esta semana

Este plan **no incluye** las páginas de Next.js (login/registro, botón "Conectar con GitHub", lista de repositorios). Antes de planearlas, avisar al usuario para acordar dirección visual (skill `frontend-design`) — no construir UI con estilos por defecto sin esa conversación primero.
