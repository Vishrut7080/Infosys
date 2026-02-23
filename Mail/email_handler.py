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
LANGUAGE       = "english"          # Language for sumy tokenizer and stop words
SENTENCE_COUNT = 2                  # Number of sentences to keep in the summary
FETCH_COUNT    = 5                  # How many of the latest emails to fetch

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
    """
    Extracts the plain-text body from an email message object.

    Multipart emails contain multiple parts (plain text, HTML, attachments).
    We prefer plain text. If only HTML is available, we strip the tags.
    Attachments are skipped entirely.
    """
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type        = part.get_content_type()
            content_disposition = str(part.get_content_disposition())

            # Skip attachments
            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                # Plain text found — decode and use immediately
                body = part.get_payload(decode=True).decode(errors='replace')
                break  # Prefer plain text over HTML, so stop here

            elif content_type == "text/html" and not body:
                # Fallback: strip HTML tags if no plain text part exists
                raw_html = part.get_payload(decode=True).decode(errors='replace')
                body = strip_html(raw_html)
    else:
        # Single-part email
        raw = msg.get_payload(decode=True)
        if raw:
            body = raw.decode(errors='replace')

    return body.strip()

# ----------------------
# Helper: Strip HTML tags from a string
# ----------------------

def strip_html(raw_html: str) -> str:
    """
    Removes HTML tags and decodes HTML entities to get clean plain text.
    Used as a fallback when an email only has an HTML part.
    """
    # Unescape HTML entities first (e.g. &amp; → &, &nbsp; → space)
    text = html.unescape(raw_html)
    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ----------------------
# Helper: Summarize text using Sumy LSA
# ----------------------

def summarize_body(body: str, sentence_count: int = SENTENCE_COUNT) -> str:
    """
    Uses Sumy's LSA summarizer to extract the most important sentences
    from the email body.

    LSA (Latent Semantic Analysis) works by decomposing the term-sentence
    matrix using SVD, then ranking sentences by how much they contribute
    to the main topics. It handles longer emails better than greedy methods.

    Args:
        body:           The raw plain-text email body.
        sentence_count: Number of sentences to include in the summary.

    Returns:
        A summarized string, or the original body if it's too short to summarize.
    """
    # Clean up excessive whitespace and newlines before summarizing
    cleaned = re.sub(r'\n+', ' ', body).strip()

    # If the body is very short (e.g. a one-liner), just return it as-is
    if len(cleaned.split()) < 30:
        return cleaned if cleaned else "No body content."

    try:
        parser     = PlaintextParser.from_string(cleaned, Tokenizer(LANGUAGE))
        stemmer    = Stemmer(LANGUAGE)
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words(LANGUAGE)

        # Extract the top N sentences
        summary_sentences = summarizer(parser.document, sentence_count)
        summary = ' '.join(str(s) for s in summary_sentences)
        return summary if summary else cleaned[:300]  # fallback to first 300 chars

    except Exception as e:
        # If sumy fails for any reason, return a truncated version of the body
        return cleaned[:300] + "..." if len(cleaned) > 300 else cleaned


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
def get_top_senders():
    # webbrowser.open("https://mail.google.com/mail/u/0/#inbox") - can open the inbox
    try:
        # commecting to an email account
        mail=imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(EMAIL_USER,EMAIL_PASS)
        # selecting mailbox
        mail.select('inbox')

        # searching email
        result,data=mail.search(None,'All')
        mail_ids=data[0].split()

        # Check if inbox is empty
        if not mail_ids:
            mail.logout()
            return['Inbox is empty']
        
        latest_ids=mail_ids[-5:]
        senders=[]

        for mail_id in reversed(latest_ids):
            # fetching email content
            result,msg_data=mail.fetch(mail_id, "(RFC822)")
            raw_email=msg_data[0][1]
            msg=email.message_from_bytes(raw_email)
            senders.append(msg['From'])
        mail.logout()
        return senders
    
    except imaplib.IMAP4.error as e:
        return [f'[System]: IMAP Error: {str(e)}. Please check your email credentials.']

    except Exception as e:
        return [f'Error: {str(e)}']
    
__all__=['open_gmail_compose', 'get_top_senders']