import pyttsx3

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

# sample text to be played
sample_text='Welcome to the Voice Based Email Assistant.'

# calling function
speak_text(sample_text)

__all__=['speak_text']