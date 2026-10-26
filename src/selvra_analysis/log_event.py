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
import csv
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
    row = [start.strip(), slut.strip(), typ, notering.strip()]
    created = not log_path.exists()
    # Start on a new line even if the file was edited by hand without a final newline.
    needs_newline = not created and log_path.read_bytes()[-1:] not in (b"\n", b"")
    with log_path.open("a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        writer = csv.writer(f, lineterminator="\n")  # quotes notes with commas or quotes
        if created:
            writer.writerow(HEADER)
        writer.writerow(row)
    print(f"{'Skapade' if created else 'La till i'} {log_path}: {', '.join(x for x in row if x)}")


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
