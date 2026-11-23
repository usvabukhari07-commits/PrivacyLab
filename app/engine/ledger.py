from app.db import get_conn


class BudgetExhausted(Exception):
    def __init__(self, remaining):
        super().__init__("privacy budget exhausted")
        self.remaining = remaining


def remaining_budget(dataset_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT epsilon_budget, epsilon_spent FROM datasets WHERE id = ?", (dataset_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise KeyError("dataset not found")
    return row["epsilon_budget"] - row["epsilon_spent"]


def charge(dataset_id, epsilon):
    """Atomically check and deduct epsilon. Returns the remaining budget.
    BEGIN IMMEDIATE locks the database so two requests can't both overspend."""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT epsilon_budget, epsilon_spent FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if row is None:
            conn.rollback()
            raise KeyError("dataset not found")
        remaining = row["epsilon_budget"] - row["epsilon_spent"]
        if epsilon > remaining + 1e-9:
            conn.rollback()
            raise BudgetExhausted(remaining)
        conn.execute(
            "UPDATE datasets SET epsilon_spent = epsilon_spent + ? WHERE id = ?",
            (epsilon, dataset_id),
        )
        conn.commit()
        return remaining - epsilon
    finally:
        conn.close()