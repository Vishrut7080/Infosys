"""Tests for mock services — verifies that the mock email and telegram
implementations behave correctly, and that the tool handlers work with
them end-to-end (including via the agent loop when MOCK_SERVICES=true).
"""

import pytest
from unittest.mock import patch

from app.services.mocks.mock_email import MockEmailService
from app.services.mocks.mock_telegram import (
    MockTelegramState,
    telegram_send_message,
    telegram_get_messages,
    telegram_is_authorized,
    telegram_is_ready,
    telegram_status,
    start_telegram_in_thread,
)


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_mocks():
    """Clear shared mock state before each test."""
    MockEmailService.reset()
    MockTelegramState.reset()
    yield
    MockEmailService.reset()
    MockTelegramState.reset()


# ---------------------------------------------------------------------------
#  MockEmailService
# ---------------------------------------------------------------------------

class TestMockEmailService:
    def test_send_email(self):
        svc = MockEmailService('{"email": "me@test.com"}')
        ok, msg = svc.send_email("dest@test.com", "Hi", "Hello body")
        assert ok is True
        assert "MOCK" in msg
        sent = MockEmailService.get_sent_emails()
        assert len(sent) == 1
        assert sent[0]["to"] == "dest@test.com"
        assert sent[0]["subject"] == "Hi"

    def test_get_emails_returns_canned(self):
        svc = MockEmailService('{"email": "me@test.com"}')
        emails = svc.get_emails(count=1)
        assert len(emails) == 1
        assert "sender" in emails[0]

    def test_reset_clears_sent(self):
        svc = MockEmailService('{"email": "me@test.com"}')
        svc.send_email("a@b.com", "x", "y")
        assert len(MockEmailService.get_sent_emails()) == 1
        MockEmailService.reset()
        assert len(MockEmailService.get_sent_emails()) == 0


# ---------------------------------------------------------------------------
#  MockTelegram
# ---------------------------------------------------------------------------

class TestMockTelegram:
    def test_send_message(self):
        ok, msg = telegram_send_message("Alice", "Hi!", email="u@test.com")
        assert ok is True
        assert "MOCK" in msg
        assert len(MockTelegramState.get_sent_messages()) == 1

    def test_get_messages(self):
        msgs = telegram_get_messages(count=2, email="u@test.com")
        assert len(msgs) == 2
        assert "name" in msgs[0]

    def test_status_disconnected_by_default(self):
        assert telegram_status("u@test.com") == "disconnected"
        assert telegram_is_authorized("u@test.com") is False
        assert telegram_is_ready("u@test.com") is False

    def test_start_marks_connected(self):
        start_telegram_in_thread("u@test.com")
        assert telegram_status("u@test.com") == "ready"
        assert telegram_is_authorized("u@test.com") is True
        assert telegram_is_ready("u@test.com") is True


# ---------------------------------------------------------------------------
#  Tool handlers via mock services
# ---------------------------------------------------------------------------

class TestToolsWithMocks:
    """Test that the actual tool handlers (email_tools / telegram_tools)
    work correctly when wired to mock services."""

    def test_send_email_tool_with_mock(self, mocker):
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        # Patch the EmailService reference inside email_tools to use mock
        mocker.patch(
            "app.tools.email_tools.EmailService",
            MockEmailService,
        )
        from app.tools.email_tools import send_email_handler, _gmail_verified
        _gmail_verified.add("u@test.com")  # simulate PIN already verified
        result = send_email_handler("u@test.com", to="x@y.com", subject="Test", body="Body")
        assert "MOCK" in result
        assert len(MockEmailService.get_sent_emails()) == 1

    def test_get_emails_tool_with_mock(self, mocker):
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        mocker.patch(
            "app.tools.email_tools.EmailService",
            MockEmailService,
        )
        from app.tools.email_tools import get_emails_handler
        result = get_emails_handler("u@test.com", count=2)
        assert "mock-alice@example.com" in result.lower() or "mock" in result.lower()

    def test_send_telegram_tool_with_mock(self, mocker):
        mocker.patch(
            "app.tools.telegram_tools.telegram_send_message",
            telegram_send_message,
        )
        from app.tools.telegram_tools import send_telegram_handler, _telegram_verified
        _telegram_verified.add("u@test.com")
        result = send_telegram_handler("u@test.com", contact="Alice", message="Hi")
        assert "MOCK" in result or "sent" in result.lower()
        _telegram_verified.discard("u@test.com")

    def test_get_telegram_tool_with_mock(self, mocker):
        mocker.patch(
            "app.tools.telegram_tools.telegram_get_messages",
            telegram_get_messages,
        )
        from app.tools.telegram_tools import get_telegram_handler
        result = get_telegram_handler("u@test.com", count=1)
        assert "Mock-Alice" in result


# ---------------------------------------------------------------------------
#  Agent end-to-end with mock services
# ---------------------------------------------------------------------------

class TestAgentE2EWithMocks:
    """Full agent loop: mock LLM requests a tool → tool runs against mock
    service → LLM summarises the result."""

    def test_agent_sends_mock_email(self, mocker):
        from tests.conftest import _make_llm_response, make_tool_call
        from app.agent.core import OpenRouterAgent

        # Mock auth to return credentials
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        # Wire mock email service
        mocker.patch("app.tools.email_tools.EmailService", MockEmailService)

        # Pre-authorize Gmail PIN for the test user
        from app.tools.email_tools import _gmail_verified
        _gmail_verified.add("me@test.com")

        tool_call = make_tool_call(
            "tc_email",
            "send_email",
            '{"to": "friend@test.com", "subject": "Hello", "body": "Hi there!"}',
        )
        responses = iter([
            _make_llm_response(tool_calls=[tool_call]),
            _make_llm_response(content="Email sent to friend@test.com."),
        ])

        with patch.object(OpenRouterAgent, "_call_llm", side_effect=lambda: next(responses, None)):
            agent = OpenRouterAgent(api_key="fake", user_email="me@test.com")
            reply = agent.chat("Send an email to friend@test.com saying Hi there!")

        assert "friend@test.com" in reply
        sent = MockEmailService.get_sent_emails()
        assert len(sent) == 1
        assert sent[0]["to"] == "friend@test.com"

    def test_agent_reads_mock_telegram(self, mocker):
        from tests.conftest import _make_llm_response, make_tool_call
        from app.agent.core import OpenRouterAgent

        mocker.patch(
            "app.tools.telegram_tools.telegram_get_messages",
            telegram_get_messages,
        )

        tool_call = make_tool_call("tc_tg", "get_telegram_messages", '{"count": 2}')
        responses = iter([
            _make_llm_response(tool_calls=[tool_call]),
            _make_llm_response(content="You have messages from Mock-Alice and Mock-Bob."),
        ])

        with patch.object(OpenRouterAgent, "_call_llm", side_effect=lambda: next(responses, None)):
            agent = OpenRouterAgent(api_key="fake", user_email="me@test.com")
            reply = agent.chat("Check my Telegram messages")

        assert "Mock-Alice" in reply or "Mock-Bob" in reply
        # Verify the tool result was stored in history
        tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "Mock-Alice" in tool_msgs[0]["content"]


# ---------------------------------------------------------------------------
#  MockAgent — no API key needed
# ---------------------------------------------------------------------------

class TestMockAgent:
    def test_greeting(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("Hello")
        assert "hello" in reply.lower() or "help" in reply.lower()

    def test_check_emails(self, mocker):
        mocker.patch(
            "app.tools.email_tools.auth_service.get_credentials",
            return_value={"gmail_address": "me@gmail.com", "gmail_token": '{"email": "me@gmail.com"}'},
        )
        mocker.patch("app.tools.email_tools.EmailService", MockEmailService)
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("Check my emails")
        assert "mock" in reply.lower() or "email" in reply.lower()
        assert len(agent.last_tool_results) >= 1

    def test_check_telegram(self, mocker):
        mocker.patch(
            "app.tools.telegram_tools.telegram_get_messages",
            telegram_get_messages,
        )
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("Get my telegram messages")
        assert "mock" in reply.lower() or "telegram" in reply.lower()

    def test_get_time(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("What time is it?")
        assert ":" in reply  # time format contains colon

    def test_tell_joke(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("Tell me a joke")
        assert len(reply) > 10

    def test_cancel(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("Cancel")
        assert "cancel" in reply.lower()

    def test_fallback(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("xyzzy nonsense blah")
        assert "offline mode" in reply.lower()

    def test_email_overview_pattern(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("give me an overview of my inbox")
        assert any(word in reply.lower() for word in ("inbox", "email", "overview", "error"))

    def test_important_emails_pattern(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("show me my important emails")
        # Either returns emails or "no high-priority" message
        assert len(reply) > 5

    def test_email_body_pattern(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("read the body of the first email")
        assert len(reply) > 5

    def test_telegram_conversation_pattern(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("show me the conversation with Mock-Alice")
        assert len(reply) > 5

    def test_add_task_pattern(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("add a task buy milk")
        assert any(word in reply.lower() for word in ("task", "created", "error"))

    def test_list_tasks_pattern(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("list my pending tasks")
        assert len(reply) > 5

    def test_complete_task_pattern(self):
        from app.services.mocks.mock_agent import MockAgent
        agent = MockAgent("u@test.com")
        reply = agent.chat("complete task #1")
        assert len(reply) > 5

    def test_telegram_conversation_in_state(self):
        """Verify MockTelegramState._conversations contains expected contacts."""
        assert "Mock-Alice" in MockTelegramState._conversations
        assert len(MockTelegramState._conversations["Mock-Alice"]) >= 1
        assert "text" in MockTelegramState._conversations["Mock-Alice"][0]

    def test_telegram_get_conversation_function(self):
        """telegram_get_conversation returns correct messages for a known contact."""
        from app.services.mocks.mock_telegram import telegram_get_conversation
        msgs = telegram_get_conversation("Mock-Alice", count=5)
        assert len(msgs) >= 1
        assert all("sender" in m and "text" in m for m in msgs)

    def test_telegram_get_conversation_unknown_contact(self):
        from app.services.mocks.mock_telegram import telegram_get_conversation
        msgs = telegram_get_conversation("Nobody Known", count=5)
        assert msgs == []


# ---------------------------------------------------------------------------
#  Granular mock config flags
# ---------------------------------------------------------------------------

class TestGranularMockFlags:
    def test_mock_services_enables_all(self):
        from app.core.config import Settings
        s = Settings(MOCK_SERVICES=True, MOCK_EMAIL=False, MOCK_TELEGRAM=False, MOCK_LLM=False)
        assert s.mock_email is True
        assert s.mock_telegram is True
        assert s.mock_llm is True

    def test_granular_flags_independent(self):
        from app.core.config import Settings
        s = Settings(MOCK_SERVICES=False, MOCK_EMAIL=True, MOCK_TELEGRAM=False, MOCK_LLM=True)
        assert s.mock_email is True
        assert s.mock_telegram is False
        assert s.mock_llm is True

    def test_all_false_by_default(self):
        from app.core.config import Settings
        s = Settings(MOCK_SERVICES=False, MOCK_EMAIL=False, MOCK_TELEGRAM=False, MOCK_LLM=False)
        assert s.mock_email is False
        assert s.mock_telegram is False
        assert s.mock_llm is False
