"""Synthetic, de-identified demo data.

One record per student per term. Every feature is computed only from weeks 1-8
of the term (the prediction cutoff); the outcome describes what happened AFTER
the term, so the demo data respects the "no future information" rule. The demo
also contains an intentional measurement-bias stress case so responsible-ML
checks have a reproducible disparity to detect.
"""
import numpy as np
import pandas as pd

TERMS = ["2023-1", "2023-2", "2024-1", "2024-2", "2025-1", "2025-2"]
PROGRAMS = {
    "Computer Science": 0.12,
    "Engineering": 0.22,
    "Business": 0.0,
    "Nursing": 0.05,
    "Education": -0.08,
    "Arts and Humanities": -0.05,
}
MODES = ["Campus", "Online", "Blended"]
WEEKS = 8


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def generate(n_students=1800, seed=42):
    rng = np.random.default_rng(seed)
    start_probs = np.array([0.30, 0.15, 0.20, 0.15, 0.12, 0.08])
    students, records, weekly = [], [], []
    last = len(TERMS) - 1

    for i in range(n_students):
        sid = f"STU-{10000 + i}"
        program = str(rng.choice(list(PROGRAMS)))
        mode = str(rng.choice(MODES, p=[0.5, 0.3, 0.2]))
        gender = str(rng.choice(["Female", "Male", "Non-binary"], p=[0.52, 0.455, 0.025]))
        first_gen = int(rng.random() < 0.38)
        aid = int(rng.random() < 0.45)
        z = rng.normal() + PROGRAMS[program] + 0.12 * first_gen + 0.10 * aid + (0.18 if mode == "Online" else 0.0)
        entrance = float(np.clip(rng.normal(72 - 2.5 * z, 9), 35, 100))
        r = rng.random()
        age = rng.uniform(0, 1.5) if r < 0.92 else rng.uniform(2, 6) if r < 0.97 else rng.uniform(9, 15)
        students.append((sid, program, mode, gender, first_gen, aid, round(entrance, 1), round(float(age), 2)))

        start = int(rng.choice(len(TERMS), p=start_probs))
        s_prev, prior_gpa, cum_failed, earned, attempted = 0.0, None, 0, 0.0, 0.0

        for t in range(start, len(TERMS)):
            term = TERMS[t]
            s = 0.55 * s_prev + rng.normal(0, 0.85)
            s_prev = s
            latent = 0.9 * z + 0.8 * s
            deter = max(0.0, s - 0.15)  # deterioration during the term

            load_p = [0.03, 0.30, 0.47, 0.20] if mode == "Campus" else [0.12, 0.33, 0.38, 0.17]
            load = int(rng.choice([9, 12, 15, 18], p=load_p))
            gpa = float(np.clip(3.05 - 0.40 * latent + rng.normal(0, 0.33), 0.3, 4.0))
            p_gpa = gpa if prior_gpa is None else prior_gpa
            credit_ratio = (earned / attempted) if attempted > 0 else np.nan

            w = np.arange(WEEKS)
            base_att = 93 - 8.5 * max(latent, -1.2) + rng.normal(0, 3.5)
            att = np.clip(base_att - deter * 2.6 * w + rng.normal(0, 4, WEEKS), 0, 100)
            lms = np.clip(np.round(5.0 - 0.75 * latent - deter * 0.28 * w + rng.normal(0, 0.9, WEEKS)), 0, 7)
            done = np.clip(0.92 - 0.075 * latent - deter * 0.045 * w + rng.normal(0, 0.10, WEEKS), 0, 1)
            due = rng.integers(1, 3, WEEKS)
            missed_w = rng.binomial(due, 1 - done)
            late_w = rng.binomial(due - missed_w, float(np.clip(0.06 + 0.05 * max(latent, 0), 0, 0.5)))

            fee_hold = int(rng.random() < _sigmoid(-2.5 + 0.55 * z + 0.35 * aid + 0.3 * deter))
            reg_delay = int(max(0, rng.normal(1.5 + 2.5 * max(z, 0) + 7 * fee_hold, 2.5)))
            advising = int(rng.poisson(max(0.15, 1.1 - 0.3 * z)))

            # Synthetic fairness stress case: the demo simulates a recording/measurement
            # problem affecting the Female group. The underlying outcome is unchanged,
            # but observed engagement signals are systematically lower, creating a
            # realistic proxy-driven overprediction pattern for the fairness audit to catch.
            if gender == "Female" and t == last - 1:
                att = np.clip(att - 18.0, 0, 100)
                lms = np.clip(lms - 1.25, 0, 7)
                done = np.clip(done - 0.16, 0, 1)

            outcome = ""
            if t < last:
                p_drop = _sigmoid(-3.65 + 0.80 * latent + 1.0 * deter + 0.55 * fee_hold + 0.10 * cum_failed)
                u = rng.random()
                p_transfer, p_leave = 0.02, 0.015 + 0.01 * fee_hold
                if u < p_drop:
                    outcome = "dropout"
                elif u < p_drop + p_transfer:
                    outcome = "transferred"
                elif u < p_drop + p_transfer + p_leave:
                    outcome = "approved_leave"
                else:
                    outcome = "continued"

            records.append((
                sid, term, t - start + 1, load,
                None if np.isnan(credit_ratio) else round(float(credit_ratio), 3),
                round(gpa, 2), round(p_gpa, 2), cum_failed,
                round(float(att.mean()), 1), round(float(att[4:].mean() - att[:4].mean()), 1),
                round(float(100 * done.mean()), 1), round(float(100 * (done[4:].mean() - done[:4].mean())), 1),
                int(missed_w.sum()), int(late_w.sum()),
                round(float(lms.mean()), 2), round(float(lms[4:].mean() - lms[:4].mean()), 2), int((lms == 0).sum()),
                advising, fee_hold, reg_delay, outcome,
            ))
            for k in range(WEEKS):
                weekly.append((sid, term, k + 1, round(float(att[k]), 1), float(lms[k]), round(float(done[k]), 3)))

            # Values that only become known at the end of the term feed the NEXT term.
            cum_failed += int(rng.poisson(np.exp(-1.5 + 0.65 * latent)))
            comp = float(np.clip(0.97 - 0.10 * max(latent, 0) - 0.12 * deter + rng.normal(0, 0.05), 0.3, 1.0))
            earned += round(load * comp)
            attempted += load
            prior_gpa = gpa
            if outcome and outcome != "continued":
                break

    students = pd.DataFrame(students, columns=[
        "student_id", "program", "mode", "gender", "first_generation", "financial_aid", "entrance_score", "sync_age_days"])
    records = pd.DataFrame(records, columns=[
        "student_id", "term", "term_number", "credit_load", "credit_ratio", "gpa", "prior_gpa", "failed_courses",
        "attendance_rate", "attendance_change", "assignment_completion", "assignment_change",
        "missed_submissions", "late_submissions", "lms_days", "lms_change", "inactive_weeks",
        "advising_visits", "fee_hold", "registration_delay_days", "outcome"])
    weekly = pd.DataFrame(weekly, columns=["student_id", "term", "week", "attendance", "lms_days", "assign_done"])
    return students, records, weekly
