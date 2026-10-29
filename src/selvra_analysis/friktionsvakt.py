"""Friktionsvakten: upptäcker friktion ur systemets egna beteendejournaler.

Ett brev har inga rage clicks. Selvras friktion är andra signaler — och alla
finns redan loggade: en grind som stått på samma STOPP i veckor, ett framsteg
som inte växer trots att dagarna går, ett rör som slutat leverera. Vakten läser
dem, beskriver friktionen och föreslår vad som kan minska den.

Två konstitutionella regler skiljer den från FullStory och Mouseflow:

1. **Fynden går till BYGGAREN, aldrig till användaren.** Rapporten
   (data/rapporter/friktion.md) är Carls; ingenting pushas, ingen nudge når
   någons telefon. Att larma användaren om friktion vore att lägga friktion på
   friktionen.
2. **Vakten beskriver och föreslår — den åtgärdar aldrig automatiskt.**
   Domstolsprincipen: generatorn (vakten) föreslår, domaren (Carl) beslutar.
   Varje fynd är en hypotes om var upplevelsen skaver, inte en order.

Tystnad är standard: ser vakten ingen friktion skriver den det, kort.
Körs sist i morgonkörningen, efter självstudien.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

GRINDLOGG = Path("data/grindlogg.jsonl")
RORLOGG = Path("data/rorlogg.jsonl")
UT = Path("data/rapporter/friktion.md")

STOPP_STRECK_DAGAR = 10        # samma STOPP så länge = personen kommer inte vidare
ROR_TYST_DAGAR = 3            # ett rör utan hämtning så länge = pipeline-friktion


def _rader(fil: Path) -> list[dict]:
    if not fil.exists():
        return []
    return [json.loads(r) for r in fil.read_text().splitlines() if r.strip()]


def fastnade_grindar(grindlogg: list[dict], idag: date) -> list[str]:
    """En förslagsgrind som stått på STOPP med samma skäl länge — personen
    bygger underlag men kommer inte vidare mot en dom. Friktion i väntan."""
    per_person: dict[str, list[dict]] = defaultdict(list)
    for r in grindlogg:
        per_person[r["person"]].append(r)
    fynd = []
    for person, rader in per_person.items():
        rader.sort(key=lambda r: r["datum"])
        if rader[-1]["dom"] != "STOPP":
            continue
        skal = (rader[-1].get("skal") or "").split(";")[0][:70]
        streck = 0
        for r in reversed(rader):
            if r["dom"] == "STOPP":
                streck += 1
            else:
                break
        forsta = datetime.fromisoformat(rader[-streck]["datum"]).date()
        dagar = (idag - forsta).days
        if dagar >= STOPP_STRECK_DAGAR:
            fynd.append(f"[{person}] förslagsgrinden har stått på STOPP i {dagar} dagar: "
                        f"”{skal}”. Friktion: personen kommer inte vidare mot en dom. "
                        "Minska? Sänk design.par, eller se om underlaget faktiskt växer.")
    return fynd


def framsteg_stall(grindlogg: list[dict]) -> list[str]:
    """Väntat antal kompletta par som inte växt över de senaste loggade dagarna
    — klockan bärs kanske inte, eller studien är feldimensionerad."""
    per_person: dict[str, list[tuple]] = defaultdict(list)
    for r in grindlogg:
        m = re.search(r"\((\d+) par\)", r.get("skal") or "") or \
            re.search(r"kompletta par (\d+)", r.get("skal") or "")
        if m:
            per_person[r["person"]].append((r["datum"], int(m.group(1))))
    fynd = []
    for person, punkter in per_person.items():
        punkter.sort()
        if len(punkter) >= STOPP_STRECK_DAGAR and len({p for _, p in punkter[-STOPP_STRECK_DAGAR:]}) == 1:
            par = punkter[-1][1]
            fynd.append(f"[{person}] väntade par står stilla på {par} över "
                        f"{STOPP_STRECK_DAGAR} dagar. Friktion: dagarna går men domen "
                        "närmar sig inte. Minska? Bärs klockan varje natt?")
    return fynd


def tysta_ror(rorlogg: list[dict], idag: date) -> list[str]:
    """Ett rör som slutat leverera — data når inte personens brev längre."""
    senast: dict[tuple, str] = {}
    for r in rorlogg:
        senast[(r.get("kalla"), r.get("person"))] = r["tid"][:10]
    fynd = []
    for (kalla, person), dag in senast.items():
        tyst = (idag - datetime.fromisoformat(dag).date()).days
        if tyst >= ROR_TYST_DAGAR:
            fynd.append(f"[{person}] röret {kalla} har inte hämtat på {tyst} dagar "
                        "(senast " + dag + "). Friktion: brevet tunnas ut tyst. "
                        "Minska? Kolla synkvakten och tokenens giltighet.")
    return fynd


def rapport(idag: date | None = None) -> str:
    idag = idag or date.today()
    grind = _rader(GRINDLOGG)
    ror = _rader(RORLOGG)
    fynd = fastnade_grindar(grind, idag) + framsteg_stall(grind) + tysta_ror(ror, idag)
    rader = ["# Friktionsvakten (för byggaren, aldrig för användaren)", ""]
    if not fynd:
        rader.append("Ingen friktion över tröskel i dag. Systemet skaver inte där "
                     "journalerna ser.")
    else:
        rader.append("Varje rad är en hypotes om var upplevelsen skaver — att väga, "
                     "inte att lyda:")
        rader.append("")
        rader += [f"- {f}" for f in fynd]
    return "\n".join(rader) + "\n"


def main() -> int:
    UT.parent.mkdir(parents=True, exist_ok=True)
    UT.write_text(rapport())
    print(f"skrev {UT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
