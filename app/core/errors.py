class AssistantError(Exception):
    """Base class for all assistant-related exceptions."""
    pass

class ToolError(AssistantError):
    """Raised when an agent tool fails."""
    pass

class TelegramError(AssistantError):
    """Raised when Telegram operations fail."""
    pass

class EmailError(AssistantError):
    """Raised when email operations fail."""
    pass
