# OpenVPN Access Server - Docker

Servidor OpenVPN con interfaz web integrada.

## Requisitos

- Docker y Docker Compose instalados
- Puertos disponibles: 943, 443, 1194/udp

## Instalación

```bash
git clone https://github.com/TU_USUARIO/openvpn.git
cd openvpn
docker compose up -d
```

Esperar ~1 minuto a que inicie completamente.

## Acceso

### Panel de Administración
```
https://<IP_SERVIDOR>:943/admin
```
- Usuario: `openvpn`
- Contraseña: ver en logs (primera ejecución)

Para ver la contraseña inicial:
```bash
docker logs openvpn-as 2>&1 | grep -i password
```

### Portal de Usuario (descargar cliente)
```
https://<IP_SERVIDOR>:943
```

## Comandos útiles

```bash
# Ver estado
docker compose ps

# Ver logs
docker compose logs -f

# Ver contraseña admin
docker logs openvpn-as 2>&1 | grep -i password

# Cambiar contraseña admin
docker exec -it openvpn-as passwd openvpn

# Detener servidor
docker compose down

# Reiniciar
docker compose restart
```

## Puertos

| Puerto | Protocolo | Descripción |
|--------|-----------|-------------|
| 943    | TCP       | UI Web Admin/Cliente |
| 443    | TCP       | HTTPS VPN + Portal |
| 1194   | UDP       | OpenVPN UDP |

## Licencia

- **Gratis hasta 2 conexiones simultáneas**
- Más conexiones requieren licencia paga

## Crear usuarios

1. Acceder al panel admin: `https://<IP>:943/admin`
2. Ir a **User Management > User Permissions**
3. Agregar usuario y contraseña
4. El usuario accede a `https://<IP>:943` para descargar su cliente

## Documentación

- [OpenVPN Access Server Docker](https://openvpn.net/as-docs/docker.html)
- [OpenVPN Access Server Docs](https://openvpn.net/access-server/docs/)
