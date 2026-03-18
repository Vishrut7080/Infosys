"""Shared fixtures for the Infosys test suite."""

import pytest
from app.tools.registry import ToolRegistry


@pytest.fixture()
def fresh_registry():
    """Return a clean ToolRegistry with no tools registered."""
    return ToolRegistry()


@pytest.fixture()
def populated_registry():
    """Return a ToolRegistry pre-loaded with the real system/email/telegram tools."""
    from app.tools.registry import registry  # triggers __init__ side-effect imports
    return registry


def _make_llm_response(content=None, tool_calls=None):
    """Helper to build a fake OpenRouter /chat/completions choice dict."""
    msg: dict = {"role": "assistant"}
    if content is not None:
        msg["content"] = content
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
        msg["content"] = ""
    return {"message": msg}


def make_tool_call(call_id, name, arguments_json):
    """Build a single tool_call object matching the OpenRouter schema."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments_json},
    }


@pytest.fixture()
def make_llm_response():
    """Expose _make_llm_response as a fixture for cleaner test code."""
    return _make_llm_response
