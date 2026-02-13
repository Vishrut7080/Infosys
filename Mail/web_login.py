from flask import Flask, render_template, jsonify

app = Flask(__name__)

login_success = False

@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/check')
def check_login():
    global login_success
    return jsonify({"success": login_success})

def start_server():
    app.run(port=5000)
