# Demo script (about 13 minutes)

## Before you start (5 minutes earlier)
1. Stop any old server (`pkill -f uvicorn`).
2. For a clean demo: delete `privacylab.db` and the `data/` and `reports/` folders. The app recreates them.
3. Start: `uvicorn app.main:app --reload`, wait for "Application startup complete".
4. Open `http://localhost:8000` in one browser window. Open the data-flow diagram in another tab.
5. Have `fixtures/` open in Finder, and the screenshots folder ready as a backup.
6. Run `python make_fixtures.py` if the fixtures are missing.

## Timeline
| Time | What you do | What you say |
|---|---|---|
| 0:00 to 1:30 | Show the data-flow diagram | "Sensitive CSVs go in, noisy aggregates come out. Zone 1 is untrusted, so everything crossing boundary 1 is checked. Storage is only reachable through the server." |
| 1:30 to 3:00 | Log in as analyst. Upload `employees.csv` with `age:18:100,salary:0:300000` | "Normal case: validated, stored under a server-generated ID, logged." Then upload `bad_formula.csv`: "Adverse case: it names the exact violation, `E_FORMULA_INJECTION`, not just 'unsafe'." |
| 3:00 to 6:00 | Query page: `count`, epsilon 0.5 | "The answer is close to 200 but not exact. The evidence box shows mechanism, epsilon, sensitivity rule. The risk box shows LOW and why." |
| | Run the same query again | "Repeat returns the saved answer and charges nothing, so averaging cannot remove the noise." |
| | Run `mean` of salary epsilon 2.0, then `sum` of age epsilon 2.0, then one more | "Risk goes to HIGH as budget and epsilon grow. Now the budget is exhausted: `E_BUDGET_EXHAUSTED`. Nothing is released." |
| 6:00 to 7:30 | Upload `small_groups.csv`, `count` grouped by department, epsilon 0.5 | "Legal has 3 people, so it is hidden. Even its name does not appear." |
| 7:30 to 9:00 | Open a private window, log in as viewer, open `/api/datasets` | "Viewer only sees released noisy results. A restricted request gets a generic denial." |
| 9:00 to 11:00 | Log in as admin. Admin page: change threshold from 5 to 31, confirm. Back as analyst rerun the small-groups query | "The admin changed one rule. The same query is now a fresh release and every group is hidden." |
| | Admin page: filter the audit log by `config_change` | "Who, when, old and new value: traceable. The log never contains passwords or file contents." Then set the threshold back to 5. |
| 11:00 to 12:00 | Accuracy page: `count`, Compare | "Error follows 1/epsilon: about 10 at epsilon 0.1 and 0.5 at epsilon 2. That is the privacy and accuracy trade-off." |
| 12:00 to 13:00 | Show `screenshots/16_pytest_99_passed.png` and the report's evidence index | "99 tests, all passing: T1 to T4, authorization, CSRF, rate limits, injection, restart recovery. Average decision time 15.6 ms." |
| 13:00 to 14:00 | Limitations slide or file | "Local HTTP demo, fixed demo passwords, basic composition. Next steps: HTTPS, password change at first login, advanced accounting." |

## Backup plan
If the live demo fails, switch to the screenshots in `docs/screenshots/` in table order and say you are showing recorded evidence. Never debug live.

## Likely questions
| Question | Short answer |
|---|---|
| What is epsilon? | The privacy cost of one answer. Smaller means more noise and stronger privacy. The budget caps the total. |
| Why does repeating a query not cost anything? | We return the same saved noisy answer. A new random draw would let an attacker average the noise away. |
| What is sensitivity? | The most one person can change the answer: 1 for a count; for a sum, the larger bound; for a mean, range divided by group size. |
| Why must bounds be declared? | Without bounds, one extreme value could change a sum a lot, so no noise level would be safe. Values are clipped to the bounds. |
| What if the admin lowers the threshold? | It needs confirmation, is range-checked, and is logged with old and new values. A changed rule creates fresh releases. |
| How do you stop CSRF? | Every POST must carry a custom header only our pages send, plus SameSite strict cookies. |
| How are passwords stored? | bcrypt hashes, never in plain text or logs. |
| What are the main weaknesses? | Plain HTTP and demo passwords on localhost, unencrypted storage, basic composition accounting. |
| Did you use AI help? | Answer honestly, as in section 11 of the report. |