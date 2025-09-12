import os
import asyncio
from flask import Flask, request, abort, render_template_string, send_from_directory
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# ثابت‌ها
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "changeme")  # اینو تو Render ست کن

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

app = Flask(__name__)
pending = {}

def check_token(req):
    token = req.args.get("token") or req.form.get("token") or req.headers.get("X-ADMIN-TOKEN")
    return token and token == ADMIN_TOKEN

def run_async(coro):
    return asyncio.run(coro)

async def _send_code(phone, session_path):
    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()
    sent = await client.send_code_request(phone)
    await client.disconnect()
    return sent.phone_code_hash

async def _sign_in(phone, session_path, code):
    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()
    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        await client.disconnect()
        return {"2fa": True}
    session_str = client.session.save()
    await client.disconnect()
    return {"ok": True, "session": session_str}

async def _complete_2fa(session_path, password):
    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()
    await client.sign_in(password=password)
    session_str = client.session.save()
    await client.disconnect()
    return {"ok": True, "session": session_str}

HOME = """
<h2>Render Session Creator</h2>
<p><a href="/start?token={{token}}">Start new session</a></p>
"""

START = """
<h2>Enter phone number</h2>
<form method="post">
<input type="hidden" name="token" value="{{token}}"/>
Phone: <input name="phone" placeholder="+98912..." required/>
<button type="submit">Send Code</button>
</form>
"""

VERIFY = """
<h2>Enter code for {{phone}}</h2>
<form method="post" action="/verify">
<input type="hidden" name="token" value="{{token}}"/>
<input type="hidden" name="session" value="{{session}}"/>
Code: <input name="code" required/>
<button type="submit">Verify</button>
</form>
"""

PASS = """
<h2>Enter 2FA password for {{phone}}</h2>
<form method="post" action="/2fa">
<input type="hidden" name="token" value="{{token}}"/>
<input type="hidden" name="session" value="{{session}}"/>
Password: <input type="password" name="password" required/>
<button type="submit">Submit</button>
</form>
"""

SUCCESS = """
<h2>Session created!</h2>
<p>File: {{filename}}</p>
<a href="/download/{{filename}}?token={{token}}">Download session</a>
"""

@app.route("/")
def home():
    if not check_token(request):
        return abort(403)
    return render_template_string(HOME, token=ADMIN_TOKEN)

@app.route("/start", methods=["GET","POST"])
def start():
    if not check_token(request):
        return abort(403)
    if request.method=="GET":
        return render_template_string(START, token=ADMIN_TOKEN)
    phone = request.form["phone"].strip()
    session_name = phone.replace("+","").replace(" ","")
    session_path = os.path.join(SESSIONS_DIR, session_name)
    code_hash = run_async(_send_code(phone, session_path))
    pending[session_name] = {"phone": phone, "hash": code_hash}
    return render_template_string(VERIFY, phone=phone, session=session_name, token=ADMIN_TOKEN)

@app.route("/verify", methods=["POST"])
def verify():
    if not check_token(request):
        return abort(403)
    session_name = request.form["session"]
    code = request.form["code"].strip()
    phone = pending[session_name]["phone"]
    session_path = os.path.join(SESSIONS_DIR, session_name)
    res = run_async(_sign_in(phone, session_path, code))
    if "2fa" in res:
        return render_template_string(PASS, phone=phone, session=session_name, token=ADMIN_TOKEN)
    filename = session_name+".session"
    return render_template_string(SUCCESS, filename=filename, token=ADMIN_TOKEN)

@app.route("/2fa", methods=["POST"])
def twofa():
    if not check_token(request):
        return abort(403)
    session_name = request.form["session"]
    pwd = request.form["password"]
    session_path = os.path.join(SESSIONS_DIR, session_name)
    run_async(_complete_2fa(session_path, pwd))
    filename = session_name+".session"
    return render_template_string(SUCCESS, filename=filename, token=ADMIN_TOKEN)

@app.route("/download/<filename>")
def download(filename):
    if not check_token(request):
        return abort(403)
    return send_from_directory(SESSIONS_DIR, filename, as_attachment=True)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
