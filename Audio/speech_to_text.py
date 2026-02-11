# ----------------------
# Importing libraries
# ----------------------

# to get the mic_index from env file
import os
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

# function to record audio
def listen_text():
    # Recognizer class
    r=sr.Recognizer()

    r.pause_threshold = 1.5 # How long of a pause counts as “end of speech”.
    r.energy_threshold = 200 # adjust if mic is sensitive

    # to read from mic
    with sr.Microphone(device_index=DEVICE_INDEX) as source:
        speak_text('Listening.....')
        try:
            # to wait for 2 seconds before starting the recording and the recording lasts for 10 seconds
            audio_text=r.listen(source, phrase_time_limit=15,
                                timeout=5, # it is the Maximum time (in seconds) the system waits for you to start speaking.
                                )
            
            
            # transcribing using google speech recognition
            full_text=f'{r.recognize_google(audio_text)}'
            return full_text
        # if no audio is heard
        except sr.WaitTimeoutError:
            return "[System]: Sorry, didn't catch that"   
        except sr.UnknownValueError:
            return "[System]: Sorry, didn't catch that"   

__all__=['listen_text']