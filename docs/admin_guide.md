# Administrator guide

## Setup and start
1. Install Python 3.12 and open the project folder in a terminal.
2. Create the environment and install packages:
   ```
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. (Optional) create the sample files: `python make_fixtures.py`
4. Start the server: `uvicorn app.main:app --reload`
5. Open `http://localhost:8000`.

On first start the database `privacylab.db` and a signing key `.secret_key` are created, together
with three demo accounts:

| Username | Password | Role |
|---|---|---|
| admin | Admin#12345 | admin |
| analyst | Analyst#12345 | analyst |
| viewer | Viewer#12345 | viewer |

These are demo credentials for evaluation only (see limitations).

## Admin page (`/admin`)
### Small-group threshold
Groups with fewer people than this value are hidden from results. Default 5, allowed range 2 to 50.
1. Enter the new value and click **Change**.
2. Confirm the pop-up. The change is saved in the database and survives restarts.
3. Because the release rule changed, an identical query is treated as new and spends budget; old
   saved answers made under the old rule are not reused.
Lowering the threshold weakens privacy; raise it for sensitive data.

### Privacy budgets
Every dataset starts with a budget of 5.0 epsilon. In the budget table type a new value and click
**Set**, then confirm. The budget must be above 0, at most 100, and not lower than what has already
been spent (`E_BUDGET_BELOW_SPENT`).

### Audit log
The table shows the latest 200 events. Filter by action, outcome or user.
| Action | Meaning |
|---|---|
| login, logout | Sign-ins and sign-outs; outcomes success, failure, rate_limited |
| upload | Dataset upload; success or rejected with the error codes |
| query | Query released (success), repeated (repeat_cached), refused (denied, rejected, rate_limited) |
| access_denied | A user tried something their role does not allow |
| csrf_block | A request without the required security header |
| config_change | Admin changed the threshold or a budget; detail shows old and new value |
| accuracy_report, export | Admin report run, sanitized report downloaded |
| server_error | Unexpected failure (type only, no stack trace) |
The log never contains passwords, file contents or raw data.

### Accuracy comparison (`/accuracy`)
Choose a dataset, operation and mechanism and click **Compare**. The system repeats the noise 500
times per group at several epsilon values and reports mean error, RMSE, 95th percentile error and
relative error against the true answers, plus the run time. It spends no budget, shows true values,
and is available to admins only.

## Reviewing a decision
Each released result stores its mechanism, epsilon, sensitivity rule, clamping bounds, group-size
rule and risk rules version, so any result can be reproduced and explained.

## Backup
Copy `privacylab.db` and the `data/` folder while the server is stopped. Keep `.secret_key` private.

## Recovery instructions
| Problem | Fix |
|---|---|
| Server will not start | Read the last line of the error. Check that the virtual environment is active and `pip install -r requirements.txt` finished |
| Port already in use | `pkill -f uvicorn`, then start again |
| Everyone logged out after restart | Expected if `.secret_key` was deleted; log in again |
| Locked out after 5 wrong passwords | Wait 5 minutes, or restart the server |
| Forgot demo passwords | Reset them (keeps all data), see below |
| Database damaged | Stop the server, restore the backup of `privacylab.db`; if none, delete `privacylab.db` (all datasets and history are lost) and restart; demo accounts are recreated |
| Restart | Budgets, saved results, settings and the audit log are kept in the database, so nothing is lost on a normal restart |

Reset the demo passwords:
```
python - <<'EOF'
from app.db import init_db, get_conn
from app.auth import hash_password
init_db()
conn = get_conn()
for u, p, r in [("admin", "Admin#12345", "admin"), ("analyst", "Analyst#12345", "analyst"), ("viewer", "Viewer#12345", "viewer")]:
    conn.execute("DELETE FROM users WHERE username = ?", (u,))
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?,?,?)", (u, hash_password(p), r))
conn.commit()
EOF
```

## Running the tests
`pytest -q` (about one minute). Tests use a temporary database and never touch real data.