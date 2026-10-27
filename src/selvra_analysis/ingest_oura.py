"""Hämta sömndata från Oura Ring API och ladda in i DuckDB.

Kräver OURA_TOKEN i .env (personlig åtkomsttoken från cloud.ouraring.com/personal-access-tokens).

Laddar: sleep_score, total_sleep_seconds, rem_sleep_seconds, deep_sleep_seconds,
        efficiency, hr_lowest, hrv_avg, readiness_score per dygn.

Usage:
    uv run python -m selvra_analysis.ingest_oura --db data/selvra.duckdb
    make build-live   # kör automatiskt om OURA_TOKEN finns
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import pandas as pd

from selvra_analysis.ingest_clarity import OURA_COLUMNS, ensure_raw_tables

SNAPSHOTS = Path("data/snapshots")
DB_DEFAULT = Path("data/selvra.duckdb")
OURA_API = "https://api.ouraring.com/v2/usercollection"


def _load_dotenv() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key == "OURA_TOKEN" and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


def _get(token: str, endpoint: str, start: str, end: str) -> list[dict]:
    resp = httpx.get(f"{OURA_API}/{endpoint}", params={"start_date": start, "end_date": end},
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def parse(daily_sleep: list[dict], daily_readiness: list[dict], sleep_periods: list[dict]) -> pd.DataFrame:
    """One row per day, with each value from the endpoint that actually holds it.

    Oura's daily_sleep and daily_readiness `contributors` are 1-100 sub-scores, not
    durations, milliseconds or beats per minute. Measured values (seconds, ms, bpm, %)
    come from the sleep periods endpoint; the main period of each day is the longest one.
    """
    days: dict[str, dict] = {}
    for item in daily_sleep:
        if item.get("day"):
            days.setdefault(item["day"], {})["sleep_score"] = item.get("score")
    for item in daily_readiness:
        if item.get("day"):
            days.setdefault(item["day"], {})["readiness_score"] = item.get("score")
    main_periods: dict[str, dict] = {}
    for period in sleep_periods:
        day = period.get("day")
        if day and (period.get("total_sleep_duration") or 0) >= (
                main_periods.get(day, {}).get("total_sleep_duration") or 0):
            main_periods[day] = period
    for day, period in main_periods.items():
        days.setdefault(day, {}).update({
            "total_sleep_seconds": period.get("total_sleep_duration"),
            "deep_sleep_seconds": period.get("deep_sleep_duration"),
            "rem_sleep_seconds": period.get("rem_sleep_duration"),
            "sleep_efficiency_pct": period.get("efficiency"),
            "hrv_avg_ms": period.get("average_hrv"),
            "hr_lowest_bpm": period.get("lowest_heart_rate"),
        })
    return pd.DataFrame([{"reading_date": d, **v} for d, v in sorted(days.items())], columns=OURA_COLUMNS)


def _fetch(token: str, start: str, end: str) -> pd.DataFrame:
    return parse(_get(token, "daily_sleep", start, end), _get(token, "daily_readiness", start, end),
                 _get(token, "sleep", start, end))


def load(db_path: Path, days_back: int = 90) -> int:
    _load_dotenv()
    token = os.environ.get("OURA_TOKEN")
    if not token:
        print("OURA_TOKEN saknas — hoppar över Oura-inläsning.", file=sys.stderr)
        return 0

    end = str(date.today())
    start = str(date.today() - timedelta(days=days_back))

    print(f"Hämtar Oura-data {start} → {end}...", file=sys.stderr)
    df = _fetch(token, start, end)
    if df.empty:
        print("Inga Oura-data hittades.", file=sys.stderr)
        return 0

    text = df.to_csv(index=False)
    digest = hashlib.sha256(text.encode()).hexdigest()
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    (SNAPSHOTS / f"oura_{digest[:16]}.csv").write_text(text)
    with duckdb.connect(str(db_path)) as con:
        ensure_raw_tables(con)
        con.register("oura_df", df)
        cols = ", ".join(OURA_COLUMNS)
        con.execute("delete from raw.oura_sleep")
        con.execute(f"insert into raw.oura_sleep ({cols}) select {cols} from oura_df")  # noqa: S608
        n = con.execute("select count(*) from raw.oura_sleep").fetchone()[0]
        con.execute("delete from raw.source_files where kind = 'oura'")
        con.execute("insert into raw.source_files values ('oura', ?, ?, ?, ?)",
                    [digest, len(text.encode()), n, datetime.now(UTC).isoformat(timespec="seconds")])

    print(f"Laddade {n} Oura-dagar.", file=sys.stderr)
    return n


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    parser.add_argument("--dagar", type=int, default=90, help="Antal dagar bakåt (default: 90)")
    args = parser.parse_args(argv)
    load(args.db, args.dagar)


if __name__ == "__main__":
    main()
