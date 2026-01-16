#!/bin/bash
# Script para listar clientes OpenVPN existentes
# Uso: ./list-clients.sh

VOLUME_NAME="openvpn_openvpn_data"

echo "=== Clientes OpenVPN ==="
echo ""

docker run -v $VOLUME_NAME:/etc/openvpn --rm kylemanna/openvpn ovpn_listclients

echo ""
