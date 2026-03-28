from app.tools.registry import registry
from app.services.auth import auth_service
from app.core.config import settings
from app.database import database
import threading as _threading

if settings.mock_email:
    from app.services.mocks.mock_email import MockEmailService as EmailService
else:
    from app.services.email import EmailService

# Track which users have verified their Gmail PIN this session
_gmail_lock = _threading.Lock()
_gmail_verified: set[str] = set()


def verify_gmail_pin_handler(user_email, pin):
    """Verify the user's 4-digit Gmail PIN before allowing email operations."""
    if not pin or not pin.strip():
        return "Error: Please provide your 4-digit Gmail PIN."
    verified = auth_service.verify_pin(user_email, 'gmail', pin.strip())
    if verified:
        with _gmail_lock:
            _gmail_verified.add(user_email)
        return "Gmail PIN verified successfully. You can now send emails."
    return "Error: Incorrect Gmail PIN. Please try again."


def send_email_handler(user_email, to, subject, body):
    with _gmail_lock:
        is_verified = user_email in _gmail_verified
    if not is_verified:
        return "Error: Gmail PIN not verified. Please ask the user for their 4-digit Gmail PIN and call verify_gmail_pin first."
    creds = auth_service.get_credentials(user_email)
    if not creds or not creds.get('gmail_token'): 
        return "Error: Gmail not connected. Please ask the user to log in with Google to enable email features."
    
    service = EmailService(creds['gmail_token'])
    success, msg = service.send_email(to, subject, body)
    if success:
        database.log_activity(user_email, 'email_sent', f'to={to}')
    return msg

def get_emails_handler(user_email, count=5, category='ALL'):
    """Fetch latest emails, allowing voice-friendly category names (case-insensitive)."""
    creds = auth_service.get_credentials(user_email)
    if not creds or not creds.get('gmail_token'): 
        return "Error: Gmail not connected. Please ask the user to log in with Google to enable email features."

    # Normalize category from voice input
    cat = (category or 'ALL').strip().lower()
    mapping = {
        'all': 'ALL',
        'primary': 'PRIMARY',
        'inbox': 'ALL',
        'promotions': 'PROMOTIONS',
        'promotional': 'PROMOTIONS',
        'promo': 'PROMOTIONS',
        'updates': 'UPDATES',
        'update': 'UPDATES',
        'social': 'SOCIAL',
        'forums': 'FORUMS',
        'forum': 'FORUMS',
    }
    category_norm = mapping.get(cat, None)
    if category_norm is None:
        category_norm = category.upper() if isinstance(category, str) else 'ALL'

    service = EmailService(creds['gmail_token'])
    emails = service.get_emails(count, category_norm)
    if emails and 'error' in emails[0]: return emails[0]['error']
    database.log_activity(user_email, 'email_read', f'fetched={len(emails)}')

    return f"Here are your latest {len(emails)} emails:\n" + "\n".join(
        [f"- From: {e['sender']} | Sub: {e['subject']} | {e['summary']}" for e in emails]
    )


def search_emails_handler(user_email, query, count=5):
    """Search emails by keyword in subject or sender."""
    creds = auth_service.get_credentials(user_email)
    if not creds or not creds.get('gmail_token'): 
        return "Error: Gmail not connected. Please ask the user to log in with Google to enable email features."
    
    service = EmailService(creds['gmail_token'])
    emails = service.get_emails(count * 3, 'ALL')  # fetch more to filter
    if emails and isinstance(emails[0], dict) and 'error' in emails[0]:
        return emails[0]['error']
    
    q = query.lower()
    matches = [e for e in emails if q in e.get('subject', '').lower() or q in e.get('sender', '').lower()]
    if not matches:
        return f"No emails found matching '{query}'."
    
    matches = matches[:count]
    database.log_activity(user_email, 'email_read', f'search={query!r}, found={len(matches)}')
    return f"Found {len(matches)} emails matching '{query}':\n" + "\n".join(
        [f"- From: {e['sender']} | Sub: {e['subject']} | {e['summary']}" for e in matches]
    )


_PRIORITY_KEYWORDS = {'urgent', 'asap', 'deadline', 'action required', 'important', 'critical', 'immediate', 'overdue'}


def get_email_overview_handler(user_email, count=10):
    """Return a high-level overview of the inbox."""
    creds = auth_service.get_credentials(user_email)
    if not creds or not creds.get('gmail_token'): 
        return "Error: Gmail not connected. Please ask the user to log in with Google to enable email features."

    service = EmailService(creds['gmail_token'])
    emails = service.get_emails(count, 'ALL')
    if emails and isinstance(emails[0], dict) and 'error' in emails[0]:
        return emails[0]['error']

    senders = list(dict.fromkeys(e.get('sender', 'Unknown') for e in emails))
    subjects = [f"{i+1}. {e.get('subject', 'No Subject')} — from {e.get('sender', '?')}" for i, e in enumerate(emails)]
    database.log_activity(user_email, 'email_read', f'overview fetched={len(emails)}')
    return (
        f"Inbox overview ({len(emails)} emails):\n"
        f"Senders: {', '.join(senders[:5])}{'…' if len(senders) > 5 else ''}\n"
        "Subjects:\n" + "\n".join(subjects)
    )


def get_important_emails_handler(user_email, count=5):
    """Return emails that appear high-priority based on subject keywords."""
    creds = auth_service.get_credentials(user_email)
    if not creds or not creds.get('gmail_token'): 
        return "Error: Gmail not connected. Please ask the user to log in with Google to enable email features."

    service = EmailService(creds['gmail_token'])
    emails = service.get_emails(max(count * 4, 20), 'ALL')
    if emails and isinstance(emails[0], dict) and 'error' in emails[0]:
        return emails[0]['error']

    important = [
        e for e in emails
        if any(kw in e.get('subject', '').lower() for kw in _PRIORITY_KEYWORDS)
    ][:count]

    if not important:
        return "No high-priority emails found in your recent inbox."

    database.log_activity(user_email, 'email_read', f'important fetched={len(important)}')
    return f"Found {len(important)} important email(s):\n" + "\n".join(
        [f"- From: {e['sender']} | Sub: {e['subject']} | {e.get('summary', '')}" for e in important]
    )


def get_email_body_handler(user_email, subject_keyword='', index=1):
    """Fetch the full body of an email by subject keyword or 1-based index."""
    creds = auth_service.get_credentials(user_email)
    if not creds or not creds.get('gmail_token'): 
        return "Error: Gmail not connected. Please ask the user to log in with Google to enable email features."

    service = EmailService(creds['gmail_token'])
    emails = service.get_emails(20, 'ALL')
    if emails and isinstance(emails[0], dict) and 'error' in emails[0]:
        return emails[0]['error']

    email = None
    if subject_keyword:
        q = subject_keyword.lower()
        email = next((e for e in emails if q in e.get('subject', '').lower()), None)
    if email is None:
        idx = max(1, int(index)) - 1
        email = emails[idx] if idx < len(emails) else None

    if not email:
        return f"Email not found. Try a different keyword or index."

    database.log_activity(user_email, 'email_read', f'body={email.get("subject", "")!r}')
    body = email.get('body') or email.get('summary', 'No content available.')
    return (
        f"Email from {email.get('sender', '?')} on {email.get('date', '?')}\n"
        f"Subject: {email.get('subject', 'No Subject')}\n\n{body}"
    )


registry.register(
    name="verify_gmail_pin",
    description="Verify the user's 4-digit Gmail PIN. Must be called before sending any email.",
    schema={
        "type": "object",
        "properties": {
            "pin": {"type": "string", "description": "The 4-digit Gmail PIN"}
        },
        "required": ["pin"]
    },
    handler=verify_gmail_pin_handler
)

registry.register(
    name="send_email",
    description="Send an email to a recipient using Gmail.",
    schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body content"}
        },
        "required": ["to", "subject", "body"]
    },
    handler=send_email_handler
)

registry.register(
    name="get_emails",
    description="Fetch latest emails from Gmail inbox.",
    schema={
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to fetch (default 5)"},
            "category": {"type": "string", "enum": ["ALL", "PRIMARY", "PROMOTIONS", "UPDATES", "SOCIAL", "FORUMS"], "description": "Email category to filter by"}
        },
        "required": []
    },
    handler=get_emails_handler
)

registry.register(
    name="search_emails",
    description="Search emails by keyword in subject or sender name.",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search keyword to match against subject or sender"},
            "count": {"type": "integer", "description": "Max results to return (default 5)"}
        },
        "required": ["query"]
    },
    handler=search_emails_handler
)

registry.register(
    name="get_email_overview",
    description="Get a high-level overview of the user's inbox: total email count, unique senders, and list of subjects.",
    schema={
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of recent emails to summarize (default 10)"}
        },
        "required": []
    },
    handler=get_email_overview_handler
)

registry.register(
    name="get_important_emails",
    description="Return only high-priority emails based on keywords like 'urgent', 'deadline', 'action required', etc.",
    schema={
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Max number of important emails to return (default 5)"}
        },
        "required": []
    },
    handler=get_important_emails_handler
)

registry.register(
    name="get_email_body",
    description="Fetch the full body text of a specific email by subject keyword or 1-based index position.",
    schema={
        "type": "object",
        "properties": {
            "subject_keyword": {"type": "string", "description": "Keyword to match against email subject (optional)"},
            "index": {"type": "integer", "description": "1-based position in the inbox (default 1 = most recent)"}
        },
        "required": []
    },
    handler=get_email_body_handler
)
