"""Append a single event to the personal event log (data/raw/handelser.csv).

Usage:
    uv run python -m selvra_analysis.log_event --start 2026-10-24 --typ traning --notering "löpning 5 km"
    uv run python -m selvra_analysis.log_event --start 2026-10-22 --slut 2026-10-23 --typ sjukdom
    uv run python -m selvra_analysis.log_event --start 2026-10-22 --typ sensorbyte

Valid types:
    sjukdom, sensorbyte, alkohol, traning, resa, stress,
    menstruation, medicinandring, annat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from selvra_analysis.ingest_events import EVENT_TYPES

HEADER = ["start", "slut", "typ", "notering"]
DEFAULT_LOG = Path("data/raw/handelser.csv")


def _parse_date(value: str, field: str) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise SystemExit(f"Ogiltigt datum för --{field}: {value!r}")
    return value.strip()


def append_event(
    log_path: Path,
    start: str,
    typ: str,
    slut: str = "",
    notering: str = "",
) -> None:
    if typ not in EVENT_TYPES:
        raise SystemExit(
            f"Okänd typ {typ!r}.\nTillåtna: {', '.join(sorted(EVENT_TYPES))}"
        )
    _parse_date(start, "start")
    if slut:
        _parse_date(slut, "slut")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_row = f"{start},{slut},{typ},{notering}\n"

    if not log_path.exists():
        log_path.write_text(",".join(HEADER) + "\n" + new_row)
        print(f"Skapade {log_path} och lade till: {new_row.strip()}")
    else:
        with log_path.open("a") as f:
            f.write(new_row)
        print(f"La till i {log_path}: {new_row.strip()}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Logga en händelse i händelseloggen.")
    parser.add_argument("--start", required=True, help="Startdatum, t.ex. 2026-10-24 eller 2026-10-24 21:00")
    parser.add_argument("--slut", default="", help="Slutdatum (valfritt, för fleradagshändelser)")
    parser.add_argument(
        "--typ",
        required=True,
        choices=sorted(EVENT_TYPES),
        metavar="TYP",
        help=f"Händelsetyp: {', '.join(sorted(EVENT_TYPES))}",
    )
    parser.add_argument("--notering", default="", help="Fritext-notering (valfritt)")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help=f"Sökväg till händelseloggen (default: {DEFAULT_LOG})")
    args = parser.parse_args(argv)

    append_event(
        log_path=args.log,
        start=args.start,
        typ=args.typ,
        slut=args.slut,
        notering=args.notering,
    )


if __name__ == "__main__":
    main()
