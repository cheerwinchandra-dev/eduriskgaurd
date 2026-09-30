"""Plain-language explanations and the support taxonomy.

Explanations describe what the model associated with higher or lower risk.
They are not causes, and the wording reflects that.
"""
import json

from .modeling import FEATURES

CATEGORY = {
    "attendance_rate": "attendance", "attendance_change": "attendance",
    "assignment_completion": "workload", "assignment_change": "workload",
    "missed_submissions": "workload", "late_submissions": "workload",
    "lms_days": "engagement", "lms_change": "engagement", "inactive_weeks": "engagement",
    "gpa": "academic", "gpa_change": "academic", "failed_courses": "academic",
    "credit_ratio": "academic", "entrance_score": "academic",
    "fee_hold": "admin", "registration_delay_days": "admin",
    "advising_visits": "support", "term_number": "context",
}

SUPPORT = {
    "academic": {
        "title": "Academic progress",
        "interpretations": ["Course difficulty or a preparation gap", "Overload, illness or a change in circumstances"],
        "options": ["Tutoring or supplemental instruction", "Conversation with the course instructor", "Study plan or degree-plan review"],
        "intervention": "Tutoring referral",
    },
    "workload": {
        "title": "Assignments and deadlines",
        "interpretations": ["Workload pressure, unclear expectations or a technology problem"],
        "options": ["Deadline planning", "Accessibility or technology support", "Flexible-deadline conversation with the instructor"],
        "intervention": "Deadline or study plan",
    },
    "attendance": {
        "title": "Attendance",
        "interpretations": ["Health, work, transport or feeling disconnected"],
        "options": ["Private, open-ended check-in", "Flexible study or attendance options", "Case-management referral"],
        "intervention": "Private advisor check-in",
    },
    "engagement": {
        "title": "Learning platform activity",
        "interpretations": ["Access problems, offline study or disengagement"],
        "options": ["Private check-in", "Device or connectivity support", "A named human point of contact"],
        "intervention": "Technology or connectivity support",
    },
    "admin": {
        "title": "Fees and registration",
        "interpretations": ["Financial pressure or administrative confusion"],
        "options": ["Financial-aid counseling", "Registration assistance", "Information on emergency funding"],
        "intervention": "Financial-aid counseling",
    },
}

INTERVENTION_TYPES = [
    "Private advisor check-in", "Tutoring referral", "Financial-aid counseling", "Technology or connectivity support",
    "Deadline or study plan", "Faculty conversation", "Peer mentoring", "Counseling services (offered)", "Other",
]
CHANNELS = ["Email", "Text message", "Phone call", "In-person meeting"]
STATUSES = ["Planned", "Contacted", "Student responded", "Support in progress", "Completed", "Closed - no response"]
OPEN_STATUSES = {"Planned", "Contacted", "Student responded", "Support in progress"}


def _plural(n, word):
    n = int(round(n))
    return f"{n} {word}{'' if n == 1 else 's'}"


def phrase(feature, v):
    """A short sentence describing a feature value, or None if the value is missing."""
    if v is None:
        return None
    table = {
        "attendance_rate": lambda: f"Attendance is {v:.0f}%",
        "attendance_change": lambda: f"Attendance {'rose' if v >= 0 else 'fell'} by {abs(v):.0f} points over the last 4 weeks",
        "assignment_completion": lambda: f"{v:.0f}% of assignments completed this term",
        "assignment_change": lambda: f"Assignment completion {'rose' if v >= 0 else 'fell'} by {abs(v):.0f} points over the last 4 weeks",
        "missed_submissions": lambda: f"{_plural(v, 'missed submission')} this term",
        "late_submissions": lambda: f"{_plural(v, 'late submission')} this term",
        "lms_days": lambda: f"Active on the learning platform {v:.1f} days a week",
        "lms_change": lambda: f"Platform activity {'rose' if v >= 0 else 'dropped'} by {abs(v):.1f} days a week over the last 4 weeks",
        "inactive_weeks": lambda: f"{_plural(v, 'week')} with no platform activity",
        "gpa": lambda: f"Current GPA is {v:.2f}",
        "gpa_change": lambda: f"GPA {'rose' if v >= 0 else 'fell'} by {abs(v):.2f} since last term",
        "failed_courses": lambda: f"{_plural(v, 'failed course')} to date",
        "credit_ratio": lambda: f"{v * 100:.0f}% of attempted credits earned so far",
        "fee_hold": lambda: "An account hold is open" if v >= 0.5 else "No account hold",
        "registration_delay_days": lambda: f"Registration was {_plural(v, 'day')} late" if v >= 1 else "Registered on time",
        "advising_visits": lambda: "No advising visits this term" if v < 1 else f"{_plural(v, 'advising visit')} this term",
        "term_number": lambda: f"Term {int(v)} of study",
        "entrance_score": lambda: f"Entrance score of {v:.0f}",
    }
    fn = table.get(feature)
    return fn() if fn else None


def parse_contributions(blob):
    try:
        return json.loads(blob) if blob else []
    except (TypeError, ValueError):
        return []


def explain(blob, n_raise=4, n_protect=3, min_weight=0.04):
    """Split contributions into signals that raise and lower the estimate."""
    items = [c for c in parse_contributions(blob) if not c.get("imputed") and c.get("expected", True)]
    total = sum(abs(c["contribution"]) for c in parse_contributions(blob)) or 1.0
    out = {"raising": [], "protective": []}
    for c in items:
        w = abs(c["contribution"]) / total
        if w < min_weight:
            continue
        text = phrase(c["feature"], c["value"])
        if not text:
            continue
        entry = {"feature": c["feature"], "label": FEATURES[c["feature"]][0], "text": text, "weight": round(w, 3),
                 "category": CATEGORY.get(c["feature"], "context")}
        (out["raising"] if c["contribution"] > 0 else out["protective"]).append(entry)
    out["raising"] = out["raising"][:n_raise]
    out["protective"] = out["protective"][:n_protect]
    out["missing"] = [FEATURES[c["feature"]][0] for c in parse_contributions(blob) if c.get("imputed")]
    return out


def top_signals(blob, n=3):
    return [s["text"] for s in explain(blob, n_raise=n)["raising"]]


def categories_from(explanation, limit=3):
    seen = []
    for s in explanation["raising"]:
        cat = s["category"]
        if cat in SUPPORT and cat not in seen:
            seen.append(cat)
    return seen[:limit]


def recommendations(explanation):
    recs = []
    for cat in categories_from(explanation):
        info = SUPPORT[cat]
        recs.append({"category": cat, "title": info["title"], "possible_interpretation": info["interpretations"],
                     "support_options": info["options"], "suggested_type": info["intervention"]})
    if not recs:
        recs.append({"category": "general", "title": "General check-in",
                     "possible_interpretation": ["No single signal stands out"],
                     "support_options": ["Open-ended, private check-in"], "suggested_type": "Private advisor check-in"})
    return recs


def _num(v):
    return None if v is None or v != v else float(v)


def recent_changes(rec):
    """Observed trends and facts straight from the record (independent of model weights)."""
    out = []
    add = lambda label, text, tone: out.append({"label": label, "text": text, "tone": tone})

    def trend(label, v, threshold, worse_text, better_text):
        v = _num(v)
        if v is None:
            return
        if v <= -threshold:
            add(label, worse_text(abs(v)), "worse")
        elif v >= threshold:
            add(label, better_text(abs(v)), "better")

    trend("Attendance", rec.get("attendance_change"), 5, lambda a: f"Fell by {a:.0f} points over the last 4 weeks",
          lambda a: f"Rose by {a:.0f} points over the last 4 weeks")
    trend("Assignments", rec.get("assignment_change"), 5, lambda a: f"Completion fell by {a:.0f} points over the last 4 weeks",
          lambda a: f"Completion rose by {a:.0f} points over the last 4 weeks")
    trend("Platform activity", rec.get("lms_change"), 0.5, lambda a: f"Down {a:.1f} active days a week over the last 4 weeks",
          lambda a: f"Up {a:.1f} active days a week over the last 4 weeks")
    gpa, prior = _num(rec.get("gpa")), _num(rec.get("prior_gpa"))
    if gpa is not None and prior is not None and (rec.get("term_number") or 1) > 1:
        trend("GPA", gpa - prior, 0.15, lambda a: f"Down {a:.2f} since last term", lambda a: f"Up {a:.2f} since last term")
    missed, late, idle = _num(rec.get("missed_submissions")) or 0, _num(rec.get("late_submissions")) or 0, _num(rec.get("inactive_weeks")) or 0
    if missed >= 1:
        add("Missed submissions", f"{_plural(missed, 'submission')} missed this term", "worse" if missed >= 3 else "neutral")
    if late >= 2:
        add("Late submissions", f"{_plural(late, 'submission')} handed in late", "neutral")
    if idle >= 1:
        add("Inactive weeks", f"{_plural(idle, 'week')} with no platform activity", "worse" if idle >= 2 else "neutral")
    if (_num(rec.get("fee_hold")) or 0) >= 0.5:
        add("Account", "An account hold is open", "worse")
    if (_num(rec.get("registration_delay_days")) or 0) >= 5:
        add("Registration", f"Registration was {_plural(rec['registration_delay_days'], 'day')} late", "neutral")
    return out
