"""Dreamers minne: vad studierna lärt, och öppna hypoteser — en YAML-fil per studiemapp-rot.

Minnet är det som gör nästa förslag bättre än förra: varje dom skrivs hit, och
skannerns frågor köar här tills de blir studier. Hit flyttad ur dreamer.py
2026-10-28 (separera när filen fortsätter att växa); dreamer återexporterar
namnen, så gamla importvägar gäller.
"""

from __future__ import annotations

from pathlib import Path

import yaml

STUDIES_DIR = Path("studies")
MINNE_FILE = "minne.yml"


def _minne_path(studies_dir: Path) -> Path:
    return studies_dir / MINNE_FILE


def _load_minne(studies_dir: Path) -> str:
    path = _minne_path(studies_dir)
    if not path.exists():
        return ""
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return ""

    studier = data.get("studier", [])
    hypoteser = data.get("oppna_hypoteser", [])

    if not studier and not hypoteser:
        return ""

    lines = ["MINNE (tidigare studier och öppna hypoteser):"]
    if studier:
        lines.append("\nGenomförda och pågående studier:")
        for s in studier:
            beslut = s.get("beslut", "?")
            lines.append(f"  [{s.get('id', '?')}] {s.get('fraga', '')} → {beslut}")
            if s.get("lardom"):
                lines.append(f"    Lärdom: {s['lardom']}")
            if s.get("nasta_steg"):
                lines.append(f"    Nästa steg: {s['nasta_steg']}")
    if hypoteser:
        lines.append("\nÖppna hypoteser (ännu inte studerade):")
        for h in hypoteser:
            lines.append(f"  - {h}")
    lines.append("\nUndvik att generera studier som redan finns ovan.")
    return "\n".join(lines)


def _init_minne(studies_dir: Path) -> None:
    path = _minne_path(studies_dir)
    if path.exists():
        return

    studier = []
    for folder in sorted(studies_dir.glob("[0-9][0-9][0-9]-*")):
        if not (folder / "studie.yml").exists():
            continue
        try:
            spec = yaml.safe_load((folder / "studie.yml").read_text()) or {}
        except yaml.YAMLError:
            continue

        if (folder / "slutrapport.md").exists():
            st = "klar"
            beslut = "obestämt"
        elif (folder / "las.json").exists():
            st = "pågår"
            beslut = "pågår"
        else:
            st = "ej_last"
            beslut = "pågår"

        studier.append({
            "id": folder.name,
            "fraga": spec.get("fraga", folder.name),
            "status": st,
            "beslut": beslut,
            "lardom": "",
            "nasta_steg": "",
        })

    data = {"studier": studier, "oppna_hypoteser": []}
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False))


def _add_study_to_minne(studies_dir: Path, study_id: str, fraga: str) -> None:
    path = _minne_path(studies_dir)
    if not path.exists():
        _init_minne(studies_dir)
    data = yaml.safe_load(path.read_text()) or {}
    studier = data.get("studier", [])
    if not any(s.get("id") == study_id for s in studier):
        studier.append({
            "id": study_id,
            "fraga": fraga,
            "status": "ej_last",
            "beslut": "pågår",
            "lardom": "",
            "nasta_steg": "",
        })
        data["studier"] = studier
        # Frågan är inte längre en öppen hypotes när den blivit en studie.
        data["oppna_hypoteser"] = [h for h in (data.get("oppna_hypoteser") or []) if h != fraga]
        path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False))


def lagg_till_hypoteser(fragor: list[str], studies_dir: Path = STUDIES_DIR) -> int:
    """Lägg frågor till minnets öppna hypoteser. Returnerar antal nya."""
    _init_minne(studies_dir)
    path = _minne_path(studies_dir)
    data = yaml.safe_load(path.read_text()) or {}
    hypoteser = data.get("oppna_hypoteser") or []
    studerade = {s.get("fraga", "") for s in data.get("studier", [])}

    nya = [f for f in fragor if f not in hypoteser and f not in studerade]
    if nya:
        data["oppna_hypoteser"] = hypoteser + nya
        path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False))
    return len(nya)


def _update_minne(
    studies_dir: Path,
    study_id: str,
    lardom: str,
    nasta_steg: str,
    beslut: str,
) -> None:
    path = _minne_path(studies_dir)
    if not path.exists():
        _init_minne(studies_dir)
    data = yaml.safe_load(path.read_text()) or {}
    studier = data.get("studier", [])

    for s in studier:
        if s.get("id") == study_id:
            s["lardom"] = lardom
            s["nasta_steg"] = nasta_steg
            s["beslut"] = beslut
            s["status"] = "klar"
            break
    else:
        studier.append({
            "id": study_id,
            "fraga": study_id,
            "status": "klar",
            "beslut": beslut,
            "lardom": lardom,
            "nasta_steg": nasta_steg,
        })

    data["studier"] = studier
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False))


def show_minne(studies_dir: Path) -> str:
    path = _minne_path(studies_dir)
    if not path.exists():
        return "Inget minne ännu. Kör `make dreamer` eller `make tolka` för att bygga upp det."
    data = yaml.safe_load(path.read_text()) or {}
    studier = data.get("studier", [])
    hypoteser = data.get("oppna_hypoteser", [])

    labels = {"klar": "klar", "pågår": "pågår", "ej_last": "ej låst"}
    lines = [f"=== Dreamer-minne ({len(studier)} studie(r)) ===\n"]
    for s in studier:
        st = labels.get(s.get("status", "?"), s.get("status", "?"))
        beslut = s.get("beslut", "?")
        lines.append(f"[{s.get('id', '?')}]  {st} / {beslut}")
        lines.append(f"  Fråga: {s.get('fraga', '')}")
        if s.get("lardom"):
            lines.append(f"  Lärdom: {s['lardom']}")
        if s.get("nasta_steg"):
            lines.append(f"  Nästa: {s['nasta_steg']}")
        lines.append("")

    if hypoteser:
        lines.append("Öppna hypoteser:")
        for h in hypoteser:
            lines.append(f"  - {h}")

    return "\n".join(lines)
