# System Architecture Overview

This project is a modular, agent-based Voice Assistant designed for personal use, managing Gmail and Telegram interactions through natural language commands powered by an LLM.

## Key Architectural Principles
- **Agentic Loop**: Uses an `OpenRouterAgent` (LLM-based) to orchestrate tasks by calling predefined tools.
- **Stateless Design**: The server holds no per-user in-memory state. All persistence lives in SQLite and browser sessions. Real-time data flows through WebSocket events, not server-side dictionaries.
- **WebSocket-First Communication**: All real-time updates (conversation feed, TTS, stats) are pushed to the client over Flask-SocketIO. The frontend subscribes to WebSocket events — it never polls for live data.
- **Asynchronous Processing**: The system is fully `async` (using `httpx` and `Telethon`), ensuring non-blocking operations.
- **Production-Ready**: Containerized with multi-stage Docker builds using `uv` and served via `gunicorn` + `eventlet`.

## High-Level Component Map
- `app/agent/`: The "Brain." Manages LLM interaction, tool calling, and conversation history.
- `app/services/`: Pure, stateless functional logic (Email, Telegram, Auth).
- `app/tools/`: The bridge between the Agent and the Services.
- `app/web/`: Flask API, WebSockets, and Routes (Blueprints).
- `app/database/`: SQLite backend for persistence and logging.
- `app/core/`: Global utilities (Config, Logging, Error Handling).

## Client-Server Communication

### WebSocket Events (server → client)
| Event          | Payload                          | Purpose                          |
| :------------- | :------------------------------- | :------------------------------- |
| `feed_update`  | `{ text, time }`                 | New conversation entry           |
| `tts`          | `{ text, lang }`                 | Trigger browser speech synthesis |
| `stats_update` | `{ users, active, api_calls … }` | Admin dashboard metrics refresh  |

### Browser CustomEvents (client-side bridging)
| Event             | Source         | Listeners                      | Purpose                                                                                                |
| :---------------- | :------------- | :----------------------------- | :----------------------------------------------------------------------------------------------------- |
| `feed-update`     | `assistant.js` | dashboard, admin, lang, signup | Re-broadcasts `feed_update` so any page script can subscribe without holding a direct socket reference |
| `session-expired` | `assistant.js` | dashboard, admin               | Fired after a WebSocket disconnect + `/check-session` confirms the user is logged out                  |

### REST Endpoints (one-shot requests)
REST is used only for actions that are inherently request/response:
- **Auth**: `/login`, `/register`, `/voice-logout`, `/check-session`, Google OAuth
- **Chat**: `POST /api/chat` (sends user message; agent reply arrives via `feed_update`)
- **Data fetches**: `/get-stats`, `/get-user-info`, `/get-services`, `/get-inbox`
- **Form actions**: `/update-profile-name`, `/update-profile-password`, `/select-services`
- **Signals**: `POST /typing` (fire-and-forget), `POST /signup-closed` (beacon)
- **Admin CRUD**: `/admin/users`, `/admin/active-users`, `/admin/activity`, `/admin/stats`, etc.

### What the Frontend Never Does
- **No polling for the conversation feed.** Feed entries arrive via `feed_update` WebSocket events.
- **No polling for logout detection.** The `disconnect` WebSocket event triggers a one-shot `/check-session` check, which dispatches `session-expired` if confirmed.
- **No server-side in-memory state.** There are no `_feeds`, `_actions`, or similar dictionaries on the server — everything is event-driven or persisted in SQLite.
