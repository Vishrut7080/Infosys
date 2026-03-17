// Global Audio Assistant Module
let recognition;
let isListening = false;
let autoRestart = true;
let availableVoices = [];
let selectedVoiceURI = localStorage.getItem('assistantVoiceURI') || '';

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
    document.addEventListener('click', () => {
        if (!isListening && autoRestart) {
            console.log("[Assistant] User gesture detected, starting mic...");
            startListening();
        }
    }, { once: false });

    // 4. Load Voices for Selection
    if (window.speechSynthesis) {
        window.speechSynthesis.onvoiceschanged = loadVoices;
        loadVoices();
    }
}

function loadVoices() {
    availableVoices = window.speechSynthesis.getVoices();
    const select = document.getElementById('voiceSelect');
    if (!select) return;

    // Clear except first
    while (select.options.length > 1) select.remove(1);

    availableVoices.forEach(voice => {
        const option = document.createElement('option');
        option.value = voice.voiceURI;
        option.textContent = `${voice.name} (${voice.lang})`;
        if (voice.voiceURI === selectedVoiceURI) option.selected = true;
        select.appendChild(option);
    });

    select.onchange = () => {
        selectedVoiceURI = select.value;
        localStorage.setItem('assistantVoiceURI', selectedVoiceURI);
    };
}

function testVoiceUI() {
    speakText("This is a test of the selected assistant voice.", "en");
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
        } catch (e) { }
    }
}

function stopListening() {
    if (recognition && isListening) {
        autoRestart = false;
        recognition.stop();
    }
}

function sendSTT(text) {
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
    
    autoRestart = false;
    recognition.stop();

    const utterance = new SpeechSynthesisUtterance(text);
    
    // Apply selected voice if exists
    if (selectedVoiceURI) {
        const voice = availableVoices.find(v => v.voiceURI === selectedVoiceURI);
        if (voice) utterance.voice = voice;
    } else {
        utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-US';
    }
    
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
