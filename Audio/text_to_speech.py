import pyttsx3
import threading

_tts_lock = threading.Lock()

def speak_text(text):
    print(text)
    with _tts_lock:
        try:
            e = pyttsx3.init()
            e.setProperty('rate', 160)
            e.setProperty('volume', 1.0)
            voices = e.getProperty('voices')
            e.setProperty('voice', voices[1].id)
            e.say(text)
            e.runAndWait()
            e.stop()
        except Exception as ex:
            print(f'[TTS Error]: {ex}')

__all__ = ['speak_text']