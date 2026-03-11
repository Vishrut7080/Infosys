// ─── PAGE NAV ──────────────────────────────────────
function showPage(id, el) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('page-' + id).classList.add('active');
    if (el) el.classList.add('active');
    if (id === 'inbox') loadInbox();  // ← add this
}

// ─── USER INFO ─────────────────────────────────────
const userData = {
    name: document.getElementById('sidebarName').textContent.trim() || 'User',
    email: document.getElementById('sidebarEmail').textContent.trim() || ''
};
const initial = userData.name.charAt(0).toUpperCase();
document.getElementById('avatarInitial').textContent = initial;
document.getElementById('profileName').textContent = userData.name;
document.getElementById('profileEmail').textContent = userData.email;

// ─── STATS (mock — replace with real API if needed) ─
// setTimeout(() => {
//     document.getElementById('statEmails').textContent = '24';
//     document.getElementById('statCommands').textContent = '12';
//     document.getElementById('statSessions').textContent = '7';
// }, 400);

// ─── VOICE COMMAND ─────────────────────────────────
let voiceActive = false;
function startVoice() {
    voiceActive = true;
    document.getElementById('waveform').classList.add('active');
    const status = document.getElementById('voiceStatus');
    status.classList.add('listening');
    status.innerHTML = '<span class="status-dot"></span> Listening...';
}
function stopVoice() {
    voiceActive = false;
    document.getElementById('waveform').classList.remove('active');
    const status = document.getElementById('voiceStatus');
    status.classList.remove('listening');
    status.innerHTML = '🎧 Listening for your command...';
}

// ─── SERVICES (from /get-services) ─────────────────
async function loadServices() {
    try {
        const res = await fetch('/get-services');
        const data = await res.json();
        const services = data.services || [];
        document.getElementById('profileServices').textContent =
            services.length ? services.join(', ') : 'None connected';
        document.querySelectorAll('.service-checkbox').forEach(cb => {
            cb.checked = services.includes(cb.value);
        });
    } catch (e) { }
}
loadServices();

async function loadStats() {
    try {
        const res = await fetch('/get-stats');
        const data = await res.json();
        document.getElementById('statEmails').textContent = data.emails ?? '—';
        document.getElementById('statCommands').textContent = data.commands ?? '—';
        document.getElementById('statSessions').textContent = data.sessions ?? '—';
    } catch (e) {
        ['statEmails', 'statCommands', 'statSessions'].forEach(id => {
            document.getElementById(id).textContent = '—';
        });
    }
}
loadStats();

async function saveServices() {
    const services = Array.from(
        document.querySelectorAll('.service-checkbox:checked')
    ).map(cb => cb.value);
    try {
        await fetch('/select-services', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ services })
        });
        document.getElementById('profileServices').textContent =
            services.length ? services.join(', ') : 'None connected';
        alert('Services saved: ' + (services.join(', ') || 'none'));
    } catch (e) {
        alert('Failed to save services.');
    }
}

// ─── INBOX─
let allMessages = [];
let currentFilter = 'all';

async function loadInbox() {
    const list = document.getElementById('msgList');
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div>Loading...</div>`;
    try {
        const res = await fetch('/get-inbox');
        const data = await res.json();
        allMessages = data.messages || [];
        renderInbox();
    } catch (e) {
        list.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div>Failed to load.</div>`;
    }
}

function filterInbox(type, el) {
    currentFilter = type;
    document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    renderInbox();
}

function renderInbox() {
    const list = document.getElementById('msgList');
    const filtered = currentFilter === 'all'
        ? allMessages
        : allMessages.filter(m => m.source === currentFilter);
    if (!filtered.length) {
        list.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div>No ${currentFilter} messages.</div>`;
        return;
    }
    list.innerHTML = filtered.map(m => `
        <div class="msg-card">
            <span class="msg-source-badge badge-${m.source}">${m.source}</span>
            <div class="msg-body">
                <div class="msg-route"><strong>${m.from}</strong> → ${m.to}</div>
                <div class="msg-text">${m.text}</div>
                <div class="msg-dir">${m.dir}</div>
            </div>
            <div class="msg-time">${m.time}</div>
        </div>
    `).join('');
}