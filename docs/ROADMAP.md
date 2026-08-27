# QalitiRadar — Roadmap de Implementación

> Complementa [`ARCHITECTURE.md`](./ARCHITECTURE.md) y [`DATA_MODEL.md`](./DATA_MODEL.md). Reescribe las 8 fases de [`context/claude.md`](../context/claude.md) en 5 semanas, incorporando las decisiones de MVP ya acordadas (Docker sandbox, solo repos públicos, Hugging Face free tier, sin monetización, benchmarking simulado).

## Cómo se ejecuta esto

Este roadmap es de **nivel de milestone**, no de tarea bite-sized. Antes de empezar cada semana se generará un plan de implementación detallado (TDD, paso a paso, un archivo por semana bajo `docs/superpowers/plans/`) usando la skill `superpowers:writing-plans`, para que cada subsistema (auth, analizadores de repo, analizadores de URL, dashboard, features finales) tenga su propio plan ejecutable de forma independiente — en vez de un único plan gigante de 25 días.

**Regla dura de todas las semanas:** no se escribe código sin que la semana anterior tenga su milestone cumplido y verificado (tests pasando, funcionalidad demostrable). Esto es explícito porque el spec original marca fases por calendario, no por dependencias reales.

## Vista general

| Semana | Foco | Depende de | Milestone (Definition of Done) |
|---|---|---|---|
| 0 | Arquitectura y diseño | — | ✅ Ya completado: `ARCHITECTURE.md`, `DATA_MODEL.md`, este roadmap, repo conectado a `Ashdamy/QalitiRadar` |
| 1 | Setup + Auth | Semana 0 | Usuario se registra/loguea (email+password o GitHub OAuth `public_repo`), ve sus repos públicos listados. Docker Compose levanta Postgres+Redis+API+FE. Migraciones Alembic 0001-0010 aplicadas |
| 2 | Sandbox + analizadores de repositorio | Semana 1 | Un análisis de repo real (público) corre end-to-end: clona → sandbox Docker aislado → 7 analizadores → `Finding`/`Dimension` persistidos. Sin scoring todavía |
| 3 | Analizadores de URL + motor de scoring ISO 25010 | Semana 2 | Los 3 modos (repo/URL/combinado) producen `overall_score` + `confidence_level` persistidos. SSRF-safe fetch verificado con tests |
| 4 | Dashboard + histórico + comparación | Semana 3 | Dashboard navegable: selección de modo, resultados por modo, radar chart, timeline, comparación automática con resumen (HF o fallback), benchmarking simulado |
| 5 | Features finales + producción | Semana 4 | PDF export, compartir reporte, rate limiting activo, notificaciones de cambios significativos, tests e2e, deploy público (Vercel + Railway/Render) |

---

## Semana 1 — Setup + Autenticación

**Objetivo:** infraestructura base y que un usuario pueda entrar con GitHub y ver sus repos públicos.

**Tareas clave:**
- `docker-compose.yml`: servicios `postgres`, `redis`, `backend` (FastAPI), `frontend` (Next.js), `worker` (Celery) — todos con healthchecks.
- Backend: `app/core/config.py` (Pydantic Settings), `app/core/security.py` (hashing de password, JWT encode/decode, cifrado Fernet para `github_access_token_encrypted`).
- Alembic: migraciones 0001-0010 de [`DATA_MODEL.md`](./DATA_MODEL.md) §5, incluyendo seed de `benchmark_data` con los valores simulados.
- Auth: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/github/callback` (scopes `public_repo read:user user:email`), `refresh_tokens` con rotación.
- `GET /api/repositories` — lista repos públicos del usuario autenticado vía GitHub API.
- Frontend: página de login/registro, botón "Conectar con GitHub", lista de repositorios.

**Exit criteria (bloquea Semana 2 si falla):**
- [ ] `docker-compose up` levanta los 5 servicios sin error.
- [ ] Test de integración: registro → login → token JWT válido.
- [ ] Test de integración: callback de GitHub OAuth crea/actualiza `users` con `github_access_token_encrypted` (verificar que NO queda en texto plano en ningún log ni columna).
- [ ] `GET /api/repositories` devuelve solo repos con `is_private=false` reales de una cuenta de prueba.

**Riesgo a vigilar:** si el registro de la OAuth App de GitHub tarda en aprobarse/configurarse, usar un usuario de prueba (Personal Access Token de solo lectura) para no bloquear el resto de la semana.

---

## Semana 2 — Sandbox + Analizadores de Repositorio

**Objetivo:** ejecutar análisis reales y aislados sobre repos públicos.

**Tareas clave:**
- `backend/app/utils/sandbox.py`: wrapper que invoca `docker run` con la lista fija de flags de `ARCHITECTURE.md` §4.1 (`--rm --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges --memory=512m --cpus=0.5 --pids-limit=100`), nunca `shell=True`, nunca interpolando input de usuario en el comando.
- Celery: `analyze_repository_task` con `task_time_limit=600` (10 min) y `task_soft_time_limit=570` (permite cleanup antes del kill duro).
- 7 analizadores en `app/analyzers/repository/`: `structure.py`, `documentation.py`, `dependencies.py` (npm audit/pip-audit), `tests.py`, `cicd.py`, `security.py` (Gitleaks + Semgrep), `activity.py` (GitHub API: commits/issues/PRs).
- Clonado: `git clone --depth 1 --branch <default_branch>` con `<default_branch>` validado contra regex `^[a-zA-Z0-9._/-]+$` antes de usarlo en el comando (mitigación de inyección).
- `POST /api/repositories/{id}/analyze` → crea `Analysis(status=pending)`, encola tarea, devuelve `202`.
- `GET /api/analysis/{id}` con polling (o SSE si da tiempo) para progreso.

**Exit criteria:**
- [ ] Análisis de un repo público real de prueba completa en <10 min y persiste al menos 1 `Finding` por cada uno de los 7 analizadores (o "sin hallazgos" explícito, no error silencioso).
- [ ] Test: un repo con un `.env` con secret de prueba dispara un `Finding` tipo `security` severidad `critical` vía Gitleaks.
- [ ] Test: matar el contenedor a mitad de análisis (simular timeout) no deja procesos huérfanos (`docker ps` limpio después).
- [ ] Test: intentar pasar un `branch` con `; rm -rf /` como input es rechazado por la validación de regex antes de llegar a `subprocess`.
- [ ] El working directory temporal del clon se borra siempre (éxito o fallo) — verificar con test que revisa el filesystem del worker tras la corrida.

---

## Semana 3 — Analizadores de URL + Motor de Scoring ISO 25010

**Objetivo:** analizar URLs de terceros de forma segura y calcular el score ISO 25010 para los 3 modos.

**Tareas clave:**
- `app/utils/url_validation.py`: resolución DNS + validación de IP (bloquear RFC1918, loopback, link-local/`169.254.0.0/16`), re-validación en cada redirect, solo esquemas `http`/`https`. Este módulo se usa antes de CUALQUIER request saliente a una URL de usuario.
- 4 analizadores en `app/analyzers/url/`: `performance.py` (Lighthouse CI headless), `security.py` (headers HSTS/CSP/X-Frame-Options + validez SSL), `accessibility.py` (axe-core headless), `seo.py`.
- `app/services/scoring_service.py`: implementa la fórmula `Σ(peso_i × métrica_i) / Σ(pesos)` de `context/claude.md` para las 3 tablas de pesos (repo, URL, combinado), más `confidence_level` basado en cantidad de evidencia encontrada.
- `app/analyzers/combined.py`: dispara ambos análisis en paralelo (Celery `chord`), calcula `Discrepancy` cuando `|repo_score - url_score| > 15`.

**Exit criteria:**
- [ ] Test: `url_validation.py` rechaza `http://169.254.169.254/`, `http://localhost:8000`, `http://192.168.1.1`, y una URL pública que redirige a cualquiera de las anteriores.
- [ ] Test: análisis de una URL pública real de prueba produce `overall_score` entre 0-100 con las 5 dimensiones de la tabla de URL.
- [ ] Test: análisis combinado con scores de repo=80 y url=60 genera `Discrepancy` (delta=20 > 15); con 80 y 75 no la genera.
- [ ] Test: fórmula de scoring con pesos que no suman 1.0 normaliza correctamente (división por `Σ(pesos)`).

---

## Semana 4 — Dashboard + Histórico + Comparación

**Objetivo:** que el usuario vea y entienda sus resultados, incluyendo evolución en el tiempo.

**Tareas clave:**
- Frontend: página de selección de modo (3 tarjetas), páginas de resultados por modo (radar chart con Recharts, lista de findings, plan de mejora priorizado por severidad).
- `app/services/comparison_service.py`: al completar un análisis, busca el anterior del mismo `repository_id`/`app_id`, calcula diffs por dimensión → `AnalysisComparison`, `Improvement[]`, `Regression[]`.
- `app/services/summary_service.py`: llama a Hugging Face Inference API (`mistralai/Mistral-7B-Instruct-v0.3`) con el prompt de `context/claude.md` §8; si falla (timeout, sin API key, rate limit del free tier) usa plantilla predefinida con los mismos datos.
- `app/services/benchmark_service.py`: lee `benchmark_data` (seed simulado de Semana 1) y expone `GET /api/repository/{id}/benchmark`.
- `GET /api/repository/:id/timeline`, `GET /api/repository/:id/progress`, `GET /api/analysis/:id/comparison/:other_id`.
- Frontend: gráfico de evolución temporal, vista de comparación (quick compare + full compare), highlight de cambios críticos.

**Exit criteria:**
- [ ] Segundo análisis del mismo repo genera automáticamente `AnalysisComparison` con al menos 1 `Improvement` o `Regression` reales (no vacío) cuando hay cambios de score.
- [ ] Test: `summary_service` con API key inválida cae a la plantilla sin lanzar excepción al usuario.
- [ ] Dashboard muestra correctamente 3 análisis históricos de un mismo repo con su gráfico de evolución (dato de prueba sembrado).
- [ ] Comparación de dos análisis con delta de seguridad negativo se resalta visualmente como regresión.

---

## Semana 5 — Features finales + Producción

**Objetivo:** MVP público, con las reglas de negocio y no funcionales del spec cumplidas.

**Tareas clave:**
- Exportación a PDF de resultados y de comparaciones (usar `raw_data`/`Finding` ya persistidos, no re-analizar).
- `shared_reports`: `POST /api/analysis/{id}/share` genera token + expiración; `GET /api/reports/shared/{token}` público sin auth.
- Rate limiting Redis (sliding window) en la API: 5 análisis/hora, 20/día, 2 en paralelo por usuario — verificado ANTES de encolar, con `429` claro al frontend.
- Job Celery Beat: purga de análisis más allá de 50 por repo / 90 días de retención (respetando "mantener al menos los últimos 10").
- Notificaciones de cambio significativo (bajada >10 puntos, nuevo riesgo crítico) — email o in-app, lo que se decida al llegar a esta semana.
- Tests end-to-end (Playwright o similar) de los 3 flujos completos (repo, URL, combinado).
- Deploy: frontend a Vercel, backend+worker a Railway/Render, Postgres/Redis gestionados, dominio, monitoreo básico (logs + healthchecks).

**Exit criteria:**
- [ ] Un usuario nuevo, desde cero, completa el flujo: registro → conectar GitHub → analizar repo → ver resultado → compartir link público → exportar PDF, en producción (no localhost).
- [ ] Rate limit verificado: el 6to análisis en la misma hora devuelve `429` sin haber tocado el worker.
- [ ] Test: análisis #51 de un mismo repo dispara la purga del más antiguo, manteniendo el histórico en 50 (o 10 si la retención de 90 días ya aplicó antes).
- [ ] `docs/DEPLOYMENT.md` (nuevo, a escribir esta semana) documenta cómo desplegar desde cero.

---

## Qué NO entra en este roadmap (explícitamente pospuesto)

Según las decisiones de MVP ya acordadas:
- Repositorios privados (scope `repo` de GitHub) — Fase futura 2.
- Análisis de URLs que requieren login — Fase futura 3.
- Monetización / tiers de pago — Fase futura 3.
- Firecracker/gVisor en vez de Docker — Fase futura de infraestructura.
- Benchmarking con datos reales de usuarios (requiere 100+ repos analizados primero).
