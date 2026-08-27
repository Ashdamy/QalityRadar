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

# Se ejecuta como nobody; el sandbox tambien lo fuerza con --user.
USER 65534:65534
WORKDIR /repo
