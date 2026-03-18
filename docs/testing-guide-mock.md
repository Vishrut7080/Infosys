# Testing Guide — Mock Mode

This guide walks through every feature of the assistant using fully mocked services.
No real Gmail credentials or Telegram account are required.

## Prerequisites

1. **Seed the database** (safe to run multiple times — skips existing users):

   ```bash
   uv run seed_db.py
   ```

   Take note of the PINs printed in the output, e.g.:

   ```
   [seed] Store PINs for alice@example.com: True - PINs stored
          Gmail PIN: 4821
          Telegram PIN: 7563
   ```

   Save these — you will need them when testing email/Telegram sending.

2. **Configure `.env`** — only these keys are needed for full mock mode:

   ```env
   FLASK_SECRET_KEY=any-dev-secret
   MOCK_LLM=true
   MOCK_EMAIL=true
   MOCK_TELEGRAM=true
   ```

   With `MOCK_LLM=true`, no OpenRouter API key is required.

3. **Start the server**:

   ```bash
   uv run python main.py
   ```

   Open `http://localhost:5000`.

---

## Test Users

| Name         | Email             | Password    | Audio Password | Role  |
| ------------ | ----------------- | ----------- | -------------- | ----- |
| Alice Admin  | alice@example.com | password123 | open sesame    | Admin |
| Bob User     | bob@example.com   | password123 | hello bob      | User  |
| Carol Tester | carol@example.com | password123 | _(none)_       | User  |

---

## 1. Auto Voice Login

The page automatically starts listening ~1 second after load. No button press needed.

| What to do                                      | Expected result                                                       |
| ----------------------------------------------- | --------------------------------------------------------------------- |
| Open `http://localhost:5000`                    | Message shows "Listening for your audio password…"; mic button pulses |
| **Say "open sesame"**                           | "Welcome back, Alice! Loading…" → redirected to dashboard             |
| Reload the page; **say "hello bob"**            | Logs in as Bob                                                        |
| Reload the page; **click into the email field** | Voice recognition pauses (stop animation)                             |
| Click away from all fields (blur with no text)  | Voice recognition resumes automatically                               |
| **Click the mic button** while it's listening   | Stops listening (manual pause)                                        |
| **Click the mic button** while stopped          | Restarts listening                                                    |
| Try an unrecognised phrase (e.g. "banana")      | "Audio password not recognised" error in red                          |

**Fallback:** The standard email + password form always works alongside voice.

---

## 2. Standard (Keyboard) Login

| What to do                                               | Expected result                         |
| -------------------------------------------------------- | --------------------------------------- |
| Enter `alice@example.com` + `password123`, click Sign In | Redirected to dashboard                 |
| Enter wrong password                                     | Red error message "Invalid credentials" |
| Click the eye icon                                       | Toggles password visibility             |

---

## 3. Sign Up (new user flow)

| What to do                                  | Expected result                                                      |
| ------------------------------------------- | -------------------------------------------------------------------- |
| Go to `http://localhost:5000/signup`        | Sign-up form                                                         |
| Fill name, email, password, submit          | Redirected to `/pin_reveal` with a randomly generated audio password |
| Note the audio password shown               | Use this phrase to voice-login later                                 |
| Return to login; **say the audio password** | Logged in as the new user                                            |

---

## 4. Dashboard Navigation

Once logged in as Alice, the dashboard should load.

| Voice command to say | Expected result                          |
| -------------------- | ---------------------------------------- |
| "Show my inbox"      | Navigates to the inbox tab               |
| "Go to profile"      | Navigates to the profile tab             |
| "Open tasks"         | Navigates to the tasks page              |
| "Go to dashboard"    | Navigates back to the main dashboard tab |

---

## 5. Agent — Capabilities

| Voice command        | Expected result                                                                |
| -------------------- | ------------------------------------------------------------------------------ |
| "What can you do?"   | Agent lists all capabilities: email, Telegram, tasks, system tools, navigation |
| "Help"               | Same capabilities list                                                         |
| "What are you?"      | Same capabilities list                                                         |
| "Introduce yourself" | Same capabilities list                                                         |

---

## 6. Email Tools (Mock)

All email operations hit the mock service — no real Gmail needed.

### Read emails

| Voice command                           | Expected result                                 |
| --------------------------------------- | ----------------------------------------------- |
| "Check my emails"                       | Lists 5 mock emails (sender, subject)           |
| "Give me an overview of my inbox"       | Summary: total count, unread count, top senders |
| "Show me important emails"              | Lists emails flagged as important               |
| "Read email 1" / "Open the first email" | Full body of email #1                           |
| "Search emails for meeting"             | Returns mock emails matching "meeting"          |
| "Search emails for invoice"             | Returns mock emails matching "invoice"          |

### Send email

| Step | What to do                                                     | Expected                             |
| ---- | -------------------------------------------------------------- | ------------------------------------ |
| 1    | Say "Send an email"                                            | Agent asks for recipient + Gmail PIN |
| 2    | Say your Gmail PIN (from `seed_db.py` output)                  | "PIN verified."                      |
| 3    | Say "Send to test@example.com, subject Test, body Hello world" | "Email sent."                        |

---

## 7. Telegram Tools (Mock)

All Telegram operations hit the mock service.

### Read messages

| Voice command                       | Expected result                               |
| ----------------------------------- | --------------------------------------------- |
| "Check my Telegram messages"        | Latest 5 mock messages                        |
| "Show conversation with Mock-Alice" | Full mock conversation thread with Mock-Alice |
| "Show conversation with Mock-Bob"   | Full mock conversation thread with Mock-Bob   |

### Send message

| Step | What to do                                       | Expected                              |
| ---- | ------------------------------------------------ | ------------------------------------- |
| 1    | Say "Send a Telegram message"                    | Agent asks for contact + Telegram PIN |
| 2    | Say your Telegram PIN (from `seed_db.py` output) | "PIN verified."                       |
| 3    | Say "Send to Mock-Alice, message Hello there"    | "Message sent."                       |

---

## 8. Task Management

Tasks are stored in the real SQLite database even in mock mode.

| Voice command                     | Expected result                   |
| --------------------------------- | --------------------------------- |
| "Add a task: buy groceries"       | "Task added: Buy groceries"       |
| "Add a task: review pull request" | "Task added: Review pull request" |
| "Show my tasks"                   | Lists all pending tasks with IDs  |
| "Show all tasks"                  | Lists pending + completed tasks   |
| "Complete task 1"                 | "Task 1 marked as done."          |
| "Delete task 2"                   | "Task 2 deleted."                 |
| "Show pending tasks"              | Lists only incomplete tasks       |

You can also use the **Tasks** page in the dashboard directly — add tasks via the text box, tick to complete, click × to delete.

---

## 9. System Tools

| Voice command                              | Expected result                       |
| ------------------------------------------ | ------------------------------------- |
| "What time is it?"                         | Current time in 12-hour format        |
| "What's today's date?"                     | Current date with weekday             |
| "Tell me a joke"                           | A random programmer joke              |
| "What is 42 times 18?"                     | "756" (uses `calculate` tool)         |
| "Give me a random number between 1 and 10" | A random integer                      |
| "Show my profile"                          | Your name, email, and role            |
| "What is the system info?"                 | OS name, Python version, machine arch |

---

## 10. Navigation by Voice

| Voice command             | Expected result         |
| ------------------------- | ----------------------- |
| "Navigate to admin"       | Redirected to `/admin`  |
| "Open the login page"     | Redirected to `/`       |
| "Show me the signup page" | Redirected to `/signup` |

---

## 11. Admin Panel (Alice only)

Log in as `alice@example.com` (she has the Admin role).

| What to do          | Expected result                                 |
| ------------------- | ----------------------------------------------- |
| Go to `/admin`      | Admin dashboard with user list                  |
| Click a user row    | Expand user details (email, role, created date) |
| Click "Impersonate" | Log in as that user                             |
| Click "Delete"      | Delete that user (confirmation required)        |
| View activity log   | Shows login/command events from seed data       |

---

## 12. UI / Multi-language

| What to do                                      | Expected result             |
| ----------------------------------------------- | --------------------------- |
| Click "🇮🇳 हिंदी" button                             | UI switches to Hindi labels |
| Click "🇺🇸 English"                               | UI switches back to English |
| Open voice assistant and say a command in Hindi | LLM responds (mock or real) |

---

## 13. Cancellation

| Voice command                          | Expected result              |
| -------------------------------------- | ---------------------------- |
| Start sending email, then say "cancel" | Agent acknowledges and stops |
| Say "never mind" at any point          | Current action aborted       |
| Say "stop" during TTS playback         | Speech stops immediately     |

---

## Common Issues

| Symptom                         | Fix                                                                                            |
| ------------------------------- | ---------------------------------------------------------------------------------------------- |
| Mic doesn't auto-start          | Browser may request mic permission on first load — allow it; page will auto-restart            |
| "Microphone error: not-allowed" | Grant mic permission in browser settings, then reload                                          |
| PIN not working                 | Re-run `uv run seed_db.py` and check the printed PINs — they're random each time for new users |
| Tasks not showing               | Check you are logged in (tasks are per-user in the DB)                                         |
