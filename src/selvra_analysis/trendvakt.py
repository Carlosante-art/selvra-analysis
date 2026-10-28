"""Trendvakten: skannerns wearable-mönster som en rad i morgonnotisen.

För en hjärtstoppsöverlevare är det här Selvras ärliga roll mellan
kardiologbesöken: beskriva när vilopulsen börjar driva eller sömnen ligger
under hans eget normala — och vara tyst alla andra morgnar. Beskriva, aldrig
råda; domaren i hjärtfrågor är läkaren, inte motorn.

En signal som tänt får vila (COOLDOWN_DAGAR) innan samma mönstertyp får låta
igen — en trend som består är samma trend, inte en ny nyhet. Vilan bokförs i
personens mapp (trendvakt.json, gitignorerad som allt personligt).

Steg↔nattpuls-detektorn ingår inte här: samband är förslagsmaterial och går
via förslagsgrinden, inte via trendvakten.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb

from selvra_analysis import scanner
from selvra_analysis.ingest_garmin import person_paths

COOLDOWN_DAGAR = 7


def trendrad(person: str, db_path: Path, idag: date | None = None,
             skriv: bool = True) -> str | None:
    """Beskrivande rad(er) när ett mönster tänt och inte är i vila, annars None.

    skriv=False förhandsgranskar utan att förbruka vilotiden (morgonpush visa)."""
    idag = idag or date.today()
    try:
        df = scanner._load(db_path)
    except duckdb.Error:
        return None

    monster = scanner._vilopuls_trend(df) + scanner._somn_under_normalt(df)
    if not monster:
        return None

    marker = person_paths(person)["dir"] / "trendvakt.json"
    vila = json.loads(marker.read_text()) if marker.exists() else {}
    rader = []
    for p in monster:
        senast = vila.get(p.typ)
        if senast and (idag - date.fromisoformat(senast)).days < COOLDOWN_DAGAR:
            continue
        vila[p.typ] = str(idag)
        rader.append("Selvra ser: " + p.beskrivning)
    if not rader:
        return None
    if skriv:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(vila))
    return "\n".join(rader)
