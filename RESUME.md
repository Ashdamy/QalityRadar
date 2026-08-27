# RESUME — Bitácora de QalitiRadar

> Documento vivo. Se actualiza a medida que avanza el proyecto.
> Última actualización: 2026-08-27

---

## ¿En qué etapa va el proyecto?

**Fase actual: Semana 1 — Setup + Autenticación (backend), en ejecución.**

| Etapa | Estado |
|---|---|
| Fase 0 — Arquitectura y diseño | ✅ Completada |
| Diseño visual (mockup de pantallas Semana 1) | ✅ Aprobado |
| Semana 1 — Setup + Auth (backend) | 🔄 En progreso (2 de 9 tareas completadas) |
| Semana 1 — Frontend (páginas reales) | ⏸️ Pendiente (se implementa después del backend) |
| Semanas 2-5 | ⏸️ No iniciadas |

---

## Paso a paso de lo que se ha hecho

### 1. Lectura y análisis de la especificación

Leí completo `context/claude.md` (645 líneas) y analicé la visión del producto: un escáner de calidad de software basado en ISO/IEC 25010 con tres modos de análisis (repositorio, URL desplegada, y combinado), histórico temporal, comparación entre análisis y resúmenes generados con IA.

Detecté que el documento pedía explícitamente hacer preguntas antes de codificar, así que planteé 6 ambigüedades: mecanismo de sandbox, alcance de repos privados, proveedor de IA, URLs con login, monetización, y de dónde saldrían los datos de benchmarking.

### 2. Decisiones de alcance del MVP

Respondiste las 6 preguntas. Decisiones acordadas:

| Pregunta | Decisión MVP |
|---|---|
| Sandbox de ejecución | Docker con límites de recursos |
| Repositorios | Solo públicos (scope `public_repo`) |
| IA para resúmenes | Hugging Face Inference API (Mistral-7B, free tier) + fallback a plantillas |
| URLs con login | No soportadas |
| Monetización | 100% gratuito; límites 5/hora, 20/día |
| Benchmarking | Datos simulados por lenguaje |

### 3. Corrección del repositorio

**Problema encontrado:** la carpeta `QalitiRadar/` no era un repositorio git propio — estaba anidada dentro de `proyectos/`, que apunta a `Apollored7/proyecto-app-habitos` (otro proyecto, la app de hábitos). El spec indicaba que QalitiRadar debía vivir en `Ashdamy/QalitiRadar`.

**Solución aplicada:** inicialicé un repo git independiente dentro de `QalitiRadar/`, lo conecté a `https://github.com/Ashdamy/QalitiRadar`, traje el commit inicial del remoto como base, y desde entonces todo el trabajo de QalitiRadar vive ahí — completamente separado del proyecto de hábitos.

### 4. Documentos de arquitectura (Fase 0)

Creé y subí tres documentos:

- **`docs/ARCHITECTURE.md`** — componentes del sistema con diagramas, flujos de datos para los 3 modos de análisis, y análisis de riesgos de seguridad. Incluye un riesgo crítico que **no estaba en el spec original: SSRF** (Server-Side Request Forgery) — analizar una URL arbitraria del usuario permite que un atacante haga que nuestro servidor consulte direcciones internas, incluyendo metadatos de la nube. Documenté la mitigación obligatoria (validar la IP tras resolver DNS, y re-validar en cada redirect).
- **`docs/DATA_MODEL.md`** — las 12 tablas con su DDL completo, índices, constraints, y el orden de las migraciones Alembic.
- **`docs/ROADMAP.md`** — 5 semanas con criterios de salida verificables por semana (en vez de las 8 fases por calendario del spec original, que no tenían forma de comprobarse).

### 5. Plan detallado de la Semana 1

Escribí `docs/superpowers/plans/2026-08-27-week1-setup-auth.md`: 9 tareas paso a paso con metodología TDD (test primero, verificar que falla, implementar, verificar que pasa, commit). Cada tarea trae el código exacto a escribir, los comandos a correr, y el resultado esperado.

Dejé explícitamente fuera del plan las páginas de frontend, para hablar primero de diseño.

### 6. Diseño visual de las pantallas

Creé un prototipo interactivo con las 3 pantallas de la Semana 1 (login/registro, conexión con GitHub, selección de repositorio).

**Dirección estética acordada y aprobada:** herramienta técnica seria estilo Vercel/Linear/GitHub — tema oscuro, paleta gris-neutra fría en oklch, un solo color de acento cian ("señal de radar"), tipografía IBM Plex Sans + IBM Plex Mono, sin gradientes ni decoraciones genéricas de SaaS.

Quedó acordado que **de ahora en adelante, cualquier cosa nueva de diseño se muestra primero como prototipo** antes de implementarla en código.

### 7. Ejecución de la Semana 1 (en curso)

Modo de trabajo: subagentes especializados, uno por tarea, con revisión independiente después de cada una. El trabajo ocurre en una rama aislada (`week1-setup-auth`) para no tocar `main` hasta que todo esté revisado.

**Antes de empezar** hice un escaneo del plan buscando contradicciones y encontré 4 defectos reales, que corregí con decisiones registradas:

1. La Task 9 usaba un fixture de test (`db_session_with_github_user`) que no estaba definido en ninguna parte.
2. Ninguna tarea creaba la base de datos de tests (`qalitiradar_test`) que varias tareas asumían existente.
3. La configuración de variables de entorno para tests era frágil — dependía del orden alfabético en que pytest importa los archivos. Lo moví a un `conftest.py` que pytest carga siempre primero.
4. La Task 8 declaraba modificar un archivo que en realidad no toca.

**Progreso de las 9 tareas:**

| # | Tarea | Estado |
|---|---|---|
| 1 | Scaffolding + Docker Compose + endpoint `/health` | ✅ Completada y revisada |
| 2 | Configuración (pydantic-settings) + sesión de base de datos | ✅ Completada y revisada |
| 3 | Modelo `User` + migraciones 0001-0003 | ✅ Completada y revisada |
| 4 | Migraciones 0004-0010 + modelos restantes | ⏸️ Pendiente |
| 5 | Hashing de contraseñas + JWT | ⏸️ Pendiente |
| 6 | Cifrado del token de GitHub (Fernet) | ⏸️ Pendiente |
| 7 | Endpoints de registro y login | ⏸️ Pendiente |
| 8 | Callback de GitHub OAuth | ⏸️ Pendiente |
| 9 | Listado de repositorios públicos | ⏸️ Pendiente |

**Infraestructura ya funcionando:** Docker Desktop levantado, contenedores de PostgreSQL y Redis corriendo y sanos, ambas bases de datos creadas (`qalitiradar` para desarrollo, `qalitiradar_test` para tests) y las migraciones 0001-0003 aplicadas y verificadas en las dos.

### 8. Cambio de nombre del proyecto

El proyecto pasó de llamarse **QualityRadar** a **QalitiRadar**. Se aplicó en documentación, código, `docker-compose.yml` y credenciales de base de datos (usuario y base `qalitiradar`, base de tests `qalitiradar_test`).

Pendiente de tu parte: renombrar el repositorio en GitHub (Settings → Repository name → `QalitiRadar`). En cuanto lo hagas, actualizo el remote local. GitHub mantiene redirecciones automáticas, así que nada se rompe mientras tanto.

Pendiente mío, para el final: renombrar la carpeta local en disco. Se pospuso a propósito porque el worktree de git guarda rutas absolutas y los contenedores montan `./backend` — renombrarla en plena implementación rompería ambos.

### 9. Problema de entorno resuelto: conflicto de puerto de PostgreSQL

Durante la Task 3 apareció un problema real del entorno: **un servicio nativo de PostgreSQL de Windows (`postgresql-x64-18`) ya estaba ocupando el puerto 5432**, así que todo lo que se conectaba a `localhost:5432` desde el host llegaba al servidor equivocado — fallando de forma silenciosa, sin error claro.

Solución aplicada: el contenedor de Postgres ahora se publica en el puerto **5433** del host. Tu PostgreSQL nativo queda intacto (parece estar en uso para Odoo). Las conexiones entre contenedores siguen usando `postgres:5432`; solo las herramientas que corren desde el host (pytest, alembic) apuntan a `localhost:5433`.

---

## Lo que sigue

1. Terminar las 9 tareas de la Semana 1 (backend de autenticación).
2. Revisión final de toda la rama antes de integrarla a `main`.
3. Implementar el frontend real de la Semana 1, usando el prototipo aprobado como referencia exacta de estilos.
4. Semana 2: sandbox de análisis + los 7 analizadores de repositorio.

---

## Enlaces útiles

- Repositorio: https://github.com/Ashdamy/QalitiRadar
- Especificación original: [`context/claude.md`](context/claude.md)
- Arquitectura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Modelo de datos: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)
- Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Plan de la Semana 1: [`docs/superpowers/plans/2026-08-27-week1-setup-auth.md`](docs/superpowers/plans/2026-08-27-week1-setup-auth.md)
