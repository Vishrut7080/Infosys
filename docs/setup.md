# Setup & Deployment

## Environment Variables
The application relies on a `.env` file for local development. All variables are loaded by `pydantic-settings` in `app/core/config.py`.

| Variable               | Description                                                        |
| :--------------------- | :----------------------------------------------------------------- |
| `OPEN_ROUTER_API_key`  | API Key for OpenRouter LLM access                                  |
| `OPENROUTER_MODEL`     | The specific model string (e.g., google/gemini-2.0-flash-exp:free) |
| `OPENROUTER_TIMEOUT`   | Request timeout for LLM calls in seconds (default: None/disabled)  |
| `GROQ_API_KEY`         | API Key for Groq LLM (fast alternative to OpenRouter)              |
| `GROQ_MODEL`           | Groq model string (default: llama-3.3-70b-versatile)               |
| `GOOGLE_CLIENT_ID`     | OAuth Client ID for Google login                                   |
| `GOOGLE_CLIENT_SECRET` | OAuth Client Secret for Google login                               |
| `FLASK_SECRET_KEY`     | Secret key for signing sessions                                    |
| `FLASK_ENV`            | `development` or `production`                                      |
| `FLASK_HOST`           | Bind address (default `0.0.0.0`)                                   |
| `FLASK_PORT`           | Port (default `5000`)                                              |
| `DATABASE_DIR`         | Path for SQLite database files (default `./Database`)              |

### Mock Services Configuration

| Variable          | Description                                                      |
| :---------------- | :--------------------------------------------------------------- |
| `MOCK_SERVICES`   | Master toggle - enables all mocks below when `true`              |
| `MOCK_EMAIL`      | Use in-memory email service (no SMTP/IMAP needed)                |
| `MOCK_TELEGRAM`   | Use mock Telegram service (no Telethon needed)                   |
| `MOCK_LLM`        | Use MockAgent (pattern-matched responses, no API key needed)     |

Granular mock flags (`MOCK_EMAIL`, `MOCK_TELEGRAM`, `MOCK_LLM`) take precedence over `MOCK_SERVICES` when set explicitly.

## Local Development
1. Create a `.env` file using the `.env.example` as a template.
2. Ensure you have `uv` installed (`pip install uv`).
3. Install dependencies: `uv sync`
4. Run locally: `python main.py`

The dev server uses Flask-SocketIO with `eventlet` for WebSocket support. All real-time communication (conversation feed, TTS, stats) flows over WebSocket — see [architecture.md](architecture.md) for the full event reference.

## Production Deployment (Docker)
The app is designed to run in a single container.
1. Build the image: `docker build -t voice-assistant .`
2. Run the container: `docker run -p 5000:5000 -e FLASK_ENV=production -e ... voice-assistant`

Or with Docker Compose: `docker compose up`

*Note: For production, ensure the SQLite database files are mapped to a persistent Docker volume.*
