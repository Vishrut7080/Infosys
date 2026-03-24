const GOOGLE_DOMAINS = ['gmail.com', 'googlemail.com'];
const MICROSOFT_DOMAINS = ['outlook.com', 'hotmail.com', 'live.com', 'msn.com'];

let keyboardLoginAttempted = false;
let pollingActive = true;

// Signal to the toast system that this page prefers bottom placement.
try { if (document && document.body) document.body.dataset.toastPosition = 'bottom'; } catch (e) { }
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

    // Mark keyboard mode immediately (handles autofill where no keydown fires)
    // and keep it set for the rest of the session so voice doesn't restart on failure
    keyboardLoginAttempted = true;

    try {
        const response = await fetch('/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const result = await response.json();

        if (result.status === 'success') {
            messageEl.style.color = '#4ade80';
            messageEl.innerText = window.LangManager?.isHindi() ? 'साइन इन हो रहा है…' : 'Signing in…';
            setTimeout(() => {
                window.location.href = result.redirect || '/dashboard';
            }, 150);
        } else {
            VoiceAILoader.hide();
            messageEl.style.color = '#f87171';
            messageEl.innerText = result.message || 'Login failed';
        }
    } catch (error) {
        VoiceAILoader.hide();
        messageEl.style.color = '#f87171';
        messageEl.innerText = 'Error connecting to server';
        console.error('Login error:', error);
    }
});

// ── AUDIO (VOICE) LOGIN — Web Speech API → /voice-login ─────────
(function initVoiceLogin() {
    const btn = document.getElementById('voiceMicBtn');
    const label = document.getElementById('voiceLoginLabel');
    const msgEl = document.getElementById('message');
    if (!btn) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        btn.style.display = 'none';
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    let listening = false;

    // Persistent bottom-center listening pill using the global Toast utility.
    let _listeningToast = null;
    function setListening(state) {
        listening = state;
        btn.classList.toggle('listening', state);
        label.textContent = state
            ? (window.LangManager?.isHindi() ? 'सुन रहा है…' : 'Listening…')
            : (window.LangManager?.isHindi() ? 'ऑडियो पासवर्ड से साइन इन करें' : 'Sign in with audio password');
    }

    // The listening pill is managed independently of the recognition cycle.
    // It is shown once when the user starts a session and hidden only when they
    // intentionally stop — NOT on every recognition.onend/restart cycle, which
    // is what caused the constant flash.
    function showListeningPill() {
        if (_listeningToast) return; // already visible — skip
        try {
            const c = document.getElementById('toast-container');
            if (c) c.classList.add('position-bottom');
            const msg = window.LangManager?.isHindi() ? 'सुन रहा है…' : 'Listening…';
            _listeningToast = Toast.show(msg, 'info', 24 * 60 * 60 * 1000);
            if (_listeningToast) _listeningToast.classList.add('toast-listening');
        } catch (e) { }
    }

    function hideListeningPill() {
        try {
            if (_listeningToast) { Toast.dismiss(_listeningToast); _listeningToast = null; }
            const c = document.getElementById('toast-container');
            if (c) c.classList.remove('position-bottom');
        } catch (e) { }
    }

    let shouldListen = true;

    function startListening() {
        if (!shouldListen || keyboardLoginAttempted) return;
        try {
            recognition.start();
            setListening(true);
            showListeningPill(); // idempotent — won't flash on auto-restart
            if (msgEl) {
                msgEl.style.color = '#94a3b8';
                msgEl.textContent = window.LangManager?.isHindi()
                    ? 'ऑडियो पासवर्ड सुन रहा है…'
                    : 'Listening for your audio password…';
            }
        } catch { /* already running */ }
    }

    // NOTE: Welcome speech intentionally removed — no automatic guidance on the login page.

    // Button acts as manual toggle
    btn.addEventListener('click', () => {
        if (listening) {
            shouldListen = false;
            hideListeningPill();
            recognition.stop();
        } else {
            shouldListen = true;
            startListening();
        }
    });

    // Pause when user focuses a keyboard input; resume on blur if nothing was typed
    document.querySelectorAll('#email, #password').forEach(input => {
        input.addEventListener('focus', () => {
            shouldListen = false;
            hideListeningPill();
            if (listening) recognition.stop();
        });
        input.addEventListener('blur', () => {
            if (!keyboardLoginAttempted && input.value === '') {
                shouldListen = true;
                setTimeout(startListening, 400);
            }
        });
    });

    recognition.onresult = async (event) => {
        const spoken = event.results[0][0].transcript.toLowerCase().trim();
        setListening(false);
        // Let VoiceNav intercept navigation commands before attempting voice login
        window.dispatchEvent(new CustomEvent('feed-update', { detail: { text: '[User]: ' + spoken, time: '' } }));
        if (msgEl) { msgEl.style.color = '#94a3b8'; msgEl.textContent = `Heard: "${spoken}" — verifying…`; }
        try {
            const res = await fetch('/voice-login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: spoken }),
            });
            const data = await res.json();
            if (data.status === 'success') {
                if (msgEl) { msgEl.style.color = '#4ade80'; msgEl.textContent = `Welcome back, ${data.name}!`; }
                setTimeout(() => { window.location.href = data.redirect || '/dashboard'; }, 150);
            } else {
                if (msgEl) { msgEl.style.color = '#f87171'; msgEl.textContent = data.message || 'Audio password not recognised.'; }
            }
        } catch {
            if (msgEl) { msgEl.style.color = '#f87171'; msgEl.textContent = 'Error connecting to server.'; }
        }
    };

    recognition.onerror = (event) => {
        setListening(false);
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
            shouldListen = false;
            if (btn) btn.style.display = 'none';
            return;
        }
        if (msgEl) { msgEl.style.color = '#f87171'; msgEl.textContent = `Microphone error: ${event.error}`; }
    };

    recognition.onend = () => {
        setListening(false);
        if (shouldListen && !keyboardLoginAttempted) setTimeout(startListening, 800);
    };

    // Ensure the toast container exists and is bottom-positioned before any toast is shown
    function ensureBottomToastContainer() {
        try {
            let c = document.getElementById('toast-container');
            if (!c) {
                c = document.createElement('div');
                c.id = 'toast-container';
                c.classList.add('position-bottom');
                document.body.appendChild(c);
            } else {
                c.classList.add('position-bottom');
            }
        } catch (e) { /* ignore DOM issues */ }
    }

    // Attempt to start listening on page load so the listening pill appears immediately
    // (some browsers require a user gesture; if blocked, onerror will handle it)
    window.addEventListener('load', () => {
        // Create the bottom-positioned container first to avoid a visual jump
        ensureBottomToastContainer();
        setTimeout(() => {
            try {
                if (btn && shouldListen && !keyboardLoginAttempted) startListening();
            } catch (e) { /* ignore */ }
        }, 250);
    });
})();

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



// ── Auto-set message when arriving from signup ──────────────
if (new URLSearchParams(window.location.search).get('from') === 'signup') {
    const msg = document.getElementById('message');
    if (msg) {
        msg.style.color = '#4ade80';
        msg.textContent = window.LangManager?.isHindi()
            ? '🎙 पंजीकरण सफल! कृपया लॉगिन करें।'
            : '🎙 Registration successful! Please log in.';
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

// Initialize shared voice handlers for login page
document.addEventListener('DOMContentLoaded', () => { if (window.VoiceNav) VoiceNav.init('login'); });
