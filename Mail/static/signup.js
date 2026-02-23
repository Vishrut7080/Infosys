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
        validateAudio();

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