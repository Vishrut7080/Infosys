"""Mock LLM Agent — allows the app to run without an OpenRouter API key.

When MOCK_SERVICES=True, this agent replaces OpenRouterAgent. It pattern-
matches user input and dispatches tool calls locally, returning canned
LLM-like responses so the full UI loop can be exercised.

Supports:
- Full conversation state for multi-turn flows (email, telegram, tasks)
- Hindi (Devanagari) and English commands
- All registered tools (system, email, telegram, tasks)
"""

import json
import re
from app.tools.registry import registry
from app.core.logging import logger


EMAIL_REGEX = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w+$')


def extract_and_clean_contact(text: str) -> dict:
    """Extract and clean email/phone/contact from user input.
    
    Returns: {
        'type': 'email' | 'phone' | 'contact_number' | 'contact_name',
        'value': str | int,
        'raw': str
    }
    """
    original = text.strip()
    
    # 1. Email detection - contains @
    if '@' in original:
        cleaned = re.sub(r'\s+', '', original)
        cleaned = re.sub(r'@+', '@', cleaned)
        cleaned = re.sub(r'\.+', '.', cleaned)
        if re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', cleaned):
            return {'type': 'email', 'value': cleaned, 'raw': original}
    
    # 2. Phone number - starts with + or digits, min 10 chars
    phone_match = re.search(r'(\+?\d[\d\s\-]{8,})', original)
    if phone_match:
        digits = re.sub(r'[^\d]', '', phone_match.group(1))
        if phone_match.group(1).startswith('+'):
            digits = '+' + digits
        if len(digits) >= 10:
            return {'type': 'phone', 'value': digits, 'raw': original}
    
    # 3. Contact number - "contact 3", "3rd contact", "number 3"
    contact_idx = re.search(r'contact\s*#?(\d+)|#?(\d+)(?:st|nd|rd|th)?\s*contact|number\s*(\d+)', original.lower(), re.IGNORECASE)
    if contact_idx:
        for g in contact_idx.groups():
            if g:
                return {'type': 'contact_number', 'value': int(g) - 1, 'raw': original}
    
    # 4. Default: contact name
    return {'type': 'contact_name', 'value': original.strip(), 'raw': original}


class MockAgent:
    """Drop-in replacement for ``OpenRouterAgent`` that needs no API key."""

    # Conversation states
    STATE_IDLE = "idle"
    STATE_COLLECTING_EMAIL = "collecting_email"
    STATE_VERIFYING_EMAIL_PIN = "verifying_email_pin"
    STATE_COLLECTING_TELEGRAM = "collecting_telegram"
    STATE_VERIFYING_TELEGRAM_PIN = "verifying_telegram_pin"
    STATE_COLLECTING_TASK = "collecting_task"

    def __init__(self, user_email: str):
        self.user_email = user_email
        self.last_tool_results: list[dict] = []
        self.history: list[dict] = []
        self.state = self.STATE_IDLE
        self.pending_data: dict = {}
        self.last_raw_response: str = ""  # For compatibility with real agents
        self.user_lang: str = "en"  # Track user's language (en/hi)

    def chat(self, user_input: str, lang_hint: str = '') -> str:
        """Handle multi-turn conversation based on current state."""
        # Detect language from input
        if self._is_hindi_input(user_input):
            self.user_lang = "hi"
        elif lang_hint == 'hi':
            self.user_lang = "hi"
        
        # If user switches language, handle it
        if lang_hint == 'hi':
            self.user_lang = "hi"
            self.history.append({
                "role": "user",
                "content": "[System note: The user is speaking in Hindi. Respond in Devnagari script.]"
            })

        # If in a conversation flow, handle that first
        if self.state != self.STATE_IDLE:
            return self._handle_conversation_state(user_input)

        # Otherwise, try to match a new command
        result = self.try_chat(user_input)
        if result is not None:
            return result

        # Fallback message
        fallback_en = (
            f"I heard: \"{user_input}\". "
            "I'm running in offline mode, so I can help with emails, Telegram, "
            "navigation, tasks, time, date, jokes, and more. Try asking something specific!"
        )
        fallback_hi = (
            f"मैंने सुना: \"{user_input}\". "
            "मैं ऑफ़लाइन मोड में हूं, इसलिए मैं ईमेल, टेलीग्राम, नेविगेशन, टास्क, "
            "समय, तारीख, जोक्स और बहुत कुछ में मदद कर सकता हूं। कुछ specific पूछें!"
        )
        return fallback_hi if lang_hint == 'hi' else fallback_en

    def _handle_conversation_state(self, user_input: str) -> str:
        """Handle multi-turn conversation based on current state."""
        text = user_input.lower().strip()
        text_hi = user_input.strip()  # Keep original for Hindi

        if self.state == self.STATE_COLLECTING_EMAIL:
            return self._handle_email_collecting(text, text_hi)
        elif self.state == self.STATE_VERIFYING_EMAIL_PIN:
            return self._handle_verifying_email_pin(text, text_hi)
        elif self.state == self.STATE_COLLECTING_TELEGRAM:
            return self._handle_telegram_collecting(text, text_hi)
        elif self.state == self.STATE_VERIFYING_TELEGRAM_PIN:
            return self._handle_verifying_telegram_pin(text, text_hi)
        elif self.state == self.STATE_COLLECTING_TASK:
            return self._handle_task_collecting(text, text_hi)

        # Reset to idle if unknown state
        self.state = self.STATE_IDLE
        self.pending_data = {}
        return "Something went wrong. Let's start over."

    def _handle_email_collecting(self, text: str, text_hi: str) -> str:
        """Handle email collection flow - collects recipient (with cleaning), subject, body then asks for PIN."""
        # Check for cancel
        if self._is_cancel(text, text_hi):
            self._reset_state()
            return self._respond("Email send cancelled.", "ईमेल भेजना रद्द कर दिया गया।")

        # Step 1: Collect recipient with extraction+cleaning
        if "recipient" not in self.pending_data:
            result = extract_and_clean_contact(text)
            
            if result['type'] == 'email':
                self.pending_data['recipient'] = result['value']
                return self._respond(
                    "What is the subject? (or 'skip' if no subject)",
                    "Subject क्या है? (या 'skip' लिखें यदि कोई subject नहीं है)"
                )
            elif result['type'] == 'phone':
                return self._respond(
                    "That looks like a phone number. For email, please provide an email address (e.g., abcd@gmail.com).",
                    "यह phone number है। Email के लिए email address दें (जैसे, abcd@gmail.com)।"
                )
            else:
                return self._respond(
                    "Please provide a valid email address (e.g., abcd@gmail.com).",
                    "कृपया valid email address दें (जैसे, abcd@gmail.com)।"
                )

        # Step 2: Collect subject
        if "subject" not in self.pending_data:
            if text.strip().lower() == "skip" or text.strip().lower() == "छोड़ें":
                self.pending_data["subject"] = "No Subject"
            else:
                self.pending_data["subject"] = text.strip() if text.strip() else "No Subject"
            return self._respond(
                "What is the email body? Write the full message.",
                "ईमेल का body क्या है? पूरा message लिखें।"
            )

        # Step 3: Collect body then ask for PIN
        if "body" not in self.pending_data:
            if text.strip().lower() == "skip" or text.strip().lower() == "छोड़ें":
                self.pending_data["body"] = ""
            else:
                self.pending_data["body"] = text.strip()
            
            # Now ask for PIN
            self.state = self.STATE_VERIFYING_EMAIL_PIN
            recipient = self.pending_data.get("recipient", "")
            subject = self.pending_data.get("subject", "No Subject")
            body_preview = self.pending_data.get("body", "")[:50]
            preview = f"to {recipient}" + (f", subject: {subject}" if subject != "No Subject" else "")
            return self._respond(
                f"Ready to send email {preview}{'...' if body_preview else ''}. Please provide your 4-digit Gmail PIN.",
                f"Ready to send email {preview}{'...' if body_preview else ''}. कृपया अपना 4-digit Gmail PIN दें।"
            )

        return ""

    def _handle_verifying_email_pin(self, text: str, text_hi: str) -> str:
        """Handle PIN verification after email content is collected."""
        # Check for cancel
        if self._is_cancel(text, text_hi):
            self._reset_state()
            return self._respond("Email send cancelled.", "ईमेल भेजना रद्द कर दिया गया।")

        # Extract PIN
        pin_match = re.search(r"\b(\d{4})\b", text)
        if not pin_match:
            return self._respond("Please provide your 4-digit Gmail PIN.", "कृपया अपना 4-digit Gmail PIN दें।")

        # Verify PIN
        result = self._call_tool("verify_gmail_pin", {"pin": pin_match.group(1)})
        if result and ("success" in result.lower() or "verified" in result.lower()):
            # PIN verified, send the email
            send_result = self._call_tool("send_email", {
                "to": self.pending_data.get("recipient", ""),
                "subject": self.pending_data.get("subject", "No Subject"),
                "body": self.pending_data.get("body", "")
            })
            self._reset_state()
            return self._respond(
                send_result if send_result else "Email sent successfully.",
                send_result if send_result else "ईमेल सफलतापूर्वक भेजा गया।"
            )
        
        return self._respond("PIN verification failed. Please try again.", "PIN verification failed. फिर से PIN दें।")

    def _handle_telegram_collecting(self, text: str, text_hi: str) -> str:
        """Handle telegram collection flow - extracts contact, message then PIN."""
        # Check for cancel
        if self._is_cancel(text, text_hi):
            self._reset_state()
            return self._respond("Telegram send cancelled.", "टेलीग्राम भेजना रद्द कर दिया गया।")

        # Step 1: Collect recipient using unified extraction
        if "recipient" not in self.pending_data:
            result = extract_and_clean_contact(text)
            
            if result['type'] == 'email':
                # Treat email as contact name
                self.pending_data['recipient'] = result['value']
                return self._respond(
                    f"What is the message you want to send to {result['value']}?",
                    f"{result['value']} को क्या message भेजना है?"
                )
            elif result['type'] == 'phone':
                # Use phone number as recipient
                self.pending_data['recipient'] = result['value']
                return self._respond(
                    f"What is the message you want to send to {result['value']}?",
                    f"{result['value']} को क्या message भेजना है?"
                )
            elif result['type'] == 'contact_number':
                # Fetch messages and resolve index to sender name
                msgs = self._call_tool("get_telegram_messages", {"count": 10})
                if msgs and isinstance(msgs, str) and "error" not in msgs.lower():
                    lines = [line.strip() for line in msgs.split('\n') if line.strip()]
                    senders = []
                    for line in lines:
                        if line.startswith("From:"):
                            parts = line.split("|")[0]
                            sender = parts.replace("From:", "").strip()
                            if sender and sender not in senders:
                                senders.append(sender)
                    
                    idx = result['value']
                    if 0 <= idx < len(senders):
                        self.pending_data['recipient'] = senders[idx]
                        return self._respond(
                            f"What is the message you want to send to {senders[idx]}?",
                            f"{senders[idx]} को क्या message भेजना है?"
                        )
                    else:
                        return self._respond(
                            f"Contact {idx + 1} not found. You have {len(senders)} contacts.",
                            f"Contact {idx + 1} नहीं मिला। आपके पास {len(senders)} contacts हैं।"
                        )
                return self._respond(
                    "Could not fetch contacts. Please provide a contact name.",
                    "Contacts नहीं ले सका। कृपया contact का नाम दें।"
                )
            else:
                # Contact name
                if result['value']:
                    self.pending_data['recipient'] = result['value']
                    return self._respond(
                        "What is the message you want to send?",
                        "Message क्या है जो भेजना है?"
                    )
                return self._respond(
                    "Please provide the recipient name or number (e.g., 'Alice' or 'contact 3').",
                    "कृपया recipient का नाम या number दें (जैसे, 'Alice' या 'contact 3')।"
                )

        # Step 2: Collect message then ask for PIN
        if "message" not in self.pending_data:
            self.pending_data["message"] = text.strip()
            self.state = self.STATE_VERIFYING_TELEGRAM_PIN
            recipient = self.pending_data.get("recipient", "")
            msg_preview = self.pending_data.get("message", "")[:30]
            return self._respond(
                f"Ready to send message to {recipient}{'...' if msg_preview else ''}. Please provide your 4-digit Telegram PIN.",
                f"Ready to send message to {recipient}{'...' if msg_preview else ''}. कृपया अपना 4-digit Telegram PIN दें।"
            )

        return ""

    def _handle_verifying_telegram_pin(self, text: str, text_hi: str) -> str:
        """Handle PIN verification after telegram message is collected."""
        # Check for cancel
        if self._is_cancel(text, text_hi):
            self._reset_state()
            return self._respond("Telegram send cancelled.", "टेलीग्राम भेजना रद्द कर दिया गया।")

        # Extract PIN
        pin_match = re.search(r"\b(\d{4})\b", text)
        if not pin_match:
            return self._respond("Please provide your 4-digit Telegram PIN.", "कृपया अपना 4-digit Telegram PIN दें।")

        # Verify PIN
        result = self._call_tool("verify_telegram_pin", {"pin": pin_match.group(1)})
        if result and ("success" in result.lower() or "verified" in result.lower()):
            # PIN verified, send the telegram
            send_result = self._call_tool("send_telegram", {
                "contact": self.pending_data.get("recipient", ""),
                "message": self.pending_data.get("message", "")
            })
            self._reset_state()
            return self._respond(
                send_result if send_result else "Telegram message sent successfully.",
                send_result if send_result else "टेलीग्राम संदेश सफलतापूर्वक भेजा गया।"
            )
        
        return self._respond("PIN verification failed. Please try again.", "PIN verification failed. फिर से PIN दें।")

    def _handle_task_collecting(self, text: str, text_hi: str) -> str:
        """Handle task collection flow."""
        # Check for cancel
        if self._is_cancel(text, text_hi):
            self._reset_state()
            return self._respond("Task creation cancelled.", "टास्क जोड़ना रद्द कर दिया गया।")

        # Collect task title
        if "title" not in self.pending_data:
            if text.strip():
                self.pending_data["title"] = text.strip()
                result = self._call_tool("add_task", {"title": self.pending_data.get("title", "")})
                self._reset_state()
                return self._respond(
                    result if result else "Task added successfully.",
                    result if result else "टास्क सफलतापूर्वक जोड़ा गया।"
                )
            return self._respond("Please provide the task title.", "कृपया टास्क का title दें।")
        
        return ""  # Should never reach here

    def _is_cancel(self, text: str, text_hi: str) -> bool:
        """Check if user wants to cancel."""
        cancel_patterns = [
            "cancel", "never mind", "nevermind", "abort", "stop",
            "रद्द", "बंद करो", "बंद", "नहीं", "नहीं चाहिए"
        ]
        return any(p in text for p in cancel_patterns)

    def _reset_state(self):
        """Reset conversation state."""
        self.state = self.STATE_IDLE
        self.pending_data = {}

    def try_chat(self, user_input: str) -> str | None:
        """Pattern-match user_input and return a response, or None if unrecognised."""
        self.last_tool_results = []
        text = user_input.lower().strip()
        text_original = user_input.strip()

        # Check for Hindi input first
        is_hindi = bool(re.search(r'[\u0900-\u097F]', text_original))

        # ── HINDI COMMAND MAPPING ───────────────────────────────
        if is_hindi:
            # Map Hindi to English for processing
            text = self._map_hindi_to_english(text_original.lower())

        # ── NAVIGATION ─────────────────────────────────────────
        nav_result = self._handle_navigation(text)
        if nav_result:
            return nav_result

        # ── EMAIL ─────────────────────────────────────────────
        email_result = self._handle_email_commands(text, text_original)
        if email_result:
            return email_result

        # ── TELEGRAM ──────────────────────────────────────────
        telegram_result = self._handle_telegram_commands(text, text_original)
        if telegram_result:
            return telegram_result

        # ── TASKS ─────────────────────────────────────────────
        task_result = self._handle_task_commands(text, text_original)
        if task_result:
            return task_result

        # ── SYSTEM TOOLS ──────────────────────────────────────
        system_result = self._handle_system_commands(text, text_original, is_hindi)
        if system_result:
            return system_result

        # ── LANGUAGE SWITCH ───────────────────────────────────
        if self._is_language_switch(text, text_original):
            return None  # Let switch_language tool handle it

        # ── CANCEL ────────────────────────────────────────────
        if re.search(r"(cancel|never ?mind|stop|abort|रद्द|बंद करो)", text):
            self._reset_state()
            return "ठीक है, रद्द कर दिया गया।" if is_hindi else "Okay, cancelled."

        # ── GREETING ─────────────────────────────────────────
        if re.search(r"^(hi|hello|hey|good morning|good afternoon|good evening|नमस्ते|हेलो|हाय)", text):
            greeting_en = "Hello! How can I help you today? I can manage your emails, Telegram messages, tasks, or navigate the app."
            greeting_hi = "नमस्ते! आज मैं आपकी कैसे मदद कर सकता हूं? मैं आपके ईमेल, टेलीग्राम मैसेज, टास्क, या ऐप में नेविगेट करने में मदद कर सकता हूं।"
            return greeting_hi if is_hindi else greeting_en

        # ── HELP / CAPABILITIES ────────────────────────────────
        if re.search(r"(help|what can you do|capabilities|मेरी सहायता करो|तुम क्या कर सकते हो|आप क्या कर सकते हैं)", text):
            help_en = (
                "I'm your personal voice assistant! I can: "
                "read your Gmail inbox (overview, important emails, full email body, search) and send emails, "
                "read your Telegram messages and conversations and send Telegram messages, "
                "manage your tasks (add, list, complete, delete), "
                "check the date and time, do calculations, tell jokes, show your profile, "
                "navigate the app by voice, switch language, set reminders, and logout. Just ask!"
            )
            help_hi = (
                "मैं आपका personal voice assistant हूं! मैं कर सकता हूं: "
                "आपके Gmail inbox पढ़ना (overview, important emails, full email body, search) और ईमेल भेजना, "
                "आपके Telegram messages और conversations पढ़ना और Telegram messages भेजना, "
                "आपके tasks manage करना (add, list, complete, delete), "
                "date और time check करना, calculations करना, jokes बताना, आपकी profile दिखाना, "
                "voice से app में navigate करना, language switch करना, reminders set करना, और logout करना। बस पूछें!"
            )
            return help_hi if is_hindi else help_en

        # ── GOODBYE ───────────────────────────────────────────
        if re.search(r"(bye|goodbye|see you|good night|अलविदा|अच्छी रात|जाऊं|जाता हूं)", text):
            return "अलविदा! आपका दिन शुभ हो।" if is_hindi else "Goodbye! Have a great day."

        # ── Unrecognised — caller decides what to do ───────────
        return None

    def _map_hindi_to_english(self, text: str) -> str:
        """Map Hindi keywords to English for processing."""
        hindi_map = {
            # Time/Date
            "क्या समय है": "what time is it",
            "समय": "time",
            "आज की तारीख": "today date",
            "तारीख": "date",
            "आज": "today",
            # Email
            "ईमेल भेजो": "send email",
            "ईमेल": "email",
            "मेल": "email",
            "इनबॉक्स": "inbox",
            "ईमेल पढ़ो": "read email",
            "ईमेल दिखाओ": "show email",
            "important ईमेल": "important email",
            "ज़रूरी ईमेल": "important email",
            "ईमेल सर्च करो": "search email",
            # Telegram
            "टेलीग्राम भेजो": "send telegram",
            "टेलीग्राम": "telegram",
            "टीजी": "telegram",
            "टेलीग्राम पढ़ो": "read telegram",
            "टेलीग्राम दिखाओ": "show telegram",
            # Tasks
            "टास्क जोड़ो": "add task",
            "टास्क बनाओ": "add task",
            "टास्क": "task",
            "टास्क दिखाओ": "list tasks",
            "मेरे टास्क": "my tasks",
            "टास्क पूरा करो": "complete task",
            "टास्क हटाओ": "delete task",
            # Navigation
            "जाओ": "go to",
            "नेविगेट": "navigate",
            "खोलो": "open",
            "दिखाओ": "show",
            # Profile
            "प्रोफ़ाइल": "profile",
            "मेरी जानकारी": "my info",
            "मेरे बारे में": "about me",
            # Language
            "हिंदी": "hindi",
            "अंग्रेज़ी": "english",
            "भाषा बदलो": "switch language",
            # Calculator
            "कैलकुलेट": "calculate",
            "गणना": "calculate",
            "जोड़": "add",
            "घटाओ": "subtract",
            "गुना": "multiply",
            "भाग": "divide",
            # Random
            "रैंडम": "random",
            "रैंडम नंबर": "random number",
            "कोई नंबर": "random number",
            # Joke
            "जोक": "joke",
            "मज़ाक": "joke",
            "हास्य": "joke",
            # Reminder
            "रिमाइंडर": "reminder",
            "याद दिलाओ": "remind me",
            "अलर्ट": "alert",
            # Logout
            "लॉगआउट": "logout",
            "बाहर निकलो": "logout",
            "sign out": "logout",
            # System
            "सिस्टम जानकारी": "system info",
            "कंप्यूटर जानकारी": "system info",
        }

        result = text
        for hi, en in hindi_map.items():
            result = result.replace(hi, en)
        return result

    def _handle_navigation(self, text: str) -> str | None:
        """Handle navigation commands."""
        nav_map = {
            "dashboard": "dashboard",
            "profile": "profile",
            "inbox": "inbox",
            "tasks": "tasks",
            "login": "login",
            "signup": "signup",
            "admin": "admin",
        }
        nav_keywords = ["go to", "open", "navigate", "show", "खोलो", "जाओ", "नेविगेट", "दिखाओ"]

        for keyword, page in nav_map.items():
            if keyword in text and any(w in text for w in nav_keywords):
                result = self._call_tool("navigate", {"page": page})
                if result:
                    return f"Navigating to {keyword}."
                break
        return None

    def _handle_email_commands(self, text: str, original: str) -> str | None:
        """Handle all email-related commands."""
        # Send email - expanded patterns
        if re.search(r"(send|compose|write).*(email|mail|ईमेल)", text) or "mail to" in text:
            self.state = self.STATE_COLLECTING_EMAIL
            self.pending_data = {}
            return self._respond(
                "Who is the recipient? Please provide the email address (e.g., abcd@gmail.com).",
                "किसको भेजना है? कृपया email address दें (जैसे, abcd@gmail.com)।"
            )

        # Read emails / inbox
        if re.search(r"(check|read|get|fetch|पढ़ो|दिखाओ).*(email|inbox|mail|इनबॉक्स|मेल)", text):
            count = self._extract_count(text) or 5
            result = self._call_tool("get_emails", {"count": count})
            suggestion = " आप किसी एक email को पूरा पढ़ने के लिए कह सकते हैं।" if result else ""
            return (result or "मैं आपके emails fetch नहीं कर सका।") + suggestion

        # Email overview
        if re.search(r"(overview|summary|सारांश|खाता).*(inbox|email|mail|इनबॉक्स)", text):
            result = self._call_tool("get_email_overview", {"count": 10})
            return result or "मैं inbox overview नहीं ले सका।"

        # Important emails
        if re.search(r"(important|urgent|priority|ज़रूरी|महत्वपूर्ण).*(email|mail|ईमेल)", text):
            count = self._extract_count(text) or 5
            result = self._call_tool("get_important_emails", {"count": count})
            return result or "कोई important emails नहीं मिले।"

        # Read specific email
        if re.search(r"(read|open|body|full|content|पढ़ो).*(email|mail|ईमेल)", text):
            index = self._extract_index(text) or 1
            result = self._call_tool("get_email_body", {"index": index})
            return result or "मैं उस email को नहीं पढ़ सका।"

        # Search emails
        if re.search(r"(search|सर्च|खोज).*(email|mail|ईमेल)", text):
            query = self._extract_search_query(text)
            result = self._call_tool("search_emails", {"query": query, "count": 5})
            return result or f"'{query}' के लिए कोई email नहीं मिला।"

        # Verify Gmail PIN
        if "verify" in text and "gmail" in text:
            pin_match = re.search(r"\b(\d{4})\b", text)
            if pin_match:
                result = self._call_tool("verify_gmail_pin", {"pin": pin_match.group(1)})
                return result
            return "कृपया अपना 4-digit Gmail PIN दें।"

        return None

    def _handle_telegram_commands(self, text: str, original: str) -> str | None:
        """Handle all Telegram-related commands."""
        # Send telegram - expanded patterns
        if re.search(r"(send|compose|write).*(telegram|टेलीग्राम)", text) or re.search(r"(telegram|टेलीग्राम).*message", text) or re.search(r"message.*(telegram|टेलीग्राम)", text):
            self.state = self.STATE_COLLECTING_TELEGRAM
            self.pending_data = {}
            return self._respond(
                "Who do you want to send to? Provide the contact name or number (e.g., 'Alice' or 'contact 3').",
                "किसको भेजना है? Contact का नाम या number दें (जैसे, 'Alice' या 'contact 3')।"
            )

        # Read telegram messages
        if re.search(r"(check|read|get|fetch|पढ़ो|दिखाओ).*(telegram|tg|टेलीग्राम|टीजी)", text):
            count = self._extract_count(text) or 5
            result = self._call_tool("get_telegram_messages", {"count": count})
            return result or "कोई Telegram messages नहीं मिले।"

        # Conversation with contact
        if re.search(r"(conversation|chat|history|बातचीत|इतिहास).*(with|from|से|के साथ)", text):
            contact = self._extract_contact(text)
            result = self._call_tool("get_telegram_conversation", {"contact": contact, "count": 10})
            return result or f"{contact} के साथ कोई conversation नहीं मिला।"

        # Verify Telegram PIN
        if "verify" in text and "telegram" in text:
            pin_match = re.search(r"\b(\d{4})\b", text)
            if pin_match:
                result = self._call_tool("verify_telegram_pin", {"pin": pin_match.group(1)})
                return result
            return "कृपया अपना 4-digit Telegram PIN दें।"

        return None

    def _handle_task_commands(self, text: str, original: str) -> str | None:
        """Handle all task-related commands."""
        # Add task
        if re.search(r"(add|create|new|जोड़ो|बनाओ).*(task|todo|to.?do|टास्क)", text):
            # Extract task title
            title = self._extract_task_title(text)
            if title:
                result = self._call_tool("add_task", {"title": title})
                return result
            # Need to collect task title
            self.state = self.STATE_COLLECTING_TASK
            self.pending_data = {}
            return "टास्क का title क्या है?"

        # List tasks
        if re.search(r"(list|show|what are|दिखाओ|दिखाएं).*(pending|done|all|लंबित|पूर्ण|सभी)?\s*(tasks?|todos?|to.?dos?|टास्क)", text):
            status = self._extract_task_status(text) or "pending"
            result = self._call_tool("list_tasks", {"status": status})
            return result or "कोई tasks नहीं मिले।"

        # Complete task
        if re.search(r"(complete|finish|done|mark|पूरा|हो गया).*(task|टास्क)\s*#?(\d+)", text):
            id_m = re.search(r"#?(\d+)", text)
            if id_m:
                result = self._call_tool("complete_task", {"task_id": int(id_m.group(1))})
                return result or "Task updated."
            return "कृपया task number बताएं।"

        # Delete task
        if re.search(r"(delete|remove|हटाओ).*(task|टास्क)\s*#?(\d+)", text):
            id_m = re.search(r"#?(\d+)", text)
            if id_m:
                result = self._call_tool("delete_task", {"task_id": int(id_m.group(1))})
                return result or "Task deleted."
            return "कृपया task number बताएं।"

        return None

    def _handle_system_commands(self, text: str, original: str, is_hindi: bool) -> str | None:
        """Handle all system tool commands."""
        # Get time
        if re.search(r"(what time|current time|time is it|क्या समय है|समय क्या है)", text):
            result = self._call_tool("get_time", {})
            return result or "मैं time check नहीं कर सका।"

        # Get date
        if re.search(r"(what date|today.?s date|what is the date|आज की तारीख|तारीख क्या है)", text):
            result = self._call_tool("get_date", {})
            return result or "मैं date check नहीं कर सका।"

        # Get datetime
        if re.search(r"(datetime|date and time|समय और तारीख|पूरा समय)", text):
            result = self._call_tool("get_datetime", {})
            return result or "मैं datetime check नहीं कर सका।"

        # Get system info
        if re.search(r"(system info|system status|सिस्टम जानकारी|कंप्यूटर जानकारी)", text):
            result = self._call_tool("get_system_info", {})
            return result or "मैं system info नहीं ले सका।"

        # Random number
        if re.search(r"(random number|रैंडम|कोई नंबर|random)", text):
            min_val = self._extract_min(text) or 1
            max_val = self._extract_max(text) or 100
            result = self._call_tool("random_number", {"min_val": min_val, "max_val": max_val})
            return f"यह रैंडम नंबर है: {result}" if is_hindi else f"Here's a random number: {result}"

        # Calculate
        if re.search(r"(calculate|कैलकुलेट|गणना|calculate|compute)", text):
            expr = self._extract_expression(text)
            if expr:
                result = self._call_tool("calculate", {"expression": expr})
                return f"Result: {result}"
            return "कृपया एक expression दें।"

        # Tell joke
        if re.search(r"(tell|say|बताओ).*(joke|funny|जोक|मज़ाक)", text):
            result = self._call_tool("tell_joke", {})
            return result

        # User profile
        if re.search(r"(who am i|my profile|user profile|प्रोफ़ाइल|मेरी जानकारी)", text):
            result = self._call_tool("get_user_profile", {})
            return result or "मैं आपकी profile नहीं ले सका।"

        # Set reminder
        if re.search(r"(set reminder|remind me|रिमाइंडर|याद दिलाओ)", text):
            message = self._extract_reminder_message(text)
            minutes = self._extract_minutes(text) or 5
            if message:
                result = self._call_tool("set_reminder", {"message": message, "minutes": minutes})
                return result
            return "रिमाइंडर का message क्या है?"

        # Logout
        if re.search(r"(logout|sign out|लॉगआउट|बाहर निकलो)", text):
            result = self._call_tool("logout", {})
            return result

        return None

    def _is_language_switch(self, text: str, original: str) -> bool:
        """Check if user wants to switch language."""
        return bool(re.search(r"(switch language|हिंदी|अंग्रेज़ी|hindi|english|भाषा बदलो)", text))

    # ── HELPER METHODS FOR EXTRACTING PARAMETERS ───────────────

    def _extract_count(self, text: str) -> int | None:
        """Extract count number from text."""
        match = re.search(r"(\d+)\s*(emails?|messages?|tasks?)?", text)
        return int(match.group(1)) if match else None

    def _extract_index(self, text: str) -> int | None:
        """Extract email/index number from text."""
        match = re.search(r"#?(\d+)", text)
        return int(match.group(1)) if match else None

    def _extract_search_query(self, text: str) -> str:
        """Extract search query from text."""
        patterns = [
            r"search\s+(?:emails?|mails?)\s+(?:for\s+)?(.+)",
            r"find\s+(?:emails?|mails?)\s+(?:with\s+)?(.+)",
            r"search\s+(?:for\s+)?(.+)",
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()
        return "meeting"  # Default

    def _extract_contact(self, text: str) -> str:
        """Extract contact name from text."""
        patterns = [
            r"(?:with|from)\s+([\w][\w\s-]*?)(?:\s*\?)?$",
            r"(?:with|from)\s+(.{1,30})(?:\s|$)",
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip().title()
        return "Mock-Alice"

    def _extract_task_title(self, text: str) -> str | None:
        """Extract task title from text."""
        patterns = [
            r"(?:add|create|new)\s+(?:a\s+)?(?:task|todo|to-do)\s+(?:called\s+)?(.+)",
            r"(?:task|todo|to-do)\s+(?:called\s+)?(.+)",
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip().capitalize()
        return None

    def _extract_task_status(self, text: str) -> str | None:
        """Extract task status from text."""
        if re.search(r"(pending|लंबित)", text):
            return "pending"
        if re.search(r"(done|complete|पूर्ण|हो गया)", text):
            return "done"
        return "all"

    def _extract_min(self, text: str) -> int | None:
        """Extract minimum value."""
        match = re.search(r"(?:between|from|min)\s*(\d+)", text)
        return int(match.group(1)) if match else None

    def _extract_max(self, text: str) -> int | None:
        """Extract maximum value."""
        match = re.search(r"(?:to|and|max)\s*(\d+)", text)
        return int(match.group(1)) if match else None

    def _extract_expression(self, text: str) -> str | None:
        """Extract math expression from text."""
        # Look for numbers and operators
        match = re.search(r"[\d\s\+\-\*\/\(\)]+", text)
        if match:
            expr = match.group(0).strip()
            if re.match(r"^[\d\s\+\-\*\/\(\)]+$", expr):
                return expr
        return None

    def _extract_reminder_message(self, text: str) -> str | None:
        """Extract reminder message from text."""
        patterns = [
            r"(?:remind me to|set reminder for|रिमाइंडर)\s+(.+?)(?:\s+in|\s+after|\s+\d|$)",
            r"(?:to|for)\s+(.+?)(?:\s+in|\s+after|$)",
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1).strip()
        return None

    def _extract_minutes(self, text: str) -> int | None:
        """Extract minutes from text."""
        match = re.search(r"(\d+)\s*(minute|min|मिनट)", text)
        return int(match.group(1)) if match else None

    def _respond(self, en: str, hi: str) -> str:
        """Return response in the user's detected language."""
        return hi if self.user_lang == "hi" else en

    def _is_hindi_input(self, text: str) -> bool:
        """Check if text contains Devanagari (Hindi) characters."""
        return bool(re.search(r'[\u0900-\u097F]', text))

    def _call_tool(self, tool_name: str, args: dict) -> str | None:
        """Call a registered tool and track the result."""
        tool = registry.get_tool(tool_name)
        if not tool:
            logger.warning(f"[MockAgent] Tool '{tool_name}' not found")
            return None
        try:
            result = tool["handler"](self.user_email, **args)
            result_str = str(result)
            self.last_tool_results.append({"tool": tool_name, "result": result_str})
            return result_str
        except Exception as e:
            logger.error(f"[MockAgent] Tool error {tool_name}: {e}")
            return f"Error: {e}"