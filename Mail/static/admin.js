// ── Data ──
let allUsers = [];
let allActivity = [];
let allActive = [];
let apiUsage = {};
let allErrors = [];

// ── Init ──
document.getElementById('adminInitial').textContent = ADMIN_NAME.charAt(0).toUpperCase();

// ── Panel switching ──
function showPanel(id, el) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('nav .nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('panel-' + id).classList.add('active');
    if (el) el.classList.add('active');

    // Lazy load
    if (id === 'users') loadUsers();
    if (id === 'activity') loadActivity();
    if (id === 'api') loadApiUsage();
    if (id === 'errors') loadErrors();
    if (id === 'status') refreshStatus();
}

// ── Stats ──
async function loadStats() {
    try {
        const res = await fetch('/admin/stats');
        const data = await res.json();

        document.getElementById('sTotalUsers').textContent = data.total_users ?? '—';
        document.getElementById('sActiveNow').textContent = data.active_users ?? '—';
        document.getElementById('sTotalCommands').textContent = data.total_commands ?? '—';
        document.getElementById('sTotalLogins').textContent = data.total_logins ?? '—';
        document.getElementById('sEmailsSent').textContent = data.emails_sent ?? '—';
        document.getElementById('sTgSent').textContent = data.tg_sent ?? '—';
        document.getElementById('sWaSent').textContent = data.wa_sent ?? '—';

        // PIN fails
        const pf = data.pin_fails ?? 0;
        document.getElementById('sPinFails').textContent = pf;
        document.getElementById('trendErrors').textContent = pf > 0 ? `${pf} FAILS` : 'NONE';

        document.getElementById('activeCount').textContent =
            `${data.active_users} user${data.active_users !== 1 ? 's' : ''} active`;
        document.getElementById('activeUserCount').textContent = data.active_users;

        // Status panel info
        document.getElementById('infoUsers').textContent = data.total_users;
        document.getElementById('infoAdmins').textContent = data.total_admins;
        document.getElementById('infoSessions').textContent = data.total_logins;
    } catch (e) { console.error('Stats error:', e); }
}

// ── Active users ──
async function loadActiveUsers() {
    try {
        const res = await fetch('/admin/active-users?minutes=30');
        const data = await res.json();
        allActive = data.active_users || [];

        const el = document.getElementById('overviewActiveUsers');
        if (!allActive.length) {
            el.innerHTML = '<div style="text-align:center;color:var(--muted);padding:30px;font-size:12px;">No active users right now.</div>';
            return;
        }
        el.innerHTML = allActive.map(u => `
                <div class="active-user-row">
                    <div class="user-dot">${(u.name || u.email)[0].toUpperCase()}</div>
                    <div class="user-row-info">
                        <div class="user-row-name">${u.name || u.email}</div>
                        <div class="user-row-email">${u.email}</div>
                    </div>
                    <div class="user-row-time">${u.last_seen?.slice(11, 16) || ''}</div>
                </div>
            `).join('');
    } catch (e) { }
}

// ── Overview recent activity ──
async function loadOverviewActivity() {
    try {
        const res = await fetch('/admin/activity?limit=10');
        const data = await res.json();
        const log = data.log || [];
        const el = document.getElementById('overviewRecentActivity');
        if (!log.length) {
            el.innerHTML = '<div style="text-align:center;color:var(--muted);padding:30px;font-size:12px;">No recent activity.</div>';
            return;
        }
        el.innerHTML = log.map(a => `
                <div class="log-row">
                    <span class="log-action la-${a.action} la-default">${a.action.replace(/_/g, ' ')}</span>
                    <span class="log-email">${a.email.split('@')[0]}</span>
                    <span class="log-time">${a.logged_at?.slice(11, 16) || ''}</span>
                </div>
            `).join('');
    } catch (e) { }
}

// ── Users ──
async function loadUsers() {
    try {
        const res = await fetch('/admin/users');
        const data = await res.json();
        allUsers = data.users || [];
        renderUsers();
    } catch (e) { }
}

function renderUsers() {
    const tbody = document.getElementById('userTableBody');
    if (!allUsers.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:40px;">No users found.</td></tr>';
        return;
    }
    tbody.innerHTML = allUsers.map(u => `
            <tr>
                <td style="font-weight:500;">${u.name}</td>
                <td style="font-family:var(--mono);font-size:11px;color:var(--muted);">${u.email}</td>
                <td><span class="badge ${u.is_admin ? 'badge-admin' : 'badge-user'}">${u.is_admin ? 'admin' : 'user'}</span></td>
                <td style="font-family:var(--mono);">${u.sessions || 0}</td>
                <td style="color:var(--muted);font-size:11px;font-family:var(--mono);">${u.created_at?.slice(0, 10) || '—'}</td>
                <td>
                    <button class="action-btn" onclick="viewUserActivity('${u.email}')">Logs</button>
                    ${u.is_admin
            ? `<button class="action-btn" onclick="removeAdmin('${u.email}')">Demote</button>`
            : `<button class="action-btn" onclick="makeAdmin('${u.email}')">Promote</button>`
        }
                    <button class="action-btn danger" onclick="deleteUser('${u.email}','${u.name}')">Delete</button>
                </td>
            </tr>
        `).join('');
}

// ── Activity ──
async function loadActivity() {
    try {
        const res = await fetch('/admin/activity?limit=200');
        const data = await res.json();
        allActivity = data.log || [];
        renderActivity(allActivity);
        document.getElementById('infoLogs').textContent = allActivity.length;
    } catch (e) { }
}

function renderActivity(log) {
    const el = document.getElementById('activityList');
    if (!log.length) {
        el.innerHTML = '<div style="text-align:center;color:var(--muted);padding:40px;font-size:12px;">No activity found.</div>';
        return;
    }
    el.innerHTML = log.map(a => `
            <div class="log-row">
                <span class="log-action la-${a.action}" style="text-transform:capitalize;">
                    ${a.action.replace(/_/g, ' ')}
                </span>
                <span class="log-email">${a.email}</span>
                <span class="log-detail">${a.detail || '—'}</span>
                <span class="log-time">${a.logged_at || ''}</span>
            </div>
        `).join('');
}

function applyFilters() {
    const emailF = document.getElementById('fEmail').value.toLowerCase();
    const actionF = document.getElementById('fAction').value;
    renderActivity(allActivity.filter(a =>
        (!emailF || a.email.includes(emailF)) &&
        (!actionF || a.action === actionF)
    ));
}

function viewUserActivity(email) {
    showPanel('activity', document.querySelectorAll('.nav-item')[2]);
    document.getElementById('fEmail').value = email;
    loadActivity().then(applyFilters);
}

// ── API Usage ──
async function loadApiUsage() {
    try {
        const res = await fetch('/admin/api-usage');
        const data = await res.json();
        apiUsage = data.usage || {};
        renderApiUsage();
    } catch (e) { }
}

function renderApiUsage() {
    const entries = Object.entries(apiUsage).sort((a, b) => b[1] - a[1]);
    const total = entries.reduce((s, [, v]) => s + v, 0);
    const barsEl = document.getElementById('apiUsageBars');
    const topEl = document.getElementById('apiTopActions');
    const rawBody = document.getElementById('apiRawBody');

    if (!entries.length) {
        barsEl.innerHTML = topEl.innerHTML = '<div style="color:var(--muted);font-size:12px;text-align:center;padding:20px;">No data</div>';
        return;
    }

    // Bars
    barsEl.innerHTML = entries.slice(0, 8).map(([action, count]) => `
            <div class="api-row">
                <span class="api-label">${action.replace(/_/g, ' ')}</span>
                <div class="api-bar-bg">
                    <div class="api-bar-fill" style="width:${Math.round(count / entries[0][1] * 100)}%"></div>
                </div>
                <span class="api-count">${count}</span>
            </div>
        `).join('');

    // Top 5 cards
    const colors = ['var(--accent)', 'var(--info)', 'var(--success)', '#818cf8', '#fbbf24'];
    topEl.innerHTML = entries.slice(0, 5).map(([action, count], i) => `
            <div style="display:flex;align-items:center;justify-content:space-between;
                        padding:10px 0;border-bottom:1px solid rgba(255,180,50,0.05);">
                <div>
                    <div style="font-size:13px;font-weight:500;color:${colors[i]}">
                        #${i + 1} ${action.replace(/_/g, ' ')}
                    </div>
                    <div style="font-size:10px;color:var(--muted);font-family:var(--mono);">
                        ${Math.round(count / total * 100)}% of all actions
                    </div>
                </div>
                <div style="font-family:var(--mono);font-size:18px;font-weight:700;color:${colors[i]}">${count}</div>
            </div>
        `).join('');

    // Raw table
    rawBody.innerHTML = entries.map(([action, count]) => `
            <tr>
                <td style="font-family:var(--mono);">${action}</td>
                <td style="font-family:var(--mono);font-weight:700;">${count}</td>
                <td style="color:var(--muted);font-family:var(--mono);">${Math.round(count / total * 100)}%</td>
                <td><div style="height:4px;width:${Math.round(count / entries[0][1] * 80)}px;
                    background:var(--accent);border-radius:2px;"></div></td>
            </tr>
        `).join('');
}

// ── Errors ──
async function loadErrors() {
    try {
        const res = await fetch('/admin/error-logs');
        const data = await res.json();
        allErrors = data.errors || [];

        // Also get pin fails from activity
        const res2 = await fetch('/admin/activity?limit=10000');
        const data2 = await res2.json();
        const log = data2.log || [];
        const pinFails = log.filter(l => l.action === 'pin_failed');

        // Stats
        document.getElementById('eTotal').textContent = allErrors.length;
        document.getElementById('ePinFails').textContent = pinFails.length;
        document.getElementById('pinFailCount').textContent = pinFails.length;

        // Last 24h errors
        const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 19).replace('T', ' ');
        const recent = allErrors.filter(e => (e.logged_at || '') > yesterday);
        document.getElementById('eRecent').textContent = recent.length;

        // Error list
        const errEl = document.getElementById('errorList');
        if (!allErrors.length) {
            errEl.innerHTML = '<div style="text-align:center;color:var(--success);padding:30px;font-size:12px;">✓ No errors found</div>';
        } else {
            errEl.innerHTML = allErrors.map(e => `
                    <div class="error-row">
                        <span class="error-icon">⚠️</span>
                        <div class="error-body">
                            <div class="error-msg">${e.action}: ${e.detail || 'no detail'}</div>
                            <div class="error-meta">${e.email} · ${e.logged_at}</div>
                        </div>
                    </div>
                `).join('');
        }

        // PIN fails list
        const pfEl = document.getElementById('pinFailList');
        if (!pinFails.length) {
            pfEl.innerHTML = '<div style="text-align:center;color:var(--success);padding:20px;font-size:12px;">✓ No PIN failures</div>';
        } else {
            pfEl.innerHTML = pinFails.map(p => `
                    <div class="log-row">
                        <span class="log-action la-pin_failed">pin failed</span>
                        <span class="log-email">${p.email}</span>
                        <span class="log-detail">${p.detail || '—'}</span>
                        <span class="log-time">${p.logged_at || ''}</span>
                    </div>
                `).join('');
        }
    } catch (e) { console.error('Errors load error:', e); }
}

// ── Status ──
function refreshStatus() {
    fetch('/admin/stats').then(r => r.json()).then(data => {
        document.getElementById('statusUserDB').textContent = '● Online';
        document.getElementById('statusAdminDB').textContent = '● Online';
        document.getElementById('infoUsers').textContent = data.total_users;
        document.getElementById('infoAdmins').textContent = data.total_admins;
        document.getElementById('infoSessions').textContent = data.total_logins;
    }).catch(() => {
        document.getElementById('statusUserDB').textContent = '● Error';
        document.getElementById('statusAdminDB').textContent = '● Error';
    });
}

// ── Admin actions ──
async function makeAdmin(email) {
    if (!confirm(`Promote ${email} to admin?`)) return;
    const res = await fetch('/admin/add-admin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
    const data = await res.json();
    if (data.status === 'success') loadUsers();
    else alert('Error: ' + data.message);
}

async function removeAdmin(email) {
    if (!confirm(`Remove admin from ${email}?`)) return;
    const res = await fetch('/admin/remove-admin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
    const data = await res.json();
    if (data.status === 'success') loadUsers();
    else alert('Error: ' + data.message);
}

async function deleteUser(email, name) {
    if (!confirm(`Delete "${name}" (${email})?\n\nThis is permanent.`)) return;
    const res = await fetch('/admin/delete-user', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
    const data = await res.json();
    if (data.status === 'success') { loadUsers(); loadStats(); }
    else alert('Error: ' + data.message);
}

// ── Refresh all ──
function refreshAll() {
    loadStats();
    loadActiveUsers();
    loadOverviewActivity();
}

// ── Auto refresh ──
setInterval(loadStats, 30000);
setInterval(loadActiveUsers, 15000);
setInterval(loadOverviewActivity, 10000);

// ── Init ──
refreshAll();

// ── Live Feed ──
let adminFeedIndex = 0;

async function pollAdminFeed() {
    try {
        const res = await fetch(`/api/feed?since=${adminFeedIndex}`);
        const data = await res.json();
        if (!data.entries || !data.entries.length) return;

        const feed = document.getElementById('adminConvFeed');
        if (!feed) return;

        const empty = feed.querySelector('[style*="padding:30px"]');
        if (empty) empty.remove();

        for (const entry of data.entries) {
            const isUser = /^\[user\]/i.test(entry.text);
            const isTg = /^\[telegram\]/i.test(entry.text);
            const role = isUser ? 'user' : isTg ? 'telegram' : 'system';

            const colors = {
                user: 'var(--accent)',
                telegram: 'var(--info)',
                system: 'var(--muted)',
            };
            const labels = { user: 'User', telegram: 'Telegram', system: 'Assistant' };

            const text = entry.text
                .replace(/^\[System\]:\s*/i, '')
                .replace(/^\[User\]:\s*/i, '')
                .replace(/^\[Telegram\]:\s*/i, '');

            const row = document.createElement('div');
            row.style.cssText = `display:flex;gap:8px;align-items:flex-start;font-size:12px;`;
            row.innerHTML = `
                <span style="color:${colors[role]};font-weight:600;min-width:64px;flex-shrink:0;">
                    ${labels[role]}
                </span>
                <span style="color:var(--text);flex:1;line-height:1.5;">${text}</span>
                <span style="color:var(--muted);font-size:10px;flex-shrink:0;">${entry.time || ''}</span>
            `;
            feed.appendChild(row);
        }

        adminFeedIndex = data.next_index;
        feed.scrollTop = feed.scrollHeight;
    } catch (e) { }
}

function clearAdminFeed() {
    const feed = document.getElementById('adminConvFeed');
    if (feed) feed.innerHTML = '<div style="text-align:center;color:var(--muted);font-size:12px;padding:30px;">Conversation will appear here...</div>';
    adminFeedIndex = 0;
    fetch('/api/feed/clear', { method: 'POST' }).catch(() => { });
}

setInterval(pollAdminFeed, 800);

// ── Voice Navigation ──────────────────────────────────────────
async function pollAdminNavCommands() {
    try {
        const res = await fetch('/api/nav_command');
        const data = await res.json();
        if (!data.command) return;
        const cmd = data.command.toLowerCase();

        const navItems = document.querySelectorAll('nav .nav-item');

        if (cmd.includes('overview') || cmd.includes('home')) {
            showPanel('overview', navItems[0]);
        } else if (cmd.includes('users panel') || cmd.includes('go to users') || cmd.includes('open users')) {
            showPanel('users', navItems[1]);
        } else if (cmd.includes('activity')) {
            showPanel('activity', navItems[2]);
        } else if (cmd.includes('api')) {
            showPanel('api', navItems[3]);
        } else if (cmd.includes('error')) {
            showPanel('errors', navItems[4]);
        } else if (cmd.includes('system status') || cmd.includes('status')) {
            showPanel('status', navItems[5]);
        } else if (cmd.includes('user dashboard')) {
            window.location.href = '/dashboard';
        }
    } catch (e) { }
}

setInterval(pollAdminNavCommands, 600);

// ── Detect voice logout ──────────────────────────────────────
async function checkAdminLogoutStatus() {
    try {
        const res = await fetch('/check-session');
        const data = await res.json();
        if (!data.logged_in) {
            if (window.opener || window.history.length <= 1) {
                window.close();
                setTimeout(() => { window.location.href = '/'; }, 500);
            } else {
                window.location.href = '/';
            }
        }
    } catch (e) { }
}
setInterval(checkAdminLogoutStatus, 2000);

// ─── ADMIN PROFILE ACTIONS ──────────────────────────
async function updateAdminName() {
    const name = document.getElementById('adminNewName').value.trim();
    if (!name) return alert('Please enter a name');
    try {
        const res = await fetch('/update-profile-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        alert(data.message);
        if (data.status === 'success') location.reload();
    } catch (e) { alert('Failed to update name'); }
}

async function updateAdminPassword() {
    const old_password = document.getElementById('adminOldPass').value;
    const new_password = document.getElementById('adminNewPass').value;
    if (!old_password || !new_password) return alert('Fill both fields');
    try {
        const res = await fetch('/update-profile-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password, new_password })
        });
        const data = await res.json();
        alert(data.message);
    } catch (e) { alert('Failed to update password'); }
}

async function updateAdminAudio() {
    const audio_password = document.getElementById('adminNewAudio').value.trim();
    if (!audio_password) return alert('Enter audio password');
    try {
        const res = await fetch('/update-profile-audio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audio_password })
        });
        const data = await res.json();
        alert(data.message);
    } catch (e) { alert('Failed to update audio password'); }
}