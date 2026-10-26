from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis.report import period_metrics, render


def db_with(tmp_path: Path, values: list[float], day: date) -> duckdb.DuckDBPyConnection:
    rows = [{"reading_at_local": datetime.combine(day, datetime.min.time()) + timedelta(minutes=5 * i),
             "reading_date": day, "glucose_mmol": v, "flag_compression_low": i == 0,
             "flag_implausible_jump": False} for i, v in enumerate(values)]
    con = duckdb.connect(str(tmp_path / "r.duckdb"))
    con.execute("create schema intermediate; create schema marts")
    con.register("df", pd.DataFrame(rows))
    con.execute("create table intermediate.int_cgm_flagged as select * from df")
    con.execute("create table marts.fct_glucose_daily as select ?::date as reading_date, 288 as n_expected", [day])
    con.execute("create table intermediate.int_glycaemic_events (event_type varchar, start_date date, "
                "contains_artefact boolean)")
    con.execute("insert into intermediate.int_glycaemic_events values ('hypo_level1', ?, true)", [day])
    return con


def test_metrics_are_pooled_over_readings(tmp_path: Path) -> None:
    # 288 readings: 72 at 3.5 (the first flagged as artefact), 216 at 7.0
    values = [3.5] * 72 + [7.0] * 216
    con = db_with(tmp_path, values, date(2026, 1, 1))
    m = period_metrics(con, date(2026, 1, 1), date(2026, 1, 1))
    assert m["tbr_pct"] == 25.0 and m["tir_pct"] == 75.0
    assert abs(m["tbr_pct_clean"] - 100 * 71 / 287) < 1e-9
    assert m["coverage_pct"] == 100.0
    assert (m["n_hypo_level1"], m["n_hypo_level1_clean"]) == (1, 0)
    assert abs(m["gmi_pct"] - (3.31 + 0.02392 * (sum(values) / 288) * 18.016)) < 1e-9


def test_report_flags_short_periods_and_marks_targets(tmp_path: Path) -> None:
    con = db_with(tmp_path, [7.0] * 288, date(2026, 1, 1))
    m = period_metrics(con, date(2026, 1, 1), date(2026, 1, 1))
    text = render(m, {}, date(2026, 1, 1), date(2026, 1, 1), {"fingerprint": "abc", "synthetic": False})
    assert "Under konsensuskravet" in text
    assert "| Tid i målområdet 3,9–10,0 | 100,0 % |" in text and "| ja |" in text
