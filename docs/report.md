# PrivacyLab: A Differentially Private Analytics Portal

Information Security course, Class 1, Group 6, Proposal 06
Student(s): [your name and ID; teammates if they contributed]
Submission date: 25 November 2026
Repository: https://github.com/usvabukhari07-commits/PrivacyLab

## Abstract
PrivacyLab is a locally runnable web system that publishes aggregate statistics from uploaded CSV
files without exposing individuals. It validates uploads, answers count, sum and mean queries with
Laplace or Gaussian noise, tracks a per-dataset privacy budget (epsilon) that is enforced on the
server, protects against repeated-query averaging and small-group disclosure, and explains the
privacy risk of every release. Three roles (admin, analyst, viewer) are enforced server-side, and
every security-relevant action is written to an append-only audit log. The system is verified by
99 automated tests, all passing, covering the six functional requirements, the mandatory cases
T1 to T4 and T-final, and authorization, injection, CSRF, rate-limit and recovery behaviour.
Average query decision latency is 15.6 ms.

## 1. Problem and purpose
Organisations hold sensitive records but still need to share statistics. Releasing exact aggregates
can leak facts about individuals, especially when the same question is asked many times or when a
group is small. Differential privacy limits what any released answer reveals about one person by
adding calibrated random noise, and bounds the total leakage with a privacy budget. The purpose of
this project is a small, understandable system that takes controlled input, applies this protection,
explains each decision, and keeps enough evidence for a reviewer to reproduce it.

## 2. Objectives
1. Provide a complete input-to-result workflow: upload, validate, query, noise, budget, explain.
2. Make every decision explainable: each result shows its mechanism, epsilon, sensitivity rule,
   clamping bounds, group-size rule and risk rules (`app/engine/risk.py`).
3. Protect data, credentials, sessions, uploads and logs according to a threat model
   (`docs/threat_model.md`).
4. Measure effectiveness with repeatable positive, negative, edge-case and misuse tests
   (`docs/test_results.md`).

## 3. Background: differential privacy in brief
- **Epsilon** measures the privacy cost of a release; smaller epsilon means more noise and
  stronger privacy.
- **Sensitivity** is the most one person can change the true answer. It sets the noise size.
- **Laplace mechanism**: noise with scale = sensitivity / epsilon.
- **Gaussian mechanism**: noise with standard deviation sensitivity x sqrt(2 ln(1.25/delta)) / epsilon,
  valid for epsilon below 1, with delta = 1e-5.
- **Composition**: privacy costs of several releases add up, so a total budget is enforced.
- **Post-processing and repeats**: repeating a query and averaging answers removes noise, so repeats
  must not produce fresh noise.

## 4. Requirements and architecture
### 4.1 Functional requirements
| ID | Requirement | Implementation |
|---|---|---|
| FR-1 | CSV schema validation | `app/engine/schema.py` |
| FR-2 | Query builder | `app/engine/query.py` |
| FR-3 | Laplace/Gaussian noise | `app/engine/mechanisms.py` |
| FR-4 | Epsilon ledger | `app/engine/ledger.py` |
| FR-5 | Accuracy comparison | `app/engine/accuracy.py` |
| FR-6 | Privacy-risk explanation | `app/engine/risk.py` |

### 4.2 Layered design
1. Browser interface: plain HTML and JavaScript pages in `static/` (login, dashboard, query,
   accuracy, admin).
2. API and service layer: FastAPI routes in `app/main.py` handling authentication, authorization,
   business rules and safe errors.
3. Security engine: independently testable functions in `app/engine/` with no web code.
4. Repository layer: SQLite in `app/db.py`, including the append-only audit log.
5. Test fixtures: sanitized sample data in `fixtures/` and the pytest suite in `tests/`.

### 4.3 Roles
| Role | Permissions |
|---|---|
| Admin | Configure budgets and thresholds, view audit log, run accuracy reports, plus analyst functions |
| Analyst | Upload data, run queries, export sanitized report |
| Viewer | View released noisy results only |

### 4.4 Data-flow and trust boundaries
See `docs/data_flow_diagram.md` and `docs/data_flow_diagram.png`. Boundary 1 separates the untrusted
browser from the server; boundary 2 separates the server from storage.

## 5. Implementation
### 5.1 CSV validation (FR-1)
The server checks the extension, size (2 MB), emptiness, binary content, UTF-8 encoding, header
shape (at most 20 columns, unique names, safe characters), row count (at most 10,000), declared
bounds for numeric columns, numeric content, and text cells that start with `=`, `+`, `-` or `@`.
Every rejection returns a stable code such as `E_FORMULA_INJECTION`. Files are stored under
server-generated identifiers, and only error codes, never file contents, reach the audit log.
Evidence: `tests/test_schema.py`; `docs/screenshots/02_upload_accepted.png`,
`03_upload_formula_rejected.png`, `04_upload_oversized_rejected.png`.

### 5.2 Query builder (FR-2)
Only three operations (count, sum, mean), declared numeric columns and text group-by columns are
accepted; there is no free-form SQL. Values are clamped to the bounds declared at upload so that
sensitivity is well defined: count 1, sum max(|min|,|max|), mean (max - min) / group size.
Groups smaller than the threshold (default 5) are suppressed.
Evidence: `tests/test_queries.py`; `docs/screenshots/05_query_result_with_risk.png`.

### 5.3 Noise (FR-3)
Laplace and Gaussian noise are drawn from a generator seeded by operating-system entropy.
Epsilon must be between 0.01 and 2.0 per query, and below 1 for the Gaussian mechanism.
Evidence: `tests/test_mechanisms.py`.

### 5.4 Epsilon ledger (FR-4)
Each dataset starts with a budget of 5.0. Checking and deducting happen in one locked database
transaction, so concurrent requests cannot overspend. Denied queries release nothing. The first
noisy answer to a query is stored and returned for identical repeats at no cost, for every user.
Evidence: tests T1 and T2; `docs/screenshots/06_T1_budget_exhausted.png`,
`07_T2_repeat_cached.png`.

### 5.5 Accuracy comparison (FR-5)
For a chosen query the admin page repeats the noise 500 times per group at epsilon 0.1, 0.25, 0.5,
1.0 and 2.0 and reports mean absolute error, RMSE, 95th percentile error and relative error against
the true values, plus run time. It spends no budget and is admin-only because it shows true values.
Evidence: `docs/screenshots/08_T3_accuracy_table.png`.

### 5.6 Privacy-risk explanation (FR-6)
Six named rules produce LOW, MEDIUM or HIGH with a reason and a recommended action:
| Rule | Checks |
|---|---|
| R1 budget usage | share of the budget used (50% medium, 80% high) |
| R2 epsilon size | per-query epsilon (above 0.5 medium, above 1.0 high) |
| R3 small groups | groups hidden, or every shown group is large enough |
| R4 noise vs value | noise large compared with the released value (utility warning) |
| R5 repeat query | saved answer reused, no extra privacy spent |
| R6 mechanism | Gaussian (epsilon, delta) note |
The rules version and thresholds are stored with each explanation, so decisions can be reproduced.
Evidence: `tests/test_risk.py`.

### 5.7 Administration and audit
Admins can change the small-group threshold (2 to 50) and dataset budgets, with a confirmation step,
range checks, a rule that a budget cannot fall below what is already spent, and an audit entry
recording the old and new value. Because the threshold is part of each query's fingerprint, a changed
rule produces a fresh release instead of reusing an old one.
Evidence: `docs/screenshots/11_admin_threshold_change.png`, `12_audit_log_filtered.png`.

## 6. Security design
| Control | Where |
|---|---|
| bcrypt password hashing | `app/auth.py` |
| Signed session cookie, 30-minute expiry, SameSite strict | `app/main.py` |
| Server-side role checks on every endpoint, generic denial, denial logged | `app/auth.py` |
| CSRF header required on all state-changing requests | `app/main.py` middleware |
| Rate limits: 5 failed logins per 5 minutes, 10 uploads and 30 queries per minute | `app/ratelimit.py` |
| Parameterized SQL, whitelisted query options | `app/db.py`, `app/engine/query.py` |
| Safe errors: stable codes, no stack traces, failures logged by type | `app/main.py` |
| Append-only audit log without passwords or raw data | `app/db.py` |
| Secrets (`.secret_key`, database, uploads) excluded from Git | `.gitignore` |
| Security headers (nosniff, frame deny, no-store on API) | `app/main.py` |

The threat model lists 17 threats with mitigations and the test that demonstrates each
(`docs/threat_model.md`).

## 7. Evaluation
### 7.1 Overall results
| Measure | Result | Evidence |
|---|---|---|
| Automated tests | 99 total, 99 passed (100%), required 80% | `docs/test_results.md`, `docs/pytest_output.txt`, `screenshots/16_pytest_99_passed.png` |
| Clean-install run from the repository | 99 passed | repeated from a fresh clone |
| Unresolved critical defects (authorization, injection, secret exposure, unsafe file handling) | 0 | `docs/test_results.md` |
| Average query decision latency | 15.6 ms (maximum 47.6 ms, 20 queries) | `test_decision_latency_is_reported` |

### 7.2 Mandatory cases
| Case | Result | Evidence |
|---|---|---|
| T1 budget exhaustion | Third 2.0 query on a 5.0 budget denied with `E_BUDGET_EXHAUSTED`; 30 concurrent 0.5 charges allow exactly 10; PASS | `test_T1_*`; screenshot 06 |
| T2 repeated-query protection | Ten repeats return the identical saved answer at zero cost; PASS | `test_T2_*`; screenshot 07 |
| T3 accuracy and error | Mean absolute error of a count is within 15% of 1/epsilon at all five epsilons and falls as epsilon grows; PASS | `test_T3_*`; screenshot 08 |
| T4 small-group disclosure | A group of 3 is hidden and its name never appears; threshold 31 hides every group; PASS | `test_T4_*`; screenshot 09 |
| T-final | Malformed and oversized input rejected, unauthorized requests denied and logged, repeated submissions rate limited, unexpected error handled safely, state preserved across restart; PASS | `docs/test_results.md` (T-final table) |

### 7.3 Accuracy measurements (T3)
Count query grouped by department (4 groups of 50), 500 trials per group:
| Epsilon | Expected mean abs error (1/epsilon) | Measured mean abs error | RMSE | Mean relative error % |
|---|---|---|---|---|
| 0.1 | 10.0 | [copy from screenshot 08] | [ ] | [ ] |
| 0.25 | 4.0 | [ ] | [ ] | [ ] |
| 0.5 | 2.0 | [ ] | [ ] | [ ] |
| 1.0 | 1.0 | [ ] | [ ] | [ ] |
| 2.0 | 0.5 | [ ] | [ ] | [ ] |

The measurements follow the theory: halving epsilon doubles the error, and the privacy gained at
small epsilon costs accuracy, which is the central trade-off of differential privacy.

### 7.4 Demonstration of administrative traceability
The admin raised the small-group threshold from 5 to 31. The same query then produced a new release
with all groups hidden, and the audit log recorded who changed it and the old and new values.
Evidence: `test_admin_changes_threshold_and_the_change_is_traceable`; screenshots 11 and 12.

### 7.5 Issues found while testing
One test failed in the first full run because it searched the exported report for the word
"password", which appears in the report's own disclaimer. The test was corrected to look for password
hashes and real passwords, and the full suite then passed (`docs/test_results.md`, defects table).

## 8. Limitations
See `docs/limitations_ethics.md`. The main ones: plain HTTP and fixed demo passwords (local demo),
unencrypted storage, in-memory rate-limit counters, basic composition accounting, floating-point
noise sampling, and suppression decided from true group sizes.

## 9. Ethics
Only synthetic sample data is used. Hiding small groups protects individuals but also makes small
communities invisible, so thresholds must balance privacy and fair representation. Administrators hold
power to weaken privacy, so their changes are confirmed and permanently logged. No external system was
targeted in testing. The use of an AI assistant is described in section 11.

## 10. Conclusion
PrivacyLab meets the six functional requirements and the mandatory evaluation cases. Its main
contribution is a privacy budget that is actually enforced on the server, with protection against
repeated queries and small groups, explanations for every decision, and traceable administration.
Future work: HTTPS, forced password change, advanced composition accounting, hardened noise sampling,
and per-person budgets.

## 11. Team and use of AI assistance
[Fill in: who did what. For example: "Implementation, testing and documentation by [name]; teammates
contributed [what]."]
[Fill in according to your course rules, for example: "An AI assistant (Claude) was used for code
suggestions, test drafting and document drafting. The author ran, tested and reviewed all code and is
responsible for the submission."]

## 12. Evidence index
| Claim | Evidence |
|---|---|
| All six functional requirements work | `tests/`, screenshots 02, 05, 06, 08 |
| Budget exhaustion is enforced | `test_T1_*`, screenshot 06 |
| Repeats cannot weaken privacy | `test_T2_*`, screenshot 07 |
| Accuracy follows theory | `test_T3_*`, screenshot 08, section 7.3 |
| Small groups are protected | `test_T4_*`, screenshot 09 |
| Authorization is enforced server-side | `test_T_final_*`, screenshots 10 and 12 |
| CSRF protection | `test_csrf_header_is_required_for_state_changing_requests`, screenshot 14 |
| Brute-force protection | `test_T_final_repeated_failed_logins_are_rate_limited`, screenshot 15 |
| Admin changes are traceable | `test_admin_*`, screenshots 11 and 12 |
| Export is sanitized | `test_export_is_sanitized`, screenshot 13 |
| Performance | 15.6 ms average, `test_decision_latency_is_reported` |
| Reproducible from a clean install | README setup, repeated from a fresh clone: 99 passed |