#!/bin/bash
# Script para reparar configuración de OpenVPN
# Quita ifconfig-pool conflictivo y reinicia el servicio

set -e

VOLUME_NAME="openvpn_openvpn_data"

echo "=== Reparando OpenVPN ==="
echo ""

# 1. Detener contenedores
echo "Deteniendo contenedores..."
docker compose down 2>/dev/null || true

# 2. Quitar ifconfig-pool problemático
echo "Quitando ifconfig-pool conflictivo..."
docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn sh -c 'sed -i "/^ifconfig-pool/d" /etc/openvpn/openvpn.conf'

# 3. Mostrar config actual
echo ""
echo "Configuración actual:"
echo "---"
docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn cat /etc/openvpn/openvpn.conf
echo "---"
echo ""

# 4. Actualizar código
echo "Actualizando código..."
git pull

# 5. Iniciar servicios
echo ""
echo "Iniciando OpenVPN..."
docker compose up -d

# 6. Esperar un poco y mostrar logs
sleep 3
echo ""
echo "Logs de OpenVPN:"
docker logs openvpn --tail 15

echo ""
echo "=== Reparación completada ==="
