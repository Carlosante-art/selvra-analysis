"""Integritetsvakten: metoderna är öppna, människors data är det aldrig.

Repot är publikt. Den här vakten gör gränsen mekanisk: inga persondatafiler i
indexet, inga hemligheter i spårat innehåll. Faller den har något hamnat på fel
sida gränsen — åtgärda läckan, mjuka aldrig upp vakten (docs/INTEGRITET.md).

Mönstren för hemligheter byggs med konkatenering så att vaktens egen fil
aldrig triggar sig själv.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent

# Sökvägar som aldrig får spåras: persondata, databaser, nycklar, miljöfiler.
FORBJUDNA_SOKVAGAR = re.compile(
    r"^data/|\.duckdb$|push\.json$|person\.yml$|\.pem$|^\.env|/\.env|\.env\.save$"
    r"|/snapshots/|/garmin/|^dashboard/index\.html$")
TILLATNA_UNDANTAG = {
    "data/handelser.mall.csv",      # tom mall, inga händelser
    "data/raw/.gitkeep",
    "data/raw/clarity/.gitkeep",
}

# Hemligheter och personuppgifter som aldrig får finnas i spårat innehåll.
HEMLIGT = [re.compile(p, re.IGNORECASE) for p in (
    "sk-" + "ant-",                      # Anthropic-nycklar
    "GC" + "DC_",                        # Garmin-token
    "soder" + "as",                      # lösenord/e-post som läckt i chatt
    "ckarjal" + "ainen",                 # privata e-postadresser
    r"@gma" + r"il\.com",
    "BEGIN " + r"(EC |RSA )?PRIVATE KEY",
    "DEXCOM_" + r"PASSWORD\s*=\s*[^.\s]",   # värde, inte platshållare
    "NIGHTSCOUT_" + r"TOKEN\s*=\s*[^.\s]",
)]

TEXTFILER = (".py", ".md", ".yml", ".yaml", ".sql", ".sh", ".toml", ".cfg",
             ".json", ".csv", ".qmd", ".txt", "Makefile", ".gitignore")


def _sparade() -> list[str]:
    ut = subprocess.run(["git", "ls-files"], cwd=ROT, capture_output=True,  # noqa: S607
                        text=True, check=True)
    return ut.stdout.splitlines()


def test_inga_persondatafiler_i_indexet() -> None:
    fel = [f for f in _sparade()
           if FORBJUDNA_SOKVAGAR.search(f) and f not in TILLATNA_UNDANTAG]
    assert not fel, f"persondata/nycklar spårade i publikt repo: {fel}"


def test_inga_hemligheter_i_sparat_innehall() -> None:
    fel = []
    for namn in _sparade():
        fil = ROT / namn
        if not (namn.endswith(TEXTFILER) or fil.suffix == ""):
            continue
        if not fil.exists():
            continue
        text = fil.read_text(errors="ignore")
        fel += [f"{namn}: mönster {i}" for i, m in enumerate(HEMLIGT) if m.search(text)]
    assert not fel, f"hemlighet/personuppgift i spårad fil: {fel}"


def test_mallfilen_ar_bara_en_mall() -> None:
    """data/handelser.mall.csv visar formatet med fiktiva exempel från mars 2025.
    Riktiga händelser hör hemma i data/raw/ (gitignorerat) — en rad utanför
    exempelmånaden är sannolikt en riktig händelse på väg ut i det öppna."""
    rader = (ROT / "data/handelser.mall.csv").read_text().strip().splitlines()[1:]
    fel = [r for r in rader if not r.startswith("2025-03")]
    assert not fel, f"rader utanför exempelmånaden i mallen: {fel}"