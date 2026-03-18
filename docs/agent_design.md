# Agent Design: Tool-Calling Architecture

The assistant uses an agentic architecture centered on `OpenRouterAgent` (in `app/agent/core.py`).

## The Agent Loop (ReAct)
1. **User Request**: User sends text (typed or transcribed from speech) via `POST /api/chat`.
2. **LLM Reasoning**: The `OpenRouterAgent` calls the LLM with the full `history` + `registry.get_definitions()`.
3. **Tool Call**: The LLM returns a JSON object requesting a tool call.
4. **Execution**: The agent pauses, calls the matching `ToolHandler` (from `app/tools/`), and gets the results.
5. **Observation**: The Agent sends the result back to the LLM.
6. **Final Answer**: The LLM generates the natural language response, which is pushed to the client via the `feed_update` WebSocket event (and optionally spoken aloud via the `tts` event).

## Response Delivery
The agent never returns its response over HTTP. Instead:
- The `/api/chat` endpoint kicks off the agent loop asynchronously.
- Each conversation entry (user message, tool output, agent reply) is emitted to the user's SocketIO room via `feed_update`.
- The client `assistant.js` receives `feed_update`, dispatches a `feed-update` CustomEvent, and any page-specific script (dashboard, admin, lang, signup) can react.

## Adding New Features
To add a new tool (e.g., WhatsApp):
1. **Service Layer**: Implement the functionality in `app/services/whatsapp.py`.
2. **Tool Handler**: Register a new tool in `app/tools/whatsapp_tools.py` using `registry.register`.
3. **Registration**: Ensure `app/tools/__init__.py` imports it.
4. **Agent Logic**: The LLM will automatically see the new tool definition on the next turn.
