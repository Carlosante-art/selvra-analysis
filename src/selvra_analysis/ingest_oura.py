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
import os
import sys
from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis import manifest

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


def _fetch(token: str, start: str, end: str) -> pd.DataFrame:
    try:
        import httpx
    except ImportError:
        raise SystemExit("Installera httpx: uv add httpx")

    headers = {"Authorization": f"Bearer {token}"}
    rows = []

    for endpoint, key in [("daily_sleep", "sleep"), ("daily_readiness", "readiness")]:
        resp = httpx.get(
            f"{OURA_API}/{endpoint}",
            params={"start_date": start, "end_date": end},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            date = item.get("day")
            if not date:
                continue
            if key == "sleep":
                contributors = item.get("contributors", {})
                rows.append({
                    "reading_date": date,
                    "sleep_score": item.get("score"),
                    "total_sleep_seconds": contributors.get("total_sleep"),
                    "rem_sleep_seconds": contributors.get("rem_sleep"),
                    "deep_sleep_seconds": contributors.get("deep_sleep"),
                    "efficiency": contributors.get("efficiency"),
                })
            else:
                existing = next((r for r in rows if r["reading_date"] == date), None)
                if existing:
                    existing["readiness_score"] = item.get("score")
                    existing["hrv_avg"] = item.get("contributors", {}).get("hrv_balance")
                    existing["hr_lowest"] = item.get("contributors", {}).get("resting_heart_rate")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in ["readiness_score", "hrv_avg", "hr_lowest"]:
        if col not in df.columns:
            df[col] = None
    return df


def load(db_path: Path, days_back: int = 90) -> int:
    _load_dotenv()
    token = os.environ.get("OURA_TOKEN")
    if not token:
        print("OURA_TOKEN saknas — hoppar över Oura-inläsning.", file=sys.stderr)
        return 0

    from datetime import date, timedelta
    end = str(date.today())
    start = str(date.today() - timedelta(days=days_back))

    print(f"Hämtar Oura-data {start} → {end}...", file=sys.stderr)
    df = _fetch(token, start, end)
    if df.empty:
        print("Inga Oura-data hittades.", file=sys.stderr)
        return 0

    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.register("oura_df", df)
        con.execute("""
            CREATE OR REPLACE TABLE raw.oura_sleep AS
            SELECT * FROM oura_df
        """)
        n = con.execute("SELECT COUNT(*) FROM raw.oura_sleep").fetchone()[0]
        manifest.record(con, "oura_sleep", [(Path("oura_api"), n)])

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
