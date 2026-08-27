# QalitiRadar

Escáner automático de calidad de software basado en **ISO/IEC 25010**. Analiza un repositorio (GitHub), una URL de una app desplegada, o ambos, y genera una puntuación de calidad con hallazgos, riesgos y recomendaciones priorizadas — con histórico y comparación entre análisis a lo largo del tiempo.

> Backend de la Semana 1 completo: API de autenticación (registro/login con password + OAuth de GitHub), esquema de datos completo (10 migraciones) y suite de tests. El frontend y el pipeline de análisis todavía no existen.

## Documentación

- [`context/claude.md`](context/claude.md) — especificación de producto original y decisiones de alcance del MVP
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — arquitectura técnica, flujos de datos, riesgos de seguridad
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — modelo de datos completo (tablas, relaciones, índices)
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — plan de implementación semana a semana

## Stack

- **Backend:** Python 3.11+, FastAPI, PostgreSQL, SQLAlchemy + Alembic, Celery + Redis
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS + shadcn/ui, Recharts
- **Análisis:** Gitleaks, Semgrep, Lighthouse CI, axe-core
- **Infraestructura:** Docker + Docker Compose

## Estado

Ver [`docs/ROADMAP.md`](docs/ROADMAP.md) para el plan de fases. Semana 1 (backend: auth, esquema de datos, migraciones) completa; el resto del roadmap sigue pendiente.

## Desarrollo local

1. Copiar `backend/.env.example` a `backend/.env` y completar los valores (`JWT_SECRET`, `ENCRYPTION_KEY` generada con Fernet, credenciales de GitHub OAuth, etc.).
2. Levantar Postgres y Redis: `docker compose up -d postgres redis`. Postgres queda expuesto en `localhost:5433` (no 5432, que suele estar ocupado por una instalación nativa de PostgreSQL en Windows).
3. Crear la base de datos de test, ya que las migraciones y la suite de tests usan una base separada de la de desarrollo (`qalitiradar_test` vs `qalitiradar`):
   ```
   psql -h localhost -p 5433 -U qalitiradar -c "CREATE DATABASE qalitiradar_test;"
   ```
4. Aplicar las migraciones contra AMBAS bases, apuntando `DATABASE_URL` a cada una:
   ```
   cd backend
   DATABASE_URL=postgresql+psycopg://qalitiradar:qalitiradar_dev@localhost:5433/qalitiradar alembic upgrade head
   DATABASE_URL=postgresql+psycopg://qalitiradar:qalitiradar_dev@localhost:5433/qalitiradar_test alembic upgrade head
   ```
5. Correr la suite de tests desde `backend/`: `python -m pytest -q`.
