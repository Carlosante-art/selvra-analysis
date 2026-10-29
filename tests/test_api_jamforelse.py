"""API-jämförelsens diffning: facit mot källor, ärliga luckor, dagsgränser."""

from datetime import date, datetime

import pandas as pd

from selvra_analysis import api_jamforelse as aj
from selvra_analysis import rorlogg

FACIT = pd.DataFrame([
    {"reading_date": date(2026, 10, 30), "steps": 8000, "total_sleep_seconds": 25200,
     "deep_sleep_seconds": 5400, "rem_sleep_seconds": 4800, "hr_lowest_bpm": 46, "hrv_avg_ms": 70.0},
])


def test_diff_raknas_falt_for_falt() -> None:
    kalla = pd.DataFrame([{"reading_date": date(2026, 10, 30), "steps": 7850,
                           "total_sleep_seconds": 25200, "deep_sleep_seconds": 5100,
                           "rem_sleep_seconds": 4800, "hr_lowest_bpm": 47, "hrv_avg_ms": None}])
    diff = aj.diffa(FACIT, {"api": kalla})
    steg = diff[diff["falt"] == "steps"].iloc[0]
    assert steg["api_diff"] == -150
    hrv = diff[diff["falt"] == "hrv_avg_ms"].iloc[0]
    assert pd.isna(hrv["api_diff"])  # saknat värde är en lucka (NaN), aldrig en nolla


def test_saknad_dag_hos_kallan_blir_streck() -> None:
    kalla = pd.DataFrame([{"reading_date": date(2026, 10, 29), "steps": 1}])
    diff = aj.diffa(FACIT, {"api": kalla})
    assert pd.isna(diff[diff["falt"] == "steps"].iloc[0]["api"])


def test_rapporten_ar_bara_aggregat() -> None:
    kalla = FACIT.copy()
    text = aj.rapport(aj.diffa(FACIT, {"api": kalla}), ["not: test"], ["api"])
    assert "FIT (facit)" in text
    assert "rådatan bor i data/fit/" in text
    assert "not: test" in text


def test_natt_tillhor_uppvakningsdagen() -> None:
    # sleep_level 23:30 → nästa dag; 06:30 → samma dag: natten tillhör
    # uppvakningsdagen. Ändras regeln i _ta_somn måste detta test ändras medvetet.
    a = aj._Ack()
    aj._ta_somn(a, {"sleep_level": 3}, datetime(2026, 10, 29, 23, 30))
    aj._ta_somn(a, {"sleep_level": 4}, datetime(2026, 10, 30, 6, 30))
    assert set(a.somn) == {date(2026, 10, 30)}
    assert a.somn[date(2026, 10, 30)]["total_sleep_seconds"] == 120


def test_rorloggen_beskriver_roret_aldrig_manniskan(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rad = rorlogg.logga("garminconnect", "x", bibliotek="0.2.0", enhet="Venu 3",
                        firmware="12.18", dagar=10, rader=9, falt=["steps", "hrv_avg_ms"])
    assert rad["falt"] == ["hrv_avg_ms", "steps"]
    text = (tmp_path / "data" / "rorlogg.jsonl").read_text()
    assert "Venu 3" in text
    for forbjudet in ("mmol", "bpm_varde", "sleep_seconds_varde"):
        assert forbjudet not in text  # form, aldrig mätvärden
