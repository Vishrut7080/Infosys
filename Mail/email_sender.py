# ========================
# EMAIL SENDER — email_sender.py
# ========================
# Flow:
#   compose_email_by_voice() collects recipient/subject/body,
#   asks yes/no confirmation, then returns '__READY_TO_SEND__'
#   and stores details in app.config['pending_email'].
#   main.py then asks for PIN and calls send_email() directly.
#   PIN is NEVER asked inside this file for compose flow.
#   PIN IS asked inside reply_email_by_voice() since that's
#   self-contained and called directly from main.py.
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


# ----------------------
# Core Send Function
# ----------------------

def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
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
    except smtplib.SMTPRecipientsRefused:
        return False, f'[System]: Recipient {to} was refused. Check the address.'
    except smtplib.SMTPException as e:
        return False, f'[System]: SMTP error: {str(e)}'
    except Exception as e:
        return False, f'[System]: Unexpected error: {str(e)}'


# ----------------------
# Email Address Parser
# ----------------------

def spoken_to_email(spoken: str) -> str:
    result = spoken.strip().lower()

    result = re.sub(r'(?<=[a-z])-(?=[a-z0-9])', '', result)
    result = re.sub(r'(?<=[a-z0-9])-(?=[a-z])', '', result)
    result = re.sub(r'(?<=[0-9])-(?=[0-9])', '', result)

    # Replace spoken @ symbols — longest first, break after first match
    for at in ['at the rate', 'at the rate of', 'at the', 'at']:
        if at in result:
            result = result.replace(at, '@')
            break

    # Replace spoken dot
    result = result.replace(' dot ', '.')
    result = result.replace(' dot', '.')
    result = result.replace('dot ', '.')

    # Remove trailing dot before @
    result = re.sub(r'\.\s*@', '@', result)

    prev = None
    while prev != result:
        prev = result
        result = re.sub(r'([a-z0-9])\.([a-z0-9])', r'\1 \2', result)
    result = re.sub(r'([a-z0-9])\.$', r'\1', result)
    result = re.sub(r'([a-z0-9])\.\s', r'\1 ', result)

    # Remove standalone trailing dots
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

        # Re-insert missing dot before TLD in no-@ case too
        result = re.sub(
            r'(gmail|yahoo|outlook|hotmail|icloud|protonmail|live|rediff|proton)(com|net|org|in|co)',
            r'\1.\2',
            result
        )

    # Fix "therategmail" / "theradegmail" Whisper artifacts
    result = re.sub(r'therate([a-z])', r'\1', result)
    result = re.sub(r'therad([a-z])', r'\1', result)

    # Fix Whisper domain prefix artifacts — @therategmail.com → @gmail.com
    result = re.sub(
        r'@[a-z]*?(gmail|yahoo|outlook|hotmail|icloud|protonmail|live)\.',
        r'@\1.',
        result
    )

    # Last resort — insert @ before known domain if still missing
    if '@' not in result:
        result = re.sub(
            r'(gmail|yahoo|outlook|hotmail|icloud|protonmail|live)\.',
            r'@\1.',
            result
        )

    result = result.strip('.')
    return result


# ----------------------
# Email Validator
# ----------------------

def is_valid_email(address: str) -> bool:
    domain_part = address.split('@')[-1] if '@' in address else ''
    return (
        '@' in address
        and len(domain_part) > 3
        and bool(re.search(r'[a-z]+\.[a-z]+', domain_part))
    )


# ----------------------
# Voice Compose Flow
# ----------------------
# NOTE: This function does NOT ask for PIN.
# It collects details, asks yes/no, then returns '__READY_TO_SEND__'
# and stores details in app.config['pending_email'].
# main.py handles the PIN and calls send_email() after verification.

def compose_email_by_voice() -> str:

    # ── Step 1: Recipient ──
    speak_text('[System]: Please say the recipient email address.')
    recipient, _ = listen_text(duration=10)
    recipient = recipient.strip()
    speak_text(f'[User]: {recipient}')
    recipient_clean = spoken_to_email(recipient)

    if not is_valid_email(recipient_clean):
        speak_text(
            f'[System]: That doesn\'t look valid: {recipient_clean}. Try again.'
        )
        speak_text('[System]: Please say the recipient email address again.')
        recipient, _ = listen_text(duration=10)
        recipient = recipient.strip()
        speak_text(f'[User]: {recipient}')
        recipient_clean = spoken_to_email(recipient)

        if not is_valid_email(recipient_clean):
            return '[System]: Could not get a valid email address. Email cancelled.'

    # ── Step 2: Subject ──
    speak_text('[System]: What is the subject of your email?')
    subject, _ = listen_text(duration=8)
    subject = subject.strip()
    speak_text(f'[User]: {subject}')

    if not subject or subject.startswith('[System]'):
        return '[System]: No subject received. Email cancelled.'

    # ── Step 3: Body ──
    speak_text('[System]: Please say your message.')
    body, _ = listen_text(duration=15)
    body = body.strip()
    speak_text(f'[User]: {body}')

    if not body or body.startswith('[System]'):
        return '[System]: No message received. Email cancelled.'

    # ── Step 4: Yes/No Confirmation ──
    speak_text(
        f'[System]: Ready to send. '
        f'To: {recipient_clean}. '
        f'Subject: {subject}. '
        f'Message: {body}. '
        f'Say yes to send or no to cancel.'
    )
    confirm, _ = listen_text(duration=5)
    confirm = confirm.lower().strip().replace('.', '')
    speak_text(f'[User]: {confirm}')

    if any(word in confirm for word in CONFIRM_WORDS):
        # Store for main.py to pick up after PIN
        _web_login.app.config['pending_email'] = {
            'to':      recipient_clean,
            'subject': subject,
            'body':    body,
        }
        return '__READY_TO_SEND__'

    elif any(word in confirm for word in CANCEL_WORDS):
        return '[System]: Email cancelled. No message was sent.'
    else:
        return '[System]: Response unclear. Email cancelled to be safe.'


# ----------------------
# Direct Send
# (used by main.py after PIN verification, and for AI suggested replies)
# ----------------------

def send_reply_direct(to: str, subject: str, body: str, msg_id: str = '') -> tuple[bool, str]:
    """
    Sends an email directly with pre-composed content.
    msg_id is optional — only needed for reply threading.
    """
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    try:
        if msg_id and subject and not subject.startswith('Re:'):
            subject = f'Re: {subject}'

        msg = MIMEMultipart()
        msg['From']    = EMAIL_USER
        msg['To']      = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        if msg_id:
            msg['In-Reply-To'] = msg_id
            msg['References']  = msg_id

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to, msg.as_string())

        return True, f'[System]: Email sent to {to}.'
    except Exception as e:
        return False, f'[System]: Failed to send. {str(e)}'


# ----------------------
# Voice Reply Flow
# (self-contained — asks PIN internally since it's called directly)
# ----------------------

def reply_email_by_voice(reply_to: str, original_subject: str, original_msg_id: str) -> str:
    try:
        speak_text('[System]: What would you like to say in your reply?')
        body, _ = listen_text(duration=10)
        body = body.strip()
        if not body:
            return '[System]: No reply content heard. Cancelled.'
        speak_text(f'[User]: {body}')

        subject = (
            f'Re: {original_subject}'
            if not original_subject.startswith('Re:')
            else original_subject
        )

        speak_text(
            f'[System]: Ready to send. '
            f'To: {reply_to}. Subject: {subject}. '
            f'Message: {body}. Say yes to send.'
        )
        confirm, _ = listen_text(duration=5)
        confirm = (confirm[0] if isinstance(confirm, tuple) else confirm).lower().strip()
        speak_text(f'[User]: {confirm}')

        if not any(w in confirm for w in CONFIRM_WORDS):
            return '[System]: Reply cancelled.'

        # PIN check
        speak_text('[System]: Please say your 4-digit Gmail PIN to confirm.')
        pin_heard, _ = listen_text(duration=8)
        pin_heard = pin_heard.strip().lower()
        word_to_digit = {
            'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
            'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        }
        pin_digits = pin_heard
        for word, digit in word_to_digit.items():
            pin_digits = pin_digits.replace(word, digit)
        pin_digits = ''.join(c for c in pin_digits if c.isdigit())

        current_email = _web_login.app.config.get('current_email', '')
        if not verify_pin(current_email, 'gmail', pin_digits):
            return '[System]: Incorrect PIN. Reply not sent.'

        ok, msg = send_reply_direct(
            to=reply_to,
            subject=subject,
            body=body,
            msg_id=original_msg_id,
        )
        return msg

    except Exception as e:
        return f'[System]: Failed to send reply. {str(e)}'


__all__ = [
    'compose_email_by_voice', 'send_email',
    'send_reply_direct', 'reply_email_by_voice',
    'spoken_to_email', 'is_valid_email',
]