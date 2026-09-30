"""Training, calibration, evaluation, fairness audit and explanations.

Design rules taken from the research:
* temporal split (train on earlier terms, calibrate on the next, test on the latest known term)
* class-weighted training, then probability calibration on an isolated term
* transparent baseline (logistic regression) compared with tree ensembles and a rule baseline
* metrics that survive class imbalance: PR-AUC, recall, precision, Brier, top-k
* sensitive attributes are excluded from the model and used only for the fairness audit
"""
import json
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .common import MODEL_DIR, load_config, now_str

# name: (label, privacy tier, group)
FEATURES = {
    "term_number": ("Term of study", 1, "Administrative"),
    "entrance_score": ("Entrance score", 2, "Academic"),
    "gpa": ("Current GPA", 2, "Academic"),
    "gpa_change": ("GPA change vs last term", 2, "Academic"),
    "failed_courses": ("Failed courses to date", 2, "Academic"),
    "credit_ratio": ("Share of attempted credits earned", 2, "Academic"),
    "attendance_rate": ("Attendance rate", 2, "Engagement"),
    "attendance_change": ("Attendance change (last 4 weeks)", 2, "Engagement"),
    "assignment_completion": ("Assignment completion", 2, "Engagement"),
    "assignment_change": ("Assignment completion change (last 4 weeks)", 2, "Engagement"),
    "lms_days": ("Active days per week on learning platform", 2, "Engagement"),
    "lms_change": ("Platform activity change (last 4 weeks)", 2, "Engagement"),
    "advising_visits": ("Advising visits this term", 2, "Administrative"),
    "fee_hold": ("Account hold open", 2, "Administrative"),
    "registration_delay_days": ("Registration delay (days)", 2, "Administrative"),
}
FEATURE_COLUMNS = list(FEATURES)

# Expected direction of association (+1: a higher value goes with higher risk, -1: lower risk, 0: no expectation).
# Only used to decide which signals advisors are shown. If a fitted coefficient contradicts expectation it is a
# statistical overlap artefact, so it is hidden instead of being shown as a misleading "protective" factor.
DIRECTION = {
    "term_number": 0, "entrance_score": -1, "gpa": -1, "gpa_change": -1, "failed_courses": 1, "credit_ratio": -1,
    "attendance_rate": -1, "attendance_change": -1, "assignment_completion": -1, "assignment_change": -1,
    "lms_days": -1, "lms_change": -1, "advising_visits": -1, "fee_hold": 1, "registration_delay_days": 1,
}
KNOWN_OUTCOMES = {"continued", "dropout", "transferred", "approved_leave", "graduated"}
AUDIT_ATTRIBUTES = ["gender", "first_generation", "financial_aid", "mode", "program"]
GROUP_LABELS = {
    "first_generation": {1: "First-generation", 0: "Not first-generation"},
    "financial_aid": {1: "Receives financial aid", 0: "No financial aid"},
}
ATTRIBUTE_TITLES = {
    "gender": "Gender", "first_generation": "First-generation status", "financial_aid": "Financial aid",
    "mode": "Study mode", "program": "Program",
}

LIMITATIONS = [
    "Scores are estimates of association, not causes. A low attendance signal may reflect health, work, transport or access barriers.",
    "Trained on one institution's history (or synthetic demo data). It must be validated locally before real use.",
    "Transfers, approved leave and graduation are not counted as dropout; records with unknown outcomes are excluded from training.",
    "Learning-platform activity is not the same as learning: students may study offline or share devices.",
    "Small groups produce unstable error rates; results for groups under the minimum size are not reported.",
]
PROHIBITED_USES = [
    "Denying admission, aid, grades or services", "Disciplinary or punitive action",
    "Lowering expectations of a student", "Automated messages to students without human review",
    "Diagnosing why a student may leave",
]
PERMITTED_USES = [
    "Prioritising supportive outreach by trained advisors", "Spotting course-level engagement patterns",
    "Evaluating whether support programmes help students continue",
]


class Platt:
    """Sigmoid calibration fitted on an isolated validation term."""

    def fit(self, scores, y):
        self.lr = LogisticRegression(C=1e4, max_iter=1000)
        self.lr.fit(np.asarray(scores).reshape(-1, 1), y)
        return self

    def predict(self, scores):
        return self.lr.predict_proba(np.asarray(scores).reshape(-1, 1))[:, 1]

    @property
    def slope(self):
        return float(self.lr.coef_[0][0])


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _raw(kind, model, X):
    if kind == "logistic":
        return model.decision_function(X)
    return _logit(model.predict_proba(X)[:, 1])


def prepare(records: pd.DataFrame, students: pd.DataFrame) -> pd.DataFrame:
    df = records.merge(students, on="student_id", how="left")
    df["gpa_change"] = df["gpa"] - df["prior_gpa"]
    return df


def _confusion_metrics(y, pred):
    y = np.asarray(y).astype(bool)
    pred = np.asarray(pred).astype(bool)
    tp, fp = int((pred & y).sum()), int((pred & ~y).sum())
    fn, tn = int((~pred & y).sum()), int((~pred & ~y).sum())
    div = lambda a, b: (a / b) if b else None
    return {
        "flagged": int(pred.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "recall": div(tp, tp + fn), "precision": div(tp, tp + fp),
        "fpr": div(fp, fp + tn), "fnr": div(fn, fn + tp),
    }


def evaluate(y, p, cfg):
    y = np.asarray(y).astype(int)
    out = {
        "n": int(len(y)), "positives": int(y.sum()), "base_rate": float(y.mean()),
        "pr_auc": float(average_precision_score(y, p)), "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
    }
    for name in ("moderate", "elevated"):
        thr = cfg["risk"][f"{name}_threshold"]
        m = _confusion_metrics(y, p >= thr)
        m["threshold"] = thr
        out[name] = m
    k = max(1, int(round(0.10 * len(y))))
    top = np.argsort(-np.asarray(p))[:k]
    hits = int(y[top].sum())
    out["top10"] = {
        "k": k, "recall": hits / max(1, int(y.sum())), "precision": hits / k,
        "lift": (hits / k) / max(1e-9, float(y.mean())),
    }
    return out


def calibration_bins(y, p, bins=5):
    frame = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    frame["bin"] = pd.qcut(frame["p"], bins, duplicates="drop")
    grouped = frame.groupby("bin", observed=True).agg(predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size"))
    return [{"predicted": float(r.predicted), "observed": float(r.observed), "n": int(r.n)} for r in grouped.itertuples()]


def rule_baseline(df):
    """A simple advising rule used as the comparison point."""
    flag = (df["gpa"] < 2.0) | (df["attendance_rate"] < 70) | (df["missed_submissions"] >= 4) | (df["fee_hold"] == 1)
    return flag.values


def fairness_report(df, p, cfg):
    """Audit subgroup error and calibration gaps without using protected attributes as model features."""
    thr = cfg["risk"]["moderate_threshold"]
    fair = cfg.get("fairness", {})
    min_n = fair.get("min_group_size", 30)
    cal_thr = float(fair.get("calibration_gap_threshold", 0.05))
    fpr_thr = float(fair.get("fpr_gap_threshold", 0.03))
    fnr_thr = float(fair.get("fnr_gap_threshold", 0.10))
    y = (df["outcome"] == "dropout").astype(int).values
    p = np.asarray(p, dtype=float)
    overall = _confusion_metrics(y, p >= thr)
    overall["mean_predicted"] = float(p.mean()) if len(p) else None
    overall["observed_rate"] = float(y.mean()) if len(y) else None
    overall["flag_rate"] = float((p >= thr).mean()) if len(p) else None
    overall["calibration_gap"] = (
        None if overall["mean_predicted"] is None or overall["observed_rate"] is None
        else float(overall["mean_predicted"] - overall["observed_rate"])
    )
    rows = []

    def gap(value, baseline):
        return None if value is None or baseline is None else float(value - baseline)

    def ratio(value, baseline):
        if value is None or baseline in (None, 0):
            return None
        return float(value / baseline)

    for attr in AUDIT_ATTRIBUTES:
        if attr not in df.columns:
            continue
        for value, idx in df.groupby(attr, dropna=True).indices.items():
            yy, pp = y[idx], p[idx]
            label = GROUP_LABELS.get(attr, {}).get(value, str(value))
            m = _confusion_metrics(yy, pp >= thr)
            sufficient = len(idx) >= min_n
            few_pos = int(yy.sum()) < 10
            row = {
                "attribute": attr, "attribute_title": ATTRIBUTE_TITLES[attr], "group": label, "n": int(len(idx)),
                "positives": int(yy.sum()), "sufficient": bool(sufficient),
                "observed_rate": float(yy.mean()) if sufficient else None,
                "mean_predicted": float(pp.mean()) if sufficient else None,
                "flag_rate": float((pp >= thr).mean()) if sufficient else None,
                "recall": m["recall"] if sufficient and not few_pos else None,
                "precision": m["precision"] if sufficient else None,
                "fpr": m["fpr"] if sufficient else None,
                "fnr": m["fnr"] if sufficient and not few_pos else None,
                "calibration_gap": gap(float(pp.mean()), float(yy.mean())) if sufficient else None,
                "calibration_disparity": (
                    float((pp.mean() - yy.mean()) - overall["calibration_gap"])
                    if sufficient and overall["calibration_gap"] is not None else None
                ),
                "flag_rate_gap": gap(float((pp >= thr).mean()), overall["flag_rate"]) if sufficient else None,
                "recall_gap": gap(m["recall"], overall["recall"]) if sufficient and not few_pos else None,
                "precision_gap": gap(m["precision"], overall["precision"]) if sufficient else None,
                "fpr_gap": gap(m["fpr"], overall["fpr"]) if sufficient else None,
                "fnr_gap": gap(m["fnr"], overall["fnr"]) if sufficient and not few_pos else None,
                "flag_rate_ratio": ratio(float((pp >= thr).mean()), overall["flag_rate"]) if sufficient else None,
                "overprediction": False, "review": False, "notes": [],
            }
            if not sufficient:
                row["notes"].append(f"Fewer than {min_n} students: group metrics withheld")
            else:
                if row["fnr_gap"] is not None and row["fnr_gap"] > fnr_thr:
                    row["notes"].append(f"FNR is {row['fnr_gap']:+.1%} vs overall")
                if row["fpr_gap"] is not None and row["fpr_gap"] > fpr_thr:
                    row["notes"].append(f"FPR is {row['fpr_gap']:+.1%} vs overall")
                if row["calibration_gap"] is not None and row["calibration_gap"] > cal_thr:
                    row["overprediction"] = True
                    row["notes"].append(f"Overprediction gap is {row['calibration_gap']:+.1%}")
                if few_pos:
                    row["notes"].append("Few dropout cases: recall is not reported")
                elif int(yy.sum()) < 30:
                    row["notes"].append("Small number of dropout cases: interpret recall with caution")
                row["review"] = bool(row["overprediction"] or
                                     (row["fpr_gap"] is not None and row["fpr_gap"] > fpr_thr) or
                                     (row["fnr_gap"] is not None and row["fnr_gap"] > fnr_thr))
            rows.append(row)

    sufficient_rows = [r for r in rows if r["sufficient"]]
    worst = max(sufficient_rows, key=lambda r: r["calibration_gap"] if r["calibration_gap"] is not None else -999, default=None)
    review = [r for r in sufficient_rows if r["review"]]
    return {
        "threshold": thr,
        "minimum_group_size": min_n,
        "overall": overall,
        "groups": rows,
        "status": "review" if review else "clear",
        "disparities": {
            "groups_in_review": len(review),
            "largest_calibration_gap": (
                {
                    "attribute": worst["attribute"], "attribute_title": worst["attribute_title"], "group": worst["group"],
                    "gap": worst["calibration_gap"], "disparity": worst["calibration_disparity"],
                    "mean_predicted": worst["mean_predicted"], "observed_rate": worst["observed_rate"],
                } if worst and worst["calibration_gap"] is not None else None
            ),
        },
        "mitigation": {
            "status": "human_review_gate" if review else "monitor",
            "applied": bool(review),
            "title": "Human-review mitigation" if review else "Fairness monitoring",
            "action": (
                "The model score remains demographic-blind. Because a material subgroup disparity was detected, automated risk-based outreach must not be treated as a final decision; reviewers must verify current course evidence before action. The next model version should be re-calibrated and re-tested on the affected subgroup before deployment."
                if review else
                "Protected attributes are excluded from prediction and checked separately. Continue monitoring calibration and error-rate gaps on each new model version."
            ),
            "why": "Demographic attributes are audit-only and are not used as individual prediction features.",
        },
        "metric_definitions": {
            "calibration_gap": "Group mean predicted risk minus overall observed dropout rate; positive values indicate overprediction relative to the observed outcome rate.",
            "flag_rate_gap": "Group share at or above the moderate threshold minus the overall share.",
            "fpr_gap": "False-positive rate difference from the overall population.",
            "fnr_gap": "False-negative rate difference from the overall population.",
            "recall": "Share of actual dropout cases detected at the moderate threshold.",
        },
    }


def train(records: pd.DataFrame, students: pd.DataFrame, source="demo", log=print):
    cfg = load_config()
    df = prepare(records, students)
    terms_all = sorted(df["term"].unique())
    current_term = terms_all[-1]
    known = df[df["outcome"].isin(KNOWN_OUTCOMES)].copy()
    known_terms = sorted(known["term"].unique())
    if len(known_terms) < 3:
        raise ValueError("At least 3 terms with known outcomes are needed for a time-based train/calibrate/test split.")
    test_term, cal_term, train_terms = known_terms[-1], known_terms[-2], known_terms[:-2]

    tr = known[known["term"].isin(train_terms)]
    ca = known[known["term"] == cal_term]
    te = known[known["term"] == test_term]
    y = lambda d: (d["outcome"] == "dropout").astype(int).values
    for name, part in (("training", tr), ("calibration", ca), ("test", te)):
        if y(part).sum() < 5 or (1 - y(part)).sum() < 5:
            raise ValueError(f"The {name} period has too few dropout or continuing cases to train responsibly.")

    log(f"Split: train {train_terms} | calibrate {cal_term} | test {test_term} | score {current_term}")
    seed = 42
    models = {
        "logistic": Pipeline([
            ("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()),
            ("clf", LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000))]),
        "forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("clf", RandomForestClassifier(n_estimators=300, min_samples_leaf=12, max_depth=8,
                                           class_weight="balanced_subsample", n_jobs=-1, random_state=seed))]),
        "boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                   l2_regularization=1.0, class_weight="balanced", random_state=seed),
    }
    calibrators, metrics, test_probs = {}, {}, {}
    for kind, model in models.items():
        model.fit(tr[FEATURE_COLUMNS], y(tr))
        calibrators[kind] = Platt().fit(_raw(kind, model, ca[FEATURE_COLUMNS]), y(ca))
        p_test = calibrators[kind].predict(_raw(kind, model, te[FEATURE_COLUMNS]))
        test_probs[kind] = p_test
        metrics[kind] = evaluate(y(te), p_test, cfg)
        log(f"  {kind:9s} PR-AUC {metrics[kind]['pr_auc']:.3f}  ROC-AUC {metrics[kind]['roc_auc']:.3f}  Brier {metrics[kind]['brier']:.3f}")

    rule = _confusion_metrics(y(te), rule_baseline(te))
    metrics["rule_baseline"] = rule
    serve = "logistic"
    p_serve = test_probs[serve]

    lr = models["logistic"].named_steps["clf"]
    importance = sorted(
        ({"feature": f, "label": FEATURES[f][0], "coefficient": float(c),
          "expected": bool(DIRECTION[f] != 0 and np.sign(c) == DIRECTION[f])} for f, c in zip(FEATURE_COLUMNS, lr.coef_[0])),
        key=lambda d: -abs(d["coefficient"]))

    train_stats = {f: [float(tr[f].mean()), float(tr[f].std() or 1.0)] for f in FEATURE_COLUMNS}
    version = datetime.now().strftime("v%Y.%m.%d-%H%M")
    gap = metrics["boosting"]["pr_auc"] - metrics[serve]["pr_auc"]
    card = {
        "name": "EduGuard student support risk model", "version": version, "trained_at": now_str(),
        "data_source": source,
        "purpose": "Estimate the chance that a student will withdraw after the current term so advisors can prioritise supportive outreach.",
        "target": "Withdrawal after the term (true dropout). Transfers, approved leave and graduation are not counted; unknown outcomes are excluded.",
        "horizon": "Next academic term",
        "prediction_cutoff": "Week 8 of the term. Only information available by then is used.",
        "split": {"train_terms": train_terms, "calibration_term": cal_term, "test_term": test_term, "scored_term": current_term},
        "serving_model": "Calibrated logistic regression (transparent, explainable per student)",
        "challengers": ["Random forest", "Gradient boosting"],
        "imbalance_handling": "Class-weighted training; probabilities re-calibrated on a separate term; thresholds set by advisor capacity.",
        "features": [{"name": f, "label": v[0], "tier": v[1], "group": v[2]} for f, v in FEATURES.items()],
        "excluded_from_model": ["Gender", "First-generation status", "Financial aid status", "Program", "Study mode"],
        "excluded_note": "These attributes are never used for prediction. They are used only to audit fairness.",
        "fairness_mitigation_note": (
            "Fairness mitigation is implemented as a human-review gate when a subgroup shows a material calibration or error-rate disparity. Protected attributes are not used to change an individual's score; instead, automated outreach is held for evidence review and the next model version must be re-calibrated and re-tested before deployment."
        ),
        "metrics": metrics, "calibration": calibration_bins(y(te), p_serve),
        "importance": importance,
        "comparison_note": (
            f"Gradient boosting scores {gap:+.3f} PR-AUC vs the serving model. "
            + ("The gap is small, so the transparent model is kept." if gap < 0.05
               else "The gap is notable; review before deciding whether to switch.")),
        "limitations": LIMITATIONS, "prohibited_uses": PROHIBITED_USES, "permitted_uses": PERMITTED_USES,
        "retraining": "Retrain every term and after any change to policies, the learning platform or the student system.",
    }
    fairness = fairness_report(te, p_serve, cfg)

    bundle = {"version": version, "features": FEATURE_COLUMNS, "models": models, "calibrators": calibrators,
              "serve": serve, "train_stats": train_stats, "card": card, "fairness": fairness,
              "current_term": current_term}
    save_bundle(bundle)
    return bundle


def save_bundle(bundle):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_DIR / "risk_model.joblib")
    (MODEL_DIR / "model_card.json").write_text(
        json.dumps({"card": bundle["card"], "fairness": bundle["fairness"]}, indent=2), encoding="utf-8")


def reevaluate(bundle, records: pd.DataFrame, students: pd.DataFrame):
    """Recompute test metrics and the fairness audit after thresholds change (no retraining)."""
    cfg = load_config()
    df = prepare(records, students)
    known = df[df["outcome"].isin(KNOWN_OUTCOMES)]
    te = known[known["term"] == bundle["card"]["split"]["test_term"]]
    yy = (te["outcome"] == "dropout").astype(int).values
    for kind, model in bundle["models"].items():
        p = bundle["calibrators"][kind].predict(_raw(kind, model, te[bundle["features"]]))
        bundle["card"]["metrics"][kind] = evaluate(yy, p, cfg)
        if kind == bundle["serve"]:
            bundle["fairness"] = fairness_report(te, p, cfg)
    save_bundle(bundle)
    return bundle


def load_bundle():
    path = MODEL_DIR / "risk_model.joblib"
    return joblib.load(path) if path.exists() else None


def score_all(bundle, records: pd.DataFrame, students: pd.DataFrame):
    """Score every record. Returns (predictions frame, contributions for the scored term)."""
    df = prepare(records, students)
    X = df[bundle["features"]]
    serve = bundle["serve"]
    raw = _raw(serve, bundle["models"][serve], X)
    prob = bundle["calibrators"][serve].predict(raw)
    current = bundle["current_term"]

    pipe = bundle["models"]["logistic"]
    Xs = pipe.named_steps["scaler"].transform(pipe.named_steps["imputer"].transform(X))
    contrib = Xs * pipe.named_steps["clf"].coef_[0] * bundle["calibrators"]["logistic"].slope
    missing = X.isna().values
    coef = pipe.named_steps["clf"].coef_[0]
    expected = [bool(DIRECTION[f] != 0 and np.sign(coef[j]) == DIRECTION[f]) for j, f in enumerate(bundle["features"])]

    rows = []
    for i, r in enumerate(df.itertuples(index=False)):
        is_current = r.term == current
        blob = None
        if is_current:
            items = [{"feature": f, "contribution": float(contrib[i, j]), "value": None if missing[i, j] else float(X.iloc[i, j]),
                      "imputed": bool(missing[i, j]), "expected": expected[j]} for j, f in enumerate(bundle["features"])]
            items.sort(key=lambda d: -abs(d["contribution"]))
            blob = json.dumps(items[:8])
        rows.append((r.student_id, r.term, float(prob[i]), bundle["version"], now_str(), 0 if is_current else 1, blob))
    preds = pd.DataFrame(rows, columns=["student_id", "term", "probability", "model_version", "created_at",
                                         "retrospective", "contributions"])
    return preds


def drift_report(bundle, current_df: pd.DataFrame):
    out = []
    for f, (mean, std) in bundle["train_stats"].items():
        if f != "term_number" and f in current_df and current_df[f].notna().any():
            shift = (float(current_df[f].mean()) - mean) / (std or 1.0)
            out.append({"feature": f, "label": FEATURES[f][0], "shift": float(shift), "flag": abs(shift) > 0.5})
    return sorted(out, key=lambda d: -abs(d["shift"]))
