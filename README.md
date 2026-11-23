# PrivacyLab: Differentially Private Analytics Portal

A local web portal that publishes aggregate statistics from uploaded CSV files under differential
privacy. It adds calibrated noise (Laplace or Gaussian), tracks a per-dataset privacy budget
(epsilon ledger), refuses queries when the budget is spent, hides small groups, and explains the
privacy risk of every release. Course project for Information Security (Class 1, Group 6, Proposal 06).

## Features
- FR-1 CSV schema validation (type, size, structure, bounds, formula-injection checks)
- FR-2 Query builder (count, sum, mean, optional group-by; whitelist only, no free-form SQL)
- FR-3 Laplace and Gaussian noise
- FR-4 Epsilon ledger (atomic budget deduction, exhaustion, repeated-query protection)
- FR-5 Accuracy comparison (error against epsilon, admin only)
- FR-6 Privacy-risk explanation (rules R1 to R6, LOW / MEDIUM / HIGH)
- Roles: admin, analyst, viewer, enforced on the server
- Audit log, CSRF protection, rate limiting, safe errors, sanitized export, admin controls

## Requirements
- Python 3.10 or newer (developed and tested on 3.12)
- macOS, Linux or Windows; no Docker, no paid services, no internet needed after installing packages

## Setup
```bash
git clone https://github.com/usvabukhari07-commits/PrivacyLab.git
cd PrivacyLab
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python make_fixtures.py           # creates sample CSV files in fixtures/
```

## Run
```bash
uvicorn app.main:app --reload
```
Open http://localhost:8000. The database (`privacylab.db`) and signing key (`.secret_key`) are
created automatically on first start.

## Demo accounts
| Username | Password | Role |
|---|---|---|
| admin | Admin#12345 | admin |
| analyst | Analyst#12345 | analyst |
| viewer | Viewer#12345 | viewer |

Demo credentials for evaluation only.

## Quick walkthrough
1. Log in as `analyst`. Upload `fixtures/employees.csv` with bounds `age:18:100,salary:0:300000`.
2. Open "Run private queries": run `count` with epsilon 0.5 and read the evidence and risk boxes.
3. Run the same query again: the saved answer is returned at no cost (repeated-query protection).
4. Spend the budget: run queries until you get `E_BUDGET_EXHAUSTED`.
5. Upload `fixtures/small_groups.csv`, run `count` grouped by `department`: the small group is hidden.
6. Upload `fixtures/bad_formula.csv`: rejected with `E_FORMULA_INJECTION`.
7. Log in as `admin`: open the admin page, change the small-group threshold, then view the audit log.
8. As admin open the accuracy page and click Compare.
9. Log in as `viewer`: only released results are visible; other pages are denied.

## Tests
```bash
pytest -q
```
99 automated tests (about one minute) cover all six functional requirements, the mandatory
evaluation cases T1 to T4 and T-final, and authorization, injection, CSRF, rate-limit and recovery
tests. Tests run on a temporary database. Results: `docs/test_results.md`.

## Project layout
```
app/
  main.py          API routes, middleware, startup
  auth.py          password hashing, sessions, role checks
  db.py            SQLite tables and append-only audit log
  ratelimit.py     rate limiting
  engine/          security engine (no web code)
    schema.py      FR-1 CSV validation
    query.py       FR-2 query builder, clamping, small groups
    mechanisms.py  FR-3 Laplace / Gaussian noise
    ledger.py