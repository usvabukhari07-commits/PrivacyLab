RULES_VERSION = "risk-rules-v1"

THRESHOLDS = {
    "budget_medium": 0.5,     # share of budget used
    "budget_high": 0.8,
    "epsilon_moderate": 0.5,  # per-query epsilon
    "epsilon_weak": 1.0,
    "noise_ratio_warn": 0.5,  # noise scale compared with the released value
}

LEVELS = ["LOW", "MEDIUM", "HIGH"]


def _worse(a, b):
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


def explain_risk(spec, evidence, rows, suppressed_groups, budget_remaining,
                 budget_total, cached, thresholds=None):
    t = dict(THRESHOLDS)
    if thresholds:
        t.update(thresholds)

    reasons = []
    overall = "LOW"

    def add(rule, level, affects, detail):
        reasons.append({"rule": rule, "level": level, "affects": affects, "detail": detail})

    # R1: how much of the budget is used
    used = (budget_total - budget_remaining) / budget_total if budget_total > 0 else 1.0
    if used >= t["budget_high"]:
        lvl = "HIGH"
    elif used >= t["budget_medium"]:
        lvl = "MEDIUM"
    else:
        lvl = "LOW"
    add("R1_BUDGET_USAGE", lvl, "privacy",
        f"{used:.0%} of this dataset's privacy budget is used; {round(budget_remaining, 2)} epsilon is left.")
    overall = _worse(overall, lvl)

    # R2: size of epsilon for this query
    eps = spec["epsilon"]
    if eps > t["epsilon_weak"]:
        lvl, text = "HIGH", "weak privacy (little noise)"
    elif eps > t["epsilon_moderate"]:
        lvl, text = "MEDIUM", "moderate privacy"
    else:
        lvl, text = "LOW", "strong privacy (a lot of noise)"
    add("R2_EPSILON_SIZE", lvl, "privacy", f"Epsilon {eps} gives {text}.")
    overall = _worse(overall, lvl)

    # R3: small-group protection
    k = evidence.get("min_group_size")
    if suppressed_groups > 0:
        add("R3_SMALL_GROUPS", "LOW", "privacy",
            f"{suppressed_groups} group(s) with fewer than {k} people were hidden so no individual can be singled out.")
    elif spec.get("group_by"):
        add("R3_SMALL_GROUPS", "LOW", "privacy", f"Every group shown has at least {k} people.")

    # R4: is the noise large compared to the answer? (utility, not privacy)
    worst = 0.0
    for r in rows:
        v = abs(r["value"])
        ratio = r["noise_scale"] / v if v > 0 else float("inf")
        worst = max(worst, ratio)
    if rows and worst > t["noise_ratio_warn"]:
        add("R4_NOISE_VS_VALUE", "MEDIUM", "utility",
            "Noise is large compared with at least one released value, so that number may be unreliable.")
    elif rows:
        add("R4_NOISE_VS_VALUE", "LOW", "utility", "Noise is small compared with the released values.")

    # R5: repeat query
    if cached:
        add("R5_REPEAT_QUERY", "LOW", "privacy",
            "This repeats an earlier query, so the saved answer was returned and no extra privacy was spent.")

    # R6: mechanism note
    if spec["mechanism"] == "gaussian":
        add("R6_MECHANISM", "LOW", "info",
            f"Gaussian mechanism gives (epsilon, delta)-privacy with delta = {evidence.get('delta')}.")

    actions = {
        "LOW": "No action needed.",
        "MEDIUM": "Use smaller epsilon values and avoid unnecessary queries.",
        "HIGH": "Pause and ask an administrator to review: the budget is nearly used or epsilon is large.",
    }
    return {
        "rules_version": RULES_VERSION,
        "risk_level": overall,
        "summary": f"Privacy risk of this release: {overall}.",
        "recommended_action": actions[overall],
        "reasons": reasons,
        "thresholds": t,
    }