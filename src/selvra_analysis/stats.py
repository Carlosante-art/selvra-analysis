"""Effect sizes with honest uncertainty for one person's daily data.

Days from one person are not independent: a bad week is followed by more bad days.
An ordinary bootstrap or t-test treats every day as new information and gives
confidence intervals that are too narrow. The circular block bootstrap (Politis &
Romano 1992) resamples whole runs of consecutive days instead, so the dependence
between neighbouring days is kept in every resample.

The block length is a pre-registered analysis choice: long enough to cover how far
the dependence reaches (7 days keeps a whole week together), short enough to leave
many blocks. Report the result at the pre-registered length, and as a sensitivity
check at half and double it.

Typical use:

    days = daily_series(mart, "reading_date", ["tbr_pct", "after_streak"])
    est = block_bootstrap_difference(days["tbr_pct"], days["after_streak"],
                                     block_length=7, seed=1)
    est.estimate, est.ci_low, est.ci_high
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Estimate:
    """Difference in means, exposed days minus comparison days, with a percentile interval."""

    estimate: float
    ci_low: float
    ci_high: float
    level: float
    n_exposed: int
    n_comparison: int
    block_length: int
    n_boot: int
    n_boot_valid: int
    seed: int
    method: str = "circular block bootstrap, percentile interval"

    def as_dict(self) -> dict:
        return asdict(self)


def daily_series(df: pd.DataFrame, date_column: str, columns: list[str]) -> pd.DataFrame:
    """One row per calendar day from first to last, missing days as NaN.

    Blocks must be runs of calendar days. If missing days were simply left out,
    a block could join days weeks apart and the dependence structure would be wrong.
    """
    s = df[[date_column, *columns]].copy()
    s[date_column] = pd.to_datetime(s[date_column])
    if s[date_column].duplicated().any():
        raise ValueError(f"{date_column} has duplicate days")
    s = s.set_index(date_column).sort_index()
    full = pd.date_range(s.index.min(), s.index.max(), freq="D", name=date_column)
    return s.reindex(full)


def circular_block_indices(n: int, block_length: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Row indices for `n_boot` resamples of length n, built from circular blocks."""
    if not 1 <= block_length <= n:
        raise ValueError(f"block_length must be between 1 and {n}")
    n_blocks = -(-n // block_length)
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    offsets = np.arange(block_length)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    return idx.reshape(n_boot, -1)[:, :n]


def _difference(outcome: np.ndarray, exposed: np.ndarray, comparison: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_e = np.nansum(np.where(exposed, outcome, 0.0), axis=-1) / exposed.sum(axis=-1)
        mean_c = np.nansum(np.where(comparison, outcome, 0.0), axis=-1) / comparison.sum(axis=-1)
    return mean_e - mean_c


def block_bootstrap_difference(
    outcome,
    exposed,
    *,
    block_length: int,
    seed: int,
    n_boot: int = 10_000,
    level: float = 0.95,
) -> Estimate:
    """Mean outcome on exposed days minus mean on comparison days.

    outcome: one value per calendar day, NaN for days without a valid value.
    exposed: one value per calendar day: True (exposed), False (comparison), or
             NaN/None for days in neither group (for example contaminated by another episode).
    """
    y = np.asarray(outcome, dtype=float)
    g = pd.Series(exposed, dtype="object").to_numpy()
    if y.shape != g.shape:
        raise ValueError("outcome and exposed must have one value per day")
    usable = ~np.isnan(y)
    is_exposed = usable & np.array([v is True or v == 1 for v in g])
    is_comparison = usable & np.array([v is False or (v == 0 and v is not True) for v in g])
    if is_exposed.sum() == 0 or is_comparison.sum() == 0:
        raise ValueError("need at least one exposed and one comparison day with a valid outcome")

    y0 = np.where(usable, y, 0.0)
    point = float(_difference(y0, is_exposed, is_comparison))

    rng = np.random.default_rng(seed)
    idx = circular_block_indices(len(y), block_length, n_boot, rng)
    boot = _difference(y0[idx], is_exposed[idx], is_comparison[idx])
    valid = boot[np.isfinite(boot)]
    alpha = (1 - level) / 2
    low, high = (np.quantile(valid, [alpha, 1 - alpha]) if len(valid) else (np.nan, np.nan))
    return Estimate(
        estimate=point,
        ci_low=float(low),
        ci_high=float(high),
        level=level,
        n_exposed=int(is_exposed.sum()),
        n_comparison=int(is_comparison.sum()),
        block_length=block_length,
        n_boot=n_boot,
        n_boot_valid=len(valid),
        seed=seed,
    )
