"""Load Dexcom Clarity CSV exports into DuckDB, as-is.

The raw layer keeps the export's own values as text. Typing, unit handling,
deduplication and flagging happen in dbt, where every decision is visible
and tested.

Patient identifiers are dropped here: the `Patient Info` column and the
FirstName / LastName / DateOfBirth rows never reach the database.

Usage:
    python -m selvra_analysis.ingest_clarity data/raw/*.csv --db data/selvra.duckdb
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis import manifest

PII_EVENT_TYPES = {"FirstName", "LastName", "DateOfBirth", "Förnamn", "Efternamn", "Födelsedatum"}

# Clarity header prefix -> our column name. Matched by prefix because the
# unit is part of the header ("Glucose Value (mmol/L)" or "(mg/dL)").
# Both English (US/global) and Swedish (EU) column names are included.
COLUMN_PREFIXES = {
    # English
    "Index": "source_row",
    "Timestamp": "ts_raw",
    "Event Type": "event_type",
    "Event Subtype": "event_subtype",
    "Device Info": "device_info",
    "Source Device ID": "source_device_id",
    "Glucose Value": "glucose_raw",
    "Insulin Value": "insulin_raw",
    "Carb Value": "carbs_raw",
    "Duration": "duration_raw",
    "Glucose Rate of Change": "rate_of_change_raw",
    "Transmitter Time": "transmitter_time_raw",
    "Transmitter ID": "transmitter_id",
    # Swedish (EU export)
    "Sakregister": "source_row",
    "Tidsstämpel": "ts_raw",
    "Händelsetyp": "event_type",
    "Händelseundertyp": "event_subtype",
    "Enhetsinfo": "device_info",
    "Källenhets-ID": "source_device_id",
    "Glukosvärde": "glucose_raw",
    "Insulinvärde": "insulin_raw",
    "Kolhydratvärde": "carbs_raw",
    "Varaktighet": "duration_raw",
    "Förändringshastighet": "rate_of_change_raw",
    "Sändartid": "transmitter_time_raw",
    "Sändar-ID": "transmitter_id",
}

# Swedish and English headers map to the same names; keep each name once, in order.
EXPORT_COLUMNS = list(dict.fromkeys(COLUMN_PREFIXES.values()))
RAW_COLUMNS = [*EXPORT_COLUMNS, "glucose_unit", "source_file", "loaded_at"]


def _glucose_unit(header: str) -> str:
    if "mmol" in header:
        return "mmol/L"
    if "mg/dL" in header:
        return "mg/dL"
    raise ValueError(f"Unknown glucose unit in header: {header!r}")


def _detect_separator(path: Path) -> str:
    """Sniff separator from first line — EU exports use ';', US exports use ','."""
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        first = f.readline()
    return ";" if first.count(";") > first.count(",") else ","


def read_clarity_csv(path: Path) -> pd.DataFrame:
    """Read one Clarity export and return it in the raw schema."""
    sep = _detect_separator(path)
    df = pd.read_csv(path, dtype=str, keep_default_na=False,
                     sep=sep, encoding="utf-8-sig")

    rename: dict[str, str] = {}
    unit = None
    for col in df.columns:
        for prefix, name in COLUMN_PREFIXES.items():
            if col.strip().startswith(prefix):
                rename[col] = name
                if name == "glucose_raw":
                    unit = _glucose_unit(col)
                break
    missing = set(EXPORT_COLUMNS) - set(rename.values())
    if missing:
        raise ValueError(f"{path.name}: not a Clarity export, missing columns {sorted(missing)}")

    df = df.rename(columns=rename)
    df = df[~df["event_type"].isin(PII_EVENT_TYPES)]
    df = df[EXPORT_COLUMNS].copy()
    df["glucose_unit"] = unit
    df["source_file"] = path.name
    df["loaded_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return df[RAW_COLUMNS]


def ensure_raw_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Both CGM sources exist as tables, empty if never loaded, so staging always builds."""
    con.execute("create schema if not exists raw")
    cols = ", ".join(f"{c} varchar" for c in RAW_COLUMNS)
    con.execute(f"create table if not exists raw.clarity_events ({cols})")
    con.execute(
        "create table if not exists raw.share_readings "
        "(reading_at timestamptz, value_mgdl integer, trend varchar, loaded_at varchar)"
    )
    con.execute(
        "create table if not exists raw.source_files "
        "(kind varchar, sha256 varchar, bytes bigint, n_rows bigint, loaded_at varchar)"
    )


def load(paths: list[Path], db_path: Path) -> int:
    """Rebuild raw.clarity_events from all given files. Returns row count."""
    paths = sorted(paths)
    frames = [read_clarity_csv(p) for p in paths]
    if not frames:
        raise SystemExit("No CSV files given. Put Clarity exports in data/raw/.")
    events = pd.concat(frames, ignore_index=True)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        ensure_raw_tables(con)
        con.register("events_df", events)
        con.execute("create or replace table raw.clarity_events as select * from events_df")
        n = con.execute("select count(*) from raw.clarity_events").fetchone()[0]
        manifest.record(con, "clarity", [(p, len(f)) for p, f in zip(paths, frames, strict=True)])
    return n


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--db", type=Path, default=Path("data/selvra.duckdb"))
    args = parser.parse_args(argv)

    n = load(args.files, args.db)
    print(f"Loaded {n} rows from {len(args.files)} file(s) into {args.db}", file=sys.stderr)


if __name__ == "__main__":
    main()
