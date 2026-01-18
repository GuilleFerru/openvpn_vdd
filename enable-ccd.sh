#!/bin/bash
# Script para habilitar Client Config Directory (CCD) con modo exclusivo
# Esto permite asignar IPs fijas a clientes específicos
# SOLO clientes con archivo CCD pueden conectarse (ccd-exclusive)

set -e

VOLUME_NAME="openvpn_openvpn_data"

echo "=== Configurando OpenVPN con CCD exclusivo ==="
echo ""
echo "Esto asegura:"
echo "  1. Solo clientes con archivo CCD pueden conectarse"
echo "  2. El pool dinámico excluye el rango de admin (10.8.0.4-15)"
echo ""

# Verificar si client-config-dir ya está habilitado
if docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn cat /etc/openvpn/openvpn.conf | grep -q "client-config-dir"; then
    echo "✓ client-config-dir ya está habilitado"
else
    docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn sh -c 'echo "client-config-dir /etc/openvpn/ccd" >> /etc/openvpn/openvpn.conf'
    echo "✅ client-config-dir habilitado"
fi

# Verificar si ccd-exclusive ya está habilitado
# CRITICO: Esto impide que clientes sin CCD obtengan IP dinámica
if docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn cat /etc/openvpn/openvpn.conf | grep -q "ccd-exclusive"; then
    echo "✓ ccd-exclusive ya está habilitado"
else
    docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn sh -c 'echo "ccd-exclusive" >> /etc/openvpn/openvpn.conf'
    echo "✅ ccd-exclusive habilitado - clientes sin CCD NO pueden conectarse"
fi

# Modificar ifconfig-pool para excluir rango admin (10.8.0.4-15)
# Solo como segunda barrera de seguridad
if docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn cat /etc/openvpn/openvpn.conf | grep -q "ifconfig-pool 10.8.0.16"; then
    echo "✓ ifconfig-pool ya excluye rango admin"
else
    # Eliminar cualquier ifconfig-pool existente y agregar el correcto
    docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn sh -c 'sed -i "/^ifconfig-pool/d" /etc/openvpn/openvpn.conf'
    docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn sh -c 'echo "ifconfig-pool 10.8.0.16 10.8.15.254" >> /etc/openvpn/openvpn.conf'
    echo "✅ ifconfig-pool configurado: 10.8.0.16 - 10.8.15.254 (excluye rango admin)"
fi

# Crear directorio ccd local si no existe
mkdir -p ./ccd

echo ""
echo "Reiniciando OpenVPN..."
docker compose restart openvpn

echo ""
echo "=== Configuración completada ==="
echo ""
echo "✅ CCD exclusivo habilitado"
echo "✅ Clientes sin archivo CCD NO pueden conectarse"
echo "✅ Pool dinámico excluye rango admin (10.8.0.4-15)"
echo ""
echo "NOTA: Subred 10.8.0.0/20 - 340 grupos x 12 clientes"
echo ""
echo "IMPORTANTE: Si hay clientes conectados sin CCD válido,"
echo "            serán desconectados al reiniciar OpenVPN."
