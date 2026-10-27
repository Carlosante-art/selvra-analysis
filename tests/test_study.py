import re
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
import yaml

from selvra_analysis import study as st

EXAMPLE = Path(__file__).parents[1] / "studies" / "000-exempel-promenad" / "studie.yml"


@pytest.fixture
def spec() -> dict:
    return yaml.safe_load(EXAMPLE.read_text())


@pytest.fixture
def folder(tmp_path: Path, spec: dict, monkeypatch) -> Path:
    d = tmp_path / spec["id"]
    d.mkdir()
    (d / "studie.yml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    monkeypatch.setattr(st, "_git", lambda *a: "" if a[0] in {"status", "diff"} else "abc123")
    return d


def make_db(path: Path, schedule: pd.DataFrame | None, effect: float, seed: int = 0) -> Path:
    """Evening readings 19-22 every 5 min for 2025-04-01..2025-06-30; A days shifted by `effect`."""
    rng = np.random.default_rng(seed)
    a_days = set() if schedule is None else set(schedule.loc[schedule["condition"] == "A", "date"])
    rows = []
    day = date(2025, 4, 1)
    while day <= date(2025, 6, 30):
        level = 8.0 + rng.normal(0, 1.0) + (effect if day in a_days else 0.0)
        morning = 7.0 + rng.normal(0, 1.0)  # negative control 07-10: no effect
        for hour, value in ((19, level), (7, morning)):
            for k in range(36):
                t = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=5 * k)
                rows.append({"reading_at_local": t, "reading_date": day, "glucose_mmol": value,
                             "flag_compression_low": False, "flag_implausible_jump": False})
        day += timedelta(days=1)
    df = pd.DataFrame(rows)
    with duckdb.connect(str(path)) as con:
        con.execute("create schema intermediate; create schema raw")
        con.register("df", df)
        con.execute("create table intermediate.int_cgm_flagged as select * from df")
        con.execute("create table raw.source_files (kind varchar, sha256 varchar, bytes bigint, "
                    "n_rows bigint, loaded_at varchar)")
        con.execute("insert into raw.source_files values ('clarity', 'x', 1, 1, 'now')")
        con.execute("create table raw.clarity_events as select 'EGV' as event_type, "
                    "'SYNTHETIC' as source_device_id")
    return path


def test_example_is_valid(spec: dict) -> None:
    assert st.validate(spec) == []


def test_validation_names_problems_in_swedish(spec: dict) -> None:
    spec["design"]["par"] = 4
    del spec["motbevis"]
    spec["analys"]["minsta_relevanta_effekt"] = 0
    errors = "\n".join(st.validate(spec))
    assert "minst 6" in errors
    assert "motbevis" in errors
    assert "minsta_relevanta_effekt" in errors


@pytest.mark.parametrize(("ci", "smallest", "word"), [
    ((-3.0, -1.5), -1.0, "håller"),
    ((-0.8, 0.5), -1.0, "motbevisad"),
    ((-2.0, 0.2), -1.0, "obestämt"),
    ((1.5, 3.0), 1.0, "håller"),
    ((-0.5, 0.9), 1.0, "motbevisad"),
])
def test_decision_rule_respects_direction(ci, smallest, word) -> None:
    assert word in st.decide({"ci_low": ci[0], "ci_high": ci[1]}, smallest)


def test_lock_draws_schedule_once(folder: Path) -> None:
    s = st.load(folder / "studie.yml")
    rec = st.lock(s, seed=1)
    assert (folder / "schema.csv").exists()
    assert rec["schedule_end"] == "2025-05-24"
    with pytest.raises(st.StudyError, match="redan låst"):
        st.lock(s)


def test_lock_detects_changed_study(folder: Path) -> None:
    s = st.load(folder / "studie.yml")
    st.lock(s, seed=1)
    (folder / "studie.yml").write_text((folder / "studie.yml").read_text().replace("12", "14", 1))
    with pytest.raises(st.StudyError, match="ändrats efter låsningen"):
        st.check_lock(st.load(folder / "studie.yml"))


def test_status_is_blind(folder: Path, tmp_path: Path) -> None:
    s = st.load(folder / "studie.yml")
    st.lock(s, seed=1)
    sched = st.n1.read_schedule(folder / "schema.csv")
    db = make_db(tmp_path / "t.duckdb", sched, effect=-3.0)
    with duckdb.connect(str(db), read_only=True) as con:
        text = st.status(s, con, today=date(2025, 5, 1))
    assert "Kompletta par hittills" in text
    assert "Skattning" not in text
    assert "intervall" not in text.lower().replace("intervallet", "")


def test_run_refuses_while_running_then_finds_effect_once(folder: Path, tmp_path: Path) -> None:
    s = st.load(folder / "studie.yml")
    st.lock(s, seed=1)
    sched = st.n1.read_schedule(folder / "schema.csv")
    db = make_db(tmp_path / "t.duckdb", sched, effect=-3.0)
    with duckdb.connect(str(db), read_only=True) as con:
        with pytest.raises(st.StudyError, match="pågår"):
            st.run(s, con, today=date(2025, 5, 1))
        record, report = st.run(s, con, today=date(2025, 6, 1))
        assert "håller" in record["beslut"]
        assert record["result"]["ci_high"] < -1.0
        assert "Tesen håller" in report
        assert "Spårbarhet" in report
        with pytest.raises(st.StudyError, match="redan körd"):
            st.run(s, con, today=date(2025, 6, 2))


def test_no_effect_is_not_called_an_effect(folder: Path, tmp_path: Path) -> None:
    s = st.load(folder / "studie.yml")
    st.lock(s, seed=1)
    db = make_db(tmp_path / "t.duckdb", None, effect=0.0, seed=5)
    with duckdb.connect(str(db), read_only=True) as con:
        record, _ = st.run(s, con, today=date(2025, 6, 1))
    assert "håller" not in record["beslut"]


def test_observation_with_night_window_after_training(folder: Path, tmp_path: Path) -> None:
    """Nights after training are 1.5 mmol/L lower; the engine finds it in the 00-06 window."""
    spec = yaml.safe_load(EXAMPLE.read_text())
    spec["id"] = "obs-natt"
    spec["design"] = {"typ": "observation", "exponering": {"handelse": "traning", "dagar_efter": 1},
                      "period": [date(2025, 1, 1), date(2025, 12, 31)], "retrospektiv": True}
    spec["utfall"] = {"matt": "medel", "fonster": ["00:00", "06:00"]}
    spec["analys"] = {"metod": "blockbootstrap", "blocklangd": 7, "niva": 0.95, "minsta_relevanta_effekt": -0.5,
                      "minsta_underlag": {"exponerade": 30, "jamforelse": 30}}
    d = tmp_path / "obs-natt"
    d.mkdir()
    (d / "studie.yml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    assert st.validate(spec) == []
    s = st.load(d / "studie.yml")
    st.lock(s)

    rng = np.random.default_rng(3)
    days = pd.date_range("2025-01-01", "2025-12-31").date
    training = {day: bool(rng.random() < 0.3) for day in days}
    rows = []
    for day in days:
        after = training.get(day - timedelta(days=1), False)
        level = 8.0 + rng.normal(0, 0.8) - (1.5 if after else 0.0)
        morning = 7.0 + rng.normal(0, 0.8)  # negative control 07-10: no effect
        for start_min, count, value in ((0, 72, level), (7 * 60, 36, morning)):
            for k in range(count):
                t = datetime.combine(day, datetime.min.time()) + timedelta(minutes=start_min + 5 * k)
                rows.append({"reading_at_local": t, "reading_date": day, "glucose_mmol": value,
                             "flag_compression_low": False, "flag_implausible_jump": False})
    db = tmp_path / "o.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("create schema intermediate; create schema raw; create schema marts")
        con.register("df", pd.DataFrame(rows))
        con.execute("create table intermediate.int_cgm_flagged as select * from df")
        con.register("ctx", pd.DataFrame({"reading_date": days, "had_training": [training[x] for x in days],
                                          "is_valid_day": True}))
        con.execute("create table marts.mart_analysis_days as select * from ctx")
        con.execute("create table raw.source_files (kind varchar, sha256 varchar, bytes bigint, "
                    "n_rows bigint, loaded_at varchar)")
        con.execute("create table raw.clarity_events as select 'EGV' as event_type, 'X' as source_device_id")
    with duckdb.connect(str(db), read_only=True) as con:
        record, report = st.run(s, con, today=date(2026, 1, 15))
    assert "håller" in record["beslut"]
    assert -2.0 < record["result"]["estimate"] < -1.0
    assert "00:00–06:00" in report
    assert "Observationsdata visar samband" in report


def test_observation_refuses_below_minimum_without_spending_the_study(folder: Path, tmp_path: Path) -> None:
    spec = yaml.safe_load(EXAMPLE.read_text())
    spec["id"] = "obs-lite"
    spec["design"] = {"typ": "observation", "exponering": {"handelse": "traning", "dagar_efter": 1},
                      "period": [date(2026, 10, 1), date(2026, 10, 20)], "retrospektiv": True}
    spec["utfall"] = {"kolumn": "tir_pct"}
    spec["analys"] = {"metod": "blockbootstrap", "blocklangd": 7, "minsta_relevanta_effekt": 5.0,
                      "minsta_underlag": {"exponerade": 10, "jamforelse": 10}}
    bad = dict(spec, analys={**spec["analys"], "minsta_underlag": {"exponerade": 1, "jamforelse": 15}})
    assert any("minsta_underlag" in e for e in st.validate(bad))
    d = tmp_path / "obs-lite"
    d.mkdir()
    (d / "studie.yml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    s = st.load(d / "studie.yml")
    st.lock(s)
    days = pd.date_range("2026-10-01", "2026-10-20").date
    db = tmp_path / "l.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("create schema marts")
        con.register("ctx", pd.DataFrame({"reading_date": days, "tir_pct": 70.0, "is_valid_day": True,
                                          "had_training": [i == 5 for i in range(len(days))]}))
        con.execute("create table marts.mart_analysis_days as select * from ctx")
    with duckdb.connect(str(db), read_only=True) as con:
        with pytest.raises(st.StudyError, match="pågår"):
            st.run(s, con, today=date(2026, 10, 15))
        with pytest.raises(st.StudyError, match="för lite underlag: 1 exponerade"):
            st.run(s, con, today=date(2026, 10, 27))
    assert not (d / "korningar").exists()


def test_study_file_must_name_cent_items_and_a_negative_control(spec: dict) -> None:
    del spec["negativ_kontroll"]
    del spec["protokoll"]["overforing"]
    spec["protokoll"]["andringslogg"] = None
    errors = "\n".join(st.validate(spec))
    assert "negativ_kontroll" in errors
    assert "protokoll.overforing" in errors
    assert "CENT" in errors
    assert "protokoll.andringslogg" in errors


def test_report_shows_negative_control_and_protocol(folder: Path, tmp_path: Path) -> None:
    s = st.load(folder / "studie.yml")
    st.lock(s, seed=1)
    sched = st.n1.read_schedule(folder / "schema.csv")
    db = make_db(tmp_path / "t.duckdb", sched, effect=-3.0)
    with duckdb.connect(str(db), read_only=True) as con:
        record, report = st.run(s, con, today=date(2025, 6, 1))
    neg = record["negativ_kontroll"]
    assert neg["ci_low"] <= 0 <= neg["ci_high"], "no effect was put in the morning"
    assert "## Negativ kontroll" in report
    assert "som förväntat" in report
    assert "## Protokoll (CENT 2015)" in report
    assert "Ändringar efter låsning:** inga" in report


def test_every_computed_number_in_the_report_comes_from_the_run_record(folder: Path, tmp_path: Path) -> None:
    """Text-to-number traceability (Sandve et al. 2013, rule 9): signed numbers in the report are
    computed results; each must be the formatting of a value stored in the run record."""
    s = st.load(folder / "studie.yml")
    st.lock(s, seed=1)
    db = make_db(tmp_path / "t.duckdb", st.n1.read_schedule(folder / "schema.csv"), effect=-2.0)
    with duckdb.connect(str(db), read_only=True) as con:
        record, report = st.run(s, con, today=date(2025, 6, 1))
    recorded = {st._fmt(v) for part in ("result", "negativ_kontroll")
                for v in record[part].values() if isinstance(v, float)}
    recorded.add(st._fmt(s.spec["analys"]["minsta_relevanta_effekt"]))
    in_report = set(re.findall(r"[+-]\d+,\d{2}", report))
    assert in_report, "the report should contain computed numbers"
    assert in_report <= recorded, f"numbers not traceable to the record: {in_report - recorded}"


def test_run_refuses_until_data_reaches_past_the_last_day(folder: Path, tmp_path: Path) -> None:
    """An unattended run the morning after the end must not spend the study on a partial last day."""
    s = st.load(folder / "studie.yml")
    st.lock(s, seed=1)
    sched = st.n1.read_schedule(s.schedule_path)
    db = make_db(tmp_path / "db.duckdb", sched, effect=-1.0)
    end = sched["date"].max()
    with duckdb.connect(str(db)) as con:
        con.execute("delete from intermediate.int_cgm_flagged where reading_date > ?", [end])
    with duckdb.connect(str(db), read_only=True) as con, pytest.raises(st.StudyError, match="inte förbrukad"):
        st.run(s, con, today=end + timedelta(days=1))
    assert not (folder / "korningar").exists()
