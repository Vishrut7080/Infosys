// ----------------------
// LOGIN PAGE LOGIC
// ----------------------
// Three login paths:
//   1. Gmail/Google domain      → /auth/google       (auto-detected)
//   2. Outlook/Microsoft domain → /auth/microsoft    (auto-detected)
//   3. Other email              → POST /login with password
//   4. Audio                    → main.py sets login_status → poll detects → /dashboard

const GOOGLE_DOMAINS = ['gmail.com', 'googlemail.com'];
const MICROSOFT_DOMAINS = ['outlook.com', 'hotmail.com', 'live.com', 'msn.com'];

let keyboardLoginAttempted = false;
let pollingActive = true;

// ── Auto-start audio login if arriving from signup ──────────────
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('from') === 'signup') {
    const msg = document.getElementById('message');
    if (msg) {
        msg.style.color = '#4ade80';
        msg.textContent = '🎙 Say your audio password to log in...';
    }
    keyboardLoginAttempted = false;
    pollingActive = true;
}

// ── Notify Flask on keypress — triggers audio pause ─────────────
function notifyTyping(isTyping) {
    fetch('/typing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ typing: isTyping }),
    }).catch(() => { });
}

document.querySelectorAll('input').forEach(input => {
    input.addEventListener('keydown', () => {
        keyboardLoginAttempted = true;
        notifyTyping(true);
    });
});

// ── 1. FORM SUBMIT — detect domain and route accordingly ─────────
document.getElementById('loginForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    const messageEl = document.getElementById('message');
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const domain = email.split('@')[1]?.toLowerCase();

    if (GOOGLE_DOMAINS.includes(domain)) {
        messageEl.style.color = '#8888aa';
        messageEl.innerText = 'Detected Google account. Redirecting...';
        setTimeout(() => { window.location.href = '/auth/google'; }, 700);
        return;
    }

    if (MICROSOFT_DOMAINS.includes(domain)) {
        messageEl.style.color = '#8888aa';
        messageEl.innerText = 'Detected Microsoft account. Redirecting...';
        setTimeout(() => { window.location.href = '/auth/microsoft'; }, 700);
        return;
    }

    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const result = await response.json();

        if (result.status === 'success') {
            messageEl.style.color = '#4ade80';
            messageEl.innerText = 'Login successful! Loading...';
            setTimeout(() => {
                window.location.href = result.redirect || '/dashboard';
            }, 800);
        } else {
            messageEl.style.color = '#f87171';
            messageEl.innerText = result.message || 'Login failed';
            keyboardLoginAttempted = false;
        }
    } catch (error) {
        messageEl.style.color = '#f87171';
        messageEl.innerText = 'Error connecting to server';
        console.error('Login error:', error);
    }
});

// ── 2. AUDIO LOGIN — poll /check every second ────────────────────
async function checkAudioLogin() {
    if (keyboardLoginAttempted) return;
    if (!pollingActive) return;
    if (window.location.pathname !== '/') return;

    try {
        const res = await fetch('/check');
        const data = await res.json();

        if (data.status === 'success') {
            pollingActive = false;
            window.location.href = data.redirect || '/dashboard';
        } else if (data.status === 'failed') {
            pollingActive = false;
            window.location.href = '/login-cancelled';
        }
    } catch (error) {
        console.log('Polling: server not ready yet...');
    }
}
setInterval(checkAudioLogin, 1000);

// ─────────────────────────────────────────────────────────────────
//  login_init.js  (merged inline)
// ─────────────────────────────────────────────────────────────────

// ── Password show/hide ───────────────────────────────────────────
document.getElementById('eyeBtn').addEventListener('click', () => {
    const input = document.getElementById('password');
    input.type = input.type === 'password' ? 'text' : 'password';
});

// ── Email domain hint ────────────────────────────────────────────
const emailInput = document.getElementById('email');
const hint = document.getElementById('emailHint');
const passInput = document.getElementById('password');
const googleDomains = ['gmail.com', 'googlemail.com'];
const microsoftDomains = ['outlook.com', 'hotmail.com', 'live.com', 'msn.com'];

function updateEmailHint() {
    const domain = emailInput.value.split('@')[1]?.toLowerCase();
    if (!domain) { hint.textContent = ''; passInput.required = true; return; }

    if (googleDomains.includes(domain)) {
        hint.textContent = window.LangManager?.isHindi()
            ? '→ Google से जारी रहेगा'
            : '→ Will continue with Google';
        hint.style.color = '#4285F4';
        passInput.required = false;
    } else if (microsoftDomains.includes(domain)) {
        hint.textContent = window.LangManager?.isHindi()
            ? '→ Microsoft से जारी रहेगा'
            : '→ Will continue with Microsoft';
        hint.style.color = '#00a4ef';
        passInput.required = false;
    } else {
        hint.textContent = '';
        passInput.required = true;
    }
}

emailInput.addEventListener('input', updateEmailHint);
document.addEventListener('langChanged', updateEmailHint);

// ── Loader ───────────────────────────────────────────────────────
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
window.addEventListener('load', () => VoiceAILoader.hide(600));

document.getElementById('loginForm').addEventListener('submit', () => {
    VoiceAILoader.show(
        window.LangManager?.isHindi() ? 'साइन इन हो रहा है' : 'Signing in'
    );
});

// ── Auto-trigger audio login if arriving from signup ─────────────
if (new URLSearchParams(window.location.search).get('from') === 'signup') {
    fetch('/start-audio-login', { method: 'POST' }).catch(() => { });
    const msg = document.getElementById('message');
    if (msg) {
        msg.style.color = '#4ade80';
        msg.textContent = window.LangManager?.isHindi()
            ? '🎙 अभी अपना ऑडियो पासवर्ड बोलें...'
            : '🎙 Say your audio password now...';
    }
}

// ── 3. OVERLAY — kept for non-audio failure messages ─────────────
function showOverlay(message, duration = 3000) {
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position:fixed;inset:0;background:rgba(0,0,0,0.65);
        display:flex;align-items:center;justify-content:center;z-index:9999;`;
    const box = document.createElement('div');
    box.style.cssText = `
        background:#17171d;border:1px solid rgba(255,255,255,0.1);
        padding:24px 40px;border-radius:10px;
        font-size:16px;font-family:sans-serif;color:#ededf0;`;
    box.innerText = message;
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    setTimeout(() => { overlay.remove(); window.location.href = '/'; }, duration);
}