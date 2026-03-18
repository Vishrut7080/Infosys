// Global Audio Assistant Module
let recognition;
let isListening = false;
let autoRestart = true;
let availableVoices = [];
let selectedVoiceURI = localStorage.getItem('assistantVoiceURI') || '';
let socket;
let fillerTimeout = null;
let isSpeaking = false;
let _fillerEls = [];

// Localized filler/status phrases. Keep entries short and conversational.
const I18N = {
    en: {
        fillers: [
            "Let me check on that for you.",
            "One moment please.",
            "Working on it.",
            "Just a second.",
            "Let me look into that.",
            "Give me a moment.",
            "Processing your request.",
            "Hang on, I'm on it.",
            "Let me find that for you.",
            "Almost there.",
            "On it, one sec.",
            "Sure, let me handle that.",
        ],
        thinking: 'Thinking...',
        done: 'Done',
    },
    hi: {
        fillers: [
            'जांच कर रहा हूँ…',
            'एक क्षण कृपया।',
            'काम कर रहा हूँ।',
            'एक सेकंड।',
            'मैं देख रहा हूँ…',
            'थोड़ा सा इंतजार करें।',
            'आपकी विनती संसाधित कर रहा हूँ।',
            'ठीक है, कर रहा हूँ…',
            'मिल रहा है…',
            'लगभग तैयार है।',
            'ठीक है, कर रहा हूँ।',
        ],
        thinking: 'सोच रहा हूँ…',
        done: 'संपन्न',
    }
};

// Track current conversation language. Initialize from document/lang or navigator.
let currentLang = (document.documentElement && document.documentElement.lang) ? document.documentElement.lang.split('-')[0] : (navigator.language || 'en').split('-')[0];
if (currentLang !== 'hi') currentLang = 'en';

function detectLanguageFromText(text) {
    if (!text) return null;
    // quick heuristic: Devanagari range indicates Hindi
    if (/[\u0900-\u097F]/.test(text)) return 'hi';
    return 'en';
}

function setCurrentLangFrom(text) {
    const detected = detectLanguageFromText(text);
    if (detected && detected !== currentLang) currentLang = detected;
}

function getLocalized(key) {
    const set = I18N[currentLang] || I18N.en;
    return set[key] || I18N.en[key] || '';
}

function getRandomFiller() {
    const set = I18N[currentLang] || I18N.en;
    const arr = set.fillers || I18N.en.fillers;
    return arr[Math.floor(Math.random() * arr.length)];
}

function initAssistant() {
    console.log("[Assistant] Initializing...");

    // 1. Initialize Socket.io
    socket = io();

    let hadDisconnect = false;

    socket.on('connect', () => {
        console.log("[Assistant] WebSocket Connected");
        updateUIStatus("Connected", "active");
        if (hadDisconnect) {
            Toast.show('Reconnected', 'success', 2500);
        }
        hadDisconnect = false;
    });

    socket.on('feed_update', (data) => {
        // Clear any ephemeral filler bubbles before showing the real assistant response
        clearFillerBubbles();
        window.dispatchEvent(new CustomEvent('feed-update', { detail: data }));
        if (typeof appendFeedMessage === 'function') {
            appendFeedMessage({ text: data.text, time: data.time });
            // adapt language as responses arrive
            if (data.lang) currentLang = data.lang.split('-')[0] === 'hi' ? 'hi' : 'en';
            else setCurrentLangFrom(data.text);
        }
    });

    socket.on('tts', (data) => {
        speakText(data.text, data.lang || 'en');
    });

    socket.on('toast', (data) => {
        Toast.show(data.message, data.type || 'info', data.duration || 3500);
    });

    socket.on('disconnect', () => {
        console.log("[Assistant] WebSocket Disconnected");
        hadDisconnect = true;
        updateUIStatus("Disconnected", "error");
        Toast.show('Connection lost — retrying…', 'error', 5000);
        fetch('/check-session').then(r => r.json()).then(data => {
            if (!data.logged_in) {
                window.dispatchEvent(new Event('session-expired'));
            }
        }).catch(() => { });
    });

    window.addEventListener('session-expired', () => {
        Toast.show('Session expired — please log in again', 'warning', 5000);
    });

    // 2. Setup Speech-to-Text (STT)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.error("Web Speech API not supported.");
        updateUIStatus(getLocalized('thinking') || 'Not Supported', "error");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => { isListening = true; console.log("[Assistant] Listening"); };
    recognition.onresult = (event) => {
        const result = event.results[event.results.length - 1];
        // Interrupt ongoing speech immediately on the first interim result
        if (isSpeaking) {
            interruptSpeech();
        }
        // Only send the message once speech recognition is finalised
        if (!result.isFinal) return;
        const transcript = result[0].transcript.trim();
        if (!transcript) return;
        // update language from user speech
        setCurrentLangFrom(transcript);
        sendChat(transcript);
    };
    recognition.onend = () => {
        isListening = false;
        if (autoRestart) setTimeout(startListening, 300);
    };

    startListening();

    if (window.speechSynthesis) {
        window.speechSynthesis.onvoiceschanged = loadVoices;
        loadVoices();
    }

    // Speak a welcome greeting once voices are ready
    _speakDashboardWelcome();

    // Initialize the action label to the correct language
    const _label = document.getElementById('actionLabel');
    if (_label) _label.textContent = getLocalized('thinking');

    // Allow clicking the waveform to interrupt speech
    const waveform = document.getElementById('waveform');
    if (waveform) {
        waveform.addEventListener('click', () => {
            if (isSpeaking) interruptSpeech();
        });
        waveform.title = 'Click to interrupt speech';
    }

    // Allow sending messages via Enter key in the text input
    const chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); sendChatFromInput(); }
        });
    }
}

function loadVoices() {
    availableVoices = window.speechSynthesis.getVoices();
    const select = document.getElementById('voiceSelect');
    if (!select) return;

    while (select.options.length > 1) select.remove(1);
    availableVoices.forEach(voice => {
        const option = document.createElement('option');
        option.value = voice.voiceURI;
        option.textContent = `${voice.name} (${voice.lang})`;
        if (voice.voiceURI === selectedVoiceURI) option.selected = true;
        select.appendChild(option);
    });

    // Persist voice selection
    select.onchange = function () {
        selectedVoiceURI = this.value;
        localStorage.setItem('assistantVoiceURI', selectedVoiceURI);
    };
}

function testVoiceUI() {
    speakText('Hello! This is your assistant voice.', 'en');
}

// ─── DASHBOARD WELCOME ───────────────────────────────────────
function _speakDashboardWelcome() {
    if (!window.speechSynthesis) return;
    const name = (document.body.dataset.userName || '').trim().split(' ')[0];
    const hour = new Date().getHours();
    const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    const msg = name ? `${greeting}, ${name}. I'm listening.` : `${greeting}. I'm listening.`;

    function _doSpeak() {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(msg);
        if (!availableVoices.length) availableVoices = window.speechSynthesis.getVoices();
        if (selectedVoiceURI) u.voice = availableVoices.find(v => v.voiceURI === selectedVoiceURI) || null;
        isSpeaking = true;
        u.onend = u.onerror = () => { isSpeaking = false; autoRestart = true; startListening(); };
        window.speechSynthesis.speak(u);
    }

    // Voices may not be loaded yet on first page visit — wait for them
    if (window.speechSynthesis.getVoices().length) {
        availableVoices = window.speechSynthesis.getVoices();
        setTimeout(_doSpeak, 600);  // slight delay so page has settled
    } else {
        window.speechSynthesis.addEventListener('voiceschanged', function _onV() {
            window.speechSynthesis.removeEventListener('voiceschanged', _onV);
            availableVoices = window.speechSynthesis.getVoices();
            setTimeout(_doSpeak, 600);
        });
        setTimeout(() => { if (!isSpeaking) _doSpeak(); }, 2000);  // hard fallback
    }
}

function updateUIStatus(text, state) {
    const label = document.getElementById('listenLabel');
    const badge = document.getElementById('listenBadge');
    if (label) label.textContent = text;
    if (badge) badge.className = 'listen-badge ' + state;
}

function startListening() {
    if (recognition && !isListening) try { recognition.start(); } catch (e) { }
}

// ─── ACTION INDICATOR ────────────────────────────────────────
function showActionIndicator(text, services) {
    const bar = document.getElementById('actionIndicator');
    const label = document.getElementById('actionLabel');
    const icons = document.getElementById('actionServiceIcons');
    if (!bar) return;

    label.textContent = text || getLocalized('thinking');

    if (icons) {
        icons.innerHTML = '';
        if (services && services.length) {
            services.forEach(s => {
                const tag = document.createElement('span');
                tag.className = 'action-service-tag';
                tag.textContent = s === 'gmail' ? '📧 Gmail' : s === 'telegram' ? '✈️ Telegram' : s;
                icons.appendChild(tag);
            });
        }
    }
    bar.classList.add('visible');
}

function hideActionIndicator() {
    const bar = document.getElementById('actionIndicator');
    if (bar) bar.classList.remove('visible');
}

// ─── INTERRUPT ──────────────────────────────────────────────
function interruptSpeech() {
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
    }
    isSpeaking = false;
    clearTimeout(fillerTimeout);
    hideActionIndicator();
    autoRestart = true;
    startListening();
}

// ─── SEND CHAT ──────────────────────────────────────────────
function sendChatFromInput() {
    const input = document.getElementById('chatInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    sendChat(text);
}

function sendChat(text) {
    const _userEntry = { text: "[User]: " + text, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    window.dispatchEvent(new CustomEvent('feed-update', { detail: _userEntry }));
    if (typeof appendFeedMessage === 'function') {
        appendFeedMessage(_userEntry);
    }

    showActionIndicator(getLocalized('thinking'), null);

    // Skip filler for queries that are almost certainly fast (greetings, short phrases, etc.)
    const _tl = text.trim().toLowerCase();
    const _isFastQuery = text.trim().length < 20
        || /^(hi|hello|hey|thanks?|thank you|bye|good (morning|afternoon|evening|night)|yes|no|okay|ok|cancel|stop|never ?mind)\b/i.test(_tl)
        || /^(what (time|date)|tell me a joke|who am i)/.test(_tl);

    // Speak a filler phrase only for requests likely to take a while
    if (!_isFastQuery) {
        fillerTimeout = setTimeout(() => {
            const phrase = getRandomFiller();
            speakFiller(phrase);
        }, 4000);
    }

    fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text, lang: 'en' })
    })
        .then(res => res.json())
        .then(data => {
            clearTimeout(fillerTimeout);

            // Show which services were used
            if (data.services && data.services.length) {
                const doneText = (data.lang && data.lang.split('-')[0] === 'hi') ? I18N.hi.done : getLocalized('done');
                showActionIndicator(doneText, data.services);
                setTimeout(hideActionIndicator, 3000);
            } else {
                hideActionIndicator();
            }

            // Handle navigation
            if (data.navigate) {
                const url = data.navigate;
                if (url.includes('#')) {
                    // In-page navigation (hash-based page switch)
                    const page = url.split('#')[1];
                    if (typeof showPage === 'function') showPage(page);
                } else {
                    window.location.href = url;
                    return;
                }
            }

            if (data.response) {
                // Cancel any filler that might be mid-speech
                if (isSpeaking) {
                    window.speechSynthesis.cancel();
                    isSpeaking = false;
                }
                // adapt language from assistant response
                if (data.lang) currentLang = data.lang.split('-')[0] === 'hi' ? 'hi' : 'en';
                else setCurrentLangFrom(data.response);
                speakText(data.response, data.lang || currentLang);
            }
        })
        .catch(err => {
            clearTimeout(fillerTimeout);
            hideActionIndicator();
            console.error("Error sending Chat:", err);
            Toast.show('Could not reach assistant', 'error');
        });
}

// ─── SPEAK FILLER (brief, interruptible) ────────────────────
function speakFiller(text) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel(); // clear queue to avoid Chrome bug
    const utterance = new SpeechSynthesisUtterance(text);
    if (selectedVoiceURI) {
        utterance.voice = availableVoices.find(v => v.voiceURI === selectedVoiceURI) || null;
    }
    utterance.rate = 1.1; // slightly faster for fillers
    isSpeaking = true;
    utterance.onend = () => { isSpeaking = false; };
    utterance.onerror = () => { isSpeaking = false; };
    window.speechSynthesis.speak(utterance);
    // Show an ephemeral chat bubble for the filler phrase
    try { showFillerBubble(text); } catch (e) { }
}

// ─── SPEAK TEXT (main response) ─────────────────────────────
function speakText(text, lang) {
    if (!window.speechSynthesis) return;

    autoRestart = false;
    try { if (recognition && isListening) recognition.stop(); } catch (e) { }

    window.speechSynthesis.cancel(); // clear any queued/stuck utterances

    const utterance = new SpeechSynthesisUtterance(text);
    // Re-fetch voices in case they weren't loaded yet (Chrome async)
    if (!availableVoices.length) availableVoices = window.speechSynthesis.getVoices();
    if (selectedVoiceURI) {
        utterance.voice = availableVoices.find(v => v.voiceURI === selectedVoiceURI) || null;
    }

    isSpeaking = true;
    utterance.onend = () => {
        isSpeaking = false;
        autoRestart = true;
        startListening();
    };
    utterance.onerror = () => {
        isSpeaking = false;
        autoRestart = true;
        startListening();
    };
    window.speechSynthesis.speak(utterance);
}

function showFillerBubble(text) {
    if (typeof appendFeedMessage !== 'function') return null;
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    appendFeedMessage({ text: `[System]: ${text}`, time });
    const feed = document.getElementById('convFeed');
    if (!feed) return null;
    const last = feed.querySelector('.feed-msg:last-child');
    if (!last) return null;
    last.classList.add('feed-filler');
    _fillerEls.push(last);
    // persist until cleared by `clearFillerBubbles()` when a real response arrives
    return last;
}

function clearFillerBubbles() {
    try {
        _fillerEls.forEach(el => el && el.remove());
    } catch (e) { }
    _fillerEls = [];
}

document.addEventListener('DOMContentLoaded', initAssistant);
