"""Load the personal event log (handelser.csv) into DuckDB.

The log is the context the sensor cannot see: illness, sensor changes,
alcohol, training, travel, stress. It is what makes alternative explanations
testable in step 3 of the analysis template.

Format (see data/handelser.mall.csv):
    start,slut,typ,notering
    2025-03-02,2025-03-05,sjukdom,förkyld
    2025-03-10,,sensorbyte,
    2025-03-10 21:00,,alkohol,två glas vin

`start` is a date or a datetime. `slut` is optional (single-day event).
`typ` must be one of EVENT_TYPES. The file is validated strictly: an unknown
type or an unreadable date stops the load with the line number.

Usage:
    python -m selvra_analysis.ingest_events data/raw/handelser.csv --db data/selvra.duckdb
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis import manifest

EVENT_TYPES = {
    "sjukdom",
    "sensorbyte",
    "alkohol",
    "traning",
    "resa",
    "stress",
    "menstruation",
    "medicinandring",
    "annat",
}
REQUIRED = ["start", "slut", "typ", "notering"]


class EventLogError(ValueError):
    pass


def read_event_log(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise EventLogError(f"{path.name}: saknar kolumner {missing}. Använd data/handelser.mall.csv.")

    errors = []
    for i, row in df.iterrows():
        line = i + 2  # header is line 1
        if row["typ"].strip() not in EVENT_TYPES:
            errors.append(f"rad {line}: okänd typ {row['typ']!r}, tillåtna: {sorted(EVENT_TYPES)}")
        for col in ("start", "slut"):
            value = row[col].strip()
            if (col == "start" or value) and pd.isna(pd.to_datetime(value, errors="coerce")):
                errors.append(f"rad {line}: kan inte läsa {col} {value!r}")
    if errors:
        raise EventLogError(f"{path.name}:\n  " + "\n  ".join(errors))

    out = df[REQUIRED].apply(lambda s: s.str.strip())
    out["source_line"] = range(2, len(out) + 2)
    return out


def load(path: Path, db_path: Path) -> int:
    """Load the log. A missing file gives an empty table, so the pipeline still builds."""
    if path.exists():
        events = read_event_log(path)
    else:
        print(f"No event log at {path}; analyses run without context.", file=sys.stderr)
        events = pd.DataFrame({c: pd.Series(dtype=str) for c in REQUIRED})
        events["source_line"] = pd.Series(dtype="int64")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("create schema if not exists raw")
        con.register("events_df", events)
        con.execute("create or replace table raw.personal_events as select * from events_df")
        manifest.record(con, "event_log", [(path, len(events))] if path.exists() else [])
        return con.execute("select count(*) from raw.personal_events").fetchone()[0]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--db", type=Path, default=Path("data/selvra.duckdb"))
    args = parser.parse_args(argv)
    try:
        n = load(args.file, args.db)
    except EventLogError as e:
        raise SystemExit(f"Händelseloggen har fel:\n{e}") from None
    print(f"Loaded {n} events from {args.file} into {args.db}", file=sys.stderr)


if __name__ == "__main__":
    main()
