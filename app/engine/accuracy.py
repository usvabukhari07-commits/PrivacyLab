import time
import numpy as np
from app.engine.mechanisms import add_noise
from app.engine.query import true_groups, DELTA

DEFAULT_EPSILONS = [0.1, 0.25, 0.5, 1.0, 2.0]


def compare(df, spec, bounds, epsilons=None, trials=500):
    start = time.perf_counter()
    groups = true_groups(df, spec, bounds)
    mech = spec["mechanism"]
    epsilons = epsilons or DEFAULT_EPSILONS
    if mech == "gaussian":
        epsilons = [e for e in epsilons if e < 1]   # gaussian needs epsilon below 1

    rows = []
    for eps in epsilons:
        all_errs, rel = [], []
        for g in groups:
            g_errs = []
            for _ in range(trials):
                r = add_noise(g["true"], g["sensitivity"], eps, mech, DELTA)
                g_errs.append(abs(r["noise"]))
            all_errs.extend(g_errs)
            if g["true"] != 0:
                rel.append(float(np.mean(g_errs)) / abs(g["true"]) * 100)
        arr = np.array(all_errs) if all_errs else np.array([0.0])
        rows.append({
            "epsilon": eps,
            "mean_abs_error": round(float(arr.mean()), 3),
            "rmse": round(float(np.sqrt((arr ** 2).mean())), 3),
            "p95_abs_error": round(float(np.percentile(arr, 95)), 3),
            "mean_relative_error_pct": round(float(np.mean(rel)), 3) if rel else None,
        })

    return {
        "mechanism": mech,
        "trials_per_group": trials,
        "groups": [{"group": g["group"], "true_value": round(g["true"], 2), "group_size": g["n"]} for g in groups],
        "by_epsilon": rows,
        "runtime_ms": round((time.perf_counter() - start) * 1000, 1),
    }