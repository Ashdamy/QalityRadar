#!/bin/sh
# Arranca el proxy de salida y, cuando escucha, mide la URL ($1).
set -eu

python3 /opt/qr/proxy_navegador.py 2>/tmp/proxy.log &

intentos=0
until python3 -c "import socket; socket.create_connection(('127.0.0.1', 3128), 1)" 2>/dev/null; do
    intentos=$((intentos + 1))
    if [ "$intentos" -gt 50 ]; then
        echo "el proxy no arranco" >&2
        exit 3
    fi
    sleep 0.1
done

exec node /opt/qr/medir.mjs "$1"
