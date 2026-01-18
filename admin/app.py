"""
OpenVPN Admin - API Server
Flask application for managing OpenVPN clients and groups
"""

from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, session
from functools import wraps
from datetime import datetime, timedelta
import subprocess
import os
import re
import secrets
import json

# =============================================================================
# Configuration
# =============================================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

VOLUME_NAME = "openvpn_openvpn_data"
CLIENTS_DIR = "/app/clients"
CCD_DIR = "/app/ccd"
CLIENTS_DB = "/app/clients/clients.json"
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Network configuration - Subnet /20: 10.8.0.0 - 10.8.15.255 (4096 IPs)
VPN_SUBNET_BASE = "10.8"
ADMIN_RANGE = {'start': 4, 'end': 15}  # 12 IPs for admins (10.8.0.4 - 10.8.0.15)
GROUP_SIZE = 12  # Each group has 12 IPs
FIRST_GROUP_START = 16  # First group starts at IP 16 (10.8.0.16)
MAX_IP = 4095  # Last available IP (10.8.15.255)


# =============================================================================
# IP Helper Functions
# =============================================================================

def ip_to_octets(ip_num):
    """Convert IP number (0-4095) to last two octets"""
    return ip_num // 256, ip_num % 256


def octets_to_ip(third, fourth):
    """Convert octets to full IP"""
    return f"{VPN_SUBNET_BASE}.{third}.{fourth}"


def ip_num_to_full(ip_num):
    """Convert number to full IP address"""
    third, fourth = ip_to_octets(ip_num)
    return octets_to_ip(third, fourth)


def utc_to_argentina(utc_time_str):
    """Convert UTC time string to Argentina time (GMT-3)"""
    try:
        # OpenVPN format: "Thu Jan 18 20:15:23 2026" or similar
        # Try common formats
        formats = [
            '%a %b %d %H:%M:%S %Y',
            '%Y-%m-%d %H:%M:%S',
            '%a %b %d %H:%M:%S %Y'
        ]
        for fmt in formats:
            try:
                utc_dt = datetime.strptime(utc_time_str.strip(), fmt)
                # Subtract 3 hours for Argentina (GMT-3)
                arg_dt = utc_dt - timedelta(hours=3)
                return arg_dt.strftime('%a %b %d %H:%M:%S %Y')
            except ValueError:
                continue
        return utc_time_str  # Return original if parsing fails
    except:
        return utc_time_str


# =============================================================================
# Database Functions
# =============================================================================

def load_clients_db():
    """Load clients database from JSON file"""
    if os.path.exists(CLIENTS_DB):
        with open(CLIENTS_DB, 'r') as f:
            data = json.load(f)
            if 'groups' not in data:
                data = _create_default_db(data.get('clients', {}))
                save_clients_db(data)
            return data
    return _create_default_db({})


def _create_default_db(existing_clients=None):
    """Create default database structure"""
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
        'clients': existing_clients or {},
        'next_group_start': FIRST_GROUP_START
    }


def save_clients_db(db):
    """Save clients database to JSON file"""
    os.makedirs(os.path.dirname(CLIENTS_DB), exist_ok=True)
    with open(CLIENTS_DB, 'w') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


# =============================================================================
# Group Management Functions
# =============================================================================

def get_next_ip_for_group(group_id):
    """Get next available IP for a group (doesn't increment counter)"""
    db = load_clients_db()
    group = db['groups'].get(group_id)
    if not group:
        return None
    ip = group.get('next_ip', group['range_start'])
    if ip > group['range_end']:
        return None
    return ip


def confirm_ip_used(group_id, ip_octet):
    """Confirm IP was used and update counter"""
    db = load_clients_db()
    group = db['groups'].get(group_id)
    if group and ip_octet >= group.get('next_ip', group['range_start']):
        db['groups'][group_id]['next_ip'] = ip_octet + 1
        save_clients_db(db)


def recalculate_group_counters():
    """Recalculate group counters based on actual .ovpn files"""
    db = load_clients_db()
    
    # Get list of existing clients (actual .ovpn files)
    existing_clients = set()
    if os.path.exists(CLIENTS_DIR):
        for f in os.listdir(CLIENTS_DIR):
            if f.endswith('.ovpn'):
                existing_clients.add(f.replace('.ovpn', ''))
    
    # Clean up clients that no longer exist
    clients_to_remove = [
        name for name in db.get('clients', {}).keys() 
        if name not in existing_clients
    ]
    for client_name in clients_to_remove:
        del db['clients'][client_name]
    
    # Count actual clients per group
    group_clients = {}
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
    
    # Update next_ip for each group based on highest used IP
    for gid, group in db['groups'].items():
        if gid in group_clients and group_clients[gid]:
            max_ip = max(group_clients[gid])
            db['groups'][gid]['next_ip'] = max_ip + 1
        else:
            db['groups'][gid]['next_ip'] = group['range_start']
    
    save_clients_db(db)
    return {
        'cleaned': clients_to_remove,
        'groups': {gid: len(ips) for gid, ips in group_clients.items()}
    }


# =============================================================================
# Authentication
# =============================================================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# Utility Functions
# =============================================================================

def format_bytes(b):
    """Format bytes to human readable string"""
    if b < 1024:
        return f"{b}B"
    elif b < 1024 * 1024:
        return f"{b/1024:.1f}KB"
    else:
        return f"{b/(1024*1024):.1f}MB"


# =============================================================================
# Routes - Authentication
# =============================================================================

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
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    return render_template('index.html')


# =============================================================================
# Routes - Groups API
# =============================================================================

@app.route('/api/groups', methods=['GET'])
@login_required
def get_groups():
    db = load_clients_db()
    groups = db.get('groups', {})
    clients = db.get('clients', {})
    
    # Count actual clients per group
    client_count = {}
    for client_name, client_info in clients.items():
        gid = client_info.get('group')
        if gid:
            # Verify .ovpn file exists
            if os.path.exists(f'{CLIENTS_DIR}/{client_name}.ovpn'):
                client_count[gid] = client_count.get(gid, 0) + 1
    
    # Add readable IP fields and real client count for UI
    for gid, g in groups.items():
        g['start_ip'] = ip_num_to_full(g['range_start'])
        g['end_ip'] = ip_num_to_full(g['range_end'])
        g['client_count'] = client_count.get(gid, 0)
    
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
    
    # Generate group ID from name
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
    
    start_ip = ip_num_to_full(next_start)
    end_ip = ip_num_to_full(next_end)
    return jsonify({
        'success': True, 
        'group_id': group_id, 
        'range_start': next_start, 
        'range_end': next_end, 
        'start_ip': start_ip, 
        'end_ip': end_ip
    })


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
    
    # Don't allow editing admin group
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
    """Recalculate group counters based on actual clients"""
    result = recalculate_group_counters()
    return jsonify({'success': True, 'message': 'Contadores recalculados', 'details': result})


# =============================================================================
# Routes - Clients API
# =============================================================================

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
    
    # First, get list of rejected clients to filter them out
    rejected_names = set()
    try:
        cmd = 'docker logs openvpn --tail 200 2>&1'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        for line in result.stdout.split('\n'):
            if 'client-config-dir authentication failed' in line and 'common name' in line:
                match = re.search(r"common name '([^']+)'", line)
                if match:
                    rejected_names.add(match.group(1))
    except:
        pass
    
    try:
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
                    
                    # Skip rejected clients - they appear briefly during failed auth
                    if name in rejected_names:
                        continue
                    
                    info = db.get('clients', {}).get(name, {})
                    gid = info.get('group')
                    grp = db.get('groups', {}).get(gid, {}) if gid else {}
                    
                    clients.append({
                        'name': name,
                        'real_ip': parts[1].split(':')[0],
                        'bytes_recv': format_bytes(int(parts[2])) if parts[2].isdigit() else parts[2],
                        'bytes_sent': format_bytes(int(parts[3])) if parts[3].isdigit() else parts[3],
                        'connected_since': utc_to_argentina(parts[4]) if len(parts) > 4 else 'N/A',
                        'vpn_ip': info.get('ip', 'Dinámica'),
                        'group_name': grp.get('name', ''),
                        'group_icon': grp.get('icon', '')
                    })
        
        # Get VPN IPs from routing table
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


@app.route('/api/rejected')
@login_required
def rejected_clients():
    """Get list of clients rejected due to missing CCD (ccd-exclusive)"""
    rejected = {}
    
    try:
        # Get last 500 lines of OpenVPN logs
        cmd = 'docker logs openvpn --tail 500 2>&1'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        lines = result.stdout.strip().split('\n')
        
        for line in lines:
            # Look for CCD auth failures
            if 'client-config-dir authentication failed' in line and 'common name' in line:
                # Extract client name
                match = re.search(r"common name '([^']+)'", line)
                if match:
                    name = match.group(1)
                    # Extract timestamp
                    ts_match = re.search(r'^(\w+ \w+ \d+ \d+:\d+:\d+ \d+)', line)
                    timestamp = ts_match.group(1) if ts_match else 'N/A'
                    
                    # Keep latest attempt per client
                    if name not in rejected or timestamp > rejected[name]['last_attempt']:
                        # Extract IP
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+):', line)
                        real_ip = ip_match.group(1) if ip_match else 'N/A'
                        
                        rejected[name] = {
                            'name': name,
                            'real_ip': real_ip,
                            'last_attempt': utc_to_argentina(timestamp),
                            'reason': 'Sin archivo CCD'
                        }
                        
                        # Count attempts
                        if 'attempts' in rejected.get(name, {}):
                            rejected[name]['attempts'] += 1
                        else:
                            rejected[name]['attempts'] = 1
        
        # Count total attempts per client
        for line in lines:
            if 'client-config-dir authentication failed' in line:
                match = re.search(r"common name '([^']+)'", line)
                if match and match.group(1) in rejected:
                    rejected[match.group(1)]['attempts'] = rejected.get(match.group(1), {}).get('attempts', 0) + 1
        
        # Divide by 2 because we counted twice (once in first loop, once in second)
        for name in rejected:
            rejected[name]['attempts'] = max(1, rejected[name]['attempts'] // 2)
                        
    except Exception as e:
        print(f"Error getting rejected clients: {e}")
    
    return jsonify({'clients': list(rejected.values())})


@app.route('/api/create', methods=['POST'])
@login_required
def create_client():
    data = request.json
    name = data.get('name', '').strip()
    password = data.get('password', '')
    group_id = data.get('group', '')
    
    # Validation
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
    
    assigned_ip = ip_num_to_full(ip_num)
    
    try:
        # Create CCD file for static IP
        os.makedirs(CCD_DIR, exist_ok=True)
        if ip_num % 2 == 0:
            peer_num = ip_num + 1
        else:
            peer_num = ip_num - 1
        peer_ip = ip_num_to_full(peer_num)
        
        with open(f'{CCD_DIR}/{name}', 'w') as f:
            f.write(f'ifconfig-push {assigned_ip} {peer_ip}\n')
        
        # Generate certificate
        cmd = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm -i kylemanna/openvpn easyrsa build-client-full {name} nopass'
        proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(input=f'{password}\n'.encode(), timeout=120)
        
        if proc.returncode != 0:
            # Cleanup on failure
            if os.path.exists(f'{CCD_DIR}/{name}'):
                os.remove(f'{CCD_DIR}/{name}')
            
            err = stderr.decode().lower()
            if 'bad decrypt' in err or 'pass phrase' in err:
                return jsonify({'success': False, 'error': 'Contraseña de CA incorrecta'})
            if 'already exists' in err:
                return jsonify({'success': False, 'error': 'Ya existe un cliente con ese nombre'})
            return jsonify({'success': False, 'error': stderr.decode()[:200]})
        
        # Export .ovpn file
        cmd2 = f'docker run -v {VOLUME_NAME}:/etc/openvpn --rm kylemanna/openvpn ovpn_getclient {name}'
        result = subprocess.run(cmd2, shell=True, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            # Cleanup CCD on failure
            if os.path.exists(f'{CCD_DIR}/{name}'):
                os.remove(f'{CCD_DIR}/{name}')
            return jsonify({'success': False, 'error': 'Error exportando configuración'})
        
        os.makedirs(CLIENTS_DIR, exist_ok=True)
        with open(f'{CLIENTS_DIR}/{name}.ovpn', 'wb') as f:
            f.write(result.stdout)
        
        # Confirm IP was used (updates counter)
        confirm_ip_used(group_id, ip_num)
        
        # Save to database
        db = load_clients_db()
        db['clients'][name] = {
            'group': group_id,
            'ip': assigned_ip
        }
        save_clients_db(db)
        
        return jsonify({'success': True, 'name': name, 'ip': assigned_ip, 'group': group_id})
        
    except subprocess.TimeoutExpired:
        # Cleanup CCD on timeout
        if os.path.exists(f'{CCD_DIR}/{name}'):
            os.remove(f'{CCD_DIR}/{name}')
        return jsonify({'success': False, 'error': 'Timeout - operación tardó demasiado'})
    except Exception as e:
        # Cleanup CCD on any error
        if os.path.exists(f'{CCD_DIR}/{name}'):
            os.remove(f'{CCD_DIR}/{name}')
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
        
        # Cleanup files
        ovpn = f'{CLIENTS_DIR}/{name}.ovpn'
        if os.path.exists(ovpn):
            os.remove(ovpn)
        
        db = load_clients_db()
        if name in db.get('clients', {}):
            del db['clients'][name]
            save_clients_db(db)
        
        if os.path.exists(f'{CCD_DIR}/{name}'):
            os.remove(f'{CCD_DIR}/{name}')
        
        # Restart OpenVPN to reload CRL
        try:
            subprocess.run('docker restart openvpn', shell=True, timeout=30)
        except:
            pass
        
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


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
