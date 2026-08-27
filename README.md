# QualityRadar

Escáner automático de calidad de software basado en **ISO/IEC 25010**. Analiza un repositorio (GitHub), una URL de una app desplegada, o ambos, y genera una puntuación de calidad con hallazgos, riesgos y recomendaciones priorizadas — con histórico y comparación entre análisis a lo largo del tiempo.

> Este proyecto está en fase de diseño. No hay código funcional todavía.

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

Ver [`docs/ROADMAP.md`](docs/ROADMAP.md) para el plan de fases. Actualmente en Fase 0 (arquitectura y diseño), pendiente de aprobación antes de comenzar la implementación.
