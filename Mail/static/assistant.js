// Global Audio Assistant Module
let recognition;
let isListening = false;
let autoRestart = true;

function initAssistant() {
    console.log("[Assistant] Initializing...");
    
    // 1. Setup Text-to-Speech (TTS) Polling
    setInterval(pollTTS, 1000);

    // 2. Setup Speech-to-Text (STT) 
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.error("Web Speech API not supported in this browser.");
        updateUIStatus("Not Supported", "error");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US'; 

    recognition.onstart = function() {
        isListening = true;
        console.log("[Assistant] Microphone Active");
        updateUIStatus("Listening", "active");
    };

    recognition.onresult = function(event) {
        const transcript = event.results[event.results.length - 1][0].transcript.trim();
        if (transcript) {
            console.log("[Assistant] Recognized:", transcript);
            sendSTT(transcript);
        }
    };

    recognition.onerror = function(event) {
        console.error("[Assistant] Speech Recognition Error:", event.error);
        if (event.error === 'not-allowed') {
            updateUIStatus("Mic Blocked", "error");
            autoRestart = false;
        }
    };

    recognition.onend = function() {
        isListening = false;
        console.log("[Assistant] Microphone Stopped");
        updateUIStatus("Paused", "paused");
        
        // Automatically restart listening if it stopped and we want it to keep going
        if (autoRestart) {
            setTimeout(startListening, 300);
        }
    };

    // Attempt to start immediately
    startListening();

    // 3. Setup User Gesture Fallback
    // Browsers often block mic start without a click. 
    // This ensures that the first time the user clicks anywhere, we try to start.
    document.addEventListener('click', () => {
        if (!isListening && autoRestart) {
            console.log("[Assistant] User gesture detected, starting mic...");
            startListening();
        }
    }, { once: false });
}

function updateUIStatus(text, state) {
    const label = document.getElementById('listenLabel');
    const badge = document.getElementById('listenBadge');
    if (label) label.textContent = text;
    if (badge) {
        badge.className = 'listen-badge ' + state;
    }
}

function startListening() {
    if (recognition && !isListening) {
        try {
            recognition.start();
        } catch (e) {
            // Usually "already started" error, can ignore
        }
    }
}

function stopListening() {
    if (recognition && isListening) {
        autoRestart = false;
        recognition.stop();
    }
}

function sendSTT(text) {
    // Show user text in feed immediately for responsiveness if on dashboard
    if (typeof appendFeedMessage === 'function') {
        appendFeedMessage({ text: "[User]: " + text, time: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) });
    }

    fetch('/api/stt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            text: text, 
            lang: recognition.lang.startsWith('hi') ? 'hi' : 'en' 
        })
    }).catch(err => console.error("Error sending STT:", err));
}

function pollTTS() {
    fetch('/api/tts')
        .then(res => res.json())
        .then(data => {
            if (data.messages && data.messages.length > 0) {
                data.messages.forEach(msg => {
                    speakText(msg.text, msg.lang);
                });
            }
        })
        .catch(err => console.error("Error polling TTS:", err));
}

function speakText(text, lang) {
    if (!window.speechSynthesis) return;

    console.log("[Assistant] Speaking:", text);
    
    // Temporarily disable auto-restart while speaking
    autoRestart = false;
    recognition.stop();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-US';
    
    utterance.onend = function() {
        console.log("[Assistant] Finished speaking");
        autoRestart = true;
        startListening();
    };
    
    utterance.onerror = function(e) {
        console.error("[Assistant] TTS Error:", e);
        autoRestart = true;
        startListening();
    };

    window.speechSynthesis.speak(utterance);
}

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', initAssistant);
