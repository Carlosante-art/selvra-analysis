"""Per-person dbt-variabler ur person.yml, som JSON för `dbt build --vars`.

En pensionärs promenad når 8 000 steg, inte en pendlare 10 000: trösklar är
personliga. Saknas filen eller nyckeln skrivs ett tomt objekt — dbt:s
standardvärden gäller då.

Usage:
    uv run python -m selvra_analysis.personvars testare-1   # -> {"high_steps_threshold": 8000}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

NYCKLAR = {"hoga_steg_troskel": "high_steps_threshold"}


def vars_for(person: str) -> dict:
    fil = Path("data/personer") / person / "person.yml"
    if not fil.exists():
        return {}
    conf = yaml.safe_load(fil.read_text()) or {}
    return {dbt: conf[yml] for yml, dbt in NYCKLAR.items() if yml in conf}


def main(argv: list[str] | None = None) -> None:
    person = (argv or sys.argv[1:])[0]
    print(json.dumps(vars_for(person)))


if __name__ == "__main__":
    main()
