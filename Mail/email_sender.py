# ========================
# EMAIL SENDER — email_sender.py
# ========================
import smtplib
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from Audio.speech_to_text import listen_text
from Backend.database import verify_pin
import Mail.web_login as _web_login
from Audio.text_to_speech import speak_text as _tts_orig

def speak_text(text: str, lang: str = 'en'):
    _web_login.push_to_feed(text)
    _tts_orig(text, lang=lang)

CONFIRM_WORDS = ['yes', 'ok', 'yah', 'ya', 'confirm', 'send', 'correct']
CANCEL_WORDS  = ['no', 'nah', 'nope', 'cancel', 'stop', "don't"]

def send_email(to: str, subject: str, body: str, user_email: str = None, app_pass: str = None) -> tuple[bool, str]:
    # Use provided creds or fallback to environment
    EMAIL_USER = user_email or os.getenv('EMAIL_USER')
    EMAIL_PASS = app_pass or os.getenv('EMAIL_PASS')
    
    if not EMAIL_USER or not EMAIL_PASS:
        return False, '[System]: Gmail credentials not configured.'

    try:
        msg = MIMEMultipart()
        msg['From']    = EMAIL_USER
        msg['To']      = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to, msg.as_string())

        print(f"[Email] Sent to {to} | Subject: {subject}")
        return True, f'[System]: Email sent successfully to {to}.'

    except smtplib.SMTPAuthenticationError:
        return False, '[System]: Authentication failed. Check your Gmail App Password.'
    except Exception as e:
        return False, f'[System]: Failed to send. {str(e)}'

def send_reply_direct(to: str, subject: str, body: str, msg_id: str = '', user_email: str = None, app_pass: str = None) -> tuple[bool, str]:
    """
    Sends an email directly with pre-composed content.
    """
    # Simply wrapper for send_email for now
    return send_email(to, subject, body, user_email=user_email, app_pass=app_pass)

def spoken_to_email(spoken: str) -> str:
    result = str(spoken).strip().lower()
    # Handle common artifacts
    for at in ['at the rate', 'at the rate of', 'at the', 'at']:
        if at in result:
            result = result.replace(at, '@')
            break
    result = result.replace(' dot ', '.')
    result = result.replace(' dot', '.')
    result = result.replace('dot ', '.')
    # Remove spaces around @ and .
    result = re.sub(r'\s*@\s*', '@', result)
    result = re.sub(r'\s*\.\s*', '.', result)
    # Generic cleanup
    result = result.replace(' ', '')
    return result

def is_valid_email(address: str) -> bool:
    return '@' in address and '.' in address.split('@')[-1]

__all__ = [
    'send_email', 'send_reply_direct', 'spoken_to_email', 'is_valid_email'
]
