import hashlib
import json
import pandas as pd
from app.engine.mechanisms import add_noise

OPERATIONS = {"count", "sum", "mean"}
MECHANISMS = {"laplace", "gaussian"}
CONFIG = {"min_group_size": 5}      # admin can change this
MIN_EPS = 0.01
MAX_EPS = 2.0
DELTA = 1e-5


def validate_spec(raw, columns, bounds):
    """Validate and normalize a query. Returns (spec, errors)."""
    errors = []
    op = str(raw.get("operation", "")).lower()
    mech = str(raw.get("mechanism", "laplace")).lower()
    col = raw.get("column") or None
    grp = raw.get("group_by") or None

    try:
        eps = round(float(raw.get("epsilon")), 4)
    except (TypeError, ValueError):
        eps = None
        errors.append("E_QUERY_EPSILON: epsilon must be a number")

    if op not in OPERATIONS:
        errors.append("E_QUERY_OP: operation must be count, sum or mean")
    if mech not in MECHANISMS:
        errors.append("E_QUERY_MECH: mechanism must be laplace or gaussian")
    if eps is not None and not (MIN_EPS <= eps <= MAX_EPS):
        errors.append(f"E_QUERY_EPSILON: epsilon must be between {MIN_EPS} and {MAX_EPS}")
    if mech == "gaussian" and eps is not None and eps >= 1:
        errors.append("E_GAUSS_EPSILON: gaussian mechanism requires epsilon below 1")

    if op in ("sum", "mean"):
        if col not in bounds:
            errors.append("E_QUERY_COLUMN: column must be a numeric column with declared bounds")
    else:
        col = None

    if grp is not None and (grp not in columns or grp in bounds):
        errors.append("E_QUERY_GROUP: group_by must be a text column of this dataset")

    spec = {"operation": op, "column": col, "group_by": grp, "epsilon": eps, "mechanism": mech}
    return spec, errors


def query_hash(dataset_id, spec):
    # The release rule (group-size threshold) is part of the fingerprint
    text = dataset_id + json.dumps(spec, sort_keys=True) + f"|k={CONFIG['min_group_size']}"
    return hashlib.sha256(text.encode()).hexdigest()


def run_query(df, spec, bounds):
    op, col, grp = spec["operation"], spec["column"], spec["group_by"]
    eps, mech = spec["epsilon"], spec["mechanism"]
    k = CONFIG["min_group_size"]

    lo = hi = None
    if col:
        lo, hi = bounds[col]
        df = df.copy()
        df[col] = pd.to_numeric(df[col], errors="coerce").clip(lo, hi)   # clamping

    parts = list(df.groupby(grp)) if grp else [("all rows", df)]
    rows, suppressed = [], 0

    for name, g in parts:
        n = len(g)
        if n < k:
            suppressed += 1
            continue
        if op == "count":
            true_val, sens = n, 1.0
        elif op == "sum":
            true_val, sens = float(g[col].sum()), max(abs(lo), abs(hi))
        else:
            true_val, sens = float(g[col].mean()), (hi - lo) / n
        res = add_noise(true_val, sens, eps, mech, DELTA)
        rows.append({
            "group": str(name),
            "value": round(res["noisy_value"], 2),
            "noise_scale": round(res["scale"], 4),
        })

    sens_rule = {
        "count": "1 (one person changes a count by at most 1)",
        "sum": "max(|min|, |max|) of the declared bounds",
        "mean": "(max - min) / group size",
    }[op]

    evidence = {
        "mechanism": mech,
        "epsilon": eps,
        "delta": DELTA if mech == "gaussian" else None,
        "sensitivity_rule": sens_rule,
        "clamping_bounds": [lo, hi] if col else None,
        "min_group_size": k,
        "groups_returned": len(rows),
        "groups_suppressed": suppressed,
        "composition_note": "groups are disjoint, so epsilon is charged once for the whole query",
    }
    return {"rows": rows, "suppressed_groups": suppressed, "evidence": evidence}


def true_groups(df, spec, bounds):
    """True (un-noised) answers per group. Admin accuracy report only, never released."""
    op, col, grp = spec["operation"], spec["column"], spec["group_by"]
    k = CONFIG["min_group_size"]
    lo = hi = None
    if col:
        lo, hi = bounds[col]
        df = df.copy()
        df[col] = pd.to_numeric(df[col], errors="coerce").clip(lo, hi)

    parts = list(df.groupby(grp)) if grp else [("all rows", df)]
    out = []
    for name, g in parts:
        n = len(g)
        if n < k:
            continue
        if op == "count":
            true_val, sens = float(n), 1.0
        elif op == "sum":
            true_val, sens = float(g[col].sum()), max(abs(lo), abs(hi))
        else:
            true_val, sens = float(g[col].mean()), (hi - lo) / n
        out.append({"group": str(name), "true": true_val, "sensitivity": sens, "n": n})
    return out