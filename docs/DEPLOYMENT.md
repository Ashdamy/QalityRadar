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
docker build -t qalitiradar-analyzer ./analyzer
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

# Tiene que ser el mismo que pongas en la OAuth App de GitHub, y con https.
GITHUB_OAUTH_REDIRECT_URI=https://qalitiradar.vercel.app/auth/github/callback
```

> **Nunca reutilices el `JWT_SECRET` ni el `ENCRYPTION_KEY` de desarrollo.** El de cifrado protege los tokens de GitHub de tus usuarios; si se filtra, se filtran sus cuentas.

### 4. Levantar datos y API

```bash
docker compose up -d postgres redis backend
docker compose exec backend alembic upgrade head
```

### 5. El worker, en el host

**No dentro de un contenedor.** Meterlo en uno obligaría a montar `/var/run/docker.sock`, que es una vía conocida de escalada a root en la máquina anfitriona.

```bash
cd backend
pip install -r requirements.txt
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
- **Variable de entorno:** `NEXT_PUBLIC_API_URL=https://api.tu-dominio.com`

### 8. Actualizar la OAuth App de GitHub

En *Settings → Developer settings → OAuth Apps*, cambia el callback a la dirección real:

```
https://qalitiradar.vercel.app/auth/github/callback
```

---

## Antes de abrirlo al público

Estas tres cosas **no** son un problema mientras el proyecto corre en tu ordenador, pero sí lo son en cuanto haya una dirección pública. Se declaran porque son decisiones conscientes, no descuidos.

### 1. No hay tope global de análisis simultáneos

Los límites existentes son **por usuario**: 5 análisis por hora, 2 a la vez, más 1 automático de la vigilancia. No hay ningún tope para el conjunto del servidor.

Diez personas a la vez pueden pedir 30 contenedores. A 512 MB cada uno son 15 GB de RAM, y la máquina se cae.

*Solución:* limitar la concurrencia del worker (`--concurrency=2`), que hace de tope real, y vigilar la memoria.

### 2. Cualquiera puede crear cuentas sin límite

No hay verificación de email. Como los límites de uso son por cuenta, alguien puede registrar diez cuentas y saltárselos.

*Solución:* verificación por email, o límite por IP en el registro.

### 3. Cerrar sesión no invalida el token de refresco

La renovación de sesión es sin estado: el token de refresco es válido 30 días y el servidor no lleva registro de cuáles siguen vivos. Cerrar sesión lo borra del navegador, pero un token robado seguiría funcionando.

*Solución:* guardar los tokens de refresco en la tabla `refresh_tokens`, que ya existe en el esquema, y marcarlos como revocados al cerrar sesión.

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
