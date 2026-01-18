// OpenVPN Admin - JavaScript

let groups = {};
let connectedClients = [];
let selectedIcon = '🏢';
let editSelectedIcon = '🏢';

// Icon picker handlers
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

// Modal functions
function showModal(id) {
    document.getElementById(id).style.display = 'flex';
}

function hideModal(id) {
    document.getElementById(id).style.display = 'none';
}

// Edit group modal
function showEditGroupModal(groupId, name, icon) {
    document.getElementById('editGroupId').value = groupId;
    document.getElementById('editGroupName').value = name;
    editSelectedIcon = icon;
    document.querySelectorAll('#editIconPicker .icon-option').forEach(o => {
        o.classList.toggle('selected', o.dataset.icon === icon);
    });
    showModal('modalEditGroup');
}

// Create group modal
async function showCreateGroupModal() {
    showModal('modalCreateGroup');
    const r = await fetch('/api/next-group-range');
    const d = await r.json();
    if (d.available) {
        document.getElementById('groupRangePreview').textContent = `${d.start_ip} - ${d.end_ip}`;
    } else {
        document.getElementById('groupRangePreview').textContent = '❌ No hay más rangos disponibles';
    }
}

// Edit group form
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
        location.reload();
    } else {
        alert('Error: ' + d.error);
    }
};

// Create group form
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
        location.reload();
    } else {
        alert('Error: ' + d.error);
    }
};

// Create client form
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
        status.innerHTML = `✅ Cliente creado! IP: <strong>${d.ip}</strong> &nbsp; <a href="/download/${d.name}" style="color:#00d4ff;font-weight:bold;">📥 Descargar .ovpn</a> <span style="color:#888;font-size:12px;">(recargando en 3s...)</span>`;
        document.getElementById('clientName').value = '';
        setTimeout(() => location.reload(), 3000);
    } else {
        status.className = 'status error';
        status.textContent = '❌ ' + d.error;
    }
};

// Revoke client form
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
        status.textContent = '✅ Cliente revocado correctamente (recargando...)';
        document.getElementById('revokeClientName').value = '';
        setTimeout(() => location.reload(), 1500);
    } else {
        status.className = 'status error';
        status.textContent = '❌ ' + d.error;
    }
};

// Load groups
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
                            ${!isAdmin ? `<button class="btn-edit" onclick="showEditGroupModal('${id}', '${g.name.replace(/'/g, "\\'")}', '${g.icon}')">✏️</button>` : ''}
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

// Load clients
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

// Load connected clients
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
            const vpnIpLink = c.vpn_ip && c.vpn_ip !== 'Dinámica' 
                ? `<a href="http://${c.vpn_ip}" target="_blank" style="color:#00d4ff;text-decoration:none;" title="Abrir en nueva pestaña">${c.vpn_ip}</a>`
                : c.vpn_ip;
            return `
                <tr>
                    <td><strong>${c.name}</strong></td>
                    <td>${grpBadge}</td>
                    <td style="font-family:monospace">${vpnIpLink}</td>
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

// Initialize
loadGroups();
loadConnected();
setInterval(loadConnected, 30000);
