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
import getpass
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


def person_paths(person: str) -> dict[str, Path]:
    """Each person's data lives apart: data/personer/<namn>/ (gitignored like all of data/)."""
    base = Path("data/personer") / person
    return {"token": base / "garmin", "db": base / "selvra.duckdb", "snapshots": base / "snapshots"}


def interactive_login(token_dir: Path) -> None:
    """Log in once with the person present; only Garmin's token is saved, never the password.

    The token lets later runs fetch data without the password (it lasts about a year).
    """
    print("Logga in med Garmin Connect-kontot. Lösenordet sparas inte; bara Garmins nyckel.")
    email = input("E-post: ").strip()
    password = getpass.getpass("Lösenord: ")
    garmin = Garmin(email=email, password=password, prompt_mfa=lambda: input("Kod från Garmin (sms/mejl): ").strip())
    token_dir.mkdir(parents=True, exist_ok=True)
    garmin.login(str(token_dir))  # saves the token to token_dir itself
    name = garmin.get_full_name() if hasattr(garmin, "get_full_name") else ""
    print(f"Inloggad{f' som {name}' if name else ''}. Nyckeln ligger i {token_dir}.")


def diagnose(garmin: Garmin, day: str) -> None:
    """Print what each endpoint returns for one day: the error, or the shape (keys, no values)."""
    print(f"Inloggad som: {garmin.get_full_name()!r}")
    for name in ("get_sleep_data", "get_user_summary", "get_hrv_data", "get_stats"):
        try:
            res = getattr(garmin, name)(day)
        except Exception as err:  # noqa: BLE001  (diagnosis: show every failure as it is)
            print(f"{name}: FEL {type(err).__name__}: {str(err)[:200]}")
            continue
        if isinstance(res, dict):
            inner = {k: sorted(v)[:12] for k, v in res.items() if isinstance(v, dict)}
            print(f"{name}: dict, nycklar {sorted(res)[:25]}")
            for k, v in inner.items():
                print(f"    {k}: {v}")
        else:
            print(f"{name}: {type(res).__name__} {'tom' if not res else f'längd {len(res)}'}")


def diagnose_fields(garmin: Garmin, days: int) -> None:
    """For each recent day: which of the fields the ingest reads have a value (ja/nej, no values)."""
    print("\nFält som inläsningen läser, per dag (ja = har värde):")
    for i in range(days, 0, -1):
        d = str(date.today() - timedelta(days=i))
        got = {}
        for name in ("get_sleep_data", "get_user_summary", "get_hrv_data"):
            try:
                got[name] = getattr(garmin, name)(d)
            except Exception as err:  # noqa: BLE001  (diagnosis)
                got[name] = None
                print(f"  {d} {name}: FEL {type(err).__name__}")
        row = parse_day(d, got["get_sleep_data"], got["get_user_summary"], got["get_hrv_data"])
        flags = " ".join(f"{k}={'ja' if v is not None else 'nej'}" for k, v in row.items() if k != "reading_date")
        print(f"  {d}: {flags}")


def _login_with_token(token_dir: Path) -> Garmin:
    garmin = Garmin()
    garmin.login(str(token_dir))
    return garmin


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


def _connect(token_dir: Path | None) -> Garmin | None:
    """A person's saved token if there is one, otherwise GARMIN_EMAIL/GARMIN_PASSWORD from .env."""
    try:
        if token_dir is not None and token_dir.exists():
            return _login_with_token(token_dir)
        _load_dotenv()
        email, password = os.environ.get("GARMIN_EMAIL"), os.environ.get("GARMIN_PASSWORD")
        if not email or not password:
            print("Ingen Garmin-nyckel och inget GARMIN_EMAIL/GARMIN_PASSWORD; hoppar över Garmin.", file=sys.stderr)
            return None
        return _login(email, password)
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as err:
        raise SystemExit(f"Garmin-inloggning misslyckades: {err}") from err


def load(db_path: Path, days_back: int = 90, token_dir: Path | None = None, snapshots: Path = SNAPSHOTS) -> int:
    garmin = _connect(token_dir)
    if garmin is None:
        return 0

    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Hämtar Garmin-data {start} → {end} (en dag per anrop, tar en stund)...", file=sys.stderr)
    df = _fetch(garmin, start, end)
    if df.empty:
        print("Inga Garmin-data hittades.", file=sys.stderr)
        return 0

    text = df.to_csv(index=False)
    digest = hashlib.sha256(text.encode()).hexdigest()
    snapshots.mkdir(parents=True, exist_ok=True)
    (snapshots / f"garmin_{digest[:16]}.csv").write_text(text)
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
    parser.add_argument("--db", type=Path, default=None, help="default: data/selvra.duckdb, eller personens")
    parser.add_argument("--dagar", type=int, default=90, help="Antal dagar bakåt (default: 90)")
    parser.add_argument("--person", help="en annan person än du: data i data/personer/<namn>/")
    parser.add_argument("--logga-in", action="store_true", help="logga in personen en gång (kräver --person)")
    parser.add_argument("--felsok", action="store_true", help="visa vad Garmin svarar för gårdagen (kräver --person)")
    args = parser.parse_args(argv)
    if args.person:
        paths = person_paths(args.person)
        if args.logga_in:
            interactive_login(paths["token"])
            return
        if args.felsok:
            garmin = _login_with_token(paths["token"])
            diagnose(garmin, str(date.today() - timedelta(days=1)))
            diagnose_fields(garmin, 7)
            return
        paths["db"].parent.mkdir(parents=True, exist_ok=True)
        load(args.db or paths["db"], args.dagar, paths["token"], paths["snapshots"])
        return
    if args.logga_in:
        raise SystemExit("--logga-in kräver --person NAMN")
    load(args.db or DB_DEFAULT, args.dagar)


if __name__ == "__main__":
    main()
