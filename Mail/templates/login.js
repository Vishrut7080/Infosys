async function check() {
    try {
        const res = await fetch('/check');
        const status = await res.text();

        if (status === "success") {
            window.location.href = "https://mail.google.com/mail/u/0/";
        } else if (status === "failed") {
            // show overlay for 3 seconds and close window
            showOverlay("Login cancelled", 3000);
        }
    } catch (error) {
        console.log("Server not ready yet...");
    }
}

function showOverlay(message, duration = 3000) {
    // create overlay
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

    // message box
    const box = document.createElement("div");
    box.style.background = "white";
    box.style.padding = "20px 40px";
    box.style.borderRadius = "8px";
    box.style.fontSize = "18px";
    box.style.fontFamily = "sans-serif";
    box.innerText = message;

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    // remove after duration
    setTimeout(() => {
        overlay.remove();
        window.close();
    }, duration);
}

// poll server every 1 second
setInterval(check, 1000);
