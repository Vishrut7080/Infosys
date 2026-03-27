from app.tools.registry import registry
from app.services.auth import auth_service
from app.web import socketio
from datetime import datetime
import random
import platform


def get_time_handler(user_email=None):
    return datetime.now().strftime("%I:%M %p")


def get_date_handler(user_email=None):
    return datetime.now().strftime("%A, %d %B %Y")


def get_datetime_handler(user_email=None):
    return datetime.now().strftime("%A, %d %B %Y at %I:%M %p")


def get_system_info_handler(user_email=None):
    return (
        f"OS: {platform.system()} {platform.release()}, "
        f"Python: {platform.python_version()}, "
        f"Machine: {platform.machine()}"
    )


def random_number_handler(user_email=None, min_val=1, max_val=100):
    return str(random.randint(int(min_val), int(max_val)))


def calculate_handler(user_email=None, expression=""):
    allowed = set("0123456789+-*/(). ")
    if not expression or not all(c in allowed for c in expression):
        return "Error: Only basic arithmetic expressions are allowed (digits, +, -, *, /, parentheses)."
    try:
        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307 — safe: only digits and operators allowed
        return str(result)
    except Exception:
        return "Error: Could not evaluate the expression."


def navigate_handler(user_email=None, page="dashboard"):
    pages = {
        "dashboard": "/dashboard",
        "inbox": "/dashboard#inbox",
        "profile": "/dashboard#profile",
        "tasks": "/dashboard#tasks",
        "admin": "/admin",
        "admin_overview": "/admin#overview",
        "admin_users": "/admin#users",
        "admin_activity": "/admin#activity",
        "admin_api": "/admin#api",
        "admin_errors": "/admin#errors",
        "admin_status": "/admin#status",
        "admin_profile": "/admin#profile",
        "login": "/",
        "signup": "/signup",
        "telegram": "/telegram-auth",
    }
    url = pages.get(page.lower().strip())
    if url:
        return f"NAVIGATE:{url}"
    return f"Unknown page '{page}'. Available pages: {', '.join(pages.keys())}"


def get_user_profile_handler(user_email=None):
    """Return basic profile info for the current user."""
    user = auth_service.get_user_by_email(user_email)
    if not user:
        return "Error: User profile not found."
    return (
        f"Name: {user.get('name', 'Unknown')}, "
        f"Email: {user.get('email', 'Unknown')}, "
        f"Role: {user.get('role', 'user')}"
    )


def switch_language_handler(user_email=None, language="hi"):
    lang = language.lower().strip()
    if lang not in ("hi", "en"):
        return f"Unknown language '{language}'. Use 'hi' for Hindi or 'en' for English."
    socketio.emit("lang_update", {"lang": lang}, room=user_email)
    return f"Language switched to {'Hindi' if lang == 'hi' else 'English'}."


def set_reminder_handler(user_email=None, message="", minutes=5):
    """Acknowledge a reminder request (actual scheduling is simulated)."""
    if not message:
        return "Error: Please provide a reminder message."
    return f"Reminder set: '{message}' in {int(minutes)} minutes. (Note: reminders are acknowledged but not yet persisted across sessions.)"


def tell_joke_handler(user_email=None):
    """Return a random clean joke."""
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs.",
        "I told my computer I needed a break. Now it won't stop sending me Kit-Kat ads.",
        "Why was the JavaScript developer sad? Because he didn't Node how to Express himself.",
        "What's a computer's favorite snack? Microchips.",
        "Why did the developer go broke? Because he used up all his cache.",
        "How do trees access the internet? They log in.",
        "Why do Java developers wear glasses? Because they can't C#.",
        "What did the router say to the doctor? It hurts when IP.",
    ]
    return random.choice(jokes)


# --- Register all system tools ---

registry.register(
    name="get_time",
    description="Get the current time.",
    schema={"type": "object", "properties": {}},
    handler=get_time_handler,
)

registry.register(
    name="get_date",
    description="Get the current date.",
    schema={"type": "object", "properties": {}},
    handler=get_date_handler,
)

registry.register(
    name="get_datetime",
    description="Get the current date and time together.",
    schema={"type": "object", "properties": {}},
    handler=get_datetime_handler,
)

registry.register(
    name="get_system_info",
    description="Get basic system information (OS, Python version, machine).",
    schema={"type": "object", "properties": {}},
    handler=get_system_info_handler,
)

registry.register(
    name="random_number",
    description="Generate a random integer between min_val and max_val (inclusive).",
    schema={
        "type": "object",
        "properties": {
            "min_val": {"type": "integer", "description": "Minimum value (default 1)"},
            "max_val": {"type": "integer", "description": "Maximum value (default 100)"},
        },
    },
    handler=random_number_handler,
)

registry.register(
    name="calculate",
    description="Evaluate a basic arithmetic expression (e.g. '2 + 3 * 4'). Supports +, -, *, /, parentheses.",
    schema={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The arithmetic expression to evaluate",
            }
        },
        "required": ["expression"],
    },
    handler=calculate_handler,
)

registry.register(
    name="navigate",
    description="Navigate the user to a page. User Dashboard targets: (dashboard, inbox, profile, tasks). Admin Dashboard targets: (admin, admin_overview, admin_users, admin_activity, admin_api, admin_errors, admin_status, admin_profile). Others: (login, signup, telegram).",
    schema={
        "type": "object",
        "properties": {
            "page": {
                "type": "string",
                "description": "Name of the page to navigate to",
            }
        },
        "required": ["page"],
    },
    handler=navigate_handler,
)

registry.register(
    name="get_user_profile",
    description="Get the current user's profile information (name, email, role).",
    schema={"type": "object", "properties": {}},
    handler=get_user_profile_handler,
)

registry.register(
    name="set_reminder",
    description="Set a reminder for the user. The reminder is acknowledged and spoken back.",
    schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "The reminder message"},
            "minutes": {"type": "integer", "description": "Minutes from now (default 5)"},
        },
        "required": ["message"],
    },
    handler=set_reminder_handler,
)

registry.register(
    name="switch_language",
    description="Switch the frontend UI language and TTS voice to Hindi (hi) or English (en). Use this when the user asks to switch language, enable Hindi mode, or similar.",
    schema={
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "Target language: 'hi' for Hindi (Devnagari script) or 'en' for English.",
                "enum": ["hi", "en"]
            }
        },
        "required": ["language"],
    },
    handler=switch_language_handler,
)
