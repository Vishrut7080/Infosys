from flask import Flask, render_template, jsonify,  url_for, redirect

app = Flask(__name__)

login_status = 'waiting'

@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/check')
def check_login():
    global login_status
    print('Flask sees:', login_status) #debug
    return login_status
    
def start_server():
    print("Flask server starting...")
    app.run(port=5000, use_reloader=False)
