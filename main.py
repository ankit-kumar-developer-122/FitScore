from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os, sqlite3, hashlib, uuid, json
from datetime import datetime

app = FastAPI(title="FitScore API")

# Directories
os.makedirs("public/css", exist_ok=True)
os.makedirs("public/js", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# ── Database Setup ───────────────────────────────────────────────────
DB_PATH = "fitscore.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'candidate',
        fitscore INTEGER DEFAULT 0,
        ats_score INTEGER DEFAULT 0,
        skills TEXT DEFAULT '[]',
        auto_email INTEGER DEFAULT 0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, company TEXT, salary TEXT,
        match_pct INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
        skills TEXT DEFAULT '[]', experience TEXT,
        description TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, job_id INTEGER,
        stage TEXT DEFAULT 'applied',
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    );
    CREATE TABLE IF NOT EXISTS resumes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, filename TEXT, filepath TEXT,
        version_tag TEXT DEFAULT 'Original',
        uploaded_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS workflows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, status TEXT DEFAULT 'active',
        runs INTEGER DEFAULT 0, success_rate REAL DEFAULT 100.0,
        created_at TEXT
    );
    """)
    # Seed data if empty
    if c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0:
        now = datetime.utcnow().isoformat()
        jobs = [
            ("Senior Frontend Engineer","Vercel","$150k",95,"active",'["JavaScript","React","CSS"]',"3+ yrs","Build next-gen web UIs",now),
            ("Data Scientist","OpenAI","$180k",88,"active",'["Python","ML","Statistics"]',"2+ yrs","Work on cutting-edge AI models",now),
            ("Backend Engineer","Stripe","$160k",82,"active",'["Python","Go","SQL"]',"4+ yrs","Design payment infrastructure",now),
            ("Product Designer","Figma","$140k",78,"active",'["Figma","UI/UX","Prototyping"]',"2+ yrs","Shape the future of design tools",now),
            ("ML Engineer","DeepMind","$200k",92,"active",'["Python","TensorFlow","Research"]',"3+ yrs","Push boundaries of AI research",now),
            ("DevOps Lead","Netflix","$170k",75,"active",'["AWS","Kubernetes","Terraform"]',"5+ yrs","Scale global streaming infra",now),
        ]
        c.executemany("INSERT INTO jobs (title,company,salary,match_pct,status,skills,experience,description,created_at) VALUES (?,?,?,?,?,?,?,?,?)", jobs)
    if c.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] == 0:
        now = datetime.utcnow().isoformat()
        wfs = [
            ("Daily Job Scraper","active",142,98.5,now),
            ("Resume Enhancer","paused",12,100.0,now),
            ("Auto Match Pipeline","active",89,96.2,now),
        ]
        c.executemany("INSERT INTO workflows (name,status,runs,success_rate,created_at) VALUES (?,?,?,?,?)", wfs)
    conn.commit()
    conn.close()

init_db()

# ── Auth Endpoints ───────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

@app.post("/api/register")
async def register(name: str = Form(...), email: str = Form(...), password: str = Form(...), role: str = Form("candidate")):
    conn = get_db()
    uid = str(uuid.uuid4())
    try:
        conn.execute("INSERT INTO users (id,name,email,password_hash,role,fitscore,ats_score,skills,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (uid, name, email, hash_pw(password), role, 85, 92, '["HTML","CSS","Python","Data Analysis"]', datetime.utcnow().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Email already registered")
    conn.close()
    return {"id": uid, "name": name, "email": email, "role": role}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=? AND password_hash=?", (email, hash_pw(password))).fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return dict(user)

# ── User Endpoints ───────────────────────────────────────────────────
@app.get("/api/users")
async def get_users():
    conn = get_db()
    rows = conn.execute("SELECT id,name,email,role,fitscore,ats_score,created_at FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/users/{user_id}/toggle-email")
async def toggle_email(user_id: str):
    conn = get_db()
    user = conn.execute("SELECT auto_email FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(404, "User not found")
    new_val = 0 if user["auto_email"] else 1
    conn.execute("UPDATE users SET auto_email=? WHERE id=?", (new_val, user_id))
    conn.commit()
    conn.close()
    return {"auto_email": bool(new_val)}

# ── Job Endpoints ────────────────────────────────────────────────────
@app.get("/api/jobs")
async def get_jobs():
    conn = get_db()
    rows = conn.execute("SELECT * FROM jobs ORDER BY match_pct DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/jobs")
async def create_job(title: str = Form(...), company: str = Form(...), salary: str = Form(""), skills: str = Form("[]"), experience: str = Form(""), description: str = Form("")):
    conn = get_db()
    conn.execute("INSERT INTO jobs (title,company,salary,skills,experience,description,created_at) VALUES (?,?,?,?,?,?,?)",
                 (title, company, salary, skills, experience, description, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Resume Upload ────────────────────────────────────────────────────
@app.post("/api/resumes/upload")
async def upload_resume(user_id: str = Form(...), file: UploadFile = File(...), version_tag: str = Form("Original")):
    ext = os.path.splitext(file.filename)[1]
    safe_name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join("uploads", safe_name)
    contents = await file.read()
    with open(path, "wb") as f:
        f.write(contents)
    conn = get_db()
    conn.execute("INSERT INTO resumes (user_id,filename,filepath,version_tag,uploaded_at) VALUES (?,?,?,?,?)",
                 (user_id, file.filename, path, version_tag, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"filename": file.filename, "path": path, "tag": version_tag}

@app.get("/api/resumes/{user_id}")
async def get_resumes(user_id: str):
    conn = get_db()
    rows = conn.execute("SELECT * FROM resumes WHERE user_id=? ORDER BY uploaded_at DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Applications ─────────────────────────────────────────────────────
@app.get("/api/applications")
async def get_applications():
    conn = get_db()
    rows = conn.execute("SELECT a.*, u.name as user_name, j.title as job_title FROM applications a JOIN users u ON a.user_id=u.id JOIN jobs j ON a.job_id=j.id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/applications")
async def apply_job(user_id: str = Form(...), job_id: int = Form(...)):
    conn = get_db()
    conn.execute("INSERT INTO applications (user_id,job_id,stage,created_at) VALUES (?,?,?,?)",
                 (user_id, job_id, "applied", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── Workflows ────────────────────────────────────────────────────────
@app.get("/api/workflows")
async def get_workflows():
    conn = get_db()
    rows = conn.execute("SELECT * FROM workflows").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Analytics ────────────────────────────────────────────────────────
@app.get("/api/analytics/summary")
async def analytics_summary():
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    total_apps = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    total_resumes = conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0]
    conn.close()
    return {"total_users": total_users, "total_jobs": total_jobs, "total_applications": total_apps, "total_resumes": total_resumes}

# ── DB Tables (admin view) ──────────────────────────────────────────
@app.get("/api/db/tables")
async def db_tables():
    conn = get_db()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    result = {}
    for t in tables:
        name = t["name"]
        rows = conn.execute(f"SELECT * FROM {name} LIMIT 50").fetchall()
        result[name] = [dict(r) for r in rows]
    conn.close()
    return result

# ── Serve login page ─────────────────────────────────────────────────
@app.get("/login")
async def login_page():
    return FileResponse("public/login.html")

# ── Static Files (MUST be last) ─────────────────────────────────────
app.mount("/", StaticFiles(directory="public", html=True), name="public")
