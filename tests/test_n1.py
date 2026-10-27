from datetime import date

import numpy as np
import pandas as pd
import pytest

from selvra_analysis.n1 import (
    eligible_dates,
    make_schedule,
    period_outcomes,
    period_sd,
    power,
    randomisation_test,
)


def periods_from(diffs, base=10.0):
    rows = []
    for i, d in enumerate(diffs, 1):
        rows += [{"pair": i, "condition": "A", "order": "AB", "value": base + d},
                 {"pair": i, "condition": "B", "order": "AB", "value": base}]
    return pd.DataFrame(rows)


def test_schedule_has_one_of_each_per_pair() -> None:
    s = make_schedule(date(2026, 11, 2), n_pairs=10, period_days=3, washout_days=1, seed=4)
    assert len(s) == 60
    assert s["date"].is_unique
    per_pair = s.drop_duplicates(["pair", "period"]).groupby("pair")["condition"].apply(sorted)
    assert all(c == ["A", "B"] for c in per_pair)
    assert s["washout"].sum() == 20
    assert make_schedule(date(2026, 11, 2), 10, 3, 1, seed=4).equals(s)


def test_exact_p_value_known_case() -> None:
    # All 5 pairs favour A, all with distinct sizes: only the observed signs and their
    # mirror image are as extreme, so p = 2 / 32.
    r = randomisation_test(periods_from([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert r.exact
    assert r.p_value == pytest.approx(2 / 32)
    assert r.min_attainable_p == pytest.approx(2 / 32)
    assert r.estimate == pytest.approx(3.0)


def test_too_few_pairs_gives_no_interval() -> None:
    r = randomisation_test(periods_from([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert r.ci_low == -np.inf
    assert r.ci_high == np.inf


def test_interval_contains_true_effect_and_excludes_zero() -> None:
    rng = np.random.default_rng(1)
    r = randomisation_test(periods_from(5.0 + rng.normal(0, 2, 12)))
    assert r.ci_low < 5.0 < r.ci_high
    assert r.ci_low > 0
    assert r.p_value < 0.05


def test_incomplete_pairs_are_dropped_and_counted() -> None:
    p = periods_from([1.0, 2.0, 3.0])
    p.loc[(p["pair"] == 2) & (p["condition"] == "A"), "value"] = np.nan
    r = randomisation_test(p)
    assert (r.n_pairs, r.n_pairs_dropped) == (2, 1)


def test_type_one_error_is_at_most_alpha() -> None:
    rng = np.random.default_rng(3)
    rejections = sum(
        randomisation_test(periods_from(rng.normal(0, 1, 8)), seed=i).p_value <= 0.05
        for i in range(400))
    assert rejections / 400 <= 0.07


def test_period_outcomes_skip_washout_and_invalid_days() -> None:
    s = make_schedule(date(2026, 1, 1), n_pairs=1, period_days=3, washout_days=1, seed=0)
    daily = pd.DataFrame({
        "reading_date": pd.date_range("2026-01-01", periods=6).date,
        "tir": [0.0, 60.0, 80.0, 0.0, 40.0, 50.0],
        "is_valid_day": [True, True, True, True, True, False],
    })
    out = period_outcomes(s, daily, "tir").set_index("period")
    assert out.loc[1, "value"] == 70.0
    assert out.loc[1, "n_days"] == 2
    assert out.loc[2, "value"] == 40.0
    assert out.loc[2, "n_days"] == 1


def test_power_grows_with_pairs() -> None:
    assert power(6, effect=1.0, sd=1.0, n_sim=300) < power(14, effect=1.0, sd=1.0, n_sim=300)


def test_period_sd_uses_complete_blocks() -> None:
    daily = pd.DataFrame({
        "reading_date": pd.date_range("2026-01-01", periods=6),
        "x": [1.0, 3.0, 5.0, 7.0, 100.0, 0.0],
        "is_valid_day": [True, True, True, True, True, False],
    })
    # blocks of 2: means 2, 6; the third block has an invalid day
    assert period_sd(daily, "x", 2) == pytest.approx(np.std([2.0, 6.0], ddof=1))


def test_eligible_days_restrict_randomisation_to_days_off() -> None:
    days = eligible_dates(date(2026, 11, 2), 8, weekdays=["lordag", "sondag"])
    assert [d.weekday() for d in days] == [5, 6] * 4
    s = make_schedule(date(2026, 11, 2), 4, 1, 0, seed=3, days=days)
    assert set(s["date"]) == set(days)
    per_pair = s.groupby("pair")["condition"].apply(sorted)
    assert all(c == ["A", "B"] for c in per_pair)
    with pytest.raises(ValueError, match="one-day periods"):
        make_schedule(date(2026, 11, 2), 4, 2, 1, seed=3, days=days)
