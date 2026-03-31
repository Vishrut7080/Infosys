// ─────────────────────────────────────────────────────────────
//  dashboard.js  —  VoiceMail AI
//  Handles: page nav, user info, stats, waveform, live feed,
//  audio navigation, service pills, Hindi/English support
// ─────────────────────────────────────────────────────────────

// ─── PAGE NAV ─────────────────────────────────────────────────
function showPage(id, el) {
    const chatPanel = document.getElementById('chatPanel');
    const voiceRightSlot = document.getElementById('voiceRightSlot');
    const chatSidebarSlot = document.getElementById('chatSidebarSlot');

    const targetPage = document.getElementById('page-' + id);
    if (!targetPage) {
        console.warn(`[showPage] Target page "page-${id}" not found.`);
        return;
    }

    // Determine whether the chat panel is actually moving this transition
    const currentlyOnDashboard = chatPanel && voiceRightSlot && voiceRightSlot.contains(chatPanel);
    const goingToDashboard = id === 'dashboard';
    const panelIsMoving = !!chatPanel && (currentlyOnDashboard !== goingToDashboard);

    // Only give the panel a named transition when it's physically relocating.
    // When it stays fixed in the sidebar, name=none makes it part of the frozen
    // chat-sidebar snapshot instead of triggering its own animation.
    if (chatPanel) {
        chatPanel.style.viewTransitionName = panelIsMoving ? 'chat-panel' : 'none';
    }

    const fn = () => {
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.getElementById('page-' + id).classList.add('active');
        if (el) el.classList.add('active');
        if (id === 'inbox') loadInbox();

        if (!chatPanel || !voiceRightSlot || !chatSidebarSlot) return;

        if (goingToDashboard) {
            if (chatPanel.parentElement !== voiceRightSlot) {
                voiceRightSlot.appendChild(chatPanel);
            }
            chatSidebarSlot.style.display = 'none';
            document.body.classList.remove('chat-sidebar-open');
        } else {
            chatSidebarSlot.style.display = 'flex';
            if (chatPanel.parentElement !== chatSidebarSlot) {
                chatSidebarSlot.appendChild(chatPanel);
            }
            document.body.classList.add('chat-sidebar-open');
        }
    };

    if (document.startViewTransition) {
        const t = document.startViewTransition(fn);
        // After morph completes, freeze name so on the NEXT nav it's part of the sidebar snapshot
        if (panelIsMoving && chatPanel) {
            t.finished.then(() => { chatPanel.style.viewTransitionName = 'none'; });
        }
    } else {
        fn();
        if (chatPanel) chatPanel.style.viewTransitionName = 'none';
    }
}

// ── HTML Escaping (prevent XSS) ──
function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// ─── USER INFO ────────────────────────────────────────────────
const userData = {
    name: document.getElementById('sidebarName')?.textContent.trim() || 'User',
    email: document.getElementById('sidebarEmail')?.textContent.trim() || '',
};
const initial = userData.name.charAt(0).toUpperCase();
const avatarEl = document.getElementById('avatarInitial');
if (avatarEl) avatarEl.textContent = initial;
const profileNameEl = document.getElementById('profileName');
if (profileNameEl) profileNameEl.textContent = userData.name;
const profileEmailEl = document.getElementById('profileEmail');
if (profileEmailEl) profileEmailEl.textContent = userData.email;

async function loadMyPins() {
    try {
        const res = await fetch('/api/my-pins');
        const data = await res.json();
        const gmailPinEl = document.getElementById('gmailPinValue');
        const tgPinEl = document.getElementById('telegramPinValue');
        if (gmailPinEl) gmailPinEl.textContent = data.gmail_pin || '—';
        if (tgPinEl) tgPinEl.textContent = data.telegram_pin || '—';
    } catch { }
}
loadMyPins();

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

// ─── ADMIN STATUS — show admin command group if user is admin ──
async function refreshUserAndRole() {
    try {
        const res = await fetch('/get-user-info');
        const data = await res.json();

        if (data.name) {
            const nameEl = document.getElementById('sidebarName');
            const avatarEl = document.getElementById('avatarInitial');
            const pNameEl = document.getElementById('profileName');
            const pEmailEl = document.getElementById('profileEmail');
            if (nameEl) nameEl.textContent = data.name;
            if (avatarEl) avatarEl.textContent = data.name.charAt(0).toUpperCase();
            if (pNameEl) pNameEl.textContent = data.name;
            if (pEmailEl) pEmailEl.textContent = data.email;
        }

        if (data.is_admin) {
            const el = document.getElementById('cmdAdminGroup');
            if (el) el.style.display = 'flex';
            // Show admin panel link
            const adminLink = document.getElementById('adminLink');
            if (adminLink) adminLink.style.display = 'block';
        }
    } catch (e) { }

    // Update connected services
    try {
        const sRes = await fetch('/get-services');
        const sData = await sRes.json();
        const gmailPill = document.getElementById('pill-gmail');
        const tgPill = document.getElementById('pill-telegram');
        if (gmailPill) gmailPill.style.display = sData.services.includes('gmail') ? 'flex' : 'none';
        if (tgPill) tgPill.style.display = sData.services.includes('telegram') ? 'flex' : 'none';
    } catch (e) { }
}
refreshUserAndRole();
setTimeout(refreshUserAndRole, 2000);

// LLM Model Selector: load options and handle changes
async function loadLLMOptions() {
    const sel = document.getElementById('modelSelect');
    if (!sel) return;
    sel.disabled = true;
    try {
        const res = await fetch('/api/llm-options');
        if (!res.ok) throw new Error('Failed to fetch model options');
        const data = await res.json();
        sel.innerHTML = '';
        const providers = data.providers || [];
        const current = data.current || {};
        for (const p of providers) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = p.label + (p.available ? '' : ' (unavailable)');
            if (!p.available) optgroup.disabled = true;
            for (const m of (p.models || [])) {
                const opt = document.createElement('option');
                opt.value = `${p.id}|${m.id}`;
                opt.textContent = m.label;
                if (current.provider === p.id && current.model === m.id) opt.selected = true;
                optgroup.appendChild(opt);
            }
            sel.appendChild(optgroup);
        }
        if (!sel.value && providers.length) {
            const p = providers[0];
            if (p.models && p.models.length) sel.value = `${p.id}|${p.models[0].id}`;
        }
    } catch (e) {
        sel.innerHTML = '<option>Error loading models</option>';
    } finally {
        sel.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(loadLLMOptions, 200);
    const sel = document.getElementById('modelSelect');
    if (sel) {
        sel.addEventListener('change', async (ev) => {
            const val = ev.target.value;
            if (!val) return;
            const [provider, model] = val.split('|');
            try {
                const res = await fetch('/api/switch-llm', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider, model })
                });
                const j = await res.json();
                if (!res.ok) {
                    if (window.Toast) Toast.show(j.message || 'Failed to switch model', 'error');
                    loadLLMOptions();
                    return;
                }
                if (window.Toast) Toast.show(`AI switched to ${provider} — ${model}`);
            } catch (e) {
                if (window.Toast) Toast.show('Failed to switch model', 'error');
                loadLLMOptions();
            }
        });
    }
});

// ─── WAVEFORM — always animated ───────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
    // Handle OAuth redirect - reload to get fresh session state
    if (window.location.search.includes('oauth=success')) {
        window.location.replace(window.location.pathname);
        return;
    }

    const wf = document.getElementById('waveform');
    if (wf) wf.classList.add('active');
});

// ─── SERVICE STATUS POLLING ───────────────────────────────────
let servicePollingInterval = null;
let telegramCheckAttempts = 0;
let gmailAlreadyConnected = false;
const MAX_TELEGRAM_CHECKS = 15; // Check for ~45 seconds max

function updateServiceStatus(telegramReady, gmailConnected) {
    const tgStatus = document.getElementById('telegram-status');
    const tgBanner = document.getElementById('telegram-banner');
    const gmailStatus = document.getElementById('gmail-status');
    const gmailBanner = document.getElementById('gmail-banner');

    // Update Telegram status
    if (tgStatus) {
        if (telegramReady) {
            tgStatus.textContent = 'Connected';
            tgStatus.style.color = '#4ade80';
            if (tgBanner) tgBanner.style.display = 'none';
        } else if (telegramCheckAttempts < MAX_TELEGRAM_CHECKS) {
            tgStatus.textContent = 'Connecting...';
            tgStatus.style.color = '#facc15';
            if (tgBanner) tgBanner.style.display = 'none';
        } else {
            tgStatus.textContent = 'Not connected';
            tgStatus.style.color = '#f87171';
            if (tgBanner) tgBanner.style.display = 'block';
        }
    }

    // Update Gmail status - remember if it was ever connected
    if (gmailStatus && gmailConnected) {
        gmailAlreadyConnected = true;
    }
    if (gmailStatus) {
        if (gmailAlreadyConnected || gmailConnected) {
            gmailStatus.textContent = 'Connected';
            gmailStatus.style.color = '#4ade80';
            if (gmailBanner) gmailBanner.style.display = 'none';
        } else if (telegramCheckAttempts < MAX_TELEGRAM_CHECKS) {
            gmailStatus.textContent = 'Checking...';
            gmailStatus.style.color = '#facc15';
            if (gmailBanner) gmailBanner.style.display = 'none';
        } else {
            gmailStatus.textContent = 'Not connected';
            gmailStatus.style.color = '#f87171';
            if (gmailBanner) gmailBanner.style.display = 'block';
        }
    }
}

async function checkServiceStatus() {
    // Only check Telegram if we haven't given up yet
    if (telegramCheckAttempts < MAX_TELEGRAM_CHECKS) {
        telegramCheckAttempts++;
        try {
            // Check Telegram status
            const tgRes = await fetch('/telegram/status');
            const tgData = await tgRes.json();
            const tgReady = tgData.ready === true;

            // Check Gmail status
            let gmailConnected = false;
            try {
                const gmailRes = await fetch('/gmail/status');
                const gmailData = await gmailRes.json();
                gmailConnected = gmailData.ready === true;
            } catch (e) {
                // Gmail check failed, keep current status
            }

            updateServiceStatus(tgReady, gmailConnected);

            // Stop polling if Telegram is connected (Gmail status stays visible)
            if (tgReady) {
                clearInterval(servicePollingInterval);
                servicePollingInterval = null;
            }
        } catch (e) {
            console.warn('[Service Status] Error checking status:', e);
        }
    } else {
        // Max attempts reached, stop polling but still show banner
        clearInterval(servicePollingInterval);
        servicePollingInterval = null;
        const tgBanner = document.getElementById('telegram-banner');
        if (tgBanner) tgBanner.style.display = 'block';
        // Final Gmail status update and banner
        const gmailStatus = document.getElementById('gmail-status');
        const gmailBanner = document.getElementById('gmail-banner');
        if (!gmailAlreadyConnected) {
            if (gmailStatus) {
                gmailStatus.textContent = 'Not connected';
                gmailStatus.style.color = '#f87171';
            }
            if (gmailBanner) gmailBanner.style.display = 'block';
        }
    }
}

function startServicePolling() {
    if (servicePollingInterval) return;
    telegramCheckAttempts = 0;
    gmailAlreadyConnected = false;
    // Check immediately
    checkServiceStatus();
    // Then poll every 3 seconds
    servicePollingInterval = setInterval(checkServiceStatus, 3000);
}

// Start polling on page load if we're on dashboard
window.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('telegram-status')) {
        // Set initial state to "Connecting..." while we check
        const tgStatus = document.getElementById('telegram-status');
        if (tgStatus && tgStatus.textContent === 'Checking...') {
            tgStatus.textContent = 'Connecting...';
            tgStatus.style.color = '#facc15';
        }
        startServicePolling();
    }
});

// ─────────────────────────────────────────────────────────────
//  CONVERSATION FEED (driven by WebSocket events from assistant.js)
// ─────────────────────────────────────────────────────────────
function getRoleFromText(text) {
    if (/^\[user\]/i.test(text)) return 'user';
    if (/^\[telegram\]/i.test(text)) return 'telegram';
    return 'system';
}

async function appendFeedMessage(entry) {
    const feed = document.getElementById('convFeed');
    if (!feed) return;

    const empty = feed.querySelector('.feed-empty');
    if (empty) empty.remove();

    const role = getRoleFromText(entry.text);

    let displayText = entry.text
        .replace(/^\[System\]:\s*/i, '')
        .replace(/^\[User\]:\s*/i, '')
        .replace(/^\[Telegram\]:\s*/i, '');

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
    if (role === 'user') label.textContent = LangManager?.isHindi() ? 'आप' : 'You';
    else if (role === 'telegram') label.textContent = 'Telegram';
    else label.textContent = LangManager?.isHindi() ? 'असिस्टेंट' : 'Assistant';

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

function clearFeed() {
    const feed = document.getElementById('convFeed');
    if (feed) {
        const emptyText = LangManager?.isHindi()
            ? 'बातचीत यहाँ दिखाई देगी…'
            : 'Conversation will appear here…';
        feed.innerHTML = `<div class="feed-empty">${emptyText}</div>`;
    }
}

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
        if (pillGmail) pillGmail.style.display = services.includes('gmail') ? 'flex' : 'none';
        if (pillTelegram) pillTelegram.style.display = services.includes('telegram') ? 'flex' : 'none';

        const chkG = document.getElementById('chk-gmail');
        const chkT = document.getElementById('chk-telegram');
        if (chkG) chkG.checked = services.includes('gmail');
        if (chkT) chkT.checked = services.includes('telegram');

        const ps = document.getElementById('profileServices');
        if (ps) {
            ps.textContent = services.length
                ? services.map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(', ')
                : (LangManager?.isHindi() ? 'कोई सेवा नहीं' : 'None connected');
        }
    } catch (e) { }
}

setInterval(pollServices, 30000);
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
            body: JSON.stringify({ services: selected }),
        });
    } catch (e) { }
    if (window.VoiceAILoader) VoiceAILoader.hide(400);
    const msg = selected.length
        ? (LangManager?.isHindi() ? `कनेक्ट हुआ: ${selected.join(', ')}` : `Connected: ${selected.join(', ')}`)
        : (LangManager?.isHindi() ? 'कोई सेवा नहीं चुनी' : 'No services selected');
    showServiceMsg(msg);
    pollServices();
}

function showServiceMsg(msg) {
    const el = document.getElementById('serviceMsg');
    if (el) { el.textContent = msg; setTimeout(() => { el.textContent = ''; }, 3000); }
}

// ─────────────────────────────────────────────────────────────
//  CLIENT ACTIONS (NAV, OPEN URL, ETC)
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
    if (!allMessages.length) {
        loadInbox();   // triggers load + render automatically
    } else {
        renderInbox();
    }
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
            <span class="msg-source-badge badge-${escapeHtml(m.source)}">${escapeHtml(m.source)}</span>
            <div class="msg-body">
                <div class="msg-route"><strong>${escapeHtml(m.from)}</strong> → ${escapeHtml(m.to || 'Me')}</div>
                <div class="msg-text">${escapeHtml(m.text)}</div>
                <div class="msg-dir">${escapeHtml(m.dir || '')}</div>
            </div>
            <div class="msg-time">${escapeHtml(m.time || '')}</div>
        </div>
    `).join('');
}

document.addEventListener('langChanged', () => {
    if (document.getElementById('page-inbox')?.classList.contains('active')) {
        loadInbox();
    }
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
        body: JSON.stringify({ typing: isTyping }),
    }).catch(() => { });
}

// ─────────────────────────────────────────────────────────────
//  PROFILE ACTIONS
// ─────────────────────────────────────────────────────────────
async function updateNameUI() {
    const name = document.getElementById('newNameInput').value.trim();
    if (!name) return alert('Please enter a name');
    try {
        const res = await fetch('/update-profile-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        alert(data.message);
        if (data.status === 'success') refreshUserAndRole();
    } catch (e) { alert('Failed to update name'); }
}

async function updatePasswordUI() {
    const old_password = document.getElementById('oldPassInput').value;
    const new_password = document.getElementById('newPassInput').value;
    if (!old_password || !new_password) return alert('Please fill both fields');
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

async function updateAudioUI() {
    const audio_password = document.getElementById('newAudioInput').value.trim();
    if (!audio_password) return alert('Please enter an audio password');
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

async function deleteAccountUI() {
    const password = document.getElementById('deletePassInput').value;
    if (!password) return alert('Please enter your password to confirm');
    if (!confirm('Are you absolutely sure? This cannot be undone.')) return;
    try {
        const res = await fetch('/delete-profile-account', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        const data = await res.json();
        alert(data.message);
        if (data.status === 'success') window.location.href = '/';
    } catch (e) { alert('Failed to delete account'); }
}

// ─── Detect session loss via WebSocket disconnect ────────────────
// assistant.js dispatches 'session-expired' after verifying with /check-session
window.addEventListener('session-expired', () => {
    window.location.href = '/';
});

async function loadTelegramContacts() {
    const list = document.getElementById('tgContactsList');
    if (!list) return;
    list.innerHTML = '<div style="color:var(--muted);font-size:13px;">Loading...</div>';
    try {
        const res = await fetch('/telegram/contacts');
        const data = await res.json();
        const contacts = data.contacts || [];
        if (!contacts.length) {
            list.innerHTML = '<div style="color:var(--muted);font-size:13px;">No contacts found. Make sure Telegram is connected.</div>';
            return;
        }
        list.innerHTML = contacts.map(c => `
            <div style="display:flex;justify-content:space-between;align-items:center;
                        padding:8px 12px;background:rgba(255,255,255,0.04);
                        border-radius:8px;font-size:13px;">
                <div>
                    <div style="font-weight:600;color:var(--text);">${escapeHtml(c.name)}</div>
                    <div style="color:var(--muted);font-size:11px;margin-top:2px;">
                        ${escapeHtml(c.last_message) || 'No messages'}
                    </div>
                </div>
                <div style="text-align:right;flex-shrink:0;">
                    ${c.unread ? `<span style="background:var(--accent);color:#000;border-radius:10px;padding:2px 7px;font-size:10px;font-weight:700;">${c.unread}</span>` : ''}
                    <div style="color:var(--muted);font-size:10px;margin-top:4px;">${c.date}</div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        list.innerHTML = '<div style="color:var(--muted);font-size:13px;">Failed to load contacts.</div>';
    }
}

// ─────────────────────────────────────────────────────────────
//  INIT (was dashboard_init.js — merged here)
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
    },
};
window.VoiceAILoader = VoiceAILoader;

document.getElementById('logoutBtn').addEventListener('click', e => {
    e.preventDefault();
    VoiceAILoader.show(window.LangManager?.isHindi() ? 'साइन आउट हो रहा है' : 'Signing out');
    setTimeout(() => { window.location.href = '/logout'; }, 700);
});

document.addEventListener('focusin', e => { if (e.target.tagName === 'INPUT') notifyTyping(true); });
document.addEventListener('focusout', e => { if (e.target.tagName === 'INPUT') notifyTyping(false); });

// ── TASKS ─────────────────────────────────────────────────────────────────

let currentTaskFilter = 'pending';

function switchTaskFilter(btn) {
    document.querySelectorAll('.task-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentTaskFilter = btn.dataset.status;
    loadTasks();
}

async function loadTasks() {
    const list = document.getElementById('taskList');
    if (!list) return;
    list.innerHTML = '<div style="color:var(--muted);font-size:13px;">Loading…</div>';
    try {
        const res = await fetch(`/api/tasks?status=${currentTaskFilter}`);
        const data = await res.json();
        renderTasks(data.tasks || []);
    } catch {
        list.innerHTML = '<div style="color:#f87171;font-size:13px;">Error loading tasks.</div>';
    }
}

function renderTasks(tasks) {
    const list = document.getElementById('taskList');
    if (!list) return;
    if (!tasks.length) {
        const label = currentTaskFilter === 'all' ? 'tasks' : `${currentTaskFilter} tasks`;
        list.innerHTML = `<p class="empty-state">No ${label}.</p>`;
        return;
    }
    list.innerHTML = tasks.map(t => `
        <div class="task-card${t.status === 'done' ? ' done' : ''}" id="task-${t.id}">
            <div class="task-card-body">
                <div class="task-title">${escapeHtml(t.title)}</div>
                <div class="task-meta">
                    <span class="task-priority-badge ${t.priority}">${t.priority}</span>
                    ${t.source !== 'manual' ? `<span class="task-source-badge">${t.source}</span>` : ''}
                    ${t.description ? `<span>${escapeHtml(t.description)}</span>` : ''}
                    <span>${t.created_at ? t.created_at.split(' ')[0] : ''}</span>
                </div>
            </div>
            <div class="task-actions">
                ${t.status === 'pending' ? `<button class="task-btn complete" onclick="completeTaskUI(${t.id})">✓ Done</button>` : ''}
                <button class="task-btn delete" onclick="deleteTaskUI(${t.id})">✕</button>
            </div>
        </div>
    `).join('');
}

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function addTaskUI() {
    const title = document.getElementById('taskTitleInput').value.trim();
    if (!title) return;
    const description = document.getElementById('taskDescInput').value.trim();
    const priority = document.getElementById('taskPrioritySelect').value;
    const btn = document.getElementById('addTaskBtn');
    btn.disabled = true;
    try {
        const res = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, priority }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
            document.getElementById('taskTitleInput').value = '';
            document.getElementById('taskDescInput').value = '';
            document.getElementById('taskPrioritySelect').value = 'normal';
            if (currentTaskFilter === 'pending' || currentTaskFilter === 'all') loadTasks();
        } else {
            console.error('Add task failed:', data.message);
        }
    } catch (err) {
        console.error('Add task error:', err);
    } finally {
        btn.disabled = false;
    }
}

async function completeTaskUI(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/complete`, { method: 'POST' });
        loadTasks();
    } catch { /* ignore */ }
}

async function deleteTaskUI(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
        loadTasks();
    } catch { /* ignore */ }
}

// Initialize shared voice handlers for dashboard page
document.addEventListener('DOMContentLoaded', () => { if (window.VoiceNav) VoiceNav.init('dashboard'); });

