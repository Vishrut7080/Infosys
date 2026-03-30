# Agent Design: Tool-Calling Architecture

The assistant uses an agentic architecture centered on the agent classes in `app/agent/core.py`.

## LLM Provider Tiers

The system supports three LLM providers with automatic fallback:

| Tier | Class | Provider | Condition |
|------|-------|----------|-----------|
| 1 | `OpenRouterAgent` | OpenRouter API | Default when `OPEN_ROUTER_API_key` is set |
| 2 | `GroqAgent` | Groq API | Used when `GROQ_API_KEY` is set (faster alternative) |
| 3 | `MockAgent` | Local pattern matching | Fallback on LLM timeout/error, or when `MOCK_LLM=true` |

The selection logic in `assistant.py` checks:
1. If `MOCK_LLM=true` → use `MockAgent`
2. If `GROQ_API_KEY` is set → use `GroqAgent`
3. Otherwise → use `OpenRouterAgent`

On timeout or API failure, the system automatically falls back to `MockAgent` for graceful degradation.

## The Agent Loop (ReAct)
1. **User Request**: User sends text (typed or transcribed from speech) via `POST /api/chat`.
2. **LLM Reasoning**: The agent calls the LLM with the full `history` + `registry.get_definitions()`.
3. **Tool Call**: The LLM returns a JSON object requesting one or more tool calls.
4. **Execution**: The agent pauses, calls the matching `ToolHandler` (from `app/tools/`), and gets the results.
5. **Observation**: The Agent sends the tool results back to the LLM.
6. **Final Answer**: The LLM generates the natural language response, which is pushed to the client via the `feed_update` WebSocket event (and optionally spoken aloud via the `tts` event).

The loop allows up to 5 iterations for chained tool calls before exiting with a fallback message.

## Response Delivery
The agent never returns its response over HTTP. Instead:
- The `/api/chat` endpoint kicks off the agent loop asynchronously.
- Each conversation entry (user message, tool output, agent reply) is emitted to the user's SocketIO room via `feed_update`.
- The client `assistant.js` receives `feed_update`, dispatches a `feed-update` CustomEvent, and any page-specific script (dashboard, admin, lang, signup) can react.

## Adding New Features
To add a new tool (e.g., Slack integration):

1. **Service Layer** (optional): If external API calls are needed, implement the service in `app/services/slack.py`.
2. **Mock Service** (optional): For testing, create `app/services/mocks/mock_slack.py` with the same public API.
3. **Tool Handler**: Create `app/tools/slack_tools.py` and implement handler functions:
   ```python
   def slack_send_handler(user_email, channel, message):
       # Implementation
       return "Message sent to #channel"
   
   registry.register(
       name="slack_send",
       description="Send a message to a Slack channel.",
       schema={
           "type": "object",
           "properties": {
               "channel": {"type": "string", "description": "Channel name"},
               "message": {"type": "string", "description": "Message content"}
           },
           "required": ["channel", "message"]
       },
       handler=slack_send_handler
   )
   ```
4. **Registration**: Add import to `app/tools/__init__.py`:
   ```python
   import app.tools.slack_tools  # noqa: F401
   ```
5. **Mock Toggle** (optional): Add `MOCK_SLACK` to config if using mock services.
6. **Agent Logic**: The LLM will automatically see the new tool definition on the next turn.
