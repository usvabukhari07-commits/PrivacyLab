import random

HEADER = {"X-Requested-With": "PrivacyLab"}
PASSWORDS = {"admin": "Admin#12345", "analyst": "Analyst#12345", "viewer": "Viewer#12345"}
BOUNDS = "age:18:100,salary:0:300000"


def make_csv(n=200, legal_rows=0):
    """Deterministic sample file: n rows spread evenly over 4 departments,
    plus optional tiny 'Legal' group for small-group tests."""
    rnd = random.Random(1)
    depts = ["HR", "IT", "Sales", "Finance"]
    lines = ["name_id,department,age,salary"]
    for i in range(n):
        lines.append(f"E{i:03d},{depts[i % 4]},{rnd.randint(22, 60)},{rnd.randint(40000, 200000)}")
    for i in range(legal_rows):
        lines.append(f"L{i},Legal,40,90000")
    return ("\n".join(lines) + "\n").encode()


def login(client, user):
    return client.post("/api/login", json={"username": user, "password": PASSWORDS[user]})


def upload(client, raw, filename="employees.csv", bounds=BOUNDS):
    return client.post("/api/datasets",
                       files={"file": (filename, raw, "text/csv")},
                       data={"bounds": bounds})


def upload_ok(client, raw=None, bounds=BOUNDS):
    r = upload(client, raw if raw is not None else make_csv(), bounds=bounds)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def query(client, ds_id, **kw):
    body = {"dataset_id": ds_id, "operation": "count", "epsilon": 0.5}
    body.update(kw)
    return client.post("/api/query", json=body)


def add_dataset(ds_id="ds1", budget=5.0):
    """Insert a dataset row directly (for ledger tests)."""
    from app.db import get_conn
    conn = get_conn()
    conn.execute(
        "INSERT INTO datasets (id, owner, filename, row_count, columns, bounds, "
        "epsilon_budget, epsilon_spent, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (ds_id, "tester", "t.csv", 1, "[]", "{}", budget, 0, "2026-01-01"),
    )
    conn.commit()
    conn.close()