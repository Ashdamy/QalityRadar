# RESUME — Bitácora de QalitiRadar

> Documento vivo. Se actualiza a medida que avanza el proyecto.
> Última actualización: 2026-08-27 (Semana 1 backend completa)

---

## ¿En qué etapa va el proyecto?

**Fase actual: Semana 1 — Setup + Autenticación (backend), en ejecución.**

| Etapa | Estado |
|---|---|
| Fase 0 — Arquitectura y diseño | ✅ Completada |
| Diseño visual (mockup de pantallas Semana 1) | ✅ Aprobado |
| Semana 1 — Setup + Auth (backend) | ✅ 9/9 tareas implementadas, 27/27 tests |
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
| 4 | Migraciones 0004-0010 + modelos restantes | ✅ Completada y revisada |
| 5 | Hashing de contraseñas + JWT | ✅ Completada y revisada |
| 6 | Cifrado del token de GitHub (Fernet) | ✅ Completada y revisada |
| 7 | Endpoints de registro y login | ✅ Completada y revisada |
| 8 | Callback de GitHub OAuth | ✅ Completada y revisada |
| 9 | Listado de repositorios públicos | ✅ Implementada, en revisión final |

**Suite de tests: 27/27 pasando.**

**Endpoints funcionando:**

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/health` | Comprobación de salud del servicio |
| POST | `/api/auth/register` | Registro con email + contraseña |
| POST | `/api/auth/login` | Login, devuelve un JWT |
| GET | `/api/auth/github/login` | Devuelve la URL para iniciar el flujo de GitHub |
| GET | `/api/auth/github/callback` | Recibe el código de GitHub y devuelve un JWT |
| GET | `/api/repositories` | Lista los repositorios públicos del usuario |

**Infraestructura funcionando:** Docker Desktop levantado, contenedores de PostgreSQL y Redis sanos, ambas bases de datos creadas (`qalitiradar` para desarrollo, `qalitiradar_test` para tests) y las 10 migraciones aplicadas y verificadas en las dos.

**Base de datos:** 13 tablas creadas, datos de benchmarking simulados sembrados.

### 8. Cambio de nombre del proyecto

El proyecto pasó de llamarse **QualityRadar** a **QalitiRadar**. Se aplicó en documentación, código, `docker-compose.yml` y credenciales de base de datos (usuario y base `qalitiradar`, base de tests `qalitiradar_test`).

Pendiente de tu parte: renombrar el repositorio en GitHub (Settings → Repository name → `QalitiRadar`). En cuanto lo hagas, actualizo el remote local. GitHub mantiene redirecciones automáticas, así que nada se rompe mientras tanto.

Pendiente mío, para el final: renombrar la carpeta local en disco. Se pospuso a propósito porque el worktree de git guarda rutas absolutas y los contenedores montan `./backend` — renombrarla en plena implementación rompería ambos.

### 9. Problema de entorno resuelto: conflicto de puerto de PostgreSQL

Durante la Task 3 apareció un problema real del entorno: **un servicio nativo de PostgreSQL de Windows (`postgresql-x64-18`) ya estaba ocupando el puerto 5432**, así que todo lo que se conectaba a `localhost:5432` desde el host llegaba al servidor equivocado — fallando de forma silenciosa, sin error claro.

Solución aplicada: el contenedor de Postgres ahora se publica en el puerto **5433** del host. Tu PostgreSQL nativo queda intacto (parece estar en uso para Odoo). Las conexiones entre contenedores siguen usando `postgres:5432`; solo las herramientas que corren desde el host (pytest, alembic) apuntan a `localhost:5433`.

---

### 10. Problemas de seguridad encontrados y corregidos

Las revisiones independientes de cada tarea encontraron varios problemas reales que el plan original no contemplaba. Estos ya están **corregidos**:

- **Enumeración de usuarios por tiempo de respuesta** (login): el endpoint devolvía siempre el mismo error `401`, pero tardaba menos cuando el email no existía, porque se saltaba la comprobación de contraseña. Eso permite averiguar qué correos están registrados. Corregido igualando el costo de ambos caminos.
- **Errores de GitHub sin manejar**: cuando GitHub rechaza un código de autorización (lo más común: códigos expirados o ya usados), responde con `HTTP 200` y un cuerpo de error — no con un error HTTP. El código original habría fallado con un `500` genérico. Ahora devuelve `400` si el código es inválido y `502` si GitHub no responde, sin filtrar nunca el token ni la respuesta cruda de GitHub.
- **Faltaba el endpoint que inicia el flujo OAuth**: el plan solo tenía el callback, así que la regla de pedir exactamente los permisos `public_repo read:user user:email` no estaba implementada en ningún sitio. Se añadió `GET /api/auth/github/login`.
- **Modelo de datos incompleto**: faltaba el modelo `SharedReport`, lo que podía provocar que una futura migración automática propusiera borrar esa tabla.

### ⚠️ Deuda de seguridad pendiente (antes de producción)

Estas quedan documentadas en el código y **deben cerrarse antes de exponer el servicio públicamente**:

1. **Falta la protección CSRF del flujo OAuth** (parámetro `state`). Sin ella, un atacante podría hacer que la cuenta de GitHub de otra persona quede vinculada a su sesión. Implementarla requiere almacenamiento de sesión, que está fuera del alcance de la Semana 1. Es seguro mientras esto corra solo en local.
2. **Límite de 72 bytes de bcrypt**: contraseñas más largas provocan un error no manejado.
3. **Condición de carrera en el registro**: dos registros simultáneos del mismo email podrían devolver un `500` en lugar de `409`.

---

## Lo que sigue

1. Revisión final de toda la rama antes de integrarla a `main`.
2. Prueba end-to-end real del flujo de GitHub con las credenciales OAuth ya configuradas.
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
