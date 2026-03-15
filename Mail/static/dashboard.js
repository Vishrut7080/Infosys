// ─────────────────────────────────────────────────────────────
//  dashboard.js  —  VoiceMail AI
//  Handles: page nav, user info, stats, waveform always-on,
//  live conversation feed, audio navigation, service pills,
//  Hindi/English translation support
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

// ─── WAVEFORM — always animated ───────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
    const wf = document.getElementById('waveform');
    if (wf) wf.classList.add('active');
});

// ─────────────────────────────────────────────────────────────
//  CONVERSATION FEED
// ─────────────────────────────────────────────────────────────
let lastFeedIndex = 0;

function getRoleFromText(text) {
    if (/^\[user\]/i.test(text)) return 'user';
    if (/^\[telegram\]/i.test(text)) return 'telegram';
    return 'system';
}

async function appendFeedMessage(entry) {
    const feed = document.getElementById('convFeed');
    if (!feed) return;

    // Remove placeholder
    const empty = feed.querySelector('.feed-empty');
    if (empty) empty.remove();

    const role = getRoleFromText(entry.text);

    // Clean prefix
    let displayText = entry.text
        .replace(/^\[System\]:\s*/i, '')
        .replace(/^\[User\]:\s*/i, '')
        .replace(/^\[Telegram\]:\s*/i, '');

    // Translate if Hindi mode active
    if (window.LangManager && LangManager.isHindi()) {
        try {
            const translated = await LangManager.translate([displayText]);
            displayText = translated[0] || displayText;
        } catch (e) { }
    }

    const div = document.createElement('div');
    div.className = `feed-msg feed-${role}`;

    const label = document.createElement('span');
    label.className = 'feed-label';
    if (role === 'user') {
        label.textContent = LangManager?.isHindi() ? 'आप' : 'You';
    } else if (role === 'telegram') {
        label.textContent = 'Telegram';
    } else {
        label.textContent = LangManager?.isHindi() ? 'असिस्टेंट' : 'Assistant';
    }

    const text = document.createElement('span');
    text.className = 'feed-text';
    text.textContent = displayText;

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
            for (const entry of data.entries) {
                await appendFeedMessage(entry);
            }
            lastFeedIndex = data.next_index;
        }
    } catch (e) { }
}

function clearFeed() {
    const feed = document.getElementById('convFeed');
    if (feed) {
        const emptyText = LangManager?.isHindi()
            ? 'बातचीत यहाँ दिखाई देगी…'
            : 'Conversation will appear here…';
        feed.innerHTML = `<div class="feed-empty">${emptyText}</div>`;
    }
    lastFeedIndex = 0;
    fetch('/api/feed/clear', { method: 'POST' }).catch(() => { });
}

setInterval(pollFeed, 800);

// ─────────────────────────────────────────────────────────────
//  SERVICE STATUS PILLS
// ─────────────────────────────────────────────────────────────
async function pollServices() {
    try {
        const res = await fetch('/get-services');
        const data = await res.json();
        const services = data.services || [];

        const pillGmail = document.getElementById('pill-gmail');
        const pillTelegram = document.getElementById('pill-telegram');
        const pillWhatsapp = document.getElementById('pill-whatsapp');
        if (pillGmail) pillGmail.style.display = services.includes('gmail') ? 'flex' : 'none';
        if (pillTelegram) pillTelegram.style.display = services.includes('telegram') ? 'flex' : 'none';
        if (pillWhatsapp) pillWhatsapp.style.display = services.includes('whatsapp') ? 'flex' : 'none';

        const chkG = document.getElementById('chk-gmail');
        const chkT = document.getElementById('chk-telegram');
        const chkW = document.getElementById('chk-whatsapp');
        if (chkG) chkG.checked = services.includes('gmail');
        if (chkT) chkT.checked = services.includes('telegram');
        if (chkW) chkW.checked = services.includes('whatsapp');

        const ps = document.getElementById('profileServices');
        if (ps) {
            if (services.length) {
                ps.textContent = services.map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(', ');
            } else {
                ps.textContent = LangManager?.isHindi() ? 'कोई सेवा नहीं' : 'None connected';
            }
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
    if (window.VoiceAILoader) VoiceAILoader.show(LangManager?.isHindi() ? 'कनेक्ट हो रहा है' : 'Connecting');
    try {
        await fetch('/select-services', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ services: selected })
        });
    } catch (e) { }
    if (window.VoiceAILoader) VoiceAILoader.hide(400);
    const msg = selected.length
        ? (LangManager?.isHindi()
            ? `कनेक्ट हुआ: ${selected.join(', ')}`
            : `Connected: ${selected.join(', ')}`)
        : (LangManager?.isHindi() ? 'कोई सेवा नहीं चुनी' : 'No services selected');
    showServiceMsg(msg);
    pollServices();
}

function showServiceMsg(msg) {
    const el = document.getElementById('serviceMsg');
    if (el) { el.textContent = msg; setTimeout(() => { el.textContent = ''; }, 3000); }
}

// ─────────────────────────────────────────────────────────────
//  AUDIO NAVIGATION
// ─────────────────────────────────────────────────────────────
async function pollNavCommands() {
    try {
        const res = await fetch('/api/nav_command');
        const data = await res.json();
        if (!data.command) return;
        const cmd = data.command.toLowerCase();

        const navItems = document.querySelectorAll('.nav-item');
        if (cmd.includes('dashboard') || cmd.includes('home')) {
            showPage('dashboard', navItems[0]);
        } else if (cmd.includes('profile')) {
            showPage('profile', navItems[1]);
        } else if (cmd.includes('inbox') || cmd.includes('messages') || cmd.includes('unified')) {
            showPage('inbox', navItems[2]);
        }

        if (cmd.includes('select gmail') || cmd.includes('enable gmail') || cmd.includes('add gmail')) {
            const el = document.getElementById('chk-gmail');
            if (el) { el.checked = true; saveServices(); showServiceMsg(LangManager?.isHindi() ? 'Gmail जोड़ा ✓' : 'Gmail connected ✓'); }
        }
        if (cmd.includes('select telegram') || cmd.includes('enable telegram') || cmd.includes('add telegram')) {
            const el = document.getElementById('chk-telegram');
            if (el) { el.checked = true; saveServices(); showServiceMsg(LangManager?.isHindi() ? 'Telegram जोड़ा ✓' : 'Telegram connected ✓'); }
        }
        if (cmd.includes('select whatsapp') || cmd.includes('enable whatsapp') || cmd.includes('add whatsapp')) {
            const el = document.getElementById('chk-whatsapp');
            if (el) { el.checked = true; saveServices(); showServiceMsg(LangManager?.isHindi() ? 'WhatsApp जोड़ा ✓' : 'WhatsApp connected ✓'); }
        }
        if (cmd.includes('deselect whatsapp') || cmd.includes('disable whatsapp') || cmd.includes('remove whatsapp')) {
            const el = document.getElementById('chk-whatsapp');
            if (el) { el.checked = false; showServiceMsg(LangManager?.isHindi() ? 'WhatsApp हटाया' : 'WhatsApp removed'); }
        }
        if (cmd.includes('select all') || cmd.includes('enable all') || cmd.includes('all services')) {
            ['chk-gmail', 'chk-telegram', 'chk-whatsapp'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.checked = true;
            });
            saveServices();
            showServiceMsg(LangManager?.isHindi() ? 'सभी सेवाएं जुड़ीं ✓' : 'All services connected ✓');
        }
        if (cmd.includes('select both') || cmd.includes('enable both') || (cmd.includes('gmail') && cmd.includes('telegram'))) {
            const g = document.getElementById('chk-gmail');
            const t = document.getElementById('chk-telegram');
            if (g) g.checked = true;
            if (t) t.checked = true;
            saveServices();
            showServiceMsg(LangManager?.isHindi() ? 'Gmail + Telegram जुड़े ✓' : 'Gmail + Telegram connected ✓');
        }
        if (cmd.includes('deselect gmail') || cmd.includes('disable gmail') || cmd.includes('remove gmail')) {
            const el = document.getElementById('chk-gmail');
            if (el) { el.checked = false; showServiceMsg(LangManager?.isHindi() ? 'Gmail हटाया' : 'Gmail removed'); }
        }
        if (cmd.includes('deselect telegram') || cmd.includes('disable telegram') || cmd.includes('remove telegram')) {
            const el = document.getElementById('chk-telegram');
            if (el) { el.checked = false; showServiceMsg(LangManager?.isHindi() ? 'Telegram हटाया' : 'Telegram removed'); }
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
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div>${LangManager?.isHindi() ? 'लोड हो रहा है...' : 'Loading...'}</div>`;
    try {
        const res = await fetch('/get-inbox');
        const data = await res.json();
        allMessages = data.messages || [];

        // Translate message content if Hindi mode
        if (window.LangManager && LangManager.isHindi() && allMessages.length) {
            for (let msg of allMessages) {
                try {
                    const translated = await LangManager.translate([msg.text, msg.from]);
                    msg.text = translated[0] || msg.text;
                    msg.from = translated[1] || msg.from;
                } catch (e) { }
            }
        }
        renderInbox();
    } catch (e) {
        list.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div>${LangManager?.isHindi() ? 'लोड नहीं हो सका।' : 'Failed to load.'}</div>`;
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
        const msg = LangManager?.isHindi()
            ? `कोई ${currentFilter === 'all' ? '' : currentFilter + ' '}संदेश नहीं।`
            : `No ${currentFilter} messages.`;
        list.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div>${msg}</div>`;
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

// Re-render inbox when language switches
document.addEventListener('langChanged', () => {
    if (document.getElementById('page-inbox')?.classList.contains('active')) {
        loadInbox();
    }
    // Update clear feed button placeholder
    const feed = document.getElementById('convFeed');
    const empty = feed?.querySelector('.feed-empty');
    if (empty) {
        empty.textContent = LangManager?.isHindi()
            ? 'बातचीत यहाँ दिखाई देगी…'
            : 'Conversation will appear here…';
    }
});

// ─────────────────────────────────────────────────────────────
//  TYPING NOTIFICATION
// ─────────────────────────────────────────────────────────────
function notifyTyping(isTyping) {
    fetch('/typing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ typing: isTyping })
    }).catch(() => { });
}

// ── Detect voice logout ──────────────────────────────────────
async function checkLogoutStatus() {
    try {
        const res = await fetch('/check-session');
        const data = await res.json();
        if (!data.logged_in) {
            window.location.href = '/';
        }
    } catch (e) { }
}
setInterval(checkLogoutStatus, 2000);

// ─────────────────────────────────────────────────────────────
//  dashboard_init.js
//  Page-level initialisation for dashboard.html.
//  Runs after dashboard.js has loaded.
// ─────────────────────────────────────────────────────────────

const VoiceAILoader = {
    el: document.getElementById('va-loader'),
    label: document.getElementById('va-label'),
    show(text = 'Loading') {
        this.label.textContent = text;
        this.el.classList.remove('va-hidden');
    },
    hide(delay = 0) {
        setTimeout(() => this.el.classList.add('va-hidden'), delay);
    }
};
window.VoiceAILoader = VoiceAILoader;

document.getElementById('logoutBtn').addEventListener('click', e => {
    e.preventDefault();
    VoiceAILoader.show(
        window.LangManager?.isHindi() ? 'साइन आउट हो रहा है' : 'Signing out'
    );
    setTimeout(() => { window.location.href = '/logout'; }, 700);
});

document.addEventListener('focusin', e => { if (e.target.tagName === 'INPUT') notifyTyping(true); });
document.addEventListener('focusout', e => { if (e.target.tagName === 'INPUT') notifyTyping(false); });