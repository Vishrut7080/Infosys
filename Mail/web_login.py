from flask import Flask, render_template, jsonify,  url_for, redirect

app = Flask(__name__)

login_status = False

@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/check')
def check_login():
    global login_status
    
    if login_status == "success":
        return redirect("https://mail.google.com")
    
    elif login_status == "failed":
        return "Login failed", 403
    
    return "Waiting for voice confirmation..."

def start_server():
    app.run(port=5000)
