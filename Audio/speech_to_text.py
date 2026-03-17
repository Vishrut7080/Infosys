from Audio.io_queues import stt_queue
import queue

def listen_text(duration: int = 5, force_lang: str = None) -> tuple:
    """
    Blocks until text is received from the frontend via the STT queue.
    """
    try:
        # Wait for input from the frontend
        # The frontend should send { "text": "...", "lang": "en|hi" }
        data = stt_queue.get(timeout=60) # 1 min timeout to prevent total deadlock
        text = data.get("text", "")
        lang = data.get("lang", force_lang or "en")
        
        if not text:
            return "[System]: Sorry, didn't catch that", lang
            
        print(f"[STT Frontend] Transcribed: {text}")
        return text, lang
    except queue.Empty:
        # If no input received within the timeout
        return "", force_lang or "en"

__all__ = ['listen_text']
