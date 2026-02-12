import os, webbrowser, imaplib, email
from dotenv import load_dotenv

load_dotenv()

EMAIL_USER=os.getenv('EMAIL_USER')
EMAIL_PASS=os.getenv('EMAIL_PASS')

def open_gmail_compose():
    webbrowser.open('https://mail.google.com/mail/u/0/?fs=1&tf=cm')

def get_top_senders():
    webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
    try:
        mail=imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(EMAIL_USER,EMAIL_PASS)
        mail.select('inbox')

        results,data=mail.search(None,'All')
        mail_ids=data[0].split()
        latest_ids=mail.ids[-5:]

        senders=[]

        for i in reversed(latest_ids):
            result,msg_data=mail.fetch(i, "(RFC822)")
            raw_email=msg_data[0][1]
            msg=email.message_from_bytes(raw_email)
            senders.append(msg['From'])

            mail.logout()
            return senders
        
    except Exception as e:
        return [f'Error: {str(e)}']
    
__all__=['open_gmail_compose', 'get_top_senders']