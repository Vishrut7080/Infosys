# # =================================================
# IMPORTS
# # =================================================
from Audio.text_to_speech import speak_text as _speak_text_orig
from Audio.speech_to_text import listen_text
from Mail.email_handler import open_gmail_compose, get_top_senders
from Mail.email_sender import compose_email_by_voice, send_reply_direct, reply_email_by_voice
from Backend.database import (
    verify_audio, get_user_by_email, update_name, update_password,
    update_audio, delete_user, is_admin, get_all_users, admin_delete_user,
    log_activity as _db_log_activity, verify_pin
)
from Mail.web_login import push_to_feed, push_nav_command
import Mail.web_login as web_login
import threading, webbrowser, requests
from dotenv import load_dotenv
import os, time, datetime, random, re, json
from Telegram.telegram import (
    start_telegram_in_thread, telegram_get_messages,
    telegram_send_message, telegram_get_latest, set_notification_callback
)

load_dotenv()

SECRET_AUD = os.getenv('SECRET_AUD', '')
OPEN_ROUTER_API_key=os.getenv('OPEN_ROUTER_API_key')

# ----------------------
# STATE VARIABLES
# ----------------------
force_lang           = None
user_lang            = 'en'
typing_pause_until   = 0
awaiting_services    = False
heard                = ""
login_initiated      = False
_awaiting_services_since = 0.0
_services_processed  = False   # prevents re-running service selection every loop

bye_en = '[System]: Goodbye! Take care.'
bye_hi = '[System]: अलविदा! अपना ख्याल रखें।'

# ----------------------
# HELPER: spoken PIN → digits
# ----------------------
def spoken_pin_to_digits(spoken: str) -> str:
    word_to_digit = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        'शून्य': '0', 'एक': '1', 'दो': '2', 'तीन': '3', 'चार': '4',
        'पाँच': '5', 'छः': '6', 'सात': '7', 'आठ': '8', 'नौ': '9',
    }
    result = spoken.strip().lower()
    for word, digit in word_to_digit.items():
        result = result.replace(word, digit)
    return ''.join(c for c in result if c.isdigit())


def clean_spoken_email(spoken: str) -> str:
    result = spoken.strip().lower()

    # Collapse all hyphen-separated spellings including digit-to-digit
    result = re.sub(r'(?<=[a-z])-(?=[a-z0-9])', '', result)
    result = re.sub(r'(?<=[a-z0-9])-(?=[a-z])', '', result)
    result = re.sub(r'(?<=[0-9])-(?=[0-9])', '', result)

    for at in ['at the rate', 'at the rate of', 'at the', 'at']:
        if at in result:
            result = result.replace(at, '@')
            break

    result = result.replace(' dot ', '.')
    result = result.replace(' dot', '.')
    result = result.replace('dot ', '.')

    result = re.sub(r'\.\s*@', '@', result)
    
    # Iteratively collapse dots until none remain (handles vi.sh.ru.t multi-char groups)
    prev = None
    while prev != result:
        prev = result
        result = re.sub(r'([a-z0-9])\.([a-z0-9])', r'\1 \2', result)
    result = re.sub(r'([a-z0-9])\.$', r'\1', result)
    result = re.sub(r'([a-z0-9])\.\s', r'\1 ', result)
    result = re.sub(r'\.\s+', ' ', result)

    if '@' in result:
        parts  = result.split('@', 1)
        local  = parts[0].strip().rstrip('.')
        domain = parts[1].strip().lstrip('.')
        local  = re.sub(r'(?<=[a-z0-9]) (?=[a-z0-9])', '', local)
        local  = local.replace(' ', '')
        domain = re.sub(r'(?<=[a-z0-9]) (?=[a-z0-9])', '', domain)
        domain = domain.replace(' ', '')
        # Re-insert missing dot before TLD — gmailcom → gmail.com
        domain = re.sub(
            r'(gmail|yahoo|outlook|hotmail|icloud|protonmail|live|rediff|proton)(com|net|org|in|co)',
            r'\1.\2',
            domain
        )
        result = local + '@' + domain
    else:
        result = re.sub(r'(?<=[a-z0-9]) (?=[a-z0-9])', '', result)
        result = result.replace(' ', '')

    # Fix "therategmail" / "theradegmail" artifacts
    result = re.sub(r'therate([a-z])', r'\1', result)
    result = re.sub(r'therad([a-z])', r'\1', result)

    result = re.sub(
        r'@[a-z]*?(gmail|yahoo|outlook|hotmail|icloud|protonmail|live)\.',
        r'@\1.', result
    )

    if '@' not in result:
        result = re.sub(
            r'(gmail|yahoo|outlook|hotmail|icloud|protonmail|live)\.',
            r'@\1.', result
        )

    result = result.strip('.')
    return result


def clean_spoken_name(spoken: str) -> str:
    result = spoken.strip().lower()
    result = re.sub(r'(?<=[a-z])-(?=[a-z])', ' ', result)
    tokens = result.split()
    if tokens and sum(1 for t in tokens if len(t) == 1) / len(tokens) > 0.5:
        result = ''.join(tokens)
    return result.strip()


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
    'login_opened':        {'en': '[System]: Login page opened. Please log in via browser or say your audio password.',
                            'hi': '[System]: लॉगिन पेज खुल गया। कृपया ब्राउज़र से लॉगिन करें या ऑडियो पासवर्ड बोलें।'},
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
    'tg_auth_prompt':      {'en': '[System]: Telegram needs authorization. Say your secret password to open the login page.',
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
    'profile_prompt':      {'en': '[System]: What would you like to do? Say view, change name, '
                                  'change password, change audio password, or delete my account.',
                            'hi': '[System]: आप क्या करना चाहते हैं? व्यू, नाम बदलें, पासवर्ड बदलें, '
                                  'ऑडियो पासवर्ड बदलें, या मेरा अकाउंट डिलीट करें।'},
    'admin_menu':          {'en': '[System]: Admin profile menu. Say: view, change name, change password, '
                                  'change audio password, delete my account, list users, or delete user.',
                            'hi': '[System]: एडमिन प्रोफ़ाइल मेनू। बोलें: व्यू, नाम बदलें, पासवर्ड बदलें, '
                                  'ऑडियो पासवर्ड बदलें, मेरा अकाउंट डिलीट करें, यूज़र्स देखें, या यूज़र डिलीट करें।'},
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
    'delete_confirm':      {'en': '[System]: Are you sure? Say your confirmation word to proceed.',
                            'hi': '[System]: क्या आप वाकई? पुष्टि के लिए कन्फर्मेशन वर्ड बोलें।'},
    'delete_pass':         {'en': '[System]: Please say your password to confirm deletion.',
                            'hi': '[System]: डिलीट की पुष्टि के लिए पासवर्ड बोलें।'},
    'delete_cancelled':    {'en': '[System]: Account deletion cancelled.',
                            'hi': '[System]: अकाउंट डिलीट रद्द किया गया।'},
    'admin_list_empty':    {'en': '[System]: No users registered yet.',
                            'hi': '[System]: कोई यूज़र पंजीकृत नहीं है।'},
    'admin_ask_email':     {'en': '[System]: Say the email address of the user to delete.',
                            'hi': '[System]: जिस यूज़र को डिलीट करना है उसका ईमेल बोलें।'},
    'admin_bad_email':     {'en': '[System]: Could not understand the email address. Cancelled.',
                            'hi': '[System]: ईमेल पता समझ नहीं आया। रद्द किया।'},
    'admin_self_delete':   {'en': '[System]: Use "delete my account" to delete your own account.',
                            'hi': '[System]: अपना खाता डिलीट करने के लिए "मेरा अकाउंट डिलीट" कहें।'},
    'conf_not_recognised': {'en': '[System]: Confirmation not recognised. Cancelled.',
                            'hi': '[System]: पुष्टि नहीं मिली। रद्द किया।'},
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

# ----------------------
# HINDI COMMAND MAP
# ----------------------
HINDI_COMMAND_MAP = {
    'लोगें': 'login', 'लॉगें': 'login', 'लॉग': 'login', 'लोगिन': 'login',
    'लॉगआउट': 'logout', 'लॉग आउट': 'logout', 'साइन आउट': 'logout',
    'नमस्ते': 'hello', 'हेलो': 'hello', 'हाय': 'hello',
    'अलविदा': 'goodbye', 'बाय': 'bye', 'बंद करो': 'exit',
    'हाँ': 'yes', 'हां': 'yes', 'नहीं': 'no',
    'ईमेल': 'email', 'मेल': 'mail', 'संदेश': 'message',
    'इनबॉक्स': 'inbox',
    'समय': 'time', 'तारीख': 'date',
    'मज़ाक': 'joke', 'जोक': 'joke',
    'प्रोफ़ाइल': 'profile',
    'टेलीग्राम': 'telegram',
    'भेजो': 'send', 'जांचो': 'check', 'जवाब': 'reply',
    'हिसाब': 'calculate', 'कितना': 'what is',
    'नवीनतम': 'latest', 'नया': 'recent',
    'एडमिन': 'admin', 'उपयोगकर्ता': 'users', 'डिलीट': 'delete', 'यूज़र': 'user',
    'चेक': 'check', 'जाँचो': 'check', 'देखो': 'check', 'खोलो': 'check', 'पढ़ो': 'check',
    'बेजी': 'send', 'भेजी': 'send', 'बेजो': 'send', 'भेज': 'send', 'सेंड': 'send',
    'लिखो': 'compose',
    'तेलीग्राम': 'telegram', 'टेलीग्रम': 'telegram', 'टेली': 'telegram',
}

# ----------------------
# NAVIGATION COMMANDS
# ----------------------
NAV_PHRASES = [
    'go to dashboard', 'open dashboard', 'show dashboard',
    'go to profile',   'open profile',   'show profile',   'my profile',
    'go to inbox',     'open inbox',     'show inbox',     'unified inbox',
    'go to messages',  'open messages',  'show messages',
    'select gmail',    'enable gmail',   'add gmail',
    'select telegram', 'enable telegram','add telegram',
    'deselect gmail',  'disable gmail',  'remove gmail',
    'deselect telegram','disable telegram','remove telegram',
    'save services',   'confirm services','save and continue',
    'select both',     'enable both',    'both services',
    'select gmail and telegram', 'select telegram and gmail',
    'go to users', 'show users panel', 'open users',
    'go to activity', 'activity logs', 'open activity',
    'go to api usage', 'api usage', 'open api',
    'go to error logs', 'error logs', 'open errors',
    'go to system status', 'system status', 'open status',
    'go to overview', 'show overview', 'open overview',
    'go to user dashboard', 'user dashboard', 'open user dashboard',
]

def normalize_hindi(text: str) -> str:
    for hindi, english in HINDI_COMMAND_MAP.items():
        text = text.replace(hindi, english)
    return text

def r(key: str, lang: str = None) -> str:
    _lang = lang or user_lang
    return RESPONSES.get(key, {}).get(_lang, RESPONSES.get(key, {}).get('en', ''))

# ----------------------
# SPEAK
# ----------------------
def speak_text(text: str, lang: str = 'en'):
    push_to_feed(text)
    _speak_text_orig(text, lang=lang)

def log_activity(action: str, detail: str = ''):
    if web_login.login_status != 'success':
        return
    email = web_login.app.config.get('current_email', '')
    if email:
        _db_log_activity(email, action, detail)

# ----------------------
# KEYWORD SETS
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

# ----------------------
# TELEGRAM NOTIFICATION CALLBACK
# ----------------------
def on_new_telegram(sender, text):
    speak_text(f'[Telegram]: New message from {sender}: {text}')

set_notification_callback(on_new_telegram)

# ----------------------
# JOKES
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
# CALCULATOR
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
    for filler in ['what is', "what's", 'calculate', 'compute', 'equals',
                   'equal to', '?', 'क्या है', 'बताओ', 'हिसाब', 'कितना']:
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
        allowed = re.fullmatch(r'[\d\s\+\-\*\/\(\)\.]+', expr)
        if not allowed:
            return r('not_understood')
        result = eval(expr)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return (f'[System]: उत्तर है {result}।' if user_lang == 'hi'
                else f'[System]: The answer is {result}.')
    except ZeroDivisionError:
        return ('[System]: शून्य से भाग नहीं हो सकता।' if user_lang == 'hi'
                else '[System]: Cannot divide by zero.')
    except Exception:
        return r('not_understood')

# ----------------------
# AI REPLY HELPER (local Ollama)
# ----------------------
def generate_local_reply(message: str) -> str | None:
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
              "Authorization": f"Bearer {OPEN_ROUTER_API_key}"
            },
            data=json.dumps({
                "model": "openrouter/hunter-alpha",             
                "messages": [
                    {
                      "role": "user",
                      "content": "You are an AI assistant helping reply to messages.\n"
                        "Write a short natural reply (1-2 sentences).\n"
                        f"Message:\n{message}\nReply:"
                    },
                ]                
            })
            )
        data = response.json()
        return data.get("response", "").strip() or None
    except Exception as e:
        print("Response Error:", e)
        return None

# ----------------------
# HANDLE EMAIL REPLY FLOW
# ----------------------
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

# ----------------------
# HANDLE TELEGRAM REPLY FLOW
# ----------------------
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
# PROFILE HANDLER
# ----------------------
def handle_profile():
    global user_lang, confirmation_words, login_initiated

    current_email = web_login.app.config.get('current_email', '')
    if not current_email:
        speak_text(r('profile_not_found'), lang=user_lang)
        return

    user_is_admin = is_admin(current_email)
    speak_text(r('admin_menu') if user_is_admin else r('profile_prompt'), lang=user_lang)

    response, _ = listen_text()
    response = response.lower().strip().replace('.', '')
    speak_text(f'[User]: {response}')

    if any(w in response for w in ['view', 'show', 'what', 'देखो', 'बताओ']):
        user = get_user_by_email(current_email)
        if user:
            speak_text(
                f'[System]: Your profile. Name: {user["name"]}. '
                f'Email: {user["email"]}. Account created on: {user["created_at"]}.',
                lang=user_lang,
            )
        else:
            speak_text(r('profile_google'), lang=user_lang)

    elif any(w in response for w in ['name', 'नाम']):
        speak_text(r('name_prompt'), lang=user_lang)
        new_name_raw, _ = listen_text()
        new_name = clean_spoken_name(new_name_raw)
        speak_text(f'[User]: {new_name}')
        if new_name:
            ok, msg = update_name(current_email, new_name)
            speak_text(f'[System]: {msg}')
        else:
            speak_text(r('name_cancelled'), lang=user_lang)

    elif (any(w in response for w in ['password', 'पासवर्ड'])
          and not any(w in response for w in ['audio', 'ऑडियो'])):
        speak_text(r('pass_current'), lang=user_lang)
        old_pass, _ = listen_text()
        speak_text(r('pass_new'), lang=user_lang)
        new_pass, _ = listen_text()
        if old_pass and new_pass:
            ok, msg = update_password(current_email, old_pass.strip(), new_pass.strip())
            speak_text(f'[System]: {msg}')
        else:
            speak_text(r('pass_cancelled'), lang=user_lang)

    elif any(w in response for w in ['audio', 'ऑडियो']):
        speak_text(r('audio_prompt'), lang=user_lang)
        new_audio, _ = listen_text()
        new_audio = new_audio.strip()
        speak_text(f'[User]: {new_audio}')
        if new_audio:
            ok, msg = update_audio(current_email, new_audio)
            speak_text(f'[System]: {msg}')
            if ok and new_audio.lower() not in confirmation_words:
                confirmation_words.append(new_audio.lower())
        else:
            speak_text(r('audio_cancelled'), lang=user_lang)

    elif any(w in response for w in [
        'delete my', 'delete account', 'मेरा अकाउंट', 'डिलीट', 'delete'
    ]):
        speak_text(r('delete_confirm'), lang=user_lang)
        conf, _ = listen_text()
        conf = conf.lower().strip()
        speak_text(f'[User]: {conf}')
        if any(w in conf for w in confirmation_words):
            speak_text(r('delete_pass'), lang=user_lang)
            password, _ = listen_text()
            ok, msg = delete_user(current_email, password.strip())
            speak_text(f'[System]: {msg}')
            if ok:
                web_login.login_status = 'waiting'
                login_initiated = False
        else:
            speak_text(r('delete_cancelled'), lang=user_lang)

    elif user_is_admin and any(w in response for w in [
        'list users', 'show users', 'all users', 'list user',
        'यूज़र्स देखें', 'उपयोगकर्ता', 'सभी यूज़र्स', 'users'
    ]):
        all_users = get_all_users()
        if not all_users:
            speak_text(r('admin_list_empty'), lang=user_lang)
        else:
            speak_text(
                f'[System]: {len(all_users)} registered users.'
                if user_lang == 'en'
                else f'[System]: {len(all_users)} पंजीकृत यूज़र्स।',
                lang=user_lang,
            )
            for i, u in enumerate(all_users, 1):
                role_label = 'admin' if u['is_admin'] else 'user'
                speak_text(
                    f'{i}. {u["name"]}, {u["email"]}, {role_label}, '
                    f'{u["sessions"]} sessions.',
                    lang=user_lang,
                )
                time.sleep(0.3)

    elif user_is_admin and any(w in response for w in [
        'delete user', 'remove user', 'यूज़र डिलीट', 'यूज़र हटाएं'
    ]):
        speak_text(r('admin_ask_email'), lang=user_lang)
        target_raw, _ = listen_text(duration=10)
        target_email   = clean_spoken_email(target_raw)
        speak_text(f'[User]: {target_email}')

        if not target_email or '@' not in target_email:
            speak_text(r('admin_bad_email'), lang=user_lang)
        elif target_email == current_email:
            speak_text(r('admin_self_delete'), lang=user_lang)
        else:
            confirm_prompt = (
                f'[System]: Delete {target_email}? Say your confirmation word to proceed.'
                if user_lang == 'en'
                else f'[System]: {target_email} को डिलीट करें? पुष्टि के लिए कन्फर्मेशन वर्ड बोलें।'
            )
            speak_text(confirm_prompt, lang=user_lang)
            conf, _ = listen_text(duration=6)
            conf = conf.lower().strip()
            speak_text(f'[User]: {conf}')

            if any(w in conf for w in confirmation_words):
                ok, msg = admin_delete_user(target_email)
                speak_text(f'[System]: {msg}')
                if ok:
                    _db_log_activity(current_email, 'admin_delete_user',
                                     f'deleted:{target_email}')
            else:
                speak_text(r('conf_not_recognised'), lang=user_lang)

    else:
        speak_text(r('not_understood'), lang=user_lang)


# ========================
# HELPER: connect services after selection
# ========================
def _connect_services(verified_services: list, announce: bool = True):
    if 'telegram' in verified_services:
        api_id   = int(os.getenv('TELEGRAM_API_ID', 0))
        api_hash = os.getenv('TELEGRAM_API_HASH', '')
        if api_id and api_hash:
            start_telegram_in_thread()
            time.sleep(5)
            from Telegram.telegram import _client, _loop as tg_loop
            import asyncio as _asyncio
            authorized = False
            if _client and _client.is_connected() and tg_loop:
                try:
                    fut = _asyncio.run_coroutine_threadsafe(
                        _client.is_user_authorized(), tg_loop
                    )
                    authorized = fut.result(timeout=5)
                except Exception:
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
                if announce:
                    speak_text(r('tg_auto'), lang=user_lang)

    if announce and verified_services:
        names = ', '.join(verified_services)
        speak_text(
            f'[System]: {names} connected.'
            if user_lang == 'en'
            else f'[System]: {names} कनेक्ट हुआ।',
            lang=user_lang,
        )


# ========================
# START FLASK SERVER
# ========================
print("[Main] Starting Flask Server in a background thread...")
server_thread = threading.Thread(target=web_login.start_server, daemon=True)
server_thread.start()
time.sleep(1) # Give it a second to start

# ========================
# MAIN COMMAND LOOP
# ========================
with open('Audio/Transcribe.txt', 'a', encoding='utf-8') as file:
    while True:

        # ── AUTO-LOGIN from signup ──────────────────────────
        if (web_login.login_from_signup
                and not login_initiated
                and web_login.login_status != 'success'):
            web_login.login_from_signup = False
            login_initiated = True
            speak_text('[System]: Welcome! Say your audio password to complete login.',
                       lang=user_lang)
            continue

        # ── OAuth login completed between iterations ────────
        if login_initiated and web_login.login_status == 'success':
            login_initiated     = False
            awaiting_services   = True
            _services_processed = False
            continue

        # ── SERVICE SELECTION (immediately after login) ─────
        if awaiting_services:
            if web_login.selected_services:
                services      = list(web_login.selected_services)
                current_email = web_login.app.config.get('current_email', '')

                # No PIN at service selection — just connect
                web_login.selected_services = services
                web_login.app.config['verified_services'] = services
                awaiting_services   = False
                _services_processed = True
                _awaiting_services_since = 0.0

                _connect_services(services, announce=False)
            else:
                awaiting_services = False
                _awaiting_services_since = 0.0
                speak_text(
                    '[System]: Ready. Select services on the dashboard anytime.'
                    if user_lang == 'en'
                    else '[System]: तैयार। डैशबोर्ड पर कभी भी सेवाएं चुनें।',
                    lang=user_lang,
                )
            continue

        # ── Services selected from dashboard AFTER login ────
        if (web_login.login_status == 'success'
                and web_login.selected_services
                and not awaiting_services
                and not _services_processed
                and web_login.services_just_selected):   # ← only when freshly selected
            web_login.services_just_selected = False
            _services_processed = True
            services      = list(web_login.selected_services)
            current_email = web_login.app.config.get('current_email', '')

            from Telegram.telegram import _client as _tg_client
            tg_already_running  = _tg_client is not None and _tg_client.is_connected()
            already_verified    = web_login.app.config.get('verified_services', [])
            gmail_already_ready = 'gmail' in already_verified

            needs_processing = (
                ('telegram' in services and not tg_already_running) or
                ('gmail' in services and not gmail_already_ready)
            )

            if needs_processing:
                # Ask PIN only before actually connecting services
                verified = []
                for service in services:
                    speak_text(
                        f'[System]: Please say your 4-digit {service.capitalize()} PIN to confirm.'
                        if user_lang == 'en'
                        else f'[System]: {service.capitalize()} का 4-अंकी PIN बोलें।',
                        lang=user_lang,
                    )
                    pin_heard, _ = listen_text(duration=8)
                    pin_heard = pin_heard.strip().lower()
                    speak_text(f'[User]: {pin_heard}')
                    pin_digits = spoken_pin_to_digits(pin_heard)
                    if verify_pin(current_email, service, pin_digits):
                        speak_text(
                            f'[System]: {service.capitalize()} PIN confirmed.'
                            if user_lang == 'en'
                            else f'[System]: {service.capitalize()} PIN सही है।',
                            lang=user_lang,
                        )
                        verified.append(service)
                    else:
                        speak_text(
                            f'[System]: Incorrect PIN for {service.capitalize()}. Not connected.'
                            if user_lang == 'en'
                            else f'[System]: {service.capitalize()} PIN गलत। कनेक्ट नहीं होगा।',
                            lang=user_lang,
                        )
                web_login.selected_services = verified
                web_login.app.config['verified_services'] = verified
                _connect_services(verified, announce=True)
            continue

        # ── Typing pause ────────────────────────────────────
        if web_login.user_typing:
            typing_pause_until    = time.time() + 5
            web_login.user_typing = False

        # ── Pause while signup page is open ─────────────────
        if web_login.signup_open:
            time.sleep(0.5)
            continue

        if time.time() < typing_pause_until and not login_initiated:
            time.sleep(0.5)
            continue

        # ── RECORD ──────────────────────────────────────────
        heard, user_lang = listen_text(force_lang=force_lang)

        if login_initiated and web_login.login_status == 'success':
            login_initiated     = False
            awaiting_services   = True
            _services_processed = False
            speak_text(r('select_services'), lang=user_lang)
            continue

        speak_text(f'[User]: {heard}')
        clean_heard = heard.lower().strip().replace('.', '')
        clean_heard = normalize_hindi(clean_heard)
        file.write(f'{clean_heard}\n')

        if web_login.login_status == 'success':
            log_activity('voice_command', clean_heard[:100])

        # ── Navigation commands ──────────────────────────────
        _is_nav = False
        for phrase in NAV_PHRASES:
            if phrase in clean_heard:
                push_nav_command(clean_heard)
                _is_nav = True
                break

        # ==================================================
        # COMMAND DISPATCH
        # ==================================================

        if any(
            word == clean_heard
            or clean_heard.startswith(word + ' ')
            or clean_heard.endswith(' ' + word)
            for word in greeting
        ):
            speak_text(r('greeting'), lang=user_lang)

        elif any(x in clean_heard for x in [
            'hindi mode', 'हिंदी मोड', 'इंदी मोड', 'अन्दी मुड',
            'hindi mod', 'hindi mo'
        ]):
            force_lang = 'hi'
            user_lang  = 'hi'
            speak_text('[System]: हिंदी मोड चालू।', lang='hi')
            continue

        elif 'english mode' in clean_heard or 'switch to english' in clean_heard:
            force_lang = 'en'
            speak_text('[System]: Switched to English mode.', lang='en')
            continue

        elif ('login' in clean_heard
              or 'log in' in clean_heard
              or 'लॉगिन' in clean_heard):
            if web_login.login_status == 'success':
                speak_text(r('already_logged_in'), lang=user_lang)
                continue
            if login_initiated:
                speak_text(r('login_in_progress'), lang=user_lang)
                continue
            web_login.login_status = 'waiting'
            login_initiated = True
            speak_text(r('login_opened'), lang=user_lang)
            continue

        elif any(w in clean_heard for w in [
            'signup', 'sign up', 'register', 'साइनअप'
        ]):
            if web_login.signup_open:
                speak_text('[System]: Signup page is already open.', lang=user_lang)
                continue
            login_initiated        = False
            web_login.login_status = 'waiting'
            speak_text(r('signup_opening'), lang=user_lang)
            threading.Thread(
                target=webbrowser.open,
                args=('http://localhost:5000/signup',),
                daemon=True,
            ).start()
            continue

        elif login_initiated and web_login.login_status != 'success':
            login_initiated = False
            matched, name, matched_email = verify_audio(clean_heard.strip())
            if matched:
                welcome = (
                    f'[System]: Welcome, {name}. Login confirmed.'
                    if user_lang == 'en'
                    else f'[System]: स्वागत है, {name}। लॉगिन सफल।'
                )
                speak_text(welcome, lang=user_lang)
                web_login.login_status = 'success'
                web_login.app.config['current_email'] = matched_email

                # NEW: Populate session immediately for the web-login orchestrator
                with web_login.app.test_request_context():
                    web_login.session.clear()
                    web_login.session['user'] = {'name': name, 'email': matched_email}
                    web_login.session.permanent = True

                web_login.apply_user_credentials(matched_email)
                _db_log_activity(matched_email, 'login', 'audio')
                web_login.database.log_session(matched_email, force_insert=True)            
            else:
                speak_text(r('login_failed'), lang=user_lang)
                web_login.login_status = 'failed'
            continue

        # ── TELEGRAM — SEND ──────────────────────────────────
        elif (web_login.login_status == 'success'
              and any(w in clean_heard for w in [
                  'telegram', 'तेलीग्राम', 'टेलीग्रम', 'टेली'
              ])
              and any(w in clean_heard for w in [
                  'send', 'भेजो', 'भेज', 'बेजो', 'बेजी', 'भेजी', 'सेंड'
              ])):
            speak_text(r('tg_who'), lang=user_lang)
            recipient_raw, _ = listen_text(duration=10)
            recipient = clean_spoken_name(recipient_raw)
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
            if any(w in confirm.lower() for w in affirmation):
                # PIN confirmation just before sending
                speak_text('[System]: Please say your 4-digit Telegram PIN to confirm.',
                           lang=user_lang)
                pin_heard, _ = listen_text(duration=8)
                pin_digits = spoken_pin_to_digits(pin_heard.strip().lower())
                current_email = web_login.app.config.get('current_email', '')
                if verify_pin(current_email, 'telegram', pin_digits):
                    success, result = telegram_send_message(recipient, message)
                    speak_text(f'[System]: {result}')
                    log_activity('telegram_sent', f'to:{recipient}')
                else:
                    speak_text('[System]: Incorrect PIN. Telegram message not sent.',
                               lang=user_lang)
            else:
                speak_text(r('tg_cancelled'), lang=user_lang)

        # ── TELEGRAM — CHECK INBOX ───────────────────────────
        elif (web_login.login_status == 'success'
              and any(w in clean_heard for w in [
                  'telegram', 'तेलीग्राम', 'टेलीग्रम', 'टेली'
              ])
              and any(w in clean_heard for w in
                      inbox_req + ['message', 'messages', 'संदेश',
                                   'check', 'चेक', 'देखो', 'पढ़ो', 'खोलो'])):
            speak_text(r('tg_fetching'), lang=user_lang)
            messages = telegram_get_messages(5)
            if not messages:
                speak_text(r('tg_none'), lang=user_lang)
            else:
                for i, msg in enumerate(messages, 1):
                    sender = msg['name']
                    text   = msg['message']
                    unread = f"{msg['unread']} unread." if msg['unread'] else ''
                    speak_text(
                        f"Telegram {i}. From: {sender}. {unread} "
                        f"Message: {text}. Date: {msg['date']}."
                    )
                    speak_text(
                        ('[System]: Say yes to reply, stop to stop reading, or no for next.'
                         if user_lang == 'en'
                         else '[System]: जवाब देने के लिए हाँ, बंद करने के लिए stop, '
                              'या अगले के लिए नहीं।'),
                        lang=user_lang,
                    )
                    reply_decision, _ = listen_text()
                    reply_decision = reply_decision.lower().strip()
                    speak_text(f'[User]: {reply_decision}')

                    if any(w in reply_decision for w in
                           ['stop', 'enough', 'done', 'रुको', 'बस']):
                        speak_text(
                            '[System]: Stopped reading messages.'
                            if user_lang == 'en'
                            else '[System]: पढ़ना बंद किया।',
                            lang=user_lang,
                        )
                        break
                    elif any(w in reply_decision for w in affirmation):
                        handle_telegram_reply(sender, text)
                    else:
                        speak_text(r('tg_next'), lang=user_lang)
            continue

        # ── TELEGRAM — LATEST ────────────────────────────────
        elif (web_login.login_status == 'success'
              and any(w in clean_heard for w in [
                  'telegram', 'तेलीग्राम', 'टेलीग्रम', 'टेली'
              ])
              and any(w in clean_heard for w in [
                  'latest', 'recent', 'नवीनतम', 'नया', 'last', 'new'
              ])):
            speak_text(r('tg_latest'), lang=user_lang)
            msg = telegram_get_latest()
            if msg:
                speak_text(
                    f"[System]: Latest Telegram message. From: {msg['name']}. "
                    f"Message: {msg['message']}. Date: {msg['date']}."
                )
            else:
                speak_text(r('tg_none'), lang=user_lang)
            continue

        elif (web_login.login_status != 'success' and (
            ('send' in clean_heard and any(w in clean_heard for w in mail_req))
            or ('check' in clean_heard and any(w in clean_heard for w in inbox_req))
        )):
            speak_text(r('not_logged_in'), lang=user_lang)
            continue

        # ── EMAIL — SEND ─────────────────────────────────────
        elif (web_login.login_status == 'success'
            and any(w in clean_heard for w in mail_req)
            and any(w in clean_heard for w in [
                'send', 'compose', 'write',
                'भेजो', 'भेज', 'बेजो', 'बेजी', 'भेजी', 'सेंड', 'लिखो'
            ])):
            speak_text(r('email_send_prompt'), lang=user_lang)
            response, _ = listen_text()
            response = response.lower().strip().replace('.', '')
            speak_text(f'[User]: {response}')
            if any(s in response for s in affirmation):
                # ── Step 1: collect recipient ─────────────────
                speak_text('[System]: Please say the recipient email address.', lang=user_lang)
                for attempt in range(2):
                    raw, _ = listen_text(duration=10)
                    recipient_email = clean_spoken_email(raw)
                    speak_text(f'[User]: {recipient_email}')
                    domain_part = recipient_email.split('@')[-1] if '@' in recipient_email else ''
                    if '@' in recipient_email and len(domain_part) > 3 and re.search(r'[a-z]+\.[a-z]+', domain_part):
                        break
                    speak_text(
                        f'[System]: That doesn\'t look valid: {recipient_email}. Try again.'
                        if attempt == 0
                        else '[System]: Could not get a valid email. Cancelled.',
                        lang=user_lang,
                    )
                    if attempt == 1:
                        continue
                else:
                    continue

                # ── Step 2: subject ───────────────────────────
                speak_text('[System]: What is the subject?', lang=user_lang)
                subject, _ = listen_text(duration=10)
                subject = subject.strip()
                speak_text(f'[User]: {subject}')
                if not subject:
                    speak_text('[System]: No subject heard. Email cancelled.', lang=user_lang)
                    continue

                # ── Step 3: body ──────────────────────────────
                speak_text('[System]: Please dictate your message.', lang=user_lang)
                body, _ = listen_text(duration=15)
                body = body.strip()
                speak_text(f'[User]: {body}')
                if not body:
                    speak_text('[System]: No message heard. Email cancelled.', lang=user_lang)
                    continue

                # ── Step 4: summary + PIN confirmation ────────
                speak_text(
                    f'[System]: Ready to send to {recipient_email}. '
                    f'Subject: {subject}. '
                    f'Please say your 4-digit Gmail PIN to confirm sending.',
                    lang=user_lang,
                )
                pin_heard, _ = listen_text(duration=8)
                pin_digits = spoken_pin_to_digits(pin_heard.strip().lower())
                current_email = web_login.app.config.get('current_email', '')
                if verify_pin(current_email, 'gmail', pin_digits):
                    ok, msg = send_reply_direct(
                        to=recipient_email,
                        subject=subject,
                        body=body,
                    )
                    speak_text(f'[System]: {msg}')
                    if ok:
                        log_activity('email_sent', f'to:{recipient_email}')
                else:
                    speak_text('[System]: Incorrect PIN. Email not sent.', lang=user_lang)
            elif any(s in response for s in negation):
                speak_text(r('email_cancelled'), lang=user_lang)
            continue

        # ── EMAIL — LATEST ───────────────────────────────────
        elif (web_login.login_status == 'success'
              and any(w in clean_heard for w in [
                  'latest', 'recent', 'नवीनतम', 'नया', 'last', 'new'
              ])
              and any(w in clean_heard for w in
                      inbox_req + ['ईमेल', 'इमेल', 'email'])):
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
                    f'Subject: {latest_email["subject"]}. '
                    f'Date: {latest_email["date"]}. '
                    f'Summary: {latest_email["summary"]}.'
                )
                log_activity('email_read', f'from:{latest_email.get("sender","")}')
                speak_text(
                    '[System]: Would you like to reply to this email?'
                    if user_lang == 'en'
                    else '[System]: क्या आप इस ईमेल का जवाब देना चाहते हैं?',
                    lang=user_lang,
                )
                reply_decision, _ = listen_text()
                reply_decision = reply_decision.lower().strip()
                speak_text(f'[User]: {reply_decision}')
                if any(w in reply_decision for w in affirmation):
                    handle_reply(latest_email)
                else:
                    speak_text(
                        '[System]: Ok, no reply sent.'
                        if user_lang == 'en'
                        else '[System]: ठीक है, कोई जवाब नहीं भेजा।',
                        lang=user_lang,
                    )

        # ── EMAIL — CHECK INBOX ──────────────────────────────
        elif (web_login.login_status == 'success'
            and any(w in clean_heard for w in inbox_req)
            and any(w in clean_heard for w in [
                'check', 'read', 'open', 'show',
                'जांचो', 'जाँचो', 'चेक', 'देखो', 'खोलो', 'पढ़ो'
            ])):
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
                inbox = get_top_senders(category=category)
                for i, mail_item in enumerate(inbox, 1):
                    if 'error' in mail_item:
                        speak_text(mail_item['error'])
                        break
                    summary_text = (
                        f"Email {i}. From: {mail_item['sender']}. "
                        f"Subject: {mail_item['subject']}. "
                        f"Date: {mail_item['date']}. "
                        f"Summary: {mail_item['summary']}."
                    )
                    if mail_item['details'].get('attachments'):
                        summary_text += (
                            f" Has attachments: "
                            f"{', '.join(mail_item['details']['attachments'])}."
                        )
                    speak_text(summary_text)
                    log_activity('email_read', f'from:{mail_item.get("sender","")}')
                    if i < len(inbox):
                        speak_text(
                            ('[System]: Say stop to stop reading, or anything else to continue.'
                             if user_lang == 'en'
                             else '[System]: पढ़ना बंद करने के लिए stop बोलें।'),
                            lang=user_lang,
                        )
                        stop_heard, _ = listen_text(duration=4)
                        stop_heard = stop_heard.lower().strip()
                        speak_text(f'[User]: {stop_heard}')
                        if any(w in stop_heard for w in
                               ['stop', 'enough', 'done', 'रुको', 'बस']):
                            speak_text(
                                '[System]: Stopped reading.'
                                if user_lang == 'en'
                                else '[System]: पढ़ना बंद किया।',
                                lang=user_lang,
                            )
                            break
            elif any(s in response for s in negation):
                speak_text(r('inbox_ok'), lang=user_lang)
            continue

        # ── REPLY TO LATEST EMAIL ────────────────────────────
        elif (web_login.login_status == 'success'
              and 'reply' in clean_heard
              and 'latest' in clean_heard
              and any(w in clean_heard for w in mail_req)):
            speak_text(r('reply_fetching'), lang=user_lang)
            emails     = get_top_senders(count=1)
            email_data = emails[0] if emails else {}
            if 'error' in email_data:
                speak_text(f'[System]: {email_data["error"]}')
            else:
                speak_text(
                    f'[System]: Email from {email_data["sender"]}. '
                    f'Subject: {email_data["subject"]}.'
                )
                handle_reply(email_data)
            continue

        # ── REPLY TO SPECIFIC EMAIL ──────────────────────────
        elif (web_login.login_status == 'success'
              and 'reply' in clean_heard
              and any(w in clean_heard for w in mail_req)):
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
            speak_text(
                (f'[System]: Fetching email number {index}.'
                 if user_lang == 'en'
                 else f'[System]: ईमेल नंबर {index} लाया जा रहा है।'),
                lang=user_lang,
            )
            emails     = get_top_senders(count=index)
            email_data = emails[index - 1] if len(emails) >= index else {}
            if 'error' in email_data:
                speak_text(f'[System]: {email_data["error"]}')
            else:
                speak_text(
                    f'[System]: Email from {email_data["sender"]}. '
                    f'Subject: {email_data["subject"]}.'
                )
                handle_reply(email_data)
            continue

        # ── PROFILE ──────────────────────────────────────────
        elif (web_login.login_status == 'success'
              and any(w in clean_heard for w in ['profile', 'प्रोफ़ाइल'])):
            handle_profile()
            continue

        # ── ADMIN: LIST USERS ────────────────────────────────
        elif (web_login.login_status == 'success'
              and any(w in clean_heard for w in [
                  'list users', 'show users', 'all users',
                  'यूज़र्स देखें', 'सभी यूज़र्स'
              ])):
            current_email = web_login.app.config.get('current_email', '')
            if not is_admin(current_email):
                speak_text(r('not_logged_in'), lang=user_lang)
                continue
            all_users = get_all_users()
            if not all_users:
                speak_text(r('admin_list_empty'), lang=user_lang)
            else:
                speak_text(
                    f'[System]: {len(all_users)} registered users.'
                    if user_lang == 'en'
                    else f'[System]: {len(all_users)} पंजीकृत यूज़र्स।',
                    lang=user_lang,
                )
                for i, u in enumerate(all_users, 1):
                    role_label = 'admin' if u['is_admin'] else 'user'
                    speak_text(
                        f'{i}. {u["name"]}, {u["email"]}, {role_label}, '
                        f'{u["sessions"]} sessions.',
                        lang=user_lang,
                    )
                    time.sleep(0.3)
            continue

        # ── ADMIN: DELETE USER ───────────────────────────────
        elif (web_login.login_status == 'success'
              and any(w in clean_heard for w in [
                  'delete user', 'remove user',
                  'यूज़र डिलीट', 'यूज़र हटाएं'
              ])):
            current_email = web_login.app.config.get('current_email', '')
            if not is_admin(current_email):
                speak_text(r('not_logged_in'), lang=user_lang)
                continue
            speak_text(r('admin_ask_email'), lang=user_lang)
            target_raw, _ = listen_text(duration=10)
            target_email   = clean_spoken_email(target_raw)
            speak_text(f'[User]: {target_email}')
            if not target_email or '@' not in target_email:
                speak_text(r('admin_bad_email'), lang=user_lang)
            elif target_email == current_email:
                speak_text(r('admin_self_delete'), lang=user_lang)
            else:
                speak_text(
                    f'[System]: Delete {target_email}? Say your confirmation word to proceed.'
                    if user_lang == 'en'
                    else f'[System]: {target_email} को डिलीट करें? कन्फर्मेशन वर्ड बोलें।',
                    lang=user_lang,
                )
                conf, _ = listen_text(duration=6)
                conf = conf.lower().strip()
                speak_text(f'[User]: {conf}')
                if any(w in conf for w in confirmation_words):
                    ok, msg = admin_delete_user(target_email)
                    speak_text(f'[System]: {msg}')
                    if ok:
                        _db_log_activity(current_email, 'admin_delete_user',
                                         f'deleted:{target_email}')
                else:
                    speak_text(r('conf_not_recognised'), lang=user_lang)
            continue

        # ── LOGOUT ───────────────────────────────────────────
        elif any(w in clean_heard for w in logout_commands):
            if web_login.login_status == 'success':
                speak_text(
                    '[System]: Logging you out.'
                    if user_lang == 'en'
                    else '[System]: लॉगआउट हो रहे हैं।',
                    lang=user_lang,
                )
                web_login.login_status = 'waiting'
                login_initiated        = False
                _services_processed    = False
                try:
                    requests.post('http://localhost:5000/voice-logout', timeout=3)
                except Exception:
                    pass
                speak_text(r('logout_success'), lang=user_lang)
            else:
                speak_text(r('not_logged_in_lo'), lang=user_lang)
            continue

        # ── TIME ─────────────────────────────────────────────
        elif (('time' in clean_heard and 'date' not in clean_heard)
              or 'समय' in clean_heard):
            t = datetime.datetime.now().strftime('%I:%M %p')
            speak_text(
                f'[System]: The time is {t}.'
                if user_lang == 'en'
                else f'[System]: अभी समय है {t}।',
                lang=user_lang,
            )

        # ── DATE ─────────────────────────────────────────────
        elif ('date' in clean_heard
              or ('what' in clean_heard and 'day' in clean_heard)
              or 'तारीख' in clean_heard):
            d = datetime.datetime.now().strftime('%A, %B %d, %Y')
            speak_text(
                f'[System]: Today is {d}.'
                if user_lang == 'en'
                else f'[System]: आज {d} है।',
                lang=user_lang,
            )

        # ── JOKE ─────────────────────────────────────────────
        elif any(w in clean_heard for w in
                 ['joke', 'funny', 'मज़ाक', 'जोक']):
            joke = random.choice(JOKES_HI if user_lang == 'hi' else JOKES_EN)
            speak_text(f'[System]: {joke}', lang=user_lang)

        # ── CALCULATOR ───────────────────────────────────────
        elif any(w in clean_heard for w in [
            'calculate', 'what is', "what's", 'plus', 'minus', 'times',
            'divided by', 'जमा', 'घटा', 'गुणा', 'भाग', 'क्या है', 'कितना'
        ]):
            speak_text(calculate(clean_heard), lang=user_lang)

        # ── GOODBYE ──────────────────────────────────────────
        elif any(w in clean_heard for w in ending):
            if web_login.login_status == 'success':
                speak_text(
                    '[System]: Logging you out first.'
                    if user_lang == 'en'
                    else '[System]: पहले लॉगआउट हो रहे हैं।',
                    lang=user_lang,
                )
                web_login.login_status = 'waiting'
                login_initiated        = False
                _services_processed    = False
                try:
                    requests.post('http://localhost:5000/voice-logout', timeout=3)
                except Exception:
                    pass
            speak_text(bye_hi if user_lang == 'hi' else bye_en, lang=user_lang)
            break

        # ── FALLBACK ─────────────────────────────────────────
        elif not _is_nav:
            speak_text(r('not_understood'), lang=user_lang)

    file.close()