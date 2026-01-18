#!/bin/bash
# Script de configuración inicial de OpenVPN
# Uso: ./setup.sh <IP_PUBLICA_SERVIDOR>
# Ejemplo: ./setup.sh 200.59.147.112

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$1" ]; then
    echo -e "${RED}ERROR: Debes especificar la IP pública del servidor${NC}"
    echo ""
    echo "Uso: ./setup.sh <IP_PUBLICA>"
    echo "Ejemplo: ./setup.sh 200.59.147.112"
    echo ""
    echo "Tip: Para obtener la IP pública ejecutá: curl -s ifconfig.me"
    exit 1
fi

SERVER_ADDR=$1
VOLUME_NAME="openvpn_openvpn_data"

echo -e "${GREEN}=== Configurando OpenVPN Server ===${NC}"
echo "Dirección del servidor: $SERVER_ADDR"
echo ""

# Verificar que Docker está corriendo
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker no está corriendo${NC}"
    exit 1
fi

# Detener contenedor si existe
docker compose down 2>/dev/null || true

# Crear el volumen si no existe
echo "Creando volumen de datos..."
docker volume create $VOLUME_NAME 2>/dev/null || true

# Generar configuración del servidor con subred /20 (4096 IPs para 340 grupos)
echo "Generando configuración del servidor..."
echo "Subred: 10.8.0.0/20 (340 grupos x 12 clientes)"
docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn ovpn_genconfig -u udp://$SERVER_ADDR -s 10.8.0.0/20 -p "route 10.8.0.0 255.255.240.0"

# Inicializar PKI (esto pedirá contraseña para la CA)
echo ""
echo -e "${YELLOW}=== Inicializando PKI ===${NC}"
echo ""
echo "IMPORTANTE:"
echo "  1. Te pedirá crear una CONTRASEÑA para la CA (Autoridad Certificadora)"
echo "  2. ANOTALA en un lugar seguro - la necesitarás para crear cada cliente"
echo "  3. Te pedirá un 'Common Name' - podés dejarlo por defecto o poner un nombre"
echo ""
read -p "Presioná ENTER para continuar..."
echo ""

docker run -v $VOLUME_NAME:/etc/openvpn --rm -it kylemanna/openvpn ovpn_initpki

echo ""
echo -e "${GREEN}=== Configuración completada ===${NC}"
echo ""
echo "Próximos pasos:"
echo "  1. Iniciar el servidor:    docker compose up -d"
echo "  2. Crear un cliente:       ./create-client.sh <nombre>"
echo "  3. El archivo .ovpn estará en ./clients/<nombre>.ovpn"
echo ""
