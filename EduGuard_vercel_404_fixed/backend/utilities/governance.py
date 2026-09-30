"""Governance gate between a raw score and an advisor alert.

A score never becomes an alert on its own. The gate checks data freshness,
whether the student is already being supported, whether an advisor dismissed
the alert, and whether the change is material enough to interrupt someone.
"""
from datetime import datetime, timedelta

from .common import parse_ts
from .explain import OPEN_STATUSES


def band(p, cfg):
    if p is None:
        return "Unavailable"
    if p >= cfg["risk"]["elevated_threshold"]:
        return "Elevated"
    if p >= cfg["risk"]["moderate_threshold"]:
        return "Moderate"
    return "Low"


def freshness(age_days, cfg):
    limit = cfg["alerts"]["max_data_age_days"]
    if age_days is None:
        return "unknown"
    if age_days > limit:
        return "stale"
    return "aging" if age_days > 3 else "fresh"


def decide(prob, prev_prob, age_days, interventions, overrides, cfg, now=None, fairness_review=False):
    """Return {'status', 'reasons'} for one student.

    status: alert | suppressed | watch | none | unavailable
    """
    now = now or datetime.now()
    a = cfg["alerts"]
    if prob is None:
        return {"status": "unavailable", "reasons": ["No estimate yet. Train the model once at least 3 terms of outcomes are loaded."]}
    if freshness(age_days, cfg) == "stale":
        return {"status": "unavailable",
                "reasons": [f"Learning-platform data is {age_days:.0f} days old, so no current score is shown."]}
    b = band(prob, cfg)
    if b == "Low":
        return {"status": "none", "reasons": []}

    if fairness_review:
        return {"status": "watch", "reasons": ["A subgroup fairness disparity is under review; score-based outreach is paused pending human evidence review."]}

    active_override = next((o for o in overrides if (parse_ts(o["until"]) or now) >= now), None)
    if active_override:
        return {"status": "suppressed", "reasons": [f"Dismissed by an advisor ({active_override['reason']}) until {active_override['until'][:10]}."]}

    open_cases = [i for i in interventions if i["status"] in OPEN_STATUSES]
    if open_cases:
        return {"status": "suppressed", "reasons": ["A support case is already open."]}
    cutoff = now - timedelta(days=a["cooldown_days"])
    if any((parse_ts(i["updated_at"]) or datetime.min) >= cutoff for i in interventions):
        return {"status": "suppressed", "reasons": [f"Contacted within the last {a['cooldown_days']} days."]}

    rise = (prob - prev_prob) if prev_prob is not None else 0.0
    if b == "Elevated":
        reasons = ["Estimate is in the elevated band."]
        if rise >= a["rise_alert_threshold"]:
            reasons.append("It rose noticeably since last term.")
        return {"status": "alert", "reasons": reasons}
    if rise >= a["rise_alert_threshold"]:
        return {"status": "alert", "reasons": ["Moderate estimate that rose sharply since last term."]}
    return {"status": "watch", "reasons": ["Moderate and steady, so no new alert."]}


def priority(prob, prev_prob):
    rise = max(0.0, (prob - prev_prob)) if prev_prob is not None else 0.0
    return float(prob + 0.5 * rise)


def confidence(age_days, prob, term_number, missing_count, cfg):
    reasons = []
    if age_days is not None and age_days > 3:
        reasons.append(f"Some data is {age_days:.0f} days old")
    r = cfg["risk"]
    if abs(prob - r["elevated_threshold"]) < 0.04 or abs(prob - r["moderate_threshold"]) < 0.02:
        reasons.append("The estimate sits close to a band boundary")
    if term_number is not None and term_number <= 1:
        reasons.append("Only one term of history is available")
    if missing_count >= 2:
        reasons.append("Some inputs were missing and were estimated")
    level = "High" if not reasons else "Moderate" if len(reasons) == 1 else "Low"
    return {"level": level, "reasons": reasons}
