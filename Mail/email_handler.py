import os, webbrowser, imaplib, email, re, html
from dotenv import load_dotenv
from email.header import decode_header
from email.utils import parsedate_to_datetime

# ----------------------
# SUNNY IMPORTS- lightweight
# ----------------------
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words

load_dotenv()

# loads the passowrd and email address
EMAIL_USER=os.getenv('EMAIL_USER')
EMAIL_PASS=os.getenv('EMAIL_PASS')

# ========================
# CONFIGURATION
# ========================
SENTENCE_COUNT = 2                  # Number of sentences to keep in the summary
FETCH_COUNT    = 3                  # How many of the latest emails to fetch

# # =================================================
# TEXT SUMMARIZATION
# # =================================================
try:
    from langdetect import detect as _detect_lang
    _langdetect_available = True
except ImportError:
    _langdetect_available = False

def summarize_body(body: str, sentence_count: int = SENTENCE_COUNT) -> str:
    body = body[:2000]
    cleaned = re.sub(r'\n+', ' ', body).strip()
    if len(cleaned.split()) < 30:
        return cleaned if cleaned else "No body content."

    # ★ Detect language
    sumy_lang = 'english'
    if _langdetect_available:
        try:
            detected = _detect_lang(cleaned)
            if detected == 'hi':
                sumy_lang = 'hindi'
        except Exception:
            pass

    try:
        parser     = PlaintextParser.from_string(cleaned, Tokenizer(sumy_lang))
        stemmer    = Stemmer(sumy_lang)
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words(sumy_lang)
        summary_sentences = summarizer(parser.document, sentence_count)
        summary = ' '.join(str(s) for s in summary_sentences)
        return summary if summary else cleaned[:300]
    except Exception:
        return cleaned[:300] + '...' if len(cleaned) > 300 else cleaned

# to open a webpage to compose a new mail
def open_gmail_compose():
    # opens webpage
    webbrowser.open('https://mail.google.com/mail/u/0/?fs=1&tf=cm')
    return '[System]: Opening page to send mail..'


def decode_mime_header(raw_header: str) -> str:
    if not raw_header:
        return "Unknown"

    decoded_parts = decode_header(raw_header)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ' '.join(result).strip()

# ----------------------
# Helper: Extract plain text body from email
# ----------------------

def extract_body(msg) -> str:
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type        = part.get_content_type()
            content_disposition = str(part.get_content_disposition())

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                body = part.get_payload(decode=True).decode(errors='replace')
                break
            elif content_type == "text/html" and not body:
                raw_html = part.get_payload(decode=True).decode(errors='replace')
                body = strip_html(raw_html)
    else:
        raw = msg.get_payload(decode=True)
        if raw:
            content_type = msg.get_content_type()
            if content_type == "text/html":
                body = strip_html(raw.decode(errors='replace'))
            else:
                body = raw.decode(errors='replace')

    return body.strip()

# ----------------------
# Helper: Strip HTML tags from a string
# ----------------------

def strip_html(raw_html: str) -> str:
    text = html.unescape(raw_html)
    # Remove style and script blocks including their content
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL)
    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Remove leftover CSS-like junk (anything inside curly braces)
    text = re.sub(r'\{[^}]+\}', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ----------------------
# Helper: Extract important details from email body
# ----------------------

def extract_important_details(msg, body: str) -> dict:
    """
    Extracts structured 'important details' from the email:
      - Attachments: names of any attached files
      - Links: any URLs found in the body
      - CC / BCC recipients if present
    """
    details = {}

    # --- Attachments ---
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get_content_disposition())
            if "attachment" in disposition:
                filename = decode_mime_header(part.get_filename() or "unnamed")
                attachments.append(filename)
    details['attachments'] = attachments if attachments else None

    # --- URLs found in the body ---
    urls = re.findall(r'https?://[^\s<>"\']+', body)
    # Deduplicate while preserving order, limit to 5 to avoid noise
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
        if len(unique_urls) == 5:
            break
    details['links'] = unique_urls if unique_urls else None

    # --- CC recipients ---
    cc = msg.get('Cc')
    details['cc'] = decode_mime_header(cc) if cc else None

    return details


# ----------------------
# Main Function: Fetch and summarize latest emails
# ----------------------

# open webpage and return the name of the top mail(sender)
def get_top_senders(count: int = FETCH_COUNT, category: str='ALL'):
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('inbox')
        
        # status, folders = mail.list()
        # print('[DEBUG] Gmail folders:')
        # for f in folders:
        #     print(' ', f.decode())

        mail.select('"[Gmail]/All Mail"')

        if category == 'PRIMARY':
            result, data = mail.search(None, 'X-GM-LABELS primary')
            print(f'[DEBUG] PRIMARY → result={result}, count={len(data[0].split()) if data[0] else 0}')
            if result != 'OK' or not data[0].split():
                result, data = mail.search(None, 'ALL')
                print('[DEBUG] PRIMARY fell back to ALL')
        
        elif category == 'UPDATES':
            result, data = mail.search(None, 'X-GM-LABELS updates')
            print(f'[DEBUG] UPDATES → result={result}, count={len(data[0].split()) if data[0] else 0}')
            if result != 'OK' or not data[0].split():
                result, data = mail.search(None, 'ALL')
                print('[DEBUG] UPDATES fell back to ALL')
        
        elif category == 'PROMOTIONS':
            result, data = mail.search(None, 'X-GM-LABELS promotions')
            print(f'[DEBUG] PROMOTIONS → result={result}, count={len(data[0].split()) if data[0] else 0}')
            if result != 'OK' or not data[0].split():
                result, data = mail.search(None, 'ALL')
                print('[DEBUG] PROMOTIONS fell back to ALL')
        
        else:
            result, data = mail.search(None, 'ALL')
        
        mail_ids = data[0].split()

        if not mail_ids:
            mail.logout()
            return [{'error': 'Inbox is empty'}]

        latest_ids = mail_ids[-count:]
        emails = []

        for mail_id in reversed(latest_ids):
            result, msg_data = mail.fetch(mail_id, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            sender  = decode_mime_header(msg.get('From', 'Unknown'))
            subject = decode_mime_header(msg.get('Subject', 'No Subject'))

            raw_date = msg.get('Date')
            try:
                date_str = parsedate_to_datetime(raw_date).strftime("%a, %d %b %Y %H:%M")
            except Exception:
                date_str = raw_date or "Unknown date"

            body    = extract_body(msg)
            summary = summarize_body(body)
            details = extract_important_details(msg, body)

            emails.append({
                'sender':  sender,
                'subject': subject,
                'date':    date_str,
                'summary': summary,
                'details': details,
                'msg_id':  msg.get('Message-ID', '')
            })

        mail.logout()
        return emails

    except imaplib.IMAP4.error as e:
        return [{'error': f'[System]: IMAP Error: {str(e)}'}]
    except Exception as e:
        return [{'error': f'[System]: Error: {str(e)}'}]

__all__=['open_gmail_compose', 'get_top_senders']