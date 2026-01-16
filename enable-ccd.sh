#!/bin/bash
# Script para habilitar Client Config Directory (CCD)
# Esto permite asignar IPs fijas a clientes específicos

set -e

VOLUME_NAME="openvpn_openvpn_data"

echo "Habilitando Client Config Directory..."

# Verificar si ya está habilitado
if docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn cat /etc/openvpn/openvpn.conf | grep -q "client-config-dir"; then
    echo "CCD ya está habilitado"
else
    # Agregar directiva client-config-dir
    docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn sh -c 'echo "client-config-dir /etc/openvpn/ccd" >> /etc/openvpn/openvpn.conf'
    echo "✅ CCD habilitado en openvpn.conf"
fi

# Crear directorio ccd si no existe
docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn mkdir -p /etc/openvpn/ccd

echo ""
echo "Reiniciando OpenVPN..."
docker compose restart openvpn

echo ""
echo "✅ Listo! Los gateways ahora recibirán IPs fijas en el rango 10.8.0.100-254"
