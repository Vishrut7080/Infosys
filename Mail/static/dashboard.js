// ─────────────────────────────────────────────────────────────
//  dashboard.js  —  VoiceMail AI
//  Handles: page nav, user info, stats, waveform always-on,
//  live conversation feed, audio navigation, service pills
// ─────────────────────────────────────────────────────────────

// ─── PAGE NAV ─────────────────────────────────────────────────
function showPage(id, el) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('page-' + id).classList.add('active');
    if (el) el.classList.add('active');
    if (id === 'inbox') loadInbox();
}

// ─── USER INFO ────────────────────────────────────────────────
const userData = {
    name: document.getElementById('sidebarName')?.textContent.trim() || 'User',
    email: document.getElementById('sidebarEmail')?.textContent.trim() || ''
};
const initial = userData.name.charAt(0).toUpperCase();
const avatarEl = document.getElementById('avatarInitial');
if (avatarEl) avatarEl.textContent = initial;
const profileNameEl = document.getElementById('profileName');
if (profileNameEl) profileNameEl.textContent = userData.name;
const profileEmailEl = document.getElementById('profileEmail');
if (profileEmailEl) profileEmailEl.textContent = userData.email;

// ─── STATS ────────────────────────────────────────────────────
async function loadStats() {
    try {
        const res = await fetch('/get-stats');
        const data = await res.json();
        document.getElementById('statEmails').textContent = data.emails ?? '—';
        document.getElementById('statCommands').textContent = data.commands ?? '—';
        document.getElementById('statSessions').textContent = data.sessions ?? '—';
    } catch (e) {
        ['statEmails', 'statCommands', 'statSessions'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = '—';
        });
    }
}
loadStats();

// ─── WAVEFORM — always animated (system is always listening) ──
// The waveform is always "active" — it reflects that the system
// is perpetually listening, not a manual start/stop.
window.addEventListener('DOMContentLoaded', () => {
    const wf = document.getElementById('waveform');
    if (wf) wf.classList.add('active');
});

// ─────────────────────────────────────────────────────────────
//  CONVERSATION FEED
//  Polls /api/feed every 800ms. Appends new entries as chat
//  bubbles. Distinguishes [User] / [System] / [Telegram] roles
//  by their prefix in the text string.
// ─────────────────────────────────────────────────────────────
let lastFeedIndex = 0;

function getRoleFromText(text) {
    if (/^\[user\]/i.test(text)) return 'user';
    if (/^\[telegram\]/i.test(text)) return 'telegram';
    return 'system';
}

function appendFeedMessage(entry) {
    const feed = document.getElementById('convFeed');
    if (!feed) return;

    // Remove placeholder if present
    const empty = feed.querySelector('.feed-empty');
    if (empty) empty.remove();

    const role = getRoleFromText(entry.text);

    const div = document.createElement('div');
    div.className = `feed-msg feed-${role}`;

    const label = document.createElement('span');
    label.className = 'feed-label';
    label.textContent = role === 'user' ? 'You' : role === 'telegram' ? 'Telegram' : 'Assistant';

    const text = document.createElement('span');
    text.className = 'feed-text';
    text.textContent = entry.text
        .replace(/^\[System\]:\s*/i, '')
        .replace(/^\[User\]:\s*/i, '')
        .replace(/^\[Telegram\]:\s*/i, '');

    const time = document.createElement('span');
    time.className = 'feed-time';
    time.textContent = entry.time || '';

    div.appendChild(label);
    div.appendChild(text);
    div.appendChild(time);
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

async function pollFeed() {
    try {
        const res = await fetch(`/api/feed?since=${lastFeedIndex}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.entries && data.entries.length > 0) {
            data.entries.forEach(appendFeedMessage);
            lastFeedIndex = data.next_index;
        }
    } catch (e) { }
}

function clearFeed() {
    const feed = document.getElementById('convFeed');
    if (feed) feed.innerHTML = '<div class="feed-empty">Conversation will appear here…</div>';
    lastFeedIndex = 0;
    fetch('/api/feed/clear', { method: 'POST' }).catch(() => { });
}

setInterval(pollFeed, 800);

// ─────────────────────────────────────────────────────────────
//  SERVICE STATUS PILLS
//  Polls /get-services every 2s. Shows/hides Gmail/Telegram
//  pills in the sidebar and keeps profile checkboxes in sync.
// ─────────────────────────────────────────────────────────────
async function pollServices() {
    try {
        const res = await fetch('/get-services');
        const data = await res.json();
        const services = data.services || [];

        // Sidebar pills
        const pillGmail = document.getElementById('pill-gmail');
        const pillTelegram = document.getElementById('pill-telegram');
        const pillWhatsapp = document.getElementById('pill-whatsapp');
        if (pillGmail) pillGmail.style.display = services.includes('gmail') ? 'flex' : 'none';
        if (pillTelegram) pillTelegram.style.display = services.includes('telegram') ? 'flex' : 'none';
        if (pillWhatsapp) pillWhatsapp.style.display = services.includes('whatsapp') ? 'flex' : 'none';
        const chkW = document.getElementById('chk-whatsapp');
        if (chkW) chkW.checked = services.includes('whatsapp');

        // Profile checkboxes
        const chkG = document.getElementById('chk-gmail');
        const chkT = document.getElementById('chk-telegram');
        if (chkG) chkG.checked = services.includes('gmail');
        if (chkT) chkT.checked = services.includes('telegram');

        // Profile "Connected Services" field
        const ps = document.getElementById('profileServices');
        if (ps) {
            ps.textContent = services.length
                ? services.map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(', ')
                : 'None connected';
        }
    } catch (e) { }
}

setInterval(pollServices, 2000);
pollServices();

// ─────────────────────────────────────────────────────────────
//  SAVE SERVICES
// ─────────────────────────────────────────────────────────────
async function saveServices() {
    const selected = [...document.querySelectorAll('.service-checkbox:checked')].map(c => c.value);
    if (window.VoiceAILoader) VoiceAILoader.show('Connecting');
    try {
        await fetch('/select-services', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ services: selected })
        });
    } catch (e) { }
    if (window.VoiceAILoader) VoiceAILoader.hide(400);
    showServiceMsg(selected.length ? `Connected: ${selected.join(', ')}` : 'No services selected');
    pollServices();
}

function showServiceMsg(msg) {
    const el = document.getElementById('serviceMsg');
    if (el) { el.textContent = msg; setTimeout(() => { el.textContent = ''; }, 3000); }
}

// ─────────────────────────────────────────────────────────────
//  AUDIO NAVIGATION + AUDIO SERVICE SELECTION
//  Polls /api/nav_command every 600ms.
//  main.py pushes the raw heard text; we parse it here.
// ─────────────────────────────────────────────────────────────
async function pollNavCommands() {
    try {
        const res = await fetch('/api/nav_command');
        const data = await res.json();
        if (!data.command) return;
        const cmd = data.command.toLowerCase();

        // ── Page navigation ──
        const navItems = document.querySelectorAll('.nav-item');
        if (cmd.includes('dashboard') || cmd.includes('home')) {
            showPage('dashboard', navItems[0]);
        } else if (cmd.includes('profile')) {
            showPage('profile', navItems[1]);
        } else if (cmd.includes('inbox') || cmd.includes('messages') || cmd.includes('unified')) {
            showPage('inbox', navItems[2]);
        }

        // ── Service selection ──
        if (cmd.includes('select gmail') || cmd.includes('enable gmail') || cmd.includes('add gmail')) {
            const el = document.getElementById('chk-gmail');
            if (el) { el.checked = true; saveServices(); showServiceMsg('Gmail connected ✓'); }
        }
        if (cmd.includes('select telegram') || cmd.includes('enable telegram') || cmd.includes('add telegram')) {
            const el = document.getElementById('chk-telegram');
            if (el) { el.checked = true; saveServices(); showServiceMsg('Telegram connected ✓'); }
        }
        if (cmd.includes('select whatsapp') || cmd.includes('enable whatsapp') || cmd.includes('add whatsapp')) {
            const el = document.getElementById('chk-whatsapp');
            if (el) { el.checked = true; saveServices(); showServiceMsg('WhatsApp connected ✓'); }
        }
        if (cmd.includes('deselect whatsapp') || cmd.includes('disable whatsapp') || cmd.includes('remove whatsapp')) {
            const el = document.getElementById('chk-whatsapp');
            if (el) { el.checked = false; showServiceMsg('WhatsApp removed'); }
        }
        // Update the "select both" block to include whatsapp:
        if (cmd.includes('select all') || cmd.includes('enable all') || cmd.includes('all services')) {
            ['chk-gmail', 'chk-telegram', 'chk-whatsapp'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.checked = true;
            });
            saveServices();
            showServiceMsg('All services connected ✓');
        }
        // ★ Select BOTH at once
        if (cmd.includes('select both') || cmd.includes('enable both') || (cmd.includes('gmail') && cmd.includes('telegram'))) {
            const g = document.getElementById('chk-gmail');
            const t = document.getElementById('chk-telegram');
            if (g) g.checked = true;
            if (t) t.checked = true;
            saveServices();
            showServiceMsg('Gmail + Telegram connected ✓');
        }
        if (cmd.includes('deselect gmail') || cmd.includes('disable gmail') || cmd.includes('remove gmail')) {
            const el = document.getElementById('chk-gmail');
            if (el) { el.checked = false; showServiceMsg('Gmail removed'); }
        }
        if (cmd.includes('deselect telegram') || cmd.includes('disable telegram') || cmd.includes('remove telegram')) {
            const el = document.getElementById('chk-telegram');
            if (el) { el.checked = false; showServiceMsg('Telegram removed'); }
        }
        if (cmd.includes('save services') || cmd.includes('confirm services') || cmd.includes('save and continue')) {
            saveServices();
        }

    } catch (e) { }
}

setInterval(pollNavCommands, 600);

// ─────────────────────────────────────────────────────────────
//  UNIFIED INBOX
// ─────────────────────────────────────────────────────────────
let allMessages = [];
let currentFilter = 'all';

async function loadInbox() {
    const list = document.getElementById('msgList');
    if (!list) return;
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div>Loading...</div>';
    try {
        const res = await fetch('/get-inbox');
        const data = await res.json();
        allMessages = data.messages || [];
        renderInbox();
    } catch (e) {
        list.innerHTML = '<div class="empty-state"><div class="empty-icon">❌</div>Failed to load.</div>';
    }
}

function filterInbox(type, el) {
    currentFilter = type;
    document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
    if (el) el.classList.add('active');
    renderInbox();
}

function renderInbox() {
    const list = document.getElementById('msgList');
    if (!list) return;
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
                <div class="msg-route"><strong>${m.from}</strong> → ${m.to || 'Me'}</div>
                <div class="msg-text">${m.text}</div>
                <div class="msg-dir">${m.dir || ''}</div>
            </div>
            <div class="msg-time">${m.time || ''}</div>
        </div>
    `).join('');
}

// ─────────────────────────────────────────────────────────────
//  TYPING NOTIFICATION  (pauses voice loop in main.py)
// ─────────────────────────────────────────────────────────────
function notifyTyping(isTyping) {
    fetch('/typing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ typing: isTyping })
    }).catch(() => { });
}

document.addEventListener('focusin', e => { if (e.target.tagName === 'INPUT') notifyTyping(true); });
document.addEventListener('focusout', e => { if (e.target.tagName === 'INPUT') notifyTyping(false); });