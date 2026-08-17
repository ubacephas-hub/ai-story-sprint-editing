#!/usr/bin/env python3
"""AI StorySprint Editing — dependency-free full-stack course platform."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from http.cookies import SimpleCookie
from email.parser import BytesParser
from email.policy import default
import sqlite3, os, re, json, secrets, hashlib, hmac, html, mimetypes, time, datetime, traceback

ROOT=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(ROOT,"storysprint.db")
UPLOADS=os.path.join(ROOT,"uploads")
os.makedirs(UPLOADS,exist_ok=True)
HOST=os.getenv("HOST","0.0.0.0"); PORT=int(os.getenv("PORT","8000"))
APP_NAME="AI StorySprint Editing"

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def esc(x): return html.escape(str(x or ""),quote=True)
def slug(s): return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-") or secrets.token_hex(4)
def pw_hash(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    key=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,240000)
    return salt.hex()+":"+key.hex()
def pw_check(password,stored):
    try:
        s,k=stored.split(":"); return hmac.compare_digest(pw_hash(password,bytes.fromhex(s)).split(":")[1],k)
    except: return False

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c

def init_db():
    c=db(); c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL COLLATE NOCASE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student' CHECK(role IN('admin','student')), account_status TEXT NOT NULL DEFAULT 'active' CHECK(account_status IN('active','disabled')), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT, slug TEXT UNIQUE NOT NULL, published INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS modules(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, title TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, module_id INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE, title TEXT NOT NULL, description TEXT, position INTEGER NOT NULL DEFAULT 0, video_kind TEXT NOT NULL DEFAULT 'none', video_source TEXT, video_mime TEXT);
    CREATE TABLE IF NOT EXISTS resources(id INTEGER PRIMARY KEY, lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, type TEXT NOT NULL CHECK(type IN('link','text','document')), title TEXT NOT NULL, url TEXT, content TEXT, file_path TEXT, description TEXT, position INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS course_access(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','active','suspended')), created_at TEXT NOT NULL, UNIQUE(user_id,course_id));
    CREATE TABLE IF NOT EXISTS lesson_progress(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'in_progress' CHECK(status IN('in_progress','completed')), updated_at TEXT NOT NULL, completed_at TEXT, UNIQUE(user_id,lesson_id));
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, csrf TEXT NOT NULL, expires_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS password_resets(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
    """)
    if not c.execute("SELECT 1 FROM courses").fetchone():
        c.execute("INSERT INTO courses(title,description,slug,created_at) VALUES(?,?,?,?)",(APP_NAME,"Master the AI StorySprint editing workflow.","ai-storysprint-editing",now()))
        cid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
        structure=[("Tools & Glossary",["Tools & Glossary"]),("Laptop Version",["Prompt Generation","Image Generation","Importing & Editing"]),("Phone Version",["Prompt Generation","Image Generation","Importing & Editing"]),("Prompt Adjustment",["Prompt Adjustment"])]
        n=1
        for mp,(mt,ls) in enumerate(structure,1):
            c.execute("INSERT INTO modules(course_id,title,position) VALUES(?,?,?)",(cid,mt,mp)); mid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
            for lp,lt in enumerate(ls,1):
                c.execute("INSERT INTO lessons(module_id,title,description,position) VALUES(?,?,?,?)",(mid,lt,f"Lesson {n}: {lt}. Add your lesson description from the admin dashboard.",lp)); n+=1
    if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",("Course Administrator","admin@storysprint.local",pw_hash("Admin123!"),"admin",now()))
    if not c.execute("SELECT 1 FROM users WHERE email='student@storysprint.local'").fetchone():
        c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",("Demo Student","student@storysprint.local",pw_hash("Student123!"),"student",now())); uid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
        cid=c.execute("SELECT id FROM courses LIMIT 1").fetchone()[0]
        c.execute("INSERT INTO course_access(user_id,course_id,status,created_at) VALUES(?,?,?,?)",(uid,cid,"active",now()))
    c.commit(); c.close()

CSS="""
:root{--ink:#151b2b;--muted:#667085;--line:#e4e7ec;--bg:#f7f8fa;--card:#fff;--brand:#5b4bdb;--brand2:#4338ca;--ok:#138a5b;--warn:#b54708;--danger:#b42318}*{box-sizing:border-box}body{margin:0;font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);background:var(--bg)}a{color:var(--brand);text-decoration:none}h1,h2,h3{line-height:1.2;margin:0 0 12px}h1{font-size:clamp(28px,5vw,46px)}h2{font-size:24px}h3{font-size:18px}.container{width:min(1080px,calc(100% - 32px));margin:auto}.topbar{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:4}.nav{min-height:66px;display:flex;align-items:center;gap:20px}.brand{font-weight:800;color:var(--ink);margin-right:auto}.navlinks{display:flex;gap:8px;align-items:center}.navlinks a{padding:10px 12px;color:var(--muted);font-weight:650;border-radius:9px}.navlinks a:hover{background:var(--bg);color:var(--ink)}main{padding:34px 0 70px}.hero{min-height:70vh;display:grid;place-items:center;text-align:center}.hero-inner{max-width:700px}.eyebrow{color:var(--brand);font-weight:800;text-transform:uppercase;letter-spacing:.08em;font-size:12px}.lead{font-size:19px;color:var(--muted)}.actions{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0;justify-content:center}.btn{display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:10px 18px;border:0;border-radius:10px;font:inherit;font-weight:750;cursor:pointer;background:var(--brand);color:white}.btn:hover{background:var(--brand2)}.btn.secondary{background:#fff;color:var(--ink);border:1px solid var(--line)}.btn.danger{background:var(--danger)}.btn.small{min-height:36px;padding:7px 11px;font-size:13px}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:42px}.summary div,.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px}.summary strong{display:block;font-size:20px}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}.stack{display:grid;gap:16px}.progress{height:12px;border-radius:20px;background:#e8e7fb;overflow:hidden}.progress i{height:100%;display:block;background:var(--brand);border-radius:inherit}.module-head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}.lesson-list{list-style:none;padding:0;margin:14px 0 0}.lesson-list li{border-top:1px solid var(--line)}.lesson-list a{padding:14px 2px;display:flex;gap:12px;color:var(--ink);align-items:center}.status-dot{width:22px;height:22px;border:2px solid #c7cbd4;border-radius:50%;display:inline-grid;place-items:center;flex:none;font-size:12px}.status-dot.done{background:var(--ok);border-color:var(--ok);color:#fff}.status-dot.going{border-color:var(--brand);background:#eceafe}.badge{font-size:12px;font-weight:750;padding:4px 8px;border-radius:20px;background:#eef0f3;color:#596273}.badge.active,.badge.completed{background:#e7f6ef;color:var(--ok)}.badge.pending,.badge.in_progress{background:#fff3e7;color:var(--warn)}.badge.suspended,.badge.disabled{background:#feeceb;color:var(--danger)}.video{aspect-ratio:16/9;background:#101322;border-radius:14px;overflow:hidden;display:grid;place-items:center;color:#d0d5dd}.video video{width:100%;height:100%;background:#000}.lesson-nav{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.resource-text{white-space:pre-wrap;background:#fafafa;padding:14px;border-radius:10px}.form-card{max-width:560px;margin:auto}.field{display:grid;gap:6px;margin:0 0 16px}.field label{font-weight:700}.field input,.field textarea,.field select{width:100%;padding:12px 13px;border:1px solid #cfd4dc;border-radius:9px;background:white;font:inherit}.field textarea{min-height:110px;resize:vertical}.alert{padding:13px 16px;border-radius:10px;margin-bottom:16px;background:#eef0ff;color:#3730a3}.alert.error{background:#feeceb;color:#912018}.alert.ok{background:#e7f6ef;color:#087443}.admin-layout{display:grid;grid-template-columns:210px 1fr;gap:24px}.sidebar{background:#fff;border:1px solid var(--line);padding:12px;border-radius:14px;height:max-content;position:sticky;top:90px}.sidebar a{display:block;color:var(--muted);font-weight:700;padding:10px;border-radius:8px}.sidebar a:hover{background:var(--bg);color:var(--ink)}table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}th,td{text-align:left;padding:11px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;color:var(--muted)}.inline{display:inline}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.split{display:flex;justify-content:space-between;align-items:flex-start;gap:15px}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.kpi strong{display:block;font-size:28px}.empty{text-align:center;color:var(--muted);padding:32px}.footer{text-align:center;color:var(--muted);padding:25px}.mobile-only{display:none}@media(max-width:760px){.container{width:min(100% - 22px,1080px)}.summary,.kpis,.grid{grid-template-columns:1fr 1fr}.admin-layout{grid-template-columns:1fr}.sidebar{display:flex;overflow:auto;position:static}.sidebar a{white-space:nowrap}.navlinks a{display:none}.navlinks a.mobile-only{display:inline-flex}.mobile-only{display:block}main{padding-top:24px}table{display:block;overflow-x:auto}.lesson-nav .btn{flex:1}.summary div{padding:14px}}@media(max-width:440px){.summary,.kpis,.grid{grid-template-columns:1fr}.actions .btn{width:100%}.brand{font-size:14px}.card{padding:16px}}
"""

def layout(title,body,user=None,admin=False):
    if user:
        links=(f'<a href="/admin">Overview</a><a href="/admin/modules">Modules</a><a href="/admin/lessons">Lessons</a><a href="/admin/resources">Resources</a><a href="/admin/students">Students</a>' if user['role']=='admin' else '<a href="/dashboard">Dashboard</a><a href="/course">Course</a><a href="/account">Account</a>')
        nav=f'<nav class="nav container"><a class="brand" href="{("/admin" if user["role"]=="admin" else "/dashboard")}">{APP_NAME}</a><div class="navlinks">{links}<a class="mobile-only" href="/account">Menu</a></div></nav>'
    else: nav=f'<nav class="nav container"><a class="brand" href="/">{APP_NAME}</a><div class="navlinks"><a href="/login">Login</a><a href="/enroll">Enroll</a></div></nav>'
    sidebar=''
    if admin:
        sidebar='<aside class="sidebar"><a href="/admin">Overview</a><a href="/admin/modules">Modules</a><a href="/admin/lessons">Lessons</a><a href="/admin/videos">Videos</a><a href="/admin/resources">Resources</a><a href="/admin/students">Students</a><a href="/admin/settings">Settings</a></aside>'
        body=f'<div class="admin-layout">{sidebar}<section>{body}</section></div>'
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#5b4bdb"><title>{esc(title)} · {APP_NAME}</title><style>{CSS}</style></head><body><header class="topbar">{nav}</header><main><div class="container">{body}</div></main><footer class="footer">© {datetime.date.today().year} {APP_NAME}</footer></body></html>'

class App(BaseHTTPRequestHandler):
    server_version="StorySprint/1.0"
    def log_message(self,fmt,*args): print("%s %s"%(self.address_string(),fmt%args))
    def send_html(self,s,status=200,headers=None):
        b=s.encode(); self.send_response(status); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("X-Frame-Options","SAMEORIGIN"); self.send_header("Referrer-Policy","same-origin"); self.send_header("Cache-Control","no-store");
        for k,v in (headers or []): self.send_header(k,v)
        self.end_headers(); self.wfile.write(b)
    def redirect(self,url,cookie=None):
        self.send_response(303); self.send_header("Location",url)
        if cookie:self.send_header("Set-Cookie",cookie)
        self.end_headers()
    def parse_body(self):
        n=int(self.headers.get("Content-Length",0)); raw=self.rfile.read(n); ct=self.headers.get("Content-Type","")
        if "multipart/form-data" in ct:
            msg=BytesParser(policy=default).parsebytes(b"Content-Type: "+ct.encode()+b"\r\nMIME-Version: 1.0\r\n\r\n"+raw); out={}
            for p in msg.iter_parts():
                name=p.get_param("name",header="content-disposition"); fn=p.get_filename(); data=p.get_payload(decode=True)
                out[name]={"filename":fn,"data":data,"type":p.get_content_type()} if fn else data.decode(errors="replace")
            return out
        return {k:v[-1] for k,v in parse_qs(raw.decode(),keep_blank_values=True).items()}
    def session(self):
        ck=SimpleCookie(self.headers.get("Cookie")); token=ck.get("session")
        if not token:return None,None
        c=db(); r=c.execute("SELECT s.token,s.csrf,u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>? AND u.account_status='active'",(token.value,int(time.time()))).fetchone(); c.close(); return (r,token.value) if r else (None,None)
    def require(self,role=None):
        u,t=self.session()
        if not u:self.redirect("/login?error="+quote("Please log in to continue.")); return None
        if role and u["role"]!=role:self.send_html(layout("Unauthorized",'<div class="card empty"><h2>Access denied</h2><p>You are not authorized to view this page.</p></div>',u),403); return None
        return u
    def csrf_ok(self,u,data): return u and data.get("csrf") and hmac.compare_digest(str(data.get("csrf")),u["csrf"])
    def access(self,u):
        c=db(); r=c.execute("SELECT ca.*,c.title FROM course_access ca JOIN courses c ON c.id=ca.course_id WHERE ca.user_id=? ORDER BY ca.id LIMIT 1",(u["id"],)).fetchone(); c.close(); return r
    def do_HEAD(self):
        """Preview/deployment health checks commonly use HEAD."""
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
    def do_GET(self):
        try:self.route_get()
        except BrokenPipeError:pass
        except Exception:
            traceback.print_exc(); self.send_html(layout("Error",'<div class="alert error">Something went wrong. Please try again.</div>'),500)
    def do_POST(self):
        try:self.route_post()
        except Exception:
            traceback.print_exc(); self.send_html(layout("Error",'<div class="alert error">Something went wrong. Please try again.</div>'),500)
    def route_get(self):
        p=urlparse(self.path); path=p.path; q={k:v[-1] for k,v in parse_qs(p.query).items()}; u,_=self.session()
        if path=="/health":
            c=db(); counts=c.execute("SELECT (SELECT count(*) FROM modules),(SELECT count(*) FROM lessons),(SELECT count(*) FROM users)").fetchone(); c.close()
            payload=json.dumps({"status":"ok","database":"connected","modules":counts[0],"lessons":counts[1],"users":counts[2]}).encode()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(payload))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(payload); return
        if path=="/":
            body='<section class="hero"><div class="hero-inner"><div class="eyebrow">Online video course</div><h1>AI StorySprint Editing</h1><p class="lead">Master the AI StorySprint editing workflow.</p><div class="actions"><a class="btn" href="/enroll">Enroll Now</a><a class="btn secondary" href="/login">Login</a></div><div class="summary"><div><strong>4</strong>Modules</div><div><strong>8</strong>Video Lessons</div><div><strong>2</strong>Laptop + Phone Workflows</div><div><strong>✓</strong>Supporting Resources</div></div></div></section>'
            return self.send_html(layout("Home",body,u))
        if path in ("/login","/enroll","/forgot"):
            if u:return self.redirect("/admin" if u["role"]=="admin" else "/dashboard")
            err=f'<div class="alert error">{esc(q.get("error"))}</div>' if q.get("error") else ''
            ok=f'<div class="alert ok">{esc(q.get("ok"))}</div>' if q.get("ok") else ''
            if path=="/login": fields='<h2>Welcome back</h2><p class="muted">Log in to continue your course.</p><div class="field"><label>Email</label><input type="email" name="email" required autocomplete="email"></div><div class="field"><label>Password</label><input type="password" name="password" required autocomplete="current-password"></div><button class="btn">Login</button><p><a href="/forgot">Forgot your password?</a></p><p>New here? <a href="/enroll">Create an account</a></p>'
            elif path=="/enroll": fields='<h2>Enroll</h2><p class="muted">Create your student account. Access starts as pending until an administrator activates it.</p><div class="field"><label>Name</label><input name="name" required></div><div class="field"><label>Email</label><input type="email" name="email" required></div><div class="field"><label>Password</label><input type="password" name="password" minlength="8" required></div><button class="btn">Create account</button><p>Already registered? <a href="/login">Login</a></p>'
            else: fields='<h2>Reset password</h2><p class="muted">Enter your account email to create a one-time reset link.</p><div class="field"><label>Email</label><input type="email" name="email" required></div><button class="btn">Create reset link</button><p><a href="/login">Back to login</a></p>'
            return self.send_html(layout(path[1:].title(),f'<div class="card form-card">{err}{ok}<form method="post">{fields}</form></div>'))
        if path=="/reset":
            token=q.get("token",""); c=db(); r=c.execute("SELECT * FROM password_resets WHERE token=? AND expires_at>? AND used=0",(token,int(time.time()))).fetchone(); c.close()
            if not r:return self.send_html(layout("Reset password",'<div class="card form-card"><div class="alert error">This reset link is invalid or expired.</div><a href="/forgot">Request another link</a></div>'),400)
            return self.send_html(layout("Reset password",f'<div class="card form-card"><h2>Choose a new password</h2><form method="post"><input type="hidden" name="token" value="{esc(token)}"><div class="field"><label>New password</label><input type="password" name="password" minlength="8" required></div><button class="btn">Update password</button></form></div>'))
        if path=="/logout": return self.logout()
        if path.startswith("/media/video/"): return self.video_stream(path)
        if path.startswith("/media/resource/"): return self.resource_file(path)
        if path.startswith("/admin"): return self.admin_get(path,q)
        if path in ("/dashboard","/course","/account") or path.startswith("/lesson/"):
            u=self.require("student");
            if not u:return
            if path=="/account":return self.account_page(u,q)
            ac=self.access(u)
            if not ac or ac["status"]!="active":
                return self.send_html(layout("Course access",f'<div class="card empty"><h2>Course access: {esc(ac["status"] if ac else "pending").title()}</h2><p>Your account is ready, but course access must be active. Please contact the course administrator.</p><a class="btn secondary" href="/account">View account</a></div>',u),403)
            if path in ("/dashboard","/course"):return self.dashboard(u)
            return self.lesson_page(u,int(path.rsplit("/",1)[1]))
        self.send_html(layout("Not found",'<div class="card empty"><h2>Page not found</h2><a href="/">Return home</a></div>',u),404)
    def route_post(self):
        path=urlparse(self.path).path; data=self.parse_body()
        if path=="/login":
            c=db(); u=c.execute("SELECT * FROM users WHERE email=?",(data.get("email","").strip(),)).fetchone()
            if not u or not pw_check(data.get("password",""),u["password_hash"]):c.close(); return self.redirect("/login?error="+quote("Email or password is incorrect."))
            if u["account_status"]!="active":c.close(); return self.redirect("/login?error="+quote("This account is disabled."))
            tok=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24); c.execute("INSERT INTO sessions VALUES(?,?,?,?)",(tok,u["id"],csrf,int(time.time())+30*86400)); c.commit(); c.close()
            return self.redirect("/admin" if u["role"]=="admin" else "/dashboard",f"session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={30*86400}")
        if path=="/enroll":
            name=data.get("name","").strip(); email=data.get("email","").strip().lower(); password=data.get("password","")
            if not name or "@" not in email or len(password)<8:return self.redirect("/enroll?error="+quote("Enter a name, valid email, and password of at least 8 characters."))
            c=db()
            try:
                c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",(name,email,pw_hash(password),"student",now())); uid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; cid=c.execute("SELECT id FROM courses LIMIT 1").fetchone()[0]; c.execute("INSERT INTO course_access(user_id,course_id,status,created_at) VALUES(?,?,?,?)",(uid,cid,"pending",now())); c.commit()
            except sqlite3.IntegrityError:c.close(); return self.redirect("/enroll?error="+quote("An account with that email already exists."))
            c.close(); return self.redirect("/login?ok="+quote("Account created. Log in while access approval is pending."))
        if path=="/forgot":
            c=db(); u=c.execute("SELECT id FROM users WHERE email=?",(data.get("email","").strip(),)).fetchone(); token=None
            if u:
                token=secrets.token_urlsafe(32); c.execute("INSERT INTO password_resets VALUES(?,?,?,0)",(token,u["id"],int(time.time())+3600)); c.commit()
            c.close()
            # No email provider is configured in this hosted first version, so safely show the one-time link.
            msg="If the account exists, a reset link was created."
            if token: msg+=f' <a href="/reset?token={quote(token)}">Open your one-time reset link</a> (valid for 1 hour).'
            return self.send_html(layout("Reset link",f'<div class="card form-card"><div class="alert ok">{msg}</div><a class="btn secondary" href="/login">Back to login</a></div>'))
        if path=="/reset":
            token=data.get("token",""); password=data.get("password","")
            if len(password)<8:return self.redirect("/reset?token="+quote(token))
            c=db(); r=c.execute("SELECT * FROM password_resets WHERE token=? AND expires_at>? AND used=0",(token,int(time.time()))).fetchone()
            if not r:c.close(); return self.redirect("/forgot")
            c.execute("UPDATE users SET password_hash=? WHERE id=?",(pw_hash(password),r["user_id"])); c.execute("UPDATE password_resets SET used=1 WHERE token=?",(token,)); c.execute("DELETE FROM sessions WHERE user_id=?",(r["user_id"],)); c.commit(); c.close(); return self.redirect("/login?ok="+quote("Password updated. Please log in."))
        if path.startswith("/admin"):return self.admin_post(path,data)
        u=self.require("student");
        if not u:return
        if not self.csrf_ok(u,data):return self.send_html(layout("Expired form",'<div class="alert error">This form expired. Refresh the page and try again.</div>',u),403)
        if path.startswith("/lesson/") and path.endswith("/complete"):
            lid=int(path.split("/")[2]); c=db(); valid=c.execute("SELECT 1 FROM lessons l JOIN modules m ON m.id=l.module_id JOIN course_access ca ON ca.course_id=m.course_id WHERE l.id=? AND ca.user_id=? AND ca.status='active'",(lid,u["id"])).fetchone()
            if valid:c.execute("INSERT INTO lesson_progress(user_id,lesson_id,status,updated_at,completed_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,lesson_id) DO UPDATE SET status='completed',updated_at=excluded.updated_at,completed_at=excluded.completed_at",(u["id"],lid,"completed",now(),now())); c.commit()
            c.close(); return self.redirect(f"/lesson/{lid}?ok=completed")
        if path=="/account/password":
            c=db(); real=c.execute("SELECT password_hash FROM users WHERE id=?",(u["id"],)).fetchone(); new=data.get("new_password","")
            if not pw_check(data.get("current_password",""),real[0]) or len(new)<8:c.close(); return self.redirect("/account?error="+quote("Current password is incorrect or the new password is too short."))
            c.execute("UPDATE users SET password_hash=? WHERE id=?",(pw_hash(new),u["id"])); c.commit(); c.close(); return self.redirect("/account?ok="+quote("Password changed."))
        self.send_html(layout("Not found","<h2>Not found</h2>",u),404)
    def logout(self):
        u,t=self.session()
        if t:
            c=db(); c.execute("DELETE FROM sessions WHERE token=?",(t,)); c.commit(); c.close()
        self.redirect("/", "session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
    def course_rows(self,user_id):
        c=db(); rows=c.execute("SELECT l.*,m.title module_title,m.position module_position,lp.status progress_status FROM lessons l JOIN modules m ON m.id=l.module_id LEFT JOIN lesson_progress lp ON lp.lesson_id=l.id AND lp.user_id=? ORDER BY m.position,l.position",(user_id,)).fetchall(); mods=c.execute("SELECT * FROM modules ORDER BY position").fetchall(); c.close(); return rows,mods
    def dashboard(self,u):
        rows,mods=self.course_rows(u["id"]); done=sum(r["progress_status"]=="completed" for r in rows); total=len(rows); pct=round(done*100/total) if total else 0; nxt=next((r for r in rows if r["progress_status"]!="completed"),rows[-1] if rows else None)
        congrats='<div class="alert ok"><h3>Congratulations!</h3>You have completed AI StorySprint Editing.</div>' if total and done==total else ''
        course=''
        for m in mods:
            ls=[r for r in rows if r["module_id"]==m["id"]]; items=''.join(f'<li><a href="/lesson/{r["id"]}"><span class="status-dot {"done" if r["progress_status"]=="completed" else "going" if r["progress_status"]=="in_progress" else ""}">{"✓" if r["progress_status"]=="completed" else ""}</span><span><strong>Lesson {rows.index(r)+1} — {esc(r["title"])}</strong><br><span class="muted">{("Completed" if r["progress_status"]=="completed" else "In Progress" if r["progress_status"] else "Not Started")}</span></span></a></li>' for r in ls)
            course+=f'<article class="card"><div class="module-head"><div><span class="eyebrow">Module {m["position"]}</span><h3>{esc(m["title"])}</h3></div><span class="badge">{len(ls)} lesson{"s" if len(ls)!=1 else ""}</span></div><ul class="lesson-list">{items}</ul></article>'
        body=f'<div class="split"><div><div class="eyebrow">Student dashboard</div><h2>{APP_NAME}</h2><p class="muted">Welcome back, {esc(u["name"])}.</p></div></div>{congrats}<section class="card"><div class="split"><div><h3>Your Progress</h3><strong>{done} / {total} Lessons Completed</strong></div><strong>{pct}%</strong></div><div class="progress" style="margin:15px 0"><i style="width:{pct}%"></i></div>{f"<a class=\"btn\" href=\"/lesson/{nxt['id']}\">Continue Learning</a>" if nxt else ""}</section><h2 style="margin-top:28px">Course content</h2><div class="stack">{course}</div>'
        return self.send_html(layout("Dashboard",body,u))
    def lesson_page(self,u,lid):
        c=db(); rows=c.execute("SELECT l.*,m.title module_title,m.position module_position FROM lessons l JOIN modules m ON m.id=l.module_id ORDER BY m.position,l.position").fetchall(); lesson=next((x for x in rows if x["id"]==lid),None)
        if not lesson:c.close(); return self.send_html(layout("Missing lesson",'<div class="alert error">This lesson could not be found.</div>',u),404)
        c.execute("INSERT INTO lesson_progress(user_id,lesson_id,status,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,lesson_id) DO NOTHING",(u["id"],lid,"in_progress",now())); c.commit(); prog=c.execute("SELECT status FROM lesson_progress WHERE user_id=? AND lesson_id=?",(u["id"],lid)).fetchone(); res=c.execute("SELECT * FROM resources WHERE lesson_id=? ORDER BY position,id",(lid,)).fetchall(); c.close(); idx=[r["id"] for r in rows].index(lid); prev=rows[idx-1] if idx else None; nxt=rows[idx+1] if idx+1<len(rows) else None
        video=f'<video controls controlsList="nodownload noplaybackrate" disablePictureInPicture playsinline preload="metadata" src="/media/video/{lid}">Your browser does not support video.</video>' if lesson["video_kind"]!="none" and lesson["video_source"] else '<div><strong>Video coming soon.</strong><br><span class="muted">The administrator has not attached a video yet.</span></div>'
        rr=''
        for r in res:
            if r["type"]=="link": content=f'<a class="btn secondary small" target="_blank" rel="noopener" href="{esc(r["url"])}">Open link</a>'
            elif r["type"]=="document": content=f'<a class="btn secondary small" href="/media/resource/{r["id"]}" target="_blank">Open document</a>'
            else: content=f'<div class="resource-text">{esc(r["content"])}</div>'
            rr+=f'<article class="card"><span class="eyebrow">{esc(r["type"])}</span><h3>{esc(r["title"])}</h3><p class="muted">{esc(r["description"])}</p>{content}</article>'
        if not rr:rr='<div class="card empty">No resources have been added for this lesson yet.</div>'
        body=f'<p><a href="/dashboard">← Dashboard</a></p><div class="eyebrow">Module {lesson["module_position"]} — {esc(lesson["module_title"])}</div><h2>Lesson {idx+1} — {esc(lesson["title"])}</h2><div class="video">{video}</div><section class="card" style="margin-top:18px"><div class="split"><div><h3>{esc(lesson["title"])}</h3><p class="muted">{esc(lesson["description"])}</p></div><span class="badge {esc(prog["status"])}">{esc(prog["status"].replace("_"," ").title())}</span></div><form method="post" action="/lesson/{lid}/complete"><input type="hidden" name="csrf" value="{esc(u["csrf"])}"><button class="btn">{"Completed ✓" if prog["status"]=="completed" else "Mark as Complete"}</button></form></section><h2 style="margin-top:28px">Resources</h2><div class="stack">{rr}</div><div class="lesson-nav" style="margin-top:26px">{f"<a class=\"btn secondary\" href=\"/lesson/{prev['id']}\">← Previous Lesson</a>" if prev else "<span></span>"}{f"<a class=\"btn\" href=\"/lesson/{nxt['id']}\">Next Lesson →</a>" if nxt else "<a class=\"btn\" href=\"/dashboard\">Finish Course</a>"}</div>'
        return self.send_html(layout(lesson["title"],body,u))
    def account_page(self,u,q):
        ac=self.access(u); msg=(f'<div class="alert error">{esc(q["error"])}</div>' if q.get("error") else f'<div class="alert ok">{esc(q["ok"])}</div>' if q.get("ok") else '')
        body=f'<h2>Account</h2>{msg}<div class="grid"><section class="card"><h3>Your details</h3><p><strong>Name</strong><br>{esc(u["name"])}</p><p><strong>Email</strong><br>{esc(u["email"])}</p><p><strong>Course access</strong><br><span class="badge {esc(ac["status"] if ac else "pending")}">{esc((ac["status"] if ac else "pending").title())}</span></p><a class="btn secondary" href="/logout">Logout</a></section><section class="card"><h3>Change password</h3><form method="post" action="/account/password"><input type="hidden" name="csrf" value="{esc(u["csrf"])}"><div class="field"><label>Current password</label><input type="password" name="current_password" required></div><div class="field"><label>New password</label><input type="password" name="new_password" minlength="8" required></div><button class="btn">Change password</button></form></section></div>'
        self.send_html(layout("Account",body,u))
    def video_stream(self,path):
        u=self.require("student");
        if not u:return
        lid=int(path.rsplit("/",1)[1]); c=db(); r=c.execute("SELECT l.* FROM lessons l JOIN modules m ON m.id=l.module_id JOIN course_access ca ON ca.course_id=m.course_id WHERE l.id=? AND ca.user_id=? AND ca.status='active'",(lid,u["id"])).fetchone(); c.close()
        if not r or not r["video_source"]:return self.send_error(404)
        if r["video_kind"]=="upload":return self.serve_private(os.path.join(UPLOADS,r["video_source"]),r["video_mime"] or "video/mp4",inline=True)
        try:
            req=Request(r["video_source"],headers={"User-Agent":"StorySprintVideo/1.0","Range":self.headers.get("Range","")}); remote=urlopen(req,timeout=15); data=remote.read(); self.send_response(remote.status); self.send_header("Content-Type",remote.headers.get("Content-Type",r["video_mime"] or "video/mp4")); self.send_header("Content-Length",str(len(data))); self.send_header("Accept-Ranges","bytes"); self.send_header("Cache-Control","private, max-age=300"); self.end_headers(); self.wfile.write(data)
        except:self.send_error(502,"Video is temporarily unavailable")
    def resource_file(self,path):
        u=self.require("student");
        if not u:return
        rid=int(path.rsplit("/",1)[1]); c=db(); r=c.execute("SELECT r.* FROM resources r JOIN lessons l ON l.id=r.lesson_id JOIN modules m ON m.id=l.module_id JOIN course_access ca ON ca.course_id=m.course_id WHERE r.id=? AND ca.user_id=? AND ca.status='active'",(rid,u["id"])).fetchone(); c.close()
        if not r or not r["file_path"]:return self.send_error(404)
        self.serve_private(os.path.join(UPLOADS,r["file_path"]),mimetypes.guess_type(r["file_path"])[0] or "application/octet-stream",True)
    def serve_private(self,path,mime,inline=False):
        if not os.path.isfile(path):return self.send_error(404)
        size=os.path.getsize(path); start=0; end=size-1; rg=self.headers.get("Range")
        if rg:
            m=re.match(r"bytes=(\d+)-(\d*)",rg)
            if m:start=int(m.group(1)); end=int(m.group(2) or end)
        length=end-start+1; self.send_response(206 if rg else 200); self.send_header("Content-Type",mime); self.send_header("Content-Length",str(length)); self.send_header("Accept-Ranges","bytes"); self.send_header("Content-Disposition",("inline" if inline else "attachment")+f'; filename="{esc(os.path.basename(path))}"'); self.send_header("Cache-Control","private, max-age=300");
        if rg:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
        self.end_headers();
        with open(path,"rb") as f:f.seek(start); self.wfile.write(f.read(length))
    def admin_get(self,path,q):
        u=self.require("admin")
        if not u:return
        c=db(); csrf=f'<input type="hidden" name="csrf" value="{esc(u["csrf"])}">'; msg=f'<div class="alert ok">{esc(q.get("ok"))}</div>' if q.get("ok") else ''
        if path=="/admin":
            total=c.execute("SELECT count(*) FROM users WHERE role='student'").fetchone()[0]; active=c.execute("SELECT count(*) FROM course_access WHERE status='active'").fetchone()[0]; lessons=c.execute("SELECT count(*) FROM lessons").fetchone()[0]; completed=c.execute("SELECT count(*) FROM (SELECT user_id,count(*) n FROM lesson_progress WHERE status='completed' GROUP BY user_id HAVING n>=?)",(lessons,)).fetchone()[0]; avg=c.execute("SELECT COALESCE(AVG(done*100.0/?),0) FROM (SELECT u.id,count(CASE WHEN lp.status='completed' THEN 1 END) done FROM users u LEFT JOIN lesson_progress lp ON lp.user_id=u.id WHERE u.role='student' GROUP BY u.id)",(lessons or 1,)).fetchone()[0]; c.close()
            body=f'<h2>Overview</h2><p class="muted">Manage your course and students.</p><div class="kpis"><div class="card kpi"><span>Total students</span><strong>{total}</strong></div><div class="card kpi"><span>Active students</span><strong>{active}</strong></div><div class="card kpi"><span>Completed students</span><strong>{completed}</strong></div><div class="card kpi"><span>Average progress</span><strong>{avg:.0f}%</strong></div></div>'
        elif path=="/admin/modules":
            mods=c.execute("SELECT m.*,count(l.id) lesson_count FROM modules m LEFT JOIN lessons l ON l.module_id=m.id GROUP BY m.id ORDER BY m.position").fetchall(); c.close(); rows=''.join(f'<tr><td>{m["position"]}</td><td><strong>{esc(m["title"])}</strong><br><span class="muted">{m["lesson_count"]} lessons</span></td><td><form class="row" method="post" action="/admin/module/{m["id"]}/edit">{csrf}<input name="title" value="{esc(m["title"])}" required style="padding:8px"><input name="position" type="number" min="1" value="{m["position"]}" style="width:65px;padding:8px"><button class="btn small">Save</button></form></td><td><form method="post" action="/admin/module/{m["id"]}/delete" onsubmit="return confirm(\'Delete this module and its lessons?\')">{csrf}<button class="btn danger small">Delete</button></form></td></tr>' for m in mods)
            body=f'<div class="split"><div><h2>Modules</h2><p class="muted">Create, edit, delete, and reorder modules.</p></div></div>{msg}<div class="card"><h3>Add module</h3><form class="row" method="post" action="/admin/module/create">{csrf}<input name="title" placeholder="Module title" required style="padding:10px;flex:1"><input name="position" type="number" min="1" value="{len(mods)+1}" style="padding:10px;width:80px"><button class="btn">Add</button></form></div><table><thead><tr><th>Order</th><th>Module</th><th>Edit</th><th></th></tr></thead><tbody>{rows}</tbody></table>'
        elif path in ("/admin/lessons","/admin/videos"):
            ls=c.execute("SELECT l.*,m.title module_title,m.position mp FROM lessons l JOIN modules m ON m.id=l.module_id ORDER BY m.position,l.position").fetchall(); mods=c.execute("SELECT * FROM modules ORDER BY position").fetchall(); c.close()
            rows=''.join(f'<tr><td>Module {x["mp"]}<br><span class="muted">{esc(x["module_title"])}</span></td><td><strong>{esc(x["title"])}</strong><br><span class="badge">{esc(x["video_kind"])}</span></td><td><a class="btn small" href="/admin/lesson/{x["id"]}">{"Manage video" if path.endswith("videos") else "Edit lesson"}</a></td></tr>' for x in ls)
            opts=''.join(f'<option value="{m["id"]}">{m["position"]}. {esc(m["title"])}</option>' for m in mods)
            add='' if path.endswith("videos") else f'<div class="card"><h3>Add lesson</h3><form method="post" action="/admin/lesson/create">{csrf}<div class="grid"><div class="field"><label>Title</label><input name="title" required></div><div class="field"><label>Module</label><select name="module_id">{opts}</select></div></div><div class="field"><label>Description</label><textarea name="description"></textarea></div><button class="btn">Add lesson</button></form></div>'
            body=f'<h2>{"Videos" if path.endswith("videos") else "Lessons"}</h2><p class="muted">{"Attach or replace protected lesson videos." if path.endswith("videos") else "Course content is loaded from the database."}</p>{msg}{add}<table><thead><tr><th>Module</th><th>Lesson</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table>'
        elif re.fullmatch(r"/admin/lesson/\d+",path):
            lid=int(path.rsplit("/",1)[1]); l=c.execute("SELECT l.*,m.title module_title FROM lessons l JOIN modules m ON m.id=l.module_id WHERE l.id=?",(lid,)).fetchone(); mods=c.execute("SELECT * FROM modules ORDER BY position").fetchall(); resources=c.execute("SELECT * FROM resources WHERE lesson_id=? ORDER BY position,id",(lid,)).fetchall(); c.close()
            if not l:return self.send_html(layout("Missing lesson","<div class=alert>Lesson not found.</div>",u,True),404)
            opts=''.join(f'<option value="{m["id"]}" {"selected" if m["id"]==l["module_id"] else ""}>{m["position"]}. {esc(m["title"])}</option>' for m in mods)
            rr=''.join(f'<tr><td>{r["position"]}</td><td>{esc(r["title"])}</td><td>{esc(r["type"])}</td><td><a class="btn small secondary" href="/admin/resource/{r["id"]}">Edit</a></td></tr>' for r in resources) or '<tr><td colspan="4">No resources yet.</td></tr>'
            body=f'<p><a href="/admin/lessons">← Lessons</a></p><h2>Edit lesson</h2>{msg}<section class="card"><form method="post" action="/admin/lesson/{lid}/edit">{csrf}<div class="grid"><div class="field"><label>Lesson title</label><input name="title" value="{esc(l["title"])}" required></div><div class="field"><label>Module</label><select name="module_id">{opts}</select></div></div><div class="field"><label>Description</label><textarea name="description">{esc(l["description"])}</textarea></div><div class="field"><label>Position in module</label><input type="number" name="position" min="1" value="{l["position"]}"></div><button class="btn">Save lesson</button></form></section><section class="card"><h3>Video</h3><p class="muted">Current: {esc(l["video_kind"])}. External URLs are streamed through an authenticated endpoint; private uploads are stored outside public web files.</p><form enctype="multipart/form-data" method="post" action="/admin/lesson/{lid}/video">{csrf}<div class="field"><label>Video source type</label><select name="video_kind"><option value="none">No video / coming soon</option><option value="external">Protected external URL</option><option value="upload">Private video upload</option></select></div><div class="field"><label>Secure video URL (for external)</label><input type="url" name="video_url" placeholder="https://your-video-host.example/video.mp4" value="{esc(l["video_source"] if l["video_kind"]=="external" else "")}"></div><div class="field"><label>Video file (for upload)</label><input type="file" name="video_file" accept="video/*"></div><button class="btn">Save video</button></form></section><section><div class="split"><h2>Resources</h2><a class="btn" href="/admin/resource/new?lesson_id={lid}">Add resource</a></div><table><thead><tr><th>Order</th><th>Title</th><th>Type</th><th></th></tr></thead><tbody>{rr}</tbody></table></section><form method="post" action="/admin/lesson/{lid}/delete" style="margin-top:30px" onsubmit="return confirm(\'Delete this lesson?\')">{csrf}<button class="btn danger">Delete lesson</button></form>'
        elif path=="/admin/resources":
            rs=c.execute("SELECT r.*,l.title lesson_title,m.title module_title FROM resources r JOIN lessons l ON l.id=r.lesson_id JOIN modules m ON m.id=l.module_id ORDER BY m.position,l.position,r.position").fetchall(); c.close(); rows=''.join(f'<tr><td>{esc(r["module_title"])} / {esc(r["lesson_title"])}</td><td>{esc(r["title"])}</td><td>{esc(r["type"])}</td><td><a class="btn small" href="/admin/resource/{r["id"]}">Edit</a></td></tr>' for r in rs) or '<tr><td colspan="4">No resources have been added.</td></tr>'
            body=f'<div class="split"><div><h2>Resources</h2><p class="muted">Manage lesson links, text, and documents.</p></div><a class="btn" href="/admin/resource/new">Add resource</a></div>{msg}<table><thead><tr><th>Lesson</th><th>Resource</th><th>Type</th><th></th></tr></thead><tbody>{rows}</tbody></table>'
        elif path=="/admin/resource/new" or re.fullmatch(r"/admin/resource/\d+",path):
            rid=None if path.endswith("new") else int(path.rsplit("/",1)[1]); r=c.execute("SELECT * FROM resources WHERE id=?",(rid,)).fetchone() if rid else None; lessons=c.execute("SELECT l.id,l.title,m.title module_title,m.position mp FROM lessons l JOIN modules m ON m.id=l.module_id ORDER BY m.position,l.position").fetchall(); c.close(); selected=int(q.get("lesson_id",r["lesson_id"] if r else lessons[0]["id"])); opts=''.join(f'<option value="{x["id"]}" {"selected" if x["id"]==selected else ""}>Module {x["mp"]}: {esc(x["title"])}</option>' for x in lessons)
            body=f'<h2>{"Edit" if r else "Add"} resource</h2>{msg}<div class="card"><form enctype="multipart/form-data" method="post" action="/admin/resource/{rid if r else "create"}">{csrf}<div class="field"><label>Lesson</label><select name="lesson_id">{opts}</select></div><div class="grid"><div class="field"><label>Type</label><select name="type"><option value="link" {"selected" if r and r["type"]=="link" else ""}>Link</option><option value="text" {"selected" if r and r["type"]=="text" else ""}>Text</option><option value="document" {"selected" if r and r["type"]=="document" else ""}>Document</option></select></div><div class="field"><label>Order</label><input type="number" name="position" min="1" value="{r["position"] if r else 1}"></div></div><div class="field"><label>Title</label><input name="title" required value="{esc(r["title"] if r else "")}"></div><div class="field"><label>Optional description</label><textarea name="description">{esc(r["description"] if r else "")}</textarea></div><div class="field"><label>URL (for Link)</label><input type="url" name="url" value="{esc(r["url"] if r else "")}"></div><div class="field"><label>Text/content (for Text)</label><textarea name="content">{esc(r["content"] if r else "")}</textarea></div><div class="field"><label>File (for Document)</label><input type="file" name="document"></div><button class="btn">Save resource</button></form>{f'<form method="post" action="/admin/resource/{rid}/delete" style="margin-top:20px" onsubmit="return confirm(\'Delete this resource?\')">{csrf}<button class="btn danger">Delete</button></form>' if r else ''}</div>'
        elif path=="/admin/students":
            lessons=c.execute("SELECT count(*) FROM lessons").fetchone()[0]; students=c.execute("SELECT u.*,ca.status access_status,count(CASE WHEN lp.status='completed' THEN 1 END) done FROM users u LEFT JOIN course_access ca ON ca.user_id=u.id LEFT JOIN lesson_progress lp ON lp.user_id=u.id WHERE u.role='student' GROUP BY u.id ORDER BY u.created_at DESC").fetchall(); c.close(); rows=''.join(f'<tr><td><strong>{esc(s["name"])}</strong><br>{esc(s["email"])}</td><td><span class="badge {esc(s["account_status"])}">{esc(s["account_status"])}</span></td><td><span class="badge {esc(s["access_status"])}">{esc(s["access_status"])}</span></td><td>{s["done"]}/{lessons} ({round(s["done"]*100/(lessons or 1))}%)</td><td>{esc(s["created_at"][:10])}</td><td><a class="btn small" href="/admin/student/{s["id"]}">View</a></td></tr>' for s in students)
            body=f'<h2>Students</h2><p class="muted">Activate, suspend, and view student progress. Passwords are never visible.</p>{msg}<div class="card"><h3>Add student</h3><form class="row" method="post" action="/admin/student/create">{csrf}<input name="name" placeholder="Name" required style="padding:10px"><input name="email" type="email" placeholder="Email" required style="padding:10px"><input name="password" type="password" minlength="8" placeholder="Temporary password" required style="padding:10px"><select name="status" style="padding:10px"><option>pending</option><option>active</option></select><button class="btn">Add</button></form></div><table><thead><tr><th>Student</th><th>Account</th><th>Access</th><th>Progress</th><th>Registered</th><th></th></tr></thead><tbody>{rows}</tbody></table>'
        elif re.fullmatch(r"/admin/student/\d+",path):
            sid=int(path.rsplit("/",1)[1]); s=c.execute("SELECT u.*,ca.status access_status FROM users u LEFT JOIN course_access ca ON ca.user_id=u.id WHERE u.id=? AND role='student'",(sid,)).fetchone(); prog=c.execute("SELECT l.title,m.title module_title,lp.status FROM lessons l JOIN modules m ON m.id=l.module_id LEFT JOIN lesson_progress lp ON lp.lesson_id=l.id AND lp.user_id=? ORDER BY m.position,l.position",(sid,)).fetchall(); c.close()
            if not s:return self.send_html(layout("Missing student","<div class=alert>Student not found.</div>",u,True),404)
            rows=''.join(f'<tr><td>{esc(x["module_title"])}</td><td>{esc(x["title"])}</td><td><span class="badge {esc(x["status"] or "")}">{esc((x["status"] or "not started").replace("_"," "))}</span></td></tr>' for x in prog)
            body=f'<p><a href="/admin/students">← Students</a></p><h2>{esc(s["name"])}</h2>{msg}<div class="card"><p><strong>Email:</strong> {esc(s["email"])}</p><p><strong>Registered:</strong> {esc(s["created_at"][:10])}</p><form method="post" action="/admin/student/{sid}/status">{csrf}<div class="field"><label>Course access status</label><select name="status"><option {"selected" if s["access_status"]=="pending" else ""}>pending</option><option {"selected" if s["access_status"]=="active" else ""}>active</option><option {"selected" if s["access_status"]=="suspended" else ""}>suspended</option></select></div><button class="btn">Update access</button></form></div><h3>Lesson progress</h3><table><thead><tr><th>Module</th><th>Lesson</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>'
        elif path=="/admin/settings":
            c.close(); body=f'<h2>Settings</h2>{msg}<div class="card"><h3>Course platform</h3><p><strong>Name:</strong> {APP_NAME}</p><p><strong>Enrollment:</strong> Manual activation</p><p><strong>Video protection:</strong> Authenticated streaming proxy/private files</p><p class="muted">Payment and certificate integrations can be added later without changing the course and access data model.</p></div><div class="card"><h3>Administrator account</h3><p>{esc(u["email"])}</p><a class="btn secondary" href="/logout">Logout</a></div>'
        else:c.close(); return self.send_html(layout("Not found","<div class=alert>Admin page not found.</div>",u,True),404)
        self.send_html(layout("Admin",body,u,True))
    def admin_post(self,path,data):
        u=self.require("admin")
        if not u:return
        if not self.csrf_ok(u,data):return self.send_html(layout("Expired form",'<div class="alert error">This form expired. Refresh and try again.</div>',u,True),403)
        c=db()
        try:
            if path=="/admin/module/create":
                cid=c.execute("SELECT id FROM courses LIMIT 1").fetchone()[0]; c.execute("INSERT INTO modules(course_id,title,position) VALUES(?,?,?)",(cid,data.get("title","Untitled"),int(data.get("position",99)))); dest="/admin/modules?ok=Module+added"
            elif re.fullmatch(r"/admin/module/\d+/edit",path):
                mid=int(path.split("/")[3]); c.execute("UPDATE modules SET title=?,position=? WHERE id=?",(data.get("title"),int(data.get("position",1)),mid)); dest="/admin/modules?ok=Module+updated"
            elif re.fullmatch(r"/admin/module/\d+/delete",path):
                c.execute("DELETE FROM modules WHERE id=?",(int(path.split("/")[3]),)); dest="/admin/modules?ok=Module+deleted"
            elif path=="/admin/lesson/create":
                mid=int(data["module_id"]); pos=c.execute("SELECT COALESCE(MAX(position),0)+1 FROM lessons WHERE module_id=?",(mid,)).fetchone()[0]; c.execute("INSERT INTO lessons(module_id,title,description,position) VALUES(?,?,?,?)",(mid,data["title"],data.get("description",""),pos)); lid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; dest=f"/admin/lesson/{lid}?ok=Lesson+added"
            elif re.fullmatch(r"/admin/lesson/\d+/edit",path):
                lid=int(path.split("/")[3]); c.execute("UPDATE lessons SET title=?,description=?,module_id=?,position=? WHERE id=?",(data["title"],data.get("description",""),int(data["module_id"]),int(data.get("position",1)),lid)); dest=f"/admin/lesson/{lid}?ok=Lesson+updated"
            elif re.fullmatch(r"/admin/lesson/\d+/delete",path):
                lid=int(path.split("/")[3]); c.execute("DELETE FROM lessons WHERE id=?",(lid,)); dest="/admin/lessons?ok=Lesson+deleted"
            elif re.fullmatch(r"/admin/lesson/\d+/video",path):
                lid=int(path.split("/")[3]); kind=data.get("video_kind","none"); source=None; mime=None
                if kind=="external": source=data.get("video_url","").strip(); mime="video/mp4"
                elif kind=="upload":
                    f=data.get("video_file")
                    if isinstance(f,dict) and f.get("filename"):
                        ext=os.path.splitext(f["filename"])[1].lower()[:10]; name=f"video_{lid}_{secrets.token_hex(8)}{ext}"; open(os.path.join(UPLOADS,name),"wb").write(f["data"]); source=name; mime=f.get("type") or mimetypes.guess_type(name)[0]
                    else:
                        old=c.execute("SELECT video_source,video_mime FROM lessons WHERE id=?",(lid,)).fetchone(); source=old[0] if old else None; mime=old[1] if old else None
                c.execute("UPDATE lessons SET video_kind=?,video_source=?,video_mime=? WHERE id=?",(kind,source,mime,lid)); dest=f"/admin/lesson/{lid}?ok=Video+updated"
            elif path=="/admin/resource/create" or re.fullmatch(r"/admin/resource/\d+",path):
                rid=None if path.endswith("create") else int(path.rsplit("/",1)[1]); typ=data.get("type","link"); file_path=None
                f=data.get("document")
                if isinstance(f,dict) and f.get("filename"):
                    safe=slug(os.path.splitext(f["filename"])[0])+os.path.splitext(f["filename"])[1].lower()[:12]; file_path=f"doc_{secrets.token_hex(8)}_{safe}"; open(os.path.join(UPLOADS,file_path),"wb").write(f["data"])
                elif rid:
                    old=c.execute("SELECT file_path FROM resources WHERE id=?",(rid,)).fetchone(); file_path=old[0] if old else None
                vals=(int(data["lesson_id"]),typ,data["title"],data.get("url",""),data.get("content",""),file_path,data.get("description",""),int(data.get("position",1)))
                if rid:c.execute("UPDATE resources SET lesson_id=?,type=?,title=?,url=?,content=?,file_path=?,description=?,position=? WHERE id=?",vals+(rid,))
                else:c.execute("INSERT INTO resources(lesson_id,type,title,url,content,file_path,description,position) VALUES(?,?,?,?,?,?,?,?)",vals); rid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
                dest=f"/admin/resource/{rid}?ok=Resource+saved"
            elif re.fullmatch(r"/admin/resource/\d+/delete",path):
                c.execute("DELETE FROM resources WHERE id=?",(int(path.split("/")[3]),)); dest="/admin/resources?ok=Resource+deleted"
            elif path=="/admin/student/create":
                c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",(data["name"],data["email"].strip().lower(),pw_hash(data["password"]),"student",now())); sid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; cid=c.execute("SELECT id FROM courses LIMIT 1").fetchone()[0]; c.execute("INSERT INTO course_access(user_id,course_id,status,created_at) VALUES(?,?,?,?)",(sid,cid,data.get("status","pending"),now())); dest=f"/admin/student/{sid}?ok=Student+added"
            elif re.fullmatch(r"/admin/student/\d+/status",path):
                sid=int(path.split("/")[3]); c.execute("UPDATE course_access SET status=? WHERE user_id=?",(data.get("status","pending"),sid)); dest=f"/admin/student/{sid}?ok=Access+updated"
            else:c.close(); return self.send_html(layout("Not found","<div class=alert>Action not found.</div>",u,True),404)
            c.commit(); c.close(); self.redirect(dest)
        except (ValueError,KeyError,sqlite3.IntegrityError) as e:
            c.rollback(); c.close(); self.send_html(layout("Could not save",'<div class="alert error">The information could not be saved. Check required fields and ensure the email is unique.</div><a href="javascript:history.back()">Go back</a>',u,True),400)

if __name__=="__main__":
    init_db(); print(f"AI StorySprint Editing running at http://{HOST}:{PORT}"); ThreadingHTTPServer((HOST,PORT),App).serve_forever()
