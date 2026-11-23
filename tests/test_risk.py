import pytest

from app.engine.risk import explain_risk, RULES_VERSION


def explain(eps=0.2, remaining=4.8, total=5.0, rows=None, suppressed=0,
            cached=False, thresholds=None, mech="laplace"):
    spec = {"operation": "count", "column": None, "group_by": None,
            "epsilon": eps, "mechanism": mech}
    evidence = {"min_group_size": 5, "delta": 1e-5 if mech == "gaussian" else None}
    if rows is None:
        rows = [{"group": "all rows", "value": 200.0, "noise_scale": 0.5}]
    return explain_risk(spec, evidence, rows, suppressed, remaining, total, cached, thresholds)


def rules(result):
    return {r["rule"]: r["level"] for r in result["reasons"]}


def test_small_epsilon_and_unused_budget_is_low_risk():
    r = explain()
    assert r["risk_level"] == "LOW"
    assert rules(r)["R1_BUDGET_USAGE"] == "LOW"
    assert rules(r)["R2_EPSILON_SIZE"] == "LOW"


def test_moderate_epsilon_is_medium_risk():
    assert explain(eps=0.8, remaining=4.2)["risk_level"] == "MEDIUM"


def test_large_epsilon_is_high_risk_and_asks_for_review():
    r = explain(eps=2.0, remaining=3.0)
    assert r["risk_level"] == "HIGH"
    assert "administrator" in r["recommended_action"]


def test_budget_nearly_used_is_high_risk():
    r = explain(eps=0.2, remaining=0.5)
    assert rules(r)["R1_BUDGET_USAGE"] == "HIGH"
    assert r["risk_level"] == "HIGH"


def test_half_budget_used_is_medium_risk():
    assert rules(explain(remaining=2.0))["R1_BUDGET_USAGE"] == "MEDIUM"


def test_suppressed_groups_are_explained():
    r = explain(suppressed=2)
    detail = next(x["detail"] for x in r["reasons"] if x["rule"] == "R3_SMALL_GROUPS")
    assert "2 group(s)" in detail


def test_repeat_query_is_explained():
    assert "R5_REPEAT_QUERY" in rules(explain(cached=True))


def test_large_noise_is_flagged_as_a_utility_problem():
    rows = [{"group": "all rows", "value": 1.0, "noise_scale": 10.0}]
    r = explain(rows=rows)
    assert rules(r)["R4_NOISE_VS_VALUE"] == "MEDIUM"
    assert next(x for x in r["reasons"] if x["rule"] == "R4_NOISE_VS_VALUE")["affects"] == "utility"


def test_gaussian_mechanism_is_explained():
    assert "R6_MECHANISM" in rules(explain(eps=0.5, mech="gaussian"))


def test_changing_a_threshold_changes_the_decision_and_is_recorded():
    r = explain(eps=0.2, thresholds={"epsilon_moderate": 0.1})
    assert r["risk_level"] == "MEDIUM"
    assert r["thresholds"]["epsilon_moderate"] == 0.1


def test_decision_is_reproducible_and_versioned():
    assert explain() == explain()
    assert explain()["rules_version"] == RULES_VERSION