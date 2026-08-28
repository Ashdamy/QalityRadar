#!/bin/sh
# El sandbox monta el sistema de archivos en solo lectura y /tmp como un
# tmpfs vacio. Semgrep espera encontrar sus directorios de configuracion y
# cache ya creados y aborta si no existen, asi que se preparan aqui, en cada
# arranque, dentro de la unica ruta escribible.
set -e
mkdir -p /tmp/.config /tmp/.cache /tmp/.semgrep
exec "$@"
