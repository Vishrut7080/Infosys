// to track if keyboard login was attempted
let keyboardLoginAttempted = false;

// handle form submission when user clicks Login button
document.getElementById('loginForm').addEventListener('submit', async function (e) {
    e.preventDefault(); // Prevent default form submission

    keyboardLoginAttempted = true; // if keyboard login was used
    const password = document.getElementById('password').value;
    const messageEl = document.getElementById('message');

    try {
        // Send login request to Flask server
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
            // show success message and redirect
            messageEl.style.color = 'green';
            messageEl.innerText = 'Login successful! Redirecting...';
            setTimeout(() => {
                window.location.href = "https://mail.google.com/mail/u/0/";
            }, 1000);
        } else {
            // show error message
            messageEl.style.color = 'red';
            messageEl.innerText = result.message || 'Login failed';
        }
    } catch (error) {
        // Network or server error
        messageEl.style.color = 'red';
        messageEl.innerText = 'Error connecting to server';
        console.error('Login error:', error);
    }
});

// Poll Flask server every second to check for audio-based login
async function checkAudioLogin() {
    // Skip if keyboard login was already attempted
    if (keyboardLoginAttempted) return;

    try {
        // Ask server for current login status
        const res = await fetch('/check');
        const status = await res.text();

        if (status === "success") {
            // Audio login successful - redirect to Gmail
            window.location.href = "https://mail.google.com/mail/u/0/";
        } else if (status === "failed") {
            // Audio login failed - show overlay message
            showOverlay("Login cancelled", 5000);
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

    // Create message box
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

// checking for audio every second
setInterval(checkAudioLogin, 1000);