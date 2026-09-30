"""Validated CSV import of student-term records.

One row per student per term. Rows with an `outcome` are history used for
training; rows without one (the latest term) are the students to score.
Invalid rows are quarantined with a reason, never silently dropped or guessed.
"""
import io
import re

import numpy as np
import pandas as pd

from . import bootstrap, cache, db
from .common import MODEL_DIR, now_str
from .modeling import KNOWN_OUTCOMES

REQUIRED = ["student_id", "term", "gpa", "attendance_rate", "assignment_completion"]
RANGES = {
    "term_number": (1, 30), "credit_load": (0, 40), "credit_ratio": (0, 1), "gpa": (0, 4.0), "prior_gpa": (0, 4.0),
    "failed_courses": (0, 100), "attendance_rate": (0, 100), "attendance_change": (-100, 100),
    "assignment_completion": (0, 100), "assignment_change": (-100, 100), "missed_submissions": (0, 200),
    "late_submissions": (0, 200), "lms_days": (0, 7), "lms_change": (-7, 7), "inactive_weeks": (0, 52),
    "advising_visits": (0, 100), "fee_hold": (0, 1), "registration_delay_days": (0, 365), "entrance_score": (0, 100),
}
RECORD_COLS = ["student_id", "term", "term_number", "credit_load", "credit_ratio", "gpa", "prior_gpa", "failed_courses",
               "attendance_rate", "attendance_change", "assignment_completion", "assignment_change",
               "missed_submissions", "late_submissions", "lms_days", "lms_change", "inactive_weeks",
               "advising_visits", "fee_hold", "registration_delay_days", "outcome"]
TEMPLATE_COLUMNS = REQUIRED + [c for c in RECORD_COLS if c not in REQUIRED and c != "prior_gpa"] + [
    "program", "mode", "gender", "first_generation", "financial_aid", "entrance_score", "data_synced_at"]
TEMPLATE_COLUMNS = list(dict.fromkeys(TEMPLATE_COLUMNS))
MAX_ROWS = 200_000
TERM_RE = re.compile(r"^\d{4}-\d$")
YES = {"1", "yes", "y", "true", "t"}
NO = {"0", "no", "n", "false", "f"}


def template_csv():
    rows = [
        dict(student_id="S-0001", term="2024-1", gpa=3.1, attendance_rate=91, assignment_completion=88, attendance_change=-2,
             assignment_change=-4, missed_submissions=1, late_submissions=1, lms_days=5, lms_change=-0.3, inactive_weeks=0,
             advising_visits=1, fee_hold=0, registration_delay_days=0, failed_courses=0, credit_ratio=0.96, term_number=2,
             outcome="continued", program="Business", mode="Campus"),
        dict(student_id="S-0001", term="2024-2", gpa=3.0, attendance_rate=84, assignment_completion=79, attendance_change=-9,
             assignment_change=-14, missed_submissions=3, late_submissions=2, lms_days=4, lms_change=-1.1, inactive_weeks=1,
             advising_visits=0, fee_hold=1, registration_delay_days=6, failed_courses=0, credit_ratio=0.95, term_number=3,
             outcome="", program="Business", mode="Campus"),
    ]
    return pd.DataFrame(rows).reindex(columns=TEMPLATE_COLUMNS).to_csv(index=False)


def _flag(value):
    v = str(value).strip().lower()
    return 1 if v in YES else 0 if v in NO else None


def parse(csv_text: str):
    try:
        df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    except Exception as exc:  # malformed CSV
        raise ValueError(f"Could not read the file as CSV: {exc}")
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    if len(df) == 0:
        raise ValueError("The file has no data rows.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"The file has more than {MAX_ROWS:,} rows. Split it and import in parts.")

    good, bad = [], []
    for i, row in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        sid, term = row["student_id"].strip(), row["term"].strip()
        problem = None
        if not sid:
            problem = "student_id is empty"
        elif not TERM_RE.match(term):
            problem = f"term '{term}' must look like 2025-1"
        out = row.get("outcome", "").strip().lower()
        if not problem and out and out not in KNOWN_OUTCOMES:
            problem = f"outcome '{out}' is not one of {', '.join(sorted(KNOWN_OUTCOMES))}"
        clean = {"student_id": sid, "term": term, "outcome": out}
        if not problem:
            for col, (lo, hi) in RANGES.items():
                raw = str(row.get(col, "")).strip()
                if raw == "":
                    clean[col] = np.nan
                    if col in REQUIRED:
                        problem = f"{col} is empty"
                        break
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    problem = f"{col} '{raw}' is not a number"
                    break
                if not lo <= val <= hi:
                    problem = f"{col} {val:g} is outside {lo:g} to {hi:g}"
                    break
                clean[col] = val
        if problem:
            bad.append({"row": i, "student_id": sid, "reason": problem})
            continue
        for col in ("program", "mode", "gender"):
            clean[col] = row.get(col, "").strip()
        clean["first_generation"] = _flag(row.get("first_generation", ""))
        clean["financial_aid"] = _flag(row.get("financial_aid", ""))
        clean["synced"] = row.get("data_synced_at", "").strip()
        good.append(clean)

    frame = pd.DataFrame(good)
    dupes = 0
    if not frame.empty:
        before = len(frame)
        frame = frame.drop_duplicates(["student_id", "term"], keep="last")
        dupes = before - len(frame)
        frame = frame.sort_values(["student_id", "term"]).reset_index(drop=True)
        if "term_number" not in frame or frame["term_number"].isna().all():
            frame["term_number"] = frame.groupby("student_id").cumcount() + 1
        frame["term_number"] = frame["term_number"].fillna(frame.groupby("student_id").cumcount() + 1)
        if frame["prior_gpa"].isna().all():
            frame["prior_gpa"] = frame.groupby("student_id")["gpa"].shift(1)
        frame["prior_gpa"] = frame["prior_gpa"].fillna(frame["gpa"])
    return frame, bad, dupes


def apply(csv_text: str, mode="append"):
    frame, bad, dupes = parse(csv_text)
    report = {"rows": len(frame) + len(bad) + dupes, "accepted": int(len(frame)), "quarantined": len(bad),
              "duplicates": int(dupes), "errors": bad[:25], "trained": False, "message": ""}
    if frame.empty:
        report["message"] = "No valid rows were found, so nothing was imported."
        return report

    students = (frame.sort_values("term").groupby("student_id")
                .agg({"program": "last", "mode": "last", "gender": "last", "first_generation": "last",
                      "financial_aid": "last", "entrance_score": "last", "synced": "last"}).reset_index())
    for col, default in (("program", "Unspecified"), ("mode", "Unspecified"), ("gender", "Not provided")):
        students[col] = students[col].replace("", default).fillna(default)
    students["synced_at"] = students["synced"].apply(lambda v: v if re.match(r"^\d{4}-\d\d-\d\d", v or "") else now_str())
    students["sync_age_days"] = 0.0
    students = students.drop(columns=["synced"])
    records = frame.reindex(columns=RECORD_COLS)

    if mode == "replace":
        db.clear_all()
        for f in ("risk_model.joblib", "model_card.json"):
            (MODEL_DIR / f).unlink(missing_ok=True)
    with db.connect() as con:
        con.executemany(
            "INSERT OR REPLACE INTO students(student_id,program,mode,gender,first_generation,financial_aid,entrance_score,synced_at,sync_age_days) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            [tuple(None if (isinstance(v, float) and np.isnan(v)) else v for v in r) for r in students[
                ["student_id", "program", "mode", "gender", "first_generation", "financial_aid", "entrance_score",
                 "synced_at", "sync_age_days"]].itertuples(index=False, name=None)])
        cols = ",".join(RECORD_COLS)
        con.executemany(
            f"INSERT OR REPLACE INTO records({cols}) VALUES({','.join('?' * len(RECORD_COLS))})",
            [tuple(None if (isinstance(v, float) and np.isnan(v)) else v for v in r)
             for r in records.itertuples(index=False, name=None)])
    db.set_meta("source", "imported")
    db.set_meta("current_term", str(records["term"].max()))
    cache.clear()

    report["students"] = int(len(students))
    report["terms"] = sorted(records["term"].unique().tolist())
    report["with_outcomes"] = int((records["outcome"] != "").sum())
    try:
        bootstrap.retrain(source="imported")
        report["trained"] = True
        report["message"] = "Data imported. The model was retrained and every student was re-scored."
    except ValueError as exc:
        report["message"] = f"Data imported, but the model could not be trained yet: {exc}"
    return report
