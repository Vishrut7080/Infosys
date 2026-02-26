1. python main.py                 (Program starts)
2. Load environment variables     (From .env)
3. Enter while loop               (Infinite)
4. listen_text()                  (Wait for speech)
5. User: "hello"                  (Speech captured)
6. speak_text('[User]: hello')    (Echo to user)
7. Match greeting command         (Find in if-elif)
8. speak_text(greeting_response)  (Respond)
9. Loop back to step 4            (Continue)
10. User: "login"                 (Login command)
11. Start Flask thread            (Web server)
12. Open browser                  (Show login page)
13. User: "program"               (Confirmation)
14. Set login_status = "success"  (Authenticated)
15. Browser redirects to Gmail    (Login complete)
16. User: "send mail"             (Email command)
17. Check login_status            (Verify authenticated)
18. Confirm with user             (Ask yes/no)
19. open_gmail_compose()          (Open Gmail)
20. User: "logout"                (Logout command)
21. Reset login_status            (Clear auth)
22. User: "bye"                   (Exit command)
23. Break loop                    (End program)
24. file.close()                  (Clean up)

# ========================
# NEW WORK
# ========================

1.  python main.py                        (Program starts)
2.  Load environment variables            (From .env)
3.  Open Transcribe.txt                   (For logging)
4.  Enter while loop                      (Infinite)

-- TYPING PAUSE CHECK --
5.  web_login.user_typing == True?        (Browser keypress detected)
6.  Set typing_pause_until = now + 20s    (Pause audio for 20 seconds)
7.  Skip listen_text() for 20s           (Wait out the pause)

-- OAUTH CHECK (top of loop) --
8.  login_initiated AND status=="success"?(OAuth completed between recordings)
9.  Reset login_initiated = False         (Clear flag)
10. Continue to next iteration            (Skip recording)

-- AUDIO RECORDING --
11. listen_text()                         (Record 5 seconds)
12. Transcribe audio → heard             (Faster Whisper)

-- OAUTH CHECK (after recording) --
13. login_initiated AND status=="success"?(OAuth completed DURING recording)
14. Reset login_initiated = False         (Discard recorded audio)
15. Continue to next iteration            (Skip processing)

-- COMMAND PROCESSING --
16. speak_text('[User]: heard')           (Echo transcription)
17. clean_heard = heard.lower().strip()   (Normalize)
18. Write to Transcribe.txt              (Log command)

-- GREETING --
19. "hi/hello/hey" in clean_heard?        (Match greeting)
20. speak_text('Hi, what can I do?')      (Respond)

-- LOGIN --
21. "login" in clean_heard?               (Match login)
22. Already logged in? → say so           (Guard)
23. Start Flask server thread             (Web server)
24. webbrowser.open(localhost:5000)       (Show login page)
25. speak_text('Login page opened...')    (Instruct user)

-- AUDIO PASSWORD --
26. login_initiated AND word in           (Confirmation word heard)
    confirmation_words?
27. verify_audio() against database       (Check audio password)
28. Match? → login_status = "success"     (Authenticated)
29. No match? → check SECRET_AUD env      (Admin fallback)
30. Still no match? → login cancelled     (Failed)

-- BROWSER/KEYBOARD LOGIN --
31. User types credentials in browser     (Keyboard login)
32. POST /login → verify_user()           (Check database)
33. login_status = "success"              (Authenticated)
34. login.js polls /check → "success"     (JS detects login)
35. Redirect to /auth/google              (Start OAuth)
36. Google consent screen                 (User approves)
37. /auth/google/callback                 (Token exchange)
38. speak_text('Welcome Name')            (Greet user)
39. Redirect to Gmail inbox               (Login complete)

-- SIGNUP --
40. "signup/register" in clean_heard?     (Match signup)
41. Open localhost:5000/signup            (Show signup page)
42. User fills form → POST /register      (Submit)
43. create_user() → hash + store          (Save to SQLite)
44. Redirect to login page                (Registration done)

-- LOGIN CANCELLATION --
45. login_initiated AND status!="success"?(Any other word heard)
46. login_status = "failed"               (Cancel login)
47. speak_text('Login cancelled')         (Inform user)

-- MAIL FEATURES (requires login) --
48. Not logged in + mail command?         (Guard)
49. speak_text('Please log in first')     (Reject)

-- SEND MAIL --
50. "send mail/email" in clean_heard?     (Match send)
51. Confirm with user (yes/no)            (Ask)
52. compose_email_by_voice()              (Voice compose)
53. Collect: recipient → subject → body   (5 steps)
54. spoken_to_email() → fix address       (Parse email)
55. Confirm before sending                (Read back)
56. send_email() via SMTP port 465        (Send)

-- CHECK INBOX --
57. "check inbox/mail" in clean_heard?    (Match inbox)
58. Confirm with user (yes/no)            (Ask)
59. get_top_senders() via IMAP            (Fetch 5 emails)
60. extract_body() → strip_html()         (Parse body)
61. summarize_body() via Sumy LSA         (Summarize)
62. speak_text(sender+subject+summary)    (Read each email)

-- OTHER FEATURES --
63. "time" in clean_heard?                (Match time)
64. speak_text(current time)              (Respond)
65. "date/day" in clean_heard?            (Match date)
66. speak_text(current date)              (Respond)
67. "joke/funny" in clean_heard?          (Match joke)
68. speak_text(random joke)               (Respond)
69. Math keywords in clean_heard?         (Match calculator)
70. parse_math() → eval() → result        (Calculate)
71. speak_text(answer)                    (Respond)

-- LOGOUT --
72. "logout/sign out" in clean_heard?     (Match logout)
73. login_status = "waiting"              (Clear auth)
74. speak_text('Logged out')              (Confirm)

-- EXIT --
75. "bye/goodbye/exit" in clean_heard?    (Match exit)
76. speak_text('Goodbye')                 (Farewell)
77. Break while loop                      (End program)
78. file.close()                          (Clean up)