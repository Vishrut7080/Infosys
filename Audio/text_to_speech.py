import pyttsx3

# ----------------------
# Speaking logic

# ----------------------

def speak_text(text):
    engine=pyttsx3.init()

    # Custom voice settings
    engine.setProperty('rate', 160)
    engine.setProperty('volume', 1.0)

    # Get Avaialble Voices
    voices=engine.getProperty('voices')
    engine.setProperty('voice', voices[0])

    # Speech part
    engine.say(text)

    # Waiting for the speech to end
    engine.runAndWait()

__all__=['speak_text']