"""Importera händelser från en iCal-fil (.ics) till händelseloggen.

Mappar kalenderhändelse-titlar till händelsetyper via nyckelord.
Exportera din kalender som .ics från Google Calendar, Apple Calendar
eller Outlook och kör detta script.

Usage:
    uv run python -m selvra_analysis.import_kalender ~/Downloads/kalender.ics
    make import-kalender fil=~/Downloads/kalender.ics
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from selvra_analysis.log_event import DEFAULT_LOG, append_event

# Nyckelordsmappning: händelsetyp → sökord (lowercase, delsträng-match)
NYCKELORD: dict[str, list[str]] = {
    "traning":        ["träning", "traning", "gym", "löpning", "lopning", "cykling",
                       "simning", "yoga", "crossfit", "workout", "run", "bike", "swim",
                       "promenad", "walk", "hike", "vandring"],
    "stress":         ["stress", "möte", "deadline", "presentation", "intervju"],
    "sjukdom":        ["sjuk", "feber", "förkylning", "förkylning", "virus", "ill",
                       "sick", "covid", "magsjuka", "influensa"],
    "alkohol":        ["alkohol", "vin", "öl", "whisky", "drink", "pub", "bar",
                       "middag", "dinner", "sällskap"],
    "resa":           ["resa", "flyg", "tåg", "hotell", "semester", "trip", "travel",
                       "flight", "train", "hotel"],
    "menstruation":   ["mens", "menstruation", "period"],
    "medicinandring": ["insulin", "dos", "basal", "medicin", "läkemedel"],
    "sensorbyte":     ["sensor", "cgm", "dexcom", "libre"],
}


def _parse_ics_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _classify(title: str) -> str | None:
    low = title.lower()
    for typ, words in NYCKELORD.items():
        if any(w in low for w in words):
            return typ
    return None


def parse_ics(path: Path) -> list[dict]:
    text = path.read_text(errors="replace")
    events = []
    current: dict | None = None

    for line in text.splitlines():
        if line.startswith("BEGIN:VEVENT"):
            current = {}
        elif line.startswith("END:VEVENT") and current is not None:
            events.append(current)
            current = None
        elif current is not None:
            if line.startswith("SUMMARY"):
                current["title"] = line.split(":", 1)[-1].strip()
            elif line.startswith("DTSTART"):
                current["start"] = _parse_ics_date(line.split(":", 1)[-1])
            elif line.startswith("DTEND"):
                current["end"] = _parse_ics_date(line.split(":", 1)[-1])

    return [e for e in events if e.get("title") and e.get("start")]


def import_from_ics(
    ics_path: Path,
    log_path: Path,
    min_date: date | None = None,
    max_date: date | None = None,
    dry_run: bool = False,
) -> list[dict]:
    raw_events = parse_ics(ics_path)
    imported = []

    for ev in raw_events:
        start: date = ev["start"]
        end: date = ev.get("end") or start
        title: str = ev["title"]

        if min_date and start < min_date:
            continue
        if max_date and start > max_date:
            continue

        typ = _classify(title)
        if not typ:
            continue

        # Klipp bort tid-delen och håll end på senaste dagen (DTEND i iCal är exklusiv)
        slut = str(end - __import__("datetime").timedelta(days=1)) if end > start else ""

        imported.append({"start": str(start), "slut": slut, "typ": typ, "notering": title[:60]})
        if not dry_run:
            append_event(log_path=log_path, start=str(start), typ=typ,
                        slut=slut, notering=title[:60])

    return imported


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fil", type=Path, help="Sökväg till .ics-filen")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--fran", default=None, help="Importera från och med ÅÅÅÅ-MM-DD")
    parser.add_argument("--till", default=None, help="Importera till och med ÅÅÅÅ-MM-DD")
    parser.add_argument("--forhandsgranska", action="store_true",
                        help="Visa vad som skulle importeras utan att skriva")
    args = parser.parse_args(argv)

    if not args.fil.exists():
        raise SystemExit(f"Filen hittades inte: {args.fil}")

    min_date = date.fromisoformat(args.fran) if args.fran else None
    max_date = date.fromisoformat(args.till) if args.till else None

    events = import_from_ics(
        ics_path=args.fil,
        log_path=args.log,
        min_date=min_date,
        max_date=max_date,
        dry_run=args.forhandsgranska,
    )

    if not events:
        print("Inga matchande händelser hittades.")
        return

    action = "Skulle importera" if args.forhandsgranska else "Importerade"
    print(f"{action} {len(events)} händelse(r):")
    for ev in events:
        slut_str = f" → {ev['slut']}" if ev["slut"] else ""
        print(f"  {ev['start']}{slut_str}  {ev['typ']:15}  {ev['notering']}")

    if args.forhandsgranska:
        print("\nKör utan --forhandsgranska för att skriva till loggen.")


if __name__ == "__main__":
    main()
