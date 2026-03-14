from twilio.rest import Client
import os

_client = None
FROM = None

def _get_client():
    global _client, FROM
    if _client is None:
        _client = Client(os.getenv('TWILIO_SID'), os.getenv('TWILIO_TOKEN'))
        FROM = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')
    return _client, FROM

def whatsapp_send_message(to_number: str, message: str) -> tuple[bool, str]:
    client, from_ = _get_client()
    try:
        client.messages.create(
            body=message,
            from_=from_,
            to=f'whatsapp:{to_number}'
        )
        return True, f'WhatsApp message sent to {to_number}.'
    except Exception as e:
        return False, f'WhatsApp send failed: {str(e)}'

def whatsapp_get_messages(limit: int = 5) -> list[dict]:
    client, from_ = _get_client()
    try:
        messages = client.messages.list(to=from_, limit=limit)
        results = []
        for m in messages:
            results.append({
                'name':    m.from_.replace('whatsapp:', ''),
                'message': m.body,
                'date':    m.date_sent.strftime('%a, %d %b %Y %H:%M') if m.date_sent else 'Unknown',
                'source':  'whatsapp'
            })
        return results
    except Exception as e:
        print(f'[WhatsApp] fetch error: {e}')
        return []

__all__ = ['whatsapp_send_message', 'whatsapp_get_messages']