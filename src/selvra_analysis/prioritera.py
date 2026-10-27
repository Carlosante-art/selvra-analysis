"""Prioritera: vad är närmast ett svar?

Rankar låsta studier efter hur nära de är att kunna köras (dagar som saknas,
takt hittills) och öppna hypoteser efter hur mycket exponeringsdata som redan
finns. Avslöjar aldrig effekter — bara underlag.

Usage:
    uv run python -m selvra_analysis.prioritera
    make prioritera
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from selvra_analysis import study as st

DB_DEFAULT = Path("data/selvra.duckdb")
STUDIES_DIR = Path("studies")

# Nyckelord i en hypotes → exponeringskolumn i mart_analysis_days.
HYPOTES_KOLUMNER = {
    "träning": "had_training", "traning": "had_training",
    "stress": "had_stress",
    "sjuk": "is_ill",
    "alkohol": "had_alcohol",
    "resa": "is_travelling", "resor": "is_travelling",
    "medicin": "had_medication_change",
    "mens": "is_menstruating",
    "arbete": "is_workday", "arbetsdag": "is_workday", "skift": "is_workday",
    "steg": "high_steps",
    "sömn": "sleep_score", "somn": "sleep_score", "sover": "sleep_score",
}


def _studie_mappar() -> list[Path]:
    """Exempelstudier hör till demo-databasen och prioriteras aldrig."""
    return sorted(f for f in STUDIES_DIR.glob("[0-9][0-9][0-9]-*")
                  if (f / "studie.yml").exists() and "exempel" not in f.name)


def _obs_lage(study: st.Study, con) -> dict:
    """Underlag just nu mot kravet, och takten hittills. Visar aldrig utfallet."""
    daily, col = st._daily_outcome(study, con)
    s = st._observation_series(study, daily, col)
    n_exp, n_cmp = st._observation_counts(s)
    floor = study.spec["analys"]["minsta_underlag"]
    period_slut = study.design["period"][1]

    elapsed_weeks = max(1, len(s[s.index <= pd.Timestamp(date.today())])) / 7
    exp_per_vecka = n_exp / elapsed_weeks

    saknas = []
    if n_exp < floor["exponerade"]:
        brist = floor["exponerade"] - n_exp
        takt = f" (~{brist / exp_per_vecka:.0f} veckor i nuvarande takt)" if exp_per_vecka > 0 else ""
        saknas.append(f"{brist} exponerade dagar{takt}")
    if n_cmp < floor["jamforelse"]:
        saknas.append(f"{floor['jamforelse'] - n_cmp} jämförelsedagar")
    if date.today() <= period_slut:
        saknas.append(f"perioden pågår till {period_slut}")

    return {"id": study.spec["id"], "typ": "observation",
            "underlag": f"{n_exp}/{floor['exponerade']} exponerade, {n_cmp}/{floor['jamforelse']} jämförelse",
            "saknas": saknas}


def _n1_lage(folder: Path, study: st.Study) -> dict:
    rec = json.loads((folder / "las.json").read_text())
    slut = rec.get("schedule_end", "?")
    saknas = [] if str(date.today()) > str(slut) else [f"försöket pågår till {slut}"]
    return {"id": study.spec["id"], "typ": "n1", "underlag": f"schema till {slut}", "saknas": saknas}


def lasta_studier(con) -> list[dict]:
    """Läget för varje låst studie utan slutrapport: vad saknas innan den kan köras?"""
    lagen = []
    for folder in _studie_mappar():
        if not (folder / "las.json").exists() or (folder / "slutrapport.md").exists():
            continue
        try:
            study = st.load((folder / "studie.yml").resolve())
            lage = _obs_lage(study, con) if study.kind == "observation" else _n1_lage(folder, study)
        except (st.StudyError, duckdb.Error, KeyError) as err:
            lage = {"id": folder.name, "typ": "?", "underlag": f"kunde inte läsas: {err}", "saknas": ["?"]}
        lagen.append(lage)
    # Minst saknat först: det som är närmast ett svar hamnar överst.
    return sorted(lagen, key=lambda x: len(x["saknas"]))


def utkast() -> list[str]:
    """Studier som varken är låsta eller körda: väntar på granskning och beslut."""
    return [f.name for f in _studie_mappar()
            if not (f / "las.json").exists() and not (f / "slutrapport.md").exists()]


def _hypotes_underlag(fraga: str, dagar: dict[str, int]) -> int | None:
    low = fraga.lower()
    for ord_, kolumn in HYPOTES_KOLUMNER.items():
        if ord_ in low:
            return dagar.get(kolumn, 0)
    return None


def rankade_hypoteser(con, studies_dir: Path = STUDIES_DIR) -> list[tuple[str, int | None]]:
    """Öppna hypoteser ur minnet, mest befintligt dataunderlag först."""
    minne_path = studies_dir / "minne.yml"
    if not minne_path.exists():
        return []
    data = yaml.safe_load(minne_path.read_text()) or {}
    hypoteser = data.get("oppna_hypoteser") or []
    if not hypoteser:
        return []

    df = con.execute("select * from marts.mart_analysis_days where is_valid_day").df()
    dagar: dict[str, int] = {}
    for kolumn in set(HYPOTES_KOLUMNER.values()):
        if kolumn not in df.columns:
            continue
        # sleep_score är ett mätvärde (dagar med data räknas); övriga är exponeringsflaggor.
        if kolumn == "sleep_score":
            dagar[kolumn] = int(df[kolumn].notna().sum())
        else:
            dagar[kolumn] = int((df[kolumn] == True).sum())

    rankade = [(h, _hypotes_underlag(h, dagar)) for h in hypoteser]
    return sorted(rankade, key=lambda x: -1 if x[1] is None else x[1], reverse=True)


def rapport(db_path: Path) -> str:
    with duckdb.connect(str(db_path), read_only=True) as con:
        lagen = lasta_studier(con)
        hypoteser = rankade_hypoteser(con)
    vantande = utkast()

    lines = ["# Prioritering — vad är närmast ett svar?", ""]

    lines.append("## Låsta studier")
    if lagen:
        for lage in lagen:
            if lage["saknas"]:
                lines.append(f"- **{lage['id']}** ({lage['underlag']}) — saknas: {'; '.join(lage['saknas'])}")
            else:
                lines.append(f"- **{lage['id']}** ({lage['underlag']}) — **redo att köras**")
    else:
        lines.append("Inga låsta studier väntar.")
    lines.append("")

    lines.append("## Utkast som väntar på granskning och låsning")
    if vantande:
        lines.extend(f"- {namn} — kör granska, lås sedan" for namn in vantande)
    else:
        lines.append("Inga utkast.")
    lines.append("")

    lines.append("## Öppna hypoteser, mest dataunderlag först")
    if hypoteser:
        for fraga, n in hypoteser:
            underlag = f"{n} dagar med exponeringsdata" if n is not None else "underlag okänt"
            lines.append(f"- ({underlag}) {fraga}")
    else:
        lines.append("Inga öppna hypoteser i minnet.")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = parser.parse_args(argv)

    text = rapport(args.db)
    print(text)
    out = Path("data/rapporter/prioritering.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(text + "\n")
    print(f"\nSparad: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
