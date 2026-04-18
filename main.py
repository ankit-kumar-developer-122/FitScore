from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os, sqlite3, hashlib, uuid, json, re
from datetime import datetime
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

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
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "").strip()
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "").strip()
MATCH_THRESHOLD = int(os.getenv("JOB_MATCH_THRESHOLD", "60"))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_request_user(request: Request) -> sqlite3.Row:
    user_id = (request.headers.get("X-User-Id") or "").strip()
    if not user_id:
        raise HTTPException(401, "Authentication required")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "User not found")
    return user


def require_roles(request: Request, allowed_roles: set[str]) -> sqlite3.Row:
    user = get_request_user(request)
    if user["role"] not in allowed_roles:
        raise HTTPException(403, "You do not have permission to perform this action")
    return user

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
        description TEXT, location TEXT DEFAULT '',
        package_text TEXT DEFAULT '', application_url TEXT DEFAULT '',
        created_at TEXT
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
    CREATE TABLE IF NOT EXISTS notification_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        job_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        status TEXT NOT NULL,
        payload_json TEXT DEFAULT '{}',
        created_at TEXT,
        UNIQUE(user_id, job_id, channel),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    );
    """)
    resume_columns = {row[1] for row in c.execute("PRAGMA table_info(resumes)").fetchall()}
    job_columns = {row[1] for row in c.execute("PRAGMA table_info(jobs)").fetchall()}
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
    if "location" not in job_columns:
        try:
            c.execute("ALTER TABLE jobs ADD COLUMN location TEXT DEFAULT ''")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    if "package_text" not in job_columns:
        try:
            c.execute("ALTER TABLE jobs ADD COLUMN package_text TEXT DEFAULT ''")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    if "application_url" not in job_columns:
        try:
            c.execute("ALTER TABLE jobs ADD COLUMN application_url TEXT DEFAULT ''")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    # Seed data if empty
    if c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0:
        now = datetime.utcnow().isoformat()
        jobs = [
            ("Senior Frontend Engineer","Vercel","$150k",95,"active",'["JavaScript","React","CSS"]',"3+ yrs","Build next-gen web UIs","Remote","15-18 LPA","https://vercel.com/careers",now),
            ("Data Scientist","OpenAI","$180k",88,"active",'["Python","ML","Statistics"]',"2+ yrs","Work on cutting-edge AI models","San Francisco, CA","22-28 LPA","https://openai.com/careers",now),
            ("Backend Engineer","Stripe","$160k",82,"active",'["Python","Go","SQL"]',"4+ yrs","Design payment infrastructure","Bengaluru","18-24 LPA","https://stripe.com/jobs",now),
            ("Product Designer","Figma","$140k",78,"active",'["Figma","UI/UX","Prototyping"]',"2+ yrs","Shape the future of design tools","London","14-18 LPA","https://www.figma.com/careers/",now),
            ("ML Engineer","DeepMind","$200k",92,"active",'["Python","TensorFlow","Research"]',"3+ yrs","Push boundaries of AI research","Mountain View, CA","25-32 LPA","https://deepmind.google/about/careers/",now),
            ("DevOps Lead","Netflix","$170k",75,"active",'["AWS","Kubernetes","Terraform"]',"5+ yrs","Scale global streaming infra","Remote","20-26 LPA","https://jobs.netflix.com/",now),
        ]
        c.executemany("INSERT INTO jobs (title,company,salary,match_pct,status,skills,experience,description,location,package_text,application_url,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", jobs)
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
        suggestions.append("Add email, phone, and LinkedIn at the top.")
    if "projects" not in sections_found:
        suggestions.append("Add a Projects section with tools and outcomes.")
    if metrics_count < 3:
        suggestions.append("Add numbers like %, time saved, revenue, or users served.")
    if len(keywords_found) < 5:
        suggestions.append("Match more job keywords from the target role.")
    if len(action_verbs_found) < 4:
        suggestions.append("Start bullets with strong verbs like built, led, or improved.")
    if word_count < 350:
        suggestions.append("Add more relevant detail to reach stronger ATS coverage.")

    bonus_suggestions = []
    if "summary" not in sections_found:
        bonus_suggestions.append("Add a 2-line summary tailored to the role.")
    if len(keywords_found) >= 5:
        bonus_suggestions.append("Mirror exact skill names from the job description.")
    if metrics_count >= 3:
        bonus_suggestions.append("Move your strongest quantified wins to the top third.")
    if "skills" in sections_found:
        bonus_suggestions.append("Group skills by language, framework, cloud, and tools.")
    if not github_present:
        bonus_suggestions.append("Add GitHub or portfolio links if they support the role.")

    suggestions.extend(item for item in bonus_suggestions if item not in suggestions)

    return {
        "ats_score": score,
        "word_count": word_count,
        "keywords_found": keywords_found,
        "sections_found": sections_found,
        "metrics_count": metrics_count,
        "action_verbs_found": action_verbs_found,
        "suggestions": suggestions[:5],
    }


def normalize_skill_terms(raw_skills) -> set[str]:
    if isinstance(raw_skills, str):
        try:
            raw_skills = json.loads(raw_skills)
        except json.JSONDecodeError:
            raw_skills = [item.strip() for item in raw_skills.split(",") if item.strip()]
    if not isinstance(raw_skills, list):
        return set()
    return {str(skill).strip().lower() for skill in raw_skills if str(skill).strip()}


def get_user_match_profile(conn: sqlite3.Connection, user_row: sqlite3.Row) -> dict:
    stored_skills = normalize_skill_terms(user_row["skills"] or "[]")
    latest_resume = conn.execute(
        "SELECT ats_score, analysis_json FROM resumes WHERE user_id=? ORDER BY uploaded_at DESC LIMIT 1",
        (user_row["id"],)
    ).fetchone()
    resume_analysis = {}
    if latest_resume and latest_resume["analysis_json"]:
        try:
            resume_analysis = json.loads(latest_resume["analysis_json"])
        except json.JSONDecodeError:
            resume_analysis = {}
    resume_keywords = {str(item).strip().lower() for item in resume_analysis.get("keywords_found", []) if str(item).strip()}
    combined_skills = sorted(stored_skills | resume_keywords)
    return {
        "skills": combined_skills,
        "ats_score": int((latest_resume["ats_score"] if latest_resume and latest_resume["ats_score"] is not None else user_row["ats_score"]) or 0),
    }


def calculate_job_match(job_skills: set[str], user_profile: dict) -> int:
    user_skills = set(user_profile["skills"])
    if not user_skills:
        return 0
    overlap = len(job_skills & user_skills)
    skill_score = int((overlap / max(1, len(job_skills))) * 70) if job_skills else 0
    ats_bonus = min(30, int(user_profile["ats_score"] * 0.3))
    return min(100, skill_score + ats_bonus)


def build_match_payload(user_row: sqlite3.Row, job_row: sqlite3.Row, match_score: int, user_profile: dict) -> dict:
    return {
        "user": {
            "id": user_row["id"],
            "name": user_row["name"],
            "email": user_row["email"],
            "role": user_row["role"],
            "ats_score": user_profile["ats_score"],
        },
        "job": {
            "id": job_row["id"],
            "title": job_row["title"],
            "company": job_row["company"],
            "salary": job_row["salary"],
            "location": job_row["location"],
            "package_text": job_row["package_text"],
            "experience": job_row["experience"],
            "description": job_row["description"],
            "application_url": job_row["application_url"],
        },
        "match": {
            "score": match_score,
            "shared_skills": sorted(set(user_profile["skills"]) & normalize_skill_terms(job_row["skills"] or "[]")),
        },
        "sent_at": datetime.utcnow().isoformat(),
    }


def send_n8n_webhook(payload: dict) -> tuple[bool, str]:
    if not N8N_WEBHOOK_URL:
        return False, "N8N webhook URL is not configured"
    req = urlrequest.Request(
        N8N_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"X-FitScore-Secret": N8N_WEBHOOK_SECRET} if N8N_WEBHOOK_SECRET else {})
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as response:
            return True, f"Webhook accepted with status {response.status}"
    except HTTPError as exc:
        return False, f"Webhook HTTP error {exc.code}"
    except URLError as exc:
        return False, f"Webhook connection error: {exc.reason}"


def notify_matches_for_job(conn: sqlite3.Connection, job_id: int, auto_email_only: bool = True) -> dict:
    job_row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job_row:
        raise HTTPException(404, "Job not found")

    user_query = "SELECT * FROM users WHERE role='candidate'"
    if auto_email_only:
        user_query += " AND auto_email=1"
    user_rows = conn.execute(user_query).fetchall()

    job_skills = normalize_skill_terms(job_row["skills"] or "[]")
    notified = []
    skipped = 0

    for user_row in user_rows:
        prior = conn.execute(
            "SELECT 1 FROM notification_logs WHERE user_id=? AND job_id=? AND channel='n8n_email' AND status='sent'",
            (user_row["id"], job_id)
        ).fetchone()
        if prior:
            skipped += 1
            continue

        user_profile = get_user_match_profile(conn, user_row)
        match_score = calculate_job_match(job_skills, user_profile)
        if match_score < MATCH_THRESHOLD:
            continue

        payload = build_match_payload(user_row, job_row, match_score, user_profile)
        ok, message = send_n8n_webhook(payload)
        conn.execute(
            """
            INSERT INTO notification_logs (user_id, job_id, channel, status, payload_json, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(user_id, job_id, channel) DO UPDATE SET
                status=excluded.status,
                payload_json=excluded.payload_json,
                created_at=excluded.created_at
            """,
            (
                user_row["id"],
                job_id,
                "n8n_email",
                "sent" if ok else "failed",
                json.dumps({"payload": payload, "message": message}),
                datetime.utcnow().isoformat(),
            )
        )
        if ok:
            notified.append({
                "user_id": user_row["id"],
                "email": user_row["email"],
                "match_score": match_score,
            })

    return {
        "job_id": job_id,
        "job_title": job_row["title"],
        "notified_count": len(notified),
        "skipped_count": skipped,
        "notified_users": notified,
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
async def create_job(request: Request, title: str = Form(...), company: str = Form(...), salary: str = Form(""), skills: str = Form("[]"), experience: str = Form(""), description: str = Form(""), location: str = Form(""), package_text: str = Form(""), application_url: str = Form("")):
    require_roles(request, {"recruiter"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO jobs (title,company,salary,skills,experience,description,location,package_text,application_url,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (title, company, salary, skills, experience, description, location, package_text, application_url, datetime.utcnow().isoformat())
    )
    job_id = cursor.lastrowid
    notification_result = notify_matches_for_job(conn, job_id)
    conn.commit()
    conn.close()
    return {"ok": True, "job_id": job_id, "notifications": notification_result}

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


@app.post("/api/automation/match-and-notify")
async def match_and_notify(request: Request, job_id: int = Form(...), auto_email_only: int = Form(1)):
    require_roles(request, {"recruiter"})
    conn = get_db()
    result = notify_matches_for_job(conn, job_id, auto_email_only=bool(auto_email_only))
    conn.commit()
    conn.close()
    return result

# ── Workflows ────────────────────────────────────────────────────────
@app.get("/api/workflows")
async def get_workflows(request: Request):
    require_roles(request, {"recruiter"})
    conn = get_db()
    rows = conn.execute("SELECT * FROM workflows").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/recruiter/dashboard")
async def recruiter_dashboard(request: Request, job_id: int | None = None):
    require_roles(request, {"recruiter"})
    conn = get_db()
    jobs = [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, id DESC").fetchall()]
    if not jobs:
        conn.close()
        return {
            "jobs": [],
            "selected_job": None,
            "candidates": [],
            "summary": {"total_jobs": 0, "total_candidates": 0, "shortlisted": 0, "avg_ats": 0},
        }

    selected_job = next((job for job in jobs if job["id"] == job_id), jobs[0] if jobs else None)
    job_skills = normalize_skill_terms(selected_job["skills"] or "[]")
    candidate_rows = conn.execute("SELECT * FROM users WHERE role='candidate'").fetchall()

    ranked_candidates = []
    for candidate in candidate_rows:
        profile = get_user_match_profile(conn, candidate)
        match_score = calculate_job_match(job_skills, profile)
        potential_score = round((match_score * 0.7) + (profile["ats_score"] * 0.3), 1)
        ranked_candidates.append({
            "id": candidate["id"],
            "name": candidate["name"],
            "email": candidate["email"],
            "ats_score": profile["ats_score"],
            "match_score": match_score,
            "potential_score": potential_score,
            "skills": profile["skills"][:8],
            "shared_skills": sorted(set(profile["skills"]) & job_skills),
        })

    ranked_candidates.sort(key=lambda item: (-item["ats_score"], -item["match_score"], item["name"].lower()))
    top_candidates = ranked_candidates[:10]
    high_potential_low_ats = sorted(
        [
            candidate for candidate in ranked_candidates
            if candidate["match_score"] >= 60 and candidate["ats_score"] < 75
        ],
        key=lambda item: (-item["match_score"], -item["potential_score"], item["name"].lower())
    )[:10]
    shortlisted = [candidate for candidate in ranked_candidates if candidate["ats_score"] >= 80]
    avg_ats = round(sum(candidate["ats_score"] for candidate in ranked_candidates) / len(ranked_candidates), 1) if ranked_candidates else 0

    conn.close()
    return {
        "jobs": jobs,
        "selected_job": selected_job,
        "candidates": ranked_candidates,
        "top_candidates": top_candidates,
        "high_potential_low_ats": high_potential_low_ats,
        "summary": {
            "total_jobs": len(jobs),
            "total_candidates": len(ranked_candidates),
            "shortlisted": len(shortlisted),
            "avg_ats": avg_ats,
        },
    }

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
async def db_tables(request: Request):
    require_roles(request, {"recruiter"})
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
