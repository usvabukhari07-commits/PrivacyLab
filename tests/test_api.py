import os
import time

from fastapi.testclient import TestClient

from app.engine.query import CONFIG
from app.engine.schema import MAX_BYTES
from tests.helpers import HEADER, PASSWORDS, BOUNDS, login, upload, upload_ok, query, make_csv


def audit_rows(client):
    login(client, "admin")
    return client.get("/api/audit").json()


# ---------- Authentication ----------

def test_anonymous_requests_are_rejected(client):
    for path in ["/api/me", "/api/datasets", "/api/results", "/api/audit", "/api/export"]:
        assert client.get(path).status_code in (401, 403), path


def test_wrong_password_and_unknown_user_get_the_same_generic_error(client):
    a = client.post("/api/login", json={"username": "analyst", "password": "wrong"})
    b = client.post("/api/login", json={"username": "ghost", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_sql_injection_in_login_does_not_work(client):
    r = client.post("/api/login", json={"username": "' OR '1'='1", "password": "' OR '1'='1"})
    assert r.status_code == 401


def test_logout_ends_the_session(client):
    login(client, "analyst")
    assert client.get("/api/me").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_T_final_repeated_failed_logins_are_rate_limited(client):
    for _ in range(5):
        r = client.post("/api/login", json={"username": "analyst", "password": "wrong"})
        assert r.status_code == 401
    blocked = login(client, "analyst")            # correct password, but blocked
    assert blocked.status_code == 429
    assert login(client, "admin").status_code == 200   # other accounts are unaffected
    rows = client.get("/api/audit").json()
    assert any(r["action"] == "login" and r["outcome"] == "rate_limited" for r in rows)


# ---------- Authorization (server-side, per role) ----------

def test_T_final_viewer_is_denied_everything_except_released_results(client):
    login(client, "viewer")
    assert client.get("/api/datasets").status_code == 403
    assert client.get("/api/audit").status_code == 403
    assert client.get("/api/export").status_code == 403
    assert client.get("/api/admin/config").status_code == 403
    assert upload(client, make_csv()).status_code == 403
    assert query(client, "x").status_code == 403
    assert client.post("/api/accuracy", json={"dataset_id": "x", "operation": "count"}).status_code == 403
    assert client.post("/api/admin/budget",
                       json={"dataset_id": "x", "new_budget": 1.0, "confirm": True}).status_code == 403
    assert client.get("/api/results").status_code == 200
    assert client.get("/api/datasets").json() == {"detail": "Access denied"}   # generic denial


def test_T_final_analyst_cannot_use_admin_functions(client):
    login(client, "analyst")
    assert client.get("/api/audit").status_code == 403
    assert client.get("/api/admin/config").status_code == 403
    assert client.post("/api/accuracy", json={"dataset_id": "x", "operation": "count"}).status_code == 403
    assert client.post("/api/admin/min-group-size",
                       json={"min_group_size": 10, "confirm": True}).status_code == 403
    assert CONFIG["min_group_size"] == 5


def test_denied_attempts_are_logged(client):
    login(client, "viewer")
    client.get("/api/datasets")
    rows = audit_rows(client)
    assert any(r["action"] == "access_denied" and r["username"] == "viewer" for r in rows)


def test_viewer_sees_only_noisy_released_results(client):
    login(client, "analyst")
    ds = upload_ok(client)
    query(client, ds, epsilon=2.0)
    login(client, "viewer")
    results = client.get("/api/results").json()
    assert len(results) == 1
    assert set(results[0].keys()) == {"id", "created_at", "dataset", "operation", "column",
                                      "group_by", "epsilon", "mechanism", "rows", "suppressed_groups"}
    assert set(results[0]["rows"][0].keys()) == {"group", "value", "noise_scale"}


# ---------- CSRF and headers ----------

def test_csrf_header_is_required_for_state_changing_requests(client):
    r = client.post("/api/login", json={"username": "analyst", "password": PASSWORDS["analyst"]},
                    headers={"X-Requested-With": ""})
    assert r.status_code == 403
    assert r.json() == {"detail": "Access denied"}

    login(client, "analyst")                      # logged in, but a forged request has no header
    forged = client.post("/api/datasets", files={"file": ("a.csv", make_csv(), "text/csv")},
                         data={"bounds": BOUNDS}, headers={"X-Requested-With": ""})
    assert forged.status_code == 403
    assert any(r["action"] == "csrf_block" for r in audit_rows(client))


def test_security_headers_are_set(client):
    login(client, "analyst")
    r = client.get("/api/me")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


# ---------- Uploads: malformed, oversized and malicious input ----------

def test_valid_upload_gets_a_server_generated_id_and_is_stored(client):
    login(client, "analyst")
    r = upload(client, make_csv())
    assert r.status_code == 200
    ds_id = r.json()["id"]
    assert len(ds_id) == 32
    assert os.path.exists(f"data/{ds_id}.csv")


def test_T_final_malformed_oversized_and_malicious_uploads_are_rejected(client):
    login(client, "analyst")
    cases = [
        ("big.csv", b"a" * (MAX_BYTES + 10), "E_FILE_SIZE"),
        ("tool.exe", make_csv(), "E_FILE_TYPE"),
        ("bin.csv", b"a,b\n1,\x00\n", "E_FILE_BINARY"),
        ("inject.csv", b"name_id,department,age,salary\nE1,=cmd|x,30,50000\n", "E_FORMULA_INJECTION"),
    ]
    for name, raw, code in cases:
        r = upload(client, raw, filename=name)
        assert r.status_code == 422, name
        assert any(code in e for e in r.json()["detail"]), name
    text = str(audit_rows(client))
    assert "E_FORMULA_INJECTION" in text
    assert "=cmd" not in text                     # file content never reaches the log


def test_path_traversal_in_filename_is_neutralised(client):
    login(client, "analyst")
    r = upload(client, make_csv(), filename="../../evil.csv")
    assert r.status_code == 200
    assert client.get("/api/datasets").json()[0]["filename"] == "evil.csv"


def test_T_final_upload_flooding_is_rate_limited(client):
    login(client, "analyst")
    small = make_csv(n=10)
    for _ in range(10):
        assert upload(client, small).status_code == 200
    assert upload(client, small).status_code == 429


# ---------- Query misuse and safe failure ----------

def test_unknown_dataset_and_injection_style_ids_give_a_clean_404(client):
    login(client, "analyst")
    for bad_id in ["nope", "x' OR 1=1 --"]:
        r = query(client, bad_id)
        assert r.status_code == 404
        assert "Traceback" not in r.text


def test_injection_style_column_is_rejected(client):
    login(client, "analyst")
    ds = upload_ok(client)
    r = query(client, ds, operation="sum", column="age; DROP TABLE users")
    assert r.status_code == 422
    assert client.get("/api/datasets").status_code == 200     # database still fine


def test_T_final_query_flooding_is_rate_limited(client):
    login(client, "analyst")
    ds = upload_ok(client)
    for _ in range(30):
        assert query(client, ds, epsilon=1.0).status_code == 200
    assert query(client, ds, epsilon=1.0).status_code == 429


def test_T_final_unexpected_error_fails_safely(quiet_client):
    c = quiet_client
    login(c, "analyst")
    ds = upload_ok(c)
    os.remove(f"data/{ds}.csv")                   # simulate a damaged data file
    r = query(c, ds, epsilon=1.0)
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error (E_INTERNAL)"}
    assert "Traceback" not in r.text
    assert c.get("/api/datasets").json()[0]["epsilon_spent"] == 0    # nothing was charged
    assert any(x["action"] == "server_error" for x in audit_rows(c))


def test_audit_log_never_contains_passwords(client):
    client.post("/api/login", json={"username": "analyst", "password": "Secret!Guess1"})
    login(client, "analyst")
    text = str(audit_rows(client))
    assert "Secret!Guess1" not in text
    assert PASSWORDS["analyst"] not in text


# ---------- Admin controls (traceable changes) ----------

def test_admin_changes_threshold_and_the_change_is_traceable(client):
    login(client, "analyst")
    ds = upload_ok(client, make_csv(n=120, legal_rows=3))
    before = query(client, ds, group_by="department", epsilon=0.5).json()
    assert len(before["rows"]) == 4 and before["suppressed_groups"] == 1

    login(client, "admin")
    assert client.post("/api/admin/min-group-size", json={"min_group_size": 31}).status_code == 400
    assert client.post("/api/admin/min-group-size",
                       json={"min_group_size": 1, "confirm": True}).status_code == 422
    ok = client.post("/api/admin/min-group-size", json={"min_group_size": 31, "confirm": True})
    assert ok.status_code == 200 and ok.json()["previous"] == 5

    login(client, "analyst")
    after = query(client, ds, group_by="department", epsilon=0.5).json()
    assert after["cached"] is False               # a changed rule produces a fresh release
    assert after["rows"] == [] and after["suppressed_groups"] == 5

    rows = audit_rows(client)
    assert any("min_group_size 5 -> 31" in (r["detail"] or "") for r in rows)


def test_admin_budget_change_is_validated_and_traceable(client):
    login(client, "analyst")
    ds = upload_ok(client)
    query(client, ds, epsilon=2.0)

    login(client, "admin")
    body = {"dataset_id": ds, "new_budget": 1.0}
    assert client.post("/api/admin/budget", json=body).status_code == 400            # no confirmation
    low = client.post("/api/admin/budget", json={**body, "confirm": True})
    assert low.status_code == 422 and "E_BUDGET_BELOW_SPENT" in low.json()["detail"][0]
    ok = client.post("/api/admin/budget", json={**body, "new_budget": 8.0, "confirm": True})
    assert ok.status_code == 200
    assert client.get("/api/datasets").json()[0]["epsilon_budget"] == 8.0
    assert any("budget 5.0 -> 8.0" in (r["detail"] or "") for r in client.get("/api/audit").json())


def test_audit_log_can_be_filtered(client):
    login(client, "viewer")
    client.get("/api/datasets")
    login(client, "admin")
    rows = client.get("/api/audit", params={"action": "access_denied"}).json()
    assert rows and all(r["action"] == "access_denied" for r in rows)


# ---------- FR-5 accuracy report and export ----------

def test_accuracy_report_is_admin_only_and_correct(client):
    login(client, "analyst")
    ds = upload_ok(client)
    body = {"dataset_id": ds, "operation": "count"}
    assert client.post("/api/accuracy", json=body).status_code == 403

    login(client, "admin")
    r = client.post("/api/accuracy", json=body)
    assert r.status_code == 200
    data = r.json()
    assert len(data["by_epsilon"]) == 5
    assert data["groups"][0]["true_value"] == 200
    assert client.post("/api/accuracy", json={**body, "operation": "delete"}).status_code == 422


def test_export_is_sanitized(client):
    login(client, "analyst")
    ds = upload_ok(client)
    query(client, ds, epsilon=1.0)
    r = client.get("/api/export")
    assert r.status_code == 200
    assert r.json()["results"]
    text = r.text
    assert "E000" not in text                     # no raw rows
    assert "true_value" not in text and '"true"' not in text
    assert "$2b$" not in text                     # no password hashes
    assert PASSWORDS["analyst"] not in text and PASSWORDS["admin"] not in text


# ---------- Recovery after restart ----------

def test_T_final_budget_cache_and_audit_survive_a_restart(client):
    from app.main import app as fastapi_app
    login(client, "analyst")
    ds = upload_ok(client)
    first = query(client, ds, epsilon=2.0).json()

    with TestClient(fastapi_app) as restarted:     # a fresh start on the same database
        restarted.headers.update(HEADER)
        assert login(restarted, "analyst").status_code == 200
        assert restarted.get("/api/datasets").json()[0]["epsilon_spent"] == 2.0
        again = query(restarted, ds, epsilon=2.0).json()
        assert again["cached"] is True and again["rows"] == first["rows"]
        rows = audit_rows(restarted)
        assert any(r["action"] == "upload" and r["outcome"] == "success" for r in rows)


def test_T_final_admin_setting_survives_a_restart(client):
    from app.main import app as fastapi_app
    login(client, "admin")
    client.post("/api/admin/min-group-size", json={"min_group_size": 31, "confirm": True})
    CONFIG["min_group_size"] = 5                  # pretend the process memory was lost

    with TestClient(fastapi_app):                 # startup reloads settings from the database
        assert CONFIG["min_group_size"] == 31


# ---------- Performance (for the report) ----------

def test_decision_latency_is_reported(client):
    login(client, "analyst")
    ds = upload_ok(client)
    times = []
    for i in range(20):
        start = time.perf_counter()
        r = query(client, ds, epsilon=round(0.01 + i * 0.01, 2))
        times.append((time.perf_counter() - start) * 1000)
        assert r.status_code == 200
    average = sum(times) / len(times)
    print(f"\nQUERY LATENCY: average {average:.1f} ms, max {max(times):.1f} ms over {len(times)} queries")
    assert average < 500