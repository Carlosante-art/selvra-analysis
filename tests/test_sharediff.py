"""Share-diffen: parning per slot, ärliga kategorier, aggregat-rapport."""

import pandas as pd

from selvra_analysis import sharediff as sd


def _serie(tider: list[str], varden: list[float]) -> pd.Series:
    return pd.Series(varden, index=pd.to_datetime(tider), name="mmol")


def test_kategorier_och_diff() -> None:
    share = _serie(["2026-10-26 20:00", "2026-10-26 20:05", "2026-10-26 20:15"],
                   [8.0, 8.2, 9.0])
    clarity = _serie(["2026-10-26 20:00", "2026-10-26 20:05", "2026-10-26 20:10"],
                     [8.0, 8.3, 8.6])
    df = sd.diffa(share, clarity)
    assert df.loc["2026-10-26 20:00", "kategori"] == "bada"
    assert df.loc["2026-10-26 20:10", "kategori"] == "bara_clarity"  # share tappade
    assert df.loc["2026-10-26 20:15", "kategori"] == "bara_share"
    assert abs(df.loc["2026-10-26 20:05", "diff"] - (-0.1)) < 1e-9


def test_rapporten_ar_arlig_om_rokprov_och_facitlaget() -> None:
    share = _serie(["2026-10-26 20:00", "2026-10-26 20:05"], [8.0, 8.2])
    clarity = _serie(["2026-10-26 20:00", "2026-10-26 20:05", "2026-10-26 20:10"],
                     [8.0, 8.2, 8.5])
    text = sd.rapport(sd.diffa(share, clarity))
    assert "Rökprov" in text                      # < ett dygns överlapp sägs rakt ut
    assert "inte vilket som har rätt" in text     # ingen serie är facit
    assert "| parade slots (båda levererade) | 2 |" in text


def test_tapp_utanfor_overlappet_raknas_inte() -> None:
    # Clarity-exportens slut är inte ett rör-tapp: allt efter sista gemensamma
    # slot ligger utanför jämförelsen.
    share = _serie(["2026-10-26 20:00", "2026-10-26 21:00", "2026-10-26 22:00"],
                   [8.0, 9.0, 10.0])
    clarity = _serie(["2026-10-26 19:00", "2026-10-26 20:00"], [7.5, 8.0])
    text = sd.rapport(sd.diffa(share, clarity))
    assert "| slots bara i Clarity (realtidsröret tappade) | 0 |" in text
    assert "| slots bara i Share | 0 |" in text


def test_inget_overlapp_sags_rakt_ut() -> None:
    share = _serie(["2026-10-28 10:00"], [8.0])
    clarity = _serie(["2026-10-20 10:00"], [7.0])
    assert "Inget överlapp" in sd.rapport(sd.diffa(share, clarity))
