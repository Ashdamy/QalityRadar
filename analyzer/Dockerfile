FROM python:3.11-slim

# Gitleaks: deteccion de secretos. Version fijada para que el analisis sea
# reproducible entre ejecuciones.
ARG GITLEAKS_VERSION=8.21.2
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && curl -sSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    | tar -xz -C /usr/local/bin gitleaks \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir semgrep==1.95.0

# Semgrep escribe configuracion y cache en $HOME al arrancar. El contenedor
# corre como `nobody`, cuyo home (/nonexistent) no existe ni es escribible, y
# el sistema de archivos va en solo lectura: sin esto Semgrep aborta con
# PermissionError antes de analizar nada.
#
# Se apunta a /tmp, que el sandbox monta como tmpfs escribible, y se
# desactivan las funciones que necesitan red (metricas y version check),
# porque el contenedor se ejecuta con --network=none.
ENV HOME=/tmp \
    XDG_CONFIG_HOME=/tmp/.config \
    XDG_CACHE_HOME=/tmp/.cache \
    SEMGREP_SETTINGS_FILE=/tmp/.semgrep/settings.yml \
    SEMGREP_VERSION_CACHE_PATH=/tmp/.semgrep/version \
    SEMGREP_SEND_METRICS=off \
    SEMGREP_ENABLE_VERSION_CHECK=0

# Semgrep espera que sus directorios de configuracion y cache existan y aborta
# si no. El sandbox monta /tmp como un tmpfs vacio en cada ejecucion, asi que
# los crea este punto de entrada al arrancar, no la construccion de la imagen.
COPY entrypoint.sh /usr/local/bin/analyzer-entrypoint
RUN chmod 0755 /usr/local/bin/analyzer-entrypoint

# Se ejecuta como nobody; el sandbox tambien lo fuerza con --user.
USER 65534:65534
WORKDIR /repo
ENTRYPOINT ["/usr/local/bin/analyzer-entrypoint"]
