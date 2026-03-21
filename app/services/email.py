import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import cast, List, Dict, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from app.core.logging import logger
from app.core.config import settings

class EmailService:
    def __init__(self, token_json: str):
        self.creds = None
        if token_json:
            try:
                # token_json is stored as a stringified dict from authlib
                token_data = json.loads(token_json)
                self.creds = Credentials(
                    token=token_data.get('access_token'),
                    refresh_token=token_data.get('refresh_token'),
                    token_uri=token_data.get('uri', 'https://oauth2.googleapis.com/token'),
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET,
                    scopes=token_data.get('scope', '').split() if isinstance(token_data.get('scope'), str) else token_data.get('scope')
                )
            except Exception as e:
                logger.error(f"Failed to load credentials: {e}")

    def _get_service(self):
        if not self.creds:
            return None
        if self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                return None
        return build('gmail', 'v1', credentials=self.creds)

    def send_email(self, to: str, subject: str, body: str) -> tuple[bool, str]:
        service = self._get_service()
        if not service:
            return False, "Gmail credentials invalid or expired. Please log in with Google again."

        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            message.attach(MIMEText(body, 'plain'))
            raw_string = base64.urlsafe_b64encode(message.as_bytes()).decode()

            service.users().messages().send(userId='me', body={'raw': raw_string}).execute()
            logger.info(f"Email sent successfully to {to}")
            return True, f'Email sent successfully to {to}.'
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            return False, f'Failed to send. {str(e)}'

    def get_emails(self, count: int = 5, category: str = 'ALL') -> List[Dict]:
        service = self._get_service()
        if not service:
            return [{'error': 'Gmail credentials invalid or expired. Please log in with Google again.'}]

        try:
            query = ''
            if category.upper() == 'PRIMARY': query = 'category:primary'
            elif category.upper() == 'PROMOTIONS': query = 'category:promotions'
            elif category.upper() == 'UPDATES': query = 'category:updates'
            elif category.upper() == 'SOCIAL': query = 'category:social'
            elif category.upper() == 'FORUMS': query = 'category:forums'
            
            results = service.users().messages().list(userId='me', labelIds=['INBOX'], q=query, maxResults=count).execute()
            messages = results.get('messages', [])

            emails = []
            for msg in messages:
                m = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                payload = m.get('payload', {})
                headers = payload.get('headers', [])

                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                
                snippet = m.get('snippet', '')
                body = snippet 
                
                if 'parts' in payload:
                    for part in payload['parts']:
                        if part['mimeType'] == 'text/plain':
                            data = part['body'].get('data')
                            if data:
                                body = base64.urlsafe_b64decode(data).decode()
                            break
                elif 'body' in payload:
                     data = payload['body'].get('data')
                     if data:
                        body = base64.urlsafe_b64decode(data).decode()

                emails.append({
                    'sender': sender,
                    'subject': subject,
                    'date': date_str,
                    'summary': snippet,
                    'body': body
                })

            logger.info(f"Fetched {len(emails)} emails")
            return emails

        except Exception as e:
            logger.error(f"Error fetching mail: {e}")
            return [{'error': f'Error fetching mail: {str(e)}'}]
