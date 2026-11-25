# Test results

Run date: 25 Nov 2026. Command: `pytest -v` (full log in `pytest_output.txt`).

## Summary
| Measure | Result |
|---|---|
| Automated tests | 105 |
| Passed | 105 (100%) |
| Failed | 0 |
| Required pass rate | at least 80% |
| Total run time | about 1 to 1.5 minutes |
| Average query decision latency | 15.6 ms (max 47.6 ms, 20 queries) |
| Unresolved critical authorization, injection, secret-exposure or file-handling defects | 0 |

Evidence: `screenshots/16_pytest_all_passed.png`, `pytest_output.txt`.

## Functional requirement coverage
| Requirement | Module | Main tests |
|---|---|---|
| FR-1 CSV schema validation | `app/engine/schema.py` | `tests/test_schema.py` (21 tests) |
| FR-2 Query builder | `app/engine/query.py` | `tests/test_queries.py` (25 tests) |
| FR-3 Laplace/Gaussian noise | `app/engine/mechanisms.py` | `tests/test_mechanisms.py` (14 tests) |
| FR-4 Epsilon ledger | `app/engine/ledger.py` | `tests/test_ledger.py` (6 tests), `test_T1_*` |
| FR-5 Accuracy comparison | `app/engine/accuracy.py` | `test_T3_*`, `test_accuracy_report_is_admin_only_and_correct` |
| FR-6 Privacy-risk explanation | `app/engine/risk.py` | `tests/test_risk.py` (11 tests) |
| API, security and recovery | `app/main.py` | `tests/test_api.py` (28 tests) |

## T1: Privacy-budget exhaustion
| Field | Detail |
|---|---|
| Input | Dataset with budget 5.0. Queries: count (epsilon 2.0), mean of salary (2.0), sum of age (2.0); then sum of age (1.0); then count (0.01) |
| Expected | First two allowed (remaining 3.0, then 1.0); third denied with `E_BUDGET_EXHAUSTED`; fourth allowed (remaining 0.0); fifth denied; denied queries release nothing. 30 concurrent charges of 0.5 against a budget of 5.0 allow exactly 10 |
| Actual | As expected |
| Evidence | `test_T1_budget_exhaustion_through_the_api`, `test_T1_budget_is_deducted_then_exhausted`, `test_T1_budget_can_be_used_exactly_then_nothing_more`, `test_T1_concurrent_requests_cannot_overspend`; `screenshots/06_T1_budget_exhausted.png` |
| Status | PASS |

## T2: Repeated-query protection
| Field | Detail |
|---|---|
| Input | The same count query (epsilon 1.0) submitted 11 times, then by a second user, then with a different epsilon |
| Expected | First call charged (remaining 4.0). Next 10 return `cached: true`, identical noisy rows, charge 0, budget unchanged. Second user gets the same saved answer. A different epsilon is a new query and is charged |
| Actual | As expected |
| Evidence | `test_T2_repeated_query_returns_same_answer_and_costs_nothing`, `test_T2_another_user_gets_the_same_saved_answer`, `test_T2_a_different_epsilon_is_a_new_query_and_is_charged`; `screenshots/07_T2_repeat_cached.png` |
| Status | PASS |

## T3: Accuracy and error measurements
| Field | Detail |
|---|---|
| Input | Count query grouped by department (4 groups of 50), 500 trials per group, epsilon 0.1, 0.25, 0.5, 1.0, 2.0 |
| Expected | Mean absolute error close to 1/epsilon for a count (within 15%), and decreasing as epsilon grows. Gaussian reports use only epsilon below 1 |
| Actual | All checks passed. Measured values are in the table below |
| Evidence | `test_T3_count_error_is_about_one_over_epsilon`, `test_T3_error_shrinks_as_epsilon_grows`, `test_T3_report_has_true_values_and_runtime`, `test_T3_gaussian_report_only_uses_epsilon_below_one`; `screenshots/08_T3_accuracy_table.png` |
| Status | PASS |

Measured error (fixed random seed 2026, 500 trials per group):
| Epsilon | Expected mean abs error (1/epsilon) | Measured mean abs error | Measured RMSE | Mean relative error % |
|---|---|---|---|---|
| 0.1 | 10.0 | 9.951 | 14.04 | 19.903 |
| 0.25 | 4.0 | 3.915 | 5.603 | 7.83 |
| 0.5 | 2.0 | 2.001 | 2.783 | 4.003 |
| 1.0 | 1.0 | 0.987 | 1.384 | 1.975 |
| 2.0 | 0.5 | 0.504 | 0.709 | 1.008 |

Performance: average decision latency 15.6 ms, maximum 47.6 ms over 20 queries (`test_decision_latency_is_reported`).

## T4: Small-group disclosure
| Field | Detail |
|---|---|
| Input | Dataset with four groups of 30 plus a "Legal" group of 3 people; count grouped by department, epsilon 0.5, threshold 5. Also a group of exactly 5, a group of 4, a tiny ungrouped dataset, and threshold raised to 31 |
| Expected | Legal hidden, 1 group suppressed, the name "Legal" appears nowhere in the response. Group of exactly 5 shown, group of 4 hidden. Tiny ungrouped dataset suppressed. Threshold 31 hides every group |
| Actual | As expected |
| Evidence | `test_T4_small_groups_are_suppressed`, `test_T4_group_of_exactly_threshold_size_is_shown`, `test_T4_raising_the_threshold_hides_more_groups`, `test_T4_tiny_dataset_without_grouping_is_suppressed`, `test_T4_small_group_is_not_disclosed_through_the_api`; `screenshots/09_T4_small_group_hidden.png` |
| Status | PASS |

## T-final: Robustness, misuse, failure and recovery
| Case | Input | Expected | Actual | Evidence | Status |
|---|---|---|---|---|---|
| Malformed input | Empty, binary, non-UTF-8, duplicate or bad column names, too many rows or columns, header only, non-numeric values, bad bounds text | Rejected with a stable error code | As expected | `tests/test_schema.py`; `screenshots/03_upload_formula_rejected.png` | PASS |
| Oversized input | File larger than 2 MB | `E_FILE_SIZE`, rejected, nothing stored | As expected | `test_oversized_file_rejected`, `test_T_final_malformed_oversized_and_malicious_uploads_are_rejected`; `screenshots/04_upload_oversized_rejected.png` | PASS |
| Malicious file | Cells starting with `=`, `+`, `-`, `@`; path in file name | Injection rejected; path stripped; file content never written to the log | As expected | `test_formula_injection_rejected`, `test_path_traversal_in_filename_is_neutralised` | PASS |
| Unauthorized request | Anonymous, viewer and analyst calling restricted endpoints | Generic `Access denied`, attempt logged, no data exposed | As expected | `test_anonymous_requests_are_rejected`, `test_T_final_viewer_is_denied_everything_except_released_results`, `test_T_final_analyst_cannot_use_admin_functions`, `test_denied_attempts_are_logged`; `screenshots/10_viewer_denied.png`, `screenshots/12_audit_log_filtered.png` | PASS |
| Forged request (CSRF) | POST without the required header, with and without a logged-in session | 403 and logged | As expected | `test_csrf_header_is_required_for_state_changing_requests`; `screenshots/14_csrf_blocked.png` | PASS |
| Repeated submission | 5 wrong passwords then the right one; 11 uploads in a minute; 31 queries in a minute | Login blocked (429); upload and query limits enforced | As expected | `test_T_final_repeated_failed_logins_are_rate_limited`, `test_T_final_upload_flooding_is_rate_limited`, `test_T_final_query_flooding_is_rate_limited`; `screenshots/15_login_rate_limited.png` | PASS |
| Safe failure | Data file deleted before a query | HTTP 500 with `E_INTERNAL`, no stack trace, no budget charged, failure logged | As expected | `test_T_final_unexpected_error_fails_safely` | PASS |
| Recovery after restart | Fresh application start on the same database | Budget, saved results, audit log and admin threshold all preserved | As expected | `test_T_final_budget_cache_and_audit_survive_a_restart`, `test_T_final_admin_setting_survives_a_restart` | PASS |
| Injection | SQL text in login, dataset ID and column fields | Rejected or harmless, database intact | As expected | `test_sql_injection_in_login_does_not_work`, `test_injection_style_column_is_rejected`, `test_unknown_dataset_and_injection_style_ids_give_a_clean_404` | PASS |

## Admin traceability (demonstration from the brief)
An administrator changed the small-group threshold from 5 to 31. The same query then produced a new release in which all groups were hidden, and the audit log recorded who made the change and the old and new values. Budget changes are validated (cannot go below what is already spent) and logged the same way.
Evidence: `test_admin_changes_threshold_and_the_change_is_traceable`, `test_admin_budget_change_is_validated_and_traceable`, `test_audit_log_can_be_filtered`; `screenshots/11_admin_threshold_change.png`, `screenshots/12_audit_log_filtered.png`.

## Sanitized export
Exported report contains only noisy released values, rule settings and budget status: no raw rows, no true values, no password hashes or passwords.
Evidence: `test_export_is_sanitized`; `screenshots/13_export_report.png`.

## Defects found during testing
| Finding | Cause | Resolution |
|---|---|---|
| `test_export_is_sanitized` failed in the first full run | The test searched for the word "password", which appears in the report's own disclaimer note ("no passwords") | Test changed to look for password hashes and the real demo passwords; suite re-run and passed |
| Login page showed one generic error for every failure | Page did not distinguish the CSRF header failure from wrong credentials | Header added to the login request; separate messages for 403 and 429 |
| Ledger test file was empty during the first full runs, so its 6 tests were not collected | Test code had not been added to `tests/test_ledger.py` | Tests added; total rose from 99 to 105 and all pass |

## Known limitations
See `limitations_ethics.md`.