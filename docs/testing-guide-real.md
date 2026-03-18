# Testing Guide — Real Services

This guide walks through testing the assistant with real Gmail and Telegram credentials.  
Before following this guide, complete the setup steps in [docs/setup.md](setup.md).

---

## Prerequisites

### 1. Get an OpenRouter API key

Sign up at [openrouter.ai](https://openrouter.ai) and copy your API key.

### 2. Google OAuth (sign in with Google, optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → New Project
2. APIs & Services → OAuth consent screen → External → fill required fields
3. Credentials → Create OAuth 2.0 Client ID → Web Application
4. Authorised redirect URIs: `http://localhost:5000/auth/google/callback`
5. Copy `Client ID` and `Client Secret`

### 3. Gmail App Password (for email sending/reading)

> Standard Google account passwords do **not** work. You need an App Password.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable 2-Step Verification if not already on
3. Search "App passwords" → Select app: Mail, device: Other → name it "Assistant"
4. Copy the 16-character password (shown once)

### 4. Telegram API Credentials

1. Go to [my.telegram.org/auth](https://my.telegram.org/auth) and log in
2. Go to "API development tools"
3. Create a new application — note the **API ID** (a number) and **API Hash** (a hex string)
4. Use the phone number registered with your Telegram account (in international format, e.g. `+15550001234`)

---

## Configure `.env`

```env
# Flask
FLASK_SECRET_KEY=pick-a-long-random-string
FLASK_ENV=development

# Database
DATABASE_DIR=./Database

# OpenRouter (required for real LLM)
OPEN_ROUTER_API_key=sk-or-...
OPENROUTER_MODEL=google/gemini-2.0-flash-exp:free

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Real services — leave these unset (or False/0) to use real backends
MOCK_EMAIL=false
MOCK_TELEGRAM=false
MOCK_LLM=false
```

Do **not** set `MOCK_EMAIL`, `MOCK_TELEGRAM`, or `MOCK_LLM` to `true` when testing real services.

---

## Seed the Database

```bash
uv run seed_db.py
```

This creates Alice, Bob, and Carol with placeholder Gmail/Telegram credentials.  
For real testing, register a **new** account with your actual credentials through the UI.

---

## 1. Sign Up with Real Credentials

1. Open `http://localhost:5000/signup`
2. Fill in your name, email, and a password
3. After submitting, the **pin reveal page** shows:
   - Your generated audio password (write it down — this is your voice login phrase)
   - Your Gmail PIN and Telegram PIN (write these down — needed to authorise sending)
4. Click "Continue to Dashboard" or return to login

These PINs are stored in the database. They are only shown once at registration.

---

## 2. Voice Login

| What to do                                            | Expected result                                            |
| ----------------------------------------------------- | ---------------------------------------------------------- |
| Go to `http://localhost:5000`                         | "Listening for your audio password…" shown after ~1 second |
| **Say your audio password phrase** (shown at sign-up) | Logged in automatically                                    |
| Say a wrong phrase                                    | "Audio password not recognised" error                      |

---

## 3. Sign In with Google

| What to do                   | Expected result                                 |
| ---------------------------- | ----------------------------------------------- |
| Click "Continue with Google" | Redirected to Google OAuth consent screen       |
| Choose your Google account   | Redirected back and logged into dashboard       |
| If account not registered    | Error: "This Google account is not registered." |

> Google OAuth uses your email as the identifier. Register with the same email as your Google account if you want both login methods to map to the same user.

---

## 4. Email — Read (Real Gmail IMAP)

Open the Voice Assistant on the dashboard.

| Voice command                     | Expected result                             |
| --------------------------------- | ------------------------------------------- |
| "Check my emails"                 | Fetches real emails from your Gmail IMAP    |
| "Give me an overview of my inbox" | Summary: total, unread, top senders         |
| "Show important emails"           | Emails categorised as important             |
| "Read email 1"                    | Full body of the most recent email          |
| "Search emails for invoice"       | Gmail IMAP search for "invoice" in subjects |

**Note:** The first call may be slow while the IMAP connection is established.

---

## 5. Email — Send (Real Gmail SMTP)

Sending requires Gmail PIN authorisation every session.

| Step | What to do                                                                | Expected                                                              |
| ---- | ------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| 1    | Say "Send an email"                                                       | Agent asks: "Who should I send it to? Please provide your Gmail PIN." |
| 2    | Say "My PIN is XXXX" (use your Gmail PIN from sign-up)                    | "Gmail PIN verified."                                                 |
| 3    | Say "Send to test@example.com, subject Hello, body Testing the assistant" | Gmail SMTP sends the email; "Email sent."                             |

Check your Gmail Sent folder to confirm delivery.

---

## 6. Telegram — Read (Real Telethon)

> The first time Telegram tools are called, Telethon initiates an authentication session. This requires confirming a code sent to your Telegram app.

| Voice command                           | Expected result                                |
| --------------------------------------- | ---------------------------------------------- |
| "Check my Telegram messages"            | Authenticates and fetches real recent messages |
| "Show conversation with [Contact Name]" | Full message thread with that contact          |

**First-time authentication:**  
If your session isn't saved, Telethon will prompt for a confirmation code via your Telegram app. This is a one-time step per device.

---

## 7. Telegram — Send (Real Telethon)

Sending requires Telegram PIN authorisation every session.

| Step | What to do                                                 | Expected                                                                 |
| ---- | ---------------------------------------------------------- | ------------------------------------------------------------------------ |
| 1    | Say "Send a Telegram message"                              | Agent asks: "Who should I send it to? Please provide your Telegram PIN." |
| 2    | Say "My PIN is XXXX" (your Telegram PIN from sign-up)      | "Telegram PIN verified."                                                 |
| 3    | Say "Send to [Contact Name], message Hello from assistant" | Message sent via Telethon; "Message sent."                               |

Check your Telegram app to confirm delivery.

---

## 8. Task Management

Tasks use the local SQLite database regardless of `MOCK_EMAIL`/`MOCK_TELEGRAM` settings.

| Voice command                        | Expected result                      |
| ------------------------------------ | ------------------------------------ |
| "Add a task: review pull request 42" | "Task added: Review pull request 42" |
| "List my tasks"                      | All pending tasks with IDs           |
| "Complete task 1"                    | "Task 1 marked as done."             |
| "Delete task 2"                      | "Task 2 deleted."                    |

---

## 9. System Tools

These work without any external credentials.

| Voice command                | Expected result                  |
| ---------------------------- | -------------------------------- |
| "What time is it?"           | Current system time              |
| "What is 144 divided by 12?" | "12"                             |
| "Tell me a joke"             | A programmer joke                |
| "What is the system info?"   | OS, Python version, architecture |

---

## 10. Admin Panel

Log in as a user with the Admin role (add admin via `seed_db.py` or the admin panel).

| What to do           | Expected result                           |
| -------------------- | ----------------------------------------- |
| Navigate to `/admin` | User table, activity log                  |
| Add a user as admin  | That user can access `/admin`             |
| View activity log    | Real login and command events from the DB |

---

## PIN Verification Flows

### Gmail PIN

- Shown once at sign-up on the pin-reveal page
- Stored hashed in the `pins` table in `users.db`
- Called via the `verify_gmail_pin` agent tool before `send_email`
- Once verified per session, subsequent send_email calls don't re-prompt

### Telegram PIN

- Shown once at sign-up if Telegram credentials were provided
- Same hashed storage and session-level persistence
- Called via `verify_telegram_pin` before `send_telegram`

If you lose your PIN, delete the user and re-register, or reset it directly in the SQLite DB.

---

## Common Issues

| Symptom                                  | Fix                                                                                                                              |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Gmail IMAP fails with auth error         | Ensure 2FA is on and you're using an App Password, not your account password                                                     |
| Gmail sends but the email doesn't arrive | Check Gmail Sent folder; verify `gmail_address` and `gmail_app_pass` in the DB match your account                                |
| Telegram "phone number not registered"   | Ensure the phone number in your `.env`/account matches your active Telegram account                                              |
| Telethon asks for a confirmation code    | Enter the code from your Telegram app — this is a one-time device authorisation                                                  |
| OpenRouter rate limit / 429 error        | The free model has rate limits; wait a few seconds and retry, or switch to a paid model in `OPENROUTER_MODEL`                    |
| PINs lost after re-seed                  | `seed_db.py` skips existing users; PINs are only shown on first creation. Delete `./Database/users.db` and re-seed to regenerate |
