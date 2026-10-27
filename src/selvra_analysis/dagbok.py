"""Interaktiv dagbok: visa gårdagens CGM-siffror och logga händelser.

Usage:
    uv run python -m selvra_analysis.dagbok            # gårdag
    uv run python -m selvra_analysis.dagbok --date 2026-10-22
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

import duckdb

from selvra_analysis.log_event import DEFAULT_LOG, append_event

DB_DEFAULT = Path("data/selvra.duckdb")

# Händelsetyper att fråga om i ordning (sensorbyte och medicinandring utelämnas — ovanliga)
SNABB_FRAGOR = [
    ("traning",        "Tränade du?"),
    ("stress",         "Stressig dag?"),
    ("sjukdom",        "Sjuk (förkylning, feber, magont)?"),
    ("alkohol",        "Alkohol?"),
    ("resa",           "Reste du?"),
    ("menstruation",   "Menstruation?"),
    ("sensorbyte",     "Sensorbyte?"),
    ("medicinandring", "Ändrade du medicin/dos?"),
    ("annat",          "Något annat värt att notera?"),
]

TIR_MAL = 70.0
TBR_VARNING = 4.0


def _tir_emoji(tir: float) -> str:
    if tir >= TIR_MAL:
        return "✓"
    if tir >= 50:
        return "~"
    return "!"


def _visa_dag(row: dict, already_logged: list[str]) -> None:
    d = row["reading_date"]
    valid = row["is_valid_day"]
    tir = row["tir_pct"] or 0.0
    tar2 = row["tar_level2_pct"] or 0.0
    tbr = row["tbr_pct"] or 0.0
    snitt = row["mean_mmol"] or 0.0
    cv = row["cv_pct"] or 0.0
    hypo1 = int(row["n_hypo_level1_events"] or 0)
    hypo2 = int(row["n_hypo_level2_events"] or 0)
    hypo_ext = int(row["n_hypo_extended_events"] or 0)
    hyper2 = int(row["n_hyper_level2_events"] or 0)

    print()
    print(f"  {d}  {'(ofullständig dag)' if not valid else ''}")
    print(f"  {'─' * 38}")
    print(f"  TIR   {tir:5.1f}%  {_tir_emoji(tir)}  (mål ≥{TIR_MAL:.0f}%)")
    print(f"  TAR2  {tar2:5.1f}%     (kraftig hyper >13.9)")
    print(f"  TBR   {tbr:5.1f}%  {'!' if tbr > TBR_VARNING else ' '}  (varning >{TBR_VARNING:.0f}%)")
    print(f"  Snitt {snitt:5.1f} mmol/L   CV {cv:.0f}%")

    episoder = []
    if hypo1:
        episoder.append(f"{hypo1}×hypo-L1")
    if hypo2:
        episoder.append(f"{hypo2}×hypo-L2")
    if hypo_ext:
        episoder.append(f"{hypo_ext}×ext-hypo")
    if hyper2:
        episoder.append(f"{hyper2}×hyper-L2")
    if episoder:
        print(f"  Episoder: {', '.join(episoder)}")

    if already_logged:
        print(f"  Redan loggat: {', '.join(already_logged)}")
    print()


def _ja(prompt: str) -> bool:
    try:
        svar = input(f"  {prompt} [j/N] ").strip().lower()
    except EOFError:
        return False
    return svar in ("j", "ja", "y", "yes")


def _notering(prompt: str = "  Notering (Enter för ingen): ") -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def run(target_date: date, db_path: Path, log_path: Path) -> None:
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            "SELECT * FROM marts.mart_analysis_days WHERE reading_date = ?",
            [str(target_date)],
        ).fetchall()
        cols = [d[0] for d in con.description]

    if not rows:
        print(f"\n  Ingen CGM-data för {target_date}.")
        if not _ja("Logga händelse ändå?"):
            return
        row = dict.fromkeys(cols)
        row["reading_date"] = target_date
        row["is_valid_day"] = False
        already_logged = []
    else:
        row = dict(zip(cols, rows[0], strict=True))
        already_logged = _already_logged(log_path, target_date)
        _visa_dag(row, already_logged)

    logged_count = 0
    for typ, fraga in SNABB_FRAGOR:
        if typ in already_logged:
            continue
        if _ja(fraga):
            notering = ""
            if _ja("  Lägg till notering?"):
                notering = _notering("  Notering: ")
            append_event(log_path=log_path, start=str(target_date), typ=typ, notering=notering)
            logged_count += 1

    print()
    if logged_count:
        print(f"  Loggade {logged_count} händelse(r) för {target_date}.")
    else:
        print(f"  Inget nytt loggat för {target_date}.")
    print()


def _already_logged(log_path: Path, target_date: date) -> list[str]:
    if not log_path.exists():
        return []
    found = []
    with log_path.open() as f:
        for row in csv.DictReader(f):
            start = row.get("start", "").strip()[:10]
            slut = row.get("slut", "").strip()[:10] or start
            if start <= str(target_date) <= slut:
                found.append(row["typ"].strip())
    return found


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--date",
        default=str(date.today() - timedelta(days=1)),
        help="Datum att visa (default: igår)",
    )
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args(argv)

    try:
        target = date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit(f"Ogiltigt datum: {args.date!r}") from None

    run(target_date=target, db_path=args.db, log_path=args.log)


if __name__ == "__main__":
    main()
