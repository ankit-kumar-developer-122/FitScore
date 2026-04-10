from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os, sqlite3, hashlib, uuid, json, re
from datetime import datetime

from pypdf import PdfReader
from docx import Document

app = FastAPI(title="FitScore API")

allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = ["*"] if allowed_origins_env.strip() == "*" else [
    origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code >= 400:
            return response

        if path.endswith((".css", ".js")):
            response.headers["Cache-Control"] = "no-cache"
        elif path.endswith(".html") or path == ".":
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response

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
        ats_score INTEGER DEFAULT 0,
        analysis_json TEXT DEFAULT '{}',
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
    resume_columns = {row[1] for row in c.execute("PRAGMA table_info(resumes)").fetchall()}
    if "ats_score" not in resume_columns:
        try:
            c.execute("ALTER TABLE resumes ADD COLUMN ats_score INTEGER DEFAULT 0")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    if "analysis_json" not in resume_columns:
        try:
            c.execute("ALTER TABLE resumes ADD COLUMN analysis_json TEXT DEFAULT '{}'")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
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


ACTION_VERBS = {
    "built", "created", "developed", "designed", "implemented", "improved",
    "optimized", "led", "managed", "launched", "delivered", "automated",
    "analyzed", "architected", "collaborated", "scaled"
}

COMMON_KEYWORDS = {
    "python", "javascript", "react", "sql", "aws", "docker", "kubernetes",
    "ci/cd", "git", "api", "machine learning", "data", "fastapi", "testing"
}

SECTION_PATTERNS = {
    "contact": r"(email|phone|linkedin|github)",
    "summary": r"(summary|profile|objective)",
    "experience": r"(experience|employment|work history)",
    "education": r"(education|academic)",
    "skills": r"(skills|technical skills|technologies)",
    "projects": r"(projects|project experience)"
}


def extract_resume_text(path: str, ext: str) -> str:
    ext = ext.lower()
    if ext == ".pdf":
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if ext in {".docx", ".doc"}:
        document = Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if ext in {".txt", ".md"}:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise HTTPException(400, "Unsupported file type for ATS analysis")


def analyze_resume_text(text: str) -> dict:
    lowered = text.lower()
    words = re.findall(r"\b[\w.+#/-]+\b", text)
    word_count = len(words)
    email_present = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text))
    phone_present = bool(re.search(r"(\+\d{1,3}[\s-]?)?(\d[\s-]?){10,}", text))
    linkedin_present = "linkedin.com" in lowered
    github_present = "github.com" in lowered
    metrics_count = len(re.findall(r"\b\d+%|\b\d+\+|\$\d+|\b\d+\b", text))
    action_verbs_found = sorted({verb for verb in ACTION_VERBS if re.search(rf"\b{re.escape(verb)}\b", lowered)})
    keywords_found = sorted({kw for kw in COMMON_KEYWORDS if kw in lowered})
    sections_found = [name for name, pattern in SECTION_PATTERNS.items() if re.search(pattern, lowered)]
    all_caps_ratio = (sum(1 for char in text if char.isupper()) / max(1, sum(1 for char in text if char.isalpha())))

    score = 35
    score += min(15, len(sections_found) * 3)
    score += 10 if email_present else 0
    score += 6 if phone_present else 0
    score += 4 if linkedin_present else 0
    score += 3 if github_present else 0
    score += min(12, len(keywords_found) * 2)
    score += min(10, metrics_count * 2)
    score += min(8, len(action_verbs_found))

    if word_count < 200:
        score -= 12
    elif word_count < 350:
        score -= 5
    elif word_count > 1200:
        score -= 8

    if all_caps_ratio > 0.18:
        score -= 5

    score = max(0, min(100, score))

    suggestions = []
    if not email_present or not phone_present:
        suggestions.append("Add clear contact details so ATS can parse your profile reliably.")
    if "projects" not in sections_found:
        suggestions.append("Add a Projects section to surface hands-on work and keywords.")
    if metrics_count < 3:
        suggestions.append("Include more quantified achievements like percentages, time saved, or revenue impact.")
    if len(keywords_found) < 5:
        suggestions.append("Match more role-specific keywords such as tools, frameworks, and cloud platforms.")
    if len(action_verbs_found) < 4:
        suggestions.append("Strengthen bullet points with action verbs like built, led, optimized, or automated.")
    if word_count < 350:
        suggestions.append("Your resume may be too short for strong ATS coverage; add more relevant detail.")

    return {
        "ats_score": score,
        "word_count": word_count,
        "keywords_found": keywords_found,
        "sections_found": sections_found,
        "metrics_count": metrics_count,
        "action_verbs_found": action_verbs_found,
        "suggestions": suggestions[:5],
    }

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
    extracted_text = extract_resume_text(path, ext)
    analysis = analyze_resume_text(extracted_text)
    conn = get_db()
    conn.execute("INSERT INTO resumes (user_id,filename,filepath,version_tag,uploaded_at) VALUES (?,?,?,?,?)",
                 (user_id, file.filename, path, version_tag, datetime.utcnow().isoformat()))
    conn.execute(
        "UPDATE resumes SET ats_score=?, analysis_json=? WHERE id = last_insert_rowid()",
        (analysis["ats_score"], json.dumps(analysis))
    )
    conn.execute("UPDATE users SET ats_score=? WHERE id=?", (analysis["ats_score"], user_id))
    conn.commit()
    conn.close()
    return {
        "filename": file.filename,
        "path": path,
        "tag": version_tag,
        "ats_score": analysis["ats_score"],
        "analysis": analysis,
    }

@app.get("/api/resumes/{user_id}")
async def get_resumes(user_id: str):
    conn = get_db()
    rows = conn.execute("SELECT * FROM resumes WHERE user_id=? ORDER BY uploaded_at DESC", (user_id,)).fetchall()
    conn.close()
    resumes = []
    for row in rows:
        item = dict(row)
        try:
            item["analysis"] = json.loads(item.get("analysis_json") or "{}")
        except json.JSONDecodeError:
            item["analysis"] = {}
        resumes.append(item)
    return resumes

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


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

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
    return FileResponse("public/login.html", headers={"Cache-Control": "no-cache"})

# ── Static Files (MUST be last) ─────────────────────────────────────
app.mount("/", CachedStaticFiles(directory="public", html=True), name="public")
