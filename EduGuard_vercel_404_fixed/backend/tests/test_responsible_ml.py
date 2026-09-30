import numpy as np
import pandas as pd

from backend.utilities.common import DEFAULT_CONFIG
from backend.utilities.modeling import fairness_report
from backend.utilities import governance


def cfg():
    return {
        "risk": {"moderate_threshold": 0.10, "elevated_threshold": 0.25},
        "alerts": DEFAULT_CONFIG["alerts"],
        "fairness": DEFAULT_CONFIG["fairness"],
    }


def test_fairness_report_exposes_disparity_metrics():
    rows = []
    for i in range(70):
        group = "A" if i < 35 else "B"
        # Group A is intentionally overpredicted relative to its observed rate.
        observed = 1 if i < 10 else 0
        predicted = 0.45 if group == "A" else 0.05
        rows.append((group, observed, predicted))
    df = pd.DataFrame(rows, columns=["gender", "outcome_flag", "p"])
    df["outcome"] = np.where(df.outcome_flag == 1, "dropout", "continued")
    result = fairness_report(df, df.p.values, cfg())
    group = next(g for g in result["groups"] if g["group"] == "A")
    assert group["calibration_gap"] is not None
    assert group["fpr_gap"] is not None
    assert group["fnr_gap"] is not None
    assert group["review"] is True
    assert result["mitigation"]["applied"] is True


def test_small_groups_are_withheld():
    df = pd.DataFrame({
        "gender": ["Small"] * 5 + ["Large"] * 30,
        "outcome": ["continued"] * 35,
    })
    p = np.array([0.2] * 5 + [0.02] * 30)
    result = fairness_report(df, p, cfg())
    small = next(g for g in result["groups"] if g["group"] == "Small")
    assert small["sufficient"] is False
    assert small["mean_predicted"] is None
    assert "withheld" in small["notes"][0].lower()


def test_fairness_review_pauses_score_based_alerts():
    result = governance.decide(0.6, None, 0, [], [], cfg(), fairness_review=True)
    assert result["status"] == "watch"
    assert "fairness" in result["reasons"][0].lower()
