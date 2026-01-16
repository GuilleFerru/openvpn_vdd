#!/bin/bash
# Script para crear un cliente OpenVPN
# Uso: ./create-client.sh <nombre_cliente>
# Ejemplo: ./create-client.sh usuario1

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo -e "${RED}ERROR: Debes especificar el nombre del cliente${NC}"
    echo ""
    echo "Uso: ./create-client.sh <nombre_cliente>"
    echo "Ejemplo: ./create-client.sh juan"
    exit 1
fi

CLIENT_NAME=$1
VOLUME_NAME="openvpn_openvpn_data"

# Crear carpeta clients si no existe
mkdir -p ./clients

echo -e "${GREEN}=== Creando cliente: $CLIENT_NAME ===${NC}"
echo ""
echo -e "${YELLOW}Te pedirá la contraseña de la CA que creaste en el setup${NC}"
echo ""

# Generar certificado del cliente (pedirá la contraseña de la CA)
docker run -v $VOLUME_NAME:/etc/openvpn --rm -it kylemanna/openvpn easyrsa build-client-full $CLIENT_NAME nopass

# Exportar archivo .ovpn
echo ""
echo "Exportando archivo de configuración..."
docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn ovpn_getclient $CLIENT_NAME > ./clients/${CLIENT_NAME}.ovpn

echo ""
echo -e "${GREEN}=== Cliente creado exitosamente ===${NC}"
echo ""
echo "Archivo: ./clients/${CLIENT_NAME}.ovpn"
echo ""
echo "Instrucciones para el usuario:"
echo "  1. Descargar OpenVPN Connect: https://openvpn.net/client/"
echo "  2. Importar el archivo ${CLIENT_NAME}.ovpn"
echo "  3. Conectar"
echo ""
