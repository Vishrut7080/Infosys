from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders

# ----------------------
# VARIABLES
# ----------------------

heard=""
ending=['goodbye','bye','exit','see you later']
bye='[System]: Goodbye!Take care.'

# ----------------------
# Commands
# ----------------------

mail_req=['send','mail']
inbox_req=['check','inbox']
affirmation=['yes','ok', 'yah','ya']
negation=['no', 'nah']
mail='[System]: Email will be added in next milestone. To be continued....'

# ----------------------
# Command Logic
# ----------------------

# Open file
with open('Audio/Transcribe.txt','a') as file:
    # loop for repeated audio recordings
    while True:
        # listen to audio
        heard=listen_text()
        speak_text(f'[User]: {heard}')
        # normalize text
        clean_heard = heard.lower().strip().replace('.', '')

        # write to file
        file.write(f'{clean_heard}\n')

        # To send a mail
        if all(word in clean_heard for word in mail_req):
            speak_text('[System]: You want to send mail?')
            heard=listen_text().lower().strip().replace('.', '')
            if any(s in heard for s in affirmation):
                speak_text(heard)
                compose=open_gmail_compose()
                speak_text(compose)
                continue
            elif any(s in heard for s in negation):
                speak_text(heard)
                speak_text('[System]: Ok Thanks for confirming.')
                continue

        # To check inbox
        elif all(word in clean_heard for word in inbox_req):
            speak_text('[System]: You want to check the inbox?')
            heard=listen_text().lower().strip().replace('.','')
            if any(s in heard for s in affirmation):
                speak_text(heard)
                inbox=get_top_senders()
                speak_text(inbox)
                continue
            elif any(s in heard for s in negation):
                speak_text(heard)
                speak_text('[System]: Ok Thanks for confirming.')
                continue
        
        # To terminate Loop
        elif any(word in clean_heard for word in ending):
            speak_text(bye)
            break

        # When speech is not understood
        else:
            speak_text("[System]: Please try a different command.")
    file.close()