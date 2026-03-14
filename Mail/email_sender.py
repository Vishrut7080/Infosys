# ========================
# EMAIL SENDER — email_sender.py# 
# ========================
# Handles the full voice-driven email composition flow:
#   1. Ask for recipient
#   2. Ask for subject
#   3. Ask for message body
#   4. Confirm before sending
#   5. Send via Gmail SMTP

# Requirements:
#   - Gmail account with App Password (NOT your main password)
#   - Add to .env: EMAIL_USER, EMAIL_PASS (App Password)
#   - Enable 2FA on Gmail, then generate App Password at:
#     https://myaccount.google.com/apppasswords

# SMTP vs IMAP:
#   IMAP  (email_handler.py) = reading emails
#   SMTP  (this file)        = sending emails
# ========================

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from Audio.speech_to_text import listen_text
from Audio.text_to_speech import speak_text


# Words that count as confirmation
CONFIRM_WORDS = ['yes', 'ok', 'yah', 'ya', 'confirm', 'send', 'correct']
# Words that count as cancellation
CANCEL_WORDS  = ['no', 'nah', 'nope', 'cancel', 'stop', "don't"]


# ----------------------
# Core Send Function
# ----------------------

def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS') 
    """
    Sends a plain-text email via Gmail SMTP.

    Args:
        to:      Recipient email address
        subject: Email subject line
        body:    Plain text message body

    Returns:
        (True, success_message) or (False, error_message)
    """
    try:
        # Build the MIME message
        msg = MIMEMultipart()
        msg['From']    = EMAIL_USER
        msg['To']      = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail's SMTP server over SSL (port 465)
        # Use SMTP_SSL instead of SMTP + starttls — simpler and equally secure
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to, msg.as_string())

        print(f"[Email] Sent to {to} | Subject: {subject}")
        return True, f'[System]: Email sent successfully to {to}.'

    except smtplib.SMTPAuthenticationError:
        # Most common error — wrong password or App Password not set up
        return False, '[System]: Authentication failed. Make sure you are using a Gmail App Password, not your main password.'

    except smtplib.SMTPRecipientsRefused:
        return False, f'[System]: Recipient address {to} was refused. Please check the email address.'

    except smtplib.SMTPException as e:
        return False, f'[System]: SMTP error while sending: {str(e)}'

    except Exception as e:
        return False, f'[System]: Unexpected error: {str(e)}'

def spoken_to_email(spoken: str) -> str:
    text = spoken.lower().strip()

    # Replace spoken words with symbols
    replacements = {
        ' at '         : '@',
        ' at'          : '@',      # "johnsmith at gmail"
        'at '          : '@',      # "at gmail" at start
        ' dot '        : '.',
        ' dot'         : '.',
        'dot '         : '.',
        ' underscore ' : '_',
        ' underscore'  : '_',
        ' hyphen '     : '-',
        ' dash '       : '-',
        ' gmail'       : '@gmail', # "john gmail dot com"
        ' yahoo'       : '@yahoo',
        ' outlook'     : '@outlook',
        ' hotmail'     : '@hotmail',
    }

    for spoken_form, symbol in replacements.items():
        text = text.replace(spoken_form, symbol)

    # Handle Whisper's hyphen artifact — "VISH-RUT-AT-Gmail.com" style
    # If no @ found yet, check if a hyphen precedes a known domain
    if '@' not in text:
        import re
        # Match pattern like "something-gmail.com" or "something-yahoo.com"
        text = re.sub(
            r'-?(gmail|yahoo|outlook|hotmail|icloud|protonmail|live)(\.|dot)',
            r'@\1.',
            text
        )

    # Remove any remaining spaces (Whisper sometimes adds spaces mid-address)
    # but preserve the @ and . we just inserted
    parts = text.split('@')
    if len(parts) == 2:
        local  = parts[0].replace(' ', '')
        domain = parts[1].replace(' ', '')
        text   = f"{local}@{domain}"

    return text.strip()

# ----------------------
# Basic Email Validator
# ----------------------

def is_valid_email(address: str) -> bool:
    """
    Simple check that the address contains @ and a dot after it.
    Voice recognition sometimes mishears emails, so we validate before sending.
    """
    return '@' in address and '.' in address.split('@')[-1]


# ----------------------
# Voice Compose Flow
# ----------------------

def compose_email_by_voice() -> str:
    """
    Guides the user through composing an email entirely by voice.

    Flow:
      1. Ask for recipient email
      2. Ask for subject
      3. Ask for message body
      4. Read back a summary and ask for confirmation
      5. Send or cancel based on response

    Returns:
        A status string to be spoken back to the user.
    """

    # ── Step 1: Recipient ──
    speak_text('[System]: Please say the recipient email address.')
    recipient, _ = listen_text(duration=6)
    recipient = recipient.strip()
    speak_text(f'[User]: {recipient}')

    # Voice recognition often adds spaces in emails (e.g. "john @ gmail . com")
    # Remove spaces around @ and . to reconstruct the address
    recipient_clean = spoken_to_email(recipient)

    if not is_valid_email(recipient_clean):
        speak_text(f'[System]: That doesn\'t look like a valid email address: {recipient}. Please try again.')
        # One retry
        speak_text('[System]: Please say the recipient email address again.')
        recipient, _ = listen_text(duration=6)
        recipient = recipient.strip()
        speak_text(f'[User]: {recipient}')
        recipient_clean = recipient.replace(' ', '').lower()

        if not is_valid_email(recipient_clean):
            return '[System]: Could not get a valid email address. Email cancelled.'

    # ── Step 2: Subject ──
    speak_text('[System]: What is the subject of your email?')
    subject, _ = listen_text(duration=6)
    subject = subject.strip()
    speak_text(f'[User]: {subject}')

    if not subject or subject.startswith('[System]'):
        return '[System]: No subject received. Email cancelled.'

    # ── Step 3: Body ──
    speak_text('[System]: Please say your message.')
    body, _ = listen_text(duration=10)
    body = body.strip()   # longer duration for message body
    speak_text(f'[User]: {body}')

    if not body or body.startswith('[System]'):
        return '[System]: No message received. Email cancelled.'

    # ── Step 4: Confirmation ──
    # Read back the full details so the user can verify before sending
    speak_text(
        f'[System]: Ready to send. '
        f'To: {recipient_clean}. '
        f'Subject: {subject}. '
        f'Message: {body}. '
        f'Shall I send this email?'
    )

    confirm, _ = listen_text(duration=5)
    confirm = confirm.lower().strip().replace('.', '')
    speak_text(f'[User]: {confirm}')

    if any(word in confirm for word in CONFIRM_WORDS):
        # ── Step 5: Send ──
        success, message = send_email(recipient_clean, subject, body)
        return message

    elif any(word in confirm for word in CANCEL_WORDS):
        return '[System]: Email cancelled. No message was sent.'

    else:
        # Unclear response — cancel to be safe
        return '[System]: Response unclear. Email cancelled to be safe.'

# ----------------------
# Suggested Reply
# ----------------------

def send_reply_direct(reply_to: str, subject: str, msg_id: str, body: str) -> str:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    """
    Sends a reply directly with a pre-composed body (used for AI suggested replies).
    """
    try:
        subject = f'Re: {subject}' if not subject.startswith('Re:') else subject

        msg                = MIMEMultipart()
        msg['From']        = EMAIL_USER
        msg['To']          = reply_to
        msg['Subject']     = subject
        msg['In-Reply-To'] = msg_id
        msg['References']  = msg_id
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, reply_to, msg.as_string())

        return f'[System]: Reply sent to {reply_to}.'

    except Exception as e:
        return f'[System]: Failed to send. {str(e)}'

def reply_email_by_voice(reply_to: str, original_subject: str, original_msg_id: str) -> str:
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    try:
        speak_text('[System]: What would you like to say in your reply?')
        body, _ = listen_text(duration=10)
        body = body.strip()
        if not body:
            return '[System]: No reply content heard. Cancelled.'
        speak_text(f'[User]: {body}')

        subject = f'Re: {original_subject}' if not original_subject.startswith('Re:') else original_subject
        speak_text(f'[System]: Ready to send. To: {reply_to}. Subject: {subject}. Message: {body}. Shall I send it?')
        confirm = listen_text().lower().strip()
        speak_text(f'[User]: {confirm}')

        affirmation = ['yes', 'ok', 'yah', 'ya', 'send', 'confirm']
        if not any(w in confirm for w in affirmation):
            return '[System]: Reply cancelled.'

        msg                = MIMEMultipart()
        msg['From']        = EMAIL_USER
        msg['To']          = reply_to
        msg['Subject']     = subject
        msg['In-Reply-To'] = original_msg_id
        msg['References']  = original_msg_id
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, reply_to, msg.as_string())

        return f'[System]: Reply sent to {reply_to}.'
    except Exception as e:
        return f'[System]: Failed to send reply. {str(e)}'

__all__ = ['compose_email_by_voice', 'send_email','send_reply_direct','reply_email_by_voice']