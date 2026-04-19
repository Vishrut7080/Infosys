// Global Audio Assistant Module
let recognition;
let isListening = false;
let autoRestart = true;
let availableVoices = [];
let selectedVoiceURI = localStorage.getItem('assistantVoiceURI') || '';
let socket;
let fillerTimeout = null;
let isSpeaking = false;
let speechBlocked = false;  // Block auto-speech after escape key
let userPaused = false;    // Track if user intentionally paused (vs auto-pause)
let _fillerEls = [];
let _speechResumeTimer = null;

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
        Toast.show(data.message, data.type || 'info', data.duration || 3500, { link: data.link });
    });

    socket.on('lang_update', (data) => {
        if (data.lang === 'hi' || data.lang === 'en') {
            if (window.LangManager) LangManager.set(data.lang);
        }
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
    // _speakDashboardWelcome(); // DISABLED: Causes greeting spam on every page reload

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

    // Pause/Resume speech synthesis on Escape key - Speech recognition stays active
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && window.speechSynthesis) {
            e.preventDefault();  // Prevent default browser behavior

            if (userPaused) {
                // Currently paused (by user) → resume
                window.speechSynthesis.resume();
                isSpeaking = true;
                userPaused = false;
                _startSpeechKeepAlive();  // Restart keep-alive
                // Restart speech recognition if it stopped
                if (!isListening && typeof startListening === 'function') {
                    setTimeout(startListening, 300);
                }
                updateVoiceStatusIndicators();
            } else if (window.speechSynthesis.speaking) {
                // Currently speaking → pause and STOP keep-alive (intentional pause)
                window.speechSynthesis.pause();
                isSpeaking = false;
                userPaused = true;  // Mark as user-intentional pause
                _stopSpeechKeepAlive();  // Stop auto-restart mechanism
                // Keep speech recognition active - don't restart it, just keep it
                updateVoiceStatusIndicators();
            } else {
                // Not speaking and not paused → cancel any pending speech
                window.speechSynthesis.cancel();
                userPaused = false;
                // Keep recognition running if it was running
                updateVoiceStatusIndicators();
            }
        }
    });

    // Reset userPaused when user starts speaking (via mic or input)
    const resetUserPaused = () => { userPaused = false; };
    const chatInputEl = document.getElementById('chatInput');
    if (chatInputEl) {
        chatInputEl.addEventListener('input', resetUserPaused);
        chatInputEl.addEventListener('keydown', resetUserPaused);
    }
    if (typeof startListening === 'function') {
        const originalStartListening = startListening;
        startListening = function () {
            resetUserPaused();
            return originalStartListening.apply(this, arguments);
        };
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

// Update voice status indicators - shows both STT and TTS state
function updateVoiceStatusIndicators() {
    const label = document.getElementById('listenLabel');
    const badge = document.getElementById('listenBadge');

    if (!label || !badge) return;

    // Determine STT status
    let sttStatus = isListening ? 'listening' : 'not-listening';

    // Determine TTS status
    let ttsStatus = '';
    if (window.speechSynthesis) {
        if (window.speechSynthesis.speaking) {
            ttsStatus = 'speaking';
        } else if (window.speechSynthesis.paused) {
            ttsStatus = 'paused';
        }
    }

    // Build combined status text
    let statusText = '';
    let stateClass = sttStatus;

    if (ttsStatus === 'speaking') {
        statusText = '🔊 Speaking';
        stateClass = 'speaking';
    } else if (ttsStatus === 'paused') {
        statusText = '⏸ Paused';
        stateClass = 'paused';
    } else if (isListening) {
        statusText = '🎤 Listening';
        stateClass = 'listening';
    } else {
        statusText = '🎤 Ready';
        stateClass = 'ready';
    }

    label.textContent = statusText;
    badge.className = 'listen-badge ' + stateClass;
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
    _stopSpeechKeepAlive();
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
    }
    isSpeaking = false;
    clearTimeout(fillerTimeout);
    hideActionIndicator();

    // Explicitly stop and reset the restart loop
    autoRestart = true;
    try {
        if (recognition) {
            recognition.stop();
        }
    } catch (e) {
        // Recognition might already be stopped
    }
    // Start listening again after a tiny delay to let the browser process cancel()
    setTimeout(startListening, 50);
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
    // Check if voice-nav should handle this navigation locally
    const trimmed = text.trim().toLowerCase();
    const isNavCommand = /^(go to|open|take me to|show me|cancel|go back|return|log\s?out|sign out|sign\s?me\s?out|log\s?me\s?out|logout)\b/i.test(trimmed);

    if (isNavCommand && window.VoiceNav && window.VoiceNav._navigationHandled) {
        // Voice-nav already handled this navigation, skip backend processing
        console.log('[Assistant] Skipping navigation - handled by VoiceNav');
        return;
    }

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
        body: JSON.stringify({ text: text, lang: currentLang })
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
                const targetPath = url.split('#')[0];
                const currentPath = window.location.pathname;

                if (targetPath === currentPath || (targetPath === '/dashboard' && currentPath === '/dashboard') || (targetPath === '/admin' && currentPath === '/admin')) {
                    // In-page navigation (already on the base page)
                    const hash = url.includes('#') ? url.split('#')[1] : null;

                    if (currentPath === '/admin' && typeof showPanel === 'function') {
                        showPanel(hash || 'overview');
                    } else if (typeof showPage === 'function') {
                        showPage(hash || 'dashboard');
                    }
                } else {
                    // Different base page, full reload
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

// ─── Chrome speechSynthesis keepalive ────────────────────────
// Chrome silently pauses long utterances after ~15 s.
// Calling resume() on a short interval prevents this.
function _startSpeechKeepAlive() {
    _stopSpeechKeepAlive();
    _speechResumeTimer = setInterval(() => {
        if (window.speechSynthesis && window.speechSynthesis.speaking) {
            window.speechSynthesis.pause();
            window.speechSynthesis.resume();
        }
    }, 5000);
}
function _stopSpeechKeepAlive() {
    if (_speechResumeTimer) { clearInterval(_speechResumeTimer); _speechResumeTimer = null; }
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
    _startSpeechKeepAlive();
    utterance.onend = () => { isSpeaking = false; _stopSpeechKeepAlive(); };
    utterance.onerror = () => { isSpeaking = false; _stopSpeechKeepAlive(); };
    window.speechSynthesis.speak(utterance);
    // Show an ephemeral chat bubble for the filler phrase
    try { showFillerBubble(text); } catch (e) { }
}

// ─── SPEAK TEXT (main response) ─────────────────────────────
function speakText(text, lang) {
    if (!window.speechSynthesis) return;

    autoRestart = false;
    try { if (recognition && isListening) recognition.stop(); } catch (e) { }

    _stopSpeechKeepAlive();

    // If user had intentionally paused, cancel to start fresh (not resume old speech)
    if (userPaused) {
        window.speechSynthesis.cancel();
        userPaused = false;  // Reset - we're starting new
    }

    // Small delay after cancel() — Chrome sometimes swallows the next
    // utterance if speak() is called synchronously after cancel().
    setTimeout(() => {
        const utterance = new SpeechSynthesisUtterance(text);
        if (!availableVoices.length) availableVoices = window.speechSynthesis.getVoices();

        const langCode = (lang || 'en').split('-')[0];
        let voice = null;
        if (selectedVoiceURI) {
            voice = availableVoices.find(v => v.voiceURI === selectedVoiceURI) || null;
        }
        if (!voice && langCode === 'hi') {
            voice = availableVoices.find(v =>
                v.lang.startsWith('hi') ||
                v.name.toLowerCase().includes('hindi')
            ) || null;
            if (!voice) {
                Toast.show('No Hindi voice found on this device', 'warning', 4000);
            }
        }
        utterance.voice = voice;

        isSpeaking = true;
        _startSpeechKeepAlive();
        utterance.onend = () => {
            isSpeaking = false;
            _stopSpeechKeepAlive();
            autoRestart = true;
            startListening();
        };
        utterance.onerror = (e) => {
            // "interrupted" is expected when we call cancel() — don't treat as failure
            if (e.error === 'interrupted') return;
            isSpeaking = false;
            _stopSpeechKeepAlive();
            autoRestart = true;
            startListening();
        };
        window.speechSynthesis.speak(utterance);
    }, 50);
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
