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
from Mail.web_login import push_to_feed, push_nav_command, push_action
import Mail.web_login as web_login
import threading, requests
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
_services_processed  = False   

bye_en = '[System]: Goodbye! Take care.'
bye_hi = '[System]: अलविदा! अपना ख्याल रखें।'

# ----------------------
# HELPERS
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
    prev = None
    while prev != result:
        prev = result
        result = re.sub(r'([a-z0-9])\.([a-z0-9])', r'\1 \2', result)
    result = re.sub(r'([a-z0-9])\.$', r'\1', result)
    result = re.sub(r'([a-z0-9])\.\s', r'\1 ', result)
    result = re.sub(r'\.\s+', ' ', result)
    if '@' in result:
        parts  = result.split('@', 1)
        local, domain = parts[0].strip().rstrip('.'), parts[1].strip().lstrip('.')
        local = local.replace(' ', '')
        domain = domain.replace(' ', '')
        domain = re.sub(r'(gmail|yahoo|outlook|hotmail|icloud|protonmail|live|rediff|proton)(com|net|org|in|co)', r'\1.\2', domain)
        result = local + '@' + domain
    else:
        result = result.replace(' ', '')
    result = re.sub(r'therate([a-z])', r'\1', result)
    result = re.sub(r'therad([a-z])', r'\1', result)
    result = re.sub(r'@[a-z]*?(gmail|yahoo|outlook|hotmail|icloud|protonmail|live)\.', r'@\1.', result)
    if '@' not in result:
        result = re.sub(r'(gmail|yahoo|outlook|hotmail|icloud|protonmail|live)\.', r'@\1.', result)
    return result.strip('.')

def clean_spoken_name(spoken: str) -> str:
    result = spoken.strip().lower()
    result = re.sub(r'(?<=[a-z])-(?=[a-z])', ' ', result)
    tokens = result.split()
    if tokens and sum(1 for t in tokens if len(t) == 1) / len(tokens) > 0.5:
        result = ''.join(tokens)
    return result.strip()

# ----------------------
# RESPONSES
# ----------------------
RESPONSES = {
    'greeting':            {'en': '[System]: Hi! How can I help you?', 'hi': '[System]: नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?'},
    'already_logged_in':   {'en': '[System]: You are already logged in.', 'hi': '[System]: आप पहले से लॉगिन हैं।'},
    'login_in_progress':   {'en': '[System]: Login is already in progress.', 'hi': '[System]: लॉगिन पहले से जारी है।'},
    'login_opened':        {'en': '[System]: Login page opened. Please log in via browser or say your audio password.', 'hi': '[System]: लॉगिन पेज खुल गया। कृपया ब्राउज़र से लॉगिन करें या ऑडियो पासवर्ड बोलें।'},
    'login_failed':        {'en': '[System]: Audio password not recognised. Login cancelled.', 'hi': '[System]: ऑडियो पासवर्ड पहचाना नहीं गया। लॉगिन रद्द।'},
    'login_cancelled':     {'en': '[System]: Login cancelled.', 'hi': '[System]: लॉगिन रद्द किया गया।'},
    'select_services':     {'en': '[System]: Please select your services on the dashboard.', 'hi': '[System]: कृपया डैशबोर्ड पर अपनी सेवाएं चुनें।'},
    'signup_opening':      {'en': '[System]: Opening signup page...', 'hi': '[System]: साइनअप पेज खोल रहे हैं...'},
    'not_logged_in':       {'en': '[System]: Please log in first.', 'hi': '[System]: कृपया पहले लॉगिन करें।'},
    'logout_success':      {'en': '[System]: You have been logged out successfully.', 'hi': '[System]: आप सफलतापूर्वक लॉगआउट हो गए।'},
    'not_logged_in_lo':    {'en': '[System]: You are not currently logged in.', 'hi': '[System]: आप अभी लॉगिन नहीं हैं।'},
    'not_understood':      {'en': '[System]: Please try a different command.', 'hi': '[System]: कृपया कोई अलग कमांड आज़माएं।'},
    'tg_fetching':         {'en': '[System]: Fetching your Telegram messages.', 'hi': '[System]: आपके Telegram संदेश लाए जा रहे हैं।'},
    'tg_none':             {'en': '[System]: No Telegram messages found.', 'hi': '[System]: कोई Telegram संदेश नहीं मिला।'},
    'tg_next':             {'en': '[System]: Okay, moving to the next message.', 'hi': '[System]: ठीक है, अगले संदेश पर जा रहे हैं।'},
    'tg_latest':           {'en': '[System]: Getting your latest Telegram message.', 'hi': '[System]: आपका नवीनतम Telegram संदेश लाया जा रहा है।'},
    'tg_who':              {'en': '[System]: Who do you want to send a Telegram message to?', 'hi': '[System]: आप किसे Telegram संदेश भेजना चाहते हैं?'},
    'tg_what':             {'en': '[System]: What is your message?', 'hi': '[System]: आपका संदेश क्या है?'},
    'tg_confirm_send':     {'en': '[System]: Sending. Please confirm.', 'hi': '[System]: भेज रहे हैं। कृपया पुष्टि करें।'},
    'tg_cancelled':        {'en': '[System]: Telegram message cancelled.', 'hi': '[System]: Telegram संदेश रद्द किया गया।'},
    'tg_no_recipient':     {'en': '[System]: I did not catch the recipient.', 'hi': '[System]: प्राप्तकर्ता समझ नहीं आया।'},
    'tg_empty_msg':        {'en': '[System]: Message was empty. Cancelled.', 'hi': '[System]: संदेश खाली था। रद्द किया गया।'},
    'tg_auth_prompt':      {'en': '[System]: Telegram needs authorization. Say your secret password to open the login page.', 'hi': '[System]: Telegram को अनुमति चाहिए। लॉगिन पेज खोलने के लिए पासवर्ड बोलें।'},
    'tg_auth_ok':          {'en': '[System]: Confirmed. Opening Telegram login page.', 'hi': '[System]: पुष्टि हुई। Telegram लॉगिन पेज खुल रहा है।'},
    'tg_auth_fail':        {'en': '[System]: Incorrect password. Telegram not connected.', 'hi': '[System]: गलत पासवर्ड। Telegram कनेक्ट नहीं हुआ।'},
    'tg_auto':             {'en': '[System]: Telegram connected automatically.', 'hi': '[System]: Telegram स्वचालित रूप से जुड़ गया।'},
    'tg_starting':         {'en': '[System]: Starting Telegram.', 'hi': '[System]: Telegram शुरू हो रहा है।'},
    'gmail_ready':         {'en': '[System]: Gmail ready.', 'hi': '[System]: Gmail तैयार है।'},
    'email_send_prompt':   {'en': '[System]: You want to send an email?', 'hi': '[System]: क्या आप ईमेल भेजना चाहते हैं?'},
    'email_cancelled':     {'en': '[System]: Ok, no email sent.', 'hi': '[System]: ठीक है, कोई ईमेल नहीं भेजा।'},
    'inbox_prompt':        {'en': '[System]: You want to check the inbox?', 'hi': '[System]: क्या आप इनबॉक्स देखना चाहते हैं?'},
    'inbox_category':      {'en': '[System]: Primary, promotions, updates or all?', 'hi': '[System]: प्राइमरी, प्रमोशन, अपडेट या सभी?'},
    'inbox_ok':            {'en': '[System]: Ok, thanks for confirming.', 'hi': '[System]: ठीक है, धन्यवाद।'},
    'cat_prompt':          {'en': '[System]: Should I read from primary, promotions, updates or all emails?', 'hi': '[System]: प्राइमरी, प्रमोशन, अपडेट या सभी ईमेल पढ़ूं?'},
    'reply_fetching':      {'en': '[System]: Fetching the latest email.', 'hi': '[System]: नवीनतम ईमेल लाया जा रहा है।'},
    'reply_which':         {'en': '[System]: Which email do you want to reply to? Say a number — 1 for latest.', 'hi': '[System]: किस ईमेल का जवाब देना है? नंबर बोलें — 1 सबसे नया।'},
    'profile_prompt':      {'en': '[System]: What would you like to do? Say view, change name, change password, change audio password, or delete my account.', 'hi': '[System]: आप क्या करना चाहते हैं? व्यू, नाम बदलें, पासवर्ड बदलें, ऑडियो पासवर्ड बदलें, या मेरा अकाउंट डिलीट करें।'},
    'admin_menu':          {'en': '[System]: Admin profile menu. Say: view, change name, change password, change audio password, delete my account, list users, or delete user.', 'hi': '[System]: एडमिन प्रोफ़ाइल मेनू। बोलें: व्यू, नाम बदलें, पासवर्ड बदलें, ऑडियो पासवर्ड बदलें, मेरा अकाउंट डिलीट करें, यूज़र्स देखें, या यूज़र डिलीट करें।'},
    'profile_not_found':   {'en': '[System]: Could not find your profile. Please log in again.', 'hi': '[System]: आपका प्रोफ़ाइल नहीं मिला। कृपया फिर से लॉगिन करें।'},
    'profile_google':      {'en': '[System]: Profile not found in database. You may have logged in via Google.', 'hi': '[System]: डेटाबेस में प्रोफ़ाइल नहीं मिला। आपने Google से लॉगिन किया होगा।'},
    'name_prompt':         {'en': '[System]: What would you like your new name to be?', 'hi': '[System]: आपका नया नाम क्या होगा?'},
    'name_cancelled':      {'en': '[System]: No name received. Cancelled.', 'hi': '[System]: कोई नाम नहीं मिला। रद्द किया गया।'},
    'pass_current':        {'en': '[System]: Please say your current password.', 'hi': '[System]: कृपया अपना मौजूदा पासवर्ड बोलें।'},
    'pass_new':            {'en': '[System]: Please say your new password.', 'hi': '[System]: कृपया अपना नया पासवर्ड बोलें।'},
    'pass_cancelled':      {'en': '[System]: Password change cancelled.', 'hi': '[System]: पासवर्ड बदलना रद्द किया गया।'},
    'audio_prompt':        {'en': '[System]: Please say your new secret audio password.', 'hi': '[System]: कृपया अपना नया ऑडियो पासवर्ड बोलें।'},
    'audio_cancelled':     {'en': '[System]: No audio password received. Cancelled.', 'hi': '[System]: कोई ऑडियो पासवर्ड नहीं मिला। रद्द किया गया।'},
    'delete_confirm':      {'en': '[System]: Are you sure? Say your confirmation word to proceed.', 'hi': '[System]: क्या आप वाकई? पुष्टि के लिए कन्फर्मेशन वर्ड बोलें।'},
    'delete_pass':         {'en': '[System]: Please say your password to confirm deletion.', 'hi': '[System]: डिलीट की पुष्टि के लिए पासवर्ड बोलें।'},
    'delete_cancelled':    {'en': '[System]: Account deletion cancelled.', 'hi': '[System]: अकाउंट डिलीट रद्द किया गया।'},
    'admin_list_empty':    {'en': '[System]: No users registered yet.', 'hi': '[System]: कोई यूज़र पंजीकृत नहीं है।'},
    'admin_ask_email':     {'en': '[System]: Say the email address of the user to delete.', 'hi': '[System]: जिस यूज़र को डिलीट करना है उसका ईमेल बोलें।'},
    'admin_bad_email':     {'en': '[System]: Could not understand the email address. Cancelled.', 'hi': '[System]: ईमेल पता समझ नहीं आया। रद्द किया।'},
    'admin_self_delete':   {'en': '[System]: Use "delete my account" to delete your own account.', 'hi': '[System]: अपना खाता डिलीट करने के लिए "मेरा अकाउंट डिलीट" कहें।'},
    'conf_not_recognised': {'en': '[System]: Confirmation not recognised. Cancelled.', 'hi': '[System]: पुष्टि नहीं मिली। रद्द किया।'},
    'suggest_generating':  {'en': '[System]: Analysing and generating a suggested reply...', 'hi': '[System]: सुझाया गया जवाब तैयार किया जा रहा है...'},
    'suggest_send':        {'en': 'Shall I send this?', 'hi': 'क्या मैं यह भेजूं?'},
    'suggest_sending':     {'en': '[System]: Sending suggested reply...', 'hi': '[System]: सुझाया गया जवाब भेजा जा रहा है...'},
    'suggest_custom':      {'en': '[System]: Ok, let me take your custom reply instead.', 'hi': '[System]: ठीक है, आपका खुद का जवाब लेते हैं।'},
    'suggest_failed':      {'en': '[System]: Could not generate a suggestion. Please dictate your reply.', 'hi': '[System]: सुझाव नहीं बन सका। कृपया अपना जवाब बोलें।'},
    'nav_confirmed':       {'en': '[System]: Opening page.', 'hi': '[System]: पेज खोल रहे हैं।'},
}

HINDI_COMMAND_MAP = {
    'लोगें': 'login', 'लॉगें': 'login', 'लॉग': 'login', 'लोगिन': 'login',
    'लॉगआउट': 'logout', 'लॉग आउट': 'logout', 'साइन आउट': 'logout',
    'नमस्ते': 'hello', 'हेलो': 'hello', 'हाय': 'hello',
    'अलविदा': 'goodbye', 'बाय': 'bye', 'बंद करो': 'exit',
    'हाँ': 'yes', 'हां': 'yes', 'नहीं': 'no',
    'ईमेल': 'email', 'मेल': 'mail', 'संदेश': 'message',
    'इनबॉक्स': 'inbox', 'समय': 'time', 'तारीख': 'date',
    'मज़ाक': 'joke', 'जोक': 'joke', 'प्रोफ़ाइल': 'profile',
    'टेलीग्राम': 'telegram', 'भेजो': 'send', 'जांचो': 'check', 'जवाब': 'reply',
    'हिसाब': 'calculate', 'कितना': 'what is', 'नवीनतम': 'latest', 'नया': 'recent',
    'एडमिन': 'admin', 'उपयोगकर्ता': 'users', 'डिलीट': 'delete', 'यूज़र': 'user',
    'चेक': 'check', 'जाँचो': 'check', 'देखो': 'check', 'खोलो': 'check', 'पढ़ो': 'check',
    'बेजी': 'send', 'भेजी': 'send', 'बेजो': 'send', 'भेज': 'send', 'सेंड': 'send',
    'लिखो': 'compose', 'तेलीग्राम': 'telegram', 'टेलीग्रम': 'telegram', 'टेली': 'telegram',
}

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
    for hindi, english in HINDI_COMMAND_MAP.items(): text = text.replace(hindi, english)
    return text

def r(key: str, lang: str = None) -> str:
    _lang = lang or user_lang
    return RESPONSES.get(key, {}).get(_lang, RESPONSES.get(key, {}).get('en', ''))

def speak_text(text: str, lang: str = 'en'):
    push_to_feed(text)
    _speak_text_orig(text, lang=lang)

def log_activity(action: str, detail: str = ''):
    if not web_login.is_voice_authenticated: return
    email = web_login.app.config.get('current_email', '')
    if email: _db_log_activity(email, action, detail)

mail_req, inbox_req, affirmation, negation = ['mail', 'email', 'message', 'मेल', 'ईमेल', 'संदेश'], ['inbox', 'mail', 'mails', 'इनबॉक्स', 'मेल'], ['yes', 'ok', 'yah', 'ya', 'want to', 'हाँ', 'ठीक है', 'हां', 'भेजो'], ['no', 'nah', 'nope', "don't want to", 'नहीं', 'मत भेजो']
greeting, ending, logout_commands, confirmation_words = ['hi', 'hello', 'hey', 'नमस्ते', 'हेलो', 'हाय'], ['goodbye', 'bye', 'exit', 'see you later', 'अलविदा', 'बाय', 'बंद करो'], ['logout', 'log out', 'sign out', 'signout', 'लॉगआउट', 'साइन आउट'], ['correct', 'confirm', 'yes', 'हाँ', 'सही']
if SECRET_AUD: confirmation_words.append(SECRET_AUD.lower().strip())

def on_new_telegram(sender, text): speak_text(f'[Telegram]: New message from {sender}: {text}')
set_notification_callback(on_new_telegram)

JOKES_EN = ["Why do programmers prefer dark mode? Because light attracts bugs!", "Why did the computer go to the doctor? It had a virus!", "I told my computer I needed a break. Now it won't stop sending me Kit Kat ads.", "Why did the programmer quit his job? Because he didn't get arrays.", "How many programmers does it take to change a light bulb? None — that's a hardware problem."]
JOKES_HI = ["प्रोग्रामर डार्क मोड क्यों पसंद करते हैं? क्योंकि रोशनी में बग आते हैं!", "कंप्यूटर डॉक्टर के पास क्यों गया? उसे वायरस हो गया था!", "मैंने कंप्यूटर से कहा मुझे ब्रेक चाहिए, अब वो Kit Kat के विज्ञापन भेजता रहता है।", "प्रोग्रामर ने नौकरी क्यों छोड़ी? उसे arrays समझ नहीं आई।", "गणित की किताब उदास क्यों थी? उसमें बहुत सारी समस्याएं थीं।"]

MATH_WORDS = {'plus': '+', 'add': '+', 'minus': '-', 'subtract': '-', 'times': '*', 'multiplied by': '*', 'multiply': '*', 'divided by': '/', 'divide': '/', 'over': '/', 'power': '**', 'squared': '**2', 'cubed': '**3', 'percent of': '/100*', 'जमा': '+', 'घटा': '-', 'गुणा': '*', 'भाग': '/'}
def calculate(text: str) -> str:
    expr = text.lower()
    for filler in ['what is', "what's", 'calculate', 'compute', 'equals', 'equal to', '?', 'क्या है', 'बताओ', 'हिसाब', 'कितना']: expr = expr.replace(filler, '')
    for word, symbol in MATH_WORDS.items(): expr = expr.replace(word, symbol)
    expr = re.sub(r'[^0-9+\-*/().\s]', '', expr).strip()
    if not expr: return r('not_understood')
    try:
        result = eval(expr)
        if isinstance(result, float) and result.is_integer(): result = int(result)
        return f'[System]: {"उत्तर है" if user_lang=="hi" else "The answer is"} {result}।'
    except: return r('not_understood')

def generate_local_reply(message: str) -> str | None:
    try:
        res = requests.post(url="https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {OPEN_ROUTER_API_key}"}, data=json.dumps({"model": "openrouter/hunter-alpha", "messages": [{"role": "user", "content": f"Write a short natural reply (1-2 sentences) to:\n{message}"}]}))
        return res.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip() or None
    except: return None

def handle_reply(email_data: dict):
    reply_to, subject = email_data['sender'], email_data['subject']
    speak_text(r('suggest_generating'), lang=user_lang)
    suggestion = generate_local_reply(f"From: {reply_to}\nSubject: {subject}\n\n{email_data.get('summary', '')}")
    if suggestion:
        speak_text(f'[System]: {suggestion}. {r("suggest_send")}', lang=user_lang)
        response, _ = listen_text()
        if any(w in response.lower() for w in affirmation):
            speak_text(r('suggest_sending'), lang=user_lang)
            speak_text(reply_email_by_voice(reply_to, subject, email_data.get('msg_id', '')))
            return
    else: speak_text(r('suggest_failed'), lang=user_lang)
    speak_text(reply_email_by_voice(reply_to, subject, email_data.get('msg_id', '')))

def handle_telegram_reply(recipient: str, original_message: str):
    speak_text(r('suggest_generating'), lang=user_lang)
    suggestion = generate_local_reply(original_message)
    if suggestion:
        speak_text(f'[System]: {suggestion}. {r("suggest_send")}', lang=user_lang)
        confirm, _ = listen_text()
        if any(w in confirm.lower() for w in affirmation):
            success, result = telegram_send_message(recipient, suggestion)
            speak_text(f'[System]: {result}')
            return
    else: speak_text(r('suggest_failed'), lang=user_lang)
    message, _ = listen_text(duration=10)
    speak_text(r('tg_confirm_send'), lang=user_lang)
    confirm, _ = listen_text()
    if any(w in confirm.lower() for w in affirmation):
        success, result = telegram_send_message(recipient, message)
        speak_text(f'[System]: {result}')
    else: speak_text(r('tg_cancelled'), lang=user_lang)

def handle_profile():
    current_email = web_login.app.config.get('current_email', '')
    if not current_email: speak_text(r('profile_not_found'), lang=user_lang); return
    user_is_admin = is_admin(current_email)
    speak_text(r('admin_menu') if user_is_admin else r('profile_prompt'), lang=user_lang)
    response, _ = listen_text()
    clean_res = response.lower().strip()
    if 'view' in clean_res:
        user = get_user_by_email(current_email)
        if user: speak_text(f'[System]: Your profile. Name: {user["name"]}. Email: {user["email"]}.')
        else: speak_text(r('profile_google'), lang=user_lang)
    elif 'name' in clean_res:
        speak_text(r('name_prompt'), lang=user_lang)
        new_name, _ = listen_text()
        if new_name: ok, msg = update_name(current_email, clean_spoken_name(new_name)); speak_text(f'[System]: {msg}')
        else: speak_text(r('name_cancelled'), lang=user_lang)
    elif 'logout' in clean_res:
        do_logout()
    elif 'delete' in clean_res:
        speak_text(r('delete_confirm'), lang=user_lang)
        conf, _ = listen_text()
        if any(w in conf.lower() for w in confirmation_words):
            speak_text(r('delete_pass'), lang=user_lang)
            password, _ = listen_text()
            ok, msg = delete_user(current_email, password.strip()); speak_text(f'[System]: {msg}')
            if ok: do_logout()
        else: speak_text(r('delete_cancelled'), lang=user_lang)

def do_logout():
    speak_text(r('logout_success'), lang=user_lang)
    web_login.is_voice_authenticated = False
    web_login.force_logout = True
    web_login.login_status = 'waiting'

def _connect_services(verified_services: list, announce: bool = True):
    if 'telegram' in verified_services:
        start_telegram_in_thread()
        time.sleep(5)
        from Telegram.telegram import _client, _loop as tg_loop
        import asyncio
        authorized = False
        if _client and _client.is_connected():
            try: authorized = asyncio.run_coroutine_threadsafe(_client.is_user_authorized(), tg_loop).result(timeout=5)
            except: authorized = False
        if not authorized:
            speak_text(r('tg_auth_prompt'), lang=user_lang)
            auth_word, _ = listen_text(duration=8)
            if auth_word.lower().strip() == SECRET_AUD.lower().strip():
                speak_text(r('tg_auth_ok'), lang=user_lang)
                push_action('open_url', {'url': '/telegram-auth'})
            else: speak_text(r('tg_auth_fail'), lang=user_lang)
        elif announce: speak_text(r('tg_auto'), lang=user_lang)
    if announce and verified_services: speak_text(f'[System]: {", ".join(verified_services)} connected.', lang=user_lang)

print("[Main] Starting Flask Server...")
threading.Thread(target=web_login.start_server, daemon=True).start()
time.sleep(1)

with open('Audio/Transcribe.txt', 'a', encoding='utf-8') as file:
    while True:
        if web_login.login_from_signup and not login_initiated:
            web_login.login_from_signup = False
            login_initiated = True
            speak_text('[System]: Welcome! Say your audio password to complete login.')
            continue
        
        if awaiting_services and web_login.selected_services:
            services = list(web_login.selected_services)
            web_login.app.config['verified_services'] = services
            awaiting_services, _services_processed = False, True
            _connect_services(services, announce=False)

        if web_login.user_typing: typing_pause_until = time.time() + 5; web_login.user_typing = False
        if web_login.signup_open or time.time() < typing_pause_until: time.sleep(0.5); continue

        heard, user_lang = listen_text(force_lang=force_lang)
        if not heard: continue
        speak_text(f'[User]: {heard}')
        clean_heard = normalize_hindi(heard.lower().strip().replace('.', ''))
        file.write(f'{clean_heard}\n')

        if web_login.is_voice_authenticated: log_activity('voice_command', clean_heard[:100])

        _is_nav = False
        for phrase in NAV_PHRASES:
            if phrase in clean_heard:
                push_nav_command(clean_heard)
                if any(x in phrase for x in ['select', 'enable', 'add', 'deselect', 'disable', 'remove']):
                    svc = 'Gmail' if 'gmail' in phrase else 'Telegram'
                    speak_text(f'[System]: {"Selecting" if "deselect" not in phrase else "Removing"} {svc}.', lang=user_lang)
                else: speak_text(r('nav_confirmed'), lang=user_lang)
                _is_nav = True; break
        if _is_nav: continue

        if any(w in clean_heard for w in greeting): speak_text(r('greeting'), lang=user_lang)
        elif 'hindi mode' in clean_heard: force_lang = user_lang = 'hi'; speak_text('[System]: हिंदी मोड चालू।', lang='hi')
        elif 'english mode' in clean_heard: force_lang = user_lang = 'en'; speak_text('[System]: English mode active.', lang='en')
        elif 'login' in clean_heard:
            if web_login.is_voice_authenticated: speak_text(r('already_logged_in'), lang=user_lang)
            else: web_login.login_status, login_initiated = 'waiting', True; speak_text(r('login_opened'), lang=user_lang)
        elif 'signup' in clean_heard or 'register' in clean_heard:
            if web_login.signup_open: speak_text('[System]: Signup page already open.')
            else: push_action('open_url', {'url': '/signup'}); speak_text(r('signup_opening'), lang=user_lang)
        elif login_initiated and web_login.login_status != 'success':
            login_initiated = False
            matched, name, email = verify_audio(clean_heard)
            if matched:
                speak_text(f'[System]: Welcome, {name}. Login confirmed.', lang=user_lang)
                web_login.login_status, web_login.is_voice_authenticated = 'success', True
                web_login.app.config['current_email'] = email
                _db_log_activity(email, 'login', 'audio')
                awaiting_services = True
            else: speak_text(r('login_failed'), lang=user_lang); web_login.login_status = 'failed'

        # ── TELEGRAM ──────────────────────────────────────────
        elif web_login.is_voice_authenticated and 'telegram' in clean_heard:
            if 'send' in clean_heard:
                speak_text(r('tg_who'), lang=user_lang)
                recipient_raw, _ = listen_text(duration=10)
                recipient = clean_spoken_name(recipient_raw)
                if not recipient: speak_text(r('tg_no_recipient'), lang=user_lang); continue
                speak_text(f'[User]: {recipient}')
                speak_text(r('tg_what'), lang=user_lang)
                message, _ = listen_text(duration=10)
                if not message.strip(): speak_text(r('tg_empty_msg'), lang=user_lang); continue
                speak_text(f'[User]: {message}')
                speak_text(r('tg_confirm_send'), lang=user_lang)
                conf, _ = listen_text()
                if any(w in conf.lower() for w in affirmation):
                    speak_text('[System]: Say your Telegram PIN to confirm.', lang=user_lang)
                    pin_h, _ = listen_text()
                    if verify_pin(web_login.app.config.get('current_email'), 'telegram', spoken_pin_to_digits(pin_h)):
                        success, res = telegram_send_message(recipient, message)
                        speak_text(f'[System]: {res}')
                    else: speak_text('[System]: Incorrect PIN.', lang=user_lang)
            elif any(w in clean_heard for w in inbox_req + ['message', 'messages']):
                speak_text(r('tg_fetching'), lang=user_lang)
                msgs = telegram_get_messages(5)
                if msgs:
                    for i, m in enumerate(msgs, 1):
                        speak_text(f"Telegram {i}. From: {m['name']}. Message: {m['message']}.")
                        speak_text(r('suggest_send'), lang=user_lang)
                        rep, _ = listen_text()
                        if any(w in rep.lower() for w in affirmation): handle_telegram_reply(m['name'], m['message'])
                else: speak_text(r('tg_none'), lang=user_lang)

        # ── EMAIL ─────────────────────────────────────────────
        elif web_login.is_voice_authenticated and any(w in clean_heard for w in mail_req):
            if 'send' in clean_heard or 'compose' in clean_heard:
                speak_text(r('email_send_prompt'), lang=user_lang)
                res, _ = listen_text()
                if any(w in res.lower() for w in affirmation):
                    speak_text('[System]: Say recipient email.', lang=user_lang)
                    raw_email, _ = listen_text()
                    email_addr = clean_spoken_email(raw_email)
                    speak_text('[System]: Subject?', lang=user_lang)
                    subj, _ = listen_text()
                    speak_text('[System]: Message body?', lang=user_lang)
                    body, _ = listen_text()
                    speak_text(f'[System]: Send to {email_addr}? Say your Gmail PIN to confirm.')
                    pin_h, _ = listen_text()
                    if verify_pin(web_login.app.config.get('current_email'), 'gmail', spoken_pin_to_digits(pin_h)):
                        ok, msg = send_reply_direct(to=email_addr, subject=subj, body=body)
                        speak_text(f'[System]: {msg}')
                    else: speak_text('[System]: Incorrect PIN.', lang=user_lang)
            elif any(w in clean_heard for w in inbox_req):
                speak_text(r('cat_prompt'), lang=user_lang)
                cat, _ = listen_text()
                category = 'PRIMARY' if 'primary' in cat.lower() else 'ALL'
                emails = get_top_senders(3, category=category)
                for i, e in enumerate(emails, 1):
                    if 'error' in e: speak_text(e['error']); break
                    speak_text(f"Email {i}. From: {e['sender']}. Subject: {e['subject']}. Summary: {e['summary']}")
                    speak_text('[System]: Reply?', lang=user_lang)
                    rep, _ = listen_text()
                    if any(w in rep.lower() for w in affirmation): handle_reply(e)

        elif any(w in clean_heard for w in logout_commands): do_logout()
        elif 'time' in clean_heard: speak_text(f'[System]: The time is {datetime.datetime.now().strftime("%I:%M %p")}.')
        elif 'joke' in clean_heard: speak_text(f'[System]: {random.choice(JOKES_HI if user_lang=="hi" else JOKES_EN)}')
        elif any(w in clean_heard for w in ['calculate', 'plus', 'minus', 'times']): speak_text(calculate(clean_heard))
        elif any(w in clean_heard for w in ending): do_logout(); speak_text(r('bye_hi' if user_lang=='hi' else 'bye_en')); break
        elif not _is_nav: speak_text(r('not_understood'), lang=user_lang)
