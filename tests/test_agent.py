"""Tests for the OpenRouterAgent with a mocked LLM backend.

These tests never hit the real OpenRouter API — every HTTP call is intercepted
so we can verify the full tool-call execution loop in isolation.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from app.agent.core import OpenRouterAgent
from tests.conftest import _make_llm_response, make_tool_call


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _patch_llm(responses: list):
    """
    Return a context-manager that patches ``_call_llm`` to yield *responses*
    one at a time.  Each element should be a dict as returned by
    ``_make_llm_response`` (i.e. a single ``choices[0]`` item).
    """
    it = iter(responses)
    return patch.object(
        OpenRouterAgent,
        "_call_llm",
        side_effect=lambda self_ignored=None: next(it, None),
    )


# ---------------------------------------------------------------------------
#  Tests — plain text conversation
# ---------------------------------------------------------------------------

class TestPlainConversation:
    def test_simple_reply(self):
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm([_make_llm_response(content="Hello!")]):
            reply = agent.chat("Hi")
        assert reply == "Hello!"

    def test_empty_content_fallback(self):
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm([_make_llm_response(content="")]):
            reply = agent.chat("Hi")
        assert reply == "I heard you, but I don't know what to say."

    def test_llm_unreachable(self):
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm([None]):
            reply = agent.chat("Hi")
        assert "trouble" in reply.lower()


# ---------------------------------------------------------------------------
#  Tests — tool call execution
# ---------------------------------------------------------------------------

class TestToolCallExecution:
    def test_get_time_tool(self):
        """LLM requests get_time → agent executes it → LLM replies with time."""
        tool_call = make_tool_call("tc1", "get_time", "{}")
        responses = [
            _make_llm_response(tool_calls=[tool_call]),  # LLM asks for tool
            _make_llm_response(content="It is 03:30 PM."),  # LLM replies after tool result
        ]
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm(responses):
            reply = agent.chat("What time is it?")
        assert reply == "It is 03:30 PM."
        # Verify tool result was appended to history
        tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["name"] == "get_time"

    def test_calculate_tool(self):
        tool_call = make_tool_call("tc2", "calculate", '{"expression": "2 + 3 * 4"}')
        responses = [
            _make_llm_response(tool_calls=[tool_call]),
            _make_llm_response(content="The answer is 14."),
        ]
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm(responses):
            reply = agent.chat("What's 2 + 3 * 4?")
        assert reply == "The answer is 14."
        tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
        assert tool_msgs[0]["content"] == "14"

    def test_unknown_tool_graceful(self):
        """An unregistered tool name returns an error string instead of crashing."""
        tool_call = make_tool_call("tc3", "nonexistent_tool", "{}")
        responses = [
            _make_llm_response(tool_calls=[tool_call]),
            _make_llm_response(content="Sorry, I can't do that."),
        ]
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm(responses):
            reply = agent.chat("Do something impossible")
        assert reply == "Sorry, I can't do that."
        tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "not available" in tool_msgs[0]["content"].lower()

    def test_tool_handler_raises(self):
        """If a tool handler throws, the error is captured as a tool result."""
        tool_call = make_tool_call("tc4", "get_time", "{}")
        responses = [
            _make_llm_response(tool_calls=[tool_call]),
            _make_llm_response(content="Something went wrong."),
        ]
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        from app.tools.registry import registry
        tool_entry = registry.get_tool("get_time")
        assert tool_entry is not None
        original = tool_entry["handler"]
        registry._tools["get_time"]["handler"] = MagicMock(side_effect=RuntimeError("boom"))
        try:
            with _patch_llm(responses):
                reply = agent.chat("time?")
        finally:
            registry._tools["get_time"]["handler"] = original
        tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
        assert "error" in tool_msgs[0]["content"].lower()

    def test_multiple_tool_calls_in_one_turn(self):
        """LLM requests two tools at once — both are executed."""
        calls = [
            make_tool_call("tc5", "get_date", "{}"),
            make_tool_call("tc6", "get_time", "{}"),
        ]
        responses = [
            _make_llm_response(tool_calls=calls),
            _make_llm_response(content="Today is Monday, time is noon."),
        ]
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm(responses):
            reply = agent.chat("What day and time is it?")
        tool_msgs = [m for m in agent.history if m.get("role") == "tool"]
        assert len(tool_msgs) == 2

    def test_loop_limit(self):
        """If LLM keeps requesting tools forever, the loop caps at 5 iterations."""
        tool_call = make_tool_call("tcX", "get_time", "{}")
        # Always return a tool call — the loop should break after 5 iterations
        infinite_tool_responses = [_make_llm_response(tool_calls=[tool_call])] * 6
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm(infinite_tool_responses):
            reply = agent.chat("loop forever")
        assert "stuck" in reply.lower()


# ---------------------------------------------------------------------------
#  Tests — navigate tool
# ---------------------------------------------------------------------------

class TestNavigateTool:
    def test_valid_page(self):
        from app.tools.system_tools import navigate_handler
        result = navigate_handler(page="inbox")
        assert result == "NAVIGATE:/dashboard#inbox"

    def test_unknown_page(self):
        from app.tools.system_tools import navigate_handler
        result = navigate_handler(page="nonexistent")
        assert "unknown" in result.lower()

    def test_last_tool_results_tracked(self):
        """Verify that agent.last_tool_results is populated after tool execution."""
        tool_call = make_tool_call("tc_nav", "navigate", '{"page": "inbox"}')
        responses = [
            _make_llm_response(tool_calls=[tool_call]),
            _make_llm_response(content="Taking you to your inbox."),
        ]
        agent = OpenRouterAgent(api_key="fake", user_email="u@test.com")
        with _patch_llm(responses):
            agent.chat("Go to inbox")
        assert len(agent.last_tool_results) == 1
        assert agent.last_tool_results[0]["tool"] == "navigate"
        assert "NAVIGATE:" in agent.last_tool_results[0]["result"]
