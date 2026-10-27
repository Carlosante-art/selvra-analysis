"""Förslagsgrinden: en rad i morgonnotisen — men bara när granskaren säger att frågan går att pröva.

Motorn föreslår aldrig ur mönster ensamma. Varje morgon prövas mallstudien tyst mot
personens växande baslinje genom hela designgranskningen (granska.review). Den dagen
granskaren inte längre stoppar tänds en inbjudan i notisen. Fram tills dess: tystnad.
Beskriva och bjuda in — aldrig råda, aldrig locka.

Utkastet skrivs till data/personer/<namn>/forslag/<id>/studie.yml så Carl kan granska
och låsa exakt den fil som godkändes. Är utkastet låst (las.json finns) föreslås inget
mer — då pågår försöket.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import yaml

from selvra_analysis import granska
from selvra_analysis import study as st

FORSLAG_ID = "p01-promenad-vilopuls"
ANTAL_DAGAR = 24
AVSTAND_DAGAR = 3
START_OM_DAGAR = 14

INBJUDAN = ("Selvra ser att underlaget nu räcker för att pröva en fråga på riktigt: "
            "sänker en promenaddag nattens vilopuls? Upplägget är granskat och klart "
            "att låsa — säg till Carl om du vill försöka.")


def _mall(idag: date) -> dict:
    start = idag + timedelta(days=START_OM_DAGAR)
    datum = [start + timedelta(days=i * AVSTAND_DAGAR) for i in range(ANTAL_DAGAR)]
    return {
        "id": FORSLAG_ID,
        "titel": "Promenaddag och nattens vilopuls",
        "fraga": "Är vilopulsen lägre natten efter en dag med minst 8 000 steg jämfört med en vanlig dag?",
        "tes": "En dag med minst 8 000 steg ger minst 2 slag lägre vilopuls natten efter.",
        "motbevis": "Hela intervallet visar en mindre sänkning än 2 slag, eller ingen.",
        "design": {
            "typ": "n1",
            "A": "Minst 8 000 steg, varav en rask promenad på 45–60 minuter före 17:00",
            "B": "Vanlig dag, högst 4 000 steg, ingen planerad promenad",
            "start": start, "par": 12, "periodlangd_dagar": 1, "tvatt_dagar": 0,
            "foljsamhet": {"kolumn": "steps", "A": {"min": 8000}, "B": {"max": 4000}},
            "verkan": {"typ": "traning", "borjar": "10:00"},
            "dagar": {"datum": datum, "minsta_avstand": AVSTAND_DAGAR},
            "dagar_motivering": "Alla dagar är lika; tre dagars mellanrum täcker eftereffekten.",
            "genomforbarhet": ("A görs som en planerad promenad; en vanlig dag ligger stegen "
                               "långt under tröskeln, så B är den naturliga dagen."),
        },
        "utfall": {"kolumn": "hr_lowest_bpm"},
        "analys": {"metod": "randomiseringstest", "niva": 0.95, "minsta_relevanta_effekt": -2},
        "protokoll": {
            "periodeffekt": "Ordningen lottas; långsam konditionsförändring drabbar A och B lika.",
            "overforing": "Minst tre kalenderdagar mellan studiedagar, över 24–48 h eftereffekt.",
            "stoppregel": ("Avbryt vid sjukdom eller bröstsmärta vid ansträngning; "
                           "promenaden är frivillig varje gång."),
            "andringslogg": [],
        },
        "negativ_kontroll": {
            "kolumn": "steps",
            "motivering": ("Gårdagens steg kan inte påverkas av dagens lottning; "
                           "en skillnad där avslöjar schemaläckage."),
        },
    }


def _bygg_marts(person: str) -> bool:
    """Personens marts måste vara färska innan granskningen. make äger receptet."""
    make = subprocess.run(["/usr/bin/make", "person-build", f"PERSON={person}"],  # noqa: S603
                          check=False, capture_output=True)
    if make.returncode != 0:
        print(f"  person-build misslyckades; hoppar över förslaget: "
              f"{make.stderr.decode()[-200:]}", file=sys.stderr)
    return make.returncode == 0


def forslagsrad(person: str, db_path: Path, idag: date | None = None,
                bygg: bool = True) -> str | None:
    """Inbjudan när granskaren godkänner mallstudien mot personens data, annars None."""
    idag = idag or date.today()
    mapp = db_path.parent / "forslag" / FORSLAG_ID
    if (mapp / "las.json").exists():
        return None  # försöket pågår; motorn tjatar inte
    if bygg and not _bygg_marts(person):
        return None

    mapp.mkdir(parents=True, exist_ok=True)
    spec = _mall(idag)
    (mapp / "studie.yml").write_text(
        yaml.dump(spec, allow_unicode=True, sort_keys=False, default_flow_style=False))
    try:
        studie = st.load(mapp / "studie.yml")
        with duckdb.connect(str(db_path), read_only=True) as con:
            resultat = granska.review(studie, con, today=idag)
    except (st.StudyError, duckdb.Error) as err:
        print(f"  förslaget kunde inte granskas: {err}", file=sys.stderr)
        return None

    dom = resultat.get("verdict", resultat.get("dom", ""))
    stopp = [c for c in resultat.get("checks", []) if c.get("level") == granska.STOPP]
    print(f"  förslagsgrinden: {dom or ('STOPP' if stopp else 'OK')}"
          + (f" ({stopp[0]['text'][:80]}…)" if stopp else ""), file=sys.stderr)
    if stopp or dom == granska.STOPP:
        return None
    return INBJUDAN
