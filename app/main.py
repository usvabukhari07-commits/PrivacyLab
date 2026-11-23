import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from app import ratelimit as rl
from app.db import init_db, get_conn, log_event
from app.auth import hash_password, verify_password, current_user, require_role
from app.engine.schema import validate_csv, MAX_BYTES
from app.engine.query import validate_spec, query_hash, run_query, CONFIG
from app.engine.ledger import charge, BudgetExhausted
from app.engine.risk import explain_risk, RULES_VERSION
from app.engine.accuracy import compare

app = FastAPI(title="PrivacyLab")


def load_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    path = ".secret_key"
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    os.chmod(path, 0o600)   # only the owner can read it
    return key


SECRET_KEY = load_secret_key()
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=1800,          # sessions expire after 30 minutes
    same_site="strict",
    https_only=False,      # localhost demo only
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- Security middleware ----------

@app.middleware("http")
async def security_guard(request: Request, call_next):
    # CSRF defence: state-changing API calls must carry a header that only our own pages send
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
        if request.headers.get("x-requested-with") != "PrivacyLab":
            log_event(None, "csrf_block", "denied", request.url.path[:100])
            return JSONResponse(status_code=403, content={"detail": "Access denied"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Safe failure: log the type only, never return a stack trace
    log_event(None, "server_error", "failure", f"{request.url.path[:80]} {type(exc).__name__}")
    return JSONResponse(status_code=500, content={"detail": "Internal error (E_INTERNAL)"})


# ---------- Startup ----------

def load_settings():
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'min_group_size'").fetchone()
    conn.close()
    if row:
        CONFIG["min_group_size"] = int(row["value"])


@app.on_event("startup")
def startup():
    init_db()
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        demo_users = [
            ("admin", "Admin#12345", "admin"),
            ("analyst", "Analyst#12345", "analyst"),
            ("viewer", "Viewer#12345", "viewer"),
        ]
        for username, pw, role in demo_users:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                (username, hash_password(pw), role),
            )
        conn.commit()
    conn.close()
    load_settings()


class LoginRequest(BaseModel):
    username: str
    password: str


# ---------- Pages ----------

@app.get("/")
def home():
    return FileResponse("static/login.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse("static/dashboard.html")


@app.get("/query")
def query_page():
    return FileResponse("static/query.html")


@app.get("/accuracy")
def accuracy_page():
    return FileResponse("static/accuracy.html")


@app.get("/admin")
def admin_page():
    return FileResponse("static/admin.html")


# ---------- Authentication ----------

@app.post("/api/login")
def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    key = f"login:{ip}|{body.username.lower()[:50]}"

    # Rate limit: 5 failed attempts per 5 minutes per user and address
    if rl.is_limited(key, 5, 300):
        log_event(body.username[:50], "login", "rate_limited")
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.")

    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (body.username,)).fetchone()
    conn.close()

    if row and verify_password(body.password, row["password_hash"]):
        rl.reset(key)
        request.session["user"] = {"username": row["username"], "role": row["role"]}
        log_event(row["username"], "login", "success")
        return {"ok": True, "role": row["role"]}

    rl.record(key)
    # Generic message: don't reveal whether the username exists
    log_event(body.username[:50], "login", "failure")
    raise HTTPException(status_code=401, detail="Invalid username or password")


@app.post("/api/logout")
def logout(request: Request):
    user = request.session.get("user")
    if user:
        log_event(user["username"], "logout", "success")
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/audit")
def audit(action: Optional[str] = None, outcome: Optional[str] = None, username: Optional[str] = None,
          user=Depends(require_role("admin"))):
    sql = "SELECT timestamp, username, action, outcome, detail FROM audit_log"
    clauses, params = [], []
    # Column names come from this fixed list; values are always parameterized
    for col, val in (("action", action), ("outcome", outcome), ("username", username)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val[:50])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT 200"
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Datasets (FR-1) ----------

@app.post("/api/datasets")
async def upload_dataset(
    file: UploadFile = File(...),
    bounds: str = Form(""),
    user=Depends(require_role("admin", "analyst")),
):
    if not rl.check(f"upload:{user['username']}", 10, 60):
        log_event(user["username"], "upload", "rate_limited")
        raise HTTPException(status_code=429, detail=["E_RATE_LIMIT: too many uploads, wait a minute"])

    raw = await file.read(MAX_BYTES + 1)   # never read more than the limit
    filename = os.path.basename(file.filename or "")[:100]
    result = validate_csv(raw, filename, bounds)

    if not result["ok"]:
        codes = ",".join(e.split(":")[0] for e in result["errors"])
        log_event(user["username"], "upload", "rejected", codes[:200])
        raise HTTPException(status_code=422, detail=result["errors"])

    dataset_id = uuid.uuid4().hex          # server-generated ID
    os.makedirs("data", exist_ok=True)
    with open(f"data/{dataset_id}.csv", "wb") as f:
        f.write(raw)

    conn = get_conn()
    conn.execute(
        "INSERT INTO datasets (id, owner, filename, row_count, columns, bounds, created_at) VALUES (?,?,?,?,?,?,?)",
        (
            dataset_id, user["username"], filename, result["rows"],
            json.dumps(result["columns"]), json.dumps(result["bounds"]),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()
    log_event(user["username"], "upload", "success", f"dataset={dataset_id} rows={result['rows']}")
    return {"id": dataset_id, "rows": result["rows"], "columns": result["columns"],
            "warnings": result["warnings"]}


@app.get("/api/datasets")
def list_datasets(user=Depends(require_role("admin", "analyst"))):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, filename, row_count, columns, epsilon_budget, epsilon_spent, created_at "
        "FROM datasets ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Private queries (FR-2, FR-3, FR-4, FR-6) ----------

query_lock = threading.Lock()   # serializes cache check + charge + store


class QueryRequest(BaseModel):
    dataset_id: str
    operation: str
    column: Optional[str] = None
    group_by: Optional[str] = None
    epsilon: float
    mechanism: str = "laplace"


@app.post("/api/query")
def run_dp_query(body: QueryRequest, user=Depends(require_role("admin", "analyst"))):
    if not rl.check(f"query:{user['username']}", 30, 60):
        log_event(user["username"], "query", "rate_limited")
        raise HTTPException(status_code=429, detail=["E_RATE_LIMIT: too many queries, wait a minute"])

    conn = get_conn()
    ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (body.dataset_id,)).fetchone()
    conn.close()
    if ds is None:
        log_event(user["username"], "query", "rejected", "E_DATASET_NOT_FOUND")
        raise HTTPException(status_code=404, detail=["E_DATASET_NOT_FOUND: dataset not found"])

    columns = json.loads(ds["columns"])
    bounds = json.loads(ds["bounds"])
    spec, errors = validate_spec(body.model_dump(exclude={"dataset_id"}), columns, bounds)
    if errors:
        codes = ",".join(e.split(":")[0] for e in errors)
        log_event(user["username"], "query", "rejected", f"{codes} dataset={ds['id']}")
        raise HTTPException(status_code=422, detail=errors)

    qhash = query_hash(ds["id"], spec)

    with query_lock:
        # 1. Repeated-query protection: return the saved answer, charge nothing
        conn = get_conn()
        cached = conn.execute(
            "SELECT id, result, evidence FROM queries WHERE dataset_id = ? AND query_hash = ?",
            (ds["id"], qhash),
        ).fetchone()
        ds_now = conn.execute(
            "SELECT epsilon_budget, epsilon_spent FROM datasets WHERE id = ?", (ds["id"],)
        ).fetchone()
        conn.close()
        if cached:
            out = json.loads(cached["result"])
            evidence = json.loads(cached["evidence"])
            remaining = ds_now["epsilon_budget"] - ds_now["epsilon_spent"]
            evidence["budget_remaining"] = round(remaining, 4)
            explanation = explain_risk(spec, evidence, out["rows"], out["suppressed_groups"],
                                       remaining, ds_now["epsilon_budget"], True)
            log_event(user["username"], "query", "repeat_cached",
                      f"dataset={ds['id']} query={cached['id']} risk={explanation['risk_level']}")
            return {
                "query_id": cached["id"], "cached": True, "epsilon_charged": 0,
                "budget_remaining": round(remaining, 4),
                "rows": out["rows"], "suppressed_groups": out["suppressed_groups"],
                "evidence": evidence, "explanation": explanation,
            }

        # 2. Compute the noisy answer (not released yet)
        df = pd.read_csv(f"data/{ds['id']}.csv", dtype=str, keep_default_na=False)
        outcome = run_query(df, spec, bounds)

        # 3. Charge the budget; refuse if it would be exceeded
        try:
            remaining = charge(ds["id"], spec["epsilon"])
        except BudgetExhausted as e:
            log_event(user["username"], "query", "denied",
                      f"E_BUDGET_EXHAUSTED dataset={ds['id']} requested={spec['epsilon']} remaining={e.remaining:.4f}")
            raise HTTPException(status_code=403, detail=[
                f"E_BUDGET_EXHAUSTED: requested {spec['epsilon']}, only {round(e.remaining, 4)} left"
            ])

        # 4. Save the result so repeats return the same answer
        qid = uuid.uuid4().hex
        evidence = outcome["evidence"]
        evidence["budget_remaining"] = round(remaining, 4)
        conn = get_conn()
        conn.execute(
            "INSERT INTO queries (id, dataset_id, username, query_hash, spec, epsilon, mechanism, result, evidence, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (qid, ds["id"], user["username"], qhash, json.dumps(spec), spec["epsilon"], spec["mechanism"],
             json.dumps({"rows": outcome["rows"], "suppressed_groups": outcome["suppressed_groups"]}),
             json.dumps(evidence), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        conn.close()

    explanation = explain_risk(spec, evidence, outcome["rows"], outcome["suppressed_groups"],
                               remaining, ds["epsilon_budget"], False)
    log_event(user["username"], "query", "success",
              f"dataset={ds['id']} query={qid} op={spec['operation']} eps={spec['epsilon']} risk={explanation['risk_level']}")
    return {
        "query_id": qid, "cached": False, "epsilon_charged": spec["epsilon"],
        "budget_remaining": round(remaining, 4),
        "rows": outcome["rows"], "suppressed_groups": outcome["suppressed_groups"],
        "evidence": evidence, "explanation": explanation,
    }


# ---------- Released results (all logged-in roles, noisy values only) ----------

@app.get("/api/results")
def list_results(user=Depends(current_user)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT q.id, q.created_at, q.spec, q.result, d.filename "
        "FROM queries q JOIN datasets d ON d.id = q.dataset_id "
        "ORDER BY q.created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        spec = json.loads(r["spec"])
        res = json.loads(r["result"])
        out.append({
            "id": r["id"], "created_at": r["created_at"], "dataset": r["filename"],
            "operation": spec["operation"], "column": spec["column"], "group_by": spec["group_by"],
            "epsilon": spec["epsilon"], "mechanism": spec["mechanism"],
            "rows": res["rows"], "suppressed_groups": res["suppressed_groups"],
        })
    return out


# ---------- Accuracy comparison (FR-5, admin only) ----------

class AccuracyRequest(BaseModel):
    dataset_id: str
    operation: str
    column: Optional[str] = None
    group_by: Optional[str] = None
    mechanism: str = "laplace"


@app.post("/api/accuracy")
def accuracy_report(body: AccuracyRequest, user=Depends(require_role("admin"))):
    conn = get_conn()
    ds = conn.execute("SELECT * FROM datasets WHERE id = ?", (body.dataset_id,)).fetchone()
    conn.close()
    if ds is None:
        raise HTTPException(status_code=404, detail=["E_DATASET_NOT_FOUND: dataset not found"])

    columns = json.loads(ds["columns"])
    bounds = json.loads(ds["bounds"])
    raw = body.model_dump(exclude={"dataset_id"})
    raw["epsilon"] = 0.5   # placeholder: the report tests several epsilons itself
    spec, errors = validate_spec(raw, columns, bounds)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    df = pd.read_csv(f"data/{ds['id']}.csv", dtype=str, keep_default_na=False)
    result = compare(df, spec, bounds)
    log_event(user["username"], "accuracy_report", "success",
              f"dataset={ds['id']} op={spec['operation']} runtime_ms={result['runtime_ms']}")
    return result


# ---------- Admin controls (high-impact: admin only, confirmation required) ----------

@app.get("/api/admin/config")
def admin_config(user=Depends(require_role("admin"))):
    return {"min_group_size": CONFIG["min_group_size"]}


class ThresholdChange(BaseModel):
    min_group_size: int
    confirm: bool = False


@app.post("/api/admin/min-group-size")
def change_min_group_size(body: ThresholdChange, user=Depends(require_role("admin"))):
    if not body.confirm:
        raise HTTPException(status_code=400, detail=["E_CONFIRM_REQUIRED: confirmation missing"])
    if not (2 <= body.min_group_size <= 50):
        log_event(user["username"], "config_change", "rejected", "E_THRESHOLD_RANGE")
        raise HTTPException(status_code=422, detail=["E_THRESHOLD_RANGE: value must be between 2 and 50"])

    old = CONFIG["min_group_size"]
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_by, updated_at) VALUES (?,?,?,?)",
        ("min_group_size", str(body.min_group_size), user["username"],
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()
    CONFIG["min_group_size"] = body.min_group_size
    log_event(user["username"], "config_change", "success",
              f"min_group_size {old} -> {body.min_group_size}")
    return {"min_group_size": body.min_group_size, "previous": old}


class BudgetChange(BaseModel):
    dataset_id: str
    new_budget: float
    confirm: bool = False


@app.post("/api/admin/budget")
def change_budget(body: BudgetChange, user=Depends(require_role("admin"))):
    if not body.confirm:
        raise HTTPException(status_code=400, detail=["E_CONFIRM_REQUIRED: confirmation missing"])
    if not (0 < body.new_budget <= 100):
        raise HTTPException(status_code=422, detail=["E_BUDGET_RANGE: budget must be above 0 and at most 100"])

    conn = get_conn()
    ds = conn.execute("SELECT epsilon_budget, epsilon_spent FROM datasets WHERE id = ?",
                      (body.dataset_id,)).fetchone()
    if ds is None:
        conn.close()
        raise HTTPException(status_code=404, detail=["E_DATASET_NOT_FOUND: dataset not found"])
    cur = conn.execute(
        "UPDATE datasets SET epsilon_budget = ? WHERE id = ? AND epsilon_spent <= ?",
        (body.new_budget, body.dataset_id, body.new_budget),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        log_event(user["username"], "config_change", "rejected",
                  f"E_BUDGET_BELOW_SPENT dataset={body.dataset_id}")
        raise HTTPException(status_code=422, detail=[
            f"E_BUDGET_BELOW_SPENT: {ds['epsilon_spent']} is already spent, budget cannot be lower"])
    log_event(user["username"], "config_change", "success",
              f"dataset={body.dataset_id} budget {ds['epsilon_budget']} -> {body.new_budget}")
    return {"dataset_id": body.dataset_id, "new_budget": body.new_budget}


# ---------- Sanitized export ----------

@app.get("/api/export")
def export_report(user=Depends(require_role("admin", "analyst"))):
    conn = get_conn()
    qs = conn.execute(
        "SELECT q.id, q.created_at, q.username, q.spec, q.result, q.evidence, "
        "d.filename, d.epsilon_budget, d.epsilon_spent "
        "FROM queries q JOIN datasets d ON d.id = q.dataset_id ORDER BY q.created_at DESC LIMIT 200"
    ).fetchall()
    conn.close()

    results = []
    for r in qs:
        res = json.loads(r["result"])
        results.append({
            "query_id": r["id"], "time": r["created_at"], "run_by": r["username"],
            "dataset": r["filename"], "query": json.loads(r["spec"]),
            "released_rows": res["rows"], "groups_suppressed": res["suppressed_groups"],
            "evidence": json.loads(r["evidence"]),
            "budget_status": {"spent": r["epsilon_spent"], "total": r["epsilon_budget"]},
        })

    now = datetime.now(timezone.utc)
    report = {
        "report_type": "PrivacyLab sanitized release report",
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_by": user["username"],
        "risk_rules_version": RULES_VERSION,
        "min_group_size": CONFIG["min_group_size"],
        "note": "Contains only noisy released values. No raw rows, no true values, no passwords.",
        "results": results,
    }
    os.makedirs("reports", exist_ok=True)
    name = f"report_{now.strftime('%Y%m%d_%H%M%S')}.json"
    path = os.path.join("reports", name)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    log_event(user["username"], "export", "success", f"{name} results={len(results)}")
    return FileResponse(path, media_type="application/json", filename=name)