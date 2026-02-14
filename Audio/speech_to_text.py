# ----------------------
# STT (SPEECH TO TEXT) LOGIC
# ----------------------

# to get the mic_index from env file
import os, time
from dotenv import load_dotenv
from Audio.text_to_speech import speak_text

# for speech recognition library
import speech_recognition as sr

# load variables from env file
load_dotenv()

# Get device index from env file
DEVICE_INDEX=int(os.getenv('DEVICE_INDEX'))

# ----------------------
# Listening Logic
# ----------------------

# Recognizer class
r=sr.Recognizer()
# r.energy_threshold = 180 # adjust if mic is sensitive
r.dynamic_energy_threshold = True   # auto-adjust sensitivity
r.pause_threshold = 2.0 # How long of a pause counts as “end of speech”.
r.non_speaking_duration = 0.5

mic = sr.Microphone(device_index=DEVICE_INDEX)

# function to record audio
def listen_text(duration=5):
    # to read from mic
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=0.8) #This dynamically calibrates the microphone to the room noise. Without this, the recognizer often ignores speech.
        speak_text('Listening.....')
        time.sleep(0.5)   # small delay before listening

        # ----------------------
        # ERROR HANDLING
        # ----------------------
        try:
            audio_text=r.record(source, duration=8)
                                # phrase_time_limit=10,
                                # timeout=5, # it is the Maximum time (in seconds) the system waits for you to start speaking.                             
                        
            # transcribing using google speech recognition
            full_text=f'{r.recognize_google(audio_text)}'
            return full_text
        # if no audio is heard
        except sr.WaitTimeoutError:
            return "[System]: Sorry, didn't catch that"   
        except sr.UnknownValueError:
            return "[System]: Sorry, didn't catch that"   

__all__=['listen_text']