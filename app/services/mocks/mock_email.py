"""Mock EmailService — simulates send/receive without SMTP/IMAP.

Stores all sent emails and returns canned inbox data so that the agent
tool-call loop can be exercised end-to-end without real Gmail credentials.
"""

from datetime import datetime
from app.core.logging import logger


class MockEmailService:
    """Drop-in replacement for ``app.services.email.EmailService``."""

    # Class-level store shared across instances in the same process
    _sent: list[dict] = []
    _inbox: list[dict] = [
        {
            "sender": "mock-alice@example.com",
            "subject": "Welcome to the Mock Inbox",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "summary": "This is a simulated email used for testing the assistant.",
            "body": "This is a simulated email used for testing the assistant. No real IMAP connection was made.",
        },
        {
            "sender": "mock-bob@example.com",
            "subject": "Meeting Tomorrow",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "summary": "Reminder: team standup at 10 AM.",
            "body": "Reminder: team standup at 10 AM. Please prepare your updates.",
        },
        {
            "sender": "newsletter@techweekly.com",
            "subject": "This Week in AI — Issue #42",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "summary": "Top stories: GPT-5 rumors, new robotics breakthroughs, and more.",
            "body": "Top stories this week include GPT-5 rumors from OpenAI, Boston Dynamics' new warehouse robot, and a deep dive into transformer architectures.",
        },
        {
            "sender": "hr@infosys.com",
            "subject": "Upcoming Holiday Schedule",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "summary": "Please review the holiday calendar for Q3.",
            "body": "Dear team, please review the attached holiday calendar for Q3 2025. Submit any PTO requests by end of week.",
        },
        {
            "sender": "mock-carol@example.com",
            "subject": "Project Deadline Extended",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "summary": "The client approved a 2-week extension for the deliverable.",
            "body": "Good news — the client has approved a 2-week extension. New deadline is July 30th. Let me know if you need anything.",
        },
        {
            "sender": "noreply@github.com",
            "subject": "[GitHub] New pull request in voicemail-ai",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "summary": "mock-dave opened PR #47: Add dark mode toggle.",
            "body": "mock-dave opened a new pull request: Add dark mode toggle to the dashboard settings page.",
        },
        {
            "sender": "billing@cloud-provider.io",
            "subject": "Your Monthly Invoice — June 2025",
            "date": datetime.now().strftime("%d %b %H:%M"),
            "summary": "Total due: $12.34 for compute and storage usage.",
            "body": "Your invoice for June 2025 is ready. Total: $12.34. Breakdown: Compute $8.50, Storage $3.84.",
        },
    ]

    def __init__(self, token_json: str):
        self.token_json = token_json
        self.user_email = "mock-user@example.com" # Default for mock
        try:
             import json
             data = json.loads(token_json)
             # If the token mock contains an email, use it (optional)
             if 'email' in data:
                 self.user_email = data['email']
        except:
            pass
        logger.info(f"[MockEmail] Initialized with token")

    def send_email(self, to: str, subject: str, body: str) -> tuple[bool, str]:
        entry = {
            "from": self.user_email,
            "to": to,
            "subject": subject,
            "body": body,
            "timestamp": datetime.now().isoformat(),
        }
        MockEmailService._sent.append(entry)
        logger.info(f"[MockEmail] Sent email to {to}: {subject}")
        return True, f"[MOCK] Email sent to {to}."

    def get_emails(self, count: int = 5, category: str = "ALL") -> list[dict]:
        logger.info(f"[MockEmail] Fetching {count} emails (category={category})")
        return MockEmailService._inbox[:count]

    # --- Test helpers ---

    @classmethod
    def get_sent_emails(cls) -> list[dict]:
        """Return all emails sent during this process lifetime."""
        return list(cls._sent)

    @classmethod
    def reset(cls):
        """Clear sent emails (call between tests)."""
        cls._sent.clear()
