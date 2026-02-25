// ----------------------
// LOGIN PAGE LOGIC
// ----------------------
// Handles two login paths:
//   1. Keyboard login  — user fills the form and clicks Login
//   2. Audio login     — voice assistant authenticates in the background,
//                        Flask sets a session flag, and we poll /check every second
//   3. Google      — user clicks "Sign in with Google"; Flask handles the
//                        redirect flow and the callback sends the user to Gmail
//
// ALL successful logins redirect to Gmail.
// ----------------------

// Track whether the user has already attempted keyboard login.
// If they have, we stop polling for audio login to avoid a race condition.
let keyboardLoginAttempted = false;

// Target URL after any successful login
const REDIRECT_URL = "http://localhost:5000/auth/google";

// Tell Flask the user is typing so audio login polling pauses
function notifyTyping(isTyping) {
    fetch('/typing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ typing: isTyping })
    }).catch(() => { });  // silent fail — non-critical
}

// Fire when any input is focused or typed in
document.querySelectorAll('input').forEach(input => {
    input.addEventListener('keydown', () => {
        keyboardLoginAttempted = true;
        notifyTyping(true);
    });
});


// ----------------------
// 1. KEYBOARD LOGIN — form submit handler
// ----------------------

document.getElementById('loginForm').addEventListener('submit', async function (e) {
    e.preventDefault(); // Prevent full page reload on submit

    keyboardLoginAttempted = true; // Flag so audio polling stops
    const messageEl = document.getElementById('message');

    try {
        // POST credentials to Flask /login endpoint
        const response = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email: document.getElementById('email').value.trim(),
                password: document.getElementById('password').value
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            // Show success message then redirect to Gmail
            messageEl.style.color = 'green';
            messageEl.innerText = 'Login successful! Redirecting to Gmail...';
            setTimeout(() => {
                window.location.href = REDIRECT_URL;
            }, 1000);

        } else {
            // Show error returned by the server
            messageEl.style.color = 'red';
            messageEl.innerText = result.message || 'Login failed';
        }

    } catch (error) {
        // Network or server-side crash
        messageEl.style.color = 'red';
        messageEl.innerText = 'Error connecting to server';
        console.error('Login error:', error);
    }
});


// ----------------------
// 2. AUDIO LOGIN — poll Flask every second for voice-auth result
// ----------------------
// The voice assistant calls a Flask endpoint to set login_status in the session.
// This poller checks that status and acts on it without needing a page reload.

async function checkAudioLogin() {
    // Don't interfere if the user is doing keyboard login
    if (keyboardLoginAttempted) return;

    try {
        const res = await fetch('/check');
        const status = await res.text();

        if (status === "success") {
            // Voice login approved — redirect to Gmail
            window.location.href = REDIRECT_URL;

        } else if (status === "failed") {
            // Voice login rejected — show a dismissable overlay
            showOverlay("Login cancelled", 5000);
        }
        // Any other status (e.g. "pending") — keep polling silently

    } catch (error) {
        // Server not ready yet or network blip — keep polling silently
        console.log("Polling: server not ready yet...");
    }
}

// Poll every second
setInterval(checkAudioLogin, 1000);


// ----------------------
// 3. OVERLAY HELPER — shown on audio login failure
// ----------------------

function showOverlay(message, duration = 3000) {
    // Semi-transparent full-screen backdrop
    const overlay = document.createElement("div");
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0;
        width: 100%; height: 100%;
        background: rgba(0,0,0,0.6);
        display: flex; align-items: center; justify-content: center;
        z-index: 9999;
    `;

    // Message box
    const box = document.createElement("div");
    box.style.cssText = `
        background: white; padding: 20px 40px;
        border-radius: 8px; font-size: 18px;
        font-family: sans-serif; color: black;
    `;
    box.innerText = message;

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    // Auto-dismiss and close the tab after `duration` ms
    setTimeout(() => {
        overlay.remove();
        // Reset to login page instead of trying to close the tab
        window.location.href = '/';
    }, duration);
}