"""The engine-level test uses the real machinery; this checks the plumbing on known truth."""

import numpy as np
import pandas as pd

from selvra_analysis.motortest import _dom, _exponering, _mojliga_datum


def _serie(seed: int = 3, dagar: int = 90) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=dagar)
    # AR(1)-nätter: samma slags beroende som verklig CGM-data
    x = np.zeros(dagar)
    for i in range(1, dagar):
        x[i] = 0.6 * x[i - 1] + rng.normal(0, 0.8)
    return pd.Series(7.0 + x, index=idx)


def test_exposure_lands_on_the_night_after() -> None:
    s = _serie()
    d = [pd.Timestamp("2026-02-01")]
    e = _exponering(s, d)
    assert e[pd.Timestamp("2026-02-02")] is True
    assert e[pd.Timestamp("2026-02-01")] is False


def test_a_planted_large_effect_is_detected() -> None:
    s = _serie()
    rng = np.random.default_rng(7)
    datum = list(rng.choice(_mojliga_datum(s), size=15, replace=False))
    planterad = s.copy()
    for d in datum:
        planterad[d + pd.Timedelta(days=1)] -= 3.0
    dom, est = _dom(planterad, datum, seed=5)
    assert dom == "tesen håller"
    assert est < -2.0


def test_shuffled_exposures_rarely_claim_the_thesis_holds() -> None:
    """Under nollan är "motbevisad" ett korrekt friande; det falska fyndet är "håller"."""
    s = _serie()
    rng = np.random.default_rng(11)
    falska = 0
    for i in range(25):
        datum = list(rng.choice(_mojliga_datum(s), size=10, replace=False))
        dom, _ = _dom(s, datum, seed=100 + i)
        falska += dom == "tesen håller"
    assert falska <= 2, f"{falska}/25 falska fynd under nollan"
