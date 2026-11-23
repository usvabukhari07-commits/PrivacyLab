# Threat model: PrivacyLab

## 1. System summary
PrivacyLab is a local web portal that publishes aggregate statistics from uploaded CSV files
under differential privacy. Analysts run count, sum and mean queries; the system adds Laplace or
Gaussian noise, charges a per-dataset privacy budget (epsilon), refuses queries once the budget is
spent, hides small groups, and explains the privacy risk of each release. Administrators configure
budgets and rules and review the audit log. Viewers see released (noisy) results only.

See `data_flow_diagram.md` for the data-flow diagram and trust boundaries.

## 2. Assets to protect
| Asset | Why it matters |
|---|---|
| Raw uploaded CSV rows | Contain individuals' data; must never reach analysts or viewers |
| True (un-noised) answers | Releasing them would defeat the privacy guarantee |
| Privacy budget and ledger | If it can be bypassed, privacy loss is unbounded |
| Passwords and session cookies | Control access to everything else |
| Signing key (`.secret_key`) | Anyone holding it can forge sessions |
| Audit log | Evidence of what happened; must be complete and trustworthy |
| Admin configuration | Weakening it weakens privacy for every dataset |

## 3. Actors
| Actor | Trust level | Capabilities |
|---|---|---|
| Admin | Trusted, but actions are logged | Configure budgets and thresholds, view audit log, run accuracy reports |
| Analyst | Semi-trusted | Upload CSVs, run private queries, export sanitized reports |
| Viewer | Least privilege | Read released noisy results only |
| Anonymous or attacker | Untrusted | Can send any request to the API |

## 4. Assumptions and scope
- The system runs locally for demonstration; production hosting is out of scope.
- The operating system, the laptop and the Python runtime are trusted.
- Differential privacy is applied per released query with basic composition (epsilon values add up).
- Out of scope: attacks on the host machine, network eavesdropping (the demo uses plain HTTP on localhost),
  and side channels such as timing attacks on the noise generator.

## 5. Trust boundaries
- Boundary 1: browser to server (all input is untrusted)
- Boundary 2: server to storage (database, uploaded files, audit log)

## 6. Threats and mitigations
| ID | Threat | Attacker | How it could happen | Mitigation | Evidence |
|---|---|---|---|---|---|
| TH-1 | Privacy budget overspending | Analyst | Run many queries, or send concurrent requests to slip past the limit | Budget check and deduction happen in one locked database transaction; over-budget queries are denied with `E_BUDGET_EXHAUSTED` | `app/engine/ledger.py`; tests `test_T1_budget_exhaustion_through_the_api`, `test_T1_concurrent_requests_cannot_overspend` |
| TH-2 | Averaging attack | Analyst | Repeat the same query to average the noise away | First noisy answer is saved; repeats return it and cost nothing, for every user | tests `test_T2_repeated_query_returns_same_answer_and_costs_nothing`, `test_T2_another_user_gets_the_same_saved_answer` |
| TH-3 | Small-group disclosure | Analyst | Group by a column to isolate one or two people | Groups smaller than the admin-set threshold (default 5) are suppressed | `app/engine/query.py`; tests `test_T4_small_groups_are_suppressed`, `test_T4_small_group_is_not_disclosed_through_the_api` |
| TH-4 | Unauthorized access to data or admin functions | Viewer, analyst, anonymous | Call endpoints directly without the right role | Server-side role check on every endpoint; generic `Access denied`; attempt logged | tests `test_T_final_viewer_is_denied_everything_except_released_results`, `test_T_final_analyst_cannot_use_admin_functions`, `test_denied_attempts_are_logged` |
| TH-5 | Raw data or true values reaching non-admins | Analyst, viewer | Read results, export, or API responses | Only noisy values are released; true values exist only in the admin-only accuracy report; export is sanitized | tests `test_viewer_sees_only_noisy_released_results`, `test_export_is_sanitized` |
| TH-6 | CSV / formula injection | Malicious uploader | Cells starting with `=`, `+`, `-`, `@` that run as formulas when opened in a spreadsheet | Such files are rejected at validation | `app/engine/schema.py`; tests `test_formula_injection_rejected`, `test_T_final_malformed_oversized_and_malicious_uploads_are_rejected` |
| TH-7 | Oversized or malformed upload (denial of service) | Malicious uploader | Huge, binary, empty or badly encoded files | Limits on size, rows, columns, type and encoding; read is capped at the size limit | tests `test_oversized_file_rejected`, `test_binary_content_rejected`, `test_non_utf8_rejected`, `test_too_many_rows_rejected` |
| TH-8 | Path traversal through file names | Malicious uploader | File name like `../../evil.csv` | Files are stored under server-generated IDs; only the base name is kept as a label | test `test_path_traversal_in_filename_is_neutralised` |
| TH-9 | Password guessing | Anonymous | Try many passwords | bcrypt hashing; 5 failed attempts per 5 minutes per user and address, then blocked; identical error for wrong password and unknown user | tests `test_T_final_repeated_failed_logins_are_rate_limited`, `test_wrong_password_and_unknown_user_get_the_same_generic_error` |
| TH-10 | Cross-site request forgery (CSRF) | Malicious website | Trick a logged-in user's browser into sending a state-changing request | Custom header required on every POST; cookie uses SameSite=strict | test `test_csrf_header_is_required_for_state_changing_requests` |
| TH-11 | Session theft or reuse | Attacker | Steal or reuse a cookie, or keep a session alive forever | Signed cookie, 30-minute expiry, logout clears the session | `app/main.py` (session settings); test `test_logout_ends_the_session` |
| TH-12 | SQL / query injection | Analyst, anonymous | Malicious text in login, dataset ID, column name or query fields | Parameterized SQL everywhere; queries are chosen from a whitelist of operations and declared columns | tests `test_sql_injection_in_login_does_not_work`, `test_injection_style_column_is_rejected`, `test_invalid_queries_are_rejected` |
| TH-13 | Secret and information leakage | Anyone | Read passwords or secrets in logs, exports, errors or the repository; trigger errors to see internals | Audit log never stores passwords or file contents; errors return stable codes without stack traces; secret key and database are excluded from Git | tests `test_audit_log_never_contains_passwords`, `test_T_final_unexpected_error_fails_safely`; `.gitignore` |
| TH-14 | Tampering with the audit trail | Insider | Edit or delete log entries to hide activity | The code has only an append function and no update or delete endpoint; log is readable only by admins | `app/db.py` (`log_event`); `/api/audit` is read-only |
| TH-15 | Weakening privacy through admin settings | Compromised or careless admin | Lower the small-group threshold or inflate a budget | Admin-only, explicit confirmation, range checks, budget cannot go below what is spent, every change logged with old and new values; a changed rule produces fresh releases rather than reusing old ones | tests `test_admin_changes_threshold_and_the_change_is_traceable`, `test_admin_budget_change_is_validated_and_traceable` |
| TH-16 | Request flooding | Analyst, anonymous | Many uploads or queries to exhaust resources | Rate limits: 10 uploads per minute and 30 queries per minute per user | tests `test_T_final_upload_flooding_is_rate_limited`, `test_T_final_query_flooding_is_rate_limited` |
| TH-17 | Loss of state after restart | Accident | Restart resets budgets or settings, letting analysts spend again | Budgets, saved results, settings and audit log are in SQLite; settings reload at startup | tests `test_T_final_budget_cache_and_audit_survive_a_restart`, `test_T_final_admin_setting_survives_a_restart` |

## 7. Residual risks (accepted, not fully mitigated)
| Risk | Why it remains | What would reduce it |
|---|---|---|
| Plain HTTP on localhost | Demo only; no TLS certificate | Serve over HTTPS in any real deployment |
| Fixed demo passwords | Needed so a reviewer can log in | Force a password change at first login |
| Rate-limit counters are in memory | They reset when the server restarts | Store counters in the database |
| Data at rest is not encrypted | Local demo | Encrypt the uploads folder and database |
| Group-size check uses true group sizes | Common practice but not formally private | Decide suppression from a noisy count |
| Sessions are not revoked server-side before expiry | Cookie-based sessions are stateless | Keep a server-side session table |
| Colluding analysts spending the same budget | Budget is per dataset, which is the intended safety limit | Per-user budgets on top of per-dataset |
| Privacy accounting uses basic composition | Simple and safe, but loose | Advanced composition or Rényi accounting |
