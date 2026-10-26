"""Load CGM readings from Supabase (glucose_readings) into DuckDB.

Reads via DuckDB's built-in Postgres extension — no extra Python dependency.
UTC timestamps are converted to Europe/Stockholm local wall-clock time so the
data flows through the same DST-aware staging model as Clarity exports.

Requires env var:
    ANALYSIS_DB_URL  postgresql://analysis_readonly:<password>@<host>:5432/postgres

Usage:
    ANALYSIS_DB_URL=postgresql://... uv run python -m selvra_analysis.ingest_supabase \
        --user-id 98345704-bed3-4f31-ac83-4818171d39ea --db data/selvra.duckdb
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

SOURCE_FILE = "supabase_live"


def load(user_id: str, db_path: Path, pg_url: str) -> int:
    """Read glucose_readings for user_id and upsert into raw.clarity_events."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("install postgres; load postgres;")
        con.execute(f"attach '{pg_url}' as pg (type postgres, read_only)")

        con.execute("create schema if not exists raw")

        # Skapa tabellen om den inte finns (första körningen utan Clarity-export)
        con.execute("""
            create table if not exists raw.clarity_events (
                source_row        varchar,
                ts_raw            varchar,
                event_type        varchar not null,
                event_subtype     varchar,
                device_info       varchar,
                source_device_id  varchar,
                glucose_raw       varchar,
                insulin_raw       varchar,
                carbs_raw         varchar,
                duration_raw      varchar,
                rate_of_change_raw varchar,
                transmitter_time_raw varchar,
                transmitter_id    varchar,
                glucose_unit      varchar,
                source_file       varchar,
                loaded_at         varchar
            )
        """)

        # Ersätt tidigare supabase-rader; Clarity-rader rörs inte
        con.execute("delete from raw.clarity_events where source_file = ?", [SOURCE_FILE])

        loaded_at = datetime.now(UTC).isoformat(timespec="seconds")

        con.execute("""
            insert into raw.clarity_events
            select
                cast(row_number() over (order by time) as varchar)  as source_row,
                strftime(timezone('Europe/Stockholm', time), '%Y-%m-%dT%H:%M:%S') as ts_raw,
                'EGV'                                                as event_type,
                null                                                 as event_subtype,
                'Dexcom Share (Supabase)'                            as device_info,
                null                                                 as source_device_id,
                cast(value_mmol as varchar)                          as glucose_raw,
                null                                                 as insulin_raw,
                null                                                 as carbs_raw,
                null                                                 as duration_raw,
                null                                                 as rate_of_change_raw,
                null                                                 as transmitter_time_raw,
                null                                                 as transmitter_id,
                'mmol/L'                                             as glucose_unit,
                ?                                                    as source_file,
                ?                                                    as loaded_at
            from pg.public.glucose_readings
            where user_id = ?::uuid
            order by time
        """, [SOURCE_FILE, loaded_at, user_id])

        n = con.execute(
            "select count(*) from raw.clarity_events where source_file = ?", [SOURCE_FILE]
        ).fetchone()[0]

        # Manifest: spara källinfo utan fil-hash (ingen fil finns)
        con.execute("""
            create table if not exists raw.source_files (
                kind varchar, sha256 varchar, bytes bigint, n_rows bigint, loaded_at varchar
            )
        """)
        con.execute("delete from raw.source_files where kind = 'supabase'")
        con.execute(
            "insert into raw.source_files values ('supabase', ?, null, ?, ?)",
            [f"user_id={user_id}", n, loaded_at],
        )

        con.execute("detach pg")
    return n


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user-id", required=True, help="UUID för din användare i Supabase")
    parser.add_argument("--db", type=Path, default=Path("data/selvra.duckdb"))
    args = parser.parse_args(argv)

    pg_url = os.environ.get("ANALYSIS_DB_URL", "")
    if not pg_url:
        print("Fel: ANALYSIS_DB_URL är inte satt.", file=sys.stderr)
        raise SystemExit(1)

    n = load(args.user_id, args.db, pg_url)
    print(f"Laddade {n} rader från Supabase till {args.db}", file=sys.stderr)


if __name__ == "__main__":
    main()
