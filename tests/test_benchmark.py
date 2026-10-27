"""The benchmark scores mechanically and refuses cases changed after freezing."""

from datetime import date
from pathlib import Path

import duckdb
import pytest

from selvra_analysis import benchmark as bm


def test_a_stop_counts_only_for_a_reason_in_the_key() -> None:
    key = {"forvantat": "STOPP", "skal": ["positivitet"]}
    assert bm.score(key, {"dom": "STOPP", "stopp": ["positivitet"], "varningar": []}) == \
        {"ratt_dom": True, "ratt_skal": True}
    assert bm.score(key, {"dom": "STOPP", "stopp": ["tid"], "varningar": []}) == \
        {"ratt_dom": True, "ratt_skal": False}
    assert bm.score(key, {"dom": "GODKANN", "stopp": [], "varningar": ["positivitet"]})["ratt_dom"] is False


def test_a_pass_must_carry_the_required_warnings() -> None:
    key = {"forvantat": "GODKANN", "flagga": ["apparat"]}
    assert bm.score(key, {"dom": "GODKANN", "stopp": [], "varningar": ["apparat"]})["ratt_skal"]
    assert not bm.score(key, {"dom": "GODKANN", "stopp": [], "varningar": []})["ratt_skal"]


def test_stopping_everything_is_reported_as_false_stops() -> None:
    rows = [{"fall": "a", "facit": {"forvantat": "STOPP"}, "ratt_dom": True, "ratt_skal": True},
            {"fall": "b", "facit": {"forvantat": "GODKANN"}, "ratt_dom": False, "ratt_skal": False}]
    s = bm.summarise(rows)
    assert s["stoppfrekvens"] == "1/1"
    assert s["falska_stopp"] == ["b"]


def test_changed_cases_are_refused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(bm, "BENCH", tmp_path)
    monkeypatch.setattr(bm, "MANIFEST", tmp_path / "FRYST.sha256")
    (tmp_path / "fall" / "x").mkdir(parents=True)
    (tmp_path / "fall" / "x" / "facit.yml").write_text("forvantat: STOPP\n")
    bm.write_manifest()
    bm.check_manifest()
    (tmp_path / "fall" / "x" / "facit.yml").write_text("forvantat: GODKANN\n")
    with pytest.raises(SystemExit, match="skiljer sig"):
        bm.check_manifest()


def test_scenario_builds_the_tables_the_review_reads(tmp_path: Path) -> None:
    scn = {"start": date(2025, 4, 1), "dagar": 14, "idag": date(2025, 4, 15),
           "arbete": {"monster": "rullande", "cykel": [1, 0], "loggat": True},
           "steg": {"arbete": 11000, "ledig": 3000, "sd": 1}, "tackning": 1.0}
    bm.build_db(scn, tmp_path / "x.duckdb")
    with duckdb.connect(str(tmp_path / "x.duckdb"), read_only=True) as con:
        days = con.execute("select is_workday, steps >= 10000 from marts.mart_analysis_days "
                           "order by reading_date").fetchall()
        n = con.execute("select count(*) from intermediate.int_cgm_flagged").fetchone()[0]
    assert days[:2] == [(True, True), (False, False)], "rotating roster from the cycle"
    assert n == 14 * 288


def test_the_review_answers_every_development_case_correctly(tmp_path: Path) -> None:
    """Regression guard: a change to granska that lets a known flaw through, or stops a valid
    design, fails the build. The held-out set is not run here; it is the honest measure."""
    wrong = []
    for case in bm.cases("fall"):
        _, facit = bm._load(case)
        result = bm.score(facit, bm.run_granska(case, tmp_path))
        if not result["ratt_skal"]:
            wrong.append(case.name)
    assert wrong == []
