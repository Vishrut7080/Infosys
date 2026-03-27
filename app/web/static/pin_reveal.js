// ── Countdown ──
const TOTAL = 60;
let remaining = TOTAL;
const countdownEl = document.getElementById('countdown');
const countdownFill = document.getElementById('countdownFill');

// Set initial width
countdownFill.style.transform = 'scaleX(1)';

const timer = setInterval(() => {
    remaining--;
    countdownEl.textContent = remaining;
    // Shrink bar proportionally
    countdownFill.style.transform = `scaleX(${remaining / TOTAL})`;
    if (remaining <= 0) {
        clearInterval(timer);
        proceedToLogin();
    }
}, 1000);

async function proceedToLogin() {
    clearInterval(timer);
    await fetch('/api/clear-pending-pins', { method: 'POST' });
    window.location.href = '/dashboard';
}

// ── Copy PIN ──
function copyPin(elementId, btn) {
    const val = document.getElementById(elementId).textContent.trim();
    navigator.clipboard.writeText(val).then(() => {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.textContent = 'Copy';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(() => {
        // Fallback for older browsers
        const el = document.getElementById(elementId);
        const range = document.createRange();
        range.selectNode(el);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        document.execCommand('copy');
        window.getSelection().removeAllRanges();
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
    });
}

// Initialize shared voice handlers for pin reveal page
document.addEventListener('DOMContentLoaded', () => { if (window.VoiceNav) VoiceNav.init('pin_reveal'); });
