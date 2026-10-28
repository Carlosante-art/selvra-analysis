"""Synkvakten: en notis när klockan varit tyst för länge — aldrig oftare än en om dagen.

Synken ägs av Garmins app i telefonen och kan inte tvingas härifrån. Det vakten kan
göra är att upptäcka tystnaden via molnets senaste uppladdningstid och be personen
öppna Garmin Connect en stund. Operativ påminnelse, inte engagemang: tröskeln är
generös (12 h) och det kommer högst en per dygn.

Usage:
    uv run python -m selvra_analysis.synkvakt pappa            # kolla, skicka vid behov
    uv run python -m selvra_analysis.synkvakt pappa --visa     # bara status
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from selvra_analysis.ingest_garmin import _login_with_token, person_paths
from selvra_analysis.morgonpush import payload, send

TROSKEL_TIMMAR = 12


def senaste_synk(person: str) -> datetime | None:
    g = _login_with_token(person_paths(person)["token"])
    ts = (g.get_device_last_used() or {}).get("lastUsedDeviceUploadTime")
    return datetime.fromtimestamp(ts / 1000) if ts else None


def _redan_pamind_idag(markor: Path) -> bool:
    return markor.exists() and markor.read_text().strip() == str(date.today())


def kolla(person: str, skicka: bool = True) -> int:
    synk = senaste_synk(person)
    if synk is None:
        print("ingen uppladdning registrerad alls", file=sys.stderr)
        return 1
    alder = datetime.now() - synk
    print(f"senaste synk: {synk:%Y-%m-%d %H:%M} ({alder.total_seconds() / 3600:.1f} h sedan)",
          file=sys.stderr)
    if alder < timedelta(hours=TROSKEL_TIMMAR):
        return 0

    markor = person_paths(person)["dir"] / "synkvakt.datum"
    if _redan_pamind_idag(markor):
        print("redan påmind i dag; tyst", file=sys.stderr)
        return 0
    if not skicka:
        print("skulle ha skickat påminnelse (kör utan --visa för att skicka)", file=sys.stderr)
        return 0

    text = (f"Klockan har inte synkat sedan {synk:%H:%M} "
            f"({'i går ' if synk.date() < date.today() else ''}{synk:%d/%m}).\n\n"
            "Öppna Garmin Connect-appen en liten stund med klockan på armen, "
            "så kommer dagens mätningar med. Klockan sparar allt lokalt — inget är borta.")
    data = payload("Selvra: klockan har inte synkat", text, date.today())
    data["kort"] = f"Klockan tyst sedan {synk:%H:%M} — öppna Garmin Connect en stund."
    send(person, data)
    markor.write_text(str(date.today()))
    print("påminnelse skickad", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("person")
    parser.add_argument("--visa", action="store_true", help="bara status, skicka inget")
    args = parser.parse_args(argv)
    return kolla(args.person, skicka=not args.visa)


if __name__ == "__main__":
    sys.exit(main())
