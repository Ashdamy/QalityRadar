# Navegador aislado para medir paginas publicas (Lighthouse + axe-core).
#
# Se construye desde la raiz del repositorio, porque copia el proxy del
# backend (la misma version que prueban los tests):
#   docker build -f navegador/Dockerfile -t qaliti/navegador:latest .
#
# Lo lanza el worker con los limites de backend/app/utils/navegador.py:
# usuario sin privilegios, sistema de archivos de solo lectura, sin
# capacidades, 1 GB, 1 CPU, y en la red `qalitiradar-navegador`.
FROM node:20.18.1-bookworm-slim

RUN apt-get update \
    # python3 y no python3-minimal: el proxy usa asyncio, que la minima no trae.
    && apt-get install -y --no-install-recommends chromium python3 fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/qr
# Lighthouse trae axe-core: sus auditorias de accesibilidad son reglas de axe.
RUN npm install --omit=dev --no-audit --no-fund lighthouse@12.2.1 chrome-launcher@1.1.2 \
    && npm cache clean --force

COPY backend/app/utils/proxy_navegador.py /opt/qr/proxy_navegador.py
COPY navegador/medir.mjs navegador/entrypoint.sh /opt/qr/
RUN chmod 0555 /opt/qr/entrypoint.sh

# Chromium y Lighthouse escriben su perfil y temporales en HOME: el unico
# sitio escribible es el tmpfs de /tmp.
ENV HOME=/tmp CHROME_PATH=/usr/bin/chromium
USER 65534:65534
ENTRYPOINT ["/opt/qr/entrypoint.sh"]
