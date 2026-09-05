# Seguridad de QalitiRadar

Todas las defensas del sistema, por qué existen y dónde están en el código.

Este documento se mantiene **honesto a propósito**: la última sección enumera lo que *no* está cubierto. Una lista de seguridad que solo cuenta lo bueno sirve para tranquilizar, no para proteger.

---

## El riesgo que define este proyecto

QalitiRadar **descarga y analiza código de desconocidos**. Cualquiera puede pedirle que analice un repositorio público, y ese repositorio puede estar diseñado para atacar a quien lo analice.

Todo lo demás son problemas de aplicación web corrientes. Este no.

**La regla de la que cuelga todo: el código analizado nunca se ejecuta.** Solo se lee. Ni se instalan dependencias, ni se lanzan sus pruebas, ni se ejecutan sus scripts de construcción. Herramientas como SonarQube o Snyk sí ejecutan parte del proyecto; aquí se renunció a eso a cambio de eliminar la clase de ataque entera.

---

## 1. El sandbox de análisis

`backend/app/utils/sandbox.py`

Las herramientas de inspección (Gitleaks, Semgrep) corren dentro de un contenedor efímero con todo cerrado:

| Restricción | Qué impide |
|---|---|
| `--network=none` | Que el código analizado salga a internet o alcance la red interna |
| `--read-only` | Que escriba en el sistema de archivos del contenedor |
| `--cap-drop=ALL` | Todas las capacidades del kernel, sin excepción |
| `--security-opt=no-new-privileges` | Que un binario `setuid` escale privilegios |
| `--memory=512m --memory-swap=512m` | Agotar la memoria de la máquina |
| `--cpus=0.5` | Acaparar la CPU |
| `--pids-limit=100` | Una bomba de procesos (*fork bomb*) |
| `--user 65534:65534` | Ejecutar como `nobody`, nunca como root |
| `--rm` | Que quede rastro entre análisis |
| Montaje `:ro` | Que modifique el repositorio clonado |
| `--tmpfs /tmp:noexec,nosuid` | Escribir un binario en `/tmp` y ejecutarlo |

**Verificado, no solo declarado.** Hay pruebas que levantan Docker de verdad: un contenedor que intenta salir a internet falla, y uno que intenta escribir en el repositorio montado es rechazado. Están en `backend/tests/test_sandbox.py`.

### Inyección de argumentos

El nombre de la imagen se valida contra un patrón y se rechaza si empieza por `-`. Además, el comando lleva `--` antes de la imagen: aunque algo se colara en la validación, Docker ya no puede interpretarlo como una opción.

### Ningún contenedor corre como root

Ni el del análisis (ya lo hacía: `--user 65534:65534`) ni los de la propia aplicación. `backend/Dockerfile` termina en `USER 65534:65534` y `frontend/Dockerfile` en `USER node`. Si alguien logra ejecutar código dentro, la diferencia entre root y `nobody` es la diferencia entre escaparse por un fallo del núcleo y no tener por dónde empezar.

### El worker corre en el host, no en un contenedor

Es deliberado y es lo contrario de lo que parece razonable. Para crear contenedores desde dentro de otro contenedor habría que montarle `/var/run/docker.sock`, y quien controla ese socket **es root en la máquina anfitriona**. Se prefiere un worker en el host, con acceso a Docker, antes que un contenedor que regala la máquina entera si se compromete.

---

## 2. SSRF: analizar direcciones que indica el usuario

`backend/app/utils/url_validation.py`, `backend/app/utils/safe_http.py`

El modo URL hace peticiones a donde diga el usuario. Sin defensas, eso convierte al servidor en un ariete contra su propia red interna.

- **Solo `http` y `https`.** Nada de `file://`, `gopher://` ni `ftp://`.
- **Se resuelve el DNS y se comprueba la IP**, no el nombre. Un dominio puede apuntar a `127.0.0.1`.
- Se rechazan direcciones privadas, de bucle local, enlace local y reservadas.
- **Puertos bloqueados**: 22, 23, 25, 445, 3306, 5432, 5433, 6379, 9200, 11211, 27017 — SSH, correo, y las bases de datos y cachés que suelen escuchar sin contraseña dentro de una red.
- **La validación se repite en cada salto de redirección.** Es el punto que casi todos fallan: una dirección pública puede redirigir a `169.254.169.254` (metadatos de la nube) y, si solo se valida la primera, la defensa no sirve de nada.
- **Se conecta contra la IP validada, no contra el nombre.** Entre comprobar el dominio y abrir la conexión, el atacante —que controla su propio DNS— puede responder una IP pública a la comprobación y una interna a la conexión (*DNS rebinding*). Fijando la IP, la conexión va justo a donde se comprobó. La cabecera `Host` y el `sni_hostname` siguen llevando el dominio, para que el servidor enrute igual y TLS valide el certificado contra el dominio y no contra la IP.
- **El cuerpo se corta a 3 MB leyendo por trozos.** Antes se leía la respuesta entera y *después* se recortaba: el tope existía, pero la memoria ya se había gastado, así que un servidor que responde un flujo sin fin tumbaba el worker.
- **Los monitores revalidan en cada comprobación.** Un proyecto vigilado vive semanas y el DNS pudo cambiar desde el alta: la validación del primer día ya no vale.

---

## 3. Autenticación y sesiones

`backend/app/core/security.py`, `backend/app/services/session_service.py`, `backend/app/api/auth.py`

- **Contraseñas con bcrypt** y sal por contraseña. Mínimo 8 caracteres, máximo 72 (límite de bcrypt).
- **Tiempo constante al iniciar sesión.** Si el email no existe se compara igualmente contra un hash ficticio, de modo que no se pueda averiguar qué correos están registrados midiendo el tiempo de respuesta.
- **JWT con algoritmo fijado** a HS256. Se pasa `algorithms=["HS256"]` al descodificar, lo que cierra el ataque clásico de cambiar el algoritmo a `none`.
- **Token de acceso de 15 minutos**, refresco de 30 días.
- **Los dos tipos de token llevan marca.** Se firman con el mismo secreto, así que sin ella un token de refresco robado valdría como token de acceso: 30 días en vez de un solo canje.
- **Cerrar sesión invalida de verdad.** El token de refresco se registra en base de datos y se marca revocado al salir. Se guarda solo el **hash SHA-256**, nunca el token: quien lea la tabla no puede usar lo que encuentre.
- **Un token sin marca de tipo se rechaza.** Hubo un periodo en que se trataba como token de acceso, para no cortar las sesiones abiertas al desplegar los tipos; mientras duró, cualquier token sin `type` valía como token de acceso.
- **Cada renovación rota el token de refresco.** Se emite uno nuevo y el usado queda anulado, así que un token robado deja de servir en cuanto el dueño renueva, en vez de valer los 30 días enteros. El anterior se acepta 30 segundos más (`GRACE_SECONDS`): dos pestañas renovando a la vez no son un ataque, y sin ese margen la segunda se encontraría la sesión cerrada. Cerrar sesión corta también esa ventana.
- **Cada token lleva un `jti` único.** Sin él, dos tokens del mismo usuario emitidos en el mismo segundo salían **idénticos** —`iat` y `exp` tienen resolución de segundos— y al rotar se reemitía literalmente el token que se acababa de anular, dejando dos filas con el mismo hash: una viva y otra muerta. La rotación no servía de nada.
- Un token con firma válida pero no registrado se rechaza.

### OAuth de GitHub

- **Parámetro `state`** contra CSRF, guardado en Redis, **de un solo uso** y con 10 minutos de vida. Sin él, un tercero podía forzar el callback con un `code` suyo y dejar **su** cuenta de GitHub vinculada a **tu** sesión.
- **Solo se acepta un email de GitHub verificado.** El callback vincula la cuenta de GitHub a la fila de usuario que tenga ese email, y cualquiera puede añadir el correo de otra persona a su cuenta de GitHub; lo que no puede es verificarlo sin entrar en ese buzón. Aceptando uno sin verificar, para entrar en la cuenta ajena bastaba con añadir su email en GitHub y pasar por aquí. Si el principal no está verificado se usa otro que sí lo esté, que prueba lo mismo.
- Está en Redis y no en memoria del proceso para que sobreviva a un reinicio y funcione con varias instancias, donde la ida y la vuelta pueden caer en procesos distintos.

---

## 4. Autorización

Todos los endpoints exigen sesión salvo cinco, y los cinco son públicos a propósito: registro, inicio de sesión, las dos rutas de OAuth, y la lectura de un informe compartido.

- **Cada recurso comprueba su dueño.** No basta con tener sesión: hay que ser el propietario del análisis, del repositorio o del monitor.
- **Se responde 404, no 403**, cuando el recurso es de otra persona. Un 403 confirmaría que existe.

---

## 5. Secretos

- **Los tokens de GitHub de los usuarios se guardan cifrados** con Fernet (`backend/app/utils/crypto.py`). Si se filtrara la base de datos, no se filtran sus cuentas de GitHub.
- **La aplicación no arranca con un secreto de ejemplo o corto.** `JWT_SECRET` y `ENCRYPTION_KEY` se validan al cargar la configuración (`backend/app/core/config.py`): se rechazan los valores que trae `.env.example` y cualquiera de menos de 32 caracteres. Un despliegue con `JWT_SECRET=change-me-in-production` funciona perfectamente y no da ninguna señal —los tokens se firman, las sesiones abren— hasta que alguien que ha visto el repositorio firma el suyo para la cuenta que quiera. Mejor que no arranque a que arranque abierta.
- **Nada de secretos en el repositorio.** `.env` está ignorado y solo se versiona `.env.example` con los valores en blanco.
- **El patrón `.env.*` también está ignorado.** Se añadió tras encontrar un `backend/.env.docker.bak` con credenciales reales que el patrón `.env` a secas no cubría: un `git add -A` lo habría publicado.
- Los mensajes de error se sanean: si contienen rutas internas o nombres de directorios temporales, se sustituyen por un texto genérico.
- No se registran contraseñas ni tokens en los logs.

---

## 6. Límites de uso y abuso

`backend/app/services/rate_limit_service.py`

Cada análisis clona un repositorio y levanta un contenedor. Sin límites, una sola cuenta agota la máquina.

| Límite | Valor |
|---|---|
| Análisis por hora y usuario | 5 |
| Análisis por día y usuario | 20 |
| Simultáneos por usuario | 2 |
| **Simultáneos en toda la máquina** | **6** |
| Análisis automáticos (vigilancia), por hora | 10, con cupo aparte |
| Registros por hora y por IP | 5 |
| Fallos de inicio de sesión por hora y cuenta | 10 |
| Fallos de inicio de sesión por hora e IP | 30 |
| Proyectos vigilados por cuenta | 3 |

Tres decisiones que importan:

- **El tope global existe porque los límites por usuario no bastan.** No impiden que diez cuentas coincidan: treinta contenedores a 512 MB son quince gigas y la máquina se cae. Se comprueba **antes** que el límite personal.
- **Se comprueba antes de encolar**, nunca en el worker. Si se hiciera después, el cliente recibiría un 202 para algo que luego se descarta en silencio.
- **Ventana deslizante, no contador por hora natural.** Con contadores fijos se pueden lanzar 5 a las 10:59 y otros 5 a las 11:00.

### Fuerza bruta en el inicio de sesión

Se cuentan **solo los fallos**, y por dos claves a la vez porque frenan ataques distintos: la del email frena probar mil contraseñas contra una cuenta; la de la IP frena probar una contraseña común contra mil cuentas.

- **Se comprueba antes de tocar la base de datos y antes del bcrypt.** Si se mirara después, cada intento bloqueado seguiría pagando el hash y el límite no protegería la CPU de nada.
- **Cuenta igual si la cuenta no existe**, para que un 429 no revele qué emails están registrados.
- **Entrar bien borra el contador de la cuenta, no el de la IP.** Si borrara el de la IP, cualquiera con una cuenta propia podría entrar en la suya entre tandas y seguir probando sin límite contra las demás.
- **El email no se guarda en claro como clave de Redis**, sino su SHA-256: quien lea el Redis no se lleva el listado de correos que han intentado entrar.

`MAX_GLOBAL_CONCURRENT = 6` está calibrado para una máquina de 4 GB. **En una más pequeña hay que bajarlo.**

---

## 7. Exposición de datos

- **Los enlaces compartidos son tokens de 256 bits** (`secrets.token_urlsafe(32)`), imposibles de adivinar. Caducan a los 7 días (30 como máximo) y se revocan uno a uno.
- **Un token inexistente y uno caducado dan la misma respuesta.** Distinguirlos convertiría el endpoint en un oráculo sobre qué tokens han existido.
- **`noindex` en las páginas de informe compartido.** El token protege de quien no lo tiene, pero no de un buscador que ya lo vio: si alguien pega el enlace donde Google rastree, el informe quedaría indexado **aunque el enlace caduque**.
- **La documentación interactiva de la API se apaga en producción** (`ENABLE_API_DOCS=false`). No es una vulnerabilidad por sí sola, pero publicada regala el mapa completo de la API y le ahorra a un atacante todo el reconocimiento.

---

## 8. Cabeceras y transporte

`backend/app/main.py`

La API envía en cada respuesta:

| Cabecera | Para qué |
|---|---|
| `X-Content-Type-Options: nosniff` | Que el navegador no adivine el tipo de contenido |
| `X-Frame-Options: DENY` | Que nadie incruste la API en un marco |
| `Referrer-Policy: no-referrer` | Que la URL completa no viaje a terceros |
| `Permissions-Policy` | Sin cámara, micrófono ni ubicación |
| `Content-Security-Policy: default-src 'none'` | Que nada de lo que sirve la API se ejecute |

> Se añadieron tras una auditoría en la que apareció algo incómodo: **QalitiRadar penalizaba a otros sitios por no enviar estas cabeceras, y la propia API no enviaba ninguna.**

### El frontend también las envía

`frontend/next.config.ts`

La API mandaba sus cabeceras y el frontend ninguna, que es la mitad que el navegador de verdad renderiza. Envía las mismas cuatro, más una **CSP propia**: `default-src 'self'`, nada de terceros, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'` y `frame-ancestors 'none'`.

Dos concesiones, dichas por su nombre:

- **`script-src` lleva `'unsafe-inline'`.** Next inyecta scripts en línea para hidratar la página; la alternativa —un nonce por petición— obliga a renderizar todo en el servidor en cada visita. El resto de la política sigue valiendo.
- **`'unsafe-eval'` solo en desarrollo**, que es lo que necesita el recargado en caliente. En producción no se emite.

`connect-src` se construye a partir de `NEXT_PUBLIC_API_URL`, porque la API vive en otro origen y sin autorizarlo la propia política bloquearía todas las llamadas.

**Verificado en un navegador real:** las 6 pruebas end-to-end (registro, análisis, compartir, enlace público) pasan con la política activa. Una CSP que rompe la aplicación se revierte al día siguiente y no protege de nada.

**HSTS no se emite desde la aplicación.** La termina el proxy inverso, que es quien sabe si la conexión es realmente HTTPS; emitirla en local, por HTTP, dejaría el dominio inaccesible en el navegador.

**CORS con lista explícita de orígenes**, nunca `*`, porque la API responde con credenciales.

**El cuerpo de una petición se corta en 64 KB.** Lo más grande que recibe esta API es un JSON con una URL y un nombre; sin tope, una sola petición puede reservar toda la memoria del proceso antes de que nadie mire lo que trae. Se rechaza con 413 por lo que declara el `Content-Length`, antes de leer nada. Quien no lo declare (`Transfer-Encoding: chunked`) se cuela de esta comprobación: ese caso lo corta el proxy inverso, que es quien puede hacerlo sin haber leído nada.

---

## 9. Inyección

- **SQL:** todo pasa por el ORM de SQLAlchemy con consultas parametrizadas. No hay SQL construido por concatenación.
- **Comandos:** ningún `shell=True`, `os.system`, `eval` ni `exec`. Los procesos se lanzan con lista de argumentos, que no pasa por un intérprete de shell.
- **XSS:** React escapa por defecto y no se usa `dangerouslySetInnerHTML` en ningún sitio.
- **Nombres de rama validados** contra un patrón antes de llegar a `git`, y se rechaza `..`.

---

## 10. Dependencias

`.github/workflows/dependencias.yml`

El proyecto analiza las dependencias *de otros*; sin esto, nadie vigilaba las suyas.

- **`pip-audit` sobre `backend/requirements.txt` y `npm audit` sobre el frontend**, en cada cambio y una vez por semana. Semanal porque una dependencia no se vuelve vulnerable cuando la tocas, sino cuando alguien publica el aviso.
- `npm audit` corre con `--omit=dev --audit-level=high`: fallar por un aviso bajo en una herramienta de desarrollo entrena a ignorar el rojo, y entonces la auditoría deja de servir para nada.

**La primera ejecución encontró 30 vulnerabilidades conocidas en 4 paquetes**, entre ellos los dos que sostienen la autenticación entera: `pyjwt` (2.9.0, con avisos sobre la validación de firmas) y `cryptography` (43.0.1), más `starlette` vía `fastapi`. Se subieron todos y la auditoría quedó limpia:

| Paquete | Antes | Ahora |
|---|---|---|
| `fastapi` | 0.115.0 | 0.141.1 |
| `starlette` (transitiva) | 0.38.6 | 1.6.0 |
| `uvicorn` | 0.30.6 | 0.40.0 |
| `pyjwt` | 2.9.0 | 2.13.0 |
| `cryptography` | 43.0.1 | 50.0.1 |
| `pytest` | 8.3.3 | 9.1.1 |

Es el argumento entero a favor de automatizar esto: llevaban meses ahí y nadie lo sabía.

---

## 11. Lo que NO está cubierto

Esto es tan importante como lo anterior.

**No hay verificación de email.** Los límites de uso son por cuenta, así que quien tenga varias IP puede registrar varias cuentas y saltárselos. El límite por IP sube el coste del abuso; no lo elimina. Hacerlo bien exige infraestructura de correo.

**El worker tiene acceso al demonio de Docker.** Es inherente al diseño: quien logre ejecutar código como ese usuario es efectivamente root en la máquina. Se mitiga dedicando la máquina solo a esto, y es la razón de que el sandbox esté cerrado a cal y canto.

**Sin auditoría de accesos.** No queda registro de quién consultó qué. Para un MVP es asumible; para datos de terceros, no.

---

## Cómo comprobarlo

```bash
cd backend && pytest                                  # las 405 pruebas
cd backend && pytest tests/test_sandbox.py            # aislamiento real contra Docker
cd backend && pytest tests/test_url_validation.py     # SSRF
cd backend && pytest tests/test_security_hardening.py # sesiones, límites, cabeceras
cd backend && pytest tests/test_security.py           # autenticación y autorización
```

Las pruebas del sandbox **necesitan Docker en marcha**: sin él no fallan, se saltan, así que conviene mirar que se ejecutan de verdad.
