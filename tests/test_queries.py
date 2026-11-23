import io

import pandas as pd
import pytest

from app.engine import mechanisms as m
from app.engine.query import validate_spec, query_hash, run_query, true_groups, CONFIG
from tests.helpers import login, upload_ok, query, make_csv

COLUMNS = ["name_id", "department", "age", "salary"]
BOUNDS = {"age": [18, 100], "salary": [0, 300000]}
HEADER_BYTES = b"name_id,department,age,salary\n"


def spec(**kw):
    base = {"operation": "count", "column": None, "group_by": None,
            "epsilon": 0.5, "mechanism": "laplace"}
    base.update(kw)
    return base


def codes(errors):
    return [e.split(":")[0] for e in errors]


def frame(raw):
    return pd.read_csv(io.StringIO(raw.decode()), dtype=str, keep_default_na=False)


def rows_of(department, n):
    return b"".join(b"%s%d,%s,30,1000\n" % (department.encode(), i, department.encode()) for i in range(n))


@pytest.fixture(autouse=True)
def fresh_rng():
    yield
    m.set_seed(None)


# ---------- FR-2: query validation (whitelist, no free-form input) ----------

def test_valid_query_is_accepted():
    s, errs = validate_spec(spec(), COLUMNS, BOUNDS)
    assert errs == []
    assert s["operation"] == "count"


@pytest.mark.parametrize("bad,expected", [
    (spec(operation="delete"), "E_QUERY_OP"),
    (spec(operation="sum"), "E_QUERY_COLUMN"),
    (spec(operation="sum", column="department"), "E_QUERY_COLUMN"),
    (spec(operation="sum", column="age; DROP TABLE users"), "E_QUERY_COLUMN"),
    (spec(group_by="age"), "E_QUERY_GROUP"),
    (spec(group_by="nope"), "E_QUERY_GROUP"),
    (spec(epsilon=5), "E_QUERY_EPSILON"),
    (spec(epsilon=0), "E_QUERY_EPSILON"),
    (spec(epsilon="abc"), "E_QUERY_EPSILON"),
    (spec(epsilon=float("nan")), "E_QUERY_EPSILON"),
    (spec(mechanism="magic"), "E_QUERY_MECH"),
    (spec(mechanism="gaussian", epsilon=1.5), "E_GAUSS_EPSILON"),
])
def test_invalid_queries_are_rejected(bad, expected):
    _, errs = validate_spec(bad, COLUMNS, BOUNDS)
    assert expected in codes(errs)


def test_query_fingerprint_changes_with_query_dataset_and_rule(monkeypatch):
    s1 = spec()
    assert query_hash("d", s1) == query_hash("d", dict(s1))
    assert query_hash("d", s1) != query_hash("d", spec(epsilon=0.6))
    assert query_hash("d", s1) != query_hash("other", s1)
    before = query_hash("d", s1)
    monkeypatch.setitem(CONFIG, "min_group_size", 6)
    assert query_hash("d", s1) != before


# ---------- Engine: noise, clamping, small groups ----------

def test_count_is_close_to_truth_at_large_epsilon():
    m.set_seed(3)
    out = run_query(frame(make_csv()), spec(epsilon=2.0), BOUNDS)
    assert out["rows"][0]["group"] == "all rows"
    assert abs(out["rows"][0]["value"] - 200) < 10
    assert out["evidence"]["mechanism"] == "laplace"


def test_values_are_clamped_to_declared_bounds():
    raw = HEADER_BYTES + b"".join(b"a%d,X,30,1000000\n" % i for i in range(10))
    groups = true_groups(frame(raw), spec(operation="sum", column="salary"), BOUNDS)
    assert groups[0]["true"] == 10 * 300000


def test_T4_small_groups_are_suppressed(monkeypatch):
    monkeypatch.setitem(CONFIG, "min_group_size", 5)
    out = run_query(frame(make_csv(n=120, legal_rows=3)), spec(group_by="department"), BOUNDS)
    names = sorted(r["group"] for r in out["rows"])
    assert names == ["Finance", "HR", "IT", "Sales"]
    assert "Legal" not in names
    assert out["suppressed_groups"] == 1


def test_T4_group_of_exactly_threshold_size_is_shown(monkeypatch):
    monkeypatch.setitem(CONFIG, "min_group_size", 5)
    raw = HEADER_BYTES + rows_of("X", 5) + rows_of("Y", 4)
    out = run_query(frame(raw), spec(group_by="department"), BOUNDS)
    assert [r["group"] for r in out["rows"]] == ["X"]
    assert out["suppressed_groups"] == 1


def test_T4_raising_the_threshold_hides_more_groups(monkeypatch):
    monkeypatch.setitem(CONFIG, "min_group_size", 31)
    out = run_query(frame(make_csv(n=120, legal_rows=3)), spec(group_by="department"), BOUNDS)
    assert out["rows"] == []
    assert out["suppressed_groups"] == 5


def test_T4_tiny_dataset_without_grouping_is_suppressed():
    raw = HEADER_BYTES + rows_of("X", 3)
    out = run_query(frame(raw), spec(), BOUNDS)
    assert out["rows"] == []
    assert out["suppressed_groups"] == 1


# ---------- End-to-end through the API ----------

def test_T1_budget_exhaustion_through_the_api(client):
    login(client, "analyst")
    ds = upload_ok(client)

    r1 = query(client, ds, operation="count", epsilon=2.0)
    assert r1.status_code == 200
    assert r1.json()["budget_remaining"] == 3.0

    r2 = query(client, ds, operation="mean", column="salary", epsilon=2.0)
    assert r2.json()["budget_remaining"] == 1.0

    r3 = query(client, ds, operation="sum", column="age", epsilon=2.0)
    assert r3.status_code == 403
    assert "E_BUDGET_EXHAUSTED" in r3.json()["detail"][0]

    r4 = query(client, ds, operation="sum", column="age", epsilon=1.0)
    assert r4.status_code == 200
    assert r4.json()["budget_remaining"] == 0.0

    r5 = query(client, ds, operation="count", epsilon=0.01)
    assert r5.status_code == 403

    # denied queries released nothing
    assert len(client.get("/api/results").json()) == 3


def test_T2_repeated_query_returns_same_answer_and_costs_nothing(client):
    login(client, "analyst")
    ds = upload_ok(client)
    first = query(client, ds, epsilon=1.0).json()
    assert first["cached"] is False
    assert first["budget_remaining"] == 4.0

    for _ in range(10):
        again = query(client, ds, epsilon=1.0).json()
        assert again["cached"] is True
        assert again["epsilon_charged"] == 0
        assert again["rows"] == first["rows"]
        assert again["budget_remaining"] == 4.0


def test_T2_another_user_gets_the_same_saved_answer(client):
    login(client, "analyst")
    ds = upload_ok(client)
    first = query(client, ds, epsilon=1.0).json()
    login(client, "admin")
    second = query(client, ds, epsilon=1.0).json()
    assert second["cached"] is True
    assert second["rows"] == first["rows"]


def test_T2_a_different_epsilon_is_a_new_query_and_is_charged(client):
    login(client, "analyst")
    ds = upload_ok(client)
    query(client, ds, epsilon=1.0)
    other = query(client, ds, epsilon=0.5).json()
    assert other["cached"] is False
    assert other["budget_remaining"] == 3.5


def test_T4_small_group_is_not_disclosed_through_the_api(client):
    login(client, "analyst")
    ds = upload_ok(client, make_csv(n=120, legal_rows=3))
    r = query(client, ds, group_by="department", epsilon=0.5)
    body = r.json()
    assert body["suppressed_groups"] == 1
    assert "Legal" not in [x["group"] for x in body["rows"]]
    assert "Legal" not in r.text