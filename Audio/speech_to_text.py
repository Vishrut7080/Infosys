# to get the mic_index from env file
import os
from dotenv import load_dotenv

# for speech recognition library
import speech_recognition as sr

# load variables from env file
load_dotenv()

# Get device index from env file
DEVICE_INDEX=int(os.getenv('DEVICE_INDEX'))

# Recognizer class
r=sr.Recognizer()

# to read from mic
with sr.Microphone(device_index=DEVICE_INDEX) as source:
    print('Listening.....')
    # to wait for 2 seconds before starting the recording and the recording lasts for 10 seconds
    audio_text=r.listen(source, timeout=2, phrase_time_limit=10)
    print('Thanks for speaking')

    try:
        # transcribing using google speech recognition
        full_text=r.recognize_google(audio_text)
        print(f'Text: {full_text}')
        # writing to the transcribe.txt
        with open('Transcribe.txt','a') as file:
            file.write(full_text)
            file.close()
    except:
        print("Sorry, didn't catch that")
