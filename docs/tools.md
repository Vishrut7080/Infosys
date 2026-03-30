# Agent Tools Reference

All tools are registered automatically when the app starts. The LLM decides which tool to call based on the user's voice command.

## System Tools

| Tool               | Description                                          | Parameters                                                                                                            |
| ------------------ | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `get_time`         | Returns the current time (12-hour format)            | —                                                                                                                     |
| `get_date`         | Returns the current date (weekday, day month year)   | —                                                                                                                     |
| `get_datetime`     | Returns both date and time together                  | —                                                                                                                     |
| `get_system_info`  | Returns OS, Python version, and machine architecture | —                                                                                                                     |
| `random_number`    | Generates a random integer in a range                | `min_val` (int, default 1), `max_val` (int, default 100)                                                              |
| `calculate`        | Evaluates a basic arithmetic expression safely       | `expression` (string, **required**)                                                                                   |
| `navigate`         | Navigates the user to an app page                    | `page` (string, **required**) — see Navigation Targets below                                                          |
| `get_user_profile` | Returns the logged-in user's name, email, and role   | —                                                                                                                     |
| `set_reminder`     | Acknowledges a reminder (not yet persisted)          | `message` (string, **required**), `minutes` (int, default 5)                                                          |
| `tell_joke`        | Returns a random clean programmer joke               | —                                                                                                                     |
| `switch_language`  | Switches UI and TTS language                         | `language` (string, **required**) — `hi` for Hindi, `en` for English                                                  |
| `logout`           | Logs out the current user via voice command           | —                                                                                                                     |

### Navigation Targets

| Target            | Destination          |
| ----------------- | -------------------- |
| `dashboard`       | `/dashboard`         |
| `inbox`           | `/dashboard#inbox`   |
| `profile`         | `/dashboard#profile` |
| `tasks`           | `/dashboard#tasks`   |
| `admin`           | `/admin`             |
| `admin_overview`  | `/admin#overview`    |
| `admin_users`     | `/admin#users`       |
| `admin_activity`  | `/admin#activity`    |
| `admin_api`       | `/admin#api`         |
| `admin_errors`    | `/admin#errors`      |
| `admin_status`    | `/admin#status`      |
| `admin_profile`   | `/admin#profile`     |
| `login`           | `/`                  |
| `signup`          | `/signup`            |
| `telegram`        | `/telegram-auth`     |

## Email Tools

| Tool                   | Description                                                                     | Parameters                                                                                   |
| ---------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `verify_gmail_pin`     | Verifies the user's 4-digit Gmail PIN. **Must be called before sending email.** | `pin` (string, **required**)                                                                 |
| `send_email`           | Sends an email via Gmail. Requires prior PIN verification.                      | `to` (string, **required**), `subject` (string, **required**), `body` (string, **required**) |
| `get_emails`           | Fetches latest emails from Gmail inbox                                          | `count` (int, default 5), `category` (string: ALL, PRIMARY, PROMOTIONS, UPDATES)             |
| `search_emails`        | Searches emails by keyword in subject or sender                                 | `query` (string, **required**), `count` (int, default 5)                                     |
| `get_email_overview`   | Returns a summary of the inbox: total count, unread count, and top senders      | `count` (int, default 10)                                                                    |
| `get_important_emails` | Returns emails flagged as important or high priority                            | `count` (int, default 5)                                                                     |
| `get_email_body`       | Returns the full body of a specific email by index (1-based)                    | `index` (int, default 1)                                                                     |

## Telegram Tools

| Tool                        | Description                                                                  | Parameters                                                         |
| --------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `verify_telegram_pin`       | Verifies the user's 4-digit Telegram PIN. **Must be called before sending.** | `pin` (string, **required**)                                       |
| `send_telegram`             | Sends a message to a Telegram contact or group                               | `contact` (string, **required**), `message` (string, **required**) |
| `get_telegram_messages`     | Fetches latest Telegram messages                                             | `count` (int, default 5)                                           |
| `get_telegram_conversation` | Returns a full message thread with a specific contact                        | `contact` (string, **required**), `count` (int, default 10)        |

## Task Tools

| Tool            | Description                                 | Parameters                                                                                                  |
| --------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `add_task`      | Creates a new task for the logged-in user   | `title` (string, **required**), `description` (string, optional), `priority` (string: normal/high/urgent, default normal) |
| `list_tasks`    | Returns the user's tasks filtered by status | `status` (string: pending/done/all, default pending)                                                        |
| `complete_task` | Marks a task as completed by its ID         | `task_id` (int, **required**)                                                                               |
| `delete_task`   | Permanently deletes a task by its ID        | `task_id` (int, **required**)                                                                               |

## Gmail PIN Flow

1. During registration, the user receives a 4-digit Gmail PIN on the pin-reveal page.
2. When the user asks to send an email, the LLM detects this intent.
3. The LLM **must** call `verify_gmail_pin` with the user's PIN before calling `send_email`.
4. If the PIN is incorrect, the LLM asks the user to try again.
5. Once verified, the session remains authorized for subsequent sends (until the agent is reset).

The system prompt instructs the LLM about this requirement (rule #7).

## Language Switching

The `switch_language` tool allows changing the UI and TTS language between Hindi and English. When switching to Hindi, the agent responds in Devanagari script while keeping technical content (emails, PINs, URLs) in original form.

| Language | Value | Output |
|----------|-------|--------|
| Hindi    | `hi`  | Devanagari script UI and TTS |
| English  | `en`  | English UI and TTS |

## Navigation

When the `navigate` tool is called, the backend returns the URL prefixed with `NAVIGATE:` (e.g., `NAVIGATE:/dashboard#inbox`). The frontend JavaScript detects this and either:
- Switches the in-page tab (for hash-based pages like `#inbox`, `#profile`)
- Redirects to a different page (for `/admin`, `/login`, etc.)

## Cancellation / Interrupts

The user can cancel an in-progress action by:
- Saying "cancel", "stop", "never mind", or "abort" — the LLM is instructed (rule #9 in system prompt) to acknowledge and not proceed.
- Clicking the waveform area to interrupt TTS mid-speech.
- Speaking during TTS playback to auto-interrupt and send the new command.

The `logout` tool allows voice-based logout without clicking any buttons. It calls the `/voice-logout` endpoint internally.

## Adding a New Tool

1. Create the handler function in the appropriate file under `app/tools/`:
   ```python
   def my_tool_handler(user_email, param1, param2="default"):
       # user_email is always passed as the first argument
       return "Result string"
   ```

2. Register it with the registry:
   ```python
   from app.tools.registry import registry
   
   registry.register(
       name="my_tool",
       description="What this tool does (the LLM reads this to decide when to call it).",
       schema={
           "type": "object",
           "properties": {
               "param1": {"type": "string", "description": "What param1 is for"},
               "param2": {"type": "string", "description": "Optional param"},
           },
           "required": ["param1"],
       },
       handler=my_tool_handler,
   )
   ```

3. Make sure the tool module is imported in `app/tools/__init__.py`.

## Mock Services

The app supports granular mock flags so you can run any combination of real and fake services:

| `.env` flag          | Effect                                                                 |
| -------------------- | ---------------------------------------------------------------------- |
| `MOCK_SERVICES=true` | Shorthand — enables all three mocks below                              |
| `MOCK_EMAIL=true`    | Uses `MockEmailService` (in-memory inbox, no SMTP/IMAP needed)         |
| `MOCK_TELEGRAM=true` | Uses `MockTelegramState` (canned messages, no Telethon needed)         |
| `MOCK_LLM=true`      | Uses `MockAgent` (pattern-matched responses, no OpenRouter key needed) |

Granular flags take precedence over `MOCK_SERVICES`. The mock implementations live in `app/services/mocks/`. See [docs/testing-guide-mock.md](testing-guide-mock.md) for a full walkthrough.
