from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text

heard=""
ending=['goodbye','bye','exit','see you later']
bye='[Reply]: Goodbye!Take care'

# Open file
with open('Audio/Transcribe.txt','a') as file:
    # loop for repeated audio recordings
    while True:
        # listen to audio
        heard=listen_text()
        # normalize text
        clean_heard = heard.lower().strip().replace('.', '')

        # write to file
        file.write(f'{clean_heard}\n')
        # check if any ending word is present
        if any(word in clean_heard for word in ending):
            print(bye)
            speak_text(bye)
            break
        speak_text(f'{clean_heard}')
    file.close()