import json, datetime
import time as _time
import traceback
import httpx
from app.tools.registry import registry
from app.core.logging import logger
from app.core.config import settings
from app.web import socketio


class LLMUnavailableError(Exception):
    """Raised when the LLM cannot be reached or returns no response."""


_SYSTEM_PROMPT = (
    "You are Infosys Assistant, a highly efficient, pro-active voice assistant. "
    "You have access to tools for managing Gmail, Telegram, and system info. "
    "CRITICAL RULES: "
    "1. If a user asks for a task you can perform with tools, ALWAYS call the appropriate tool. "
    "2. When calling tools, extract as much info as possible (e.g., if user says 'send to John', find 'John's' email or Telegram handle). "
    "3. If a tool requires info you don't have, ask the user concisely. "
    "4. Be BRIEF. You are a voice assistant; your responses should be natural, spoken-style, and under 2 sentences unless requested otherwise. "
    "4a. For short in-process/status messages (examples: 'Thinking...', 'On it', 'Be right back'), match the user's language. "
    "If the user's message is in Hindi or they requested Hindi, respond with natural spoken Hindi equivalents for these brief status messages (for example: 'सोच रहा हूँ…' / 'सोच रही हूँ…', 'ठीक है, कर रहा हूँ…' / 'ठीक है, कर रही हूँ…', 'जल्दी आता/आती हूँ…'). "
    "Otherwise use concise English status phrases. These status messages should remain short and conversational, and should not replace the main assistant reply — use them only while the assistant is performing or verifying an action. "
    "11. LANGUAGE: If the user speaks in Hindi (including Romanized Hindi like 'email bhejo' or 'hindi mode on'), respond ENTIRELY in Devnagari script (e.g., 'आपका ईमेल भेज दिया गया है।'). "
    "Email subject lines, email body content, and Telegram message text are user content — write them entirely in Devnagari when responding to Hindi users as well. "
    "EXCEPTIONS — always keep these in their original form regardless of language: email addresses (e.g. john@example.com), Telegram handles/phone numbers (e.g. @username, +919876543210), URLs, file names, PINs, passwords, numeric values, and any technical identifiers. All other text must be in Devnagari script. "
    "12. The switch_language tool is available to explicitly change the UI language. Prefer responding naturally in Devnagari when the user's intent is Hindi rather than calling the tool unless the user explicitly asks to switch. "
    "5. Never describe the tool call process; just call the tool and relay the result. "
    "6. If the user asks what you can do, introduces itself, or asks for help, say: "
    "You can manage Gmail (read inbox overview, important emails, read full email body, search emails, send emails), "
    "manage Telegram (read recent messages, read a full conversation with a contact, send messages), "
    "manage tasks (add, list, complete, and delete tasks), "
    "answer system questions (date, time, system info, random numbers, calculate), "
    "tell jokes, look up your profile, and navigate the app by voice. "
    "You can navigate to your User Dashboard (Inbox, Profile, Tasks) or the Admin Dashboard (Overview, Users, Activity Logs, API Usage, Error Logs, System Status, My Profile)."
    "7. When sending an email, collect the information in this exact order: recipient email(s), subject, then the body. "
    "ALWAYS validate and normalize every recipient email address before using it: trim whitespace, convert to lowercase, and ensure it matches the format user@domain.tld. "
    "If the user provides a name instead of an email address, ask for the exact email address. If the address looks malformed (e.g. missing '@' or domain), point out the issue and ask the user to confirm the correct address before proceeding. "
    "After you have a valid recipient email, subject, and body, present a concise summary of the composed email and then ask the user to CONFIRM by providing their 4-digit Gmail PIN. "
    "Only call verify_gmail_pin after the user supplies the PIN and confirms the email. Do NOT send the email until verification succeeds. If you don't have the PIN, explicitly ask for it at the end (after showing the summary). "
    "8. Before sending a Telegram message, you MUST call verify_telegram_pin first. Ask the user for their 4-digit Telegram PIN if you don't have it. The pin is for confirmation not authorization, so ask for the pin after the message that is to be sent"
    "9. If the user wants to cancel or stop an action (e.g., 'never mind', 'cancel', 'stop'), acknowledge and do NOT proceed. "
    "10. After reading emails (get_emails, get_important_emails, get_email_body, get_email_overview), scan the results for action items: "
    "meetings, deadlines, follow-ups, approvals, or tasks. If you find any, proactively suggest adding them as tasks "
    "(e.g. 'I noticed a meeting with the design team on Friday — want me to add that as a task?'). "
    "If the user says yes, call add_task immediately without asking for more details unless the title is unclear."
)


class _BaseAgent:
    """Shared OpenAI-compatible chat + tool-call loop."""

    # Subclasses must set these
    _api_url: str = ""
    _extra_headers: dict = {}

    def __init__(self, api_key: str | None, user_email: str, model: str):
        self.api_key = api_key or ""
        self.user_email = user_email
        self.model = model
        self.last_tool_results: list[dict] = []
        self.last_raw_response: dict = {}
        self.history = [{"role": "system", "content": _SYSTEM_PROMPT}]

    def chat(self, user_input: str, lang_hint: str = '') -> str:
        self.lang_hint = lang_hint
        if lang_hint == 'hi':
            self.history.append({
                "role": "user",
                "content": "[System note: The user is speaking in Hindi. Please respond in Devnagari script with all non-technical text in Hindi.]"
            })
        self.history.append({"role": "user", "content": user_input})
        self.last_tool_results = []

        for _ in range(5):
            try:
                response = self._call_llm()
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                return "I'm having trouble connecting to my AI service. Please try again later."
            
            if not response:
                return "I'm having trouble connecting to my AI service. Please try again later."

            msg = response.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            if not tool_calls:
                if content:
                    self.history.append({"role": "assistant", "content": content})
                return content or "I heard you, but I don't know what to say."

            self.history.append(msg)

            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                arguments_str = tool_call["function"]["arguments"]
                tool_call_id = tool_call["id"]

                tool = registry.get_tool(function_name)
                if not tool:
                    logger.error(f"Tool {function_name} not found in registry.")
                    result_str = f"Error: Tool '{function_name}' is not available."
                else:
                    try:
                        args = json.loads(arguments_str)
                        logger.info(f"Calling {function_name} with {args}")
                        result = tool['handler'](self.user_email, **args)
                        result_str = str(result)
                    except Exception as e:
                        logger.error(f"Tool Error: {traceback.format_exc()}")
                        result_str = f"Error executing {function_name}: {str(e)}"

                self.history.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": function_name,
                    "content": result_str,
                })
                self.last_tool_results.append({"tool": function_name, "result": result_str})

        return "I got stuck in a loop trying to help you."

    def _call_llm(self) -> dict | None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        payload = {
            "model": self.model,
            "messages": self.history,
            "tools": registry.get_definitions(),
            "tool_choice": "auto",
        }
        try:
            tool_count = len(registry.get_definitions())
            logger.info(f"{self.__class__.__name__} request: model={self.model} tools={tool_count} user={self.user_email}")

            timeout_val = getattr(settings, 'OPENROUTER_TIMEOUT', None)
            http_timeout = None if timeout_val is None else float(timeout_val)

            with httpx.Client() as client:
                logger.info(f"{self.__class__.__name__} HTTP POST → {self._api_url} http_timeout={http_timeout}")
                t0 = _time.monotonic()
                res = client.post(self._api_url, headers=headers, json=payload, timeout=http_timeout)
                elapsed = _time.monotonic() - t0
                logger.info(f"{self.__class__.__name__} response in {elapsed:.2f}s status={res.status_code}")

            print(f"[DEBUG] {self.__class__.__name__} status={res.status_code} body={res.text[:1000]}", flush=True)

            if res.status_code == 429:
                logger.warning(f"{self.__class__.__name__} rate-limited (429) for user={self.user_email} — will retry in 30s")
                # Notify the user's client that we're rate-limited and will retry
                try:
                    socketio.emit('toast', {'message': '⚠️ Rate limit reached — retrying in 30s', 'type': 'warning'}, room=self.user_email)
                    # Also speak and push a short feed update so the client hears/see the status
                    socketio.emit('tts', {'text': 'Rate limit reached, retrying in 30 seconds', 'lang': 'en'}, room=self.user_email)
                    socketio.emit('feed_update', {'text': 'Rate limit reached — retrying in 30 seconds', 'time': datetime.now().strftime('%H:%M:%S'), 'lang': 'en'}, room=self.user_email)
                except Exception:
                    logger.exception("Failed to emit rate-limit notifications")
                # Wait and retry once
                _time.sleep(30)
                logger.info(f"Retrying LLM request for user={self.user_email} after rate-limit wait")
                try:
                    res = client.post(self._api_url, headers=headers, json=payload, timeout=http_timeout)
                except Exception as e:
                    logger.error(f"{self.__class__.__name__} retry request error: {e}")
                    return None
                if res.status_code == 429:
                    logger.warning(f"{self.__class__.__name__} still rate-limited after retry for user={self.user_email}")
                    return None
            if res.status_code != 200:
                logger.error(f"{self.__class__.__name__} API error {res.status_code}: {res.text}")
                return None

            data = res.json()
            self.last_raw_response = data
            choices = data.get("choices", [])
            if not choices:
                logger.warning(f"{self.__class__.__name__} returned no choices. Full response: {json.dumps(data)[:2000]}")
                return None
            logger.info(f"{self.__class__.__name__} returned {len(choices)} choice(s)")
            return choices[0]

        except Exception as e:
            logger.error(f"{self.__class__.__name__} request error: {e}")
            return None


class OpenRouterAgent(_BaseAgent):
    _api_url = "https://openrouter.ai/api/v1/chat/completions"
    _extra_headers = {
        "HTTP-Referer": "https://github.com/infosys-assistant",
        "X-Title": "Infosys Assistant",
    }

    def __init__(self, api_key: str | None, user_email: str):
        super().__init__(api_key, user_email, model=settings.OPENROUTER_MODEL)


class GroqAgent(_BaseAgent):
    _api_url = "https://api.groq.com/openai/v1/chat/completions"
    _extra_headers = {}

    def __init__(self, api_key: str | None, user_email: str):
        super().__init__(api_key, user_email, model=settings.GROQ_MODEL)
