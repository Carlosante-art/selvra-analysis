"""Blind analysis: frozen analysis code, and a record of every run.

The workflow (ANALYSMALL.md, step 4b):

1. The analysis code is written and tested on synthetic data only (make demo).
2. Its commit hash is written into the pre-registration as
       **Frusen analyskod:** <hash>
   and committed. From then on the code is frozen.
3. On real data, run_analysis() refuses to run if the analysis code, the pipeline
   (src/, transform/) or the pre-registration's own steps have changed since that
   commit, or have uncommitted changes.
4. Every run writes a record to korningar/: the result, the commit, the data version
   (checksums of the input files, never their names) and tool versions. The first
   run on real data is the confirmatory one. Later runs on real data are marked as
   reruns, so a result that was run until it looked right is visible in the history.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[2]
FROZEN_RE = re.compile(r"\*\*Frusen analyskod:\*\*\s*`?([0-9a-f]{7,40})`?")
PIPELINE_PATHS = ["src", "transform", "pyproject.toml", "uv.lock"]


class NotFrozenError(RuntimeError):
    pass


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def frozen_commit(analysis_dir: Path) -> str | None:
    prereg = analysis_dir / "forregistrering.md"
    match = FROZEN_RE.search(prereg.read_text()) if prereg.exists() else None
    return match.group(1) if match else None


def check_frozen(analysis_dir: Path) -> str:
    """Return the frozen commit if nothing the result depends on has changed since it."""
    commit = frozen_commit(analysis_dir)
    if commit is None:
        raise NotFrozenError(
            f"{analysis_dir.name}: no '**Frusen analyskod:** <hash>' in forregistrering.md. "
            "Develop on synthetic data (make demo), commit, then freeze the hash.")
    rel = analysis_dir.resolve().relative_to(ROOT)
    code = [str(p.relative_to(ROOT)) for p in analysis_dir.iterdir()
            if p.suffix in {".py", ".sql", ".R"}]
    paths = [*PIPELINE_PATHS, *code]
    changed = _git("diff", "--name-only", commit, "HEAD", "--", *paths).splitlines()
    uncommitted = _git("status", "--porcelain", "--", *paths, *code).splitlines()
    prereg = analysis_dir / "forregistrering.md"
    then = _git("show", f"{commit}:{rel}/forregistrering.md")
    if FROZEN_RE.sub("", then).strip() != FROZEN_RE.sub("", prereg.read_text()).strip():
        changed.append(f"{rel}/forregistrering.md (changed after freezing; only the hash line may be added)")
    if changed or uncommitted:
        raise NotFrozenError(
            f"{analysis_dir.name}: code changed after the frozen commit {commit}:\n  "
            + "\n  ".join(changed + uncommitted))
    return commit


def data_version(con: duckdb.DuckDBPyConnection) -> dict:
    files = con.execute(
        "select kind, sha256, bytes, n_rows from raw.source_files order by kind, sha256").df()
    synthetic = con.execute(
        "select coalesce(bool_and(source_device_id = 'SYNTHETIC'), false) "
        "from raw.clarity_events where event_type = 'EGV'").fetchone()[0]
    combined = "".join(files["sha256"])
    return {
        "synthetic": bool(synthetic),
        "files": files.to_dict(orient="records"),
        "fingerprint": _sha256_text(combined),
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def run_analysis(analysis_dir: Path, con: duckdb.DuckDBPyConnection, result: dict) -> Path:
    """Write a run record for `result`. On real data the code must be frozen."""
    analysis_dir = analysis_dir.resolve()
    data = data_version(con)
    if data["synthetic"]:
        frozen, kind = frozen_commit(analysis_dir), "development (synthetic data)"
    else:
        frozen = check_frozen(analysis_dir)
        out_dir = analysis_dir / "korningar"
        earlier = [json.loads(p.read_text()) for p in out_dir.glob("*.json")] if out_dir.exists() else []
        real = [r for r in earlier if not r["data"]["synthetic"]]
        kind = "confirmatory (first run on real data)" if not real else f"rerun {len(real)} on real data"

    head = _git("rev-parse", "HEAD")
    record = {
        "analysis": analysis_dir.name,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "kind": kind,
        "commit": head,
        "frozen_commit": frozen,
        "working_tree_clean": _git("status", "--porcelain") == "",
        "data": data,
        "parameters": yaml.safe_load((ROOT / "transform" / "dbt_project.yml").read_text())["vars"],
        "versions": {
            "python": platform.python_version(),
            **{p: version(p) for p in ("duckdb", "dbt-core", "dbt-duckdb", "numpy", "pandas")},
        },
        "result": result,
    }
    out_dir = analysis_dir / "korningar"
    out_dir.mkdir(exist_ok=True)
    stamp = record["run_at"].replace(":", "").replace("-", "")
    path = out_dir / f"{stamp}_{'synthetic' if data['synthetic'] else 'real'}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str) + "\n")
    return path
