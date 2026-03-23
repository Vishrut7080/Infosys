"""Tests for individual tools and the tool registry."""

import pytest
from datetime import datetime


# ---------------------------------------------------------------------------
#  Registry tests
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_register_and_retrieve(self, fresh_registry):
        fresh_registry.register(
            name="dummy",
            description="A dummy tool",
            schema={"type": "object", "properties": {}},
            handler=lambda user_email: "ok",
        )
        tool = fresh_registry.get_tool("dummy")
        assert tool is not None
        assert tool["name"] == "dummy"
        assert tool["handler"](None) == "ok"

    def test_get_unknown_tool(self, fresh_registry):
        assert fresh_registry.get_tool("nope") is None

    def test_get_definitions_format(self, fresh_registry):
        fresh_registry.register(
            name="t1",
            description="desc",
            schema={"type": "object", "properties": {"x": {"type": "string"}}},
            handler=lambda user_email: None,
        )
        defs = fresh_registry.get_definitions()
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] == "t1"
        assert "x" in defs[0]["function"]["parameters"]["properties"]

    def test_all_real_tools_registered(self, populated_registry):
        """Ensure that importing the tools package registers at least the system tools."""
        names = {t["name"] for t in populated_registry.get_all_tools()}
        assert "get_time" in names
        assert "get_date" in names
        assert "get_datetime" in names
        assert "calculate" in names
        assert "navigate" in names
        assert "get_user_profile" in names
        assert "set_reminder" in names
        assert "tell_joke" in names
        assert "verify_gmail_pin" in names
        assert "search_emails" in names
        assert "send_email" in names
        assert "get_emails" in names
        # New email tools
        assert "get_email_overview" in names
        assert "get_important_emails" in names
        assert "get_email_body" in names
        assert "send_telegram" in names
        assert "verify_telegram_pin" in names
        assert "get_telegram_conversation" in names
        # Task tools
        assert "add_task" in names
        assert "list_tasks" in names
        assert "complete_task" in names
        assert "delete_task" in names


# ---------------------------------------------------------------------------
#  System tools — unit tests (no external deps)
# ---------------------------------------------------------------------------

class TestSystemTools:
    def test_get_time(self):
        from app.tools.system_tools import get_time_handler
        result = get_time_handler()
        # Should be a time string like "03:30 PM"
        parsed = datetime.strptime(result, "%I:%M %p")
        assert parsed is not None

    def test_get_date(self):
        from app.tools.system_tools import get_date_handler
        result = get_date_handler()
        parsed = datetime.strptime(result, "%A, %d %B %Y")
        assert parsed is not None

    def test_get_datetime(self):
        from app.tools.system_tools import get_datetime_handler
        result = get_datetime_handler()
        assert "at" in result

    def test_get_system_info(self):
        from app.tools.system_tools import get_system_info_handler
        result = get_system_info_handler()
        assert "OS:" in result
        assert "Python:" in result

    def test_random_number_default_range(self):
        from app.tools.system_tools import random_number_handler
        for _ in range(20):
            val = int(random_number_handler())
            assert 1 <= val <= 100

    def test_random_number_custom_range(self):
        from app.tools.system_tools import random_number_handler
        for _ in range(20):
            val = int(random_number_handler(min_val=50, max_val=60))
            assert 50 <= val <= 60

    def test_calculate_basic(self):
        from app.tools.system_tools import calculate_handler
        assert calculate_handler(expression="2 + 3") == "5"
        assert calculate_handler(expression="10 / 4") == "2.5"
        assert calculate_handler(expression="(2 + 3) * 4") == "20"

    def test_calculate_rejects_dangerous_input(self):
        from app.tools.system_tools import calculate_handler
        result = calculate_handler(expression="__import__('os').system('echo hacked')")
        assert "error" in result.lower()

    def test_calculate_empty(self):
        from app.tools.system_tools import calculate_handler
        result = calculate_handler(expression="")
        assert "error" in result.lower()

    def test_navigate_all_pages(self):
        from app.tools.system_tools import navigate_handler
        pages = [
            "dashboard", "inbox", "profile", "tasks", 
            "admin", "admin_users", "admin_activity", "admin_api", 
            "admin_errors", "admin_status", "admin_profile",
            "login", "signup", "telegram"
        ]
        for page in pages:
            result = navigate_handler(page=page)
            assert result.startswith("NAVIGATE:")

    def test_navigate_unknown_page(self):
        from app.tools.system_tools import navigate_handler
        result = navigate_handler(page="nonexistent")
        assert "unknown" in result.lower()

    def test_get_user_profile(self, mocker):
        mocker.patch(
            "app.tools.system_tools.auth_service.get_user_by_email",
            return_value={"name": "Alice", "email": "alice@test.com", "role": "user"},
        )
        from app.tools.system_tools import get_user_profile_handler
        result = get_user_profile_handler("alice@test.com")
        assert "Alice" in result
        assert "alice@test.com" in result

    def test_set_reminder(self):
        from app.tools.system_tools import set_reminder_handler
        result = set_reminder_handler(message="Call mom", minutes=10)
        assert "call mom" in result.lower()
        assert "10" in result

    def test_tell_joke(self):
        from app.tools.system_tools import tell_joke_handler
        result = tell_joke_handler()
        assert isinstance(result, str) and len(result) > 10


# ---------------------------------------------------------------------------
#  Email tools — with mocked EmailService
# ---------------------------------------------------------------------------

class TestEmailTools:
    def test_send_email_no_pin(self, mocker):
        """send_email should fail if Gmail PIN not verified."""
        from app.tools.email_tools import send_email_handler, _gmail_verified
        _gmail_verified.discard("u@test.com")
        result = send_email_handler("u@test.com", to="a@b.com", subject="hi", body="hello")
        assert "pin not verified" in result.lower()

    def test_verify_gmail_pin_success(self, mocker):
        mocker.patch("app.tools.email_tools.auth_service.verify_pin", return_value=True)
        from app.tools.email_tools import verify_gmail_pin_handler, _gmail_verified
        _gmail_verified.discard("u@test.com")
        result = verify_gmail_pin_handler("u@test.com", pin="1234")
        assert "verified successfully" in result.lower()
        assert "u@test.com" in _gmail_verified

    def test_verify_gmail_pin_failure(self, mocker):
        mocker.patch("app.tools.email_tools.auth_service.verify_pin", return_value=False)
        from app.tools.email_tools import verify_gmail_pin_handler, _gmail_verified
        _gmail_verified.discard("u@test.com")
        result = verify_gmail_pin_handler("u@test.com", pin="0000")
        assert "incorrect" in result.lower()
        assert "u@test.com" not in _gmail_verified

    def test_send_email_no_creds(self, mocker):
        mocker.patch("app.tools.email_tools.auth_service.get_credentials", return_value=None)
        from app.tools.email_tools import send_email_handler, _gmail_verified
        _gmail_verified.add("u@test.com")
        result = send_email_handler("u@test.com", to="a@b.com", subject="hi", body="hello")
        assert "error" in result.lower() or "no gmail" in result.lower()

    def test_send_email_success(self, mocker):
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        mock_svc = mocker.patch("app.tools.email_tools.EmailService")
        mock_svc.return_value.send_email.return_value = (True, "Email sent!")
        from app.tools.email_tools import send_email_handler, _gmail_verified
        _gmail_verified.add("u@test.com")
        result = send_email_handler("u@test.com", to="a@b.com", subject="hi", body="hello")
        assert result == "Email sent!"

    def test_get_emails_success(self, mocker):
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        mock_svc = mocker.patch("app.tools.email_tools.EmailService")
        mock_svc.return_value.get_emails.return_value = [
            {"sender": "alice@x.com", "subject": "Hello", "summary": "How are you?"},
        ]
        from app.tools.email_tools import get_emails_handler
        result = get_emails_handler("u@test.com", count=1)
        assert "alice@x.com" in result

    def test_search_emails_no_creds(self, mocker):
        mocker.patch("app.tools.email_tools.auth_service.get_credentials", return_value=None)
        from app.tools.email_tools import search_emails_handler
        result = search_emails_handler("u@test.com", query="test")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
#  Telegram tools — with mocked telegram service
# ---------------------------------------------------------------------------

class TestTelegramTools:
    def test_send_telegram_no_pin(self):
        """send_telegram should fail if Telegram PIN not verified."""
        from app.tools.telegram_tools import send_telegram_handler, _telegram_verified
        _telegram_verified.discard("u@test.com")
        result = send_telegram_handler("u@test.com", contact="John", message="Hi")
        assert "pin not verified" in result.lower()

    def test_verify_telegram_pin_success(self, mocker):
        mocker.patch("app.tools.telegram_tools.auth_service.verify_pin", return_value=True)
        from app.tools.telegram_tools import verify_telegram_pin_handler, _telegram_verified
        _telegram_verified.discard("u@test.com")
        result = verify_telegram_pin_handler("u@test.com", pin="5678")
        assert "verified successfully" in result.lower()
        assert "u@test.com" in _telegram_verified

    def test_verify_telegram_pin_failure(self, mocker):
        mocker.patch("app.tools.telegram_tools.auth_service.verify_pin", return_value=False)
        from app.tools.telegram_tools import verify_telegram_pin_handler, _telegram_verified
        _telegram_verified.discard("u@test.com")
        result = verify_telegram_pin_handler("u@test.com", pin="0000")
        assert "incorrect" in result.lower()
        assert "u@test.com" not in _telegram_verified

    def test_verify_telegram_pin_empty(self):
        from app.tools.telegram_tools import verify_telegram_pin_handler
        result = verify_telegram_pin_handler("u@test.com", pin="")
        assert "error" in result.lower()

    def test_send_telegram_after_pin(self, mocker):
        mocker.patch(
            "app.tools.telegram_tools.telegram_send_message",
            return_value=(True, "Message sent to John"),
        )
        from app.tools.telegram_tools import send_telegram_handler, _telegram_verified
        _telegram_verified.add("u@test.com")
        result = send_telegram_handler("u@test.com", contact="John", message="Hi")
        assert "sent" in result.lower()
        _telegram_verified.discard("u@test.com")

    def test_get_telegram_no_messages(self, mocker):
        mocker.patch("app.tools.telegram_tools.telegram_get_messages", return_value=[])
        from app.tools.telegram_tools import get_telegram_handler
        result = get_telegram_handler("u@test.com")
        assert "no new" in result.lower()

    def test_get_telegram_with_messages(self, mocker):
        mocker.patch(
            "app.tools.telegram_tools.telegram_get_messages",
            return_value=[
                {"name": "Alice", "message": "Hey there!"},
                {"name": "Bob", "message": "Meeting at 3"},
            ],
        )
        from app.tools.telegram_tools import get_telegram_handler
        result = get_telegram_handler("u@test.com", count=2)
        assert "Alice" in result
        assert "Bob" in result


# ---------------------------------------------------------------------------
#  New e-mail tools — get_email_overview / get_important_emails / get_email_body
# ---------------------------------------------------------------------------

class TestNewEmailTools:
    _canned = [
        {"sender": "boss@work.com", "subject": "Urgent: deadline tomorrow", "summary": "Please submit report.", "body": "Full body content here.", "date": "Today"},
        {"sender": "friend@x.com",  "subject": "Weekend plans",              "summary": "Are you free?",          "body": "Hey, want to hang out?",     "date": "Yesterday"},
        {"sender": "noreply@shop.com","subject": "Your order shipped",       "summary": "Order #123 is on its way","body": "Track here...",             "date": "2 days ago"},
    ]

    def _mock_creds_and_service(self, mocker):
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        mock_svc = mocker.patch("app.tools.email_tools.EmailService")
        mock_svc.return_value.get_emails.return_value = self._canned
        return mock_svc

    def test_get_email_overview_shows_senders_and_subjects(self, mocker):
        self._mock_creds_and_service(mocker)
        from app.tools.email_tools import get_email_overview_handler
        result = get_email_overview_handler("u@test.com", count=3)
        assert "boss@work.com" in result
        assert "Urgent: deadline tomorrow" in result
        assert "3 emails" in result

    def test_get_email_overview_no_creds(self, mocker):
        mocker.patch("app.tools.email_tools.auth_service.get_credentials", return_value=None)
        from app.tools.email_tools import get_email_overview_handler
        result = get_email_overview_handler("u@test.com")
        assert "error" in result.lower()

    def test_get_important_emails_finds_urgent(self, mocker):
        self._mock_creds_and_service(mocker)
        from app.tools.email_tools import get_important_emails_handler
        result = get_important_emails_handler("u@test.com")
        assert "Urgent" in result
        assert "Weekend plans" not in result

    def test_get_important_emails_none_found(self, mocker):
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        mock_svc = mocker.patch("app.tools.email_tools.EmailService")
        mock_svc.return_value.get_emails.return_value = [
            {"sender": "a@b.com", "subject": "Hello", "summary": "Just checking in.", "body": "Hi!", "date": "Today"}
        ]
        from app.tools.email_tools import get_important_emails_handler
        result = get_important_emails_handler("u@test.com")
        assert "no high-priority" in result.lower()

    def test_get_email_body_by_index(self, mocker):
        self._mock_creds_and_service(mocker)
        from app.tools.email_tools import get_email_body_handler
        result = get_email_body_handler("u@test.com", index=1)
        assert "Full body content here" in result
        assert "boss@work.com" in result

    def test_get_email_body_by_keyword(self, mocker):
        self._mock_creds_and_service(mocker)
        from app.tools.email_tools import get_email_body_handler
        result = get_email_body_handler("u@test.com", subject_keyword="weekend")
        assert "Hey, want to hang out?" in result

    def test_get_email_body_not_found(self, mocker):
        self._mock_creds_and_service(mocker)
        from app.tools.email_tools import get_email_body_handler
        result = get_email_body_handler("u@test.com", subject_keyword="zzz-no-match", index=999)
        assert "not found" in result.lower()


# ---------------------------------------------------------------------------
#  Task tools — add / list / complete / delete
# ---------------------------------------------------------------------------

class TestTaskTools:
    """Tests for task_tools handlers using an in-memory SQLite DB."""

    @pytest.fixture(autouse=True)
    def _patch_db_path(self, tmp_path, monkeypatch):
        """Point the tasks module at a tmp DB so tests are isolated."""
        import app.database.tasks as tasks_mod
        import app.tools.task_tools as task_tools_mod
        db_path = str(tmp_path / "test_tasks.db")
        monkeypatch.setattr(tasks_mod, "USER_DB_PATH", db_path)
        tasks_mod.init_tasks_db()
        # Patch database functions used by task_tools to go through the tmp DB
        import app.database.database as db_mod
        monkeypatch.setattr(db_mod, "add_task",      lambda *a, **kw: tasks_mod.add_task(*a, **kw))
        monkeypatch.setattr(db_mod, "list_tasks",    lambda *a, **kw: tasks_mod.list_tasks(*a, **kw))
        monkeypatch.setattr(db_mod, "complete_task", lambda *a, **kw: tasks_mod.complete_task(*a, **kw))
        monkeypatch.setattr(db_mod, "delete_task",   lambda *a, **kw: tasks_mod.delete_task(*a, **kw))

    def test_add_task_returns_confirmation(self):
        from app.tools.task_tools import add_task_handler
        result = add_task_handler("u@test.com", "Buy milk")
        assert "Buy milk" in result
        assert "#" in result  # contains ID

    def test_add_task_empty_title_errors(self):
        from app.tools.task_tools import add_task_handler
        result = add_task_handler("u@test.com", title="")
        assert "error" in result.lower()

    def test_list_tasks_pending(self):
        from app.tools.task_tools import add_task_handler, list_tasks_handler
        add_task_handler("u@test.com", "Task A")
        add_task_handler("u@test.com", "Task B", priority="high")
        result = list_tasks_handler("u@test.com", status="pending")
        assert "Task A" in result
        assert "Task B" in result

    def test_list_tasks_empty(self):
        from app.tools.task_tools import list_tasks_handler
        result = list_tasks_handler("u@test.com")
        assert "no pending tasks" in result.lower()

    def test_complete_task(self):
        from app.tools.task_tools import add_task_handler, complete_task_handler, list_tasks_handler
        add_task_handler("u@test.com", "Finish report")
        # ID should be 1 in a fresh DB
        result = complete_task_handler("u@test.com", task_id=1)
        assert "completed" in result.lower()
        # Should no longer appear in pending list
        pending = list_tasks_handler("u@test.com", status="pending")
        assert "Finish report" not in pending

    def test_complete_nonexistent_task(self):
        from app.tools.task_tools import complete_task_handler
        result = complete_task_handler("u@test.com", task_id=9999)
        assert "error" in result.lower() or "not found" in result.lower()

    def test_delete_task(self):
        from app.tools.task_tools import add_task_handler, delete_task_handler, list_tasks_handler
        add_task_handler("u@test.com", "Temp task")
        result = delete_task_handler("u@test.com", task_id=1)
        assert "deleted" in result.lower()
        all_tasks = list_tasks_handler("u@test.com", status="all")
        assert "Temp task" not in all_tasks

    def test_delete_nonexistent_task(self):
        from app.tools.task_tools import delete_task_handler
        result = delete_task_handler("u@test.com", task_id=9999)
        assert "error" in result.lower() or "not found" in result.lower()


# ---------------------------------------------------------------------------
#  Telegram conversation tool
# ---------------------------------------------------------------------------

class TestTelegramConversationTool:
    def test_get_conversation_with_messages(self, mocker):
        mocker.patch(
            "app.tools.telegram_tools.telegram_get_conversation",
            return_value=[
                {"sender": "Alice", "text": "Meeting at 3pm?", "date": "Today 09:00"},
                {"sender": "You",   "text": "Sure!",            "date": "Today 09:01"},
            ],
        )
        from app.tools.telegram_tools import get_telegram_conversation_handler
        result = get_telegram_conversation_handler("u@test.com", contact="Alice")
        assert "Alice" in result
        assert "Meeting at 3pm?" in result

    def test_get_conversation_no_messages(self, mocker):
        mocker.patch("app.tools.telegram_tools.telegram_get_conversation", return_value=[])
        from app.tools.telegram_tools import get_telegram_conversation_handler
        result = get_telegram_conversation_handler("u@test.com", contact="Nobody")
        assert "not found" in result.lower() or "no conversation" in result.lower()

    def test_get_conversation_empty_contact(self):
        from app.tools.telegram_tools import get_telegram_conversation_handler
        result = get_telegram_conversation_handler("u@test.com", contact="")
        assert "error" in result.lower()
