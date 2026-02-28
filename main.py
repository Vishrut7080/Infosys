from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders
from Mail.email_sender import compose_email_by_voice
from Backend.database import verify_audio
import Mail.web_login as web_login
import threading, webbrowser
from dotenv import load_dotenv
import os,time, datetime, random, re

load_dotenv()

SECRET_AUD = os.getenv('SECRET_AUD', '')

# ----------------------
# VARIABLES
# ----------------------
typing_pause_until = 0
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
# JOKES BANK
# ----------------------
JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs!",
    "Why did the computer go to the doctor? It had a virus!",
    "I told my computer I needed a break. Now it won't stop sending me Kit Kat ads.",
    "Why did the programmer quit his job? Because he didn't get arrays.",
    "How many programmers does it take to change a light bulb? None — that's a hardware problem.",
    "Why do Java developers wear glasses? Because they don't C sharp.",
    "A SQL query walks into a bar, walks up to two tables and asks: Can I join you?",
    "Why was the math book sad? It had too many problems.",
    "What did zero say to eight? Nice belt!",
    "Why do scientists rarely tell jokes? Because all the good ones Argon.",
]

# ----------------------
# CALCULATOR HELPER
# ----------------------

# Words to symbols map for voice math
MATH_WORDS = {
    'plus'          : '+',
    'add'           : '+',
    'minus'         : '-',
    'subtract'      : '-',
    'times'         : '*',
    'multiplied by' : '*',
    'multiply'      : '*',
    'divided by'    : '/',
    'divide'        : '/',
    'over'          : '/',
    'power'         : '**',
    'squared'       : '**2',
    'cubed'         : '**3',
    'percent of'    : '/100*',
}


def parse_math(text: str) -> str | None:
    """
    Converts a spoken math expression to a Python expression string.
    Returns None if no valid expression found.
    Examples:
        "what is 5 plus 3"       → "5+3"
        "10 divided by 2"        → "10/2"
        "3 times 4 minus 1"      → "3*4-1"
    """
    # Remove filler words
    expr = text.lower()
    for filler in ['what is', 'what\'s', 'calculate', 'compute', 'equals', 'equal to', '?']:
        expr = expr.replace(filler, '')

    # Replace word operators with symbols
    for word, symbol in MATH_WORDS.items():
        expr = expr.replace(word, symbol)

    # Remove anything that isn't a digit, operator, dot, or space
    expr = re.sub(r'[^0-9+\-*/().\s]', '', expr).strip()

    # Remove multiple spaces
    expr = re.sub(r'\s+', '', expr)

    return expr if expr else None


def calculate(text: str) -> str:
    """
    Evaluates a spoken math expression and returns the result as a string.
    """
    expr = parse_math(text)
    if not expr:
        return '[System]: Sorry, I couldn\'t understand that math expression.'
    try:
        result = eval(expr)  # safe here — we stripped all non-math characters above
        # Format cleanly — remove unnecessary decimals
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f'[System]: The answer is {result}.'
    except ZeroDivisionError:
        return '[System]: Cannot divide by zero.'
    except Exception:
        return '[System]: Sorry, I couldn\'t calculate that.'
    

# ----------------------
# COMMAND LOGIC
# ----------------------

# Open file
with open('Audio/Transcribe.txt','a') as file:
    # loop for repeated audio recordings
    while True:

        # Check if OAuth/browser login completed between recordings
        if login_initiated and web_login.login_status == "success":
            login_initiated = False
            speak_text('[System]: Login successful.')
            continue
        
        # Skip audio processing if user is actively typing in browser
        if web_login.user_typing:
            typing_pause_until = time.time() + 20  # pause for 20 seconds
            web_login.user_typing = False           # reset flag immediately

        if time.time() < typing_pause_until and not login_initiated:
            time.sleep(0.5)
            continue

        # Record Audio
        heard=listen_text()

        # Check if OAuth/browser login completed DURING the 5s recording window
        # Discard whatever was recorded — it's irrelevant noise
        if login_initiated and web_login.login_status == "success":
            login_initiated = False
            speak_text('[System]: Login successful.')
            continue

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
            # Don't allow login if already logged in
            if web_login.login_status == "success":
                speak_text('[System]: You are already logged in.')
                continue
            
            # Don't start a new server if login is already in progress
            if login_initiated:
                speak_text('[System]: Login is already in progress.')
                continue
            
            web_login.login_status = 'waiting'
            login_initiated = True

            server_thread = threading.Thread(target=web_login.start_server)
            server_thread.daemon = True
            server_thread.start()

            webbrowser.open("http://localhost:5000")
            speak_text('[System]: Login page opened. Please log in via browser or say your confirmation word.')
            continue
        
        # ----------------------
        # LOGIN CONFIRMATION (audio password)
        # ----------------------
        elif login_initiated and clean_heard.strip() in confirmation_words:
            login_initiated = False
            # Check spoken word against database audio passwords
            matched, name = verify_audio(clean_heard.strip())
            if matched:
                speak_text(f'[System]: Welcome, {name}. Login confirmed.')
                web_login.login_status = "success"
            else:
                # Fall back to SECRET_AUD from .env for owner/admin
                if clean_heard.strip().lower() == SECRET_AUD.lower().strip():
                    speak_text('[System]: Login confirmed.')
                    web_login.login_status = "success"
                else:
                    speak_text('[System]: Audio password not recognised. Login cancelled.')
                    web_login.login_status = "failed"
            continue
        
        # ----------------------
        # SIGNUP — must be before cancellation block
        # ----------------------
        elif 'signup' in clean_heard or 'sign up' in clean_heard or 'register' in clean_heard:
            speak_text('[System]: Opening signup page...')
            threading.Thread(
                target=webbrowser.open,
                args=("http://localhost:5000/signup",),
                daemon=True
            ).start()
            continue
        
        # ----------------------
        # LOGIN CANCELLATION
        # Only triggers if login_initiated AND user hasn't logged in via browser yet.
        # We now also check login_status isn't already "success" (Google OAuth sets
        # this in the background before this block can run).
        # ----------------------
        elif login_initiated and web_login.login_status != "success":
            login_initiated = False
            speak_text('[System]: Login cancelled.')
            web_login.login_status = "failed"
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
            speak_text('[System]: You want to send an email?')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {clean_response}')

            if any(s in clean_response for s in affirmation):
                # Hand off to the full voice compose flow
                result = compose_email_by_voice()
                speak_text(result)

            elif any(s in clean_response for s in negation):
                speak_text('[System]: Ok, no email sent.')

            continue
        
        elif web_login.login_status=='success' and any(['latest','recent']) in clean_heard and(word in clean_heard for word in inbox_req):
            speak_text('[System]: Showing latest email')
            latest_email=get_top_senders(1)
            
            if 'error' in latest_email:
                speak_text(latest_email['error'])
                break

            else:
                summary_text=(
                    f'Your latest email.'
                    f'From: {latest_email['sender']}.'
                    f'Subject: {latest_email['subject']}.'
                    f'Date: {latest_email['date']}'
                    f'Summary: {latest_email['summary']}.'
                )
                if mail_item['details'].get('attachments'):
                        summary_text += f" Has attachments: {', '.join(mail_item['details']['attachments'])}."
        
                speak_text(summary_text)


        elif web_login.login_status == "success" and 'check' in clean_heard and any(word in clean_heard for word in inbox_req):
            speak_text('[System]: You want to check the inbox?')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {clean_response}')
        
            if any(s in clean_response for s in affirmation):
                inbox = get_top_senders()
        
                for i, mail_item in enumerate(inbox, 1):
                    if 'error' in mail_item:
                        speak_text(mail_item['error'])
                        break
                    
                    # Build a readable string for each email
                    summary_text = (
                        f"Email {i}. "
                        f"From: {mail_item['sender']}. "
                        f"Subject: {mail_item['subject']}. "
                        f"Date: {mail_item['date']}. "
                        f"Summary: {mail_item['summary']}."
                    )
        
                    # Mention attachments if any
                    if mail_item['details'].get('attachments'):
                        summary_text += f" Has attachments: {', '.join(mail_item['details']['attachments'])}."
        
                    speak_text(summary_text)
        
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
        # OTHER FEATURES
        # ----------------------
        elif 'time' in clean_heard and 'date' not in clean_heard:
            speak_text(f'[System]: The time is {datetime.datetime.now().strftime("%I:%M %p")}.')
        
        elif 'date' in clean_heard or ('what' in clean_heard and 'day' in clean_heard):
            speak_text(f'[System]: Today is {datetime.datetime.now().strftime("%A, %B %d, %Y")}.')
        
        elif 'joke' in clean_heard or 'funny' in clean_heard:
            speak_text(f'[System]: {random.choice(JOKES)}')
        
        elif any(w in clean_heard for w in ['calculate', 'what is', "what's", 'plus', 'minus', 'times', 'divided by']):
            speak_text(calculate(clean_heard))
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