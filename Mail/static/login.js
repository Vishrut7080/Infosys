const GOOGLE_DOMAINS = ['gmail.com', 'googlemail.com'];
const MICROSOFT_DOMAINS = ['outlook.com', 'hotmail.com', 'live.com', 'msn.com'];

let keyboardLoginAttempted = false;
let pollingActive = true;

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

// ── FORM SUBMIT — always use database login ──────────────────────
document.getElementById('loginForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    const messageEl = document.getElementById('message');
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

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

// ── AUDIO LOGIN — poll /check every second ────────────────────────
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

// ── Password show/hide ───────────────────────────────────────────
document.getElementById('eyeBtn').addEventListener('click', () => {
    const input = document.getElementById('password');
    input.type = input.type === 'password' ? 'text' : 'password';
});

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