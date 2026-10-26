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

PII_EVENT_TYPES = {"FirstName", "LastName", "DateOfBirth"}

# Clarity header prefix -> our column name. Matched by prefix because the
# unit is part of the header ("Glucose Value (mmol/L)" or "(mg/dL)").
COLUMN_PREFIXES = {
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
}

RAW_COLUMNS = [*COLUMN_PREFIXES.values(), "glucose_unit", "source_file", "loaded_at"]


def _glucose_unit(header: str) -> str:
    if "mmol" in header:
        return "mmol/L"
    if "mg/dL" in header:
        return "mg/dL"
    raise ValueError(f"Unknown glucose unit in header: {header!r}")


def read_clarity_csv(path: Path) -> pd.DataFrame:
    """Read one Clarity export and return it in the raw schema."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    rename: dict[str, str] = {}
    unit = None
    for col in df.columns:
        for prefix, name in COLUMN_PREFIXES.items():
            if col.strip().startswith(prefix):
                rename[col] = name
                if name == "glucose_raw":
                    unit = _glucose_unit(col)
                break
    missing = set(COLUMN_PREFIXES.values()) - set(rename.values())
    if missing:
        raise ValueError(f"{path.name}: not a Clarity export, missing columns {sorted(missing)}")

    df = df.rename(columns=rename)
    df = df[~df["event_type"].isin(PII_EVENT_TYPES)]
    df = df[list(COLUMN_PREFIXES.values())].copy()
    df["glucose_unit"] = unit
    df["source_file"] = path.name
    df["loaded_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return df[RAW_COLUMNS]


def load(paths: list[Path], db_path: Path) -> int:
    """Rebuild raw.clarity_events from all given files. Returns row count."""
    paths = sorted(paths)
    frames = [read_clarity_csv(p) for p in paths]
    if not frames:
        raise SystemExit("No CSV files given. Put Clarity exports in data/raw/.")
    events = pd.concat(frames, ignore_index=True)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("create schema if not exists raw")
        con.register("events_df", events)
        con.execute("create or replace table raw.clarity_events as select * from events_df")
        n = con.execute("select count(*) from raw.clarity_events").fetchone()[0]
        manifest.record(con, "clarity", [(p, len(f)) for p, f in zip(paths, frames)])
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
