"""Synkvakten: en notis när klockan varit tyst för länge — aldrig oftare än en om dagen.

Synken ägs av Garmins app i telefonen och kan inte tvingas härifrån. Det vakten kan
göra är att upptäcka tystnaden via molnets senaste uppladdningstid och be personen
öppna Garmin Connect en stund. Operativ påminnelse, inte engagemang: tröskeln är
generös (12 h) och det kommer högst en per dygn.

Vakten täcker alla personer automatiskt: varje mapp under data/personer/ med
en Garmin-nyckel OCH en kopplad telefon (push.json) vaktas. Tröskeln kan
sättas per person i person.yml (synk_troskel_timmar, default 12) — aldrig
sänkt i smyg centralt, för "så fort" i bokstavlig mening vore brus: telefoner
sover i timmar helt normalt.

Usage:
    uv run python -m selvra_analysis.synkvakt                      # alla personer
    uv run python -m selvra_analysis.synkvakt testare-1            # en person
    uv run python -m selvra_analysis.synkvakt testare-1 --visa     # bara status
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from selvra_analysis.ingest_garmin import _login_with_token, person_paths
from selvra_analysis.morgonpush import payload, send

TROSKEL_TIMMAR = 12
PERSONER = Path("data/personer")


def troskel_for(person: str) -> int:
    """Tröskeln ur person.yml (synk_troskel_timmar), annars default."""
    konf = person_paths(person)["dir"] / "person.yml"
    if konf.exists():
        v = (yaml.safe_load(konf.read_text()) or {}).get("synk_troskel_timmar")
        if isinstance(v, int) and v > 0:
            return v
    return TROSKEL_TIMMAR


def vaktbara() -> list[str]:
    """Alla personer med Garmin-nyckel och kopplad telefon — vakten följer
    infran, inte en lista som någon måste minnas att uppdatera."""
    if not PERSONER.exists():
        return []
    return sorted(m.name for m in PERSONER.iterdir()
                  if (m / "garmin").exists() and (m / "push.json").exists())


def kolla_alla(skicka: bool = True) -> int:
    personer = vaktbara()
    if not personer:
        print("inga vaktbara personer (kräver garmin-nyckel + kopplad telefon)", file=sys.stderr)
        return 0
    varsta = 0
    for person in personer:
        print(f"[{person}]", file=sys.stderr)
        varsta = max(varsta, kolla(person, skicka=skicka))
    return varsta


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
    if alder < timedelta(hours=troskel_for(person)):
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
    parser.add_argument("person", nargs="?", default=None,
                        help="en person; utelämnad = alla vaktbara")
    parser.add_argument("--visa", action="store_true", help="bara status, skicka inget")
    args = parser.parse_args(argv)
    if args.person:
        return kolla(args.person, skicka=not args.visa)
    return kolla_alla(skicka=not args.visa)


if __name__ == "__main__":
    sys.exit(main())
