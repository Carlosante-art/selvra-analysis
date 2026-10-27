"""Hämta glukos och behandlingar från en Nightscout-instans och ladda in i DuckDB.

Nightscout är DIY-communityts öppna plattform: användarens egen server med
CGM-värden och, för pump/loop-användare, insulin och kolhydrater (treatments).

Kräver NIGHTSCOUT_URL i .env (t.ex. https://mitt-ns.example.com). Skyddade
instanser behöver NIGHTSCOUT_TOKEN (en åtkomsttoken med läsrätt, skapad i
Nightscouts admin). Saknas URL hoppas inläsningen över.

Laddar:
  raw.nightscout_entries     — sgv-värden (mg/dL) med exakta instanter
  raw.nightscout_treatments  — bolusinsulin, kolhydrater, temp-basaler

Usage:
    uv run python -m selvra_analysis.ingest_nightscout --db data/selvra.duckdb
    make build-live   # kör automatiskt om NIGHTSCOUT_URL finns
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import pandas as pd

from selvra_analysis.ingest_clarity import ensure_raw_tables

SNAPSHOTS = Path("data/snapshots")
DB_DEFAULT = Path("data/selvra.duckdb")
ENTRY_COLUMNS = ["reading_at", "value_mgdl", "trend", "device"]
TREATMENT_COLUMNS = ["treatment_at", "event_type", "insulin_units", "carbs_g",
                     "duration_min", "basal_rate"]
MAX_ROWS = 100_000


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
        if key in ("NIGHTSCOUT_URL", "NIGHTSCOUT_TOKEN") and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


def _get(base: str, token: str | None, path: str, params: dict) -> list[dict]:
    if token:
        params = {**params, "token": token}
    resp = httpx.get(f"{base.rstrip('/')}{path}", params=params, timeout=60,
                     headers={"Accept": "application/json"})
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def parse_entries(items: list[dict]) -> pd.DataFrame:
    """sgv-poster till en rad per avläsning. Andra typer (mbg, cal) hoppas över."""
    rows = []
    for e in items:
        if e.get("type", "sgv") != "sgv" or e.get("sgv") is None or not e.get("date"):
            continue
        rows.append({
            "reading_at": datetime.fromtimestamp(e["date"] / 1000, tz=UTC).isoformat(),
            "value_mgdl": int(e["sgv"]),
            "trend": e.get("direction"),
            "device": e.get("device"),
        })
    return pd.DataFrame(rows, columns=ENTRY_COLUMNS)


def parse_treatments(items: list[dict]) -> pd.DataFrame:
    """Behandlingar med substans: insulin, kolhydrater eller en temp-basal.
    Rena anteckningar och sensorbyten utan värden hoppas över."""
    rows = []
    for t in items:
        insulin = t.get("insulin")
        carbs = t.get("carbs")
        rate = t.get("absolute", t.get("rate"))
        is_basal = t.get("eventType") == "Temp Basal"
        if insulin is None and carbs is None and not is_basal:
            continue
        when = t.get("created_at") or t.get("timestamp")
        if not when:
            continue
        rows.append({
            "treatment_at": when,
            "event_type": t.get("eventType", "okänd"),
            "insulin_units": float(insulin) if insulin is not None else None,
            "carbs_g": float(carbs) if carbs is not None else None,
            "duration_min": float(t["duration"]) if t.get("duration") is not None else None,
            "basal_rate": float(rate) if is_basal and rate is not None else None,
        })
    return pd.DataFrame(rows, columns=TREATMENT_COLUMNS)


def _fetch(base: str, token: str | None, start: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    entries = _get(base, token, "/api/v1/entries/sgv.json",
                   {"count": MAX_ROWS, "find[date][$gte]": int(start.timestamp() * 1000)})
    treatments = _get(base, token, "/api/v1/treatments.json",
                      {"count": MAX_ROWS,
                       "find[created_at][$gte]": start.isoformat()})
    return parse_entries(entries), parse_treatments(treatments)


def _snapshot_and_load(con, df: pd.DataFrame, table: str, kind: str, columns: list[str]) -> int:
    text = df.to_csv(index=False)
    digest = hashlib.sha256(text.encode()).hexdigest()
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    (SNAPSHOTS / f"{kind}_{digest[:16]}.csv").write_text(text)
    con.register("ns_df", df)
    cols = ", ".join(columns)
    con.execute(f"delete from raw.{table}")  # noqa: S608
    con.execute(f"insert into raw.{table} ({cols}) select {cols} from ns_df")  # noqa: S608
    n = con.execute(f"select count(*) from raw.{table}").fetchone()[0]  # noqa: S608
    con.execute("delete from raw.source_files where kind = ?", [kind])
    con.execute("insert into raw.source_files values (?, ?, ?, ?, ?)",
                [kind, digest, len(text.encode()), n,
                 datetime.now(UTC).isoformat(timespec="seconds")])
    return n


def load(db_path: Path, days_back: int = 90) -> int:
    _load_dotenv()
    base = os.environ.get("NIGHTSCOUT_URL")
    if not base:
        print("NIGHTSCOUT_URL saknas — hoppar över Nightscout-inläsning.", file=sys.stderr)
        return 0
    token = os.environ.get("NIGHTSCOUT_TOKEN")

    start = datetime.now(UTC) - timedelta(days=days_back)
    print(f"Hämtar Nightscout-data från {start.date()}...", file=sys.stderr)
    entries, treatments = _fetch(base, token, start)

    if entries.empty and treatments.empty:
        print("Inga Nightscout-data hittades.", file=sys.stderr)
        return 0

    with duckdb.connect(str(db_path)) as con:
        ensure_raw_tables(con)
        n_e = _snapshot_and_load(con, entries, "nightscout_entries",
                                 "nightscout_entries", ENTRY_COLUMNS)
        n_t = _snapshot_and_load(con, treatments, "nightscout_treatments",
                                 "nightscout_treatments", TREATMENT_COLUMNS)

    print(f"Laddade {n_e} avläsningar och {n_t} behandlingar från Nightscout.", file=sys.stderr)
    return n_e + n_t


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    parser.add_argument("--dagar", type=int, default=90, help="Antal dagar bakåt (default: 90)")
    args = parser.parse_args(argv)
    load(args.db, args.dagar)


if __name__ == "__main__":
    main()
