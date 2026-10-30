#!/bin/sh
# Crea la red del navegador aislado y, en Linux, corta en el host su salida
# hacia rangos privados y de metadatos. Ejecutar como root en el servidor:
#   sudo sh navegador/red.sh
#
# Es la TERCERA capa. La principal es el proxy de dentro del contenedor
# (backend/app/utils/proxy_navegador.py). En Docker Desktop (Windows y Mac)
# los contenedores viven en una maquina virtual: estas reglas no se aplican
# igual y no hay que contar con ellas. Ver docs/SECURITY.md.
set -eu

RED=qalitiradar-navegador

# Sin comunicacion entre contenedores de la misma red.
docker network inspect "$RED" >/dev/null 2>&1 || \
    docker network create --driver bridge \
        --opt com.docker.network.bridge.enable_icc=false "$RED"

SUBRED=$(docker network inspect -f '{{(index .IPAM.Config 0).Subnet}}' "$RED")

# DOCKER-USER se evalua antes que las reglas de Docker y no se borra al
# reiniciar el demonio.
for destino in 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 \
               172.16.0.0/12 192.0.0.0/24 192.168.0.0/16 198.18.0.0/15 224.0.0.0/4 240.0.0.0/4; do
    iptables -C DOCKER-USER -s "$SUBRED" -d "$destino" -j DROP 2>/dev/null || \
        iptables -I DOCKER-USER -s "$SUBRED" -d "$destino" -j DROP
done

echo "red $RED ($SUBRED) lista"
