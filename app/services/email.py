import smtplib
import imaplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate_to_datetime

from app.core.logging import logger
from app.core.errors import EmailError

class EmailService:
    def __init__(self, user_email: str, app_pass: str):
        self.user_email = user_email
        self.app_pass = app_pass

    def send_email(self, to: str, subject: str, body: str) -> tuple[bool, str]:
        if not self.user_email or not self.app_pass:
            return False, 'Gmail credentials not configured.'

        try:
            msg = MIMEMultipart()
            msg['From'] = self.user_email
            msg['To'] = to
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.user_email, self.app_pass)
                server.sendmail(self.user_email, to, msg.as_string())

            logger.info(f"Email sent successfully to {to}")
            return True, f'Email sent successfully to {to}.'

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP Authentication failed.")
            return False, 'Authentication failed. Check your Gmail App Password.'
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            return False, f'Failed to send. {str(e)}'

    def get_emails(self, count: int = 5, category: str = 'ALL') -> list[dict]:
        if not self.user_email or not self.app_pass:
            return [{'error': 'Gmail credentials not configured.'}]

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(self.user_email, self.app_pass)
            logger.info(f"IMAP login successful for {self.user_email}")
            mail.select("inbox")
            # ... (rest of implementation)

            search_query = 'ALL'
            if category.upper() == 'PRIMARY':
                search_query = 'X-GM-RAW "category:primary"'
            elif category.upper() == 'PROMOTIONS':
                search_query = 'X-GM-RAW "category:promotions"'
            elif category.upper() == 'UPDATES':
                search_query = 'X-GM-RAW "category:updates"'
            elif category.upper() == 'SOCIAL':
                search_query = 'X-GM-RAW "category:social"'
            elif category.upper() == 'FORUMS':
                search_query = 'X-GM-RAW "category:forums"'

            status, messages = mail.search(None, search_query)
            if status != 'OK':
                return [{'error': f'Search failed with status {status}'}]

            uids = messages[0].split()
            if not uids:
                logger.info(f"No emails found for {self.user_email}")
                return []

            top_uids = uids[-count:][::-1]
            emails = []

            for uid in top_uids:
                res, msg_data = mail.fetch(uid, '(RFC822)')
                if res != 'OK':
                    continue

                raw_email: bytes = msg_data[0][1] # type: ignore
                msg = email.message_from_bytes(raw_email)

                # Safely decode headers
                subject_header = msg.get("Subject")
                subject = "No Subject"
                if subject_header:
                    val, encoding = decode_header(subject_header)[0]
                    subject = val.decode(encoding or "utf-8") if isinstance(val, bytes) else val

                from_header = msg.get("From")
                sender = "Unknown"
                if from_header:
                    val, encoding = decode_header(from_header)[0]
                    sender = val.decode(encoding or "utf-8") if isinstance(val, bytes) else val

                date_str = msg.get("Date")
                dt = parsedate_to_datetime(date_str) if date_str else None
                fmt_date = dt.strftime("%d %b %H:%M") if dt else "Unknown"

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if isinstance(payload, bytes):
                                body = payload.decode(errors='ignore')
                            break
                else:
                    payload = msg.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        body = payload.decode(errors='ignore')

                summary = body.strip()[:150].replace('\n', ' ') + "..."
                emails.append({
                    'sender': sender,
                    'subject': subject,
                    'date': fmt_date,
                    'summary': summary,
                    'body': body
                })

            mail.logout()
            logger.info(f"Fetched {len(emails)} emails for {self.user_email}")
            return emails

        except Exception as e:
            logger.error(f"Error fetching mail for {self.user_email}: {e}")
            return [{'error': f'Error fetching mail: {str(e)}'}]
