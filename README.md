# OpenVPN Server - Docker

Servidor OpenVPN usando `kylemanna/openvpn`. Sin límite de conexiones simultáneas.

## Características

- ✅ Panel web de administración
- ✅ Sistema de grupos aislados (cada cliente solo ve su grupo)
- ✅ Grupo Admin puede ver todos los clientes
- ✅ Subred /20 con capacidad para **340 grupos x 12 clientes = 4080 clientes**
- ✅ Ver clientes conectados en tiempo real

## Requisitos

- Docker y Docker Compose instalados
- Puerto UDP 1194 disponible y abierto en firewall
- Puerto TCP 8888 para panel de administración
- IP pública del servidor

## Instalación en VM Linux

### 1. Clonar repositorio

```bash
git clone https://github.com/TU_USUARIO/openvpn.git
cd openvpn
```

### 2. Dar permisos a los scripts

```bash
chmod +x *.sh
```

### 3. Configuración inicial (solo la primera vez)

```bash
./setup.sh <IP_PUBLICA_DEL_SERVIDOR>
```

Ejemplo:
```bash
./setup.sh 200.59.147.112
```

**IMPORTANTE:** 
- Te pedirá crear una contraseña para la CA (Autoridad Certificadora)
- **ANOTALA** - La necesitarás cada vez que crees o revoques un cliente

### 4. Habilitar CCD (Client Config Directory)

```bash
./enable-ccd.sh
```

Esto permite asignar IPs fijas a los gateways.

### 5. Configurar contraseña del panel admin

```bash
echo "ADMIN_PASSWORD=TuContraseñaSegura" > .env
```

### 6. Iniciar el servidor

```bash
docker compose up -d --build
```

### 7. Acceder al panel de administración

```
http://<IP_SERVIDOR>:8888
```

## Sistema de Grupos

| Grupo | Rango IP | Puede ver | Capacidad |
|-------|----------|-----------|----------|
| 🔑 Admin | 10.8.0.4 - 10.8.0.15 | Todo | 12 clientes |
| 🏢 Grupo 1 | 10.8.0.16 - 10.8.0.27 | Solo su grupo | 12 clientes |
| 🏢 Grupo 2 | 10.8.0.28 - 10.8.0.39 | Solo su grupo | 12 clientes |
| ... | ... | ... | ... |
| 🏢 Grupo 340 | 10.8.15.244 - 10.8.15.255 | Solo su grupo | 12 clientes |

**Total:** 340 grupos × 12 clientes = **4080 clientes**

## Comandos CLI (alternativa al panel web)

### Crear clientes

```bash
./create-client.sh nombre_usuario
```

El archivo `.ovpn` se guarda en `./clients/nombre_usuario.ovpn`

## Scripts disponibles

| Script | Descripción |
|--------|-------------|
| `./setup.sh <IP>` | Configuración inicial (solo 1 vez) |
| `./create-client.sh <nombre>` | Crear nuevo cliente VPN |
| `./revoke-client.sh <nombre>` | Revocar acceso a un cliente |
| `./list-clients.sh` | Listar todos los clientes |

## Comandos útiles

```bash
# Ver estado del servidor
docker compose ps

# Ver logs en tiempo real
docker compose logs -f

# Reiniciar servidor
docker compose restart

# Detener servidor
docker compose down
```

## Configuración del cliente

1. Descargar [OpenVPN Connect](https://openvpn.net/client/) (Windows, Mac, iOS, Android)
2. Importar el archivo `.ovpn` generado
3. Conectar

## Puerto

| Puerto | Protocolo | Descripción |
|--------|-----------|-------------|
| 1194   | UDP       | OpenVPN     |

## Firewall

Asegurarse de que el puerto 1194/UDP esté abierto:

```bash
# Ver reglas actuales
sudo iptables -L -n | grep 1194

# Si usás ufw
sudo ufw allow 1194/udp
```

En GCP/Cloud, también abrir el puerto en las reglas de firewall del proyecto.

## Estructura de archivos

```
openvpn/
├── docker-compose.yml    # Configuración del contenedor
├── setup.sh              # Script de instalación inicial
├── create-client.sh      # Crear nuevos clientes
├── revoke-client.sh      # Revocar clientes
├── list-clients.sh       # Listar clientes
├── clients/              # Archivos .ovpn generados
│   └── *.ovpn
└── README.md
```

## Notas importantes

- **Sin límite de conexiones** (a diferencia de OpenVPN Access Server)
- La contraseña de la CA es requerida para crear/revocar clientes
- Los archivos `.ovpn` contienen credenciales - mantenerlos seguros
- El volumen `openvpn_openvpn_data` contiene todos los certificados

## Backup

Para respaldar la configuración y certificados:

```bash
docker run -v openvpn_openvpn_data:/etc/openvpn --rm -v $(pwd):/backup alpine tar czf /backup/openvpn-backup.tar.gz /etc/openvpn
```

## Documentación

- [kylemanna/openvpn GitHub](https://github.com/kylemanna/docker-openvpn)
- [OpenVPN Connect](https://openvpn.net/client/)
