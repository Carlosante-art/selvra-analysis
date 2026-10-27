"""Dreamer: generera en studiefil från en naturlig fråga.

Tar en fråga på svenska, analyserar tillgänglig data, och genererar en
giltig studie.yml via ett LLM-anrop. Validerar, presenterar, skriver till disk.

Kräver ANTHROPIC_API_KEY i miljön (eller i .env).

Usage:
    uv run python -m selvra_analysis.dreamer
    uv run python -m selvra_analysis.dreamer --fraga "Påverkar stress mitt TIR?"
    make dreamer
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import anthropic
import duckdb
import yaml

from selvra_analysis.study import MIN_DAYS, validate

DB_DEFAULT = Path("data/selvra.duckdb")
STUDIES_DIR = Path("studies")
MAX_RETRIES = 3

MART_COLUMNS_DOC = """\
Tillgängliga kolumner i marts.mart_analysis_days (för utfall.kolumn):
  Glukos (hela dygnet): mean_mmol, sd_mmol, cv_pct, gmi_pct
  Tid i område: tir_pct, tar_pct, tar_level2_pct, tbr_pct, tbr_level2_pct
  Rensad (utan artefakter): mean_mmol_clean, tir_pct_clean, tbr_pct_clean
  Episoder: n_hypo_level1_events, n_hypo_level2_events, n_hypo_extended_events
            n_hyper_level1_events, n_hyper_level2_events
  Tidsfönster (utfall.matt + utfall.fonster): medel, topp, tid_over_10"""

SYSTEM_PROMPT_TEMPLATE = """\
Du är Dreamer, en del av Selvra-analysmotorn. Du genererar studiedesigner.

Din uppgift: ta en fråga på svenska och returnera EXAKT en giltig studie.yml.
Inget annat. Inga förklaringar. Inga markdown-kodblock. Bara ren YAML.

STUDIEFORMAT (alla fält obligatoriska om inget annat anges):

id: NNN-kort-namn          # fylls i av systemet, ignorera
titel: ...                 # en mening
fraga: ...                 # besvarbar med ett tal
tes: ...                   # konkret påstående om effektriktning och storlek
motbevis: ...              # vad som motbevisar tesen

design:
  typ: observation         # observation | n1

  # För observation:
  exponering:
    handelse: HÄNDELSETYP  # en av: alkohol, medicinandring, menstruation, resa, sensorbyte, sjukdom, stress, traning
    dagar_efter: 0         # heltal ≥ 0; 0 = samma dag, 1 = dagen efter
  period: [FRÅN, TILL]     # ISO-datum inom tillgängligt datumspann
  retrospektiv: true/false # true om datan fanns när studien skrevs

  # För n1 (randomiserat experiment):
  A: ...                   # interventionen, exakt
  B: ...                   # jämförelsen, exakt
  start: DATUM             # ISO-datum, minst 2 veckor framåt från idag
  par: 12                  # heltal ≥ 6
  periodlangd_dagar: 2     # heltal ≥ 1
  tvatt_dagar: 1           # heltal ≥ 0, < periodlangd_dagar

utfall:
  # Alternativ A – mäter i ett tidsfönster (kräver matt + fonster):
  matt: medel              # medel | topp | tid_over_10
  fonster: ["HH:MM", "HH:MM"]  # lokal tid, start < slut, inom samma dygn
  min_tackning_pct: 70     # valfri, default 70

  # Alternativ B – mäter ett helt dygn (kräver kolumn):
  kolumn: KOLUMNNAMN       # se listan nedan

analys:
  metod: blockbootstrap    # blockbootstrap för observation, randomiseringstest för n1
  niva: 0.95
  blocklangd: 7            # dagar, för blockbootstrap
  minsta_relevanta_effekt: -0.5  # tal ≠ 0; negativt = förväntat lägre med exponering
  minsta_underlag: {exponerade: 15, jamforelse: 30}  # endast observation; var och en minst {min_days}

protokoll:                 # CENT 2015
  periodeffekt: ...        # hur tidstrender hanteras
  overforing: ...          # endast n1: hur eftereffekter hanteras (tvättdagar, AB mot BA)
  stoppregel: ...          # endast n1: när försöket avbryts i förtid (t.ex. upprepad hypo nivå 2)
  andringslogg: []         # alltid en tom lista

negativ_kontroll:          # ett utfall exponeringen INTE kan påverka, samma form som utfall
  matt: medel
  fonster: ["HH:MM", "HH:MM"]  # t.ex. ett fönster som ligger FÖRE exponeringen samma dag
  motivering: ...          # varför exponeringen inte kan påverka det

REGLER:
- observation + fonster → metod: blockbootstrap
- observation + kolumn  → metod: blockbootstrap
- n1                    → metod: randomiseringstest (inte blocklangd)
- Välj observation om frågan gäller något som redan hänt (retrospektiv: true) eller är en naturlig loggad händelse.
- Välj n1 om frågan kräver att du aktivt ändrar beteende.
- minsta_relevanta_effekt: välj kliniskt rimlig storlek. För glukos ±0.5 mmol/L är en liten men meningsfull effekt.
- För TIR/TAR/TBR i procent är ±5 procentenheter rimlig minsta effekt.
- Den negativa kontrollen måste ligga där exponeringen inte kan verka: före den i tid,
  eller ett utfall utan mekanism. Samma analys körs på den; en effekt där avslöjar snedvridning.
"""


def _load_dotenv() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key == "ANTHROPIC_API_KEY" and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


def _context(db_path: Path) -> str:
    with duckdb.connect(str(db_path), read_only=True) as con:
        span = con.execute(
            "SELECT MIN(reading_date), MAX(reading_date), COUNT(*) "
            "FROM marts.mart_analysis_days WHERE is_valid_day"
        ).fetchone()
        events = con.execute(
            "SELECT typ, COUNT(*) as n FROM raw.personal_events GROUP BY typ ORDER BY n DESC"
        ).fetchdf()

    date_from, date_to, n_days = span
    event_lines = []
    for _, row in events.iterrows():
        event_lines.append(f"  {row['typ']}: {int(row['n'])} loggade")
    if not event_lines:
        event_lines = ["  (inga händelser loggade ännu)"]

    return f"""\
TILLGÄNGLIG DATA:
  Giltiga dagar: {n_days} (från {date_from} till {date_to})
  Loggade händelser:
{chr(10).join(event_lines)}

{MART_COLUMNS_DOC}"""


def _next_id(fraga: str) -> str:
    existing = sorted(STUDIES_DIR.glob("[0-9][0-9][0-9]-*"))
    n = int(existing[-1].name[:3]) + 1 if existing else 0
    slug = re.sub(r"[^a-z0-9]+", "-", fraga.lower())[:40].strip("-")
    return f"{n:03d}-{slug}"


def _call_llm(fraga: str, context: str, error_feedback: str = "") -> str:
    client = anthropic.Anthropic()

    user_content = f"{context}\n\nFRÅGA: {fraga}"
    if error_feedback:
        user_content += f"\n\nFEL I FÖREGÅENDE FÖRSÖK — rätta dessa och försök igen:\n{error_feedback}"

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT_TEMPLATE.replace("{min_days}", str(MIN_DAYS)),
        messages=[{"role": "user", "content": user_content}],
    )
    return msg.content[0].text.strip()


def _parse_yaml(text: str) -> dict | None:
    text = re.sub(r"^```ya?ml\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
    try:
        return yaml.safe_load(text.strip())
    except yaml.YAMLError:
        return None


def generate(fraga: str, db_path: Path) -> tuple[str, dict]:
    context = _context(db_path)
    study_id = _next_id(fraga)
    error_feedback = ""

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(f"  Försök {attempt}/{MAX_RETRIES}...", file=sys.stderr)

        raw = _call_llm(fraga, context, error_feedback)
        spec = _parse_yaml(raw)

        if spec is None:
            error_feedback = "Svaret var inte giltig YAML."
            continue

        spec["id"] = study_id
        errors = validate(spec)
        if not errors:
            return study_id, spec

        error_feedback = "\n".join(f"- {e}" for e in errors)

    raise SystemExit(
        f"Kunde inte generera en giltig studiefil efter {MAX_RETRIES} försök.\n"
        f"Senaste fel:\n{error_feedback}"
    )


def write_study(study_id: str, spec: dict) -> Path:
    folder = STUDIES_DIR / study_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "studie.yml"
    path.write_text(yaml.dump(spec, allow_unicode=True, sort_keys=False, default_flow_style=False))
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fraga", default=None, help="Frågan på svenska")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = parser.parse_args(argv)

    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Sätt ANTHROPIC_API_KEY i .env eller miljön.")

    fraga = args.fraga
    if not fraga:
        print("Vad vill du veta? (Skriv din fråga på svenska)")
        fraga = input("> ").strip()
    if not fraga:
        raise SystemExit("Ingen fråga angiven.")

    print(f"\nGenererar studiedesign för: {fraga!r}", file=sys.stderr)
    study_id, spec = generate(fraga, args.db)

    print()
    print(yaml.dump(spec, allow_unicode=True, sort_keys=False, default_flow_style=False))

    try:
        svar = input("Skriv till disk? [J/n] ").strip().lower()
    except EOFError:
        svar = "j"

    if svar in ("", "j", "ja", "y", "yes"):
        path = write_study(study_id, spec)
        print(f"\nSparad: {path}")
        print("Granska fråga, tes, motbevis, minsta relevanta effekt och negativ kontroll innan du låser.")
        print("Dreamer föreslår; besluten är dina. Det du låser är det du står för.")
        print(f"Nästa steg: uv run python -m selvra_analysis.study las {path}")
    else:
        print("Avbröt — inget skrevs.")


if __name__ == "__main__":
    main()
