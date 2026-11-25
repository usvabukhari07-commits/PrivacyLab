import threading

import pytest

from app.engine.ledger import charge, remaining_budget, BudgetExhausted
from tests.helpers import add_dataset


def test_T1_budget_is_deducted_then_exhausted(db):
    add_dataset(budget=5.0)
    assert charge("ds1", 2.0) == pytest.approx(3.0)
    assert charge("ds1", 2.0) == pytest.approx(1.0)
    with pytest.raises(BudgetExhausted) as err:
        charge("ds1", 2.0)
    assert err.value.remaining == pytest.approx(1.0)


def test_T1_denied_charge_does_not_change_the_balance(db):
    add_dataset(budget=1.0)
    with pytest.raises(BudgetExhausted):
        charge("ds1", 1.5)
    assert remaining_budget("ds1") == pytest.approx(1.0)


def test_T1_budget_can_be_used_exactly_then_nothing_more(db):
    add_dataset(budget=5.0)
    charge("ds1", 2.0)
    charge("ds1", 2.0)
    charge("ds1", 1.0)
    assert remaining_budget("ds1") == pytest.approx(0.0, abs=1e-9)
    with pytest.raises(BudgetExhausted):
        charge("ds1", 0.01)


def test_T1_floating_point_dust_does_not_block_last_charge(db):
    add_dataset(budget=1.0)
    for _ in range(10):
        charge("ds1", 0.1)
    with pytest.raises(BudgetExhausted):
        charge("ds1", 0.1)


def test_unknown_dataset_raises_key_error(db):
    with pytest.raises(KeyError):
        charge("nope", 1.0)
    with pytest.raises(KeyError):
        remaining_budget("nope")


def test_T1_concurrent_requests_cannot_overspend(db):
    add_dataset(budget=5.0)
    outcomes = []

    def worker():
        try:
            charge("ds1", 0.5)
            outcomes.append("ok")
        except BudgetExhausted:
            outcomes.append("denied")
        except Exception as e:                     # anything else is a failure
            outcomes.append("error:" + type(e).__name__)

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("ok") == 10
    assert outcomes.count("denied") == 20
    assert remaining_budget("ds1") == pytest.approx(0.0, abs=1e-9)