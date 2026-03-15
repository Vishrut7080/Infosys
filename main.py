# # =================================================
# IMPORTS
# # =================================================
from Audio.text_to_speech import speak_text as _speak_text_orig
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders
from Mail.email_sender import compose_email_by_voice, send_reply_direct, reply_email_by_voice
from Backend.database import verify_audio, get_user_by_email, update_name, update_password, update_audio, delete_user
from Mail.web_login import  push_to_feed, push_nav_command
import Mail.web_login as web_login
import threading, webbrowser, requests
from dotenv import load_dotenv
import os, time, datetime, random, re
from Telegram.telegram import start_telegram_in_thread, telegram_get_messages, telegram_send_message, telegram_get_latest, set_notification_callback
from Whatsapp.whatsapp import whatsapp_send_message, whatsapp_get_messages

load_dotenv()

SECRET_AUD = os.getenv('SECRET_AUD', '')

# ----------------------
# VARIABLES
# ----------------------
force_lang = None 
user_lang = 'en' # tracks current user language: 'en' or 'hi'
typing_pause_until = 0
awaiting_services  = False
heard              = ""
login_initiated    = False

bye_en = '[System]: Goodbye! Take care.'
bye_hi = '[System]: अलविदा! अपना ख्याल रखें।'

# # =================================================
# HANDLER FUNCTION
# # =================================================
def spoken_pin_to_digits(spoken: str) -> str:
    """Convert spoken PIN like 'one two three four' to '1234'."""
    word_to_digit = {
        'zero':'0','one':'1','two':'2','three':'3','four':'4',
        'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
        'शून्य':'0','एक':'1','दो':'2','तीन':'3','चार':'4',
        'पाँच':'5','छः':'6','सात':'7','आठ':'8','नौ':'9',
    }
    result = spoken.strip().lower()
    for word, digit in word_to_digit.items():
        result = result.replace(word, digit)
    return ''.join(c for c in result if c.isdigit())

# ----------------------
# BILINGUAL RESPONSES
# ----------------------
RESPONSES = {
    'greeting':            {'en': '[System]: Hi! How can I help you?',
                            'hi': '[System]: नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?'},
    'already_logged_in':   {'en': '[System]: You are already logged in.',
                            'hi': '[System]: आप पहले से लॉगिन हैं।'},
    'login_in_progress':   {'en': '[System]: Login is already in progress.',
                            'hi': '[System]: लॉगिन पहले से जारी है।'},
    'login_opened':        {'en': '[System]: Login page opened. Please log in via browser or say your confirmation word.',
                            'hi': '[System]: लॉगिन पेज खुल गया। कृपया ब्राउज़र से लॉगिन करें या पासवर्ड बोलें।'},
    'login_confirmed':     {'en': '[System]: Login confirmed. Please select your services on the dashboard.',
                            'hi': '[System]: लॉगिन सफल। कृपया डैशबोर्ड पर सेवाएं चुनें।'},
    'login_failed':        {'en': '[System]: Audio password not recognised. Login cancelled.',
                            'hi': '[System]: ऑडियो पासवर्ड पहचाना नहीं गया। लॉगिन रद्द।'},
    'login_cancelled':     {'en': '[System]: Login cancelled.',
                            'hi': '[System]: लॉगिन रद्द किया गया।'},
    'select_services':     {'en': '[System]: Please select your services on the dashboard.',
                            'hi': '[System]: कृपया डैशबोर्ड पर अपनी सेवाएं चुनें।'},
    'signup_opening':      {'en': '[System]: Opening signup page...',
                            'hi': '[System]: साइनअप पेज खोल रहे हैं...'},
    'not_logged_in':       {'en': '[System]: Please log in first.',
                            'hi': '[System]: कृपया पहले लॉगिन करें।'},
    'logout_success':      {'en': '[System]: You have been logged out successfully.',
                            'hi': '[System]: आप सफलतापूर्वक लॉगआउट हो गए।'},
    'not_logged_in_lo':    {'en': '[System]: You are not currently logged in.',
                            'hi': '[System]: आप अभी लॉगिन नहीं हैं।'},
    'not_understood':      {'en': '[System]: Please try a different command.',
                            'hi': '[System]: कृपया कोई अलग कमांड आज़माएं।'},
    'tg_fetching':         {'en': '[System]: Fetching your Telegram messages.',
                            'hi': '[System]: आपके Telegram संदेश लाए जा रहे हैं।'},
    'tg_none':             {'en': '[System]: No Telegram messages found.',
                            'hi': '[System]: कोई Telegram संदेश नहीं मिला।'},
    'tg_reply_prompt':     {'en': '[System]: Would you like to reply to this message?',
                            'hi': '[System]: क्या आप इस संदेश का जवाब देना चाहते हैं?'},
    'tg_next':             {'en': '[System]: Okay, moving to the next message.',
                            'hi': '[System]: ठीक है, अगले संदेश पर जा रहे हैं।'},
    'tg_latest':           {'en': '[System]: Getting your latest Telegram message.',
                            'hi': '[System]: आपका नवीनतम Telegram संदेश लाया जा रहा है।'},
    'tg_who':              {'en': '[System]: Who do you want to send a Telegram message to?',
                            'hi': '[System]: आप किसे Telegram संदेश भेजना चाहते हैं?'},
    'tg_what':             {'en': '[System]: What is your message?',
                            'hi': '[System]: आपका संदेश क्या है?'},
    'tg_confirm_send':     {'en': '[System]: Sending. Please confirm.',
                            'hi': '[System]: भेज रहे हैं। कृपया पुष्टि करें।'},
    'tg_cancelled':        {'en': '[System]: Telegram message cancelled.',
                            'hi': '[System]: Telegram संदेश रद्द किया गया।'},
    'tg_no_recipient':     {'en': '[System]: I did not catch the recipient.',
                            'hi': '[System]: प्राप्तकर्ता समझ नहीं आया।'},
    'tg_empty_msg':        {'en': '[System]: Message was empty. Cancelled.',
                            'hi': '[System]: संदेश खाली था। रद्द किया गया।'},
    'tg_auth_prompt':      {'en': '[System]: Telegram needs authorization. Please say your secret password to open the login page.',
                            'hi': '[System]: Telegram को अनुमति चाहिए। लॉगिन पेज खोलने के लिए पासवर्ड बोलें।'},
    'tg_auth_ok':          {'en': '[System]: Confirmed. Opening Telegram login page.',
                            'hi': '[System]: पुष्टि हुई। Telegram लॉगिन पेज खुल रहा है।'},
    'tg_auth_fail':        {'en': '[System]: Incorrect password. Telegram not connected.',
                            'hi': '[System]: गलत पासवर्ड। Telegram कनेक्ट नहीं हुआ।'},
    'tg_auto':             {'en': '[System]: Telegram connected automatically.',
                            'hi': '[System]: Telegram स्वचालित रूप से जुड़ गया।'},
    'tg_starting':         {'en': '[System]: Starting Telegram.',
                            'hi': '[System]: Telegram शुरू हो रहा है।'},
    'gmail_ready':         {'en': '[System]: Gmail ready.',
                            'hi': '[System]: Gmail तैयार है।'},
    'email_send_prompt':   {'en': '[System]: You want to send an email?',
                            'hi': '[System]: क्या आप ईमेल भेजना चाहते हैं?'},
    'email_cancelled':     {'en': '[System]: Ok, no email sent.',
                            'hi': '[System]: ठीक है, कोई ईमेल नहीं भेजा।'},
    'inbox_prompt':        {'en': '[System]: You want to check the inbox?',
                            'hi': '[System]: क्या आप इनबॉक्स देखना चाहते हैं?'},
    'inbox_category':      {'en': '[System]: Primary, promotions, updates or all?',
                            'hi': '[System]: प्राइमरी, प्रमोशन, अपडेट या सभी?'},
    'inbox_ok':            {'en': '[System]: Ok, thanks for confirming.',
                            'hi': '[System]: ठीक है, धन्यवाद।'},
    'cat_prompt':          {'en': '[System]: Should I read from primary, promotions, updates or all emails?',
                            'hi': '[System]: प्राइमरी, प्रमोशन, अपडेट या सभी ईमेल पढ़ूं?'},
    'reply_fetching':      {'en': '[System]: Fetching the latest email.',
                            'hi': '[System]: नवीनतम ईमेल लाया जा रहा है।'},
    'reply_which':         {'en': '[System]: Which email do you want to reply to? Say a number — 1 for latest.',
                            'hi': '[System]: किस ईमेल का जवाब देना है? नंबर बोलें — 1 सबसे नया।'},
    'profile_prompt':      {'en': '[System]: What would you like to do? Say view, change name, change password, change audio password, or delete account.',
                            'hi': '[System]: आप क्या करना चाहते हैं? व्यू, नाम बदलें, पासवर्ड बदलें, ऑडियो पासवर्ड बदलें, या अकाउंट डिलीट करें।'},
    'profile_not_found':   {'en': '[System]: Could not find your profile. Please log in again.',
                            'hi': '[System]: आपका प्रोफ़ाइल नहीं मिला। कृपया फिर से लॉगिन करें।'},
    'profile_google':      {'en': '[System]: Profile not found in database. You may have logged in via Google.',
                            'hi': '[System]: डेटाबेस में प्रोफ़ाइल नहीं मिला। आपने Google से लॉगिन किया होगा।'},
    'name_prompt':         {'en': '[System]: What would you like your new name to be?',
                            'hi': '[System]: आपका नया नाम क्या होगा?'},
    'name_cancelled':      {'en': '[System]: No name received. Cancelled.',
                            'hi': '[System]: कोई नाम नहीं मिला। रद्द किया गया।'},
    'pass_current':        {'en': '[System]: Please say your current password.',
                            'hi': '[System]: कृपया अपना मौजूदा पासवर्ड बोलें।'},
    'pass_new':            {'en': '[System]: Please say your new password.',
                            'hi': '[System]: कृपया अपना नया पासवर्ड बोलें।'},
    'pass_cancelled':      {'en': '[System]: Password change cancelled.',
                            'hi': '[System]: पासवर्ड बदलना रद्द किया गया।'},
    'audio_prompt':        {'en': '[System]: Please say your new secret audio password.',
                            'hi': '[System]: कृपया अपना नया ऑडियो पासवर्ड बोलें।'},
    'audio_cancelled':     {'en': '[System]: No audio password received. Cancelled.',
                            'hi': '[System]: कोई ऑडियो पासवर्ड नहीं मिला। रद्द किया गया।'},
    'delete_confirm':      {'en': '[System]: Are you sure you want to delete your account? Say yes to confirm.',
                            'hi': '[System]: क्या आप वाकई अकाउंट डिलीट करना चाहते हैं? हाँ बोलें।'},
    'delete_pass':         {'en': '[System]: Please say your password to confirm deletion.',
                            'hi': '[System]: डिलीट की पुष्टि के लिए पासवर्ड बोलें।'},
    'delete_cancelled':    {'en': '[System]: Account deletion cancelled.',
                            'hi': '[System]: अकाउंट डिलीट रद्द किया गया।'},
    'suggest_generating':  {'en': '[System]: Analysing and generating a suggested reply...',
                            'hi': '[System]: सुझाया गया जवाब तैयार किया जा रहा है...'},
    'suggest_send':        {'en': 'Shall I send this?',
                            'hi': 'क्या मैं यह भेजूं?'},
    'suggest_sending':     {'en': '[System]: Sending suggested reply...',
                            'hi': '[System]: सुझाया गया जवाब भेजा जा रहा है...'},
    'suggest_custom':      {'en': '[System]: Ok, let me take your custom reply instead.',
                            'hi': '[System]: ठीक है, आपका खुद का जवाब लेते हैं।'},
    'suggest_failed':      {'en': '[System]: Could not generate a suggestion. Please dictate your reply.',
                            'hi': '[System]: सुझाव नहीं बन सका। कृपया अपना जवाब बोलें।'},
}

HINDI_COMMAND_MAP = {
    # login variants
    'लोगें':   'login',
    'लॉगें':   'login',
    'लॉग':     'login',
    'लोगिन':   'login',
    # logout variants
    'लॉगआउट': 'logout',
    'लॉग आउट':'logout',
    # greeting variants  
    'नमस्ते':  'hello',
    'हेलो':    'hello',
    # goodbye
    'अलविदा':  'goodbye',
    'बाय':     'bye',
    # yes/no
    'हाँ':     'yes',
    'हां':     'yes',
    'नहीं':    'no',
    # email
    'ईमेल':    'email',
    'मेल':     'mail',
    # time/date
    'समय':     'time',
    'तारीख':   'date',
    # joke
    'मज़ाक':   'joke',
    'जोक':     'joke',
    # profile
    'प्रोफ़ाइल': 'profile',
    # telegram
    'टेलीग्राम': 'telegram'
}

# -------------------------------------------------
# Navigation Commands
# -------------------------------------------------
NAV_PHRASES = [
    'go to dashboard', 'open dashboard', 'show dashboard',
    'go to profile',   'open profile',   'show profile',   'my profile',
    'go to inbox',     'open inbox',     'show inbox',     'unified inbox',
    'go to messages',  'open messages',  'show messages',
    'select gmail',    'enable gmail',    'add gmail',
    'select telegram', 'enable telegram', 'add telegram',
    'deselect gmail',  'disable gmail',   'remove gmail',
    'deselect telegram','disable telegram','remove telegram',
    'save services',   'confirm services','save and continue',
    'select both', 'enable both', 'both services',
    'select gmail and telegram', 'select telegram and gmail',
    'select whatsapp',  'enable whatsapp',  'add whatsapp',
    'deselect whatsapp','disable whatsapp', 'remove whatsapp',
    'select all',       'enable all',       'all services',
]

def normalize_hindi(text: str) -> str:
    """Replace Hindi words with English equivalents for command matching."""
    for hindi, english in HINDI_COMMAND_MAP.items():
        text = text.replace(hindi, english)
    return text

def r(key):
    """Return response string in current user language."""
    return RESPONSES.get(key, {}).get(user_lang, RESPONSES[key]['en'])

# # =================================================
# CHANGED SPEAK TEXT
# # =================================================
def speak_text(text: str, lang: str = 'en'):
    """Wrapper: speaks the text AND pushes it to the live feed."""
    push_to_feed(text)
    _speak_text_orig(text, lang=lang)

def log_activity(action: str, detail: str = ''):
    """Log to admin DB — only when logged in."""
    if web_login.login_status != 'success':
        return
    email = web_login.app.config.get('current_email', '')
    if email:
        from Backend.database import log_activity as _log
        _log(email, action, detail)

# ----------------------
# Commands (bilingual)
# ----------------------
mail_req        = ['mail', 'email', 'message', 'मेल', 'ईमेल', 'संदेश']
inbox_req       = ['inbox', 'mail', 'mails', 'इनबॉक्स', 'मेल']
affirmation     = ['yes', 'ok', 'yah', 'ya', 'want to', 'हाँ', 'ठीक है', 'हां', 'भेजो']
negation        = ['no', 'nah', 'nope', "don't want to", 'नहीं', 'मत भेजो']
greeting        = ['hi', 'hello', 'hey', 'नमस्ते', 'हेलो', 'हाय']
ending          = ['goodbye', 'bye', 'exit', 'see you later', 'अलविदा', 'बाय', 'बंद करो']
logout_commands = ['logout', 'log out', 'sign out', 'signout', 'लॉगआउट', 'साइन आउट']
confirmation_words = ['correct', 'confirm', 'yes', 'हाँ', 'सही']

if SECRET_AUD:
    confirmation_words.append(SECRET_AUD.lower().strip())

def on_new_telegram(sender, text):
    speak_text(f'[Telegram]: New message from {sender}: {text}')

set_notification_callback(on_new_telegram)

# ----------------------
# JOKES BANK
# ----------------------
JOKES_EN = [
    "Why do programmers prefer dark mode? Because light attracts bugs!",
    "Why did the computer go to the doctor? It had a virus!",
    "I told my computer I needed a break. Now it won't stop sending me Kit Kat ads.",
    "Why did the programmer quit his job? Because he didn't get arrays.",
    "How many programmers does it take to change a light bulb? None — that's a hardware problem.",
    "Why do Java developers wear glasses? Because they don't C sharp.",
    "A SQL query walks into a bar and asks two tables: Can I join you?",
    "Why was the math book sad? It had too many problems.",
    "What did zero say to eight? Nice belt!",
    "Why do scientists rarely tell jokes? Because all the good ones Argon.",
]

JOKES_HI = [
    "प्रोग्रामर डार्क मोड क्यों पसंद करते हैं? क्योंकि रोशनी में बग आते हैं!",
    "कंप्यूटर डॉक्टर के पास क्यों गया? उसे वायरस हो गया था!",
    "मैंने कंप्यूटर से कहा मुझे ब्रेक चाहिए, अब वो Kit Kat के विज्ञापन भेजता रहता है।",
    "प्रोग्रामर ने नौकरी क्यों छोड़ी? उसे arrays समझ नहीं आई।",
    "गणित की किताब उदास क्यों थी? उसमें बहुत सारी समस्याएं थीं।",
]

# ----------------------
# CALCULATOR HELPER
# ----------------------
MATH_WORDS = {
    'plus': '+', 'add': '+', 'minus': '-', 'subtract': '-',
    'times': '*', 'multiplied by': '*', 'multiply': '*',
    'divided by': '/', 'divide': '/', 'over': '/',
    'power': '**', 'squared': '**2', 'cubed': '**3',
    'percent of': '/100*',
    'जमा': '+', 'घटा': '-', 'गुणा': '*', 'भाग': '/',
}

def parse_math(text: str) -> str | None:
    expr = text.lower()
    for filler in ['what is', "what's", 'calculate', 'compute', 'equals', 'equal to', '?',
                   'क्या है', 'बताओ', 'हिसाब', 'कितना']:
        expr = expr.replace(filler, '')
    for word, symbol in MATH_WORDS.items():
        expr = expr.replace(word, symbol)
    expr = re.sub(r'[^0-9+\-*/().\s]', '', expr).strip()
    expr = re.sub(r'\s+', '', expr)
    return expr if expr else None

def calculate(text: str) -> str:
    expr = parse_math(text)
    if not expr:
        return r('not_understood')
    try:
        result = eval(expr)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f'[System]: उत्तर है {result}।' if user_lang == 'hi' else f'[System]: The answer is {result}.'
    except ZeroDivisionError:
        return '[System]: शून्य से भाग नहीं हो सकता।' if user_lang == 'hi' else '[System]: Cannot divide by zero.'
    except Exception:
        return r('not_understood')


# ----------------------
# REPLY HELPERS
# ----------------------
def generate_local_reply(message: str):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma3:1b",
                "prompt": f"""You are an AI assistant helping reply to messages.
Write a short natural reply (1-2 sentences).
Message:
{message}
Reply:""",
                "stream": False
            },
            timeout=30
        )
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print("Ollama error:", e)
        return None

def handle_reply(email_data: dict):
    reply_to = email_data['sender']
    subject  = email_data['subject']
    body     = email_data.get('summary', '')

    speak_text(r('suggest_generating'), lang=user_lang)
    suggestion = generate_local_reply(f"From: {reply_to}\nSubject: {subject}\n\n{body}")

    if suggestion:
        speak_text(f'[System]: {suggestion}. {r("suggest_send")}', lang=user_lang)
        response, _ = listen_text()
        response = response.lower().strip()
        speak_text(f'[User]: {response}')
        if any(w in response for w in affirmation):
            speak_text(r('suggest_sending'), lang=user_lang)
            result = reply_email_by_voice(reply_to, subject, email_data.get('msg_id', ''))
            speak_text(result)
            return
        speak_text(r('suggest_custom'), lang=user_lang)
    else:
        speak_text(r('suggest_failed'), lang=user_lang)

    result = reply_email_by_voice(reply_to, subject, email_data.get('msg_id', ''))
    speak_text(result)

def handle_telegram_reply(recipient: str, original_message: str):
    speak_text(r('suggest_generating'), lang=user_lang)
    suggestion = generate_local_reply(original_message)

    if suggestion:
        speak_text(f'[System]: {suggestion}. {r("suggest_send")}', lang=user_lang)
        confirm, _ = listen_text()
        confirm = confirm.lower().strip()
        speak_text(f'[User]: {confirm}')
        if any(w in confirm for w in affirmation):
            success, result = telegram_send_message(recipient, suggestion)
            speak_text(f'[System]: {result}')
            return
        speak_text(r('suggest_custom'), lang=user_lang)
    else:
        speak_text(r('suggest_failed'), lang=user_lang)

    message, _ = listen_text(duration=10)
    message = message.strip()
    speak_text(f'[User]: {message}')
    speak_text(r('tg_confirm_send'), lang=user_lang)
    confirm, _ = listen_text()
    if any(w in confirm.lower() for w in affirmation):
        success, result = telegram_send_message(recipient, message)
        speak_text(f'[System]: {result}')
    else:
        speak_text(r('tg_cancelled'), lang=user_lang)


# ----------------------
# COMMAND LOOP
# ----------------------
with open('Audio/Transcribe.txt', 'a', encoding='utf-8') as file:
    while True:

        # ── AUTO-LOGIN from signup ──────────────────────────
        if web_login.login_from_signup and not login_initiated and web_login.login_status != 'success':
            web_login.login_from_signup = False
            login_initiated = True
            speak_text('[System]: Welcome! Say your audio password to complete login.', lang=user_lang)
            continue

        # Check OAuth login completed between recordings
        if login_initiated and web_login.login_status == "success":
            login_initiated = False
            awaiting_services = True            
            continue

        if awaiting_services:
            if web_login.selected_services:
                services = web_login.selected_services
                current_email = web_login.app.config.get('current_email', '')

                # ── PIN verification for each selected service ──
                verified_services = []
                for service in services:
                    speak_text(
                        f'[System]: Please say your {service.capitalize()} PIN to authorise.',
                        lang=user_lang
                    )
                    pin_heard, _ = listen_text(duration=8)
                    pin_heard = pin_heard.strip().lower()
                    speak_text(f'[User]: {pin_heard}')

                    # Convert spoken numbers to digits — "one two three" → "123"
                    word_to_digit = {
                        'zero':'0','one':'1','two':'2','three':'3','four':'4',
                        'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
                        'शून्य':'0','एक':'1','दो':'2','तीन':'3','चार':'4',
                        'पाँच':'5','छः':'6','सात':'7','आठ':'8','नौ':'9',
                    }
                    pin_digits = pin_heard
                    for word, digit in word_to_digit.items():
                        pin_digits = pin_digits.replace(word, digit)
                    # Remove all non-digit characters
                    pin_digits = ''.join(c for c in pin_digits if c.isdigit())

                    from Backend.database import verify_pin
                    if verify_pin(current_email, service, pin_digits):
                        speak_text(
                            f'[System]: {service.capitalize()} PIN verified.' if user_lang == 'en'
                            else f'[System]: {service.capitalize()} PIN सही है।',
                            lang=user_lang
                        )
                        verified_services.append(service)
                    else:
                        speak_text(
                            f'[System]: Incorrect PIN for {service.capitalize()}. '
                            f'{service.capitalize()} will not be connected.' if user_lang == 'en'
                            else f'[System]: {service.capitalize()} का PIN गलत है। कनेक्ट नहीं होगा।',
                            lang=user_lang
                        )

                if not verified_services:
                    speak_text(
                        '[System]: No services verified. Please try again.' if user_lang == 'en'
                        else '[System]: कोई सेवा सत्यापित नहीं हुई। कृपया पुनः प्रयास करें।',
                        lang=user_lang
                    )
                    awaiting_services = False
                    continue
                
                # Update selected services to only verified ones
                web_login.selected_services = verified_services
                awaiting_services = False
                services = verified_services

                if 'telegram' in services:
                    speak_text(r('tg_starting'), lang=user_lang)
                    api_id   = int(os.getenv('TELEGRAM_API_ID', 0))
                    api_hash = os.getenv('TELEGRAM_API_HASH', '')
                    if api_id and api_hash:
                        start_telegram_in_thread()
                        time.sleep(2)
                        from Telegram.telegram import _client
                        if _client and _client.is_connected():
                            import asyncio as _asyncio
                            from Telegram.telegram import _loop as tg_loop
                            if tg_loop:
                                fut = _asyncio.run_coroutine_threadsafe(
                                    _client.is_user_authorized(), tg_loop
                                )
                                authorized = fut.result(timeout=5)
                            else:
                                authorized = False
                        else:
                            authorized = False

                        if not authorized:
                            speak_text(r('tg_auth_prompt'), lang=user_lang)
                            auth_word, _ = listen_text(duration=8)
                            auth_word = auth_word.lower().strip()
                            speak_text(f'[User]: {auth_word}')
                            if auth_word == SECRET_AUD.lower().strip():
                                speak_text(r('tg_auth_ok'), lang=user_lang)
                                webbrowser.open('http://localhost:5000/telegram-auth')
                            else:
                                speak_text(r('tg_auth_fail'), lang=user_lang)
                        else:
                            speak_text(r('tg_auto'), lang=user_lang)

                if 'gmail' in services:
                    speak_text(r('gmail_ready'), lang=user_lang)

                if 'whatsapp' in services:
                    speak_text('[System]: WhatsApp ready.', lang=user_lang)

                connected_msg = (
                    f'[System]: Connected: {", ".join(services)}. Ready.'
                    if user_lang == 'en'
                    else f'[System]: कनेक्ट हुआ: {", ".join(services)}। तैयार।'
                )
                speak_text(connected_msg, lang=user_lang)
                continue
            else:
                time.sleep(0.5)           

        # Typing pause
        if web_login.user_typing:
            typing_pause_until = time.time() + 5
            web_login.user_typing = False
        
        # ── Pause while signup page is open ──
        if web_login.signup_open:
            time.sleep(0.5)
            continue

        if time.time() < typing_pause_until and not login_initiated:
            time.sleep(0.5)
            continue

        # ── RECORD + DETECT LANGUAGE ──────────────────
        heard, user_lang = listen_text(force_lang=force_lang)

        # Check OAuth completed DURING recording
        if login_initiated and web_login.login_status == "success":
            login_initiated = False
            awaiting_services = True
            speak_text(r('select_services'), lang=user_lang)
            continue

        if awaiting_services:
            if web_login.selected_services:
                awaiting_services = False
                services = web_login.selected_services
                if 'gmail' in services:
                    speak_text(r('gmail_ready'), lang=user_lang)
                if 'whatsapp' in services:
                    speak_text('[System]: WhatsApp ready.', lang=user_lang)
                connected_msg = f'[System]: Connected: {", ".join(services)}. Ready.' if user_lang == 'en' \
                    else f'[System]: कनेक्ट हुआ: {", ".join(services)}। तैयार।'
                speak_text(connected_msg, lang=user_lang)
                continue
            else:
                time.sleep(0.5)                

        speak_text(f'[User]: {heard}')
        clean_heard = heard.lower().strip().replace('.', '')
        clean_heard = normalize_hindi(clean_heard)
        file.write(f'{clean_heard}\n')

        _is_nav = False
        for phrase in NAV_PHRASES:
            if phrase in clean_heard:
                push_nav_command(clean_heard)
                _is_nav = True
                break

        # ── GREETING ──────────────────────────────────
        if any(word == clean_heard or clean_heard.startswith(word + ' ') or clean_heard.endswith(' ' + word) for word in greeting):
            speak_text(r('greeting'), lang=user_lang)

        elif any(x in clean_heard for x in ['hindi mode', 'हिंदी मोड', 'इंदी मोड', 'अन्दी मुड', 'hindi mod', 'hindi mo']):
            force_lang = 'hi'
            user_lang = 'hi'
            speak_text('[System]: हिंदी मोड चालू।', lang='hi')
            continue
        
        elif 'english mode' in clean_heard or 'switch to english' in clean_heard:
            force_lang = 'en'
            speak_text('[System]: Switched to English mode.', lang='en')
            continue

        # ── LOGIN ─────────────────────────────────────
        elif 'login' in clean_heard or 'log in' in clean_heard or 'लॉगिन' in clean_heard:
            if web_login.login_status == "success":
                speak_text(r('already_logged_in'), lang=user_lang)
                continue
            if login_initiated:
                speak_text(r('login_in_progress'), lang=user_lang)
                continue
            web_login.login_status = 'waiting'
            login_initiated = True
            server_thread = threading.Thread(target=web_login.start_server)
            server_thread.daemon = True
            server_thread.start()
            webbrowser.open("http://localhost:5000")
            speak_text(r('login_opened'), lang=user_lang)
            continue
           
        # ── SIGNUP ────────────────────────────────────
        elif 'signup' in clean_heard or 'sign up' in clean_heard or 'register' in clean_heard or 'साइनअप' in clean_heard:
            login_initiated = False           # ← reset login state
            web_login.login_status = 'waiting'
            speak_text(r('signup_opening'), lang=user_lang)
            threading.Thread(target=webbrowser.open, args=("http://localhost:5000/signup",), daemon=True).start()
            continue

        # ── LOGIN CONFIRMATION (audio password) ───────
        elif login_initiated and web_login.login_status != "success":
            login_initiated = False
            matched, name, matched_email = verify_audio(clean_heard.strip())
            if matched:
                welcome = f'[System]: Welcome, {name}. Login confirmed.' if user_lang == 'en' \
                    else f'[System]: स्वागत है, {name}। लॉगिन सफल।'
                speak_text(welcome, lang=user_lang)
                web_login.login_status = "success"
                web_login.app.config['current_email'] = matched_email
                web_login.apply_user_credentials(matched_email)
                awaiting_services = True
                speak_text(r('select_services'), lang=user_lang)
            else:
                speak_text(r('login_failed'), lang=user_lang)
                web_login.login_status = "failed"
            continue

        # ── TELEGRAM — SEND ───────────────────────────
        elif web_login.login_status == "success" and 'telegram' in clean_heard and ('send' in clean_heard or 'भेजो' in clean_heard):
            speak_text(r('tg_who'), lang=user_lang)
            recipient, _ = listen_text()
            recipient = recipient.strip()
            if not recipient:
                speak_text(r('tg_no_recipient'), lang=user_lang)
                continue
            speak_text(f'[User]: {recipient}')
            speak_text(r('tg_what'), lang=user_lang)
            message, _ = listen_text(duration=10)
            message = message.strip()
            if not message:
                speak_text(r('tg_empty_msg'), lang=user_lang)
                continue
            speak_text(f'[User]: {message}')
            speak_text(r('tg_confirm_send'), lang=user_lang)
            confirm, _ = listen_text()
            if any(word in confirm.lower() for word in affirmation):
                speak_text('[System]: Please say your Telegram PIN to authorise.', lang=user_lang)
                pin_heard, _ = listen_text(duration=8)
                pin_heard = pin_heard.strip().lower()
                word_to_digit = {
                    'zero':'0','one':'1','two':'2','three':'3','four':'4',
                    'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
                }
                pin_digits = pin_heard
                for word, digit in word_to_digit.items():
                    pin_digits = pin_digits.replace(word, digit)
                pin_digits = ''.join(c for c in pin_digits if c.isdigit())
                current_email = web_login.app.config.get('current_email', '')
                from Backend.database import verify_pin
                if verify_pin(current_email, 'telegram', pin_digits):
                    success, result = telegram_send_message(recipient, message)
                    speak_text(f'[System]: {result}')
                    log_activity('telegram_sent', f'to:{recipient}')
                else:
                    speak_text('[System]: Incorrect PIN. Telegram message not sent.', lang=user_lang)
            else:
                speak_text(r('tg_cancelled'), lang=user_lang)

        # ── TELEGRAM — CHECK INBOX ────────────────────
        elif web_login.login_status == "success" and 'telegram' in clean_heard and any(w in clean_heard for w in inbox_req + ['message', 'messages', 'संदेश']):
            speak_text(r('tg_fetching'), lang=user_lang)
            messages = telegram_get_messages(5)
            if not messages:
                speak_text(r('tg_none'), lang=user_lang)
            else:
                for i, msg in enumerate(messages, 1):
                    sender = msg['name']
                    text   = msg['message']
                    unread = f"{msg['unread']} unread." if msg['unread'] else ''
                    speak_text(f"Telegram {i}. From: {sender}. {unread} Message: {text}. Date: {msg['date']}.")
                    speak_text(r('tg_reply_prompt'), lang=user_lang)
                    reply_decision, _ = listen_text()
                    reply_decision = reply_decision.lower().strip()
                    speak_text(f'[User]: {reply_decision}')
                    if any(word in reply_decision for word in affirmation):
                        handle_telegram_reply(sender, text)
                    else:
                        speak_text(r('tg_next'), lang=user_lang)
            continue

        # ── TELEGRAM — LATEST ─────────────────────────
        elif web_login.login_status == "success" and 'telegram' in clean_heard and any(w in clean_heard for w in ['latest', 'recent', 'नवीनतम', 'नया']):
            speak_text(r('tg_latest'), lang=user_lang)
            msg = telegram_get_latest()
            if msg:
                speak_text(f"[System]: Latest Telegram message. From: {msg['name']}. Message: {msg['message']}. Date: {msg['date']}.")
            else:
                speak_text(r('tg_none'), lang=user_lang)
            continue
            
        # ── WHATSAPP — SEND ───────────────────────────────
        elif web_login.login_status == "success" and 'whatsapp' in clean_heard and ('send' in clean_heard or 'भेजो' in clean_heard):
            speak_text('[System]: Who do you want to WhatsApp?', lang=user_lang)
            recipient, _ = listen_text()
            recipient = recipient.strip()
            speak_text(f'[User]: {recipient}')
            if not recipient:
                speak_text('[System]: No recipient heard. Cancelled.', lang=user_lang)
                continue
            speak_text('[System]: What is your message?', lang=user_lang)
            message, _ = listen_text(duration=10)
            message = message.strip()
            speak_text(f'[User]: {message}')
            if not message:
                speak_text('[System]: Message was empty. Cancelled.', lang=user_lang)
                continue
            speak_text(f'[System]: Sending WhatsApp to {recipient}. Please confirm.', lang=user_lang)
            confirm, _ = listen_text()
            if any(w in confirm.lower() for w in affirmation):
                speak_text('[System]: Please say your WhatsApp PIN to authorise.', lang=user_lang)
                pin_heard, _ = listen_text(duration=8)
                pin_heard = pin_heard.strip().lower()
                word_to_digit = {
                    'zero':'0','one':'1','two':'2','three':'3','four':'4',
                    'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
                }
                pin_digits = pin_heard
                for word, digit in word_to_digit.items():
                    pin_digits = pin_digits.replace(word, digit)
                pin_digits = ''.join(c for c in pin_digits if c.isdigit())
                current_email = web_login.app.config.get('current_email', '')
                from Backend.database import verify_pin
                if verify_pin(current_email, 'whatsapp', pin_digits):
                    success, result = whatsapp_send_message(recipient, message)
                    speak_text(f'[System]: {result}')
                    log_activity('whatsapp_sent', f'to:{recipient}')
                else:
                    speak_text('[System]: Incorrect PIN. WhatsApp message not sent.', lang=user_lang)
            else:
                speak_text('[System]: WhatsApp message cancelled.', lang=user_lang)

        # ── WHATSAPP — CHECK ──────────────────────────────
        elif web_login.login_status == "success" and 'whatsapp' in clean_heard and any(w in clean_heard for w in inbox_req + ['message', 'messages']):
            speak_text('[System]: Fetching your WhatsApp messages.', lang=user_lang)
            messages = whatsapp_get_messages(5)
            if not messages:
                speak_text('[System]: No WhatsApp messages found.', lang=user_lang)
            else:
                for i, msg in enumerate(messages, 1):
                    speak_text(f"WhatsApp {i}. From: {msg['name']}. Message: {msg['message']}. Date: {msg['date']}.")
                    speak_text('[System]: Would you like to reply to this message?', lang=user_lang)
                    reply_decision, _ = listen_text()
                    reply_decision = reply_decision.lower().strip()
                    speak_text(f'[User]: {reply_decision}')
                    if any(word in reply_decision for word in affirmation):
                        # ★ AI suggested reply — same pattern as Telegram
                        speak_text(r('suggest_generating'), lang=user_lang)
                        suggestion = generate_local_reply(msg['message'])
                        if suggestion:
                            speak_text(f'[System]: {suggestion}. Shall I send this?', lang=user_lang)
                            confirm, _ = listen_text()
                            confirm = confirm.lower().strip()
                            speak_text(f'[User]: {confirm}')
                            if any(w in confirm for w in affirmation):
                                success, result = whatsapp_send_message(msg['name'], suggestion)
                                speak_text(f'[System]: {result}')
                                continue
                            speak_text(r('suggest_custom'), lang=user_lang)
                        else:
                            speak_text(r('suggest_failed'), lang=user_lang)
                        # Manual reply fallback
                        speak_text('[System]: What is your reply?', lang=user_lang)
                        reply_msg, _ = listen_text(duration=10)
                        reply_msg = reply_msg.strip()
                        speak_text(f'[User]: {reply_msg}')
                        if reply_msg:
                            speak_text(f'[System]: Sending reply to {msg["name"]}. Confirm?', lang=user_lang)
                            confirm, _ = listen_text()
                            if any(w in confirm.lower() for w in affirmation):
                                success, result = whatsapp_send_message(msg['name'], reply_msg)
                                speak_text(f'[System]: {result}')
                            else:
                                speak_text('[System]: Reply cancelled.', lang=user_lang)
                    else:
                        speak_text('[System]: Okay, moving to the next message.', lang=user_lang)
            continue

        # ── NOT LOGGED IN GUARD ───────────────────────
        elif web_login.login_status != "success" and (
            ('send' in clean_heard and any(word in clean_heard for word in mail_req)) or
            ('check' in clean_heard and any(word in clean_heard for word in inbox_req))
        ):
            speak_text(r('not_logged_in'), lang=user_lang)
            continue

        # ── EMAIL — SEND ──────────────────────────────
        elif web_login.login_status == "success" and 'send' in clean_heard and any(word in clean_heard for word in mail_req):
            speak_text(r('email_send_prompt'), lang=user_lang)
            response, _ = listen_text()
            response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {response}')
            if any(s in response for s in affirmation):
                result = compose_email_by_voice()
                speak_text(result)
            elif any(s in response for s in negation):
                speak_text(r('email_cancelled'), lang=user_lang)
            continue

        # ── EMAIL — LATEST ────────────────────────────
        elif (
            web_login.login_status == 'success'
            and any(word in clean_heard for word in ['latest', 'recent', 'नवीनतम'])
            and any(word in clean_heard for word in inbox_req)
        ):
            speak_text(r('cat_prompt'), lang=user_lang)
            cat_response, _ = listen_text()
            cat_response = cat_response.lower().strip()
            speak_text(f'[User]: {cat_response}')
            if 'primary' in cat_response or 'प्राइमरी' in cat_response:
                category = 'PRIMARY'
            elif 'promo' in cat_response or 'प्रमोशन' in cat_response:
                category = 'PROMOTIONS'
            elif 'update' in cat_response or 'अपडेट' in cat_response:
                category = 'UPDATES'
            else:
                category = 'ALL'
            latest_emails = get_top_senders(1, category=category)
            latest_email  = latest_emails[0] if latest_emails else {}
            if 'error' in latest_email:
                speak_text(latest_email['error'])
            else:
                speak_text(
                    f'Your latest email. From: {latest_email["sender"]}. '
                    f'Subject: {latest_email["subject"]}. Date: {latest_email["date"]}. '
                    f'Summary: {latest_email["summary"]}.'
                )

        # ── EMAIL — CHECK INBOX ───────────────────────
        elif web_login.login_status == "success" and 'check' in clean_heard and any(word in clean_heard for word in inbox_req):
            speak_text(r('inbox_prompt'), lang=user_lang)
            response, _ = listen_text()
            response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {response}')
            if any(s in response for s in affirmation):
                speak_text(r('inbox_category'), lang=user_lang)
                cat_response, _ = listen_text()
                cat_response = cat_response.lower().strip()
                if 'primary' in cat_response or 'प्राइमरी' in cat_response:
                    category = 'PRIMARY'
                elif 'promo' in cat_response or 'प्रमोशन' in cat_response:
                    category = 'PROMOTIONS'
                elif 'update' in cat_response or 'अपडेट' in cat_response:
                    category = 'UPDATES'
                else:
                    category = 'ALL'
                print(f'[DEBUG] Category selected: {category}')
                inbox = get_top_senders(category=category)
                for i, mail_item in enumerate(inbox, 1):
                    if 'error' in mail_item:
                        speak_text(mail_item['error'])
                        break
                    summary_text = (
                        f"Email {i}. From: {mail_item['sender']}. "
                        f"Subject: {mail_item['subject']}. Date: {mail_item['date']}. "
                        f"Summary: {mail_item['summary']}."
                    )
                    if mail_item['details'].get('attachments'):
                        summary_text += f" Has attachments: {', '.join(mail_item['details']['attachments'])}."
                    speak_text(summary_text)
            elif any(s in response for s in negation):
                speak_text(r('inbox_ok'), lang=user_lang)
            continue

        # ── REPLY TO LATEST EMAIL ─────────────────────
        elif (
            web_login.login_status == 'success'
            and 'reply' in clean_heard
            and 'latest' in clean_heard
            and any(w in clean_heard for w in mail_req)
        ):
            speak_text(r('reply_fetching'), lang=user_lang)
            emails     = get_top_senders(count=1)
            email_data = emails[0] if emails else {}
            if 'error' in email_data:
                speak_text(f'[System]: {email_data["error"]}')
            else:
                speak_text(f'[System]: Email from {email_data["sender"]}. Subject: {email_data["subject"]}.')
                handle_reply(email_data)
            continue

        # ── REPLY TO SPECIFIC EMAIL ───────────────────
        elif (
            web_login.login_status == 'success'
            and 'reply' in clean_heard
            and any(w in clean_heard for w in mail_req)
        ):
            speak_text(r('reply_which'), lang=user_lang)
            num_heard, _ = listen_text()
            num_heard = num_heard.lower().strip()
            speak_text(f'[User]: {num_heard}')
            num_map = {
                'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                '1': 1, '2': 2, '3': 3, '4': 4, '5': 5,
                'first': 1, 'second': 2, 'third': 3, 'latest': 1, 'last': 1,
                'एक': 1, 'दो': 2, 'तीन': 3, 'चार': 4, 'पाँच': 5,
            }
            index = next((num_map[w] for w in num_map if w in num_heard), 1)
            fetching = f'[System]: Fetching email number {index}.' if user_lang == 'en' \
                else f'[System]: ईमेल नंबर {index} लाया जा रहा है।'
            speak_text(fetching, lang=user_lang)
            emails     = get_top_senders(count=index)
            email_data = emails[index - 1] if len(emails) >= index else {}
            if 'error' in email_data:
                speak_text(f'[System]: {email_data["error"]}')
            else:
                speak_text(f'[System]: Email from {email_data["sender"]}. Subject: {email_data["subject"]}.')
                handle_reply(email_data)
            continue

        # ── PROFILE ───────────────────────────────────
        elif web_login.login_status == "success" and ('profile' in clean_heard or 'प्रोफ़ाइल' in clean_heard):
            current_email = web_login.app.config.get('current_email', '')
            if not current_email:
                speak_text(r('profile_not_found'), lang=user_lang)
                continue
            speak_text(r('profile_prompt'), lang=user_lang)
            response, _ = listen_text()
            response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {response}')

            if 'view' in response or 'show' in response or 'what' in response or 'देखो' in response:
                user = get_user_by_email(current_email)
                if user:
                    speak_text(
                        f'[System]: Your profile. Name: {user["name"]}. '
                        f'Email: {user["email"]}. Account created on: {user["created_at"]}.'
                    )
                else:
                    speak_text(r('profile_google'), lang=user_lang)

            elif 'name' in response or 'नाम' in response:
                speak_text(r('name_prompt'), lang=user_lang)
                new_name, _ = listen_text()
                new_name = new_name.strip()
                speak_text(f'[User]: {new_name}')
                if new_name:
                    success, msg = update_name(current_email, new_name)
                    speak_text(f'[System]: {msg}')
                else:
                    speak_text(r('name_cancelled'), lang=user_lang)

            elif ('password' in response or 'पासवर्ड' in response) and ('audio' not in response and 'ऑडियो' not in response):
                speak_text(r('pass_current'), lang=user_lang)
                old_pass, _ = listen_text()
                speak_text(r('pass_new'), lang=user_lang)
                new_pass, _ = listen_text()
                if old_pass and new_pass:
                    success, msg = update_password(current_email, old_pass.strip(), new_pass.strip())
                    speak_text(f'[System]: {msg}')
                else:
                    speak_text(r('pass_cancelled'), lang=user_lang)

            elif 'audio' in response or 'ऑडियो' in response:
                speak_text(r('audio_prompt'), lang=user_lang)
                new_audio, _ = listen_text()
                new_audio = new_audio.strip()
                speak_text(f'[User]: {new_audio}')
                if new_audio:
                    success, msg = update_audio(current_email, new_audio)
                    speak_text(f'[System]: {msg}')
                    if success and new_audio.lower() not in confirmation_words:
                        confirmation_words.append(new_audio.lower())
                else:
                    speak_text(r('audio_cancelled'), lang=user_lang)

            elif 'delete' in response or 'डिलीट' in response:
                speak_text(r('delete_confirm'), lang=user_lang)
                confirm, _ = listen_text()
                confirm = confirm.lower().strip()
                speak_text(f'[User]: {confirm}')
                if any(w in confirm for w in affirmation):
                    speak_text(r('delete_pass'), lang=user_lang)
                    password, _ = listen_text()
                    success, msg = delete_user(current_email, password.strip())
                    speak_text(f'[System]: {msg}')
                    if success:
                        web_login.login_status = 'waiting'
                        login_initiated = False
                else:
                    speak_text(r('delete_cancelled'), lang=user_lang)
            continue

        # ── LOGOUT ────────────────────────────────────
        elif any(word in clean_heard for word in logout_commands):
            if web_login.login_status == "success":
                speak_text('[System]: Logging you out.' if user_lang == 'en' else '[System]: लॉगआउट हो रहे हैं।', lang=user_lang)
                web_login.login_status = "waiting"
                login_initiated = False
                speak_text(r('logout_success'), lang=user_lang)
            else:
                speak_text(r('not_logged_in_lo'), lang=user_lang)
            continue

        # ── TIME ──────────────────────────────────────
        elif ('time' in clean_heard and 'date' not in clean_heard) or 'समय' in clean_heard:
            t = datetime.datetime.now().strftime("%I:%M %p")
            speak_text(f'[System]: The time is {t}.' if user_lang == 'en' else f'[System]: अभी समय है {t}।', lang=user_lang)

        # ── DATE ──────────────────────────────────────
        elif 'date' in clean_heard or ('what' in clean_heard and 'day' in clean_heard) or 'तारीख' in clean_heard:
            d = datetime.datetime.now().strftime("%A, %B %d, %Y")
            speak_text(f'[System]: Today is {d}.' if user_lang == 'en' else f'[System]: आज {d} है।', lang=user_lang)

        # ── JOKE ──────────────────────────────────────
        elif 'joke' in clean_heard or 'funny' in clean_heard or 'मज़ाक' in clean_heard or 'जोक' in clean_heard:
            joke = random.choice(JOKES_HI if user_lang == 'hi' else JOKES_EN)
            speak_text(f'[System]: {joke}', lang=user_lang)

        # ── CALCULATOR ────────────────────────────────
        elif any(w in clean_heard for w in ['calculate', 'what is', "what's", 'plus', 'minus', 'times',
                                             'divided by', 'जमा', 'घटा', 'गुणा', 'भाग', 'क्या है', 'कितना']):
            speak_text(calculate(clean_heard), lang=user_lang)

        # ── GOODBYE ───────────────────────────────────
        elif any(word in clean_heard for word in ending):
            speak_text(bye_hi if user_lang == 'hi' else bye_en, lang=user_lang)
            break

        # ── FALLBACK ──────────────────────────────────
        elif not _is_nav:
            speak_text(r('not_understood'), lang=user_lang)

    file.close()