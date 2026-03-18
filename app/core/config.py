import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Flask/Gunicorn
    FLASK_ENV: str = "production"
    FLASK_HOST: str = "0.0.0.0"
    FLASK_PORT: int = 5000
    FLASK_SECRET_KEY: str = "change-me-in-production"

    # External APIs
    OPEN_ROUTER_API_key: str = ""
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash-exp:free"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Database
    DATABASE_DIR: str = "./Database"

    # Mock services — global shortcut, enables all mocks below when True
    MOCK_SERVICES: bool = False

    # Granular mock toggles — each defaults to False; MOCK_SERVICES overrides all
    MOCK_EMAIL: bool = False       # use fake email  (no SMTP/IMAP needed)
    MOCK_TELEGRAM: bool = False    # use fake Telegram (no Telethon needed)
    MOCK_LLM: bool = False         # use MockAgent   (no OpenRouter API key needed)
    # Request timeout for LLM calls (seconds). Set to null/None to disable timeout.
    OPENROUTER_TIMEOUT: int | None = None

    # Groq (fast free alternative to OpenRouter)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

    # ── Computed helpers (MOCK_SERVICES acts as a universal override) ──────
    @property
    def mock_email(self) -> bool:
        return self.MOCK_EMAIL or self.MOCK_SERVICES

    @property
    def mock_telegram(self) -> bool:
        return self.MOCK_TELEGRAM or self.MOCK_SERVICES

    @property
    def mock_llm(self) -> bool:
        return self.MOCK_LLM or self.MOCK_SERVICES

settings = Settings()
