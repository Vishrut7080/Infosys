# Infosys Voice Assistant

A modular, agent-based voice assistant that manages Gmail and Telegram through natural language commands powered by an LLM (via OpenRouter).

## Features

- **Auto voice login** — Microphone starts automatically on the login page; say your audio password without pressing any buttons
- **Voice-controlled email** — Send, read, search, and summarise Gmail emails by voice
- **Telegram integration** — Send, receive, and browse Telegram conversations by voice
- **Task management** — Add, list, complete, and delete personal tasks by voice or via the Tasks dashboard page
- **LLM-powered agent** — Natural language understanding via OpenRouter or Groq (tool-calling architecture)
- **Agent explains capabilities** — Ask "what can you do?" and the agent describes all available features
- **WebSocket-first** — All real-time data (conversation feed, TTS, session events) is pushed over Flask-SocketIO; no polling
- **Multi-language** — English and Hindi UI support
- **Admin panel** — User management, activity logs, and system monitoring
- **Google OAuth** — Sign in with Google
- **Audio password** — Voice-based authentication
- **Granular mock mode** — Mock email, Telegram, and LLM independently via `MOCK_EMAIL`, `MOCK_TELEGRAM`, `MOCK_LLM`

## Architecture

| Directory             | Purpose                                                |
| :-------------------- | :----------------------------------------------------- |
| `app/agent/`          | LLM agent with tool-calling (OpenRouter API)           |
| `app/services/`       | Email (SMTP/IMAP) and Telegram (Telethon) services     |
| `app/services/mocks/` | Mock implementations of email and Telegram for testing |
| `app/tools/`          | Tool registry bridging the agent and services          |
| `app/web/`            | Flask API, WebSockets (SocketIO), and routes           |
| `app/database/`       | SQLite backend for users and admin data                |
| `app/core/`           | Configuration, logging, and error handling             |
| `tests/`              | Pytest test suite with mocked LLM and service tests    |

See [docs/architecture.md](docs/architecture.md) and [docs/agent_design.md](docs/agent_design.md) for detailed design docs.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your API keys:

   ```env
   OPEN_ROUTER_API_key=your-openrouter-key
   OPENROUTER_MODEL=google/gemini-2.0-flash-exp:free
   FLASK_SECRET_KEY=pick-a-strong-secret
   # Optional — leave blank to skip Gmail/Telegram features
   GOOGLE_CLIENT_ID=
   GOOGLE_CLIENT_SECRET=
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Seed the development database (creates test users):

   ```bash
   uv run seed_db.py
   ```

   This creates three users (safe to run multiple times — existing users are skipped):

   | User         | Email             | Password    | Role  |
   | ------------ | ----------------- | ----------- | ----- |
   | Alice Admin  | alice@example.com | password123 | Admin |
   | Bob User     | bob@example.com   | password123 | User  |
   | Carol Tester | carol@example.com | password123 | User  |

4. Run the server:

   ```bash
   uv run python main.py
   ```

   Open `http://localhost:5000` in your browser.

See [docs/setup.md](docs/setup.md) for the full environment variable reference.

## Mock Mode

To run the app **without real Gmail/Telegram credentials**, use granular mock flags:

```env
MOCK_EMAIL=true      # in-memory email service (no SMTP/IMAP needed)
MOCK_TELEGRAM=true   # canned Telegram responses (no Telethon needed)
MOCK_LLM=true        # pattern-matched agent responses (no OpenRouter key needed)
```

Or enable all three at once:

```env
MOCK_SERVICES=true
```

In mock mode:

- **Email tools** use `MockEmailService` — sends go to an in-memory store, inbox returns canned sample emails
- **Telegram tools** use `MockTelegramState` — messages go to an in-memory store, inbox returns canned sample messages
- **LLM** uses `MockAgent` — pattern-matched responses with no API calls, full tool dispatch still works
- Useful for developing and testing the agent loop without configuring external services

See [docs/testing-guide-mock.md](docs/testing-guide-mock.md) for a step-by-step walkthrough.

## Available Agent Tools

| Tool                        | Description                             | Needs Credentials |
| --------------------------- | --------------------------------------- | :---------------: |
| `get_time`                  | Current time                            |        No         |
| `get_date`                  | Current date                            |        No         |
| `get_datetime`              | Current date and time                   |        No         |
| `get_system_info`           | OS, Python version, machine info        |        No         |
| `random_number`             | Random integer in a given range         |        No         |
| `calculate`                 | Safe arithmetic evaluator               |        No         |
| `navigate`                  | Returns URL for an app page             |        No         |
| `get_user_profile`          | Logged-in user's name, email, role      |        No         |
| `set_reminder`              | Acknowledges a reminder (in-memory)     |        No         |
| `tell_joke`                 | Random clean programmer joke            |        No         |
| `switch_language`           | Switch UI language (Hindi/English)      |        No         |
| `logout`                    | Logout via voice command                |        No         |
| `add_task`                  | Add a new personal task                 |        No         |
| `list_tasks`                | List tasks by status                    |        No         |
| `complete_task`             | Mark a task as done                     |        No         |
| `delete_task`               | Delete a task                           |        No         |
| `verify_gmail_pin`          | Verify Gmail PIN before sending         |       Gmail       |
| `send_email`                | Send an email via Gmail SMTP            |       Gmail       |
| `get_emails`                | Fetch latest emails via Gmail IMAP      |       Gmail       |
| `search_emails`             | Search emails by keyword                |       Gmail       |
| `get_email_overview`        | Inbox summary (count, unread, senders)  |       Gmail       |
| `get_important_emails`      | Important / high-priority emails        |       Gmail       |
| `get_email_body`            | Full body of a specific email           |       Gmail       |
| `verify_telegram_pin`       | Verify Telegram PIN before sending      |     Telegram      |
| `send_telegram`             | Send a Telegram message                 |     Telegram      |
| `get_telegram_messages`     | Fetch recent Telegram messages          |     Telegram      |
| `get_telegram_conversation` | Full conversation thread with a contact |     Telegram      |

See [docs/tools.md](docs/tools.md) for the full tool reference.

## Testing

The test suite uses **pytest** with the LLM fully mocked (no API calls) and mock service backends.

```bash
# Install test dependencies
uv pip install pytest pytest-mock

# Run all tests
uv run pytest tests/ -v

# Run only agent tests
uv run pytest tests/test_agent.py -v

# Run only mock service tests
uv run pytest tests/test_mock_services.py -v

# Run only tool/registry tests
uv run pytest tests/test_tools.py -v
```

### Test structure

| File                          | What it tests                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------ |
| `tests/conftest.py`           | Shared fixtures: fake LLM responses, tool call builders                                    |
| `tests/test_agent.py`         | Agent loop with mocked `_call_llm`: plain chat, tool execution, error handling, loop limit |
| `tests/test_tools.py`         | Tool registry, system tools (unit), email/telegram/task tools (with mocked services)       |
| `tests/test_mock_services.py` | Mock email/telegram services directly, tool handlers via mocks, full agent E2E with mocks  |

### Manual test guides

- [docs/testing-guide-mock.md](docs/testing-guide-mock.md) — step-by-step walkthrough using mock services (no credentials needed)
- [docs/testing-guide-real.md](docs/testing-guide-real.md) — end-to-end walkthrough with real Gmail and Telegram

## Docker

```bash
docker build -t voice-assistant .
docker compose up
```

## License

See [LICENSE](LICENSE).
