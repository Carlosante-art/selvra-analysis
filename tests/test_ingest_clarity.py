from pathlib import Path

import duckdb
import pytest

from selvra_analysis.ingest_clarity import load, read_clarity_csv

HEADER_MMOL = (
    "Index,Timestamp (YYYY-MM-DDThh:mm:ss),Event Type,Event Subtype,Patient Info,Device Info,"
    "Source Device ID,Glucose Value (mmol/L),Insulin Value (u),Carb Value (grams),"
    "Duration (hh:mm:ss),Glucose Rate of Change (mmol/L/min),Transmitter Time (Long Integer),"
    "Transmitter ID"
)


def _write(tmp_path: Path, name: str, header: str, rows: list[str]) -> Path:
    path = tmp_path / name
    path.write_text("\n".join([header, *rows]) + "\n")
    return path


@pytest.fixture
def export(tmp_path: Path) -> Path:
    return _write(tmp_path, "export.csv", HEADER_MMOL, [
        "1,,FirstName,,Carl,,,,,,,,,",
        "2,,LastName,,Example,,,,,,,,,",
        "3,,DateOfBirth,,2000-01-01,,,,,,,,,",
        "4,2025-03-01T02:00:00,EGV,,,,iOS G7,6.2,,,,,,AB12",
        "5,2025-03-01T02:05:00,EGV,,,,iOS G7,Low,,,,,,AB12",
        "6,2025-03-01T02:10:00,EGV,,,,iOS G7,High,,,,,,AB12",
    ])


def test_patient_identifiers_are_dropped(export: Path) -> None:
    df = read_clarity_csv(export)
    assert "Patient Info" not in df.columns
    assert not df["event_type"].isin({"FirstName", "LastName", "DateOfBirth"}).any()
    assert "Carl" not in df.to_string()


def test_low_and_high_are_kept_as_text(export: Path) -> None:
    df = read_clarity_csv(export)
    assert list(df["glucose_raw"]) == ["6.2", "Low", "High"]
    assert set(df["glucose_unit"]) == {"mmol/L"}


def test_mgdl_export_is_recognised(tmp_path: Path) -> None:
    header = HEADER_MMOL.replace("(mmol/L)", "(mg/dL)").replace("(mmol/L/min)", "(mg/dL/min)")
    path = _write(tmp_path, "us.csv", header, ["1,2025-03-01T02:00:00,EGV,,,,x,112,,,,,,AB12"])
    assert read_clarity_csv(path)["glucose_unit"].iloc[0] == "mg/dL"


def test_non_clarity_file_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "other.csv", "date,value", ["2025-01-01,5"])
    with pytest.raises(ValueError, match="not a Clarity export"):
        read_clarity_csv(path)


def test_load_rebuilds_table(export: Path, tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    assert load([export], db) == 3
    assert load([export, export], db) == 6  # overlap is deduplicated later, in dbt
    with duckdb.connect(str(db)) as con:
        assert con.execute("select count(*) from raw.clarity_events").fetchone()[0] == 6


HEADER_SV = (
    "Sakregister;Tidsstämpel (ÅÅÅÅ-MM-DDThh:mm:ss);Händelsetyp;Händelseundertyp;Patientinformation;"
    "Enhetsinfo;Källenhets-ID;Glukosvärde (mmol/l);Insulinvärde (E);Kolhydratvärde (gram);"
    "Varaktighet (hh:mm:ss);Förändringshastighet för glukos (mmol/l/min);Sändartid (långt heltal);Sändar-ID"
)


def test_swedish_eu_export(tmp_path: Path) -> None:
    path = tmp_path / "sv.csv"
    rows = [
        "1;;Förnamn;;Carl;;;;;;;;;",
        "2;;Efternamn;;Exempel;;;;;;;;;",
        "3;;Födelsedatum;;2000-01-01;;;;;;;;;",
        "4;2025-03-01T02:00:00;EGV;;;;iOS G7;6,2;;;;;123;AB12",
        "5;2025-03-01T02:05:00;EGV;;;;iOS G7;Lågt;;;;;423;AB12",
    ]
    path.write_text("\n".join([HEADER_SV, *rows]) + "\n", encoding="utf-8-sig")
    df = read_clarity_csv(path)
    assert list(df.columns) == list(dict.fromkeys(df.columns)), "duplicate column names"
    assert "Carl" not in df.to_string() and "Exempel" not in df.to_string()
    egv = df[df["event_type"] == "EGV"]
    assert egv["glucose_raw"].tolist() == ["6,2", "Lågt"]
    assert set(egv["glucose_unit"]) == {"mmol/L"}
    assert egv["transmitter_time_raw"].tolist() == ["123", "423"]
