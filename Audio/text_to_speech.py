import pyttsx3
import threading
import os

_tts_lock = threading.Lock()
_DIR = os.path.dirname(os.path.abspath(__file__))

def speak_text(text, lang='en'):
    print(text)
    if lang == 'hi':
        _speak_hindi(text)
        return
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

def _speak_hindi(text):
    try:
        from gtts import gTTS
        import pygame
        tts = gTTS(text=text, lang='hi')
        tmp = os.path.join(_DIR, "hindi_tmp.mp3")
        tts.save(tmp)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        os.remove(tmp)
    except Exception as ex:
        print(f'[Hindi TTS Error]: {ex}')
        print(f'[Hindi]: {text}')

__all__ = ['speak_text']