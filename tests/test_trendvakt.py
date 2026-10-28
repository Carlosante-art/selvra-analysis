"""Trendvakten: beskriver när ett mönster tänt, tiger under vilotiden."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from selvra_analysis import scanner, trendvakt

IDAG = date(2026, 10, 28)


def _stigande_vilopuls(monkeypatch) -> None:
    df = pd.DataFrame({
        "reading_date": [IDAG - timedelta(days=i) for i in range(30, 0, -1)],
        "hr_lowest_bpm": [44.0 + i * 0.35 for i in range(30)],   # ~+2,5 slag/vecka
        "total_sleep_seconds": [25200] * 30,
    })
    monkeypatch.setattr(scanner, "_load", lambda p: df)


def test_tand_signal_blir_en_rad(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _stigande_vilopuls(monkeypatch)
    rad = trendvakt.trendrad("x", tmp_path / "db.duckdb", IDAG)
    assert rad is not None
    assert rad.startswith("Selvra ser: Vilopulsen rör sig uppåt")
    assert "borde" not in rad.lower()


def test_samma_trend_ar_inte_en_ny_nyhet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _stigande_vilopuls(monkeypatch)
    assert trendvakt.trendrad("x", tmp_path / "db.duckdb", IDAG) is not None
    # Dag 2–6: samma mönster, tystnad. Dag 8: får låta igen.
    assert trendvakt.trendrad("x", tmp_path / "db.duckdb", IDAG + timedelta(days=2)) is None
    assert trendvakt.trendrad("x", tmp_path / "db.duckdb", IDAG + timedelta(days=8)) is not None


def test_inget_monster_ingen_rad_ingen_markor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame({
        "reading_date": [IDAG - timedelta(days=i) for i in range(30, 0, -1)],
        "hr_lowest_bpm": [44.0] * 30,
        "total_sleep_seconds": [25200] * 30,
    })
    monkeypatch.setattr(scanner, "_load", lambda p: df)
    assert trendvakt.trendrad("x", tmp_path / "db.duckdb", IDAG) is None
    assert not (tmp_path / "data" / "personer" / "x" / "trendvakt.json").exists()


def test_forhandsgranskning_forbrukar_inte_vilotiden(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _stigande_vilopuls(monkeypatch)
    assert trendvakt.trendrad("x", tmp_path / "db.duckdb", IDAG, skriv=False) is not None
    assert not (tmp_path / "data" / "personer" / "x" / "trendvakt.json").exists()
    assert trendvakt.trendrad("x", tmp_path / "db.duckdb", IDAG) is not None
