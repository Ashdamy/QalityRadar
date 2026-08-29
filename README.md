# QalitiRadar

Escáner de calidad de software basado en **ISO/IEC 25010**. Analiza el código de un repositorio de GitHub, una aplicación ya desplegada, o ambos a la vez, y devuelve una puntuación por dimensiones con hallazgos, riesgos y un plan de mejora priorizado.

![Resultado de un análisis](docs/screenshots/04-resultado-del-analisis.png)

---

## Qué hace

| Modo | Qué analiza | Dimensiones |
|---|---|---|
| **Repositorio** | El código fuente de un repositorio público de GitHub | 6 |
| **URL** | Una aplicación ya desplegada, sin acceso al código | 5 |
| **Combinado** | Ambos, y explica **por qué no puntúan igual** | 11 |

El modo combinado es el que más información da. Cuando el código y la producción cuentan historias distintas, esa diferencia es accionable:

- **Código malo, producción buena** → la plataforma de despliegue te está regalando HTTPS, compresión y cabeceras. Esa ventaja no es tuya: desaparece si cambias de proveedor.
- **Código bueno, producción mala** → el proyecto está bien hecho pero mal desplegado, y esa calidad no le llega a quien usa la aplicación.

Además: histórico y comparación entre análisis, exportación a PDF, enlaces públicos temporales para compartir un informe, avisos cuando la calidad empeora, y **seguimiento continuo** de proyectos enganchados.

## La puntuación es exigente a propósito

**Los puntos se ganan, no se regalan.** Cada dimensión parte de cero y solo sube con evidencia real. Un repositorio vacío no puntúa alto por no tener problemas detectados: puntúa bajo porque no demuestra nada.

Además hay techos por gravedad: un hallazgo **crítico** limita la nota a 40 y uno **alto** la limita a 70, por buena que sea el resto del análisis. Un secreto filtrado no se compensa con buena documentación.

> Las puntuaciones son una aproximación al modelo ISO/IEC 25010. **No constituyen una certificación oficial.** El mapeo completo, con sus límites declarados, está en [`docs/ISO_25010_MAPPING.md`](docs/ISO_25010_MAPPING.md).

---

## Cómo se usa

### 1. Entrar

Con email y contraseña, o conectando tu cuenta de GitHub.

![Pantalla de inicio de sesión](docs/screenshots/01-inicio-sesion.png)

### 2. Elegir qué analizar

![Los tres modos de análisis](docs/screenshots/02-modos-de-analisis.png)

### 3. Lanzar el análisis

Para una aplicación desplegada basta con la dirección pública. No hace falta acceso al código.

![Formulario de análisis de URL](docs/screenshots/03-analizar-url.png)

### 4. Leer el resultado

Puntuación global, radar por dimensiones, resumen generado y la lista de hallazgos ordenada por gravedad.

![Resultado del análisis](docs/screenshots/04-resultado-del-analisis.png)

El radar y el desglose por dimensión enseñan dónde está el problema, no solo cuánto duele:

![Dimensiones del análisis](docs/screenshots/04b-dimensiones.png)

### 5. Compartir el informe

Genera un enlace público y temporal. Quien lo reciba no necesita cuenta.

![Crear un enlace para compartir](docs/screenshots/05-compartir-informe.png)

El enlace caduca a los 7 días (30 como máximo) y se puede revocar en cualquier momento.

![Informe público](docs/screenshots/06-informe-publico.png)

### 6. Dejar un proyecto vigilado

Engancha un repositorio y se reanaliza solo cuando subes código. Recibes un aviso con cómo evolucionó.

![Pantalla de seguimiento](docs/screenshots/07-seguimiento.png)

Comprobar si algo cambió cuesta **una llamada a la API de GitHub y no descarga tu código**; el análisis completo solo se lanza cuando de verdad hay un commit nuevo. Sin esa distinción, vigilar tres proyectos serían decenas de análisis diarios inútiles.

---

## Puesta en marcha

### Requisitos

- Docker y Docker Compose
- Python 3.11 o superior
- Node.js 20 o superior

### 1. Servicios de datos

```bash
docker compose up -d postgres redis
```

PostgreSQL queda en el puerto **5433** del host, no en el 5432, para no chocar con una instalación nativa.

### 2. Configuración

```bash
cp backend/.env.example backend/.env
```

Rellena `backend/.env`:

| Variable | Cómo obtenerla |
|---|---|
| `JWT_SECRET` | Cualquier cadena larga y aleatoria |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | Crea una OAuth App en GitHub con callback `http://localhost:3000/auth/github/callback` |
| `HUGGINGFACE_API_KEY` | Opcional. Sin ella los resúmenes se generan con plantilla en vez de con IA |

Ejecutando fuera de Docker, apunta a `localhost`:

```
DATABASE_URL=postgresql+psycopg://qalitiradar:qalitiradar_dev@localhost:5433/qalitiradar
REDIS_URL=redis://localhost:6379/0
```

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 4. Worker

En otra terminal. **Corre en el host, no en un contenedor**, para poder lanzar los contenedores de análisis sin montar el socket de Docker dentro de otro contenedor — que es una vía clásica de escalada a root.

```bash
cd backend
celery -A app.worker.celery_app worker --loglevel=info --pool=solo
```

Y el planificador, para el seguimiento continuo y la purga:

```bash
celery -A app.worker.celery_app beat --loglevel=info
```

> En Windows tienen que ser dos procesos: la opción `-B` del worker no está soportada.

### 5. Imagen del sandbox

```bash
docker build -t qalitiradar-analyzer ./analyzer
```

### 6. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abre **http://localhost:3000**.

---

## Cómo está construido

```
Navegador ──▶ Next.js ──▶ FastAPI ──▶ PostgreSQL
                             │
                             ▼
                        Redis (cola)
                             │
                             ▼
                      Worker de Celery ──▶ Contenedor de análisis
                                             (aislado, sin red)
```

**Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, Celery, Redis
**Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4
**Análisis:** Gitleaks y Semgrep en sandbox, OSV.dev para vulnerabilidades de dependencias
**Informes:** ReportLab · **Resúmenes:** Hugging Face (con plantilla de respaldo)

### Seguridad

El código ajeno **nunca se ejecuta**. El análisis es estático y corre dentro de un contenedor efímero:

```
--network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges
--memory=512m --cpus=0.5 --pids-limit=100 --user 65534:65534
```

El aislamiento está **verificado con pruebas reales contra Docker**, no solo declarado: un contenedor que intenta salir a internet falla, y uno que intenta escribir en el repositorio montado es rechazado.

Al analizar una URL se resuelve el DNS y se valida la IP **en cada salto de redirección**, no solo en la dirección inicial, para que una redirección no pueda apuntar a la red interna.

---

## Pruebas

```bash
cd backend && pytest              # 345 pruebas
cd frontend && npx playwright test # 5 recorridos end-to-end
```

Las end-to-end usan un navegador real contra la aplicación en marcha. Requieren los servicios levantados y una base de datos cuyo nombre acabe en `_test`.

---

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Componentes, flujos y riesgos de seguridad |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Esquema completo: tablas, relaciones e índices |
| [`docs/ISO_25010_MAPPING.md`](docs/ISO_25010_MAPPING.md) | Qué señal alimenta cada característica del estándar |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Cómo ponerlo en internet, y qué cerrar antes de abrirlo |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Plan por semanas con criterios de salida |
| [`RESUME.md`](RESUME.md) | Bitácora del desarrollo y decisiones tomadas |

---

## Límites conocidos

Se declaran porque afectan a cómo hay que leer los resultados:

- **Solo repositorios públicos.** Los privados quedan fuera del alcance actual.
- **Se analiza una sola página** en el modo URL, la que se indique — no el sitio entero.
- **El rendimiento medido es el tiempo de respuesta del servidor**, no el de carga completa en un navegador.
- **Las comprobaciones de accesibilidad son estáticas** sobre el HTML y no sustituyen a una auditoría con axe-core.
- **La actividad del proyecto no forma parte de ISO/IEC 25010.** Se incluye porque predice la mantenibilidad futura, pero está declarada como añadido propio.

---

## Estado

Los tres modos de análisis funcionan de principio a fin. Queda el despliegue en producción.

Las defensas que hacen falta para abrirlo al público están implementadas: tope global de análisis simultáneos, límite de registros por IP, longitud mínima de contraseña, revocación real de sesión y `noindex` en los informes compartidos. Los detalles y qué ajustar según la máquina están en [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

Queda pendiente la verificación por email, que exige infraestructura de correo.

## Licencia

[MIT](LICENSE). Puedes usarlo, modificarlo y distribuirlo libremente, citando la autoría.
