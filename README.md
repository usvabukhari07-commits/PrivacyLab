# PrivacyLab: Differentially Private Analytics Portal

A local web portal that publishes aggregate statistics from uploaded CSV files under differential
privacy. It adds calibrated noise (Laplace or Gaussian), tracks a per-dataset privacy budget
(epsilon ledger), refuses queries when the budget is spent, hides small groups, and explains the
privacy risk of every release. Course project for Information Security (Class 1, Group 6, Proposal 06).

Group members: Syeda Uswa (22L-6241), Areeba Bahadur (22L-7836), Mariah Kashif (22L-7814)

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
If you received this project as a zip file, unzip it, open a terminal in the project folder and
continue from the `python3 -m venv venv` line.

## Run
```bash
uvicorn app.main:app --reload
```
Open http://localhost:8000. The database (`privacylab.db`) and signing key (`.secret_key`) are
created automatically on first start. Stop the server with Control + C.

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
105 automated tests (about one to two minutes) cover all six functional requirements, the mandatory
evaluation cases T1 to T4 and T-final, and authorization, injection, CSRF, rate-limit and recovery
tests. Tests run on a temporary database and never touch real data. Results: `docs/test_results.md`.

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
    ledger.py      FR-4 epsilon budget
    accuracy.py    FR-5 accuracy comparison
    risk.py        FR-6 privacy-risk explanation
static/            browser pages (login, dashboard, query, accuracy, admin)
tests/             pytest suite
fixtures/          sanitized sample data
docs/              threat model, diagrams, guides, test results, report, screenshots
make_fixtures.py   generates the sample CSV files
```

## Documentation
| Document | File |
|---|---|
| Data-flow diagram and trust boundaries | `docs/data_flow_diagram.md` |
| Threat model | `docs/threat_model.md` |
| Test plan and results | `docs/test_results.md` |
| Raw test output | `docs/pytest_output.txt` |
| Screenshots (evidence) | `docs/screenshots/` |
| User guide | `docs/user_guide.md` |
| Administrator guide | `docs/admin_guide.md` |
| Limitations and ethics | `docs/limitations_ethics.md` |
| Demo script | `docs/demo_script.md` |
| Final report | `docs/report.md` |

## Security summary
bcrypt password hashing; signed 30-minute sessions; server-side role checks; CSRF header on every
state-changing request; rate limits on login, uploads and queries; parameterized SQL; strict upload
validation; server-generated identifiers; atomic privacy-budget ledger; append-only audit log with no
passwords or raw data; stable error codes without stack traces; secrets kept out of Git.

## Limitations
Local demo over plain HTTP with fixed demo passwords. See `docs/limitations_ethics.md`.