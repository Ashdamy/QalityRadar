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

### Lo que se lee está acotado, y lo que se cuenta también

**Tope de tamaño por archivo (1 MB).** Los analizadores limitaban *cuántos* archivos leen (1000–1500), pero no cuánto pesa cada uno: un repositorio con un solo archivo de 500 MB hacía que se cargara entero en memoria del worker y que después cinco analizadores lo recorrieran con expresiones regulares. El worker **no tiene límite de memoria** —el de 512 MB es del contenedor del sandbox, que no interviene aquí—, así que bastaba un repositorio público para tumbarlo y con él todos los análisis en curso. Un millón de bytes sobra para código fuente; lo que pasa de ahí son paquetes minificados o datos.

**Los mensajes de error van por lista blanca.** Antes se mostraba `str(exc)` salvo que contuviera una ruta temporal, y esa lista negra solo tapaba lo que ya se conocía: el fallo de una librería llega con lo que la librería quiera contar, y los de base de datos y Redis traen dentro el host, el usuario y a veces la contraseña. Ahora, por defecto, no se enseña nada del error; solo pasan los que levanta este proyecto con un texto escrito para quien lo lee, y esos se siguen limpiando de rutas del clon.

**Un analizador colgado no bloquea la máquina.** Las tareas de análisis llevan `time_limit=600` de Celery: una expresión regular que se atasca sobre HTML hostil se corta a los diez minutos y el hueco se devuelve. Es lo que hace que las expresiones regulares sobre contenido ajeno sean un problema de rendimiento y no una forma de tumbar el servicio.

### Los analizadores no siguen enlaces simbólicos

`backend/app/analyzers/base.py`

Aquí está la trampa de leer código ajeno, y es la que más cuesta ver: la regla del proyecto es que **el código analizado nunca se ejecuta**, pero sí se lee, y leer el archivo equivocado basta para filtrarlo.

Los analizadores de Python (estructura, calidad, dependencias, pruebas…) **corren en el worker, no en el contenedor aislado**: lo que alcanzan es la máquina de verdad, la que tiene el `.env` con el `JWT_SECRET`, la clave de cifrado y las credenciales de la base de datos. Y `Path.rglob` sigue los enlaces simbólicos: un repositorio con

```
config.py -> /app/.env
```

hacía que el analizador leyera ese archivo y después informara de lo que había encontrado dentro.

**Comprobado en el sistema de destino**, no razonado: en un contenedor `python:3.11-slim` igual al del despliegue, `rglob` devuelve el enlace y `read_text` entrega el contenido del archivo de fuera.

Se cierra en un solo sitio, por donde pasan los ocho analizadores: se descartan los enlaces **y** se confirma que la ruta resuelta sigue dentro del clon. Dos comprobaciones y no una, porque la segunda no depende de cómo trate los enlaces la versión de Python que toque. Los archivos que se abren por nombre y no recorriendo —`package.json`, `requirements.txt`, `pyproject.toml`, el README, el `.gitignore`— pasan por la misma comprobación: un enlace con cualquiera de esos nombres servía igual.

Las pruebas del ataque (`tests/test_recorrido_del_repositorio.py`) **se saltan en Windows**, que no deja crear enlaces sin privilegios. Se ejecutan en Linux, que es donde corre esto:

```bash
docker run --rm -v "$PWD/backend:/src:ro" -w /tmp python:3.11-slim   sh -c "pip install -q pytest && cp /src/tests/test_recorrido_del_repositorio.py .          && PYTHONPATH=/src python -m pytest test_recorrido_del_repositorio.py -q"
```

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

### El navegador aislado

`navegador/`, `backend/app/utils/navegador.py`, `backend/app/utils/proxy_navegador.py`

Con `NAVEGADOR_REAL=true`, los análisis de URL abren además la página en Chromium para medirla con Lighthouse y axe-core. Es el punto más delicado del producto: un navegador ejecuta el JavaScript de un desconocido, y ese JavaScript puede pedir lo que quiera — `fetch("http://169.254.169.254/")`, una imagen en `http://10.0.0.5/`, un iframe hacia `localhost:5432` — o redirigir a cualquiera de ellos. Validar la URL inicial, como hace el modo estático, no basta. Por eso hay tres capas:

1. **Antes de lanzar nada**, la URL pasa por `validate_public_url` (la misma validación del modo estático) en el worker, justo antes del `docker run`.
2. **El proxy de salida, la defensa principal.** Chromium arranca con `--proxy-server` apuntando a un proxy propio dentro del contenedor, y con `--proxy-bypass-list=<-loopback>` para que **ni siquiera `localhost`** quede fuera. Por él pasa cada conexión de la página: documento, subrecursos, iframes, redirecciones y `fetch`. Para cada una:
   - **resuelve el DNS una sola vez**,
   - comprueba **todas** las IP devueltas (públicas y enrutables: fuera privadas, loopback, enlace local con `169.254.169.254`, la `fd00:ec2::254` de AWS, IPv4 mapeadas en IPv6, reservadas, multicast) y que el puerto no sea de un servicio interno,
   - y **conecta a esa misma IP, sin segunda resolución**. Un dominio que responda una IP pública a la comprobación y una privada a la conexión (*DNS rebinding*) no tiene segunda resolución que aprovechar. Hay una prueba con un resolvedor que cambia de IP pública a privada.

   Lo bloqueado recibe un 403. QUIC y WebRTC, que no pasarían por un proxy HTTP, se desactivan (`--disable-quic`, `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`). El proxy usa solo la biblioteca estándar, y la imagen copia el mismo archivo que prueban los tests.
3. **Reglas de red en el host**, la tercera capa: `navegador/red.sh` crea la red `qalitiradar-navegador` (sin comunicación entre contenedores) y añade en la cadena `DOCKER-USER` de iptables reglas que tiran el tráfico de esa red hacia rangos privados y de metadatos, por si fallaran el proxy o Chromium.

   > **Ojo: en Docker Desktop (Windows y Mac) estas reglas pueden no aplicarse igual.** Ahí los contenedores corren dentro de una máquina virtual y las reglas de iptables del anfitrión no gobiernan su tráfico de la misma manera; el script está pensado para un servidor Linux. **No hay que contar con esta capa: la defensa principal es el proxy.** En el entorno de desarrollo en Windows, la protección efectiva son las capas 1 y 2.
   >
   > Comprobado el 30/10/2026 en Docker Desktop para Windows: desde un contenedor de la red `qalitiradar-navegador`, una conexión directa (sin pasar por el proxy) **sí llega** a `host.docker.internal:8000` (la API) y a `host.docker.internal:5433` (Postgres). Pasando por el proxy, las dos se bloquean con un 403. En desarrollo lo único que separa al navegador de los servicios locales es que Chromium esté obligado a salir por el proxy.

**El contenedor**: usuario sin privilegios (65534), sistema de archivos de solo lectura con un `tmpfs` de 256 MB en `/tmp`, `--cap-drop=ALL`, `no-new-privileges`, 1 GB de memoria sin swap, 1 CPU, 256 procesos y ningún volumen montado. Chromium corre con `--no-sandbox` porque su sandbox interno necesita capacidades que el contenedor no da; el aislamiento lo pone el contenedor. La red `qalitiradar-navegador` no contiene nada nuestro: ni Postgres, ni Redis, ni la API.

**Tiempo**: el `docker run` se corta a los 90 s y, como matar el proceso de Docker no mata el contenedor, se borra por su nombre (`docker rm -f`). La tarea de Celery tiene además un corte duro a los 150 s. Si algo falla, el análisis se queda con la puntuación estática; la medición nunca lo rompe.

**La salida del contenedor es un dato hostil.** Se lee solo la última línea JSON y solo los campos esperados, con su tipo y acotados (NaN, infinitos, negativos y textos largos se descartan o se recortan).

**Cómo se lanza el contenedor, y por qué no se monta `docker.sock`.** Lo lanza el worker de Celery, que corre **en el host** (ver más arriba), con `docker run` por `subprocess`, sin shell y con el comando armado solo con constantes. Lo único que viene del usuario es la URL, ya validada, como argumento después de `--`, así que Docker nunca la lee como una opción. No se monta `/var/run/docker.sock` en ningún contenedor.

- **Riesgo que se asume:** el worker puede hablar con el demonio de Docker, y eso equivale a ser root en la máquina. Si alguien comprometiera el proceso del worker, tendría la máquina.
- **Mitigación:** el worker no ejecuta nada del usuario. El navegador y el código analizado corren en contenedores sin privilegios, y el worker solo los lanza con argumentos fijos.
- **Si algún día el worker pasa a un contenedor, no hay que montarle el socket tal cual.** Hay que ponerle delante un proxy del socket que solo permita crear, arrancar, esperar y borrar contenedores de las imágenes `qaliti/*` (por ejemplo, `docker-socket-proxy`), o usar Docker en modo *rootless*.

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
- **El hash de un token de refresco es único en la base de datos.** Dos filas con el mismo hash, una viva y otra revocada, hacen que la búsqueda devuelva una u otra sin criterio: cerrar sesión revoca una y la otra sigue abriendo. El `jti` ya lo impide; la restricción lo pone donde no depende de que nadie se acuerde.
- **Los tokens muertos se borran a diario.** Uno caducado no vale, y uno revocado no vuelve a valer pasada la ventana de gracia. Importa desde que se rota: cada renovación deja una fila revocada, unas cien al día por sesión activa. `purge_expired` existía y **no la llamaba nadie**; ahora corre en la tarea de mantenimiento junto a la purga de análisis. Borrar una fila revocada no cambia nada para quien la tuviera: un token que no consta se rechaza igual.
- Un token con firma válida pero no registrado se rechaza.

### La sesión vive en cookies httpOnly, no en `localStorage`

`backend/app/api/auth.py`, `frontend/src/lib/auth.ts`

Los tokens estaban en `localStorage`. Ahí bastaba **un solo XSS** —un comentario, una dependencia comprometida, un script inyectado— para llevarse 30 días de sesión de cualquier usuario, sin dejar rastro y sin que cerrar sesión sirviera de nada. Ahora los pone el servidor en cookies que JavaScript no puede leer.

- **`SameSite=Lax` es la defensa contra CSRF.** El navegador no adjunta la cookie en peticiones que salen de otro sitio, así que un formulario ajeno no puede actuar en nombre del usuario. Exige que el frontend y la API compartan dominio; con dominios distintos habría que bajar a `None` y volver a necesitar un testigo CSRF aparte.
- **`Secure` se controla por configuración** (`COOKIE_SECURE`, `true` en producción). En local el desarrollo va por HTTP, y una cookie `Secure` sobre HTTP se descarta en silencio.
- **`/refresh` no devuelve los tokens en el cuerpo cuando la sesión viene en cookie.** Es el detalle del que depende todo lo demás: un XSS no puede leer la cookie, pero el navegador la adjunta por él, así que le bastaría con llamar a `/refresh` y leer la respuesta. A quien manda el token de refresco en el cuerpo —un script, no un navegador— sí se le devuelven: ya los tenía.
- **`/login` y el callback de OAuth sí los devuelven**, y no abre ningún hueco: para llegar ahí hace falta la contraseña o pasar por GitHub, o sea que quien recibe la respuesta ya podía entrar.
- **Queda una cookie legible, `qr_sesion`**, que solo dice "hay sesión". La interfaz la necesita para saber si enseña la pantalla o redirige al inicio. No es una credencial: robarla no sirve de nada.
- **La cabecera `Authorization` se sigue aceptando**, y va primero: quien la manda lo hace a propósito, y una cookie olvidada en el navegador no debe pisar una petición explícita.

**Verificado en un navegador real:** una prueba end-to-end comprueba que, con la sesión abierta, `localStorage` está vacío y `document.cookie` no contiene ni `qr_access` ni `qr_refresh`.

### Rastro de lo que le pasa a una cuenta

`backend/app/services/audit_service.py`

Se anotan el registro, las entradas, las salidas, los intentos fallidos, los bloqueos por fuerza bruta y las vinculaciones con GitHub. Con eso se contesta la pregunta que se hace después de un susto: **si alguien entró donde no debía, cuándo y desde dónde**.

Es más estrecho de lo que pedía la lista de pendientes, que hablaba de registrar *quién consultó qué*. Eso crece con cada petición, guarda mucho más dato personal y no contesta esa pregunta; lo que la contesta es el rastro de la cuenta.

- **El correo de un intento contra una cuenta que no existe no se guarda.** Sería ir construyendo la lista de correos que alguien prueba, que es justo lo que no hace falta tener. El evento queda sin cuenta asociada.
- **Quedarse sin intentos también deja rastro.** Sin eso, una tanda de fuerza bruta se ve como unos cuantos fallos y luego silencio, indistinguible de que el atacante se aburriera.
- **El rastro nunca puede tumbar el inicio de sesión.** Si un fallo al anotar arrastrara la petición, un problema del registro dejaría a la gente sin poder entrar. Uno incompleto es peor que uno completo y mejor que un servicio caído.
- **La dirección se valida antes de guardarla.** La columna es `INET` y rechaza lo que no sea una dirección; detrás de según qué proxy no llega ninguna. Si el valor no parsea se guarda nulo, porque perder la dirección es mucho mejor que perder el evento entero — y es exactamente lo que pasaba antes de comprobarlo.
- **Se purga a los 90 días** con el resto del mantenimiento. Una IP es un dato personal y guardarla para siempre no ayuda a nadie.

### Verificación del correo

`backend/app/services/verification_service.py`, `backend/app/api/auth.py`

Los límites de uso son por cuenta, y crear una cuenta era escribir un correo cualquiera. Saltarse los límites era tan fácil como inventarse correos. Ahora cada cuenta con contraseña cuesta un buzón de verdad.

- **Sin verificar no se entra.** El registro crea la cuenta y manda un enlace. Hasta abrirlo, `/login` responde `403` y no emite sesión.
- **El `403` sale después de comprobar la contraseña, no antes.** Así solo sabe que la cuenta existe y está pendiente quien ya conoce la contraseña. Con una contraseña incorrecta sigue siendo el `401` de siempre.
- **Volver a entrar reenvía el enlace**, con un máximo de 3 por hora y cuenta. No hace falta un endpoint aparte para pedir otro, y como exige la contraseña, nadie puede usarlo para llenarle el buzón a un tercero.
- **El enlace es un JWT con su propia marca de tipo y caduca en 24 horas.** Se firma con el mismo secreto que los de sesión, así que sin la marca un token de acceso valdría como enlace. No tiene tabla: verificar dos veces no hace daño, y no hace falta recordar si ya se usó.
- **El token va en el fragmento (`#token=`), no en la consulta.** El navegador nunca manda el fragmento al servidor, así que no queda en los logs de acceso ni en la cabecera `Referer`.
- **Verificar no abre sesión.** El enlace suele abrirse en otro dispositivo, y quien lo abre solo ha demostrado tener el buzón, no la contraseña.
- **Las cuentas sin verificar se borran a los 7 días**, en el mantenimiento diario. Si alguien registra un correo ajeno, ese correo no queda bloqueado para siempre. El propio correo le dice al dueño que no abra el enlace si no creó la cuenta.
- **Entrar por GitHub sobre una cuenta sin verificar borra su contraseña.** Es el caso de la *pre-apropiación*: alguien registra tu correo con su contraseña y espera. Cuando entras por GitHub, la cuenta se vincula a ti, y sin este borrado su contraseña seguiría abriéndola. Las cuentas de GitHub nacen verificadas, porque GitHub solo nos entrega correos que él ya verificó.
- **El correo sale en segundo plano**, después de responder. El registro no tarda lo que tarde el SMTP, y si el SMTP falla la petición no se cae: el fallo queda en el log y basta con volver a entrar para recibir otro enlace.
- Las cuentas que existían antes de la migración `0020` se dan por verificadas.

### Olvidé mi contraseña

`POST /api/auth/password/forgot` y `POST /api/auth/password/reset`

Sin esto, quien olvidaba la contraseña perdía la cuenta.

- **Responde siempre lo mismo**, exista la cuenta o no, y también cuando se pasa del límite. Si no, serviría para averiguar qué correos están registrados. El correo sale en segundo plano para que el tiempo de respuesta tampoco lo delate.
- **El enlace es de un solo uso sin tener tabla.** El JWT lleva una huella (16 caracteres de SHA-256) del hash de la contraseña que había al pedirlo. En cuanto la contraseña cambia, la huella deja de coincidir y el enlace muere; también mueren los demás enlaces pedidos antes. Caduca en 60 minutos y lleva su propia marca de tipo, como el resto.
- **Límite de 3 peticiones por hora y correo, y 10 por hora e IP.** El de correo evita llenarle el buzón a alguien; el de IP, recorrer una lista de correos mandando enlaces. Al pasarse, la respuesta es la misma de siempre.
- **Restablecer cierra todas las sesiones abiertas.** Quien lo hace suele sospechar algo, y la sesión de un intruso no debe sobrevivir al cambio. El token de acceso que ya tuviera dura como mucho sus 15 minutos.
- **Restablecer verifica el correo** de una cuenta pendiente: abrir el enlace prueba lo mismo, que el buzón es suyo. Y cierra el caso de la pre-apropiación también por este lado: la contraseña que puso quien registró el correo ajeno se sustituye.
- **También sirve a las cuentas que solo entran por GitHub**: quien tiene el buzón es el dueño, y así puede añadirse una contraseña.
- El token va en el fragmento (`#token=`), igual que el de verificación.

### Mi cuenta

`GET /api/auth/me`, `POST /api/auth/password/change`, `POST /api/auth/logout-all`

- **`/me` devuelve lo justo** para la página: correo, si está verificado, si tiene contraseña y si GitHub está conectado. Nunca el token de GitHub, ni siquiera cifrado.
- **Cambiar la contraseña pide la actual.** Una sesión abierta en un ordenador ajeno no debe bastar para quedarse la cuenta. Los fallos cuentan en el **mismo contador que el login**: si no, con una sesión robada este endpoint serviría para probar contraseñas sin límite.
- **Una cuenta sin contraseña (solo GitHub) no la crea desde aquí**, sino con el enlace por correo, que prueba tener el buzón. Por el mismo motivo: si bastara la sesión, quien la robara se añadiría una contraseña y conservaría el acceso aunque el dueño desconectara GitHub.
- **Cambiar la contraseña cierra las demás sesiones**; la del navegador que la cambió sigue con una pareja de tokens nueva.
- **"Cerrar en todas partes"** revoca todos los tokens de refresco de la cuenta, el propio incluido. Los de acceso ya emitidos duran como mucho sus 15 minutos.

### OAuth de GitHub

- **Parámetro `state`** contra CSRF, guardado en Redis, **de un solo uso** y con 10 minutos de vida. Sin él, un tercero podía forzar el callback con un `code` suyo y dejar **su** cuenta de GitHub vinculada a **tu** sesión.
- **Solo se acepta un email de GitHub verificado.** El callback vincula la cuenta de GitHub a la fila de usuario que tenga ese email, y cualquiera puede añadir el correo de otra persona a su cuenta de GitHub; lo que no puede es verificarlo sin entrar en ese buzón. Aceptando uno sin verificar, para entrar en la cuenta ajena bastaba con añadir su email en GitHub y pasar por aquí. Si el principal no está verificado se usa otro que sí lo esté, que prueba lo mismo.
- Está en Redis y no en memoria del proceso para que sobreviva a un reinicio y funcione con varias instancias, donde la ida y la vuelta pueden caer en procesos distintos.

---

## 4. Autorización

De las 41 rutas de la API, todas exigen sesión salvo trece, y las trece son públicas a propósito:

- **Entrar y registrarse:** registro, inicio de sesión, verificación del correo, pedir y usar el enlace de restablecer la contraseña, y las dos rutas de OAuth.
- **Renovar y cerrar sesión** (`/refresh`, `/logout`): no piden sesión válida porque su trabajo es precisamente tratar con una que caducó; validan el token de refresco que reciben.
- **Lo que se comparte con un token largo:** el informe compartido y la insignia del README.
- **Datos sin información de nadie:** los límites de caducidad de los enlaces (`/api/reports/shared-config`) y el chequeo de salud.

La lista se comprobó recorriendo las rutas de la aplicación real y mirando cuáles dependen de `get_current_user`, no leyendo el código a ojo.

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
| Correos de verificación por hora y cuenta | 3 |
| Enlaces de restablecer contraseña por hora y correo | 3 |
| Peticiones de restablecer contraseña por hora e IP | 10 |
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
- **Los enlaces caducados se borran a diario.** Uno caducado ya no abre nada, así que guardarlo solo acumula tokens que un día dieron acceso a un informe. Para quien lo tenga no cambia nada: un token que no consta y uno caducado dan la misma respuesta, que es justo lo que evita que el endpoint sirva de oráculo.
- **La insignia del README es lo único público que no caduca**, y es deliberado: una que se apagara sola dejaría una imagen rota en la portada de un proyecto ajeno. Se revoca a mano. Para que eso sea aceptable, expone lo mínimo: **solo la cifra**, ni el nombre del repositorio ni los hallazgos, así que si el token se filtrara antes de publicarlo, lo que se lleva quien lo tenga es un número. Apunta al repositorio y no a un análisis, o se quedaría congelada en la nota de un día. Un token inexistente y uno revocado devuelven la misma imagen —«sin analizar»— en vez de un 404, que además de servir de oráculo dejaría la portada rota.
- **`noindex` en las páginas de informe compartido.** El token protege de quien no lo tiene, pero no de un buscador que ya lo vio: si alguien pega el enlace donde Google rastree, el informe quedaría indexado **aunque el enlace caduque**.
- **La documentación interactiva de la API se apaga en producción** (`ENABLE_API_DOCS=false`). No es una vulnerabilidad por sí sola, pero publicada regala el mapa completo de la API y le ahorra a un atacante todo el reconocimiento.
- **Los mensajes de error de un análisis no cuentan nada interno.** Por defecto no se enseña el texto de la excepción; solo pasan los errores que levanta el propio proyecto. El análisis combinado se había quedado fuera de esta regla y guardaba `error inesperado: {exc}` tal cual: un fallo de base de datos o de Redis trae el host, el usuario y a veces la contraseña, y ese mensaje lo ve el usuario **y cualquiera con un enlace compartido**. Ahora usa el mismo filtro que el de repositorio.

### Monitorización de consultas

`docker-compose.yml`

Postgres registra las consultas que tardan **más de 500 ms** y las que se quedan **esperando un bloqueo**, que es lo primero que hay que mirar cuando la aplicación se vuelve lenta o algo se atasca. Se registra el texto de la consulta pero **no sus valores** (`log_parameter_max_length=0`, también en errores): entre ellos van correos y hashes que no deben acabar en un log. Se leen con `docker compose logs postgres`.

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

**HSTS no se emite desde la aplicación.** La termina el proxy inverso, que es quien sabe si la conexión es realmente HTTPS; emitirla en local, por HTTP, dejaría el dominio inaccesible en el navegador. La configuración de Caddy de [`DEPLOYMENT.md`](DEPLOYMENT.md) la incluye (`max-age` de un año) y Caddy redirige solo de HTTP a HTTPS; en el frontend la pone Vercel.

**La API no arranca con cookies inseguras sobre HTTPS.** Si alguna dirección de la configuración (`FRONTEND_BASE_URL`, `PUBLIC_BASE_URL`, el callback de GitHub) empieza por `https://` y `COOKIE_SECURE` sigue en `false`, la aplicación se niega a arrancar. Con ese descuido todo funciona y nada avisa: el navegador simplemente manda la sesión también por HTTP, en claro.

**CORS con lista explícita de orígenes**, nunca `*`, porque la API responde con credenciales.

**El cuerpo de una petición se corta en 64 KB.** Lo más grande que recibe esta API es un JSON con una URL y un nombre; sin tope, una sola petición puede reservar toda la memoria del proceso antes de que nadie mire lo que trae. Se rechaza con 413 por lo que declara el `Content-Length`, antes de leer nada. Quien no lo declare (`Transfer-Encoding: chunked`) se cuela de esta comprobación: ese caso lo corta el proxy inverso (`request_body max_size 64KB` en la configuración de Caddy), que es quien puede hacerlo sin haber leído nada.

---

## 9. Inyección

- **SQL:** todo pasa por el ORM de SQLAlchemy con consultas parametrizadas. No hay SQL construido por concatenación.
- **Comandos:** ningún `shell=True`, `os.system`, `eval` ni `exec`. Los procesos se lanzan con lista de argumentos, que no pasa por un intérprete de shell.
- **XSS:** React escapa por defecto. `dangerouslySetInnerHTML` aparece una sola vez, en la portada, para los datos estructurados de Google (`application/ld+json`), y lo que mete son constantes del propio código, nunca datos de un usuario.
- **PDF:** ReportLab interpreta un subconjunto de HTML en los párrafos, así que todo texto ajeno se escapa antes. El título —que en el modo URL es la dirección que escribió el usuario— se había quedado sin escapar: un `<` en la URL **hacía fallar la generación del PDF** y cualquier etiqueta se interpretaba como marcado.
- **Nombres de rama validados** contra un patrón antes de llegar a `git`, y se rechaza `..`.
- **Longitud de las entradas:** todo lo que llega por el cuerpo pasa por un esquema de Pydantic con tope. La URL a analizar y el nombre de la aplicación no lo tenían, y la API aceptaba y encolaba una URL de 60.000 caracteres; ahora la URL tiene un máximo de 2.048, el nombre de 255 (el largo de su columna) y la rama también de 255. Los identificadores de las rutas son `UUID` tipados: uno mal formado es un 422 antes de tocar la base.

---

## 10. Dependencias

`.github/workflows/dependencias.yml`

El proyecto analiza las dependencias *de otros*; sin esto, nadie vigilaba las suyas.

- **`pip-audit` sobre `backend/requirements.txt` y `npm audit` sobre el frontend**, en cada cambio y una vez por semana. Semanal porque una dependencia no se vuelve vulnerable cuando la tocas, sino cuando alguien publica el aviso.
- **Las de Python se instalan por hash.** `requirements.in` lleva las directas, escritas a mano; `requirements.txt` sale de ahí con **todas las transitivas fijadas** y su hash, y es lo que instalan el contenedor y el worker con `--require-hashes`. Cierra dos cosas: que una versión transitiva cambie sin que nadie lo decida —hasta ahora el CI auditaba una resolución y el despliegue podía instalar otra— y que lo que baja de la red no sea lo que se auditó.
- El archivo fijado se compila **en un contenedor de Linux**, porque `pip-compile` resuelve para la plataforma donde corre y el resultado lleva paquetes que solo existen ahí (`uvloop`). Para desarrollar se instala `requirements.in`; el fijado es el artefacto del despliegue.
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

**Y automatizarlo no basta si nadie mira el resultado.** En octubre de 2026 una auditoría local encontró que el CI llevaba semanas sin ver `main` —no se había subido— y que se habían vuelto a acumular avisos:

| Paquete | Antes | Ahora | Avisos |
|---|---|---|---|
| `pyjwt` | 2.13.0 | 2.15.0 | 29, uno sin arreglo en 2.14 |
| `pillow` (vía `reportlab`) | 12.3.0 | 13.0.0 | 59 |
| `mako` (vía `alembic`) | 1.4.1 | 1.4.2 | 2 |
| `dnspython` | 2.8.0 | 2.9.0 | 1 |
| `certifi` | 2026.7.22 | 2026.10.19 | 2 |
| `next` | 16.3.3 | 16.4.3 | crítico: ejecución remota en `next/og` |
| `sharp`, `source-map-js` (transitivas) | — | corregidas | altos |

`next/og` y `use cache` no se usan, así que el crítico no era explotable aquí; el primer uso lo habría abierto. Como ninguna versión nueva de Python trae dependencias nuevas, se cambiaron solo esas cinco líneas de `requirements.txt` con los hashes publicados en PyPI, y se comprobó que instalan con `--require-hashes` en un contenedor de Linux. Tras el cambio, `pip-audit` (61 paquetes) y `npm audit --omit=dev` dan cero.

---

## 11. Lo que NO está cubierto

Esto es tan importante como lo anterior.

**Un buzón cuesta poco.** La verificación del correo (§3) obliga a tener un buzón real por cuenta, pero hay servicios de correo desechable que dan uno en segundos. Sube bastante el coste de saltarse los límites; no lo hace imposible. Bloquear dominios desechables sería el siguiente paso si llega a hacer falta.

**El worker tiene acceso al demonio de Docker.** Es inherente al diseño: quien logre ejecutar código como ese usuario es efectivamente root en la máquina. Se mitiga dedicando la máquina solo a esto, y es la razón de que el sandbox esté cerrado a cal y canto.

**No queda registro de quién consultó qué.** Sí lo hay de lo que le pasa a cada cuenta (§3), que es lo que sirve tras un incidente; el de lecturas se dejó fuera a propósito. Para datos de terceros haría falta.

**No hay CAPTCHA.** Contra los bots hay límites de registro por IP, verificación del correo, límites de inicio de sesión y de enlaces de recuperación, y topes de análisis por cuenta y globales. Un CAPTCHA (Cloudflare Turnstile, por ejemplo) exige una cuenta del proveedor y sus claves; se añadirá si el abuso llega a ser real.

**No se usa Row-Level Security de Postgres.** La base no está expuesta a ningún cliente: solo la API habla con ella, con un único usuario, y la autorización se aplica en cada consulta (§4). RLS tendría sentido si el navegador consultara la base directamente, como en Supabase; aquí obligaría a fijar el usuario en cada transacción, incluidas las tareas del worker que trabajan con datos de varias cuentas, sin cerrar ningún hueco que hoy esté abierto.

**El tope de 64 KB y HSTS dependen del proxy inverso.** Están en la configuración de Caddy de la guía de despliegue; un despliegue que la ignore se queda sin ellos.

---

## Cómo comprobarlo

```bash
cd backend && pytest                                  # las 613 pruebas
cd frontend && npx playwright test                    # los flujos, en un navegador real
cd backend && pytest tests/test_sandbox.py            # aislamiento real contra Docker
cd backend && pytest tests/test_url_validation.py     # SSRF
cd backend && pytest tests/test_security_hardening.py # sesiones, límites, cabeceras
cd backend && pytest tests/test_security.py           # autenticación y autorización
```

Las pruebas del sandbox **necesitan Docker en marcha**: sin él no fallan, se saltan, así que conviene mirar que se ejecutan de verdad.
