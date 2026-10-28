# Despliegue

Cómo poner QalitiRadar en internet para que otras personas puedan usarlo.

---

## La restricción que decide todo lo demás

**El worker necesita hablar con el demonio de Docker** para levantar los contenedores donde se analiza el código ajeno. Eso descarta de golpe la mayoría de plataformas.

| Plataforma | ¿Sirve? | Por qué |
|---|---|---|
| Vercel, Netlify | Solo el frontend | No ejecutan procesos de fondo |
| Render, Railway, Fly.io | **No para el worker** | Ejecutan *tu* contenedor, pero no te dejan crear contenedores hermanos |
| Google Cloud Run | No | Sin demonio de Docker dentro |
| **Una máquina virtual con Docker** | **Sí** | Es la única forma de que el worker cree contenedores |

Así que el reparto es:

```
Frontend  ──▶  Vercel                      (gratis)
Backend   ──▶  máquina virtual con Docker   ─┐
Worker    ──▶  la misma máquina, en el host ─┤ juntos
Analyzer  ──▶  contenedores efímeros        ─┘
PostgreSQL──▶  gestionado o en la misma máquina
Redis     ──▶  gestionado o en la misma máquina
```

---

## Dónde alojar la máquina

| Opción | Recursos | Coste | Aviso |
|---|---|---|---|
| **Oracle Cloud Always Free** | 4 núcleos ARM, 24 GB | Gratis para siempre | Lo mejor gratis, pero **muy a menudo da «out of capacity»** y hay que insistir días |
| **Hetzner CX22** | 2 vCPU, 4 GB | ~4 €/mes | Lo que yo elegiría: se aprovisiona al momento y no falla |
| AWS / Google Cloud, capa gratuita | 1 vCPU, 1 GB | Gratis 12 meses | **1 GB se queda corto**: cada análisis reserva 512 MB y además corre PostgreSQL |

Con menos de 2 GB de RAM el sistema se cae en cuanto haya dos análisis a la vez.

---

## Pasos

### 1. Preparar la máquina

```bash
ssh usuario@tu-servidor
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # cerrar sesión y volver a entrar
```

### 2. Traer el proyecto y construir el sandbox

```bash
git clone https://github.com/Ashdamy/QalityRadar.git
cd QalityRadar
docker build -t qaliti/analyzer:latest ./analyzer
```

Sin esa imagen, **todos los análisis de repositorio fallan**. Es el paso que más se olvida.

### 3. Configurar

```bash
cp backend/.env.example backend/.env
```

Lo que cambia respecto a desarrollo:

```bash
JWT_SECRET=<64 caracteres aleatorios: openssl rand -hex 32>
ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# El dominio del frontend, no localhost. Sin esto el navegador bloquea la API.
CORS_ORIGINS=https://qalitiradar.vercel.app

# Apaga /docs, /redoc y /openapi.json. Publicados regalan el mapa completo de
# la API y le ahorran a un atacante todo el trabajo de reconocimiento.
ENABLE_API_DOCS=false

# Tiene que ser el mismo que pongas en la OAuth App de GitHub, y con https.
GITHUB_OAUTH_REDIRECT_URI=https://qalitiradar.vercel.app/auth/github/callback

# El enlace de verificacion del correo apunta aqui.
FRONTEND_BASE_URL=https://qalitiradar.vercel.app

# Correo de verificacion. Cualquier proveedor SMTP sirve (Resend, Brevo,
# Amazon SES...). STARTTLS siempre: sin el, la contrasena del SMTP viaja en claro.
SMTP_HOST=smtp.tu-proveedor.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_STARTTLS=true
MAIL_FROM=QalitiRadar <no-reply@tu-dominio.com>
```

> **Sin `SMTP_HOST` nadie puede registrarse con contraseña.** La cuenta se crea, pero el enlace no sale y sin él no se entra. Lo único que avisa es una línea en el log: `SMTP_HOST sin configurar`. Entrar por GitHub sigue funcionando. Para que los correos no acaben en spam, configura SPF y DKIM del dominio de `MAIL_FROM` en tu proveedor.

> **Pon `COOKIE_SECURE=true`.** La sesión viaja en cookies; sin esto viajan también por HTTP y cualquiera en la misma red puede leerlas. El frontend y la API deben quedar bajo el mismo dominio (por ejemplo `qalitiradar.com` y `api.qalitiradar.com`): las cookies usan `SameSite=Lax`, que es lo que las protege de CSRF, y con dominios distintos el navegador no las enviaría.

> **La aplicación no arranca si alguno sigue con el valor de ejemplo o mide menos de 32 caracteres.** Es deliberado: un despliegue con `JWT_SECRET=change-me-in-production` funciona igual de bien y no da ninguna señal hasta que alguien firma el token que quiera.

> **Nunca reutilices el `JWT_SECRET` ni el `ENCRYPTION_KEY` de desarrollo.** El de cifrado protege los tokens de GitHub de tus usuarios; si se filtra, se filtran sus cuentas.

### 4. Levantar datos y API

```bash
docker compose up -d postgres redis backend
docker compose exec backend alembic upgrade head
```

### 5. El worker, en el host

**No dentro de un contenedor.** Meterlo en uno obligaría a montar `/var/run/docker.sock`, que es una vía conocida de escalada a root en la máquina anfitriona.

El worker se instala desde `requirements.txt`, no desde `requirements.in`: trae las versiones transitivas fijadas y sus hashes, así que instala exactamente lo mismo que el contenedor de la API y lo mismo que audita el CI.

```bash
cd backend
pip install --require-hashes -r requirements.txt
celery -A app.worker.celery_app worker --loglevel=info &
celery -A app.worker.celery_app beat --loglevel=info &
```

Para que sobrevivan a un reinicio, conviene un servicio de systemd por cada uno.

### 6. HTTPS

GitHub exige `https` en el callback de OAuth, y el navegador bloquea peticiones desde una página segura hacia una API que no lo es. **Caddy** lo resuelve con dos líneas y saca el certificado solo:

```
api.tu-dominio.com {
    reverse_proxy localhost:8000
}
```

### 7. Frontend en Vercel

Importa el repositorio en Vercel y configura:

- **Root Directory:** `frontend`
- **Variables de entorno:**
  - `NEXT_PUBLIC_API_URL=https://api.tu-dominio.com`
  - `NEXT_PUBLIC_SITE_URL=https://tu-dominio.com`. Sale en el sitemap, en `robots.txt` y en las etiquetas para compartir en redes. Si se queda en `localhost`, Google indexa direcciones que no existen.

> **Antes de abrirlo al público, rellena los datos legales.** `frontend/src/app/privacidad/page.tsx` y `frontend/src/app/terminos/page.tsx` tienen marcadores entre corchetes: tipo de sociedad, NIT, dirección, ciudad, teléfono, correo de privacidad y de contacto, área responsable, proveedor de correo y de alojamiento con sus países. La Ley 1581 exige identificar al responsable; publicarlas con corchetes es no cumplirla. Conviene que un abogado revise ambos textos.

Una vez publicada, da de alta el dominio en [Google Search Console](https://search.google.com/search-console) y envía `https://tu-dominio.com/sitemap.xml`. Es lo que hace que Google la encuentre en días en vez de semanas.

### 8. Actualizar la OAuth App de GitHub

En *Settings → Developer settings → OAuth Apps*, cambia el callback a la dirección real:

```
https://qalitiradar.vercel.app/auth/github/callback
```

---

## Lo que ya está resuelto

Estas defensas no hacían falta mientras el proyecto corría en un ordenador propio, pero sí en cuanto hay una dirección pública. Están implementadas y probadas:

| Riesgo | Cómo se ataja |
|---|---|
| Diez cuentas coincidiendo tumban la máquina | **Tope global de 6 análisis simultáneos**, además de los límites por usuario |
| Crear cuentas en cadena para saltarse los límites | **Verificación del correo** y 5 registros por hora y por IP |
| Contraseñas de un carácter | **Mínimo 8** en el registro |
| Un token robado sirve 30 días | **Cerrar sesión lo invalida en el servidor**, no solo en el navegador |
| Google indexando informes compartidos | **`noindex`** en `/r/[token]` |
| Navegador confiando de más en la API | **Cabeceras de seguridad** en cada respuesta |
| Reconocimiento gratis de la API | **`/docs` apagado** con `ENABLE_API_DOCS=false` |
| Un backup de `.env` subido sin querer | **`.env.*` ignorado** en git |

Sobre el tope global: `MAX_GLOBAL_CONCURRENT = 6` está pensado para una máquina de 4 GB. Cada análisis reserva 512 MB, así que en el peor caso son 3 GB más PostgreSQL. **Si despliegas en una máquina más pequeña, baja ese número** en `app/services/rate_limit_service.py`.

Sobre el registro: cada cuenta con contraseña necesita un buzón real, y además solo se pueden crear 5 por hora desde la misma IP. Un correo desechable sigue colando, así que esto sube el coste del abuso pero no lo elimina.

El inventario completo de defensas, con lo que **no** está cubierto, está en [`SECURITY.md`](SECURITY.md).

---

## Qué vigilar una vez en marcha

- **Memoria.** Es lo primero que se agota. `docker stats` durante un análisis.
- **Espacio en disco.** Cada análisis clona un repositorio. Se borran solos, pero las imágenes de Docker se acumulan: `docker system prune` de vez en cuando.
- **Límite de la API de GitHub.** 5.000 peticiones por hora y por token. La vigilancia gasta una por comprobación, así que hace falta mucho para agotarlo.
- **La purga.** Corre sola una vez al día y mantiene la base acotada. Si Celery Beat no está en marcha, la base crece sin freno.

---

## Coste real

| Concepto | Gratis | Recomendado |
|---|---|---|
| Frontend | Vercel Hobby | igual |
| Servidor | Oracle Always Free | Hetzner ~4 €/mes |
| PostgreSQL | En el servidor · [Neon](https://neon.tech) | igual |
| Redis | En el servidor · [Upstash](https://upstash.com) | igual |
| Dominio | Subdominio de Vercel | ~10 €/año |
| IA de resúmenes | Hugging Face gratuito | igual |
| **Total** | **0 €** | **~5 €/mes** |

Se puede desplegar entero **sin pagar nada**, a cambio de pelearse con la disponibilidad de Oracle Cloud.
