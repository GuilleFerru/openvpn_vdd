from flask import Flask, render_template_string, request, send_file, jsonify
import subprocess
import os

app = Flask(__name__)

VOLUME_NAME = "openvpn_openvpn_data"
CLIENTS_DIR = "/app/clients"

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>OpenVPN Admin</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d4ff; }
        .card { background: #16213e; padding: 20px; border-radius: 10px; margin: 20px 0; }
        input, button { padding: 10px; margin: 5px 0; border-radius: 5px; border: none; width: 100%; box-sizing: border-box; }
        input { background: #0f3460; color: #fff; }
        button { background: #00d4ff; color: #1a1a2e; cursor: pointer; font-weight: bold; }
        button:hover { background: #00a8cc; }
        .btn-danger { background: #e94560; color: #fff; }
        .btn-danger:hover { background: #c73e54; }
        .success { color: #4ecca3; }
        .error { color: #e94560; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #0f3460; }
        .status { display: none; padding: 10px; border-radius: 5px; margin-top: 10px; }
        .loading { color: #ffd700; }
    </style>
</head>
<body>
    <h1>🔐 OpenVPN Admin</h1>
    
    <div class="card">
        <h2>Crear nuevo cliente</h2>
        <form id="createForm">
            <input type="text" id="clientName" placeholder="Nombre del cliente (ej: gateway-01)" required>
            <input type="password" id="caPassword" placeholder="Contraseña de la CA" required>
            <button type="submit">Crear Cliente</button>
        </form>
        <div id="createStatus" class="status"></div>
    </div>
    
    <div class="card">
        <h2>Clientes existentes</h2>
        <button onclick="loadClients()">🔄 Actualizar lista</button>
        <table>
            <thead><tr><th>Nombre</th><th>Acciones</th></tr></thead>
            <tbody id="clientList"></tbody>
        </table>
    </div>
    
    <div class="card">
        <h2>Revocar cliente</h2>
        <form id="revokeForm">
            <input type="text" id="revokeClientName" placeholder="Nombre del cliente a revocar" required>
            <input type="password" id="revokePassword" placeholder="Contraseña de la CA" required>
            <button type="submit" class="btn-danger">⚠️ Revocar Cliente</button>
        </form>
        <div id="revokeStatus" class="status"></div>
    </div>

    <script>
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
                loadClients();
            } else {
                status.className = 'status error';
                status.textContent = '❌ Error: ' + data.error;
            }
        };
        
        document.getElementById('revokeForm').onsubmit = async (e) => {
            e.preventDefault();
            if (!confirm('¿Seguro que querés revocar este cliente?')) return;
            
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
                status.textContent = '✅ Cliente revocado';
                loadClients();
            } else {
                status.className = 'status error';
                status.textContent = '❌ Error: ' + data.error;
            }
        };
        
        async function loadClients() {
            const response = await fetch('/api/clients');
            const data = await response.json();
            const tbody = document.getElementById('clientList');
            tbody.innerHTML = data.clients.map(c => 
                '<tr><td>' + c + '</td><td><a href="/download/' + c + '" style="color:#00d4ff">📥 Descargar</a></td></tr>'
            ).join('');
        }
        
        loadClients();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/clients')
def list_clients():
    clients = []
    if os.path.exists(CLIENTS_DIR):
        clients = [f.replace('.ovpn', '') for f in os.listdir(CLIENTS_DIR) if f.endswith('.ovpn')]
    return jsonify({'clients': clients})

@app.route('/api/create', methods=['POST'])
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
        stdout, stderr = proc.communicate(input=f'{password}\n'.encode(), timeout=60)
        
        if proc.returncode != 0:
            error_msg = stderr.decode()
            if 'password' in error_msg.lower() or 'pass phrase' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Contraseña incorrecta'})
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
def revoke_client():
    data = request.json
    name = data.get('name', '').strip()
    password = data.get('password', '')
    
    if not name or not password:
        return jsonify({'success': False, 'error': 'Nombre y contraseña requeridos'})
    
    try:
        cmd = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm -i kylemanna/openvpn ovpn_revokeclient {name}'
        proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(input=f'{password}\nyes\n'.encode(), timeout=60)
        
        if proc.returncode != 0:
            return jsonify({'success': False, 'error': stderr.decode()[:200]})
        
        # Eliminar archivo .ovpn
        ovpn_file = f'{CLIENTS_DIR}/{name}.ovpn'
        if os.path.exists(ovpn_file):
            os.remove(ovpn_file)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download/<name>')
def download(name):
    filepath = f'{CLIENTS_DIR}/{name}.ovpn'
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=f'{name}.ovpn')
    return 'Archivo no encontrado', 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
