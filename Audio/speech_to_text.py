# to get the mic_index from env file
import os
from dotenv import load_dotenv

# for speech recognition library
import speech_recognition as sr

# load variables from env file
load_dotenv()

# Get device index from env file
DEVICE_INDEX=int(os.getenv('DEVICE_INDEX'))

# function to record audio
def listen_text():
    # Recognizer class
    r=sr.Recognizer()

    # to read from mic
    with sr.Microphone(device_index=DEVICE_INDEX) as source:
        print('Listening.....')
        try:
            # to wait for 2 seconds before starting the recording and the recording lasts for 10 seconds
            audio_text=r.listen(source, timeout=2, phrase_time_limit=10)
            print('Thanks for speaking')

        
            # transcribing using google speech recognition
            full_text=f'[You]: {r.recognize_google(audio_text)}'
            print(full_text)
            return full_text
        # if no audio is heard
        except sr.WaitTimeoutError:
            print("[Reply]: Sorry, didn't catch that")
            return "Sorry, didn't catch that"        

__all__=['listen_text', 'full_text']