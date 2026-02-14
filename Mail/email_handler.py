import os, webbrowser, imaplib, email
from dotenv import load_dotenv

load_dotenv()

# loads the passowrd and email address
EMAIL_USER=os.getenv('EMAIL_USER')
EMAIL_PASS=os.getenv('EMAIL_PASS')

# to open a webpage to compose a new mail
def open_gmail_compose():
    # opens webpage
    webbrowser.open('https://mail.google.com/mail/u/0/?fs=1&tf=cm')

# open webpage and return the name of the top mail(sender)
def get_top_senders():
    webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
    try:
        # commecting to an email account
        mail=imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(EMAIL_USER,EMAIL_PASS)
        # selecting mailbox
        mail.select('inbox')

        # searching email
        result,data=mail.search(None,'All')
        mail_ids=data[0].split()

        # Check if inbox is empty
        if not mail_ids:
            mail.logout()
            return['Inbox is empty']
        
        latest_ids=mail_ids[-5:]
        senders=[]

        for mail_id in reversed(latest_ids):
            # fetching email content
            result,msg_data=mail.fetch(mail_id, "(RFC822)")
            raw_email=msg_data[0][1]
            msg=email.message_from_bytes(raw_email)
            senders.append(msg['From'])

            mail.logout()
            return senders
        
    except Exception as e:
        return [f'Error: {str(e)}']
    
__all__=['open_gmail_compose', 'get_top_senders']