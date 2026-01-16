#!/bin/bash
# Script para revocar un cliente OpenVPN
# Uso: ./revoke-client.sh <nombre_cliente>
# Ejemplo: ./revoke-client.sh usuario1

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo -e "${RED}ERROR: Debes especificar el nombre del cliente a revocar${NC}"
    echo ""
    echo "Uso: ./revoke-client.sh <nombre_cliente>"
    echo ""
    echo "Para ver los clientes existentes: ./list-clients.sh"
    exit 1
fi

CLIENT_NAME=$1
VOLUME_NAME="openvpn_openvpn_data"

echo -e "${YELLOW}=== Revocando cliente: $CLIENT_NAME ===${NC}"
echo ""
echo "ADVERTENCIA: Esta acción es IRREVERSIBLE"
echo "El usuario ya no podrá conectarse a la VPN"
echo ""
read -p "¿Estás seguro? (s/N): " confirm

if [ "$confirm" != "s" ] && [ "$confirm" != "S" ]; then
    echo "Operación cancelada"
    exit 0
fi

echo ""
echo -e "${YELLOW}Te pedirá la contraseña de la CA${NC}"
echo ""

# Revocar certificado
docker run -v $VOLUME_NAME:/etc/openvpn --rm -it kylemanna/openvpn ovpn_revokeclient $CLIENT_NAME

# Eliminar archivo .ovpn si existe
if [ -f "./clients/${CLIENT_NAME}.ovpn" ]; then
    rm "./clients/${CLIENT_NAME}.ovpn"
    echo "Archivo ./clients/${CLIENT_NAME}.ovpn eliminado"
fi

echo ""
echo -e "${GREEN}=== Cliente $CLIENT_NAME revocado ===${NC}"
echo ""
