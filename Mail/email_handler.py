import os, imaplib, email, re, html
from email.header import decode_header
from email.utils import parsedate_to_datetime
import Mail.web_login as _web_login
from Audio.text_to_speech import speak_text as _tts_orig

def speak_text(text: str, lang: str = 'en'):
    _web_login.push_to_feed(text)
    _tts_orig(text, lang=lang)

def open_gmail_compose():
    _web_login.push_action('open_url', {'url': 'https://mail.google.com/mail/u/0/?fs=1&tf=cm'})
    return '[System]: Opening page to send mail..'

def get_top_senders(count=5, category='ALL', user_email=None, app_pass=None):
    # Use provided creds or fallback to environment
    EMAIL_USER = user_email or os.getenv('EMAIL_USER')
    EMAIL_PASS = app_pass or os.getenv('EMAIL_PASS')

    if not EMAIL_USER or not EMAIL_PASS:
        return [{'error': '[System]: Gmail credentials not configured.'}]

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        search_query = 'ALL'
        if category == 'PRIMARY': search_query = 'X-GM-RAW "category:primary"'
        elif category == 'PROMOTIONS': search_query = 'X-GM-RAW "category:promotions"'
        elif category == 'UPDATES': search_query = 'X-GM-RAW "category:updates"'

        status, messages = mail.uid('search', None, search_query)
        if status != 'OK': return [{'error': f'[System]: Search failed with status {status}'}]

        uids = messages[0].split()
        if not uids: return []

        top_uids = uids[-count:][::-1]
        emails = []

        for uid in top_uids:
            res, msg_data = mail.uid('fetch', uid, '(RFC822)')
            if res != 'OK': continue
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes): subject = subject.decode(encoding or "utf-8")

            sender, encoding = decode_header(msg.get("From"))[0]
            if isinstance(sender, bytes): sender = sender.decode(encoding or "utf-8")

            date_str = msg.get("Date")
            dt = parsedate_to_datetime(date_str) if date_str else None
            fmt_date = dt.strftime("%d %b %H:%M") if dt else "Unknown"

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors='ignore')
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors='ignore')

            summary = body.strip()[:150].replace('\n', ' ') + "..."
            emails.append({
                'uid': uid.decode(),
                'sender': sender,
                'subject': subject,
                'date': fmt_date,
                'summary': summary,
                'msg_id': msg.get('Message-ID', ''),
                'details': {'attachments': []}
            })

        mail.logout()
        return emails

    except Exception as e:
        return [{'error': f'[System]: Error fetching mail: {str(e)}'}]

__all__=['open_gmail_compose', 'get_top_senders']
