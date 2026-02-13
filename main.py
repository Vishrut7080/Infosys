from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders

# ----------------------
# VARIABLES
# ----------------------

heard=""
send_mail='[System]: This feature will be added in the next milestone.'
see_inboc='[System]: This feature will be added in the next milestone.'
ending=['goodbye','bye','exit','see you later']
bye='[System]: Goodbye!Take care.'

# ----------------------
# Commands
# ----------------------

mail_req=['mail','email','message']
inbox_req=['inbox','mail','mails']
affirmation=['yes','ok', 'yah','ya','want to']
negation=['no', 'nah','nope','don\'t want to']
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
        print(f'[User]: {heard}')
        # normalize text
        clean_heard = heard.lower().strip().replace('.', '')

        # write to file
        file.write(f'{clean_heard}\n')

        # To send a mail
        if 'send' in heard and any(word in clean_heard for word in mail_req):
            speak_text('[System]: You want to send mail?')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            if any(s in clean_response for s in affirmation):
                speak_text(clean_response)
                speak_text(send_mail)
                compose=open_gmail_compose()
                speak_text(compose)
                continue
            elif any(s in clean_response for s in negation):
                speak_text(clean_response)
                speak_text('[System]: Ok Thanks for confirming.')
                continue

        # To check inbox
        elif 'check' and any(word in clean_heard for word in inbox_req):
            speak_text('[System]: You want to check the inbox?')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            if any(s in clean_response for s in affirmation):
                speak_text(clean_response)
                speak_text(see_inboc)
                inbox=get_top_senders()
                speak_text(inbox)
                continue
            elif any(s in clean_response for s in negation):
                speak_text(clean_response)
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