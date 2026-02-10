from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text


heard=listen_text()

with open('Audio/Transcribe.txt','a') as file:
    file.write(f'{heard}\n')
    file.close()
speak_text(f'{heard}')