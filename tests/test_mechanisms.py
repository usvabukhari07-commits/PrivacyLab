import io

import numpy as np
import pandas as pd
import pytest

from app.engine import mechanisms as m
from app.engine.accuracy import compare
from tests.helpers import make_csv


@pytest.fixture(autouse=True)
def fresh_rng():
    yield
    m.set_seed(None)      # back to unpredictable noise after each test


def samples(n, sens, eps, mech="laplace"):
    return np.array([m.add_noise(0.0, sens, eps, mech)["noise"] for _ in range(n)])


def test_laplace_scale_is_sensitivity_over_epsilon():
    r = m.add_noise(100, 2.0, 0.5)
    assert r["scale"] == pytest.approx(4.0)
    assert r["mechanism"] == "laplace"


def test_laplace_noise_is_unbiased_with_expected_size():
    m.set_seed(1)
    s = samples(20000, 1.0, 0.5)
    assert np.mean(np.abs(s)) == pytest.approx(2.0, rel=0.05)   # mean |Laplace| = scale
    assert abs(np.mean(s)) < 0.15


def test_gaussian_noise_matches_sigma():
    m.set_seed(2)
    sigma = m.add_noise(0.0, 1.0, 0.5, "gaussian")["scale"]
    s = samples(20000, 1.0, 0.5, "gaussian")
    assert np.std(s) == pytest.approx(sigma, rel=0.05)


def test_gaussian_rejects_epsilon_of_one_or_more():
    with pytest.raises(ValueError):
        m.add_noise(0.0, 1.0, 1.0, "gaussian")


@pytest.mark.parametrize("eps", [0, -1])
def test_non_positive_epsilon_rejected(eps):
    with pytest.raises(ValueError):
        m.add_noise(0.0, 1.0, eps)


def test_negative_sensitivity_rejected():
    with pytest.raises(ValueError):
        m.add_noise(0.0, -1.0, 1.0)


def test_unknown_mechanism_rejected():
    with pytest.raises(ValueError):
        m.add_noise(0.0, 1.0, 1.0, "magic")


def test_smaller_epsilon_means_more_noise():
    m.set_seed(3)
    small = np.mean(np.abs(samples(5000, 1.0, 0.1)))
    large = np.mean(np.abs(samples(5000, 1.0, 2.0)))
    assert small > large * 5


def test_same_seed_repeats_and_different_seed_differs():
    m.set_seed(5)
    a = m.add_noise(0.0, 1.0, 1.0)["noise"]
    m.set_seed(5)
    b = m.add_noise(0.0, 1.0, 1.0)["noise"]
    m.set_seed(6)
    c = m.add_noise(0.0, 1.0, 1.0)["noise"]
    assert a == b
    assert a != c


# ---- T3: accuracy / error measurements ----

def _frame():
    return pd.read_csv(io.StringIO(make_csv().decode()), dtype=str, keep_default_na=False)


def _spec(mech="laplace"):
    return {"operation": "count", "column": None, "group_by": "department",
            "epsilon": 0.5, "mechanism": mech}


def test_T3_count_error_is_about_one_over_epsilon():
    m.set_seed(7)
    result = compare(_frame(), _spec(), {})
    assert len(result["by_epsilon"]) == 5
    for row in result["by_epsilon"]:
        expected = 1.0 / row["epsilon"]       # mean |Laplace(1/eps)| = 1/eps for a count
        assert abs(row["mean_abs_error"] - expected) / expected < 0.15


def test_T3_error_shrinks_as_epsilon_grows():
    m.set_seed(8)
    errors = [r["mean_abs_error"] for r in compare(_frame(), _spec(), {})["by_epsilon"]]
    assert errors == sorted(errors, reverse=True)


def test_T3_report_has_true_values_and_runtime():
    result = compare(_frame(), _spec(), {})
    assert len(result["groups"]) == 4
    assert all(g["true_value"] == 50 for g in result["groups"])
    assert result["runtime_ms"] >= 0


def test_T3_gaussian_report_only_uses_epsilon_below_one():
    result = compare(_frame(), _spec("gaussian"), {})
    assert all(r["epsilon"] < 1 for r in result["by_epsilon"])