from flask import Flask, render_template_string, request, send_file, jsonify, redirect, url_for, session
from functools import wraps
import subprocess
import os
import re
import secrets
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

VOLUME_NAME = "openvpn_openvpn_data"
CLIENTS_DIR = "/app/clients"
CCD_DIR = "/app/ccd"
CLIENTS_DB = "/app/clients/clients.json"
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Subred /20: 10.8.0.0 - 10.8.15.255 (4096 IPs)
VPN_SUBNET_BASE = "10.8"

# Configuracion de rangos
ADMIN_RANGE = {'start': 4, 'end': 15}  # 12 IPs para admins (10.8.0.4 - 10.8.0.15)
GROUP_SIZE = 12  # Cada grupo tiene 12 IPs
FIRST_GROUP_START = 16  # Primer grupo empieza en IP 16 (10.8.0.16)
MAX_IP = 4095  # Ultimo IP disponible (10.8.15.255)

def ip_to_octets(ip_num):
    """Convierte número de IP (0-4095) a los dos últimos octetos"""
    return ip_num // 256, ip_num % 256

def octets_to_ip(third, fourth):
    """Convierte octetos a IP completa"""
    return f"{VPN_SUBNET_BASE}.{third}.{fourth}"

def ip_num_to_full(ip_num):
    """Convierte número a IP completa"""
    third, fourth = ip_to_octets(ip_num)
    return octets_to_ip(third, fourth)

def load_clients_db():
    if os.path.exists(CLIENTS_DB):
        with open(CLIENTS_DB, 'r') as f:
            data = json.load(f)
            if 'groups' not in data:
                data = {
                    'groups': {
                        'admin': {
                            'name': 'Administradores',
                            'icon': '👑',
                            'range_start': ADMIN_RANGE['start'],
                            'range_end': ADMIN_RANGE['end'],
                            'next_ip': ADMIN_RANGE['start'],
                            'can_see_all': True,
                            'is_system': True
                        }
                    },
                    'clients': data.get('clients', {}),
                    'next_group_start': FIRST_GROUP_START
                }
                save_clients_db(data)
            return data
    return {
        'groups': {
            'admin': {
                'name': 'Administradores',
                'icon': '👑',
                'range_start': ADMIN_RANGE['start'],
                'range_end': ADMIN_RANGE['end'],
                'next_ip': ADMIN_RANGE['start'],
                'can_see_all': True,
                'is_system': True
            }
        },
        'clients': {},
        'next_group_start': FIRST_GROUP_START
    }

def save_clients_db(db):
    os.makedirs(os.path.dirname(CLIENTS_DB), exist_ok=True)
    with open(CLIENTS_DB, 'w') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def get_next_ip_for_group(group_id):
    db = load_clients_db()
    group = db['groups'].get(group_id)
    if not group:
        return None
    ip = group.get('next_ip', group['range_start'])
    if ip > group['range_end']:
        return None
    # No incrementamos aquí, lo haremos después de confirmar que el cliente se creó
    return ip

def confirm_ip_used(group_id, ip_octet):
    """Confirma que la IP fue usada y actualiza el contador"""
    db = load_clients_db()
    group = db['groups'].get(group_id)
    if group and ip_octet >= group.get('next_ip', group['range_start']):
        db['groups'][group_id]['next_ip'] = ip_octet + 1
        save_clients_db(db)

def recalculate_group_counters():
    """Recalcula los contadores de cada grupo basándose en los clientes reales que existen como archivos .ovpn"""
    db = load_clients_db()
    
    # Primero, obtener lista de clientes que realmente existen (archivos .ovpn)
    existing_clients = set()
    if os.path.exists(CLIENTS_DIR):
        for f in os.listdir(CLIENTS_DIR):
            if f.endswith('.ovpn'):
                existing_clients.add(f.replace('.ovpn', ''))
    
    # Limpiar clientes de la DB que ya no existen
    clients_to_remove = []
    for client_name in db.get('clients', {}).keys():
        if client_name not in existing_clients:
            clients_to_remove.append(client_name)
    
    for client_name in clients_to_remove:
        del db['clients'][client_name]
    
    # Contar clientes reales por grupo
    group_clients = {}  # grupo -> lista de IPs usadas
    for client_name, client_info in db.get('clients', {}).items():
        if client_name in existing_clients:
            gid = client_info.get('group')
            if gid and gid in db['groups']:
                ip_str = client_info.get('ip', '')
                if ip_str:
                    try:
                        ip_octet = int(ip_str.split('.')[-1])
                        if gid not in group_clients:
                            group_clients[gid] = []
                        group_clients[gid].append(ip_octet)
                    except:
                        pass
    
    # Actualizar next_ip de cada grupo basándose en la IP más alta usada
    for gid, group in db['groups'].items():
        if gid in group_clients and group_clients[gid]:
            max_ip = max(group_clients[gid])
            db['groups'][gid]['next_ip'] = max_ip + 1
        else:
            # Sin clientes, resetear al inicio del rango
            db['groups'][gid]['next_ip'] = group['range_start']
    
    save_clients_db(db)
    return {
        'cleaned': clients_to_remove,
        'groups': {gid: len(ips) for gid, ips in group_clients.items()}
    }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>OpenVPN Admin - Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #eee; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .login-box { background: rgba(22, 33, 62, 0.95); padding: 40px; border-radius: 20px; width: 320px; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.5); }
        h1 { color: #00d4ff; margin-bottom: 30px; font-size: 24px; }
        input { padding: 14px; margin: 10px 0; border-radius: 8px; border: 2px solid transparent; width: 100%; background: #0f3460; color: #fff; font-size: 16px; transition: border 0.3s; }
        input:focus { outline: none; border-color: #00d4ff; }
        button { padding: 14px; margin-top: 20px; border-radius: 8px; border: none; width: 100%; background: linear-gradient(135deg, #00d4ff, #00a8cc); color: #1a1a2e; cursor: pointer; font-weight: bold; font-size: 16px; transition: transform 0.2s; }
        button:hover { transform: translateY(-2px); }
        .error { color: #e94560; margin-top: 15px; }
        .icon { font-size: 70px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="icon">🔐</div>
        <h1>OpenVPN Admin</h1>
        <form method="POST">
            <input type="password" name="password" placeholder="Contraseña" required autofocus>
            <button type="submit">Ingresar</button>
        </form>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
    </div>
</body>
</html>
'''

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>OpenVPN Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; color: #eee; }
        h1 { color: #00d4ff; margin: 0; }
        h2 { color: #4ecca3; margin: 0 0 15px 0; font-size: 18px; }
        h3 { color: #ffd700; margin: 20px 0 10px 0; font-size: 16px; }
        
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; padding-bottom: 20px; border-bottom: 1px solid #0f3460; }
        .btn-logout { background: #444; color: #fff; padding: 10px 18px; border-radius: 8px; text-decoration: none; font-size: 14px; transition: background 0.3s; }
        .btn-logout:hover { background: #555; }
        
        .card { background: rgba(22, 33, 62, 0.8); padding: 20px; border-radius: 15px; margin: 20px 0; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
        
        input, button, select { padding: 12px; margin: 5px 0; border-radius: 8px; border: none; width: 100%; font-size: 14px; }
        input, select { background: #0f3460; color: #fff; border: 2px solid transparent; transition: border 0.3s; }
        input:focus, select:focus { outline: none; border-color: #00d4ff; }
        select { cursor: pointer; }
        
        button { background: linear-gradient(135deg, #00d4ff, #00a8cc); color: #1a1a2e; cursor: pointer; font-weight: bold; transition: transform 0.2s, opacity 0.2s; }
        button:hover:not(:disabled) { transform: translateY(-1px); }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .btn-danger { background: linear-gradient(135deg, #e94560, #c73e54); color: #fff; }
        .btn-secondary { background: #444; color: #fff; }
        .btn-small { width: auto; padding: 8px 16px; font-size: 13px; display: inline-block; margin: 3px; }
        .btn-edit { background: transparent; border: none; cursor: pointer; font-size: 14px; padding: 2px 6px; margin-left: 8px; opacity: 0.6; transition: opacity 0.2s; }
        .btn-edit:hover { opacity: 1; transform: none; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #0f3460; }
        th { color: #888; font-weight: normal; font-size: 13px; }
        
        .status { display: none; padding: 12px; border-radius: 8px; margin-top: 12px; }
        .loading { background: rgba(255,215,0,0.1); color: #ffd700; }
        .success { background: rgba(78,204,163,0.1); color: #4ecca3; }
        .error { background: rgba(233,69,96,0.1); color: #e94560; }
        
        .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; }
        .badge-online { background: #4ecca3; color: #1a1a2e; }
        .badge-offline { background: #333; color: #666; }
        .badge-admin { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #1a1a2e; }
        .badge-group { background: #0f3460; color: #4ecca3; }
        
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        
        .group-card { background: linear-gradient(135deg, #0f3460, #0a2847); padding: 18px; border-radius: 12px; margin: 12px 0; border-left: 4px solid #4ecca3; transition: transform 0.2s; }
        .group-card:hover { transform: translateX(5px); }
        .group-card.admin { border-left-color: #ffd700; }
        .group-header { display: flex; justify-content: space-between; align-items: center; }
        .group-icon { font-size: 28px; margin-right: 12px; }
        .group-name { font-weight: bold; font-size: 16px; }
        .group-stats { color: #888; font-size: 12px; margin-top: 5px; }
        .group-range { font-family: monospace; color: #666; font-size: 11px; }
        
        .client-row { background: #0f3460; margin: 6px 0; padding: 10px 15px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; transition: background 0.2s; }
        .client-row:hover { background: #153560; }
        .client-name { font-weight: 500; }
        .client-ip { font-family: monospace; color: #888; font-size: 12px; margin-left: 10px; }
        
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); justify-content: center; align-items: center; z-index: 1000; }
        .modal-content { background: #16213e; padding: 30px; border-radius: 20px; width: 420px; max-width: 95%; max-height: 90vh; overflow-y: auto; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #0f3460; }
        .modal-header h2 { margin: 0; }
        .modal-close { background: none; border: none; color: #888; font-size: 28px; cursor: pointer; width: auto; padding: 0; }
        .modal-close:hover { color: #fff; }
        
        .icon-picker { display: flex; gap: 8px; flex-wrap: wrap; margin: 15px 0; }
        .icon-option { padding: 12px; cursor: pointer; border-radius: 10px; font-size: 24px; transition: all 0.2s; background: #0f3460; }
        .icon-option:hover { background: #1a4a7a; transform: scale(1.1); }
        .icon-option.selected { background: #00d4ff; transform: scale(1.1); }
        
        .empty-state { text-align: center; padding: 40px; color: #666; }
        .empty-state .icon { font-size: 50px; margin-bottom: 15px; }
        
        .info-text { color: #888; font-size: 13px; margin: 10px 0; }
        .range-preview { font-family: monospace; background: #0f3460; padding: 10px 15px; border-radius: 8px; margin: 10px 0; color: #4ecca3; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 OpenVPN Admin</h1>
        <a href="/logout" class="btn-logout">🚪 Cerrar sesión</a>
    </div>

    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <h2>📡 Clientes Conectados</h2>
            <button class="btn-small btn-secondary" id="btnRefreshConnected" onclick="loadConnected()">🔄</button>
        </div>
        <table>
            <thead><tr><th>Cliente</th><th>Grupo</th><th>IP VPN</th><th>IP Real</th><th>Conectado</th><th>Tráfico</th></tr></thead>
            <tbody id="connectedList"><tr><td colspan="6" style="color:#666">Cargando...</td></tr></tbody>
        </table>
    </div>

    <div class="grid">
        <div>
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h2>📁 Grupos</h2>
                    <button class="btn-small" onclick="showCreateGroupModal()">+ Nuevo Grupo</button>
                </div>
                <div id="groupsList"></div>
            </div>
        </div>
        <div>
            <div class="card">
                <h2>➕ Crear Cliente</h2>
                <p class="info-text">Los clientes del mismo grupo pueden verse entre sí. Admins ven todo.</p>
                <form id="createForm">
                    <input type="text" id="clientName" placeholder="Nombre (ej: gw-oficina, tecnico-juan)" required>
                    <select id="clientGroup" required>
                        <option value="">-- Seleccionar grupo --</option>
                    </select>
                    <input type="password" id="caPassword" placeholder="Contraseña de la CA" required>
                    <button type="submit">Crear Cliente</button>
                </form>
                <div id="createStatus" class="status"></div>
            </div>

            <div class="card">
                <h2>⚠️ Revocar Cliente</h2>
                <form id="revokeForm">
                    <input type="text" id="revokeClientName" placeholder="Nombre del cliente" required>
                    <input type="password" id="revokePassword" placeholder="Contraseña de la CA" required>
                    <button type="submit" class="btn-danger">Revocar</button>
                </form>
                <div id="revokeStatus" class="status"></div>
            </div>
        </div>
    </div>

    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <h2>📋 Clientes por Grupo</h2>
            <button class="btn-small btn-secondary" id="btnRefreshClients" onclick="loadClients()">🔄</button>
        </div>
        <div id="clientsByGroup"></div>
    </div>

    <!-- Modal Crear Grupo -->
    <div id="modalCreateGroup" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>➕ Nuevo Grupo</h2>
                <button class="modal-close" onclick="hideModal('modalCreateGroup')">&times;</button>
            </div>
            <form id="createGroupForm">
                <label class="info-text">Nombre del grupo:</label>
                <input type="text" id="groupName" placeholder="Ej: Empresa ABC, Fábrica Norte" required>
                
                <label class="info-text">Icono:</label>
                <div class="icon-picker" id="iconPicker">
                    <span class="icon-option selected" data-icon="🏢">🏢</span>
                    <span class="icon-option" data-icon="🏭">🏭</span>
                    <span class="icon-option" data-icon="🏬">🏬</span>
                    <span class="icon-option" data-icon="🏪">🏪</span>
                    <span class="icon-option" data-icon="🏥">🏥</span>
                    <span class="icon-option" data-icon="🏫">🏫</span>
                    <span class="icon-option" data-icon="🏨">🏨</span>
                    <span class="icon-option" data-icon="🏦">🏦</span>
                    <span class="icon-option" data-icon="⚡">⚡</span>
                    <span class="icon-option" data-icon="🌐">🌐</span>
                    <span class="icon-option" data-icon="🔧">🔧</span>
                    <span class="icon-option" data-icon="📡">📡</span>
                </div>
                
                <label class="info-text">Rango de IPs asignado:</label>
                <div class="range-preview" id="groupRangePreview">Cargando...</div>
                <p class="info-text">Cada grupo puede tener hasta 20 clientes.</p>
                
                <button type="submit">Crear Grupo</button>
            </form>
        </div>
    </div>

    <!-- Modal Editar Grupo -->
    <div id="modalEditGroup" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>✏️ Editar Grupo</h2>
                <button class="modal-close" onclick="hideModal('modalEditGroup')">&times;</button>
            </div>
            <form id="editGroupForm">
                <input type="hidden" id="editGroupId">
                <label class="info-text">Nombre del grupo:</label>
                <input type="text" id="editGroupName" placeholder="Nombre del grupo" required>
                
                <label class="info-text">Icono:</label>
                <div class="icon-picker" id="editIconPicker">
                    <span class="icon-option" data-icon="🏢">🏢</span>
                    <span class="icon-option" data-icon="🏭">🏭</span>
                    <span class="icon-option" data-icon="🏬">🏬</span>
                    <span class="icon-option" data-icon="🏪">🏪</span>
                    <span class="icon-option" data-icon="🏥">🏥</span>
                    <span class="icon-option" data-icon="🏫">🏫</span>
                    <span class="icon-option" data-icon="🏨">🏨</span>
                    <span class="icon-option" data-icon="🏦">🏦</span>
                    <span class="icon-option" data-icon="⚡">⚡</span>
                    <span class="icon-option" data-icon="🌐">🌐</span>
                    <span class="icon-option" data-icon="🔧">🔧</span>
                    <span class="icon-option" data-icon="📡">📡</span>
                </div>
                
                <button type="submit">Guardar Cambios</button>
            </form>
        </div>
    </div>

    <script>
        let groups = {};
        let connectedClients = [];
        let selectedIcon = '🏢';
        let editSelectedIcon = '🏢';

        document.querySelectorAll('#iconPicker .icon-option').forEach(opt => {
            opt.onclick = () => {
                document.querySelectorAll('#iconPicker .icon-option').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                selectedIcon = opt.dataset.icon;
            };
        });

        document.querySelectorAll('#editIconPicker .icon-option').forEach(opt => {
            opt.onclick = () => {
                document.querySelectorAll('#editIconPicker .icon-option').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                editSelectedIcon = opt.dataset.icon;
            };
        });

        function showModal(id) { document.getElementById(id).style.display = 'flex'; }
        function hideModal(id) { document.getElementById(id).style.display = 'none'; }

        function showEditGroupModal(groupId, name, icon) {
            document.getElementById('editGroupId').value = groupId;
            document.getElementById('editGroupName').value = name;
            editSelectedIcon = icon;
            document.querySelectorAll('#editIconPicker .icon-option').forEach(o => {
                o.classList.toggle('selected', o.dataset.icon === icon);
            });
            showModal('modalEditGroup');
        }

        document.getElementById('editGroupForm').onsubmit = async (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            btn.disabled = true;
            btn.textContent = 'Guardando...';
            
            const groupId = document.getElementById('editGroupId').value;
            const r = await fetch('/api/groups/' + groupId, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: document.getElementById('editGroupName').value,
                    icon: editSelectedIcon
                })
            });
            const d = await r.json();
            
            btn.disabled = false;
            btn.textContent = 'Guardar Cambios';
            
            if (d.success) {
                hideModal('modalEditGroup');
                loadGroups();
            } else {
                alert('Error: ' + d.error);
            }
        };

        async function showCreateGroupModal() {
            showModal('modalCreateGroup');
            const r = await fetch('/api/next-group-range');
            const d = await r.json();
            if (d.available) {
                document.getElementById('groupRangePreview').textContent = 
                    `${d.start_ip} - ${d.end_ip}`;
            } else {
                document.getElementById('groupRangePreview').textContent = '❌ No hay más rangos disponibles';
            }
        }

        document.getElementById('createGroupForm').onsubmit = async (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            btn.disabled = true;
            btn.textContent = 'Creando...';
            
            const r = await fetch('/api/groups', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: document.getElementById('groupName').value,
                    icon: selectedIcon
                })
            });
            const d = await r.json();
            
            btn.disabled = false;
            btn.textContent = 'Crear Grupo';
            
            if (d.success) {
                hideModal('modalCreateGroup');
                document.getElementById('groupName').value = '';
                loadGroups();
            } else {
                alert('Error: ' + d.error);
            }
        };

        document.getElementById('createForm').onsubmit = async (e) => {
            e.preventDefault();
            const status = document.getElementById('createStatus');
            const btn = e.target.querySelector('button[type="submit"]');
            
            status.style.display = 'block';
            status.className = 'status loading';
            status.textContent = '⏳ Creando cliente...';
            btn.disabled = true;
            
            const r = await fetch('/api/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: document.getElementById('clientName').value,
                    password: document.getElementById('caPassword').value,
                    group: document.getElementById('clientGroup').value
                })
            });
            const d = await r.json();
            
            btn.disabled = false;
            
            if (d.success) {
                status.className = 'status success';
                status.innerHTML = `✅ Cliente creado! IP: <strong>${d.ip}</strong> &nbsp; <a href="/download/${d.name}" style="color:#00d4ff;font-weight:bold;">📥 Descargar .ovpn</a>`;
                document.getElementById('clientName').value = '';
                loadClients();
                loadGroups();
            } else {
                status.className = 'status error';
                status.textContent = '❌ ' + d.error;
            }
        };

        document.getElementById('revokeForm').onsubmit = async (e) => {
            e.preventDefault();
            if (!confirm('¿Revocar este cliente? Esta acción es IRREVERSIBLE.')) return;
            
            const status = document.getElementById('revokeStatus');
            const btn = e.target.querySelector('button[type="submit"]');
            
            status.style.display = 'block';
            status.className = 'status loading';
            status.textContent = '⏳ Revocando...';
            btn.disabled = true;
            
            const r = await fetch('/api/revoke', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: document.getElementById('revokeClientName').value,
                    password: document.getElementById('revokePassword').value
                })
            });
            const d = await r.json();
            
            btn.disabled = false;
            
            if (d.success) {
                status.className = 'status success';
                status.textContent = '✅ Cliente revocado correctamente';
                document.getElementById('revokeClientName').value = '';
                loadClients();
                loadGroups();
            } else {
                status.className = 'status error';
                status.textContent = '❌ ' + d.error;
            }
        };

        async function loadGroups() {
            const r = await fetch('/api/groups');
            const d = await r.json();
            groups = d.groups;
            
            const container = document.getElementById('groupsList');
            const select = document.getElementById('clientGroup');
            
            const sortedGroups = Object.entries(groups).sort((a, b) => {
                if (a[1].is_system) return -1;
                if (b[1].is_system) return 1;
                return a[1].name.localeCompare(b[1].name);
            });
            
            if (sortedGroups.length === 0) {
                container.innerHTML = '<div class="empty-state"><div class="icon">📁</div><p>No hay grupos creados</p></div>';
            } else {
                let html = '';
                for (const [id, g] of sortedGroups) {
                    const used = (g.next_ip || g.range_start) - g.range_start;
                    const total = g.range_end - g.range_start + 1;
                    const isAdmin = g.is_system || g.can_see_all;
                    
                    html += `
                        <div class="group-card ${isAdmin ? 'admin' : ''}">
                            <div class="group-header">
                                <div>
                                    <span class="group-icon">${g.icon}</span>
                                    <span class="group-name">${g.name}</span>
                                    ${isAdmin ? '<span class="badge badge-admin" style="margin-left:10px;">VE TODO</span>' : ''}
                                    ${!isAdmin ? `<button class="btn-edit" onclick="showEditGroupModal('${id}', '${g.name}', '${g.icon}')">✏️</button>` : ''}
                                </div>
                                <div style="text-align:right;">
                                    <div><strong>${used}</strong> / ${total}</div>
                                    <div class="group-range">${g.start_ip} - ${g.end_ip}</div>
                                </div>
                            </div>
                        </div>
                    `;
                }
                container.innerHTML = html;
            }
            
            select.innerHTML = '<option value="">-- Seleccionar grupo --</option>';
            for (const [id, g] of sortedGroups) {
                const used = (g.next_ip || g.range_start) - g.range_start;
                const total = g.range_end - g.range_start + 1;
                const full = used >= total;
                select.innerHTML += `<option value="${id}" ${full ? 'disabled' : ''}>${g.icon} ${g.name} (${used}/${total})${full ? ' - LLENO' : ''}</option>`;
            }
        }

        async function loadClients() {
            const btn = document.getElementById('btnRefreshClients');
            btn.innerHTML = '⏳';
            btn.disabled = true;
            
            const r = await fetch('/api/clients');
            const d = await r.json();
            
            const byGroup = {};
            for (const c of d.clients) {
                const gid = c.group || 'sin-grupo';
                if (!byGroup[gid]) byGroup[gid] = [];
                byGroup[gid].push(c);
            }
            
            const sortedGroups = Object.entries(groups).sort((a, b) => {
                if (a[1].is_system) return -1;
                if (b[1].is_system) return 1;
                return a[1].name.localeCompare(b[1].name);
            });
            
            let html = '';
            
            for (const [gid, g] of sortedGroups) {
                const clients = byGroup[gid] || [];
                html += `<h3>${g.icon} ${g.name}</h3>`;
                
                if (clients.length === 0) {
                    html += '<p style="color:#555;font-size:13px;margin-left:10px;">Sin clientes</p>';
                } else {
                    for (const c of clients) {
                        const isOnline = connectedClients.includes(c.name);
                        const badge = isOnline 
                            ? '<span class="badge badge-online">● Online</span>' 
                            : '<span class="badge badge-offline">○ Offline</span>';
                        
                        html += `
                            <div class="client-row">
                                <div>
                                    <span class="client-name">${c.name}</span>
                                    <span class="client-ip">${c.ip || 'IP dinámica'}</span>
                                    ${badge}
                                </div>
                                <a href="/download/${c.name}" class="btn-small" style="background:#0f3460;color:#00d4ff;">📥 .ovpn</a>
                            </div>
                        `;
                    }
                }
            }
            
            document.getElementById('clientsByGroup').innerHTML = html || '<div class="empty-state"><div class="icon">👥</div><p>No hay clientes</p></div>';
            btn.innerHTML = '🔄';
            btn.disabled = false;
        }

        async function loadConnected() {
            const btn = document.getElementById('btnRefreshConnected');
            btn.innerHTML = '⏳';
            btn.disabled = true;
            
            const r = await fetch('/api/connected');
            const d = await r.json();
            connectedClients = d.clients.map(c => c.name);
            
            const tbody = document.getElementById('connectedList');
            
            if (d.clients.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="color:#555;text-align:center;">Sin conexiones activas</td></tr>';
            } else {
                tbody.innerHTML = d.clients.map(c => {
                    const grpBadge = c.group_name 
                        ? `<span class="badge badge-group">${c.group_icon} ${c.group_name}</span>`
                        : '<span style="color:#666">-</span>';
                    return `
                        <tr>
                            <td><strong>${c.name}</strong></td>
                            <td>${grpBadge}</td>
                            <td style="font-family:monospace">${c.vpn_ip}</td>
                            <td style="font-family:monospace;color:#888">${c.real_ip}</td>
                            <td style="color:#888;font-size:12px">${c.connected_since}</td>
                            <td style="font-size:12px">↓${c.bytes_recv} ↑${c.bytes_sent}</td>
                        </tr>
                    `;
                }).join('');
            }
            
            btn.innerHTML = '🔄';
            btn.disabled = false;
            loadClients();
        }

        loadGroups();
        loadConnected();
        setInterval(loadConnected, 30000);
    </script>
</body>
</html>
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        if request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'Contraseña incorrecta'
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/groups', methods=['GET'])
@login_required
def get_groups():
    db = load_clients_db()
    groups = db.get('groups', {})
    # Agregar campos de IP legibles para la UI
    for gid, g in groups.items():
        g['start_ip'] = ip_num_to_full(g['range_start'])
        g['end_ip'] = ip_num_to_full(g['range_end'])
    return jsonify({'groups': groups})

@app.route('/api/groups', methods=['POST'])
@login_required
def create_group():
    data = request.json
    name = data.get('name', '').strip()
    icon = data.get('icon', '🏢')
    
    if not name:
        return jsonify({'success': False, 'error': 'Nombre requerido'})
    
    if len(name) > 50:
        return jsonify({'success': False, 'error': 'Nombre muy largo (máx 50 caracteres)'})
    
    db = load_clients_db()
    
    group_id = re.sub(r'[^a-z0-9]', '-', name.lower()).strip('-')
    group_id = re.sub(r'-+', '-', group_id)
    if not group_id:
        group_id = f'grupo-{len(db["groups"])}'
    
    if group_id in db['groups']:
        return jsonify({'success': False, 'error': 'Ya existe un grupo con ese nombre'})
    
    next_start = db.get('next_group_start', FIRST_GROUP_START)
    next_end = next_start + GROUP_SIZE - 1
    
    if next_end > MAX_IP:
        return jsonify({'success': False, 'error': 'No hay más rangos de IP disponibles'})
    
    db['groups'][group_id] = {
        'name': name,
        'icon': icon,
        'range_start': next_start,
        'range_end': next_end,
        'next_ip': next_start,
        'can_see_all': False,
        'is_system': False
    }
    
    db['next_group_start'] = next_start + GROUP_SIZE
    save_clients_db(db)
    
    # Retornar IPs legibles
    start_ip = ip_num_to_full(next_start)
    end_ip = ip_num_to_full(next_end)
    return jsonify({'success': True, 'group_id': group_id, 'range_start': next_start, 'range_end': next_end, 'start_ip': start_ip, 'end_ip': end_ip})

@app.route('/api/groups/<group_id>', methods=['PUT'])
@login_required
def update_group(group_id):
    data = request.json
    name = data.get('name', '').strip()
    icon = data.get('icon', '🏢')
    
    if not name:
        return jsonify({'success': False, 'error': 'Nombre requerido'})
    
    if len(name) > 50:
        return jsonify({'success': False, 'error': 'Nombre muy largo (máx 50 caracteres)'})
    
    db = load_clients_db()
    
    if group_id not in db['groups']:
        return jsonify({'success': False, 'error': 'Grupo no encontrado'})
    
    # No permitir editar grupo admin
    if db['groups'][group_id].get('is_system') or db['groups'][group_id].get('can_see_all'):
        return jsonify({'success': False, 'error': 'No se puede editar el grupo de administradores'})
    
    db['groups'][group_id]['name'] = name
    db['groups'][group_id]['icon'] = icon
    save_clients_db(db)
    
    return jsonify({'success': True})

@app.route('/api/next-group-range', methods=['GET'])
@login_required
def get_next_group_range():
    db = load_clients_db()
    next_start = db.get('next_group_start', FIRST_GROUP_START)
    next_end = next_start + GROUP_SIZE - 1
    
    if next_end > MAX_IP:
        return jsonify({'available': False})
    
    # Convertir a IPs legibles
    start_ip = ip_num_to_full(next_start)
    end_ip = ip_num_to_full(next_end)
    
    return jsonify({
        'available': True,
        'start': next_start,
        'end': next_end,
        'start_ip': start_ip,
        'end_ip': end_ip,
        'capacity': GROUP_SIZE
    })

@app.route('/api/recalculate', methods=['POST'])
@login_required
def api_recalculate():
    """Recalcula los contadores de grupos basándose en clientes reales"""
    result = recalculate_group_counters()
    return jsonify({'success': True, 'message': 'Contadores recalculados', 'details': result})

@app.route('/api/clients')
@login_required
def list_clients():
    clients = []
    db = load_clients_db()
    
    if os.path.exists(CLIENTS_DIR):
        for f in os.listdir(CLIENTS_DIR):
            if f.endswith('.ovpn'):
                name = f.replace('.ovpn', '')
                info = db.get('clients', {}).get(name, {})
                clients.append({
                    'name': name,
                    'group': info.get('group'),
                    'ip': info.get('ip')
                })
    
    return jsonify({'clients': sorted(clients, key=lambda x: (x['group'] or 'zzz', x['name']))})

@app.route('/api/connected')
@login_required
def connected_clients():
    clients = []
    db = load_clients_db()
    
    try:
        # Usar docker exec en el contenedor en ejecución, no docker run
        cmd = 'docker exec openvpn cat /tmp/openvpn-status.log 2>/dev/null || echo ""'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split('\n')
        
        in_client_list = False
        for line in lines:
            if line.startswith('Common Name,'):
                in_client_list = True
                continue
            if line.startswith('ROUTING TABLE'):
                break
            if in_client_list and ',' in line:
                parts = line.split(',')
                if len(parts) >= 4 and parts[0] != 'UNDEF':
                    name = parts[0]
                    info = db.get('clients', {}).get(name, {})
                    gid = info.get('group')
                    grp = db.get('groups', {}).get(gid, {}) if gid else {}
                    
                    clients.append({
                        'name': name,
                        'real_ip': parts[1].split(':')[0],
                        'bytes_recv': format_bytes(int(parts[2])) if parts[2].isdigit() else parts[2],
                        'bytes_sent': format_bytes(int(parts[3])) if parts[3].isdigit() else parts[3],
                        'connected_since': parts[4] if len(parts) > 4 else 'N/A',
                        'vpn_ip': info.get('ip', 'Dinámica'),
                        'group_name': grp.get('name', ''),
                        'group_icon': grp.get('icon', '')
                    })
        
        in_routing = False
        for line in lines:
            if line.startswith('Virtual Address,'):
                in_routing = True
                continue
            if line.startswith('GLOBAL STATS'):
                break
            if in_routing and ',' in line:
                parts = line.split(',')
                if len(parts) >= 2:
                    for c in clients:
                        if c['name'] == parts[1] and c['vpn_ip'] == 'Dinámica':
                            c['vpn_ip'] = parts[0]
                            break
                            
    except Exception as e:
        print(f"Error getting connected clients: {e}")
    
    return jsonify({'clients': clients})

def format_bytes(b):
    if b < 1024:
        return f"{b}B"
    elif b < 1024 * 1024:
        return f"{b/1024:.1f}KB"
    else:
        return f"{b/(1024*1024):.1f}MB"

@app.route('/api/create', methods=['POST'])
@login_required
def create_client():
    data = request.json
    name = data.get('name', '').strip()
    password = data.get('password', '')
    group_id = data.get('group', '')
    
    if not name or not password:
        return jsonify({'success': False, 'error': 'Nombre y contraseña requeridos'})
    
    if not group_id:
        return jsonify({'success': False, 'error': 'Debe seleccionar un grupo'})
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({'success': False, 'error': 'Nombre inválido (solo letras, números, guiones)'})
    
    if len(name) > 64:
        return jsonify({'success': False, 'error': 'Nombre muy largo (máx 64 caracteres)'})
    
    db = load_clients_db()
    
    group = db['groups'].get(group_id)
    if not group:
        return jsonify({'success': False, 'error': 'Grupo no existe'})
    
    ip_num = get_next_ip_for_group(group_id)
    if ip_num is None:
        return jsonify({'success': False, 'error': 'Grupo lleno, no hay más IPs disponibles'})
    
    # Convertir número de IP a IP completa
    assigned_ip = ip_num_to_full(ip_num)
    
    try:
        os.makedirs(CCD_DIR, exist_ok=True)
        # Para /20, calcular peer IP (OpenVPN necesita pares)
        if ip_num % 2 == 0:
            peer_num = ip_num + 1
        else:
            peer_num = ip_num - 1
        peer_ip = ip_num_to_full(peer_num)
        
        with open(f'{CCD_DIR}/{name}', 'w') as f:
            f.write(f'ifconfig-push {assigned_ip} {peer_ip}\n')
        
        cmd = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm -i kylemanna/openvpn easyrsa build-client-full {name} nopass'
        proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(input=f'{password}\n'.encode(), timeout=120)
        
        if proc.returncode != 0:
            if os.path.exists(f'{CCD_DIR}/{name}'):
                os.remove(f'{CCD_DIR}/{name}')
            
            err = stderr.decode().lower()
            if 'bad decrypt' in err or 'pass phrase' in err:
                return jsonify({'success': False, 'error': 'Contraseña de CA incorrecta'})
            if 'already exists' in err:
                return jsonify({'success': False, 'error': 'Ya existe un cliente con ese nombre'})
            return jsonify({'success': False, 'error': stderr.decode()[:200]})
        
        cmd2 = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm kylemanna/openvpn ovpn_getclient {name}'
        result = subprocess.run(cmd2, shell=True, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            return jsonify({'success': False, 'error': 'Error exportando configuración'})
        
        os.makedirs(CLIENTS_DIR, exist_ok=True)
        with open(f'{CLIENTS_DIR}/{name}.ovpn', 'wb') as f:
            f.write(result.stdout)
        
        # Confirmar que la IP fue usada (actualiza el contador)
        confirm_ip_used(group_id, ip_num)
        
        db = load_clients_db()
        db['clients'][name] = {
            'group': group_id,
            'ip': assigned_ip
        }
        save_clients_db(db)
        
        return jsonify({'success': True, 'name': name, 'ip': assigned_ip, 'group': group_id})
        
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout - operación tardó demasiado'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/revoke', methods=['POST'])
@login_required
def revoke_client():
    data = request.json
    name = data.get('name', '').strip()
    password = data.get('password', '')
    
    if not name or not password:
        return jsonify({'success': False, 'error': 'Nombre y contraseña requeridos'})
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return jsonify({'success': False, 'error': 'Nombre inválido'})
    
    try:
        cmd = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm -i -e EASYRSA_BATCH=1 kylemanna/openvpn ovpn_revokeclient {name} remove'
        proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(input=f'{password}\n{password}\n'.encode(), timeout=120)
        
        output = (stdout.decode() + stderr.decode()).lower()
        success = 'revoking' in output or 'data base updated' in output
        
        if 'unable to find' in output or 'not found' in output:
            ovpn = f'{CLIENTS_DIR}/{name}.ovpn'
            if os.path.exists(ovpn):
                os.remove(ovpn)
                db = load_clients_db()
                if name in db.get('clients', {}):
                    del db['clients'][name]
                    save_clients_db(db)
                if os.path.exists(f'{CCD_DIR}/{name}'):
                    os.remove(f'{CCD_DIR}/{name}')
                return jsonify({'success': True})
            return jsonify({'success': False, 'error': 'Cliente no encontrado'})
        
        if 'bad decrypt' in output and not success:
            return jsonify({'success': False, 'error': 'Contraseña incorrecta'})
        
        if proc.returncode != 0 and not success:
            return jsonify({'success': False, 'error': output[:300]})
        
        ovpn = f'{CLIENTS_DIR}/{name}.ovpn'
        if os.path.exists(ovpn):
            os.remove(ovpn)
        
        db = load_clients_db()
        if name in db.get('clients', {}):
            del db['clients'][name]
            save_clients_db(db)
        
        if os.path.exists(f'{CCD_DIR}/{name}'):
            os.remove(f'{CCD_DIR}/{name}')
        
        # Reiniciar OpenVPN para que recargue el CRL (lista de revocados)
        try:
            subprocess.run('docker restart openvpn', shell=True, timeout=30)
        except:
            pass  # Si falla el restart, al menos la revocación ya se hizo
        
        return jsonify({'success': True, 'message': 'Cliente revocado. OpenVPN reiniciado.'})
        
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download/<name>')
@login_required
def download(name):
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    path = f'{CLIENTS_DIR}/{name}.ovpn'
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=f'{name}.ovpn')
    return 'Archivo no encontrado', 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
