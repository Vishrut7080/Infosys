from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders
import Mail.web_login as web_login
import threading, webbrowser
# ----------------------
# VARIABLES
# ----------------------

heard=""
send_mail='[System]: This feature will be added in the next milestone.'
see_inbox='[System]: This feature will be added in the next milestone.'
ending=['goodbye','bye','exit','see you later']
bye='[System]: Goodbye!Take care.'
mail='[System]: Email will be added in next milestone. To be continued....'
greeting_response='[System]: Hi, what can i do for you?'

# ----------------------
# Commands
# ----------------------

mail_req=['mail','email','message']
inbox_req=['inbox','mail','mails']
affirmation=['yes','ok', 'yah','ya','want to']
negation=['no', 'nah','nope','don\'t want to']
greeting=['hi','hello','hey']

# ----------------------
# COMMAND LOGIC
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

        if any(word in clean_heard for word in greeting):
            speak_text(greeting_response)

        # ----------------------
        # LOGIN COMMAND
        # ----------------------
        elif 'login' in clean_heard:
            web_login.login_status='waiting'
            # start web server
            server_thread = threading.Thread(target=web_login.start_server)
            server_thread.daemon = True
            server_thread.start()
        
            # open browser
            webbrowser.open("http://localhost:5000")
            continue
        
        elif clean_heard.strip() == 'correct':
            speak_text('[System]: Login confirmed.')
            web_login.login_status = "success"
            continue

        elif web_login.login_status != "success" and clean_heard.strip() in ['incorrect', 'no', 'cancel']:
            speak_text('[System]: Login cancelled.')
            web_login.login_status = "failed"
            continue


        elif web_login.login_status != "success" and (('send' in clean_heard and any(word in clean_heard for word in mail_req)) or
        ('check' in clean_heard and any(word in clean_heard for word in inbox_req))):
            speak_text('[System]: Please log in first.')
            continue


        # To send a mail
        elif web_login.login_status == "success" and 'send' in clean_heard and any(word in clean_heard for word in mail_req):
            speak_text('[System]: You want to send mail?')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {clean_response}')
            if any(s in clean_response for s in affirmation):
                speak_text(send_mail)
                compose=open_gmail_compose()
                speak_text(compose)
                continue
            elif any(s in clean_response for s in negation):
                speak_text('[System]: Ok Thanks for confirming.')
                continue

        # To check inbox
        elif web_login.login_status == "success" and 'check' in clean_heard and any(word in clean_heard for word in inbox_req):
            speak_text('[System]: You want to check the inbox?')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {clean_response}')
            if any(s in clean_response for s in affirmation):
                speak_text(see_inbox)
                inbox=get_top_senders()
                speak_text(inbox)
                continue
            elif any(s in clean_response for s in negation):
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