"""Statistical validity gates: do the methods do what the reports say they do?

Each test follows ADEMP (Morris, White & Crowther, Stat Med 2019): a data-generating
mechanism, an estimand, a method, and a performance measure checked against its Monte
Carlo standard error (MCSE). The number of simulated data sets comes from the environment:
small in every CI run, large in the weekly calibration workflow.

    CALIBRATION_SIMS=2000 uv run pytest tests/test_calibration.py
"""

import math
import os
from datetime import date

import numpy as np
import pandas as pd

from selvra_analysis.n1 import make_schedule, period_outcomes, power, randomisation_test
from selvra_analysis.stats import EMPIRICAL_COVERAGE, block_bootstrap_difference

SIMS = int(os.environ.get("CALIBRATION_SIMS", "200"))
ALPHA = 0.05


def mcse(p: float, n: int) -> float:
    return math.sqrt(p * (1 - p) / n)


def ar1(n: int, phi: float, rng: np.random.Generator) -> np.ndarray:
    x = np.zeros(n)
    eps = rng.normal(0, 1, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    return x


def n1_experiment(rng: np.random.Generator, seed: int, effect: float, phi: float = 0.5):
    """12 pairs of 2-day periods with 1 washout day; daily outcome AR(1); A days shifted by effect."""
    sched = make_schedule(date(2026, 1, 5), 12, 2, 1, seed=seed)
    y = ar1(len(sched), phi, rng) + np.where(sched["condition"] == "A", effect, 0.0)
    daily = pd.DataFrame({"reading_date": sched["date"], "y": y, "is_valid_day": True})
    return randomisation_test(period_outcomes(sched, daily, "y"), seed=seed)


def test_n1_type_one_error_under_autocorrelation() -> None:
    """D: AR(1) days, no effect. E: A - B = 0. M: paired randomisation test.
    P: rejection rate at 5 % must be 5 % within 2 MCSE (the test is exact by design;
    this checks the implementation)."""
    rng = np.random.default_rng(11)
    rate = np.mean([n1_experiment(rng, s, 0.0).p_value <= ALPHA for s in range(SIMS)])
    assert abs(rate - ALPHA) <= 2 * mcse(ALPHA, SIMS) + 1e-9, rate


def test_n1_interval_covers_an_injected_effect() -> None:
    """D: AR(1) days plus a known effect of -1.0 on A days. E: -1.0. M: interval by test
    inversion. P: coverage at least 95 % minus 2 MCSE."""
    rng = np.random.default_rng(12)
    hits = [(r.ci_low <= -1.0 <= r.ci_high) for r in
            (n1_experiment(rng, s, -1.0) for s in range(SIMS))]
    assert np.mean(hits) >= 0.95 - 2 * mcse(0.95, SIMS), np.mean(hits)


def test_power_function_matches_simulated_experiments() -> None:
    """The planning tool must agree with experiments run through the real analysis.
    D: independent period means, effect 1 SD per period. P: power within 3 MCSE."""
    rng = np.random.default_rng(13)
    planned = power(12, effect=1.0, sd=1.0, n_sim=SIMS, seed=1)
    rejected = []
    for _ in range(SIMS):
        diffs = rng.normal(1.0, 1.0, 12) - rng.normal(0.0, 1.0, 12)
        periods = pd.DataFrame([{"pair": i, "condition": c, "order": "AB", "value": v}
                                for i, d in enumerate(diffs, 1) for c, v in (("A", d), ("B", 0.0))])
        rejected.append(randomisation_test(periods).p_value <= ALPHA)
    assert abs(np.mean(rejected) - planned) <= 3 * mcse(planned, SIMS) * math.sqrt(2), (np.mean(rejected), planned)


def test_block_bootstrap_coverage_is_what_reports_say() -> None:
    """D: 365 AR(1) days (phi 0.7), no effect, 7-day exposure episodes. E: 0. M: block
    bootstrap, 7-day blocks. P: coverage must equal the recorded EMPIRICAL_COVERAGE within
    2 MCSE. If the method improves or worsens, the recorded figure (and the report text)
    must be updated: the gate fails in both directions."""
    rng = np.random.default_rng(42)
    covered = 0
    for t in range(SIMS):
        y = ar1(365, 0.7, rng)
        e = np.zeros(365, dtype=bool)
        for s in rng.choice(np.arange(0, 358), size=12, replace=False):
            e[s : s + 7] = True
        est = block_bootstrap_difference(y, e, block_length=7, seed=t, n_boot=600)
        covered += est.ci_low <= 0 <= est.ci_high
    recorded = EMPIRICAL_COVERAGE[7]
    assert abs(covered / SIMS - recorded) <= 2 * mcse(recorded, SIMS) + 0.01, covered / SIMS
