from Audio.io_queues import tts_queue

def speak_text(text, lang='en'):
    """
    Puts the text into a queue to be fetched and spoken by the frontend.
    """
    print(f"[TTS to Frontend]: {text}")
    tts_queue.put({"text": text, "lang": lang})

__all__ = ['speak_text']
