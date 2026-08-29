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

## Lo que ya está resuelto

Estas defensas no hacían falta mientras el proyecto corría en un ordenador propio, pero sí en cuanto hay una dirección pública. Están implementadas y probadas:

| Riesgo | Cómo se ataja |
|---|---|
| Diez cuentas coincidiendo tumban la máquina | **Tope global de 6 análisis simultáneos**, además de los límites por usuario |
| Crear cuentas en cadena para saltarse los límites | **5 registros por hora y por IP** |
| Contraseñas de un carácter | **Mínimo 8** en el registro |
| Un token robado sirve 30 días | **Cerrar sesión lo invalida en el servidor**, no solo en el navegador |
| Google indexando informes compartidos | **`noindex`** en `/r/[token]` |

Sobre el tope global: `MAX_GLOBAL_CONCURRENT = 6` está pensado para una máquina de 4 GB. Cada análisis reserva 512 MB, así que en el peor caso son 3 GB más PostgreSQL. **Si despliegas en una máquina más pequeña, baja ese número** en `app/services/rate_limit_service.py`.

Sobre el registro por IP: no sustituye a verificar el email, que sigue siendo lo suyo si esto llega a tener uso real. Sube el coste del abuso, no lo elimina — alguien con varias IP puede saltárselo.

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
