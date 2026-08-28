# RESUME — Bitácora de QalitiRadar

> Documento vivo. Se actualiza a medida que avanza el proyecto.
> Última actualización: 2026-08-27 (Semana 1 backend completa)

---

## ¿En qué etapa va el proyecto?

**Fase actual: los tres modos de análisis funcionan de punta a punta. Queda la Semana 5 (compartir, límites de uso y despliegue).**

| Etapa | Estado |
|---|---|
| Fase 0 — Arquitectura y diseño | ✅ Completada |
| Diseño visual (mockup de pantallas Semana 1) | ✅ Aprobado |
| Semana 1 — Setup + Auth (backend) | ✅ 9/9 tareas implementadas |
| Semana 1 — Frontend (3 pantallas reales) | ✅ Implementado y funcionando |
| Semana 2A — Motor de análisis (sandbox + primer resultado) | ✅ Completada |
| Semana 2B — Las seis dimensiones ISO 25010 | ✅ Completada |
| Histórico, comparación y resumen ejecutivo | ✅ Completado |
| Exportación del informe a PDF | ✅ Completada |
| Modo 2 — Análisis de aplicaciones desplegadas (URL) | ✅ Completado |
| Resúmenes con IA (Hugging Face) | ✅ Activados en los tres modos |
| Modo 3 — Código frente a producción (combinado) | ✅ Completado |
| Deuda de seguridad (OAuth `state`, bcrypt, carrera) | ✅ Cerrada |
| Sesiones con renovación automática | ✅ Implementadas |
| Semana 5 — Compartir, límites de uso, purga y avisos | ✅ Completada |
| Pruebas end-to-end (Playwright) | ✅ 5 en verde |
| Seguimiento continuo de proyectos | ✅ Completado |
| Despliegue | ⏸️ A la espera de tu señal |

**328 pruebas en verde** en el backend y **5 end-to-end** con navegador real; el frontend compila y pasa lint.

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

Escribí `docs/plans/2026-08-27-week1-setup-auth.md`: 9 tareas paso a paso con metodología TDD (test primero, verificar que falla, implementar, verificar que pasa, commit). Cada tarea trae el código exacto a escribir, los comandos a correr, y el resultado esperado.

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

**Cerradas.** Las tres quedaron resueltas antes de plantear el despliegue (ver sección 16).

1. ~~Falta la protección CSRF del flujo OAuth~~ → implementada con `state` sobre Redis, de un solo uso.
2. ~~Límite de 72 bytes de bcrypt~~ → el registro ya lo validaba; ahora el login tampoco falla.
3. ~~Condición de carrera en el registro~~ → la restricción única de la tabla se traduce a `409`.

---

### 11. Semana 2A — El motor de análisis funciona

Ya se puede analizar un repositorio real de punta a punta. Piezas construidas:

- **Sandbox aislado** — contenedor efímero sin red, sistema de archivos en solo lectura, sin capacidades del kernel, 512 MB y medio núcleo. El aislamiento está **verificado con pruebas reales contra Docker**, no solo declarado: un contenedor que intenta salir a internet falla, y uno que intenta escribir en el repositorio montado es rechazado.
- **Clonado efímero** — clon superficial que se borra siempre, incluso cuando el análisis falla. Aquí apareció un bug real de Windows: `shutil.rmtree(ignore_errors=True)` fallaba en silencio porque git deja archivos en solo-lectura, dejando código ajeno en disco. Corregido.
- **Tres analizadores estáticos** — estructura (lenguajes, forma del proyecto), documentación (README, licencia, arquitectura) y tests (detección y clasificación, sin ejecutarlos nunca).
- **Motor de puntuación ISO 25010** — nota 0-100 por dimensión, ponderada según el estándar.
- **Endpoints** `POST /api/repositories/{id}/analyze` y `GET /api/analyses/{id}`.

Prueba real sobre `axios/axios`: 466 archivos analizados, 126 tests frente a 91 fuentes, puntuación 100/100 sin hallazgos — coherente con un proyecto ejemplarmente mantenido. Sobre `octocat/Hello-World` sí detecta hallazgos reales (sin licencia, sin tests).

**Hueco cerrado:** el listado de repositorios consultaba GitHub pero no guardaba nada, así que no había contra qué lanzar un análisis. Ahora se persisten al listarlos.

**Ojo con la puntuación:** hoy se calcula sobre 3 de las 6 dimensiones. Faltan seguridad, portabilidad y actividad (Semana 2B), así que todavía no es la nota definitiva.

---

### 12. Semana 2B y la exigencia de la puntuación

Se completaron las seis dimensiones (dependencias, CI/CD, seguridad con Gitleaks y Semgrep, actividad del proyecto).

Aquí llegó una crítica tuya que cambió el motor de raíz: *"por más malo que sea el repositorio siempre da una calificación muy alta"*. Tenías razón, y el fallo era conceptual: la puntuación **premiaba la ausencia de evidencia**. Un repositorio vacío no tenía problemas detectados, así que puntuaba alto.

El modelo se invirtió: **los puntos se ganan, no se regalan**. Cada dimensión parte de 0 y sube solo con evidencia real. El mismo error apareció dos veces más en rúbricas nuevas (un diccionario vacío puntuaba 12 y 18); ahora hay guardas que lo impiden.

También se añadieron topes por gravedad: un hallazgo crítico limita la nota a 40, uno alto a 70. Y a petición tuya se profundizó en las sub-características de la ISO 25010 para medir más aspectos dentro de cada dimensión, en lugar de calificar siempre sobre las mismas señales.

### 13. Histórico, comparación, PDF y resúmenes con IA

- **Histórico y comparación** entre dos análisis, con evolución por dimensión.
- **Informe en PDF** (ReportLab, Python puro).
- **Resúmenes con IA** vía Hugging Face. El dominio `api-inference` fue retirado, así que se migró al router (`router.huggingface.co`) con Llama 3.1 8B. Hay plantilla de respaldo: si la IA no responde, el resumen se genera igual y se marca su origen.

### 14. Modo 2 — Aplicaciones desplegadas

Análisis de una URL pública en cinco dimensiones (rendimiento, seguridad, usabilidad, accesibilidad, compatibilidad), con **84 señales** en total tras ampliarlo a petición tuya.

Defensa contra SSRF: se resuelve el DNS y se valida la IP **en cada salto de redirección**, no solo en la dirección inicial.

### 15. Modo 3 — Código frente a producción

Analiza el repositorio y su despliegue y explica **por qué no puntúan igual**, que es lo que de verdad aporta información:

- *Código malo, producción buena:* la plataforma regala HTTPS, compresión y cabeceras. Esa ventaja no es tuya y desaparece si migras de proveedor.
- *Código bueno, producción mala:* el esfuerzo no le está llegando a quien usa la aplicación.

Cada mitad se ejecuta como un análisis propio y completo, así que entra en el histórico y se puede abrir por separado.

**Comprobación de correspondencia:** es fácil pegar la URL de otra aplicación, y entonces la comparación no significa nada. El sistema **avisa, nunca bloquea** — un dominio propio, un monorepo o un proyecto renombrado son casos legítimos donde los nombres no coinciden. La página de error de la plataforma advierte por sí sola (es un hecho comprobable: ahí no hay despliegue); las señales heurísticas solo advierten cuando coinciden las dos.

Dos fallos que salieron al escribir las pruebas:

- `consolidate_score` decía ponderar por evidencia pero era una media simple: los pesos de cada modo están normalizados a 1.0 por separado, así que sumarlos no distingue un modo de otro.
- La comprobación de correspondencia volvía a clonar el repositorio solo para saber si genera una web; esa información ya estaba en las métricas del analizador de estructura.

---

### 16. Deuda de seguridad cerrada y sesiones que ya no caducan solas

**Protección CSRF del OAuth.** El flujo no generaba ni validaba el parámetro `state`, así que un tercero podía forzar el callback con un `code` propio y dejar **su** cuenta de GitHub vinculada a **tu** sesión. Ahora cada solicitud emite un `state` imposible de adivinar, guardado en Redis con 10 minutos de vida y **de un solo uso**: reproducir un callback capturado no sirve. Se eligió Redis y no memoria del proceso por dos razones concretas: sobrevive a un reinicio del backend, y funciona con varias instancias detrás de un balanceador, donde la ida y la vuelta pueden caer en procesos distintos.

**Límite de bcrypt.** El registro ya rechazaba contraseñas de más de 72 bytes, pero el login no: bcrypt lanzaba `ValueError` y el cliente recibía un `500`. Ahora devuelve `401`, que es la respuesta correcta — una contraseña así no puede coincidir con ningún hash almacenado.

**Carrera en el registro.** Comprobar si el email existe y después insertarlo deja una ventana: entre las dos operaciones otra petición puede haber insertado el mismo email. La única defensa real es la restricción única de la tabla, y ahora su error se traduce a `409` en vez de escaparse como `500`.

**Sesiones.** El token de acceso dura 15 minutos y el frontend nunca usó el de refresco, así que había que iniciar sesión constantemente. Ahora el cliente guarda ambos y renueva el acceso **en silencio** al recibir un `401`, reintentando la petición original. Si varias peticiones caducan a la vez comparten una sola renovación.

Los dos tipos de token se firman con el mismo secreto, así que llevan una marca de tipo: sin ella, un token de refresco robado valdría como token de acceso y daría 30 días en vez de un solo canje. Los emitidos antes de este cambio no la llevan y se tratan como de acceso, para no cerrar las sesiones abiertas al desplegar.

**41 pruebas nuevas** (262 en total).

---

### 17. Semana 5 y seguimiento continuo

**Enlaces compartidos.** `POST /api/analyses/{id}/share` crea un enlace público y temporal; `GET /api/reports/shared/{token}` lo sirve sin sesión. El token **es** la credencial, así que son 256 bits, caduca (7 días por defecto, 30 como máximo) y cada enlace se revoca por separado. Un token inexistente y uno caducado dan exactamente la misma respuesta: distinguirlos convertiría el endpoint en un oráculo sobre qué tokens han existido.

**Límites de uso.** 5 análisis por hora, 20 al día y 2 en paralelo, comprobados **antes de encolar**. Si se comprobaran en el worker, el cliente recibiría un `202` para algo que después se descarta en silencio. Ventana deslizante sobre Redis y no contador por hora natural, porque con contadores fijos se pueden lanzar 5 a las 10:59 y otros 5 a las 11:00.

**Purga.** Tarea diaria: máximo 50 análisis por objetivo y 90 días de retención, pero **siempre se conservan los 10 últimos**. Un proyecto aparcado que se retoma necesita su histórico para poder compararse con el pasado.

**Avisos.** Caída de más de 10 puntos, riesgos críticos nuevos, vulnerabilidades introducidas o cobertura que se desploma. Dentro de la aplicación, no por email: no hay infraestructura de correo y el MVP es gratuito. Los hallazgos nuevos se detectan comparando **títulos y no cantidades**: si se arregla uno y aparece otro, el total no cambia pero el problema nuevo existe.

**Pruebas end-to-end.** El flujo de URL se recorre entero con navegador real: registro → análisis → resultado → compartir → abrir el enlace público sin sesión. Los flujos de repositorio y combinado no se automatizan porque parten de repositorios de GitHub y eso exige un token OAuth real; fingir ese paso probaría el simulacro, no el sistema.

### 18. Seguimiento continuo

Idea tuya: dejar un proyecto enganchado y ver cómo evoluciona sin volver a pulsar «Analizar».

**La decisión que lo hace viable:** comprobar es barato, analizar es caro. Un análisis clona el repositorio y levanta un contenedor —casi un minuto—; preguntarle a GitHub cuál es el último commit es una llamada que no descarga código. Así que se comprueba cada 5 minutos y **solo se analiza cuando el commit cambia**. Si nadie ha subido nada, la vuelta no cuesta prácticamente nada.

Para direcciones no hay commit, así que se usa el `ETag` o el `Last-Modified` con una petición `HEAD`.

**Los análisis automáticos tienen cuota propia** (10/hora, 40/día), separada de la del usuario. Compartirla era el fallo más previsible: un proyecto vigilado le consumiría los análisis manuales y se encontraría bloqueado sin haber hecho nada.

**Fusión con los avisos.** Si el análisis lo lanzó el sistema, el usuario no estaba delante: se le cuenta cómo fue, **también cuando mejora**. Si lo pidió a mano, no se le avisa — el resultado ya lo tiene en pantalla. Y si la nota no se movió, silencio: un aviso diario de «sigue igual» enseña a ignorar la campana.

**Verificado en vivo** contra GitHub real: el ciclo detectó el commit `2354d41`, disparó el análisis en 2 segundos, terminó con 58,50 y generó el aviso «Ha bajado 7 puntos: ahora 58». Una segunda comprobación con el mismo commit **no** lanzó nada, que es la propiedad que sostiene toda la función.

**Nota de entorno:** en Windows, Celery Beat no puede ir dentro del worker (`-B` no está soportado); son dos procesos.

---

## Lo que sigue

1. **Despliegue**, cuando tú lo digas. La recomendación sigue siendo **Vercel para el frontend y Oracle Cloud Always Free para el backend**: Render y Railway no dan acceso al demonio de Docker, que el sandbox necesita.
2. Al desplegar, la vigilancia mejora sola: con una dirección pública se pueden usar **webhooks de GitHub** y el análisis arrancaría a los segundos del push, en vez de esperar a la siguiente comprobación.
3. Pendiente menor: la tabla `refresh_tokens` del modelo de datos no se usa. La renovación de sesión es sin estado, lo que funciona pero no permite revocar una sesión concreta al cerrarla.

---

## Enlaces útiles

- Repositorio: https://github.com/Ashdamy/QalitiRadar
- Especificación original: [`context/claude.md`](context/claude.md)
- Arquitectura: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Modelo de datos: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)
- Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Plan de la Semana 1: [`docs/plans/2026-08-27-week1-setup-auth.md`](docs/plans/2026-08-27-week1-setup-auth.md)
