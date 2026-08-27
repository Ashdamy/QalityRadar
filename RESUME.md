# RESUME — Bitácora de QualityRadar

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

**Problema encontrado:** la carpeta `QualityRadar/` no era un repositorio git propio — estaba anidada dentro de `proyectos/`, que apunta a `Apollored7/proyecto-app-habitos` (otro proyecto, la app de hábitos). El spec indicaba que QualityRadar debía vivir en `Ashdamy/QualityRadar`.

**Solución aplicada:** inicialicé un repo git independiente dentro de `QualityRadar/`, lo conecté a `https://github.com/Ashdamy/QualityRadar`, traje el commit inicial del remoto como base, y desde entonces todo el trabajo de QualityRadar vive ahí — completamente separado del proyecto de hábitos.

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
2. Ninguna tarea creaba la base de datos de tests (`qualityradar_test`) que varias tareas asumían existente.
3. La configuración de variables de entorno para tests era frágil — dependía del orden alfabético en que pytest importa los archivos. Lo moví a un `conftest.py` que pytest carga siempre primero.
4. La Task 8 declaraba modificar un archivo que en realidad no toca.

**Progreso de las 9 tareas:**

| # | Tarea | Estado |
|---|---|---|
| 1 | Scaffolding + Docker Compose + endpoint `/health` | ✅ Completada y revisada |
| 2 | Configuración (pydantic-settings) + sesión de base de datos | ✅ Completada y revisada |
| 3 | Modelo `User` + migraciones 0001-0003 | 🔄 En progreso |
| 4 | Migraciones 0004-0010 + modelos restantes | ⏸️ Pendiente |
| 5 | Hashing de contraseñas + JWT | ⏸️ Pendiente |
| 6 | Cifrado del token de GitHub (Fernet) | ⏸️ Pendiente |
| 7 | Endpoints de registro y login | ⏸️ Pendiente |
| 8 | Callback de GitHub OAuth | ⏸️ Pendiente |
| 9 | Listado de repositorios públicos | ⏸️ Pendiente |

**Infraestructura ya funcionando:** Docker Desktop levantado, contenedores de PostgreSQL y Redis corriendo y sanos, y ambas bases de datos creadas (`qualityradar` para desarrollo, `qualityradar_test` para tests).

---

## Lo que sigue

1. Terminar las 9 tareas de la Semana 1 (backend de autenticación).
2. Revisión final de toda la rama antes de integrarla a `main`.
3. Implementar el frontend real de la Semana 1, usando el prototipo aprobado como referencia exacta de estilos.
4. Semana 2: sandbox de análisis + los 7 analizadores de repositorio.

---

## Enlaces útiles

- Repositorio: https://github.com/Ashdamy/QualityRadar
- Especificación original: [`context/claude.md`](context/claude.md)
- Arquitectura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Modelo de datos: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)
- Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Plan de la Semana 1: [`docs/superpowers/plans/2026-08-27-week1-setup-auth.md`](docs/superpowers/plans/2026-08-27-week1-setup-auth.md)
