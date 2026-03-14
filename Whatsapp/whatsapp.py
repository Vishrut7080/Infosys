from twilio.rest import Client
import os
from dotenv import load_dotenv
load_dotenv()

_client = Client(os.getenv('TWILIO_SID'), os.getenv('TWILIO_TOKEN'))
FROM = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')

def whatsapp_send_message(to_number: str, message: str) -> tuple[bool, str]:
    """
    to_number: phone number with country code, e.g. '+919876543210'
    """
    try:
        msg = _client.messages.create(
            body=message,
            from_=FROM,
            to=f'whatsapp:{to_number}'
        )
        return True, f'WhatsApp message sent to {to_number}.'
    except Exception as e:
        return False, f'WhatsApp send failed: {str(e)}'

def whatsapp_get_messages(limit: int = 5) -> list[dict]:
    """Fetch recent inbound WhatsApp messages from Twilio logs."""
    try:
        messages = _client.messages.list(to=FROM, limit=limit)
        results = []
        for m in messages:
            results.append({
                'name': m.from_.replace('whatsapp:', ''),
                'message': m.body,
                'date': m.date_sent.strftime('%a, %d %b %Y %H:%M') if m.date_sent else 'Unknown',
                'source': 'whatsapp'
            })
        return results
    except Exception as e:
        print(f'[WhatsApp] fetch error: {e}')
        return []

__all__ = ['whatsapp_send_message', 'whatsapp_get_messages']