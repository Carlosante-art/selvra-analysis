"""The proposal gate: silence until the review approves, and never while a trial runs."""

import itertools
from datetime import date
from pathlib import Path

import duckdb

from selvra_analysis import forslag


def test_template_dates_are_spaced_and_in_the_future() -> None:
    idag = date(2026, 11, 1)
    spec = forslag._mall(idag)
    datum = spec["design"]["dagar"]["datum"]
    assert len(datum) == forslag.ANTAL_DAGAR
    assert min(datum) > idag
    mellanrum = [(b - a).days for a, b in itertools.pairwise(datum)]
    assert min(mellanrum) >= forslag.AVSTAND_DAGAR


def test_a_locked_proposal_is_never_nagged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # förslag bor i personmappen, relativ arbetskatalogen
    db = tmp_path / "selvra.duckdb"
    mapp = tmp_path / "data" / "personer" / "x" / "forslag" / forslag.FORSLAG_ID
    mapp.mkdir(parents=True)
    (mapp / "las.json").write_text("{}")
    assert forslag.forslagsrad("x", db, date(2026, 11, 1), bygg=False) is None


def test_a_stop_from_the_review_means_silence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "selvra.duckdb"
    duckdb.connect(str(db)).close()
    monkeypatch.setattr(forslag.st, "load", lambda p: object())
    monkeypatch.setattr(forslag.granska, "review",
                        lambda s, c, today=None: {"verdict": "STOPP", "checks": [
                            {"level": "STOPP", "id": "underlag", "text": "för lite"}]})
    assert forslag.forslagsrad("x", db, date(2026, 11, 1), bygg=False) is None


def test_an_approval_lights_the_invitation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "selvra.duckdb"
    duckdb.connect(str(db)).close()
    monkeypatch.setattr(forslag.st, "load", lambda p: object())
    monkeypatch.setattr(forslag.granska, "review",
                        lambda s, c, today=None: {"verdict": "OK", "checks": [
                            {"level": "OK", "id": "styrka", "text": "räcker"}]})
    rad = forslag.forslagsrad("x", db, date(2026, 11, 1), bygg=False)
    assert rad == forslag.INBJUDAN
    assert (tmp_path / "data" / "personer" / "x" / "forslag" / forslag.FORSLAG_ID
            / "studie.yml").exists(), "utkastet ska bo i personmappen"
