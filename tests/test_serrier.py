"""serrier: person-förbudet bevisas, kandidater är idempotenta, trappan kräver kvitto."""

import json
from datetime import date

import duckdb
import pytest

from selvra_analysis import serrier

FORBJUDNA_KOLUMNNAMN = ("person", "namn", "name", "epost", "mail", "user",
                        "anvandare", "patient", "testare", "fodd", "birth", "kon")


def _rorlogg(tmp_path, rader):
    f = tmp_path / "data" / "rorlogg.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(json.dumps(r) for r in rader) + "\n")


RAD1 = {"tid": "2026-10-29T06:00:00+00:00", "kalla": "garminconnect", "person": "x",
        "bibliotek": "0.3.20", "enhet": "Venu 3", "firmware": "17.05", "falt": ["steps"]}
RAD2 = dict(RAD1, tid="2026-11-04T06:00:00+00:00", firmware="17.06")


def test_ingen_kolumn_kan_peka_pa_en_person(tmp_path, monkeypatch) -> None:
    """Gränsen är mekanisk: varje kolumnnamn i serrier-schemat prövas mot
    förbudslistan. Registret äger händelser om rör — aldrig människor."""
    monkeypatch.chdir(tmp_path)
    _rorlogg(tmp_path, [RAD1, RAD2])
    db = tmp_path / "t.duckdb"
    serrier.uppdatera(db)
    with duckdb.connect(str(db), read_only=True) as con:
        kolumner = con.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'serrier'").fetchall()
    assert kolumner, "schemat ska finnas"
    for tabell, kolumn in kolumner:
        for forbjudet in FORBJUDNA_KOLUMNNAMN:
            assert forbjudet not in kolumn.lower(), f"{tabell}.{kolumn} kan peka på en person"


def test_firmwarebyte_blir_kandidat_exakt_en_gang(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _rorlogg(tmp_path, [RAD1, RAD2])
    assert serrier.kandidater_fran_rorlogg() == 1
    assert serrier.kandidater_fran_rorlogg() == 0  # idempotent: aldrig två gånger
    post = next(r for r in serrier._journal_rader() if r["op"] == "kandidat")
    assert post["firmware_fore"] == "17.05"
    assert post["firmware_efter"] == "17.06"
    assert post["ror"] == "garminconnect"
    assert "person" not in post  # journalen bär aldrig person-fältet ur rörloggen


def test_trappan_kraver_kvitto_och_gar_ett_steg_i_taget(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _rorlogg(tmp_path, [RAD1, RAD2])
    serrier.kandidater_fran_rorlogg()
    hid = next(r for r in serrier._journal_rader() if r["op"] == "kandidat")["id"]

    with pytest.raises(ValueError, match="kvitto"):
        serrier.satt_status(hid, "provad", "  ")
    with pytest.raises(ValueError, match="hoppar"):
        serrier.satt_status(hid, "publicerad", "två likadana klockor, natt 3")
    serrier.satt_status(hid, "provad", "två rör samma apparat, natt 2026-11-05")
    assert serrier.status_for(hid) == "provad"
    serrier.satt_status(hid, "publicerad", "tillverkaren svarade ej inom 7 dagar; aggregat")
    assert serrier.status_for(hid) == "publicerad"


def test_schemat_ar_en_aterspelning_av_journalen(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _rorlogg(tmp_path, [RAD1, RAD2])
    serrier.kandidater_fran_rorlogg()
    db = tmp_path / "t.duckdb"
    serrier.spela_upp(db)
    with duckdb.connect(str(db), read_only=True) as con:
        fw = con.execute("select version, forst_sedd from serrier.firmware order by 1").fetchall()
        h = con.execute("select status, ror from serrier.handelse").fetchall()
    assert ("17.05", date(2026, 10, 29)) in fw
    assert ("17.06", date(2026, 11, 4)) in fw
    assert h == [("kandidat", "garminconnect")]
