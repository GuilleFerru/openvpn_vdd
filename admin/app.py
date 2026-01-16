from flask import Flask, render_template_string, request, send_file, jsonify, redirect, url_for, session
from functools import wraps
import subprocess
import os
import re
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

VOLUME_NAME = "openvpn_openvpn_data"
CLIENTS_DIR = "/app/clients"
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')  # Cambiar en docker-compose

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
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #16213e; padding: 40px; border-radius: 15px; width: 300px; text-align: center; }
        h1 { color: #00d4ff; margin-bottom: 30px; }
        input { padding: 12px; margin: 10px 0; border-radius: 5px; border: none; width: 100%; box-sizing: border-box; background: #0f3460; color: #fff; }
        button { padding: 12px; margin-top: 20px; border-radius: 5px; border: none; width: 100%; background: #00d4ff; color: #1a1a2e; cursor: pointer; font-weight: bold; font-size: 16px; }
        button:hover { background: #00a8cc; }
        .error { color: #e94560; margin-top: 15px; }
        .icon { font-size: 60px; margin-bottom: 10px; }
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
        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
    </div>
</body>
</html>
'''

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>OpenVPN Admin</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 50px auto; padding: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d4ff; }
        h2 { color: #4ecca3; margin-top: 0; }
        .card { background: #16213e; padding: 20px; border-radius: 10px; margin: 20px 0; }
        input, button { padding: 10px; margin: 5px 0; border-radius: 5px; border: none; width: 100%; box-sizing: border-box; }
        input { background: #0f3460; color: #fff; }
        button { background: #00d4ff; color: #1a1a2e; cursor: pointer; font-weight: bold; }
        button:hover { background: #00a8cc; }
        .btn-danger { background: #e94560; color: #fff; }
        .btn-danger:hover { background: #c73e54; }
        .btn-small { width: auto; padding: 5px 10px; font-size: 12px; }
        .success { color: #4ecca3; }
        .error { color: #e94560; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #0f3460; }
        .status { display: none; padding: 10px; border-radius: 5px; margin-top: 10px; }
        .loading { color: #ffd700; }
        .online { color: #4ecca3; }
        .offline { color: #888; }
        .badge { display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 11px; }
        .badge-online { background: #4ecca3; color: #1a1a2e; }
        .badge-offline { background: #444; color: #888; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .btn-logout { background: #444; color: #fff; width: auto; padding: 8px 15px; font-size: 13px; }
        .btn-logout:hover { background: #666; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 OpenVPN Admin</h1>
        <a href="/logout"><button class="btn-logout">🚪 Cerrar sesión</button></a>
    </div>
    
    <div class="card">
        <h2>📡 Clientes Conectados</h2>
        <button id="btnRefreshConnected" onclick="loadConnected()">🔄 Actualizar</button>
        <table>
            <thead><tr><th>Cliente</th><th>IP VPN</th><th>IP Real</th><th>Conectado desde</th><th>Tráfico</th></tr></thead>
            <tbody id="connectedList"><tr><td colspan="5">Cargando...</td></tr></tbody>
        </table>
    </div>
    
    <div class="card">
        <h2>➕ Crear nuevo cliente</h2>
        <form id="createForm">
            <input type="text" id="clientName" placeholder="Nombre del cliente (ej: gateway-01)" required>
            <input type="password" id="caPassword" placeholder="Contraseña de la CA" required>
            <button type="submit">Crear Cliente</button>
        </form>
        <div id="createStatus" class="status"></div>
    </div>
    
    <div class="card">
        <h2>📁 Clientes existentes</h2>
        <button id="btnRefreshClients" onclick="loadClients()">🔄 Actualizar lista</button>
        <table>
            <thead><tr><th>Nombre</th><th>Estado</th><th>Acciones</th></tr></thead>
            <tbody id="clientList"></tbody>
        </table>
    </div>
    
    <div class="card">
        <h2>⚠️ Revocar cliente</h2>
        <form id="revokeForm">
            <input type="text" id="revokeClientName" placeholder="Nombre del cliente a revocar" required>
            <input type="password" id="revokePassword" placeholder="Contraseña de la CA" required>
            <button type="submit" class="btn-danger">Revocar Cliente</button>
        </form>
        <div id="revokeStatus" class="status"></div>
    </div>
    
    <div class="card">
        <h2>🗑️ Eliminar archivo .ovpn</h2>
        <p style="color:#888;font-size:12px;">Elimina archivos huérfanos sin revocar el certificado</p>
        <form id="deleteForm">
            <input type="text" id="deleteClientName" placeholder="Nombre del cliente" required>
            <button type="submit" class="btn-danger">Eliminar archivo</button>
        </form>
        <div id="deleteStatus" class="status"></div>
    </div>

    <script>
        let connectedClients = [];
        
        document.getElementById('createForm').onsubmit = async (e) => {
            e.preventDefault();
            const status = document.getElementById('createStatus');
            status.style.display = 'block';
            status.className = 'status loading';
            status.textContent = 'Creando cliente... (esto puede tardar unos segundos)';
            
            const response = await fetch('/api/create', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: document.getElementById('clientName').value,
                    password: document.getElementById('caPassword').value
                })
            });
            const data = await response.json();
            
            if (data.success) {
                status.className = 'status success';
                status.innerHTML = '✅ Cliente creado! <a href="/download/' + data.name + '" style="color:#00d4ff">Descargar ' + data.name + '.ovpn</a>';
                document.getElementById('clientName').value = '';
                loadClients();
            } else {
                status.className = 'status error';
                status.textContent = '❌ Error: ' + data.error;
            }
        };
        
        document.getElementById('revokeForm').onsubmit = async (e) => {
            e.preventDefault();
            if (!confirm('¿Seguro que querés revocar este cliente? Esta acción es IRREVERSIBLE.')) return;
            
            const status = document.getElementById('revokeStatus');
            status.style.display = 'block';
            status.className = 'status loading';
            status.textContent = 'Revocando cliente...';
            
            const response = await fetch('/api/revoke', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: document.getElementById('revokeClientName').value,
                    password: document.getElementById('revokePassword').value
                })
            });
            const data = await response.json();
            
            if (data.success) {
                status.className = 'status success';
                status.textContent = '✅ Cliente revocado correctamente';
                document.getElementById('revokeClientName').value = '';
                loadClients();
            } else {
                status.className = 'status error';
                status.textContent = '❌ Error: ' + data.error;
            }
        };
        
        document.getElementById('deleteForm').onsubmit = async (e) => {
            e.preventDefault();
            if (!confirm('¿Eliminar este archivo .ovpn?')) return;
            
            const status = document.getElementById('deleteStatus');
            status.style.display = 'block';
            
            const response = await fetch('/api/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: document.getElementById('deleteClientName').value
                })
            });
            const data = await response.json();
            
            if (data.success) {
                status.className = 'status success';
                status.textContent = '✅ Archivo eliminado';
                document.getElementById('deleteClientName').value = '';
                loadClients();
            } else {
                status.className = 'status error';
                status.textContent = '❌ Error: ' + data.error;
            }
        };
        
        async function loadClients() {
            const btn = document.getElementById('btnRefreshClients');
            const originalText = btn.innerHTML;
            btn.innerHTML = '⏳ Cargando...';
            btn.disabled = true;
            
            const response = await fetch('/api/clients');
            const data = await response.json();
            const tbody = document.getElementById('clientList');
            tbody.innerHTML = data.clients.map(c => {
                const isOnline = connectedClients.includes(c);
                const badge = isOnline 
                    ? '<span class="badge badge-online">● Online</span>' 
                    : '<span class="badge badge-offline">○ Offline</span>';
                return '<tr><td>' + c + '</td><td>' + badge + '</td><td><a href="/download/' + c + '" style="color:#00d4ff">📥 Descargar</a></td></tr>';
            }).join('');
            
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
        
        async function loadConnected() {
            const btn = document.getElementById('btnRefreshConnected');
            const originalText = btn.innerHTML;
            btn.innerHTML = '⏳ Cargando...';
            btn.disabled = true;
            
            const response = await fetch('/api/connected');
            const data = await response.json();
            const tbody = document.getElementById('connectedList');
            connectedClients = data.clients.map(c => c.name);
            
            if (data.clients.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="color:#888">No hay clientes conectados</td></tr>';
            } else {
                tbody.innerHTML = data.clients.map(c => 
                    '<tr><td><strong>' + c.name + '</strong></td><td>' + c.vpn_ip + '</td><td>' + c.real_ip + '</td><td>' + c.connected_since + '</td><td>↓' + c.bytes_recv + ' ↑' + c.bytes_sent + '</td></tr>'
                ).join('');
            }
            
            btn.innerHTML = originalText;
            btn.disabled = false;
            loadClients();
        }
        
        loadConnected();
        setInterval(loadConnected, 30000); // Auto-refresh cada 30s
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

@app.route('/api/clients')
@login_required
def list_clients():
    clients = []
    if os.path.exists(CLIENTS_DIR):
        clients = [f.replace('.ovpn', '') for f in os.listdir(CLIENTS_DIR) if f.endswith('.ovpn')]
    return jsonify({'clients': sorted(clients)})

@app.route('/api/connected')
@login_required
def connected_clients():
    """Lee el status log de OpenVPN para ver clientes conectados"""
    clients = []
    try:
        cmd = f'docker exec openvpn cat /tmp/openvpn-status.log 2>/dev/null || echo ""'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.stdout:
            lines = result.stdout.split('\n')
            in_client_list = False
            
            for line in lines:
                if line.startswith('Common Name,'):
                    in_client_list = True
                    continue
                if line.startswith('ROUTING TABLE') or line.startswith('Virtual Address'):
                    in_client_list = False
                    continue
                    
                if in_client_list and ',' in line:
                    parts = line.split(',')
                    if len(parts) >= 5 and parts[0] != 'UNDEF':
                        clients.append({
                            'name': parts[0],
                            'real_ip': parts[1].split(':')[0] if ':' in parts[1] else parts[1],
                            'bytes_recv': format_bytes(int(parts[2])) if parts[2].isdigit() else parts[2],
                            'bytes_sent': format_bytes(int(parts[3])) if parts[3].isdigit() else parts[3],
                            'connected_since': parts[4] if len(parts) > 4 else 'N/A',
                            'vpn_ip': ''
                        })
            
            # Obtener IPs VPN de la routing table
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
                        vpn_ip = parts[0]
                        client_name = parts[1]
                        for c in clients:
                            if c['name'] == client_name:
                                c['vpn_ip'] = vpn_ip
                                break
                                
    except Exception as e:
        print(f"Error getting connected clients: {e}")
    
    return jsonify({'clients': clients})

def format_bytes(bytes_num):
    if bytes_num < 1024:
        return f"{bytes_num}B"
    elif bytes_num < 1024*1024:
        return f"{bytes_num/1024:.1f}KB"
    else:
        return f"{bytes_num/(1024*1024):.1f}MB"

@app.route('/api/create', methods=['POST'])
@login_required
def create_client():
    data = request.json
    name = data.get('name', '').strip()
    password = data.get('password', '')
    
    if not name or not password:
        return jsonify({'success': False, 'error': 'Nombre y contraseña requeridos'})
    
    # Validar nombre (solo letras, números, guiones)
    if not name.replace('-', '').replace('_', '').isalnum():
        return jsonify({'success': False, 'error': 'Nombre inválido (solo letras, números, guiones)'})
    
    try:
        # Crear certificado del cliente
        cmd_create = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm -i kylemanna/openvpn easyrsa build-client-full {name} nopass'
        proc = subprocess.Popen(cmd_create, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(input=f'{password}\n'.encode(), timeout=120)
        
        if proc.returncode != 0:
            error_msg = stderr.decode()
            if 'password' in error_msg.lower() or 'pass phrase' in error_msg.lower() or 'bad decrypt' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Contraseña incorrecta'})
            if 'already exists' in error_msg.lower():
                return jsonify({'success': False, 'error': 'El cliente ya existe'})
            return jsonify({'success': False, 'error': error_msg[:200]})
        
        # Exportar .ovpn
        cmd_export = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm kylemanna/openvpn ovpn_getclient {name}'
        result = subprocess.run(cmd_export, shell=True, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            return jsonify({'success': False, 'error': 'Error exportando archivo'})
        
        # Guardar archivo
        os.makedirs(CLIENTS_DIR, exist_ok=True)
        with open(f'{CLIENTS_DIR}/{name}.ovpn', 'wb') as f:
            f.write(result.stdout)
        
        return jsonify({'success': True, 'name': name})
        
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
    
    # Validar nombre
    if not name.replace('-', '').replace('_', '').isalnum():
        return jsonify({'success': False, 'error': 'Nombre inválido'})
    
    try:
        # Usar EASYRSA_BATCH=1 para evitar confirmación "yes"
        # Solo necesita password 2 veces (revoke + CRL update)
        cmd = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm -i -e EASYRSA_BATCH=1 kylemanna/openvpn ovpn_revokeclient {name} remove'
        proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Enviar password dos veces (revoke + CRL)
        inputs = f'{password}\n{password}\n'.encode()
        stdout, stderr = proc.communicate(input=inputs, timeout=120)
        
        output = stdout.decode() + stderr.decode()
        output_lower = output.lower()
        
        # Verificar si el certificado fue revocado exitosamente
        # Buscar indicadores de éxito en el output
        revoke_success = 'revoking certificate' in output_lower or 'revocation was successful' in output_lower or 'data base updated' in output_lower
        
        # Verificar errores específicos
        if 'unable to find' in output_lower or 'not found' in output_lower or 'no such file' in output_lower:
            # El cliente no existe - eliminar archivo .ovpn si existe
            ovpn_file = f'{CLIENTS_DIR}/{name}.ovpn'
            if os.path.exists(ovpn_file):
                os.remove(ovpn_file)
                return jsonify({'success': True, 'message': 'Cliente ya revocado, archivo eliminado'})
            return jsonify({'success': False, 'error': f'Cliente "{name}" no encontrado'})
        
        # Si hubo error de password Y no hay indicadores de éxito
        if ('bad decrypt' in output_lower or 'wrong pass' in output_lower) and not revoke_success:
            return jsonify({'success': False, 'error': 'Contraseña incorrecta'})
        
        # Si el return code es error pero hay indicadores de éxito, considerar exitoso
        if proc.returncode != 0 and not revoke_success:
            return jsonify({'success': False, 'error': output[:300]})
        
        # Eliminar archivo .ovpn
        ovpn_file = f'{CLIENTS_DIR}/{name}.ovpn'
        if os.path.exists(ovpn_file):
            os.remove(ovpn_file)
        
        return jsonify({'success': True})
        
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout - operación tardó demasiado'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete', methods=['POST'])
@login_required
def delete_ovpn():
    """Elimina solo el archivo .ovpn sin revocar el certificado"""
    data = request.json
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'error': 'Nombre requerido'})
    
    ovpn_file = f'{CLIENTS_DIR}/{name}.ovpn'
    if os.path.exists(ovpn_file):
        os.remove(ovpn_file)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Archivo no encontrado'})

@app.route('/download/<name>')
@login_required
def download(name):
    # Sanitizar nombre
    name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    filepath = f'{CLIENTS_DIR}/{name}.ovpn'
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=f'{name}.ovpn')
    return 'Archivo no encontrado', 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
