from Audio.text_to_speech import speak_text
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders, suggest_reply
from Mail.email_sender import compose_email_by_voice, send_reply_direct
from Backend.database import verify_audio, get_user_by_email, update_name, update_password, update_audio, delete_user
import Mail.web_login as web_login
import threading, webbrowser
from dotenv import load_dotenv
import os,time, datetime, random, re
from Telegram.telegram import start_telegram_in_thread, telegram_get_messages, telegram_send_message, telegram_get_latest, set_notification_callback

load_dotenv()

SECRET_AUD = os.getenv('SECRET_AUD', '')

# ----------------------
# VARIABLES
# ----------------------
typing_pause_until = 0
awaiting_services = False
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

# ========================
# TELEGRAM VARIABLES
# ========================

API_ID   = int(os.getenv('TELEGRAM_API_ID', 0))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')

def on_new_telegram(sender, text):
    speak_text(f'[Telegram]: New message from {sender}: {text}')

def get_phone_by_voice():
    speak_text('[System]: Please say your Telegram phone number.')
    phone = listen_text(duration=8).strip()
    speak_text(f'[User]: {phone}')
    phone = phone.replace(' ', '').replace('-', '')
    return phone

def get_otp_by_voice():
    speak_text('[System]: Please say the OTP code sent to your Telegram app.')
    code = listen_text(duration=8).strip()
    speak_text(f'[User]: {code}')
    code = re.sub(r'[^0-9]', '', code)
    return code

set_notification_callback(on_new_telegram)

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
# SHARED REPLY HELPER
# ----------------------
def handle_reply(email_data: dict):
    """
    Shared logic for both reply commands:
    1. Suggests an AI reply based on email content
    2. User accepts or rejects
    3. If rejected, asks for custom voice reply
    4. Confirms before sending
    """
    reply_to = email_data['reply_to']
    subject  = email_data['subject']
    msg_id   = email_data['msg_id']
    body     = email_data.get('body', '')

    # Step 1 — Generate AI suggestion
    speak_text('[System]: Analysing email and generating a suggested reply...')
    suggestion = suggest_reply(reply_to, subject, body)

    if suggestion:
        speak_text(f'[System]: Suggested reply: {suggestion}. Shall I send this?')
        response = listen_text().lower().strip()
        speak_text(f'[User]: {response}')

        # User accepts suggestion
        if any(w in response for w in affirmation):
            speak_text('[System]: Sending suggested reply...')
            result = send_reply_direct(reply_to, subject, msg_id, suggestion)
            speak_text(result)
            return

        speak_text('[System]: Ok, let me take your custom reply instead.')

    else:
        speak_text('[System]: Could not generate a suggestion. Please dictate your reply.')

    # Step 2 — Custom voice reply
    result = reply_email_by_voice(reply_to, subject, msg_id)
    speak_text(result)

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
            awaiting_services = True
            speak_text('[System]: Please select your services on the dashboard.')
            continue

        if awaiting_services:
            print(f'[Debug] awaiting_services=True, selected={web_login.selected_services}')
            if web_login.selected_services:
                awaiting_services = False
                services = web_login.selected_services
        
                if 'telegram' in services:
                    speak_text('[System]: Starting Telegram.')
                    if API_ID and API_HASH:
                        start_telegram_in_thread(
                            phone_callback=get_phone_by_voice,
                            code_callback=get_otp_by_voice
                        )
        
                if 'gmail' in services:
                    speak_text('[System]: Gmail ready.')
        
                speak_text(f'[System]: Connected: {", ".join(services)}. Ready.')
            else:
                time.sleep(0.5)
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
        if login_initiated and web_login.login_status == "success":
            login_initiated = False
            awaiting_services = True
            speak_text('[System]: Please select your services on the dashboard.')
            continue

        if awaiting_services:
            print(f'[Debug] awaiting_services=True, selected={web_login.selected_services}')
            if web_login.selected_services:
                awaiting_services = False
                services = web_login.selected_services

                if 'telegram' in services:
                    speak_text('[System]: Starting Telegram.')
                    if API_ID and API_HASH:
                        start_telegram_in_thread(
                            phone_callback=get_phone_by_voice,
                            code_callback=get_otp_by_voice
                        )

                if 'gmail' in services:
                    speak_text('[System]: Gmail ready.')

                speak_text(f'[System]: Connected: {", ".join(services)}. Ready.')
            else:
                time.sleep(0.5)
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
            matched, name = verify_audio(clean_heard.strip())
            if matched:
                speak_text(f'[System]: Welcome, {name}. Login confirmed.')
                web_login.login_status = "success"
                web_login.app.config['current_email'] = os.getenv('EMAIL_USER', '')
                awaiting_services = True                          # ← ADD
                speak_text('[System]: Please select your services on the dashboard.')  # ← ADD
            else:
                if clean_heard.strip().lower() == SECRET_AUD.lower().strip():
                    speak_text('[System]: Login confirmed.')
                    web_login.login_status = "success"
                    web_login.app.config['current_email'] = os.getenv('EMAIL_USER', '')
                    awaiting_services = True                      # ← ADD
                    speak_text('[System]: Please select your services on the dashboard.')  # ← ADD
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
        
        elif (
            web_login.login_status=='success' 
            and any(word in clean_heard for word in ['latest', 'recent'])
            and any(word in clean_heard for word in inbox_req)):

            speak_text('[System]: Should I read from primary, promotions, updates or all emails?')
            cat_response = listen_text().lower().strip()
            speak_text(f'[User]: {cat_response}')

            if 'primary' in cat_response:
                category = 'PRIMARY'
            elif 'promo' in cat_response:
                category = 'PROMOTIONS'
            elif 'update' in cat_response:
                category = 'UPDATES'
            else:
                category = 'ALL'

            latest_emails = get_top_senders(1, category=category)
            latest_email = latest_emails[0] if latest_emails else {}
            
            if 'error' in latest_email:
                speak_text(latest_email['error'])
            else:
                summary_text = (
                    f'Your latest email. '
                    f'From: {latest_email["sender"]}. '
                    f'Subject: {latest_email["subject"]}. '
                    f'Date: {latest_email["date"]}. '
                    f'Summary: {latest_email["summary"]}.'
                )
                if latest_email['details'].get('attachments'):
                    summary_text += f" Has attachments: {', '.join(latest_email['details']['attachments'])}."
                speak_text(summary_text)


        elif web_login.login_status == "success" and 'check' in clean_heard and any(word in clean_heard for word in inbox_req):
            speak_text('[System]: You want to check the inbox?')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {clean_response}')
        
            if any(s in clean_response for s in affirmation):
                speak_text('[System]: Primary, promotions, updates or all?')
                cat_response = listen_text().lower().strip()
                if 'primary' in cat_response:
                    category = 'PRIMARY'
                elif 'promo' in cat_response:
                    category = 'PROMOTIONS'
                elif 'update' in cat_response:
                    category = 'UPDATES'
                else:
                    category = 'ALL'
                inbox = get_top_senders(category=category)
        
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
        
        # ========================
        # REPLY FEATURE
        # ========================
        # ----------------------
        # REPLY TO LATEST EMAIL
        # ----------------------
        elif (
            web_login.login_status == 'success'
            and 'reply' in clean_heard
            and 'latest' in clean_heard
            and any(w in clean_heard for w in mail_req)
        ):
            speak_text('[System]: Fetching the latest email.')
            email_data = get_email_for_reply(index=1)
        
            if 'error' in email_data:
                speak_text(f'[System]: {email_data["error"]}')
            else:
                speak_text(
                    f'[System]: Email from {email_data["reply_to"]}. '
                    f'Subject: {email_data["subject"]}.'
                )
                handle_reply(email_data)
            continue
        
        # ----------------------
        # REPLY TO SPECIFIC EMAIL
        # ----------------------
        elif (
            web_login.login_status == 'success'
            and 'reply' in clean_heard
            and any(w in clean_heard for w in mail_req)
        ):
            speak_text('[System]: Which email do you want to reply to? Say a number — 1 for latest, 2 for second latest.')
            num_heard = listen_text().lower().strip()
            speak_text(f'[User]: {num_heard}')
        
            num_map = {
                'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                '1': 1, '2': 2, '3': 3, '4': 4, '5': 5,
                'first': 1, 'second': 2, 'third': 3, 'latest': 1, 'last': 1,
            }
            index = next((num_map[w] for w in num_map if w in num_heard), 1)
        
            speak_text(f'[System]: Fetching email number {index}.')
            email_data = get_email_for_reply(index=index)
        
            if 'error' in email_data:
                speak_text(f'[System]: {email_data["error"]}')
            else:
                speak_text(
                    f'[System]: Email from {email_data["reply_to"]}. '
                    f'Subject: {email_data["subject"]}.'
                )
                handle_reply(email_data)
            continue    
        # ========================
        # TELEGRAM FEATURES
        # ========================

        # ----------------------
        # TELEGRAM — CHECK INBOX
        # ----------------------
        elif web_login.login_status == "success" and 'telegram' in clean_heard and any(w in clean_heard for w in inbox_req + ['message', 'messages']):
            speak_text('[System]: Fetching your Telegram messages.')
            messages = telegram_get_messages(5)
            if not messages:
                speak_text('[System]: No Telegram messages found.')
            else:
                for i, msg in enumerate(messages, 1):
                    unread = f"{msg['unread']} unread." if msg['unread'] else ''
                    speak_text(
                        f"Telegram {i}. "
                        f"From: {msg['name']}. "
                        f"{unread}"
                        f"Message: {msg['message']}. "
                        f"Date: {msg['date']}."
                    )
            continue
        
        # ----------------------
        # TELEGRAM — LATEST MESSAGE
        # ----------------------
        elif web_login.login_status == "success" and 'telegram' in clean_heard and any(w in clean_heard for w in ['latest', 'recent']):
            speak_text('[System]: Getting your latest Telegram message.')
            msg = telegram_get_latest()
            if msg:
                speak_text(
                    f"[System]: Latest Telegram message. "
                    f"From: {msg['name']}. "
                    f"Message: {msg['message']}. "
                    f"Date: {msg['date']}."
                )
            else:
                speak_text('[System]: No Telegram messages found.')
            continue
        
        # ----------------------
        # TELEGRAM — SEND MESSAGE
        # ----------------------
        elif web_login.login_status == "success" and 'telegram' in clean_heard and 'send' in clean_heard:
            speak_text('[System]: Who do you want to send a Telegram message to?')
            recipient = listen_text().strip()
            speak_text(f'[User]: {recipient}')
            speak_text('[System]: What is your message?')
            message = listen_text(duration=10).strip()
            speak_text(f'[User]: {message}')
            speak_text(f'[System]: Sending to {recipient}: {message}. Confirm?')
            confirm = listen_text().lower().strip()
            if any(w in confirm for w in affirmation):
                success, result = telegram_send_message(recipient, message)
                speak_text(f'[System]: {result}')
            else:
                speak_text('[System]: Telegram message cancelled.')
            continue

        # ========================
        # PROFILE MANAGEMENT 
        # ========================
        elif web_login.login_status == "success" and 'profile' in clean_heard:
    
            # Get current logged in email from session
            current_email = web_login.app.config.get('current_email', '')
            if not current_email:
                speak_text('[System]: Could not find your profile. Please log in again.')
                continue

            speak_text('[System]: What would you like to do? Say view, change name, change password, change audio password, or delete account.')
            response = listen_text()
            clean_response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {clean_response}')

            # ----------------------
            # View Profile
            # ----------------------
            if 'view' in clean_response or 'show' in clean_response or 'what' in clean_response:
                user = get_user_by_email(current_email)
                if user:
                    speak_text(
                        f'[System]: Your profile. '
                        f'Name: {user["name"]}. '
                        f'Email: {user["email"]}. '
                        f'Account created on: {user["created_at"]}.'
                    )
                else:
                    speak_text('[System]: Profile not found in database. You may have logged in via Google.')

            # ----------------------
            # Change Name
            # ----------------------
            elif 'name' in clean_response:
                speak_text('[System]: What would you like your new name to be?')
                new_name = listen_text().strip()
                speak_text(f'[User]: {new_name}')
                if new_name:
                    success, msg = update_name(current_email, new_name)
                    speak_text(f'[System]: {msg}')
                else:
                    speak_text('[System]: No name received. Cancelled.')

            # ----------------------
            # Change Password
            # ----------------------
            elif 'password' in clean_response and 'audio' not in clean_response:
                speak_text('[System]: Please say your current password.')
                old_pass = listen_text().strip()
                speak_text('[System]: Please say your new password.')
                new_pass = listen_text().strip()
                if old_pass and new_pass:
                    success, msg = update_password(current_email, old_pass, new_pass)
                    speak_text(f'[System]: {msg}')
                else:
                    speak_text('[System]: Password change cancelled.')

            # ----------------------
            # Change Audio Password
            # ----------------------
            elif 'audio' in clean_response:
                speak_text('[System]: Please say your new secret audio password.')
                new_audio = listen_text().strip()
                speak_text(f'[User]: {new_audio}')
                if new_audio:
                    success, msg = update_audio(current_email, new_audio)
                    speak_text(f'[System]: {msg}')
                    # Update confirmation_words with new audio
                    if success and new_audio.lower() not in confirmation_words:
                        confirmation_words.append(new_audio.lower())
                else:
                    speak_text('[System]: No audio password received. Cancelled.')

            # ----------------------
            # Delete Account
            # ----------------------
            elif 'delete' in clean_response:
                speak_text('[System]: Are you sure you want to delete your account? This cannot be undone. Say yes to confirm.')
                confirm = listen_text().lower().strip()
                speak_text(f'[User]: {confirm}')
                if any(w in confirm for w in affirmation):
                    speak_text('[System]: Please say your password to confirm deletion.')
                    password = listen_text().strip()
                    success, msg = delete_user(current_email, password)
                    speak_text(f'[System]: {msg}')
                    if success:
                        web_login.login_status = 'waiting'
                        login_initiated = False
                else:
                    speak_text('[System]: Account deletion cancelled.')

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