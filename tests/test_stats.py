import numpy as np
import pandas as pd
import pytest

from selvra_analysis.stats import (
    block_bootstrap_difference,
    circular_block_indices,
    daily_series,
)


def ar1(n: int, phi: float, rng: np.random.Generator) -> np.ndarray:
    x = np.zeros(n)
    eps = rng.normal(0, 1, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    return x


def episodic_exposure(n: int, rng: np.random.Generator) -> np.ndarray:
    """Exposure in runs of days, like the days after a high streak."""
    exposed = np.zeros(n, dtype=bool)
    for start in rng.choice(np.arange(0, n - 7), size=n // 30, replace=False):
        exposed[start : start + 7] = True
    return exposed


def test_blocks_are_consecutive_and_wrap() -> None:
    idx = circular_block_indices(10, 4, 50, np.random.default_rng(0))
    assert idx.shape == (50, 10)
    for row in idx:
        for b in range(0, 8, 4):
            block = row[b : b + 4]
            assert all((block[k + 1] - block[k]) % 10 == 1 for k in range(3))


def test_same_seed_same_result() -> None:
    rng = np.random.default_rng(1)
    y, e = rng.normal(size=200), rng.random(200) < 0.3
    a = block_bootstrap_difference(y, e, block_length=7, seed=5, n_boot=2000)
    b = block_bootstrap_difference(y, e, block_length=7, seed=5, n_boot=2000)
    assert a == b


def test_recovers_known_difference() -> None:
    rng = np.random.default_rng(2)
    n = 2000
    e = episodic_exposure(n, rng)
    y = rng.normal(0, 1, n) + 1.0 * e
    est = block_bootstrap_difference(y, e, block_length=7, seed=3, n_boot=4000)
    assert est.ci_low < 1.0 < est.ci_high
    assert est.ci_low > 0


def test_missing_and_excluded_days_are_left_out() -> None:
    y = np.array([1.0, 1.0, np.nan, 5.0, 5.0, 100.0])
    e = [False, False, True, True, True, None]
    est = block_bootstrap_difference(y, e, block_length=1, seed=0, n_boot=100)
    assert est.estimate == 4.0
    assert (est.n_exposed, est.n_comparison) == (2, 2)


def test_needs_both_groups() -> None:
    with pytest.raises(ValueError, match="at least one exposed"):
        block_bootstrap_difference([1.0, 2.0], [True, True], block_length=1, seed=0)


def test_daily_series_fills_missing_days() -> None:
    df = pd.DataFrame({"d": ["2025-01-01", "2025-01-04"], "x": [1.0, 2.0]})
    s = daily_series(df, "d", ["x"])
    assert len(s) == 4
    assert s["x"].isna().sum() == 2


def test_block_bootstrap_keeps_coverage_where_iid_bootstrap_fails() -> None:
    """Why blocks: on autocorrelated days with no true effect, the 95 % interval
    should contain zero about 95 % of the time. Resampling single days does not."""
    rng = np.random.default_rng(42)
    covered = {1: 0, 14: 0}
    trials = 150
    for t in range(trials):
        y = ar1(365, 0.7, rng)
        e = episodic_exposure(365, rng)
        for b in covered:
            est = block_bootstrap_difference(y, e, block_length=b, seed=t, n_boot=800)
            covered[b] += est.ci_low <= 0 <= est.ci_high
    coverage = {b: c / trials for b, c in covered.items()}
    assert coverage[14] >= 0.85
    assert coverage[1] < coverage[14] - 0.1
