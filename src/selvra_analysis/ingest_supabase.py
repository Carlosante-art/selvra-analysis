"""Load CGM readings collected by Selvra Diabetes (Dexcom Share polling) from Supabase.

Readings land in raw.share_readings as exact UTC instants in the unit Dexcom measures
(mg/dL), never converted to local wall-clock time and back: Share gives the instant,
so there is nothing to guess around daylight saving time.

Clarity exports stay the authoritative history (they include backfilled readings Share
never delivers). Staging uses Share readings only after the last Clarity reading, so the
two sources never count the same reading twice.

Every load writes a snapshot of the exact rows to data/snapshots/ (git-ignored) and
records its SHA-256 in raw.source_files, so an analysis result names the data version it
used and the data can be reloaded byte for byte later.

Requires in .env (never committed, never printed):
    ANALYSIS_DB_URL   postgresql://analysis_readonly:<password>@<host>:5432/postgres
    ANALYSIS_USER_ID  your user id in Selvra Diabetes

Usage:
    uv run python -m selvra_analysis.ingest_supabase --db data/selvra.duckdb
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis.ingest_clarity import ensure_raw_tables

SNAPSHOTS = Path("data/snapshots")


def fetch(user_id: str, pg_url: str) -> pd.DataFrame:
    """Read this user's readings from Supabase: reading_at (UTC), value_mgdl, trend."""
    with duckdb.connect() as con:
        con.execute("set TimeZone = 'UTC'")
        con.execute("install postgres; load postgres;")
        try:
            con.execute(f"attach '{pg_url.replace(chr(39), chr(39) * 2)}' as pg (type postgres, read_only)")
        except duckdb.Error:
            # The driver's message can contain the connection string. Never print it.
            raise SystemExit("Could not connect to Supabase with ANALYSIS_DB_URL.") from None
        return con.execute(
            """
            select time as reading_at, value_mgdl, trend
            from pg.public.glucose_readings
            where user_id = ?::uuid
            order by time
            """,
            [user_id],
        ).df()


def store(rows: pd.DataFrame, db_path: Path, snapshot_dir: Path = SNAPSHOTS) -> str:
    """Write rows to raw.share_readings, snapshot them, record the checksum. Returns it."""
    if rows.empty:
        raise SystemExit("No readings for ANALYSIS_USER_ID. Check the id.")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    loaded_at = datetime.now(UTC).isoformat(timespec="seconds")
    rows = rows.assign(reading_at=pd.to_datetime(rows["reading_at"], utc=True)).sort_values("reading_at")
    with duckdb.connect(str(db_path)) as con:
        canonical = rows.assign(reading_at=rows["reading_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        text = canonical.to_csv(index=False)
        digest = hashlib.sha256(text.encode()).hexdigest()
        snapshot = snapshot_dir / f"share_{digest[:16]}.csv"
        snapshot.write_text(text)

        ensure_raw_tables(con)
        con.register("share_df", rows)
        con.execute(
            "create or replace table raw.share_readings as "
            "select reading_at::timestamptz as reading_at, value_mgdl::integer as value_mgdl, "
            "trend, ? as loaded_at from share_df",
            [loaded_at],
        )
        con.execute("delete from raw.source_files where kind = 'dexcom_share'")
        con.execute(
            "insert into raw.source_files values ('dexcom_share', ?, ?, ?, ?)",
            [digest, len(text.encode()), len(rows), loaded_at],
        )
    return digest


def read_env_file(path: Path = Path(".env")) -> None:
    """Set KEY=VALUE lines from .env into the environment, unless already set. Values are
    taken literally (a password may contain $ or #), and nothing is ever printed."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key.strip().removeprefix("export ").strip(), value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path("data/selvra.duckdb"))
    args = parser.parse_args(argv)

    read_env_file()
    pg_url = os.environ.get("ANALYSIS_DB_URL", "")
    user_id = os.environ.get("ANALYSIS_USER_ID", "")
    if not pg_url or not user_id:
        raise SystemExit("Set ANALYSIS_DB_URL and ANALYSIS_USER_ID in .env.")
    rows = fetch(user_id, pg_url)
    digest = store(rows, args.db)
    print(f"Loaded {len(rows)} Share readings into {args.db} (data version {digest[:12]})",
          file=sys.stderr)


if __name__ == "__main__":
    main()
