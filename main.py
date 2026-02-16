from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders
import Mail.web_login as web_login
import threading, webbrowser
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_AUD = os.getenv('SECRET_AUD', '')

# ----------------------
# VARIABLES
# ----------------------

heard=""
# Initialize to track the login; a sort of flag
login_initiated = False
# login_initiated = False   Not trying to login
# login_initiated = True    Currently trying to login
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


confirmation_words = ['correct','confirm','yes']
logout_commands=['logout', 'log out', 'sign out', 'signout']

if SECRET_AUD:
    # Add the audio password to confirmation words
    confirmation_words.append(SECRET_AUD.lower().strip())

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

        # ----------------------
        # GREETING
        # ----------------------
        if any(word in clean_heard for word in greeting):
            speak_text(greeting_response)

        # ----------------------
        # LOGIN COMMAND
        # ----------------------
        elif 'login' in clean_heard:
            web_login.login_status='waiting'
            login_initiated=True
            # start web server
            server_thread = threading.Thread(target=web_login.start_server)
            server_thread.daemon = True
            server_thread.start()
        
            # open browser
            webbrowser.open("http://localhost:5000")
            continue
        
        # ----------------------
        # LOGIN CONFIRMATION
        # ----------------------

        elif login_initiated and clean_heard.strip() in confirmation_words:
            login_initiated=False
            speak_text('[System]: Login confirmed.')
            web_login.login_status = "success"
            continue

        elif web_login.login_status != "success" and login_initiated:
            login_initiated=False
            speak_text('[System]: Login cancelled.')
            web_login.login_status = "failed"
            continue
        
        # ----------------------
        # REGISTER
        # ----------------------

        elif 'signup' in clean_heard or 'sign up' in clean_heard or 'register' in clean_heard:
            speak_text('[System]: Opening signup page...')
            webbrowser.open("http://localhost:5000/signup")
            continue

        # ----------------------
        # MAIL FEATURES
        # ----------------------

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
            
        # ----------------------
        # LOGOUT        
        # ----------------------
        elif any(word in clean_heard for word in logout_commands):
            if web_login.login_status == "success":
                speak_text('[System]: Logging you out.')
                web_login.login_status = "waiting"
                login_initiated = False
                speak_text('[System]: You have been logged out successfully.')
            else:
                speak_text('[System]: You are not currently logged in.')
            continue

        # ----------------------
        # TERMINATE LOOP
        # ----------------------

        elif any(word in clean_heard for word in ending):
            speak_text(bye)
            break

        # When speech is not understood
        else:
            speak_text("[System]: Please try a different command.")
    file.close()