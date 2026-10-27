"""Hämta sömn-, puls- och stegdata från Garmin Connect och ladda in i DuckDB.

Kräver GARMIN_EMAIL och GARMIN_PASSWORD i .env (skrivs aldrig ut). Första inloggningen
sparar en token i ~/.garminconnect så lösenordet bara behövs en gång; vid MFA-fråga
körs kommandot interaktivt första gången.

Laddar per dygn: sleep_score, sömnlängd och -faser, HRV (nattens snitt, ms),
vilopuls och steg. readiness_score och sleep_efficiency_pct lämnas null —
Garmin har ingen motsvarighet till Ouras mått, och ett annat mått under samma
namn vore fel.

Usage:
    uv run python -m selvra_analysis.ingest_garmin --db data/selvra.duckdb
    make build-live   # kör automatiskt om GARMIN_EMAIL finns
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from selvra_analysis.ingest_clarity import WEARABLE_COLUMNS, ensure_raw_tables

SNAPSHOTS = Path("data/snapshots")
DB_DEFAULT = Path("data/selvra.duckdb")
TOKEN_DIR = Path.home() / ".garminconnect"
FETCH_ERRORS = (GarminConnectConnectionError, GarminConnectTooManyRequestsError, KeyError, TypeError)


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
        if key in ("GARMIN_EMAIL", "GARMIN_PASSWORD") and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


def parse_day(day: str, sleep: dict | None, summary: dict | None, hrv: dict | None) -> dict:
    """One day's row from the three Garmin responses, each value from the endpoint that holds it.

    Garmin's daily resting heart rate is the lowest 30-minute average of the day, not the
    lowest value during sleep; the registry entry for hr_lowest_bpm says so. readiness_score
    and sleep_efficiency_pct stay null: Garmin has no equivalent of Oura's measures.
    """
    dto = (sleep or {}).get("dailySleepDTO") or {}
    scores = dto.get("sleepScores") or {}
    hrv_summary = (hrv or {}).get("hrvSummary") or {}
    return {
        "reading_date": day,
        "sleep_score": (scores.get("overall") or {}).get("value"),
        "readiness_score": None,
        "total_sleep_seconds": dto.get("sleepTimeSeconds"),
        "deep_sleep_seconds": dto.get("deepSleepSeconds"),
        "rem_sleep_seconds": dto.get("remSleepSeconds"),
        "sleep_efficiency_pct": None,
        "hrv_avg_ms": hrv_summary.get("lastNightAvg"),
        "hr_lowest_bpm": (summary or {}).get("restingHeartRate"),
        "steps": (summary or {}).get("totalSteps"),
    }


def to_frame(rows: list[dict]) -> pd.DataFrame:
    """Rows with at least one value besides the date; empty frame keeps the columns."""
    kept = [r for r in rows if any(v is not None for k, v in r.items() if k != "reading_date")]
    return pd.DataFrame(kept, columns=WEARABLE_COLUMNS)


def _login(email: str, password: str) -> Garmin:
    """login(tokenstore) sköter hela flödet: provar cachade tokens, faller tillbaka
    på e-post/lösenord och sparar nya tokens till sökvägen själv."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    garmin = Garmin(email=email, password=password)
    garmin.login(str(TOKEN_DIR))
    return garmin


def _fetch(garmin: Garmin, start: date, end: date) -> pd.DataFrame:
    rows = []
    day = start
    while day <= end:
        d = str(day)
        sleep = summary = hrv = None
        with contextlib.suppress(*FETCH_ERRORS):
            sleep = garmin.get_sleep_data(d)
        with contextlib.suppress(*FETCH_ERRORS):
            summary = garmin.get_user_summary(d)
        with contextlib.suppress(*FETCH_ERRORS):
            hrv = garmin.get_hrv_data(d)
        rows.append(parse_day(d, sleep, summary, hrv))
        day += timedelta(days=1)
    return to_frame(rows)


def load(db_path: Path, days_back: int = 90) -> int:
    _load_dotenv()
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("GARMIN_EMAIL/GARMIN_PASSWORD saknas — hoppar över Garmin-inläsning.", file=sys.stderr)
        return 0

    try:
        garmin = _login(email, password)
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as err:
        raise SystemExit(f"Garmin-inloggning misslyckades: {err}") from err

    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Hämtar Garmin-data {start} → {end} (en dag per anrop, tar en stund)...", file=sys.stderr)
    df = _fetch(garmin, start, end)
    if df.empty:
        print("Inga Garmin-data hittades.", file=sys.stderr)
        return 0

    text = df.to_csv(index=False)
    digest = hashlib.sha256(text.encode()).hexdigest()
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    (SNAPSHOTS / f"garmin_{digest[:16]}.csv").write_text(text)
    with duckdb.connect(str(db_path)) as con:
        ensure_raw_tables(con)
        con.register("garmin_df", df)
        cols = ", ".join(WEARABLE_COLUMNS)
        con.execute("delete from raw.garmin_daily")
        con.execute(f"insert into raw.garmin_daily ({cols}) select {cols} from garmin_df")  # noqa: S608
        n = con.execute("select count(*) from raw.garmin_daily").fetchone()[0]
        con.execute("delete from raw.source_files where kind = 'garmin'")
        con.execute("insert into raw.source_files values ('garmin', ?, ?, ?, ?)",
                    [digest, len(text.encode()), n, datetime.now(UTC).isoformat(timespec="seconds")])

    print(f"Laddade {n} Garmin-dagar.", file=sys.stderr)
    return n


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    parser.add_argument("--dagar", type=int, default=90, help="Antal dagar bakåt (default: 90)")
    args = parser.parse_args(argv)
    load(args.db, args.dagar)


if __name__ == "__main__":
    main()
