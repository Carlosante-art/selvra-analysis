"""The design review catches, from data, the mistakes the first 10,000-steps draft made."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest
import yaml

from selvra_analysis import granska
from selvra_analysis import study as st
from selvra_analysis.ingest_oura import parse

DRAFT = Path(__file__).parents[1] / "studies" / "002-10000-steg" / "studie.yml"
TODAY = date(2025, 7, 1)


def make_db(path: Path, synthetic: bool = False, seed: int = 0) -> Path:
    """April-June 2025. Glucose 07-24 with day-to-day noise; steps like a person who walks
    11,000 on work days (Mon-Fri) and 3,500 on days off."""
    rng = np.random.default_rng(seed)
    path.unlink(missing_ok=True)
    readings, days = [], []
    day = date(2025, 4, 1)
    while day <= date(2025, 6, 30):
        level = 8.0 + rng.normal(0, 1.0)
        night = 7.0 + rng.normal(0, 1.0)
        for hour, value, n in ((7, level, 204), (0, night, 72)):
            for k in range(n):
                t = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=5 * k)
                readings.append({"reading_at_local": t, "reading_date": day, "glucose_mmol": value,
                                 "flag_compression_low": False, "flag_implausible_jump": False})
        steps = 11000 + rng.integers(-800, 800) if day.weekday() < 5 else 3500 + rng.integers(-800, 800)
        days.append({"reading_date": day, "is_valid_day": True, "steps": int(steps)})
        day += timedelta(days=1)
    with duckdb.connect(str(path)) as con:
        con.execute("create schema intermediate; create schema raw; create schema marts")
        con.register("r", pd.DataFrame(readings))
        con.execute("create table intermediate.int_cgm_flagged as select * from r")
        con.register("d", pd.DataFrame(days))
        con.execute("create table marts.mart_analysis_days as select * from d")
        con.execute("create table raw.source_files (kind varchar, sha256 varchar, bytes bigint, "
                    "n_rows bigint, loaded_at varchar)")
        con.execute("insert into raw.source_files values ('clarity', 'x', 1, 1, 'now')")
        device = "SYNTHETIC" if synthetic else "G7"
        con.execute(f"create table raw.clarity_events as select 'EGV' as event_type, '{device}' as source_device_id")
    return path


def draft(**design) -> dict:
    spec = yaml.safe_load(DRAFT.read_text())
    spec["design"].update(start=date(2025, 7, 7), foljsamhet={"kolumn": "steps", "A": {"min": 10000},
                                                               "B": {"max": 5000}},
                          verkan={"typ": "traning", "borjar": "07:00"})
    spec["design"].update(design)
    spec["analys"]["minsta_relevanta_effekt"] = -1.5
    return spec


def review(tmp_path: Path, spec: dict, **kw) -> dict:
    folder = tmp_path / spec["id"]
    folder.mkdir(exist_ok=True)
    (folder / "studie.yml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    study = st.load(folder / "studie.yml")
    with duckdb.connect(str(make_db(tmp_path / "db.duckdb", **kw)), read_only=True) as con:
        return granska.review(study, con, today=TODAY)


def levels(result: dict, check: str) -> set[str]:
    return {c["level"] for c in result["checks"] if c["id"] == check}


def test_the_first_steps_draft_is_stopped_for_positivity_and_carryover(tmp_path: Path) -> None:
    result = review(tmp_path, draft())
    assert result["verdict"] == granska.STOPP
    texts = " ".join(c["text"] for c in result["checks"] if c["level"] == granska.STOPP)
    assert "B inträffade inte en enda gång på vardagar" in texts, "few steps never happens on a work day"
    assert "A inträffade inte en enda gång på helger" in texts
    assert granska.STOPP in levels(result, "overforing"), "adjacent days after exercise"
    assert "nattliga negativa kontrollen" in texts, "the night after an A day is not a clean control"


def test_days_off_spaced_a_week_apart_pass_once_feasibility_is_explained(tmp_path: Path) -> None:
    spec = draft(dagar={"veckodagar": ["lordag"]}, dagar_motivering="B är omöjligt på arbetsdagar.")
    unexplained = review(tmp_path, spec)
    assert granska.STOPP in levels(unexplained, "positivitet"), "A never happened on a Saturday"
    spec["design"]["genomforbarhet"] = "A görs som en planerad promenad på 90 minuter på förmiddagen."
    result = review(tmp_path, spec)
    assert result["verdict"] != granska.STOPP, granska.render(result)
    assert levels(result, "overforing") == {granska.OK}
    assert granska.VARNING in levels(result, "tid"), "32 Saturdays is more than four months"


def test_a_negative_control_after_the_action_starts_is_stopped(tmp_path: Path) -> None:
    spec = draft(dagar={"veckodagar": ["lordag"]}, dagar_motivering="x", genomforbarhet="x")
    spec["design"]["verkan"]["borjar"] = "05:00"
    assert granska.STOPP in levels(review(tmp_path, spec), "tidsordning")


def test_power_is_computed_from_own_variability_and_says_how_many_pairs(tmp_path: Path) -> None:
    spec = draft(dagar={"veckodagar": ["lordag"]}, dagar_motivering="x", genomforbarhet="x", par=6)
    spec["analys"]["minsta_relevanta_effekt"] = -0.5
    result = review(tmp_path, spec)
    power = " ".join(c["text"] for c in result["checks"] if c["id"] == "styrka")
    assert "alla dagar" in power, "13 Saturdays are too few; the SD is pooled and that is said"
    assert granska.STOPP in levels(result, "styrka")
    assert "par behövs" in power


def test_review_on_synthetic_data_is_refused(tmp_path: Path) -> None:
    spec = draft(dagar={"veckodagar": ["lordag"]}, dagar_motivering="x", genomforbarhet="x")
    assert levels(review(tmp_path, spec, synthetic=True), "data") == {granska.STOPP}


def test_lock_requires_a_passed_review_of_this_exact_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(st, "_git", lambda *a: "" if a[0] in {"status", "diff"} else "abc123")
    spec = draft()
    folder = tmp_path / spec["id"]
    folder.mkdir()
    path = folder / "studie.yml"
    path.write_text(yaml.safe_dump(spec, allow_unicode=True))
    assert st.main(["las", str(path)]) == 2, "no review"
    review_file = folder / st.REVIEW_FILE
    review_file.write_text(json.dumps({"spec_sha256": "other", "verdict": "OK"}))
    assert st.main(["las", str(path)]) == 2, "review of another version"
    review_file.write_text(json.dumps({"spec_sha256": st._sha(path), "verdict": "STOPP"}))
    assert st.main(["las", str(path)]) == 2, "review with stops"
    review_file.write_text(json.dumps({"spec_sha256": st._sha(path), "verdict": "VARNING"}))
    study = st.load(path)
    st.require_review(study)
    st.lock(study, seed=1)
    assert (folder / "las.json").exists()


def test_adherence_counts_days_that_met_the_rule(tmp_path: Path) -> None:
    spec = draft(start=date(2025, 5, 5), dagar={"veckodagar": ["lordag", "sondag"]}, dagar_motivering="x")
    folder = tmp_path / spec["id"]
    folder.mkdir()
    (folder / "studie.yml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    study = st.load(folder / "studie.yml")
    st.n1.write_schedule(st.n1.make_schedule(date(2025, 5, 10), 6, 1, 0, seed=1, days=st.n1.eligible_dates(
        date(2025, 5, 10), 12, ["lordag", "sondag"])), study.schedule_path, 1)
    with duckdb.connect(str(make_db(tmp_path / "db.duckdb")), read_only=True) as con:
        adh = st._adherence(study, con)
    assert adh["A"] == {"dagar": 6, "matta": 6, "uppfyllda": 0}, "weekends never reach 10,000 in this data"
    assert adh["B"]["uppfyllda"] == 6


def test_oura_steps_come_from_daily_activity() -> None:
    df = parse([], [], [], [{"day": "2026-10-20", "steps": 10432}])
    assert df.iloc[0]["steps"] == 10432


@pytest.mark.parametrize("bad", [{"typ": "promenad", "borjar": "07:00"}, {"typ": "traning", "borjar": "7"}])
def test_action_must_be_a_known_type_with_a_clock_time(bad: dict) -> None:
    assert any("design.verkan" in e for e in st.validate(draft(verkan=bad)))


def test_observation_where_exposure_follows_day_type_is_stopped(tmp_path: Path) -> None:
    spec = yaml.safe_load((Path(__file__).parents[1] / "studies" / "000-exempel-promenad" / "studie.yml").read_text())
    spec.update(id="obs", tes="t", motbevis="m")
    spec["design"] = {"typ": "observation", "exponering": {"handelse": "hoga_steg", "dagar_efter": 0},
                      "period": [date(2025, 4, 1), date(2025, 6, 30)], "retrospektiv": True}
    spec["utfall"] = {"matt": "medel", "fonster": ["07:00", "23:59"]}
    spec["negativ_kontroll"] = {"matt": "medel", "fonster": ["00:00", "06:00"], "motivering": "x"}
    spec["analys"] = {"metod": "blockbootstrap", "blocklangd": 7, "niva": 0.95, "minsta_relevanta_effekt": -0.5,
                      "minsta_underlag": {"exponerade": 10, "jamforelse": 10}}
    spec["protokoll"] = {"periodeffekt": "x", "andringslogg": []}
    folder = tmp_path / "obs"
    folder.mkdir()
    (folder / "studie.yml").write_text(yaml.safe_dump(spec, allow_unicode=True))
    db = make_db(tmp_path / "db.duckdb")
    with duckdb.connect(str(db)) as con:
        con.execute("alter table marts.mart_analysis_days add column high_steps boolean")
        con.execute("update marts.mart_analysis_days set high_steps = steps >= 10000")
    with duckdb.connect(str(db), read_only=True) as con:
        result = granska.review(st.load(folder / "studie.yml"), con, today=TODAY)
    assert levels(result, "dagtyp") == {granska.STOPP}


def test_rotating_schedule_uses_logged_shifts_not_weekdays(tmp_path: Path) -> None:
    """With shifts logged, day types come from the log: a Tuesday off counts as a day off."""
    db = make_db(tmp_path / "db.duckdb")
    with duckdb.connect(str(db)) as con:
        con.execute("alter table marts.mart_analysis_days add column is_workday boolean")
        con.execute("update marts.mart_analysis_days set is_workday = steps >= 10000")
        workdays = granska._workdays(con)
    off = [date(2025, 7, 7) + timedelta(days=3 * i) for i in range(40)]
    spec = draft(dagar={"datum": off, "minsta_avstand": 3}, dagar_motivering="lediga dagar ur schemat")
    strata, caveat = granska._strata(spec["design"], workdays)
    assert [name for name, _ in strata] == ["lediga dagar enligt händelseloggen"]
    assert "loggat arbetspass" in caveat
    assert strata[0][1](date(2025, 6, 28)), "a Saturday without a shift is a day off"
    assert not strata[0][1](date(2025, 6, 30)), "a Monday with a shift is not"
    assert granska._min_gap_between_periods(spec["design"]) == 3
