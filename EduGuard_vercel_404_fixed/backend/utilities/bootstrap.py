"""First-run preparation: demo data, model training, scoring.

Run directly (`python -m backend.utilities.bootstrap`) from setup.bat, or let the
API call ensure_ready() on start-up.
"""
import random
import sys
import threading
from datetime import datetime, timedelta

import pandas as pd

from . import accounts, cache, datagen, db, explain, modeling
from .common import MODEL_DIR, get_logger, load_config, now_str

log = get_logger("bootstrap")
_lock = threading.Lock()


def _stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def retrain(source=None, log_fn=None):
    """Train on everything in the database, then score every record."""
    log_fn = log_fn or log.info
    with _lock:
        students = db.frame("SELECT * FROM students")
        records = db.frame("SELECT * FROM records")
        if records.empty:
            raise ValueError("There is no data to train on yet.")
        source = source or db.get_meta("source", "demo")
        bundle = modeling.train(records, students, source=source, log=log_fn)
        preds = modeling.score_all(bundle, records, students)
        db.write_frame("predictions", preds, replace=True)
        db.set_meta("current_term", bundle["current_term"])
        db.set_meta("model_version", bundle["version"])
        db.set_meta("source", source)
        cache.clear()
        return bundle


def reevaluate():
    with _lock:
        bundle = modeling.load_bundle()
        if bundle is None:
            return None
        students = db.frame("SELECT * FROM students")
        records = db.frame("SELECT * FROM records")
        modeling.reevaluate(bundle, records, students)
        cache.clear()
        return bundle


def refresh_demo_freshness():
    """Demo data should look as if it was synced recently, whenever the app starts."""
    now = datetime.now()
    rows = db.query("SELECT student_id, sync_age_days FROM students")
    with db.connect() as con:
        con.executemany("UPDATE students SET synced_at=? WHERE student_id=?",
                        [(_stamp(now - timedelta(days=float(r["sync_age_days"] or 0))), r["student_id"]) for r in rows])
    cache.clear()


def seed_interventions(seed=7):
    """Add a believable recent support history so the tracking screens are not empty."""
    rng = random.Random(seed)
    cfg = load_config()
    term = db.get_meta("current_term")
    preds = db.frame("SELECT student_id, probability, contributions FROM predictions WHERE term=?", (term,))
    cand = preds[preds["probability"] >= cfg["risk"]["moderate_threshold"]]
    now = datetime.now()
    rows = []
    for r in cand.itertuples():
        if rng.random() > 0.42:
            continue
        exp = explain.explain(r.contributions)
        cats = explain.categories_from(exp)
        itype = explain.SUPPORT[cats[0]]["intervention"] if cats else "Private advisor check-in"
        days = rng.choice([1, 2, 3, 5, 9, 12, 16, 21, 26])
        created = now - timedelta(days=days, hours=rng.randint(0, 6))
        pool = (["Planned", "Contacted", "Student responded"] if days <= 3 else
                ["Contacted", "Student responded", "Support in progress", "Completed", "Closed - no response"])
        status = rng.choice(pool)
        outcome = {"Completed": "Student used the support and is back on track.",
                   "Closed - no response": "Three attempts made; no reply.",
                   "Support in progress": "Student accepted support; follow-up scheduled."}.get(status, "")
        updated = created + timedelta(days=min(days, rng.randint(0, 4)))
        rows.append((r.student_id, _stamp(created), _stamp(updated), itype, rng.choice(explain.CHANNELS), status, outcome,
                     "Seeded demo case.", "advisor"))
    with db.connect() as con:
        con.executemany("INSERT INTO interventions(student_id,created_at,updated_at,type,channel,status,outcome,note,author) "
                        "VALUES(?,?,?,?,?,?,?,?,?)", rows)
    log.info("Seeded %d demo interventions", len(rows))


def load_demo(log_fn=None):
    log_fn = log_fn or log.info
    cfg = load_config()["demo"]
    log_fn(f"Generating synthetic student records ({cfg['students']} students)...")
    students, records, weekly = datagen.generate(cfg["students"], cfg["seed"])
    now = datetime.now()
    students["synced_at"] = [_stamp(now - timedelta(days=float(a))) for a in students["sync_age_days"]]
    db.init()
    db.clear_all()
    db.write_frame("students", students)
    db.write_frame("records", records)
    db.write_frame("weekly", weekly)
    db.set_meta("source", "demo")
    log_fn("Training and calibrating the risk model...")
    retrain("demo", log_fn)
    seed_interventions()
    log_fn("Demo data ready.")


def ensure_ready():
    db.init()
    if accounts.seed_default_advisor():
        log.info("Default academic advisor login created")
    n = db.one("SELECT COUNT(*) AS c FROM students")["c"]
    if n == 0:
        load_demo()
        return
    has_model = (MODEL_DIR / "risk_model.joblib").exists()
    has_preds = (db.one("SELECT COUNT(*) AS c FROM predictions") or {"c": 0})["c"] > 0
    if not (has_model and has_preds):
        try:
            retrain()
        except ValueError as exc:  # imported data may not be trainable yet
            log.warning("Model not trained: %s", exc)
    if db.get_meta("source") == "demo":
        refresh_demo_freshness()


if __name__ == "__main__":
    fresh = "--reset" in sys.argv
    db.init()
    if fresh:
        load_demo(print)
    else:
        ensure_ready()
    print("Bootstrap complete.")
