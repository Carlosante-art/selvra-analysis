"""Självstudien: Selvra som forskningsobjekt åt sig själv.

Domstolsprincipens meta-varv (MODELLEN): systemet ackumulerar journaler om
sitt eget arbete — domar, grindbeslut, rörlogg — och de förtjänar samma
mönsterletning som människornas data. Tre frågor varje körning:

1. **Rör-drift**: har något rör bytt form sedan förra hämtningen? Rörloggen
   jämförs med sig själv — fältlista, bibliotek, enhet, firmware. En ändring
   är ett seriebrotts-kandidat, inte ett fel; den ska SES, inte gissas.
2. **Grindarnas beteende**: hur dömer förslagsgrinden över tid, och av vilka
   skäl? Ett skäl som dominerar länge är en hypotes om granskaren själv
   (styrka-rättningen hittades manuellt ur exakt det mönstret).
3. **MODELLEN:s mått, räknade ur journaler**: domar i registret (nejen räknas),
   andel giltiga datadagar senaste 30. Prosa får inte bära måtten — det ska
   journalerna göra.

Beskrivande rapport till data/rapporter/sjalvstudie.md (gitignorerad), aldrig
push — tystnad före brus gäller även metalagret. Körs sist i morgonkörningen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

RORLOGG = Path("data/rorlogg.jsonl")
GRINDLOGG = Path("data/grindlogg.jsonl")
DB = Path("data/selvra.duckdb")
UT = Path("data/rapporter/sjalvstudie.md")
STUDIEMAPPAR = [Path("studies"), Path("data/personer")]
ROR_FORM = ("falt", "bibliotek", "enhet", "firmware")


def _rader(fil: Path) -> list[dict]:
    if not fil.exists():
        return []
    return [json.loads(r) for r in fil.read_text().splitlines() if r.strip()]


def ror_drift(rader: list[dict]) -> list[str]:
    """Formändringar mellan på varandra följande hämtningar per (kalla, person)."""
    senast: dict[tuple, dict] = {}
    fynd = []
    for r in rader:
        nyckel = (r.get("kalla"), r.get("person"))
        forra = senast.get(nyckel)
        if forra:
            for falt in ROR_FORM:
                if r.get(falt) != forra.get(falt):
                    fynd.append(f"{r['tid'][:10]} {nyckel[0]}/{nyckel[1]}: "
                                f"{falt} ändrades {forra.get(falt)!r} → {r.get(falt)!r} "
                                "— seriebrotts-kandidat")
        senast[nyckel] = r
    return fynd


def grindmonster(rader: list[dict]) -> list[str]:
    """Domfördelning och dominerande stoppskäl, per person."""
    ut = []
    personer = sorted({r["person"] for r in rader})
    for person in personer:
        egna = [r for r in rader if r["person"] == person]
        domar: dict[str, int] = {}
        skal: dict[str, int] = {}
        for r in egna:
            domar[r["dom"]] = domar.get(r["dom"], 0) + 1
            if r.get("skal"):
                kort = r["skal"].split(":")[0][:60]
                skal[kort] = skal.get(kort, 0) + 1
        fordelning = ", ".join(f"{k} {v}" for k, v in sorted(domar.items()))
        ut.append(f"{person}: {len(egna)} prövningar ({fordelning})")
        if skal:
            vanligast = max(skal, key=skal.get)  # type: ignore[arg-type]
            ut.append(f"  vanligaste stoppskäl: {vanligast} ({skal[vanligast]} ggr)"
                      + (" — dominerar länge? hypotes om granskaren, inte bara om datan"
                         if skal[vanligast] >= 14 else ""))
    return ut


def domregister() -> list[str]:
    """Alla körda studier ur journalerna: id och beslut. Nejen räknas."""
    ut = []
    for rot in STUDIEMAPPAR:
        for kj in sorted(rot.glob("**/korningar/*.json")):
            try:
                rec = json.loads(kj.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            beslut = str(rec.get("beslut", "?")).split(":")[0]
            ut.append(f"{rec.get('study', kj.parent.parent.name)}: {beslut} "
                      f"({str(rec.get('run_at', ''))[:10]})")
    return ut


def datadagar(db: Path) -> str:
    try:
        with duckdb.connect(str(db), read_only=True) as con:
            n, giltiga = con.execute(
                "select count(*), sum(is_valid_day::int) from marts.fct_glucose_daily "
                "where reading_date >= current_date - 30").fetchone()
    except duckdb.Error as err:
        return f"kunde inte läsas ({err})"
    return f"{giltiga or 0} giltiga CGM-dagar av {n or 0} senaste 30"


def rapport() -> str:
    drift = ror_drift(_rader(RORLOGG))
    rader = ["# Självstudien: systemets egna journaler", "",
             "## Rör-drift (rörloggen mot sig själv)", ""]
    rader += drift or ["Ingen formändring i rören sedan loggens start."]
    rader += ["", "## Förslagsgrindens beteende", ""]
    rader += grindmonster(_rader(GRINDLOGG)) or ["Inga grindbeslut loggade ännu."]
    rader += ["", "## Domregistret", ""]
    rader += domregister() or ["Inga körda studier hittade."]
    rader += ["", "## Datadagar", "", datadagar(DB), ""]
    return "\n".join(rader)


def main() -> int:
    UT.parent.mkdir(parents=True, exist_ok=True)
    UT.write_text(rapport())
    print(f"skrev {UT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
