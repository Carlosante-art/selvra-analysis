"""Dreamer: generera och tolka studier från naturliga frågor.

Fyra kommandon:

  generera (default) — tar en fråga, returnerar studie.yml
  tolka              — läser en slutrapport, ger klartext + nästa steg, uppdaterar minnet
  sammanfattning     — syntetiserar alla studier
  minne              — visar vad Dreamer vet sedan tidigare

Kräver ANTHROPIC_API_KEY i miljön (eller i .env).

Usage:
    uv run python -m selvra_analysis.dreamer
    uv run python -m selvra_analysis.dreamer --fraga "Påverkar stress mitt TIR?"
    uv run python -m selvra_analysis.dreamer tolka studies/001-traning-natten-efter/
    uv run python -m selvra_analysis.dreamer minne
    make dreamer
    make tolka studie=studies/001-traning-natten-efter/
    make minne
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

from selvra_analysis import sprakgrind
from selvra_analysis.dreamer_minne import (  # noqa: F401 — återexport (scanner m.fl.)
    MINNE_FILE,
    STUDIES_DIR,
    _add_study_to_minne,
    _init_minne,
    _load_minne,
    _update_minne,
    lagg_till_hypoteser,
    show_minne,
)
from selvra_analysis.study import MIN_DAYS, StudyError, load, status, validate

DB_DEFAULT = Path("data/selvra.duckdb")
MAX_RETRIES = 3

MART_COLUMNS_DOC = """\
Tillgängliga kolumner i marts.mart_analysis_days (för utfall.kolumn):
  Glukos (hela dygnet): mean_mmol, sd_mmol, cv_pct, gmi_pct
  Tid i område: tir_pct, tar_pct, tar_level2_pct, tbr_pct, tbr_level2_pct
  Rensad (utan artefakter): mean_mmol_clean, tir_pct_clean, tbr_pct_clean
  Episoder: n_hypo_level1_events, n_hypo_level2_events, n_hypo_extended_events
            n_hyper_level1_events, n_hyper_level2_events
  Sömn och aktivitet (Oura/Garmin, null om wearable-data saknas): sleep_score,
            readiness_score, hrv_avg_ms, hr_lowest_bpm, total_sleep_seconds,
            deep_sleep_seconds, rem_sleep_seconds, sleep_efficiency_pct, steps,
            stress_avg, stress_max (Garmin Firstbeat 0–100; Oura: null)
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
    handelse: HÄNDELSETYP  # en av: alkohol, hoga_steg, medicinandring, menstruation, resa, sjukdom, stress, traning
                           # hoga_steg härleds ur Oura-steg (≥10 000), kräver ingen loggning
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
  foljsamhet:              # endast n1: hur varje dags villkor verifieras ur data
    kolumn: steps          # kolumn i marts.mart_analysis_days, eller manuell
    A: {{min: 10000}}
    B: {{max: 5000}}
  verkan:                  # endast n1
    typ: traning           # traning | alkohol | somn | maltid | annat
    borjar: "HH:MM"        # tidigast A kan verka

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
  minsta_underlag: {{exponerade: 15, jamforelse: 30}}  # endast observation; var och en minst {min_days}

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
- n1: negativa kontrollen ska sluta före verkan.borjar och ligga utanför förra A-dagens
  eftereffekt (träning 24–48 h, alkohol till morgonen efter). Intilliggande dagar duger inte vid träning.
- n1: går B eller A inte att göra på vissa dagar (arbetsdag/ledig), begränsa med design.dagar.
- Insulin, kolhydratkvoter, hypobehandling och alkohol som dos är aldrig studievariabler.
- Filen är ett utkast. Den låses först efter `python -m selvra_analysis.granska` och /ny-studie.
- Generera INTE studier som redan finns i minnet nedan.
"""


# ---------------------------------------------------------------------------
# Minne
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------

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


def _call_llm(fraga: str, context: str, error_feedback: str = "", minne_text: str = "") -> str:
    client = anthropic.Anthropic()

    user_content = context
    if minne_text:
        user_content = minne_text + "\n\n" + user_content
    user_content += f"\n\nFRÅGA: {fraga}"
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


def generate(fraga: str, db_path: Path, studies_dir: Path = STUDIES_DIR) -> tuple[str, dict]:
    _init_minne(studies_dir)
    context = _context(db_path)
    minne_text = _load_minne(studies_dir)
    study_id = _next_id(fraga)
    error_feedback = ""

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(f"  Försök {attempt}/{MAX_RETRIES}...", file=sys.stderr)

        raw = _call_llm(fraga, context, error_feedback, minne_text)
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


# ---------------------------------------------------------------------------
# Tolka
# ---------------------------------------------------------------------------

TOLKA_PROMPT = """\
Du är Dreamer, tolkningslagret i Selvra-analysmotorn.

Du får en slutrapport från en genomförd studie och aktuell datastatus.
Din uppgift: förklara vad resultatet betyder på klartext svenska, ge ett konkret nästa steg,
och extrahera en lärdom för minnet.

Formatera svaret EXAKT så här — XML-taggarna är obligatoriska:

<tolkning>
Tre korta avsnitt utan rubriker, löpande text:

1. VAD RESULTATET SÄGER (2-3 meningar): förklara beslutet (tesen håller / motbevisad / obestämt)
   i termer som inte kräver statistikkunskaper. Nämn skattningen och intervallet konkret.

2. VARFÖR INTERVALLET ÄR SOM DET ÄR (1-2 meningar): förklara den viktigaste begränsningen
   — för lite data, hög variation, för kort period, eller att effekten är liten men reell.

3. NÄSTA STEG (1-2 meningar): ett konkret, handlingsbart förslag. Exempel:
   - Om obestämt + få exponerade dagar: hur många fler behövs och hur man loggar dem
   - Om obestämt + tillräcklig data men hög variation: föreslå n1-experiment
   - Om tesen håller: föreslå att bekräfta med n1 för att skilja samband från orsak
   - Om motbevisad: föreslå att undersöka en annan hypotes
</tolkning>

<minne>
beslut: håller
lärdom: EN mening om vad vi faktiskt lärde oss av denna studie
nasta_steg: EN mening om vad som bör göras härnäst
</minne>

Välj ett av: håller | motbevisad | obestämt — för beslut.
Var ärlig om begränsningar. Observationsstudier visar samband, inte orsak.
Skriv tolkning på svenska. Max 150 ord i <tolkning>-blocket.
"""


def _call_tolka(
    studie_yml: str,
    slutrapport: str,
    status_text: str,
    minne_text: str = "",
) -> tuple[str, dict]:
    client = anthropic.Anthropic()

    user_content = ""
    if minne_text:
        user_content = minne_text + "\n\n"
    user_content += f"""\
STUDIEFIL:
{studie_yml}

SLUTRAPPORT:
{slutrapport}

DATASTATUS:
{status_text}
"""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=768,
        system=TOLKA_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = msg.content[0].text.strip()

    tolkning_match = re.search(r"<tolkning>(.*?)</tolkning>", raw, re.DOTALL)
    tolkning = tolkning_match.group(1).strip() if tolkning_match else raw

    minne_data: dict = {"beslut": "obestämt", "lardom": "", "nasta_steg": ""}
    minne_match = re.search(r"<minne>(.*?)</minne>", raw, re.DOTALL)
    if minne_match:
        for line in minne_match.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip()
                if k == "beslut":
                    minne_data["beslut"] = v
                elif k == "lärdom":
                    minne_data["lardom"] = v
                elif k == "nasta_steg":
                    minne_data["nasta_steg"] = v

    return tolkning, minne_data


def _study_status_text(folder: Path, db_path: Path) -> str:
    try:
        study = load((folder / "studie.yml").resolve())
        with duckdb.connect(str(db_path), read_only=True) as con:
            return status(study, con)
    except (StudyError, duckdb.Error) as err:
        return f"Status kunde inte tas fram: {err}"


def _svar_ur_rapport(slutrapport: str) -> str:
    """Motorskriven reserv när språkgrinden stoppar AI-texten: rapportens Svar-sektion."""
    m = re.search(r"## Svar\n+(.*?)(?=\n## |\Z)", slutrapport, re.DOTALL)
    svar = m.group(1).strip() if m else slutrapport.strip().split("\n")[0]
    return svar + "\n\n(AI-tolkningen stoppades av språkgrinden; detta är rapportens eget svar.)"


def tolka(folder: Path, db_path: Path, studies_dir: Path = STUDIES_DIR) -> str:
    slutrapport_path = folder / "slutrapport.md"
    studie_path = folder / "studie.yml"

    if not studie_path.exists():
        raise SystemExit(f"Ingen studie.yml i {folder}")
    if not slutrapport_path.exists():
        raise SystemExit(
            f"Ingen slutrapport.md i {folder}\n"
            "Kör studien först: uv run python -m selvra_analysis.study kor {studie_path}"
        )

    studie_yml = studie_path.read_text()
    slutrapport = slutrapport_path.read_text()
    status_text = _study_status_text(folder, db_path)
    minne_text = _load_minne(studies_dir)

    text, minne_data = _call_tolka(studie_yml, slutrapport, status_text, minne_text)

    ok, skal = sprakgrind.granska_text(text, studie_yml + slutrapport + status_text,
                                       max_tecken=1500)
    if not ok:
        print(f"språkgrinden stoppade tolkningen ({skal}); mallat svar istället",
              file=sys.stderr)
        text = _svar_ur_rapport(slutrapport)
        minne_data = {}

    _update_minne(
        studies_dir,
        folder.name,
        minne_data.get("lardom", ""),
        minne_data.get("nasta_steg", ""),
        minne_data.get("beslut", "obestämt"),
    )

    return text


# ---------------------------------------------------------------------------
# Sammanfattning
# ---------------------------------------------------------------------------

SAMMANFATTNING_PROMPT = """\
Du är Dreamer, syntes-lagret i Selvra-analysmotorn.

Du får en lista med studier och deras resultat (eller nuvarande status om de inte är klara).
Skriv en syntes på svenska — vad har vi lärt oss, vad är fortfarande öppet, och vad bör
undersökas härnäst.

Strukturera i tre avsnitt med dessa exakta rubriker:

## Vad vi vet
Sammanfatta slutsatserna från genomförda studier. Var konkret om effektstorlekar.
Markera tydligt om en studie är retrospektiv (svagare bevis) eller randomiserad (starkare).

## Vad som är öppet
Studier som pågår eller har för lite data. Vad saknas för att de ska kunna avgöras?

## Föreslagna nästa steg
Max tre konkreta förslag, prioriterade. Varje förslag är en handlingsbar mening.

Skriv på svenska. Var ärlig om vad data kan och inte kan visa.
Max 250 ord.
"""


def _call_sammanfattning(studie_texter: list[str], minne_text: str = "") -> str:
    client = anthropic.Anthropic()
    user_content = ""
    if minne_text:
        user_content = minne_text + "\n\n"
    user_content += "STUDIER:\n\n" + "\n\n---\n\n".join(studie_texter)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=768,
        system=SAMMANFATTNING_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return msg.content[0].text.strip()


def sammanfattning(studies_dir: Path, db_path: Path) -> str:
    folders = sorted(
        [f for f in studies_dir.iterdir() if f.is_dir() and (f / "studie.yml").exists()],
        key=lambda f: f.name,
    )
    if not folders:
        return "Inga studier hittade i " + str(studies_dir)

    minne_text = _load_minne(studies_dir)
    texter = []
    for folder in folders:
        studie = (folder / "studie.yml").read_text()
        if (folder / "slutrapport.md").exists():
            rapport = (folder / "slutrapport.md").read_text()
            texter.append(f"STUDIE: {folder.name}\n\nFIL:\n{studie}\n\nRAPPORT:\n{rapport}")
        elif (folder / "las.json").exists():
            texter.append(f"STUDIE: {folder.name} (låst, pågår)\n\nFIL:\n{studie}")
        else:
            texter.append(f"STUDIE: {folder.name} (ej låst)\n\nFIL:\n{studie}")

    text = _call_sammanfattning(texter, minne_text)
    ok, skal = sprakgrind.granska_text(text, "\n".join(texter) + minne_text,
                                       max_tecken=2500)
    if not ok:
        print(f"språkgrinden stoppade syntesen ({skal}); mallad lista istället",
              file=sys.stderr)
        rader = []
        for folder in folders:
            if (folder / "slutrapport.md").exists():
                svar = _svar_ur_rapport((folder / "slutrapport.md").read_text())
                rader.append(f"- {folder.name}: {svar.splitlines()[0]}")
            elif (folder / "las.json").exists():
                rader.append(f"- {folder.name}: låst, pågår")
            else:
                rader.append(f"- {folder.name}: utkast, ej låst")
        text = ("AI-syntesen stoppades av språkgrinden. Studiernas egna svar:\n"
                + "\n".join(rader))
    return text


def write_study(study_id: str, spec: dict) -> Path:
    folder = STUDIES_DIR / study_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "studie.yml"
    path.write_text(yaml.dump(spec, allow_unicode=True, sort_keys=False, default_flow_style=False))
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_generera(fraga: str | None, db: Path) -> None:
    if not fraga:
        print("Vad vill du veta? (Skriv din fråga på svenska)")
        try:
            fraga = input("> ").strip()
        except EOFError:
            fraga = ""
    if not fraga:
        raise SystemExit("Ingen fråga angiven.")

    print(f"\nGenererar studiedesign för: {fraga!r}", file=sys.stderr)
    study_id, spec = generate(fraga, db)

    print()
    print(yaml.dump(spec, allow_unicode=True, sort_keys=False, default_flow_style=False))

    try:
        svar = input("Skriv till disk? [J/n] ").strip().lower()
    except EOFError:
        svar = "j"

    if svar in ("", "j", "ja", "y", "yes"):
        path = write_study(study_id, spec)
        _add_study_to_minne(STUDIES_DIR, study_id, fraga)
        print(f"\nSparad: {path}")
        print("Minnet uppdaterat.")
        print("Granska fråga, tes, motbevis, minsta relevanta effekt och negativ kontroll innan du låser.")
        print("Dreamer föreslår; besluten är dina. Det du låser är det du står för.")
        print(f"Nästa steg: uv run python -m selvra_analysis.study las {path}")
    else:
        print("Avbröt — inget skrevs.")


def _run_tolka(folder: Path, db: Path) -> None:
    print(f"\nTolkar {folder.name}...\n", file=sys.stderr)
    text = tolka(folder, db)
    print(text)
    out = folder / "tolkning.md"
    out.write_text(text + "\n")
    print(f"\nSparad: {out}", file=sys.stderr)
    print("Minnet uppdaterat.", file=sys.stderr)


def _run_sammanfattning(studies: Path, db: Path) -> None:
    print("\nSyntetiserar studieportföljen...\n", file=sys.stderr)
    text = sammanfattning(studies, db)
    print(text)
    out = Path("data/rapporter/portfolio.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(text + "\n")
    print(f"\nSparad: {out}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="kommando")

    gen = sub.add_parser("generera", help="Generera en studiefil från en fråga (default)")
    gen.add_argument("--fraga", default=None, help="Frågan på svenska")
    gen.add_argument("--db", type=Path, default=DB_DEFAULT)

    tol = sub.add_parser("tolka", help="Tolka en slutrapport och ge nästa steg, uppdaterar minnet")
    tol.add_argument("studie", type=Path, help="Sökväg till studiemappen")
    tol.add_argument("--db", type=Path, default=DB_DEFAULT)

    sam = sub.add_parser("sammanfattning", help="Syntetisera alla studier till en portfolio-översikt")
    sam.add_argument("--studies", type=Path, default=STUDIES_DIR)
    sam.add_argument("--db", type=Path, default=DB_DEFAULT)

    min_p = sub.add_parser("minne", help="Visa vad Dreamer vet sedan tidigare")
    min_p.add_argument("--studies", type=Path, default=STUDIES_DIR)

    # Bakåtkompatibilitet: dreamer [--fraga "..."] utan subkommando = generera
    parser.add_argument("--fraga", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)

    args = parser.parse_args(argv)

    if args.kommando == "minne":
        print(show_minne(args.studies))
        return

    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Sätt ANTHROPIC_API_KEY i .env eller miljön.")

    if args.kommando == "sammanfattning":
        _run_sammanfattning(args.studies, args.db)
        return

    if args.kommando == "tolka":
        _run_tolka(args.studie.resolve(), args.db)
        return

    _run_generera(getattr(args, "fraga", None), getattr(args, "db", DB_DEFAULT))


if __name__ == "__main__":
    main()
