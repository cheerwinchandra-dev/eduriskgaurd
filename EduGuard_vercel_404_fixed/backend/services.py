"""Business logic behind the API (kept free of web-framework code so it is easy to test)."""
import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import re

from . import agent, llm
from .utilities import bootstrap, cache, db, explain, importer, modeling
from .utilities import governance as gov
from .utilities.common import get_gemini_key, load_config, now_str, parse_ts, save_config, set_gemini_key

OVERRIDE_REASONS = ["Already in contact", "Doing well now", "Known temporary circumstance", "Data looks wrong", "Other"]
BAND_ORDER = {"Elevated": 0, "Moderate": 1, "Low": 2, "Unavailable": 3}


# ------------------------------------------------------------------ helpers
def _actor(role):
    """'advisor (jsmith)' when the request came from a signed-in person, else just the role."""
    who = getattr(role, "username", None)
    return f"{role} ({who})" if who else str(role)


def audit(role, action, student_id=None, detail=None):
    db.execute("INSERT INTO audit(ts,role,action,student_id,detail) VALUES(?,?,?,?,?)",
               (now_str(), _actor(role), action, student_id, detail))


def _bundle():
    return cache.get_bundle(modeling.load_bundle)


def _by_student(rows):
    out = {}
    for r in rows:
        out.setdefault(r["student_id"], []).append(r)
    return out


def _f(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


# ------------------------------------------------------------------ current cohort
def current_frame(cfg=None):
    """Everything the dashboard needs about the latest term, after the governance gate."""
    cfg = cfg or load_config()
    return cache.get_frame("current", 20, lambda: _build_current(cfg))


def _build_current(cfg):
    term = db.get_meta("current_term")
    if not term:
        return []
    rec = db.query(
        """SELECT r.student_id, r.term_number, s.program, s.mode, s.synced_at,
                  p.probability, p.model_version, p.created_at AS scored_at, p.contributions
           FROM records r JOIN students s ON s.student_id = r.student_id
           LEFT JOIN predictions p ON p.student_id = r.student_id AND p.term = r.term
           WHERE r.term = ?""", (term,))
    hist = db.query("SELECT student_id, term, probability FROM predictions WHERE term < ? ORDER BY term", (term,))
    hist_by = _by_student(hist)
    ints_by = _by_student(db.query("SELECT student_id, status, updated_at FROM interventions"))
    ovr_by = _by_student(db.query("SELECT student_id, reason, until FROM overrides"))
    bundle = _bundle()
    fairness_review = bool(bundle and bundle.get("fairness", {}).get("status") == "review")

    now = datetime.now()
    rows = []
    for r in rec:
        sid = r["student_id"]
        prob = _f(r["probability"])
        past = [h["probability"] for h in hist_by.get(sid, [])]
        prev = past[-1] if past else None
        synced = parse_ts(r["synced_at"])
        age = (now - synced).total_seconds() / 86400 if synced else None
        ints = ints_by.get(sid, [])
        d = gov.decide(prob, prev, age, ints, ovr_by.get(sid, []), cfg, now, fairness_review=fairness_review)
        stale = d["status"] == "unavailable"
        shown = None if stale else prob
        rows.append({
            "student_id": sid, "program": r["program"], "mode": r["mode"], "term_number": r["term_number"],
            "risk": shown, "band": gov.band(shown, cfg), "prev_risk": prev,
            "change": (shown - prev) if (shown is not None and prev is not None) else None,
            "history": [round(x, 3) for x in past] + ([round(shown, 3)] if shown is not None else []),
            "signals": [] if stale else explain.top_signals(r["contributions"], 3),
            "status": d["status"], "reasons": d["reasons"],
            "priority": gov.priority(prob, prev) if d["status"] == "alert" else 0.0,
            "in_queue": False, "queue_rank": None,
            "freshness": gov.freshness(age, cfg), "age_days": age,
            "contacts": len(ints), "last_contact": max((i["updated_at"] for i in ints), default=None),
            "model_version": r["model_version"], "scored_at": r["scored_at"], "_blob": r["contributions"],
        })
    alerts = sorted((x for x in rows if x["status"] == "alert"), key=lambda x: -x["priority"])
    cap = cfg["alerts"]["weekly_capacity"]
    for i, x in enumerate(alerts):
        x["queue_rank"] = i + 1
        x["in_queue"] = i < cap
    return rows


def _public(item):
    return {k: v for k, v in item.items() if not k.startswith("_")}


def list_students(q="", band="", program="", status="", sort="risk", page=1, size=25):
    rows = current_frame()
    q = (q or "").strip().lower()
    out = [r for r in rows
           if (not q or q in r["student_id"].lower() or q in (r["program"] or "").lower())
           and (not band or r["band"] == band) and (not program or r["program"] == program)
           and (not status or r["status"] == status)]
    if sort == "change":
        out.sort(key=lambda r: -(r["change"] if r["change"] is not None else -9))
    elif sort == "id":
        out.sort(key=lambda r: r["student_id"])
    else:
        out.sort(key=lambda r: (BAND_ORDER[r["band"]], -(r["risk"] or 0)))
    size = max(5, min(int(size), 100))
    page = max(1, int(page))
    start = (page - 1) * size
    return {"total": len(out), "page": page, "size": size, "items": [_public(r) for r in out[start:start + size]],
            "programs": sorted({r["program"] for r in rows if r["program"]})}


def alert_queue():
    cfg = load_config()
    rows = current_frame(cfg)
    alerts = sorted((r for r in rows if r["status"] == "alert"), key=lambda r: r["queue_rank"])
    count = lambda s: sum(1 for r in rows if r["status"] == s)
    return {
        "capacity": cfg["alerts"]["weekly_capacity"],
        "queue": [_public(r) for r in alerts if r["in_queue"]],
        "waitlist": [_public(r) for r in alerts if not r["in_queue"]][:50],
        "waitlist_count": sum(1 for r in alerts if not r["in_queue"]),
        "suppressed_count": count("suppressed"), "watch_count": count("watch"), "unavailable_count": count("unavailable"),
        "fairness_gate": _fairness_guardrail(),
    }


# ------------------------------------------------------------------ summary
def _funnel():
    since = _ts(datetime.now() - timedelta(days=30))
    rows = db.query("SELECT status FROM interventions WHERE created_at >= ?", (since,))
    n = lambda names: sum(1 for r in rows if r["status"] in names)
    return {"cases": len(rows), "contacted": n(set(explain.STATUSES) - {"Planned"}),
            "responded": n({"Student responded", "Support in progress", "Completed"}),
            "support_started": n({"Support in progress", "Completed"}), "completed": n({"Completed"})}


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def summary():
    cfg = load_config()
    rows = current_frame(cfg)
    if not rows:
        return {"ready": False, "term": db.get_meta("current_term"), "students": 0}
    bands = {b: sum(1 for r in rows if r["band"] == b) for b in BAND_ORDER}
    risks = [r["risk"] for r in rows if r["risk"] is not None]
    ages = [r["age_days"] for r in rows if r["age_days"] is not None]
    b = _bundle()
    card = b["card"] if b else None
    preds = db.frame("SELECT term, probability FROM predictions")
    trend = []
    for term, grp in preds.groupby("term"):
        p = grp["probability"].values
        trend.append({"term": term, "Low": int((p < cfg["risk"]["moderate_threshold"]).sum()),
                      "Moderate": int(((p >= cfg["risk"]["moderate_threshold"]) & (p < cfg["risk"]["elevated_threshold"])).sum()),
                      "Elevated": int((p >= cfg["risk"]["elevated_threshold"]).sum())})
    by_program = {}
    for r in rows:
        g = by_program.setdefault(r["program"], {"program": r["program"], "n": 0, "flagged": 0})
        g["n"] += 1
        g["flagged"] += 1 if r["band"] in ("Moderate", "Elevated") else 0
    queue_n = sum(1 for r in rows if r["in_queue"])
    return {
        "ready": True, "term": db.get_meta("current_term"), "students": len(rows), "bands": bands,
        "average_risk": float(np.mean(risks)) if risks else None,
        "queue": queue_n, "capacity": cfg["alerts"]["weekly_capacity"],
        "waitlist": sum(1 for r in rows if r["status"] == "alert") - queue_n,
        "suppressed": sum(1 for r in rows if r["status"] == "suppressed"),
        "stale": bands["Unavailable"],
        "freshness": {"median_age_days": float(np.median(ages)) if ages else None,
                      "max_age_days": float(max(ages)) if ages else None,
                      "limit_days": cfg["alerts"]["max_data_age_days"]},
        "funnel": _funnel(), "trend": sorted(trend, key=lambda t: t["term"]),
        "programs": sorted(by_program.values(), key=lambda g: -g["flagged"] / max(g["n"], 1)),
        "fairness": _fairness_guardrail(),
        "model": None if not card else {
            "version": card["version"], "trained_at": card["trained_at"], "source": card["data_source"],
            "pr_auc": card["metrics"]["logistic"]["pr_auc"], "roc_auc": card["metrics"]["logistic"]["roc_auc"],
            "recall_moderate": card["metrics"]["logistic"]["moderate"]["recall"],
            "precision_moderate": card["metrics"]["logistic"]["moderate"]["precision"],
            "base_rate": card["metrics"]["logistic"]["base_rate"]},
    }


# ------------------------------------------------------------------ student detail
def student_detail(student_id, role):
    cfg = load_config()
    item = next((r for r in current_frame(cfg) if r["student_id"] == student_id), None)
    if item is None:
        raise LookupError("Student not found")
    term = db.get_meta("current_term")
    terms = db.query("SELECT term, term_number, gpa, attendance_rate, assignment_completion, lms_days "
                     "FROM records WHERE student_id=? ORDER BY term", (student_id,))
    weekly = db.query("SELECT week, attendance, lms_days, assign_done FROM weekly WHERE student_id=? AND term=? ORDER BY week",
                      (student_id, term))
    risk_hist = db.query("SELECT term, probability, retrospective FROM predictions WHERE student_id=? ORDER BY term", (student_id,))
    ints = db.query("SELECT * FROM interventions WHERE student_id=? ORDER BY created_at DESC", (student_id,))
    notes = db.query("SELECT * FROM notes WHERE student_id=? ORDER BY created_at DESC", (student_id,))
    ovr = [o for o in db.query("SELECT * FROM overrides WHERE student_id=? ORDER BY created_at DESC", (student_id,))
           if (parse_ts(o["until"]) or datetime.min) >= datetime.now()]
    rec_row = db.one("SELECT * FROM records WHERE student_id=? AND term=?", (student_id, term)) or {}
    stale = item["status"] == "unavailable"
    exp = {"raising": [], "protective": [], "missing": []} if stale else _faculty_explain(item["_blob"])
    conf = None if stale else gov.confidence(item["age_days"], item["risk"], item["term_number"], len(exp["missing"]), cfg)
    audit(role, "view_student", student_id)
    return {
        "student": _public(item), "term": term,
        "terms": terms, "weekly": weekly,
        "risk_history": [{"term": r["term"], "probability": r["probability"], "estimate": bool(r["retrospective"])} for r in risk_hist],
        "explanation": exp, "changes": explain.recent_changes(rec_row), "confidence": conf, "recommendations": [] if stale else explain.recommendations(exp),
        "interventions": ints, "notes": notes, "overrides": ovr,
        "thresholds": cfg["risk"],
    }


# ------------------------------------------------------------------ faculty student view
FACULTY_SORTS = {"risk", "change", "id"}
FACULTY_FEATURES = {
    "gpa", "gpa_change", "failed_courses", "credit_ratio",
    "attendance_rate", "attendance_change", "assignment_completion", "assignment_change",
    "missed_submissions", "late_submissions", "lms_days", "lms_change", "inactive_weeks",
}


def _faculty_explain(blob):
    exp = explain.explain(blob)
    for key in ("raising", "protective"):
        exp[key] = [x for x in exp[key] if x["feature"] in FACULTY_FEATURES]
    exp["missing"] = [
        modeling.FEATURES[c["feature"]][0]
        for c in explain.parse_contributions(blob)
        if c.get("imputed") and c.get("feature") in FACULTY_FEATURES
    ]
    return exp


def _faculty_signals(blob, n=3):
    exp = _faculty_explain(blob)
    return [s["text"] for s in exp["raising"][:n]]


def _faculty_student_public(item):
    allowed = ("student_id", "program", "mode", "term_number", "risk", "prev_risk", "change",
               "history", "freshness", "age_days", "band")
    out = {k: item.get(k) for k in allowed}
    out["signals"] = _faculty_signals(item["_blob"], 3) if item.get("_blob") and item["status"] != "unavailable" else []
    return out


def _fairness_guardrail():
    """Return a faculty-safe summary of any material subgroup disparity."""
    b = _bundle()
    if not b or not b.get("fairness"):
        return {"status": "not_available", "message": "No fairness audit is available for the current model."}
    fairness = b["fairness"]
    groups = fairness.get("groups", [])
    candidates = [g for g in groups if g.get("sufficient")]
    threshold = load_config().get("fairness", {}).get("calibration_gap_threshold", 0.05)
    overpred = [g for g in candidates if g.get("calibration_gap") is not None and g["calibration_gap"] > threshold]
    worst = max(overpred, key=lambda g: g["calibration_gap"], default=None)
    active = fairness.get("status") == "review"
    if worst:
        message = (
            f"{worst['attribute_title']}: {worst['group']} has a {worst['calibration_gap']:+.1%} calibration gap "
            f"(mean predicted {worst['mean_predicted']:.1%} vs observed {worst['observed_rate']:.1%})."
        )
    elif active:
        message = "At least one subgroup has a material false-positive or false-negative rate disparity and is under review."
    else:
        message = "No material subgroup disparity crossed the fairness review rules."
    return {
        "status": "review" if active else "clear",
        "message": message,
        "largest_overprediction": round(worst["calibration_gap"], 4) if worst else None,
        "group_count": int(fairness.get("disparities", {}).get("groups_in_review", 0)),
        "threshold": threshold,
    }


def list_faculty_students(q="", band="", program="", sort="risk", page=1, size=25, role=None):
    rows = current_frame()
    q = (q or "").strip().lower()
    band = (band or "").strip()
    program = (program or "").strip()
    sort = sort if sort in FACULTY_SORTS else "risk"
    out = [r for r in rows
           if (not q or q in r["student_id"].lower() or q in (r["program"] or "").lower())
           and (not band or r["band"] == band)
           and (not program or r["program"] == program)]
    if sort == "change":
        out.sort(key=lambda x: -(x["change"] if x["change"] is not None else -1))
    elif sort == "id":
        out.sort(key=lambda x: x["student_id"])
    else:
        out.sort(key=lambda x: (BAND_ORDER.get(x["band"], 9), -(x["risk"] if x["risk"] is not None else -1)))
    page = max(1, int(page)); size = max(1, min(50, int(size)))
    start = (page - 1) * size
    programs = sorted({r["program"] for r in rows if r.get("program")})
    audit(role, "view_faculty_students", None, f"page={page};size={size}") if role else None
    items = [_faculty_student_public(r) for r in out[start:start + size]]
    return {
        "items": items,
        "total": len(out), "page": page, "size": size, "programs": programs,
        "fairness_guardrail": _fairness_guardrail(),
    }


def faculty_student_detail(student_id, role):
    cfg = load_config()
    item = next((r for r in current_frame(cfg) if r["student_id"] == student_id), None)
    if item is None:
        raise LookupError("Student not found")
    term = db.get_meta("current_term")
    rec = db.one(
        "SELECT term, term_number, gpa, prior_gpa, attendance_rate, attendance_change, "
        "assignment_completion, assignment_change, missed_submissions, late_submissions, lms_days, lms_change, inactive_weeks "
        "FROM records WHERE student_id=? AND term=?", (student_id, term)
    ) or {}
    terms = db.query("SELECT term, term_number, gpa, attendance_rate, assignment_completion, lms_days, missed_submissions FROM records WHERE student_id=? ORDER BY term", (student_id,))
    weekly = db.query("SELECT week, attendance, lms_days, assign_done FROM weekly WHERE student_id=? AND term=? ORDER BY week", (student_id, term))
    risk_hist = db.query("SELECT term, probability, retrospective FROM predictions WHERE student_id=? ORDER BY term", (student_id,))
    stale = item["status"] == "unavailable"
    exp = {"raising": [], "protective": [], "missing": []} if stale else _faculty_explain(item["_blob"])
    conf = None if stale else gov.confidence(item["age_days"], item["risk"], item["term_number"], len(exp["missing"]), cfg)
    student = _faculty_student_public(item)
    student["model_version"] = item.get("model_version")
    student["scored_at"] = item.get("scored_at")
    changes = explain.recent_changes(rec)
    changes = [c for c in changes if c["label"] in {
        "Attendance", "Assignments", "Platform activity", "GPA", "Missed submissions", "Late submissions", "Inactive weeks"
    }]
    audit(role, "view_faculty_student", student_id)
    return {
        "student": student,
        "term": term,
        "record": _public(rec) if rec else {},
        "changes": changes,
        "terms": terms,
        "weekly": weekly,
        "risk_history": [{"term": r["term"], "probability": r["probability"], "estimate": bool(r["retrospective"])} for r in risk_hist],
        "explanation": exp,
        "confidence": conf,
        "fairness_guardrail": _fairness_guardrail(),
        "thresholds": cfg["risk"],
        "privacy": "Faculty view omits demographic attributes, intervention history, advisor notes and account-level data.",
    }


# ------------------------------------------------------------------ interventions, notes, overrides
def add_intervention(student_id, payload, role):
    itype, channel, status = payload.get("type"), payload.get("channel", "Email"), payload.get("status", "Planned")
    if itype not in explain.INTERVENTION_TYPES:
        raise ValueError("Choose a support type from the list.")
    if channel not in explain.CHANNELS:
        raise ValueError("Choose a contact channel from the list.")
    if status not in explain.STATUSES:
        raise ValueError("Choose a status from the list.")
    if not db.one("SELECT 1 AS x FROM students WHERE student_id=?", (student_id,)):
        raise LookupError("Student not found")
    now = now_str()
    new_id = db.execute(
        "INSERT INTO interventions(student_id,created_at,updated_at,type,channel,status,outcome,note,author) VALUES(?,?,?,?,?,?,?,?,?)",
        (student_id, now, now, itype, channel, status, payload.get("outcome", ""), (payload.get("note") or "")[:1000], _actor(role)))
    cache.clear()
    audit(role, "add_intervention", student_id, f"{itype} / {status}")
    return db.one("SELECT * FROM interventions WHERE id=?", (new_id,))


def update_intervention(iid, payload, role):
    row = db.one("SELECT * FROM interventions WHERE id=?", (iid,))
    if not row:
        raise LookupError("Intervention not found")
    status = payload.get("status", row["status"])
    if status not in explain.STATUSES:
        raise ValueError("Choose a status from the list.")
    db.execute("UPDATE interventions SET status=?, outcome=?, note=?, updated_at=? WHERE id=?",
               (status, payload.get("outcome", row["outcome"]), (payload.get("note", row["note"]) or "")[:1000], now_str(), iid))
    cache.clear()
    audit(role, "update_intervention", row["student_id"], f"#{iid} -> {status}")
    return db.one("SELECT * FROM interventions WHERE id=?", (iid,))


def add_note(student_id, body, role):
    body = (body or "").strip()
    if not body:
        raise ValueError("Write a note before saving.")
    db.execute("INSERT INTO notes(student_id,created_at,author,body) VALUES(?,?,?,?)", (student_id, now_str(), _actor(role), body[:2000]))
    audit(role, "add_note", student_id)
    return db.query("SELECT * FROM notes WHERE student_id=? ORDER BY created_at DESC", (student_id,))


def add_override(student_id, reason, note, role):
    if reason not in OVERRIDE_REASONS:
        raise ValueError("Choose a reason from the list.")
    days = load_config()["alerts"]["dismiss_days"]
    until = _ts(datetime.now() + timedelta(days=days))
    db.execute("INSERT INTO overrides(student_id,created_at,reason,note,until) VALUES(?,?,?,?,?)",
               (student_id, now_str(), reason, (note or "")[:500], until))
    cache.clear()
    audit(role, "dismiss_alert", student_id, reason)
    return {"until": until}


def list_interventions(status=""):
    rows = db.query("SELECT * FROM interventions ORDER BY updated_at DESC LIMIT 500")
    band = {r["student_id"]: (r["band"], r["program"]) for r in current_frame()}
    for r in rows:
        r["band"], r["program"] = band.get(r["student_id"], ("Unavailable", ""))
    all_rows = rows
    if status:
        rows = [r for r in rows if r["status"] == status]
    n = len(all_rows) or 1
    by_status = {s: sum(1 for r in all_rows if r["status"] == s) for s in explain.STATUSES}
    by_type = {}
    for r in all_rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    responded = sum(by_status[s] for s in ("Student responded", "Support in progress", "Completed"))
    contacted = sum(v for k, v in by_status.items() if k != "Planned")
    return {"items": rows[:200], "stats": {
        "total": len(all_rows), "by_status": by_status, "by_type": by_type,
        "response_rate": responded / contacted if contacted else None,
        "completion_rate": by_status["Completed"] / n if all_rows else None,
        "open": sum(by_status[s] for s in explain.OPEN_STATUSES)},
        "types": explain.INTERVENTION_TYPES, "channels": explain.CHANNELS, "statuses": explain.STATUSES}


# ------------------------------------------------------------------ analytics (aggregate only)
def analytics():
    term = db.get_meta("current_term")
    if not term:
        return {"ready": False}
    rec = db.frame("""SELECT r.term, r.student_id, r.gpa, r.attendance_rate, r.assignment_completion, r.lms_days,
                             r.missed_submissions, s.program, s.mode
                      FROM records r JOIN students s ON s.student_id = r.student_id""")
    cur = rec[rec["term"] == term]
    by_term = (rec.groupby("term").agg(gpa=("gpa", "mean"), attendance=("attendance_rate", "mean"),
                                       assignments=("assignment_completion", "mean"), lms=("lms_days", "mean"),
                                       students=("student_id", "size")).reset_index())

    def group(col):
        out = []
        for name, g in cur.groupby(col):
            if len(g) < 10:  # small groups are hidden to protect privacy
                continue
            out.append({"name": name, "n": int(len(g)), "gpa": float(g["gpa"].mean()), "attendance": float(g["attendance_rate"].mean()),
                        "assignments": float(g["assignment_completion"].mean()), "lms": float(g["lms_days"].mean()),
                        "low_attendance_share": float((g["attendance_rate"] < 75).mean()),
                        "low_gpa_share": float((g["gpa"] < 2.0).mean())})
        return out

    def hist(series, edges, labels):
        cats = pd.cut(series, edges, labels=labels, right=False, include_lowest=True)
        counts = cats.value_counts().reindex(labels, fill_value=0)
        return [{"bucket": k, "count": int(v)} for k, v in counts.items()]

    weekly = db.frame("SELECT week, AVG(attendance) AS attendance, AVG(lms_days) AS lms, AVG(assign_done)*100 AS assignments "
                      "FROM weekly WHERE term=? GROUP BY week ORDER BY week", (term,))
    return {
        "ready": True, "term": term, "by_term": by_term.to_dict("records"),
        "by_program": group("program"), "by_mode": group("mode"),
        "attendance_distribution": hist(cur["attendance_rate"], [0, 50, 60, 70, 80, 90, 101],
                                        ["Under 50%", "50-59%", "60-69%", "70-79%", "80-89%", "90-100%"]),
        "gpa_distribution": hist(cur["gpa"], [0, 2.0, 2.5, 3.0, 3.5, 4.01], ["Under 2.0", "2.0-2.4", "2.5-2.9", "3.0-3.4", "3.5-4.0"]),
        "weekly": weekly.to_dict("records"),
    }


# ------------------------------------------------------------------ model, fairness, reports
def model_info():
    b = _bundle()
    if not b:
        return {"trained": False, "source": db.get_meta("source"), "thresholds": load_config()["risk"]}
    records = db.frame("SELECT r.*, s.entrance_score FROM records r JOIN students s ON s.student_id=r.student_id WHERE r.term=?",
                       (b["current_term"],))
    records["gpa_change"] = records["gpa"] - records["prior_gpa"]
    return {"trained": True, "card": b["card"], "fairness": b["fairness"],
            "drift": modeling.drift_report(b, records)[:8], "thresholds": load_config()["risk"]}


def equity_of_support():
    """Do flagged students in each group receive comparable contact?"""
    cfg = load_config()
    rows = {r["student_id"]: r for r in current_frame(cfg)}
    st = db.frame("SELECT student_id, gender, first_generation, financial_aid, mode FROM students")
    st = st[st["student_id"].isin(rows)]
    st["flagged"] = st["student_id"].map(lambda s: rows[s]["band"] in ("Moderate", "Elevated"))
    st["contacted"] = st["student_id"].map(lambda s: rows[s]["contacts"] > 0)
    out = []
    labels = modeling.GROUP_LABELS
    for attr in ("gender", "first_generation", "financial_aid", "mode"):
        for val, g in st[st["flagged"]].groupby(attr, dropna=True):
            label = labels.get(attr, {}).get(val, val)
            out.append({"attribute": modeling.ATTRIBUTE_TITLES[attr], "group": str(label), "flagged": int(len(g)),
                        "contacted": int(g["contacted"].sum()),
                        "contact_rate": float(g["contacted"].mean()) if len(g) >= 10 else None,
                        "sufficient": bool(len(g) >= 10)})
    return out


def reports_overview():
    s = summary()
    ints = list_interventions()
    return {"generated_at": now_str(), "summary": s, "interventions": ints["stats"], "funnel": s.get("funnel"),
            "equity_of_support": equity_of_support()}


def export_csv(kind, role):
    rows = current_frame()
    if kind == "alerts":
        data = [{"student_id": r["student_id"], "program": r["program"], "term": db.get_meta("current_term"),
                 "estimated_risk": round(r["risk"], 3), "band": r["band"],
                 "change_vs_last_term": None if r["change"] is None else round(r["change"], 3),
                 "main_signals": "; ".join(r["signals"]), "queue_rank": r["queue_rank"],
                 "in_this_week_queue": r["in_queue"], "data_age_days": round(r["age_days"] or 0, 1)}
                for r in rows if r["status"] == "alert"]
        data.sort(key=lambda d: d["queue_rank"])
    elif kind == "students":
        data = [{"student_id": r["student_id"], "program": r["program"], "mode": r["mode"], "term_number": r["term_number"],
                 "estimated_risk": None if r["risk"] is None else round(r["risk"], 3), "band": r["band"],
                 "alert_status": r["status"], "data_freshness": r["freshness"]} for r in rows]
    elif kind == "interventions":
        data = db.query("SELECT id, student_id, created_at, updated_at, type, channel, status, outcome, note FROM interventions ORDER BY created_at DESC")
    elif kind == "fairness":
        b = _bundle()
        data = [{k: v for k, v in g.items() if k != "notes"} | {"notes": "; ".join(g["notes"])} for g in (b["fairness"]["groups"] if b else [])]
    elif kind == "audit":
        data = db.query("SELECT ts, role, action, student_id, detail FROM audit ORDER BY id DESC LIMIT 5000")
    else:
        raise ValueError("Unknown report")
    audit(role, "export", None, kind)
    return f"eduguard_{kind}_{datetime.now():%Y%m%d}.csv", pd.DataFrame(data).to_csv(index=False)


def audit_log(limit=200):
    return db.query("SELECT ts, role, action, student_id, detail FROM audit ORDER BY id DESC LIMIT ?", (int(limit),))


# ------------------------------------------------------------------ settings & maintenance
def get_settings():
    cfg = load_config()
    return {"risk": cfg["risk"], "alerts": cfg["alerts"], "assistant": cfg["assistant"], "fairness": cfg["fairness"],
            "source": db.get_meta("source"), "version": cfg["version"], "model_version": db.get_meta("model_version"),
            "current_term": db.get_meta("current_term"),
            "counts": {"students": (db.one("SELECT COUNT(DISTINCT student_id) c FROM records") or {"c": 0})["c"],
                       "records": (db.one("SELECT COUNT(*) c FROM records") or {"c": 0})["c"]}}


def update_settings(changes, role):
    before = load_config()["risk"]
    save_config(changes)
    after = load_config()["risk"]
    if before != after:
        bootstrap.reevaluate()
    cache.clear()
    audit(role, "update_settings", None, json.dumps(changes)[:500])
    return get_settings()


# ------------------------------------------------------------------ assistant
def draft_message(student_id, channel, tone, role):
    item = next((r for r in current_frame() if r["student_id"] == student_id), None)
    if item is None:
        raise LookupError("Student not found")
    areas = [] if item["status"] == "unavailable" else explain.categories_from(explain.explain(item["_blob"]))
    result = agent.draft(areas, channel if channel in explain.CHANNELS else "Email", tone if tone in ("warm", "brief") else "warm")
    audit(role, "draft_message", student_id, result["source"])
    return result


def assistant_brief(student_id, role):
    """An AI-written (or rule-based) conversation brief built only from de-identified facts."""
    cfg = load_config()
    item = next((r for r in current_frame(cfg) if r["student_id"] == student_id), None)
    if item is None:
        raise LookupError("Student not found")
    if item["status"] == "unavailable":
        raise ValueError("No brief is available because this student has no current estimate.")
    term = db.get_meta("current_term")
    rec_row = db.one("SELECT * FROM records WHERE student_id=? AND term=?", (student_id, term)) or {}
    exp = explain.explain(item["_blob"])
    conf = gov.confidence(item["age_days"], item["risk"], item["term_number"], len(exp["missing"]), cfg)
    focus = explain.categories_from(exp)
    facts = agent.deidentify_case(item, exp, explain.recent_changes(rec_row), conf, focus)
    result = agent.case_brief(facts, explain.recommendations(exp), focus)
    audit(role, "ai_brief", student_id, result["source"])
    return result


_ID_LIKE = re.compile(r"\b[A-Za-z]{1,5}-\d{3,}\b")


def _ask_context():
    """Group-level statistics only. Groups under the minimum size were already removed upstream."""
    s = summary()
    a = analytics()
    b = _bundle()
    r1 = lambda v: None if v is None else round(float(v), 3)
    ctx = {
        "term": s.get("term"), "students_monitored": s.get("students"), "students_per_band": s.get("bands"),
        "weekly_outreach_queue": {"in_queue": s.get("queue"), "capacity": s.get("capacity"), "waiting": s.get("waitlist")},
        "students_without_score_because_data_is_stale": s.get("stale"), "data_freshness_days": s.get("freshness"),
        "support_last_30_days": s.get("funnel"), "band_counts_by_term": s.get("trend"),
        "moderate_or_elevated_by_program": [{"program": p["program"], "students": p["n"], "flagged": p["flagged"],
                                             "share": r1(p["flagged"] / p["n"])} for p in s.get("programs", [])],
    }
    if a.get("ready"):
        ctx["averages_by_term"] = [{k: (r1(v) if isinstance(v, float) else v) for k, v in t.items()} for t in a["by_term"]]
        ctx["engagement_by_program"] = [{k: (r1(v) if isinstance(v, float) else v) for k, v in g.items()} for g in a["by_program"]]
        ctx["engagement_by_study_mode"] = [{k: (r1(v) if isinstance(v, float) else v) for k, v in g.items()} for g in a["by_mode"]]
        ctx["attendance_distribution"] = a["attendance_distribution"]
        ctx["gpa_distribution"] = a["gpa_distribution"]
    if b:
        m = b["card"]["metrics"]["logistic"]
        ctx["model"] = {"trained": b["card"]["trained_at"][:10], "data_source": b["card"]["data_source"], "students_tested": m["n"],
                        "base_rate_of_leaving": r1(m["base_rate"]), "pr_auc": r1(m["pr_auc"]), "roc_auc": r1(m["roc_auc"]),
                        "share_of_leavers_found_at_moderate": r1(m["moderate"]["recall"]),
                        "share_correct_when_flagged_moderate": r1(m["moderate"]["precision"]),
                        "limitations": b["card"]["limitations"]}
        ctx["fairness_check"] = [{"attribute": g["attribute_title"], "group": g["group"], "students": g["n"],
                                  "observed_rate": r1(g["observed_rate"]), "estimated_rate": r1(g["mean_predicted"]),
                                  "needs_review": g["review"], "notes": g["notes"]} for g in b["fairness"]["groups"] if g["sufficient"]]
    ctx["support_reaching_flagged_students_by_group"] = [
        {"attribute": e["attribute"], "group": e["group"], "flagged": e["flagged"], "contact_rate": r1(e["contact_rate"])}
        for e in equity_of_support() if e["sufficient"]]
    return ctx


def assistant_ask(question, history, role):
    question = (question or "").strip()
    if not question:
        raise ValueError("Type a question first.")
    if len(question) > 500:
        raise ValueError("Please keep the question under 500 characters.")
    if _ID_LIKE.search(question):
        raise ValueError("Please don't include student IDs. This assistant only works with group-level data.")
    turns = [{"role": h["role"], "text": str(h["text"])[:800]} for h in (history or [])[-4:]
             if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("text")]
    result = agent.ask(question, turns, _ask_context())
    audit(role, "ai_ask", None, f"{result['source']}: {question[:120]}")
    return result


# ------------------------------------------------------------------ AI provider settings
def update_ai_config(payload, role):
    if payload.get("remove_key"):
        set_gemini_key(None)
    elif payload.get("api_key"):
        key = str(payload["api_key"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{20,120}", key):
            raise ValueError("That doesn't look like a Gemini API key. Copy it again from Google AI Studio.")
        set_gemini_key(key)
    changes = {k: payload[k] for k in ("provider", "gemini_mode", "gemini_model", "gemini_attested") if k in payload}
    if "gemini_model" in changes:
        changes["gemini_model"] = str(changes["gemini_model"]).strip().replace("models/", "")
    if changes.get("gemini_mode", "off") != "off" and not get_gemini_key():
        raise ValueError("Save a Gemini API key before turning Gemini on.")
    save_config({"assistant": changes})
    note = ", ".join(sorted(k for k in changes)) + (", key removed" if payload.get("remove_key") else ", key saved" if payload.get("api_key") else "")
    audit(role, "update_ai_settings", None, note)  # never the key itself
    return agent.status()


def test_gemini(payload, role):
    """Check the key and list usable models. Sends no student data (only the word OK)."""
    key = (payload.get("api_key") or "").strip() or get_gemini_key()
    if not key:
        raise ValueError("Enter a Gemini API key first.")
    models = llm.list_models(key)
    model = (payload.get("model") or load_config()["assistant"]["gemini_model"]).replace("models/", "")
    model_ok = model in models
    if model_ok:
        llm.gemini_generate("Reply with the single word OK.", "Say OK.", max_tokens=256, temperature=0, model=model, key=key)
    audit(role, "test_gemini", None, "ok" if model_ok else "model not available")
    return {"ok": True, "models": models[:25], "model_ok": model_ok, "suggested": models[0] if models else None,
            "message": "The key works and the model responded." if model_ok else
            (f"The key works, but {model} isn't available to it. Try {models[0]}." if models else "The key works, but no chat models were listed.")}


# ------------------------------------------------------------------ student registration
_REG_LABELS = {
    "student_id": "Student ID", "gpa": "GPA", "attendance_rate": "Attendance", "assignment_completion": "Assignment completion",
    "term_number": "Term number", "credit_ratio": "Credits passed ratio", "failed_courses": "Failed courses",
    "missed_submissions": "Missed submissions", "late_submissions": "Late submissions", "lms_days": "Days active online per week",
    "inactive_weeks": "Inactive weeks", "advising_visits": "Advising visits", "registration_delay_days": "Registration delay",
    "fee_hold": "Fee hold", "entrance_score": "Entrance score",
}
_REG_RECORD_FIELDS = ("gpa", "attendance_rate", "assignment_completion", "term_number", "credit_ratio", "failed_courses",
                      "missed_submissions", "late_submissions", "lms_days", "inactive_weeks", "advising_visits",
                      "registration_delay_days", "fee_hold")


def registration_options():
    """What the registration form needs: the term being scored and the programs and modes already in use."""
    unset = ("", "Unspecified")
    def distinct(col):
        return [r[col] for r in db.query(f"SELECT DISTINCT {col} FROM students WHERE {col} IS NOT NULL ORDER BY {col}") if r[col] not in unset]
    return {"current_term": db.get_meta("current_term"), "programs": distinct("program"), "modes": distinct("mode"),
            "model_ready": _bundle() is not None}


def _yes_no(value):
    if value in (True, 1):
        return "yes"
    if value in (False, 0):
        return "no"
    return str(value or "").strip()


def register_student(payload, role):
    """Add one student and their current-term figures, then score them right away (no full retrain)."""
    term = db.get_meta("current_term")
    if not term:
        raise ValueError("There is no student data loaded yet. Load the demo data or import a CSV in Settings first.")
    sid = str(payload.get("student_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,39}", sid):
        raise ValueError("Student ID: 2 to 40 characters using letters, numbers, dot, dash or underscore (no spaces).")

    row = {"student_id": sid, "term": term, "outcome": "",
           "program": str(payload.get("program") or "").strip()[:60], "mode": str(payload.get("mode") or "").strip()[:30],
           "gender": str(payload.get("gender") or "").strip()[:30], "first_generation": _yes_no(payload.get("first_generation")),
           "financial_aid": _yes_no(payload.get("financial_aid")), "entrance_score": payload.get("entrance_score")}
    for f in _REG_RECORD_FIELDS:
        row[f] = payload.get(f)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(row))
    w.writeheader()
    w.writerow({k: ("" if v is None else v) for k, v in row.items()})
    frame, bad, _ = importer.parse(buf.getvalue())      # the same checks a CSV import applies
    if bad:
        reason = bad[0]["reason"]
        for key, label in _REG_LABELS.items():
            if reason.startswith(key):
                reason = label + reason[len(key):]
                break
        raise ValueError(reason[0].upper() + reason[1:] + ".")
    rec = frame.iloc[0]

    students_cols = ["student_id", "program", "mode", "gender", "first_generation", "financial_aid", "entrance_score", "synced_at", "sync_age_days"]
    nn = lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else (v.item() if hasattr(v, "item") else v)
    student_row = (sid, rec["program"] or "Unspecified", rec["mode"] or "Unspecified", rec["gender"] or "Not provided",
                   nn(rec["first_generation"]), nn(rec["financial_aid"]), nn(rec["entrance_score"]), now_str(), 0.0)
    record_row = tuple(nn(v) for v in frame.reindex(columns=importer.RECORD_COLS).iloc[0])

    with bootstrap._lock:                                 # don't interleave with a retrain
        if db.one("SELECT 1 AS x FROM students WHERE lower(student_id)=lower(?)", (sid,)):
            raise ValueError(f"A student with the ID {sid} is already registered.")
        try:
            with db.connect() as con:
                con.execute(f"INSERT INTO students({','.join(students_cols)}) VALUES({','.join('?' * len(students_cols))})", student_row)
                cols = ",".join(importer.RECORD_COLS)
                con.execute(f"INSERT INTO records({cols}) VALUES({','.join('?' * len(importer.RECORD_COLS))})", record_row)
        except sqlite3.IntegrityError:
            raise ValueError(f"A student with the ID {sid} is already registered.")
        cache.clear()
        bundle = _bundle()
        scored = False
        if bundle is not None:
            preds = modeling.score_all(bundle, db.frame("SELECT * FROM records WHERE student_id=?", (sid,)),
                                       db.frame("SELECT * FROM students WHERE student_id=?", (sid,)))
            with db.connect() as con:
                con.executemany("INSERT OR REPLACE INTO predictions(student_id,term,probability,model_version,created_at,retrospective,contributions) "
                                "VALUES(?,?,?,?,?,?,?)", list(preds.itertuples(index=False, name=None)))
            scored = True
        cache.clear()
    audit(role, "register_student", sid, f"{student_row[1]} / {student_row[2]}")
    item = next((r for r in current_frame() if r["student_id"] == sid), None)
    return {"student_id": sid, "term": term, "scored": scored,
            "band": item["band"] if item else "Unavailable", "risk": item["risk"] if item else None,
            "status": item["status"] if item else None}
