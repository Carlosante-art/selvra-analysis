"""The scanner must not turn 'work day vs day off' into a hypothesis about steps."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from selvra_analysis import scanner


def days(n: int = 70, steps_follow_daytype: bool = True, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        d = date(2026, 6, 1) + timedelta(days=i)
        weekday = d.weekday() < 5
        high = weekday if steps_follow_daytype else bool(rng.random() < 0.5)
        # Work days are worse here for reasons that have nothing to do with steps.
        rows.append({"reading_date": d, "is_valid_day": True, "high_steps": high,
                     "tir_pct": (60 if weekday else 80) + rng.normal(0, 3)})
    df = pd.DataFrame(rows)
    for col in ("had_training", "had_stress", "is_ill", "had_alcohol", "is_travelling", "had_medication_change"):
        df[col] = False
    return df


def test_steps_that_follow_the_day_type_are_not_reported_as_an_effect() -> None:
    patterns = scanner._event_korrelationer(days())
    steps = [p for p in patterns if "höga steg" in p.beskrivning.lower()]
    assert len(steps) == 1
    assert "följer dagstypen" in steps[0].beskrivning
    assert steps[0].vikt == 1


def test_within_daytype_difference_removes_the_day_type() -> None:
    df = days(steps_follow_daytype=False)
    naive = df.loc[df["high_steps"], "tir_pct"].mean() - df.loc[~df["high_steps"], "tir_pct"].mean()
    within = scanner._within_daytype_diff(df[df["is_valid_day"]], "high_steps")
    assert abs(within) < 3, "steps have no effect inside a day type"
    assert abs(within) <= abs(naive) + 3
