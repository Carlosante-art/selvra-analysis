"""Record which input files a database was built from.

raw.source_files holds one row per loaded file: its SHA-256, size and row count.
File names are not stored, because Clarity names exports after the patient. The
checksums identify the exact data version in every analysis result without
revealing anything about it.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record(con: duckdb.DuckDBPyConnection, kind: str, files: list[tuple[Path, int]]) -> None:
    """Replace the manifest rows for `kind` ('clarity' or 'event_log') with `files` (path, rows)."""
    rows = pd.DataFrame(
        [
            {"kind": kind, "sha256": sha256(p), "bytes": p.stat().st_size, "n_rows": n,
             "loaded_at": datetime.now(UTC).isoformat(timespec="seconds")}
            for p, n in files
        ],
        columns=["kind", "sha256", "bytes", "n_rows", "loaded_at"],
    )
    con.execute("create schema if not exists raw")
    con.execute(
        "create table if not exists raw.source_files "
        "(kind varchar, sha256 varchar, bytes bigint, n_rows bigint, loaded_at varchar)"
    )
    con.execute("delete from raw.source_files where kind = ?", [kind])
    con.register("manifest_df", rows)
    con.execute("insert into raw.source_files select * from manifest_df")
    con.unregister("manifest_df")
