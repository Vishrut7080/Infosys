# ----------------------
# STT (SPEECH TO TEXT) LOGIC — OpenAI Whisper
# ----------------------
# Requirements:
#   pip install openai-whisper sounddevice numpy scipy python-dotenv
#   (also requires ffmpeg installed on your system)

import os, time,tempfile,numpy as np,sounddevice as sd
from scipy.io.wavfile import write as wav_write
from dotenv import load_dotenv
import whisper

from Audio.text_to_speech import speak_text

# Load environment variables from .env file
load_dotenv()

# ----------------------
# Configuration
# ----------------------

# Microphone device index — set DEVICE_INDEX in your .env file
# Run `python -m sounddevice` to list available devices and find your index
DEVICE_INDEX = int(os.getenv('DEVICE_INDEX', 0))

# Whisper model size — trade-off between speed and accuracy:
#   "tiny"   — fastest, least accurate (~39M params)
#   "base"   — good balance for most use cases (~74M params)  ← recommended
#   "small"  — better accuracy, slightly slower (~244M params)
#   "medium" — best accuracy, noticeably slower (~769M params)
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'base')

# Sample rate expected by Whisper (do not change)
SAMPLE_RATE = 16000

# ----------------------
# Model Loading
# ----------------------

# Load the Whisper model once at module level so it isn't reloaded on every call.
# The model is downloaded automatically on first use (~74MB for "base").
print(f"[STT] Loading Whisper '{WHISPER_MODEL}' model...")
model = whisper.load_model(WHISPER_MODEL)
print(f"[STT] Whisper model loaded.")


# ----------------------
# Core Listen Function
# ----------------------

def listen_text(duration: int = 5) -> str:
    try:
        speak_text('Listening.....')
        time.sleep(0.3)  # Small pause so TTS finishes before we start recording

        # --- Record audio from mic ---
        # sounddevice records into a NumPy array; shape is (samples, channels)
        print(f"[STT] Recording for {duration}s on device index {DEVICE_INDEX}...")
        audio_data = sd.rec(
            frames=int(SAMPLE_RATE * duration),
            samplerate=SAMPLE_RATE,
            channels=1,                  # Mono — Whisper expects mono audio
            dtype='int16',               # 16-bit PCM — standard for speech
            device=DEVICE_INDEX,
        )
        sd.wait()  # Block until recording is complete
        print("[STT] Recording complete. Transcribing...")

        # --- Save to a temporary WAV file ---
        # Whisper accepts file paths, so we write a temp .wav to disk.
        # It's cleaned up automatically after the `with` block.
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            wav_write(tmp_path, SAMPLE_RATE, audio_data)

        # --- Transcribe with Whisper ---
        # fp16=False avoids a warning on CPUs (use fp16=True if you have a GPU)
        result = model.transcribe(tmp_path, fp16=False, language='en')

        # Clean up the temp file
        os.remove(tmp_path)

        transcribed_text = result['text'].strip()

        # If Whisper returns an empty string, treat it as silence
        if not transcribed_text:
            return "[System]: Sorry, didn't catch that"

        print(f"[STT] Transcribed: {transcribed_text}")
        return transcribed_text

    except Exception as e:
        # Catch-all for unexpected errors (device not found, model error, etc.)
        print(f"[STT] Error during transcription: {e}")
        return "[System]: Sorry, an error occurred during transcription"


__all__ = ['listen_text']