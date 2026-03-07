# ----------------------
# STT (SPEECH TO TEXT) LOGIC — Faster Whisper
# ----------------------
# Requirements:
#   pip install faster-whisper sounddevice numpy scipy python-dotenv
#
# WHY FASTER WHISPER OVER STANDARD WHISPER?
# -----------------------------------------
# Standard OpenAI Whisper runs on PyTorch and is accurate but slow on CPU.
# A 5-second audio clip can take 3–8 seconds to transcribe on a mid-range CPU,
# making it feel laggy in any interactive / real-time application.
#
# Faster Whisper is a drop-in replacement built on CTranslate2, an optimized
# inference engine for transformer models. Key advantages:
#
#   ✓ 4–8x faster transcription on CPU compared to standard Whisper
#   ✓ Up to 2x less memory usage (supports int8 quantization)
#   ✓ Same model weights — identical accuracy to standard Whisper
#   ✓ GPU support with even greater speedup if available
#   ✓ Actively maintained with a clean, simple Python API
#
# For a voice assistant where the user is waiting for a response, this
# speed difference is the deciding factor. A 5s clip that took ~6s to
# transcribe with standard Whisper now takes ~0.8–1.5s with Faster Whisper.
#
# Model size guide (same as standard Whisper):
#   "tiny"   — fastest, least accurate (~39M params)
#   "base"   — great balance for most use cases (~74M params)  ← recommended
#   "small"  — better accuracy, slightly slower (~244M params)
#   "medium" — best accuracy, noticeably slower (~769M params)
#
# Models are downloaded automatically on first use from Hugging Face.
# ----------------------

import os,time,tempfile,numpy as np,sounddevice as sd
from scipy.io.wavfile import write as wav_write
from dotenv import load_dotenv
from faster_whisper import WhisperModel

from Audio.text_to_speech import speak_text

# Load environment variables from .env file
load_dotenv()

# ----------------------
# Configuration
# ----------------------

# Microphone device index — set DEVICE_INDEX in your .env file
# Run `python -m sounddevice` to list available devices and find your index
DEVICE_INDEX = int(os.getenv('DEVICE_INDEX', 0))

MODEL=os.getenv("MODEL")

# Whisper model size — set WHISPER_MODEL in your .env or leave as default
WHISPER_MODEL = os.getenv('WHISPER_MODEL', MODEL)

# Compute type controls the quantization level:
#   "int8"    — fastest on CPU, tiny accuracy drop, recommended for most users
#   "float16" — best for GPU (halves VRAM usage vs float32)
#   "float32" — full precision, slowest, only needed if int8 causes issues
COMPUTE_TYPE = os.getenv('WHISPER_COMPUTE_TYPE', 'int8')

# Device to run inference on: "cpu" or "cuda" (if you have an Nvidia GPU)
DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')

# Sample rate expected by Whisper — do not change
SAMPLE_RATE = 16000

# ----------------------
# Model Loading
# ----------------------

# Load the model once at module level so it isn't reloaded on every call.
# First load downloads the model weights (~74MB for "base") from Hugging Face.
# Subsequent loads are instant as the model is cached locally.
print(f"[STT] Loading Faster Whisper '{WHISPER_MODEL}' model "
      f"(device={DEVICE}, compute={COMPUTE_TYPE})...")

model = WhisperModel(
    WHISPER_MODEL,
    device=DEVICE,
    compute_type=COMPUTE_TYPE,
)

print("[STT] Faster Whisper model loaded and ready.")


# ----------------------
# Core Listen Function
# ----------------------

def listen_text(duration: int = 5, force_lang: str = None) -> tuple:
    try:
        speak_text('Listening.....')
        time.sleep(0.3)  # Small pause so TTS finishes before recording starts

        # --- Record audio from microphone ---
        # sounddevice captures audio into a NumPy array directly,
        # avoiding the overhead of pyaudio stream management.
        print(f"[STT] Recording for {duration}s on device index {DEVICE_INDEX}...")
        audio_data = sd.rec(
            frames=int(SAMPLE_RATE * duration),
            samplerate=SAMPLE_RATE,
            channels=1,       # Mono — Whisper expects single-channel audio
            dtype='int16',    # 16-bit PCM — standard format for speech models
            device=DEVICE_INDEX,
        )
        sd.wait()  # Block until the full recording is captured
        print("[STT] Recording complete. Transcribing...")

        # Check if audio has enough energy (not silence)
        if np.abs(audio_data).mean() < 50:
            print("[STT] Silence detected, skipping.")
            return "[System]: Sorry, didn't catch that", 'en'

        # --- Write audio to a temporary WAV file ---
        tmp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        tmp_path = tmp_file.name
        tmp_file.close()  # release handle so wav_write and Faster Whisper can access it
        
        wav_write(tmp_path, SAMPLE_RATE, audio_data)

        # --- Transcribe with Faster Whisper ---
        # transcribe() returns a generator of segments + language info.
        # We join all segments to get the full transcription.
        #
        # beam_size=5   — standard beam search width, good accuracy/speed balance
        # language='en' — skip language detection to save ~0.2s per call
        #                 remove this line if you need multilingual support
       
        _, info = model.transcribe(tmp_path, beam_size=5)

        # Only trust language detection if confidence is high enough
        if info.language_probability > 0.7 and info.language in ('en', 'hi'):
            detected_lang = force_lang if force_lang else info.language
        else:
            detected_lang = force_lang if force_lang else 'en'  # default to English if unsure

        segments, _ = model.transcribe(tmp_path, beam_size=5, language=detected_lang)

        transcribed_text = ' '.join(segment.text for segment in segments).strip()

        # Clean up the temporary WAV file
        os.remove(tmp_path)

        print(f"[STT] Detected language: {detected_lang}")

        # Treat an empty result as silence / no speech detected
        if not transcribed_text:
            return "[System]: Sorry, didn't catch that", 'en'

        print(f"[STT] Transcribed: {transcribed_text}")
        return transcribed_text, detected_lang

    except Exception as e:
        print(f"[STT] Error during transcription: {e}")
        return "[System]: Sorry, an error occurred during transcription", 'en'


__all__ = ['listen_text']