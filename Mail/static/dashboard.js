let selectedServices = [];
let pollingActive = true;

function toggleService(card) {
    const service = card.dataset.service;
    card.classList.toggle('selected');

    if (card.classList.contains('selected')) {
        if (!selectedServices.includes(service)) selectedServices.push(service);
    } else {
        selectedServices = selectedServices.filter(s => s !== service);
    }

    document.getElementById('confirmBtn').disabled = selectedServices.length === 0;
}

async function confirmSelection() {
    if (selectedServices.length === 0) return;

    const btn = document.getElementById('confirmBtn');
    btn.disabled = true;
    btn.querySelector('span').textContent = 'Launching...';

    await fetch('/select-services', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ services: selectedServices })
    });

    document.getElementById('statusMsg').textContent =
        `Starting: ${selectedServices.join(', ')}... You can close this window.`;

    // Only open Gmail if selected — Telegram runs in background via main.py
    if (selectedServices.includes('gmail')) {
        setTimeout(() => {
            window.open('https://mail.google.com/mail/u/0/#inbox', '_blank');
        }, 500);
    }

    // Telegram is handled entirely by main.py in the background
    // No browser needed
}

// Poll Flask for voice confirmation from main.py
async function pollVoiceConfirm() {
    if (!pollingActive) return;
    try {
        const res = await fetch('/get-services');
        const data = await res.json();
        if (data.voice_confirmed) {
            pollingActive = false;
            document.getElementById('voiceText').textContent = 'Voice confirmed!';
        }
    } catch (e) { }
}

setInterval(pollVoiceConfirm, 1000);