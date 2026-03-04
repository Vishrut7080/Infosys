// ----------------------
// LOGIN PAGE LOGIC
// ----------------------
// Three login paths:
//   1. Keyboard  — user fills form → POST /login → /auth/google
//   2. Audio     — main.py sets login_status="success" → poll detects → /auth/google
//   3. Google    — button click → /auth/google directly
//
// Key behaviour:
//   - First keypress pauses audio for 20 seconds (handled in main.py)
//   - All successful paths go through /auth/google → Gmail
// ----------------------

const REDIRECT_URL = "http://localhost:5000/auth/google";

// Tracks if user has started keyboard login — stops audio polling
let keyboardLoginAttempted = false;

// Stops polling once a result (success/failed) is received
let pollingActive = true;


// ----------------------
// Notify Flask on keypress — triggers 20s audio pause in main.py
// ----------------------
function notifyTyping(isTyping) {
    fetch('/typing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ typing: isTyping })
    }).catch(() => { });
}

document.querySelectorAll('input').forEach(input => {
    input.addEventListener('keydown', () => {
        keyboardLoginAttempted = true;
        notifyTyping(true);
    });
});


// ----------------------
// 1. KEYBOARD LOGIN
// ----------------------
document.getElementById('loginForm').addEventListener('submit', async function (e) {
    e.preventDefault();
    const messageEl = document.getElementById('message');
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    // Detect provider from email domain
    const googleDomains = ['gmail.com', 'googlemail.com'];
    const microsoftDomains = ['outlook.com', 'hotmail.com', 'live.com', 'msn.com'];
    const domain = email.split('@')[1]?.toLowerCase();

    if (googleDomains.includes(domain)) {
        messageEl.style.color = '#8888aa';
        messageEl.innerText = 'Detected Google account. Redirecting...';
        setTimeout(() => { window.location.href = '/auth/google'; }, 800);
        return;
    }

    if (microsoftDomains.includes(domain)) {
        messageEl.style.color = '#8888aa';
        messageEl.innerText = 'Detected Microsoft account. Redirecting...';
        setTimeout(() => { window.location.href = '/auth/microsoft'; }, 800);
        return;
    }

    // Standard password login for non-OAuth emails
    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const result = await response.json();

        if (result.status === 'success') {
            messageEl.style.color = '#4ade80';
            messageEl.innerText = 'Login successful! Redirecting...';
            setTimeout(() => { window.location.href = '/dashboard'; }, 800);
        } else {
            messageEl.style.color = '#ff6b6b';
            messageEl.innerText = result.message || 'Login failed';
        }
    } catch (error) {
        messageEl.style.color = '#ff6b6b';
        messageEl.innerText = 'Error connecting to server';
    }
});


// ----------------------
// 2. AUDIO LOGIN — poll /check every second
// ----------------------
async function checkAudioLogin() {
    if (keyboardLoginAttempted) return; // user is typing — skip
    if (!pollingActive) return;         // already handled — skip

    try {
        const res = await fetch('/check');
        const status = await res.text();

        if (status === "success") {
            pollingActive = false;
            window.location.href = REDIRECT_URL;

        } else if (status === "failed") {
            pollingActive = false;
            showOverlay("Login cancelled", 4000);
        }

    } catch (error) {
        console.log("Polling: server not ready yet...");
    }
}

setInterval(checkAudioLogin, 1000);


// ----------------------
// 3. OVERLAY — shown on audio login failure
// ----------------------
function showOverlay(message, duration = 3000) {
    const overlay = document.createElement("div");
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0;
        width: 100%; height: 100%;
        background: rgba(0,0,0,0.6);
        display: flex; align-items: center;
        justify-content: center; z-index: 9999;
    `;
    const box = document.createElement("div");
    box.style.cssText = `
        background: white; padding: 20px 40px;
        border-radius: 8px; font-size: 18px;
        font-family: sans-serif; color: black;
    `;
    box.innerText = message;
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    setTimeout(() => {
        overlay.remove();
        window.location.href = '/';
    }, duration);
}