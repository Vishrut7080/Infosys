// ----------------------
// SIGNUP PAGE LOGIC
// ----------------------
// Handles:
//   - Real-time field validation (name, email, password strength,
//     confirm password match, secret audio)
//   - Password show/hide toggles
//   - Form submission to Flask /register endpoint
//   - Success screen with 3-second countdown then redirect to login
// ----------------------


// ----------------------
// DOM References
// ----------------------

const form = document.getElementById('signupForm');
const nameInput = document.getElementById('name');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const confirmInput = document.getElementById('confirmPassword');
const audioInput = document.getElementById('secretAudio');
const submitBtn = document.getElementById('submitBtn');
const btnText = submitBtn.querySelector('.btn-text');
const btnSpinner = document.getElementById('btnSpinner');
const successScreen = document.getElementById('successScreen');
const countdownEl = document.getElementById('countdown');
const gmailAddressInput = document.getElementById('gmailAddress');
const gmailAppPassInput = document.getElementById('gmailAppPass');
const gmailError = document.getElementById('gmailError');
const gmailAppError = document.getElementById('gmailAppError');

// Error message elements
const nameError = document.getElementById('nameError');
const emailError = document.getElementById('emailError');
const passwordError = document.getElementById('passwordError');
const confirmError = document.getElementById('confirmError');
const audioError = document.getElementById('audioError');

// Strength bar elements
const strengthFill = document.getElementById('strengthFill');
const strengthLabel = document.getElementById('strengthLabel');


// ----------------------
// Password Show/Hide Toggles
// ----------------------
// Each toggle button has data-target pointing to the input's id

document.querySelectorAll('.toggle-pw').forEach(btn => {
    btn.addEventListener('click', () => {
        const target = document.getElementById(btn.dataset.target);
        const isHidden = target.type === 'password';
        target.type = isHidden ? 'text' : 'password';
        btn.textContent = isHidden ? '🙈' : '👁';
    });
});


// ----------------------
// Password Strength Checker
// ----------------------
// Scores the password across 4 criteria and updates the bar + label

function getStrength(pw) {
    let score = 0;
    if (pw.length >= 8) score++; // minimum length
    if (/[A-Z]/.test(pw)) score++; // uppercase letter
    if (/[0-9]/.test(pw)) score++; // digit
    if (/[^A-Za-z0-9]/.test(pw)) score++; // special character
    return score; // 0–4
}

const strengthConfig = [
    { label: '', color: 'transparent', width: '0%' },
    { label: 'Weak', color: '#ef4444', width: '25%' },
    { label: 'Fair', color: '#f97316', width: '50%' },
    { label: 'Good', color: '#facc15', width: '75%' },
    { label: 'Strong', color: '#22c55e', width: '100%' },
];

passwordInput.addEventListener('input', () => {
    const score = getStrength(passwordInput.value);
    const config = strengthConfig[score];
    strengthFill.style.width = config.width;
    strengthFill.style.background = config.color;
    strengthLabel.textContent = config.label;
    strengthLabel.style.color = config.color;
    // Re-validate confirm field live if it already has a value
    if (confirmInput.value) validateConfirm();
});


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
    input.addEventListener('focus', () => notifyTyping(true));
    input.addEventListener('blur', () => notifyTyping(false));
});

// ----------------------
// Individual Field Validators
// Returns true if valid, false if not
// ----------------------

function validateName() {
    const val = nameInput.value.trim();
    if (!val) {
        setError(nameInput, nameError, 'Name is required.');
        return false;
    }
    if (val.length < 2) {
        setError(nameInput, nameError, 'Name must be at least 2 characters.');
        return false;
    }
    clearError(nameInput, nameError);
    return true;
}

function validateEmail() {
    const val = emailInput.value.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!val) {
        setError(emailInput, emailError, 'Email is required.');
        return false;
    }
    if (!emailRegex.test(val)) {
        setError(emailInput, emailError, 'Enter a valid email address.');
        return false;
    }
    clearError(emailInput, emailError);
    return true;
}

function validatePassword() {
    const val = passwordInput.value;
    if (!val) {
        setError(passwordInput, passwordError, 'Password is required.');
        return false;
    }
    if (val.length < 8) {
        setError(passwordInput, passwordError, 'Password must be at least 8 characters.');
        return false;
    }
    clearError(passwordInput, passwordError);
    return true;
}

function validateConfirm() {
    const val = confirmInput.value;
    if (!val) {
        setError(confirmInput, confirmError, 'Please confirm your password.');
        return false;
    }
    if (val !== passwordInput.value) {
        setError(confirmInput, confirmError, 'Passwords do not match.');
        return false;
    }
    clearError(confirmInput, confirmError);
    return true;
}

function validateAudio() {
    const val = audioInput.value.trim();
    // Secret audio password is optional, but if provided must be at least 3 chars
    if (val && val.length < 3) {
        setError(audioInput, audioError, 'Audio password must be at least 3 characters.');
        return false;
    }
    clearError(audioInput, audioError);
    return true;
}

function validateGmail() {
    const val = gmailAddressInput.value.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!val) {
        setError(gmailAddressInput, gmailError, 'Gmail address is required.');
        return false;
    }
    if (!emailRegex.test(val)) {
        setError(gmailAddressInput, gmailError, 'Enter a valid Gmail address.');
        return false;
    }
    clearError(gmailAddressInput, gmailError);
    return true;
}

function validateGmailAppPass() {
    const val = gmailAppPassInput.value.trim().replace(/\s/g, '');
    if (!val) {
        setError(gmailAppPassInput, gmailAppError, 'App Password is required.');
        return false;
    }
    if (val.length < 16) {
        setError(gmailAppPassInput, gmailAppError, 'App Password should be 16 characters.');
        return false;
    }
    clearError(gmailAppPassInput, gmailAppError);
    return true;
}

// ----------------------
// Error / Clear Helpers
// ----------------------

function setError(input, errorEl, message) {
    input.classList.add('invalid');
    input.classList.remove('valid');
    errorEl.textContent = message;
}

function clearError(input, errorEl) {
    input.classList.remove('invalid');
    input.classList.add('valid');
    errorEl.textContent = '';
}


// ----------------------
// Live Validation on Blur
// ----------------------
// Validate each field when the user leaves it (not while typing,
// which feels annoying before they've finished)

nameInput.addEventListener('blur', validateName);
emailInput.addEventListener('blur', validateEmail);
passwordInput.addEventListener('blur', validatePassword);
confirmInput.addEventListener('blur', validateConfirm);
audioInput.addEventListener('blur', validateAudio);

gmailAddressInput.addEventListener('blur', validateGmail);
gmailAppPassInput.addEventListener('blur', validateGmailAppPass);

// ----------------------
// Form Submission
// ----------------------

form.addEventListener('submit', async function (e) {
    e.preventDefault();

    // Run all validators — only proceed if all pass
    const valid =
        validateName() &   // bitwise & so ALL run (not short-circuit)
        validateEmail() &
        validatePassword() &
        validateConfirm() &
        validateAudio() &
        validateGmail() &
        validateGmailAppPass();

    if (!valid) return;

    // Show loading state
    setLoading(true);

    try {
        // POST registration data to Flask /register endpoint
        const response = await fetch('/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: nameInput.value.trim(),
                email: emailInput.value.trim(),
                password: passwordInput.value,
                secret_audio: audioInput.value.trim().toLowerCase(),
                gmail_address: gmailAddressInput.value.trim(),
                gmail_app_pass: gmailAppPassInput.value.trim(),
                tg_api_id: document.getElementById('tgApiId').value.trim(),
                tg_api_hash: document.getElementById('tgApiHash').value.trim(),
                tg_phone: document.getElementById('tgPhone').value.trim(),
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            // Hide the form card, show success screen, start countdown
            showSuccessScreen();
        } else {
            // Show server-side error inline (e.g. email already exists)
            setLoading(false);
            setError(emailInput, emailError, result.message || 'Registration failed. Try again.');
        }

    } catch (error) {
        setLoading(false);
        setError(emailInput, emailError, 'Could not connect to server. Please try again.');
        console.error('Signup error:', error);
    }
});


// ----------------------
// Loading State
// ----------------------

function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    btnText.textContent = isLoading ? 'Creating account…' : 'Create Account';
    btnSpinner.hidden = !isLoading;
}


// ----------------------
// Success Screen + Countdown
// ----------------------
// Shows the success overlay and counts down 3 seconds before
// redirecting to the login page.

function showSuccessScreen() {
    // Reveal the success screen (CSS animation handles fade-in)
    successScreen.hidden = false;
    navigator.sendBeacon('/signup-closed');

    let seconds = 3;
    countdownEl.textContent = seconds;

    const interval = setInterval(() => {
        seconds--;
        countdownEl.textContent = seconds;

        if (seconds <= 0) {
            clearInterval(interval);
            // Redirect to login page after countdown
            window.location.href = '/';
        }
    }, 1000);
}

// ========================
// SAYS THE WORD TO USER
// ========================
async function suggestAudioWord(forceReplace = false) {
    try {
        const res = await fetch('/suggest-audio');
        const data = await res.json();
        if (forceReplace || !audioInput.value.trim()) {
            // Only auto-fill if empty OR user clicked refresh
            audioInput.value = data.word;
            audioInput.placeholder = `e.g. ${data.word}`;
        } else {
            // On page load, just update placeholder — don't overwrite if user typed
            audioInput.placeholder = `e.g. ${data.word}`;
        }
    } catch (e) { }
}

// Refresh button click - always replace with new suggestion
document.getElementById('refreshAudioBtn').addEventListener('click', () => {
    suggestAudioWord(true);
    // Spin animation
    const btn = document.getElementById('refreshAudioBtn');
    btn.style.transition = 'transform 0.4s ease';
    btn.style.transform = 'translateY(-50%) rotate(360deg)';
    setTimeout(() => {
        btn.style.transition = 'none';
        btn.style.transform = 'translateY(-50%) rotate(0deg)';
    }, 400);
});

suggestAudioWord(false);

window.addEventListener('beforeunload', () => {
    navigator.sendBeacon('/signup-closed');
});