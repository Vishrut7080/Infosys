// Global Audio Assistant Module
let recognition;
let isListening = false;

function initAssistant() {
    // 1. Setup Text-to-Speech (TTS) Polling
    setInterval(pollTTS, 1000);

    // 2. Setup Speech-to-Text (STT) 
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.warn("Web Speech API not supported in this browser.");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US'; // Default, could be dynamically updated

    recognition.onresult = function(event) {
        const transcript = event.results[event.results.length - 1][0].transcript.trim();
        if (transcript) {
            console.log("Recognized:", transcript);
            sendSTT(transcript);
        }
    };

    recognition.onerror = function(event) {
        console.error("Speech Recognition Error:", event.error);
    };

    recognition.onend = function() {
        // Automatically restart listening if it stopped unexpectedly
        if (isListening) {
            try { recognition.start(); } catch(e) {}
        }
    };

    startListening();
}

function startListening() {
    if (recognition && !isListening) {
        try {
            recognition.start();
            isListening = true;
            console.log("Listening started.");
        } catch (e) {
            console.error("Failed to start listening:", e);
        }
    }
}

function stopListening() {
    if (recognition && isListening) {
        recognition.stop();
        isListening = false;
        console.log("Listening stopped.");
    }
}

function sendSTT(text) {
    fetch('/api/stt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text, lang: recognition.lang.startsWith('hi') ? 'hi' : 'en' })
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

    // Pause listening while speaking to avoid echoing itself
    stopListening();

    const utterance = new SpeechSynthesisUtterance(text);
    // Use heuristic for language
    utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-US';
    
    utterance.onend = function() {
        startListening();
    };
    
    window.speechSynthesis.speak(utterance);
}

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', initAssistant);
