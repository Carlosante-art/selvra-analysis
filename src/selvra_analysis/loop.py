"""Autonom loop: en iteration av hela analyscykeln.

En körning gör:
  1. Hämtar senaste data (make live)
  2. Skannar efter mönster, sparar nya hypoteser i Dreamer-minnet
  3. Kör slutanalysen på låsta studier som nått sitt underlag
  4. Prioriterar: vad är närmast ett svar, vad är värt att logga
  5. Tolkar slutförda studier som saknar tolkning
  6. Syntetiserar hela portfoljen
  7. Skriver en loop-rapport till data/rapporter/loop-DATUM.md

Motorn driver sig själv — du behöver bara köra `make loop` regelbundet
(eller `make schemalagg` en gång, så kör den varje morgon).

Usage:
    make loop
    uv run python -m selvra_analysis.loop [--hoppa-over-live]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb

from selvra_analysis.dreamer import _load_dotenv, sammanfattning, tolka
from selvra_analysis.prioritera import rapport as prioritering
from selvra_analysis.scanner import _format, scan, spara_hypoteser
from selvra_analysis.study import StudyError
from selvra_analysis.study import load as las_studie
from selvra_analysis.study import run as kor_studie

DB_DEFAULT = Path("data/selvra.duckdb")
STUDIES_DIR = Path("studies")


def _kör_live() -> bool:
    print("→ Hämtar senaste data (make live)...", file=sys.stderr)
    make = shutil.which("make") or "make"
    # A fixed make target from this repo; no user input.
    result = subprocess.run([make, "live"], check=False, capture_output=False)  # noqa: S603
    return result.returncode == 0


def _kor_fardiga(db_path: Path) -> list[str]:
    """Kör slutanalysen på låsta studier som nått sitt underlag. Beslutet togs vid
    låsningen; körningen är mekanik. Motorn vägrar själv om något inte stämmer
    (pågår, för lite data, okommittad, redan körd) och förbrukar inget vid nej."""
    korda = []
    for folder in sorted(STUDIES_DIR.glob("[0-9][0-9][0-9]-*")):
        if not (folder / "las.json").exists() or (folder / "slutrapport.md").exists():
            continue
        if "exempel" in folder.name:
            continue  # exempelstudier hör till demo-databasen, aldrig din data
        try:
            study = las_studie((folder / "studie.yml").resolve())
            with duckdb.connect(str(db_path), read_only=True) as con:
                record, _ = kor_studie(study, con)
            korda.append(f"{folder.name}: {record['beslut']}")
            print(f"→ Körde {folder.name}: {record['beslut']}", file=sys.stderr)
        except (StudyError, ValueError) as err:
            print(f"  {folder.name}: inte redo ({err})", file=sys.stderr)
    return korda


def _tolka_osvarade(db_path: Path) -> list[str]:
    tolkade = []
    for folder in sorted(STUDIES_DIR.glob("[0-9][0-9][0-9]-*")):
        if not (folder / "slutrapport.md").exists():
            continue
        if (folder / "tolkning.md").exists():
            continue
        print(f"→ Tolkar {folder.name}...", file=sys.stderr)
        try:
            text = tolka(folder, db_path)
            out = folder / "tolkning.md"
            out.write_text(text + "\n")
            tolkade.append(folder.name)
            print(f"  Sparad: {out}", file=sys.stderr)
        except SystemExit as e:
            print(f"  Kunde inte tolka {folder.name}: {e}", file=sys.stderr)
    return tolkade


def _portfolio_syntes(db_path: Path) -> str:
    print("→ Syntetiserar portfolio...", file=sys.stderr)
    return sammanfattning(STUDIES_DIR, db_path)


def run(db_path: Path, hoppa_over_live: bool = False) -> str:
    today = str(date.today())
    lines = [f"# Loop-rapport {today}", ""]

    if not hoppa_over_live:
        ok = _kör_live()
        lines.append(f"## Datahämtning\n\n{'OK' if ok else 'FEL — se make live-output'}.\n")
    else:
        lines.append("## Datahämtning\n\nHoppades över (--hoppa-over-live).\n")

    print("→ Skannar efter mönster...", file=sys.stderr)
    patterns = scan(db_path)
    lines.append("## Mönster i data\n")
    lines.append(_format(patterns))
    lines.append("")

    nya = spara_hypoteser(patterns)
    if nya:
        lines.append(f"{nya} nya hypoteser sparade i Dreamer-minnet.\n")

    korda = _kor_fardiga(db_path)
    if korda:
        lines.append("## Slutanalyser körda\n")
        lines.extend(f"- {k}" for k in korda)
        lines.append("")

    print("→ Prioriterar...", file=sys.stderr)
    prio = prioritering(db_path)
    lines.append(prio)
    lines.append("")
    out_prio = Path("data/rapporter/prioritering.md")
    out_prio.parent.mkdir(exist_ok=True)
    out_prio.write_text(prio + "\n")

    _load_dotenv()
    har_api = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if har_api:
        tolkade = _tolka_osvarade(db_path)
        if tolkade:
            lines.append(f"## Tolkningar genomförda\n\n{', '.join(tolkade)}\n")
        else:
            lines.append("## Tolkningar\n\nInga nya slutrapporter att tolka.\n")

        syntes = _portfolio_syntes(db_path)
        lines.append("## Portfoljosyntes\n")
        lines.append(syntes)
        lines.append("")

        out_portfolio = Path("data/rapporter/portfolio.md")
        out_portfolio.parent.mkdir(exist_ok=True)
        out_portfolio.write_text(syntes + "\n")
    else:
        lines.append(
            "## LLM-steg hoppades över\n\n"
            "Sätt ANTHROPIC_API_KEY i .env för tolkning och portfoljosyntes.\n"
        )

    rapport = "\n".join(lines)
    out = Path(f"data/rapporter/loop-{today}.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(rapport + "\n")
    print(f"\nLoop klar. Rapport: {out}", file=sys.stderr)
    return rapport


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    parser.add_argument("--hoppa-over-live", action="store_true",
                        help="Hoppa över make live (använd befintlig data)")
    args = parser.parse_args(argv)
    rapport = run(args.db, args.hoppa_over_live)
    print(rapport)


if __name__ == "__main__":
    main()
