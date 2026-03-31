from app.tools.registry import registry
from app.core.config import settings
from app.services.auth import auth_service
from app.database import database

if settings.mock_telegram:
    from app.services.mocks.mock_telegram import telegram_send_message, telegram_get_messages, telegram_get_conversation
else:
    from app.services.telegram import telegram_send_message, telegram_get_messages, telegram_get_conversation

def _is_telegram_verified(user_email: str) -> bool:
    """Check if the user has verified their Telegram PIN since their last login."""
    logs = database.get_activity_log(email=user_email, limit=50)
    for log in logs:
        if log['action'] == 'telegram_verified':
            return True
        if log['action'] == 'login':
            return False
    return False

def verify_telegram_pin_handler(user_email, pin):
    """Verify the user's 4-digit Telegram PIN before allowing message sending."""
    if not pin or not pin.strip():
        return "Error: Please provide your 4-digit Telegram PIN."
    verified = auth_service.verify_pin(user_email, 'telegram', pin.strip())
    if verified:
        database.log_activity(user_email, 'telegram_verified', 'success')
        return "Telegram PIN verified successfully. You can now send Telegram messages."
    return "Error: Incorrect Telegram PIN. Please try again."

def send_telegram_handler(user_email, contact, message):
    if not _is_telegram_verified(user_email):
        return "Error: Telegram PIN not verified. Please ask the user for their 4-digit Telegram PIN and call verify_telegram_pin first."
    success, msg = telegram_send_message(contact, message, email=user_email)
    if success:
        database.log_activity(user_email, 'telegram_sent', f'to={contact}')
    return msg

def get_telegram_handler(user_email, count=5):
    msgs = telegram_get_messages(count, email=user_email)
    if not msgs: return "No new Telegram messages."
    
    return f"Here are your latest {len(msgs)} Telegram messages:\n" + "\n".join(
        [f"- From: {m['name']} | Msg: {m['message']}" for m in msgs]
    )

registry.register(
    name="verify_telegram_pin",
    description="Verify the user's 4-digit Telegram PIN. Must be called before sending any Telegram message.",
    schema={
        "type": "object",
        "properties": {
            "pin": {"type": "string", "description": "The 4-digit Telegram PIN"}
        },
        "required": ["pin"]
    },
    handler=verify_telegram_pin_handler
)

registry.register(
    name="send_telegram",
    description="Send a message to a Telegram contact.",
    schema={
        "type": "object",
        "properties": {
            "contact": {"type": "string", "description": "Name of the contact or group"},
            "message": {"type": "string", "description": "Message content"}
        },
        "required": ["contact", "message"]
    },
    handler=send_telegram_handler
)

registry.register(
    name="get_telegram_messages",
    description="Fetch latest messages from Telegram.",
    schema={
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of messages to fetch (default 5)"}
        },
        "required": []
    },
    handler=get_telegram_handler
)


def get_telegram_conversation_handler(user_email: str, contact: str, count: int = 10):
    """Fetch the full message history with a specific Telegram contact for summarising or drafting a reply."""
    if not contact or not contact.strip():
        return "Error: Please specify a contact name."
    messages = telegram_get_conversation(contact.strip(), count, email=user_email)
    if not messages:
        return f"No conversation history found with '{contact}'."
    lines = [f"[{m.get('date', '')}] {m.get('sender', '?')}: {m.get('text', '')}" for m in messages]
    return f"Conversation with {contact} ({len(messages)} messages):\n" + "\n".join(lines)


registry.register(
    name="get_telegram_conversation",
    description="Fetch the message history with a specific Telegram contact. Use this before summarising a chat or drafting a reply.",
    schema={
        "type": "object",
        "properties": {
            "contact": {"type": "string", "description": "Name of the Telegram contact or group"},
            "count":   {"type": "integer", "description": "Number of recent messages to fetch (default 10)"}
        },
        "required": ["contact"]
    },
    handler=get_telegram_conversation_handler
)


def get_telegram_contacts_handler(user_email: str, limit: int = 20):
    """Return a list of recent Telegram contacts/dialogs for the given user."""
    if settings.mock_telegram:
        from app.services.mocks.mock_telegram import MockTelegramState
        if user_email not in MockTelegramState._connected_emails:
            return []
        return [
            {'name': 'Mock-Alice', 'unread': 1, 'last_message': 'Hey there!', 'date': '18 Mar 10:00'},
            {'name': 'Mock-Bob', 'unread': 0, 'last_message': 'See you later', 'date': '18 Mar 09:30'},
        ]
    try:
        from app.services.telegram import _run_async, _clients, _loops, _get_name
        if user_email not in _loops or user_email not in _clients:
            return []
        client = _clients[user_email]

        async def _get_contacts():
            contacts = []
            async for dialog in client.iter_dialogs(limit=limit):
                contacts.append({
                    'name': _get_name(dialog.entity),
                    'unread': dialog.unread_count,
                    'last_message': dialog.message.message[:50] if dialog.message and dialog.message.message else '',
                    'date': dialog.message.date.strftime("%d %b %H:%M") if dialog.message and dialog.message.date else ''
                })
            print (contacts)
            return contacts

        return _run_async(user_email, _get_contacts())
    except Exception:
        return []


def get_telegram_contact_list_handler(user_email: str):
    """Return the user's saved Telegram contacts (address book) when available.

    Falls back to dialog list if direct contact list is not available.
    """
    if settings.mock_telegram:
        from app.services.mocks.mock_telegram import MockTelegramState
        if user_email not in MockTelegramState._connected_emails:
            return []
        # Mock returns a simplified address-book-like list
        return [
            {'name': 'Mock-Alice', 'phone': '+10000000001'},
            {'name': 'Mock-Bob', 'phone': '+10000000002'},
        ]
    try:
        from app.services.telegram import _run_async, _clients, _loops
        if user_email not in _loops or user_email not in _clients:
            return []
        client = _clients[user_email]

        async def _get_address_book():
            # Try to use a dedicated get_contacts if available, otherwise fall back
            if hasattr(client, 'get_contacts'):
                try:
                    contacts = await client.get_contacts()
                    result = []
                    for c in contacts:
                        name = getattr(c, 'first_name', None) or getattr(c, 'username', None) or ''
                        phone = getattr(c, 'phone', '')
                        result.append({'name': name, 'phone': phone})
                    return result
                except Exception:
                    pass

            # Fallback: use dialogs to build a simple contact list
            result = []
            async for dialog in client.iter_dialogs(limit=200):
                name = dialog.name if hasattr(dialog, 'name') else None
                if not name:
                    # try to derive a friendly name
                    e = dialog.entity
                    try:
                        name = e.title if hasattr(e, 'title') else (getattr(e, 'first_name', None) or getattr(e, 'username', None) or '')
                    except Exception:
                        name = ''
                result.append({'name': name, 'id': getattr(dialog.entity, 'id', None)})
            print (result)
            return result

        return _run_async(user_email, _get_address_book())
    except Exception:
        return []

registry.register(
    name="get_telegram_contacts",
    description="Return recent Telegram contacts/dialogs for the authenticated user.",
    schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Maximum number of contacts to return (default 20)"}
        },
        "required": []
    },
    handler=get_telegram_contacts_handler
)

registry.register(
    name="get_telegram_contact_list",
    description="Return the user's saved Telegram contacts (address book) when available.",
    schema={
        "type": "object",
        "properties": {},
        "required": []
    },
    handler=get_telegram_contact_list_handler
)
