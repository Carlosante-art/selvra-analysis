from pathlib import Path

import duckdb
import pandas as pd

from selvra_analysis.ingest_supabase import store


def rows() -> pd.DataFrame:
    return pd.DataFrame({
        "reading_at": pd.to_datetime(["2025-10-26 00:30:00+00:00", "2025-10-26 00:35:00+00:00"]),
        "value_mgdl": [110, 39],
        "trend": ["Flat", "SingleDown"],
    })


def test_store_snapshots_and_records_version(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    digest = store(rows(), db, tmp_path / "snap")
    again = store(rows().iloc[::-1], db, tmp_path / "snap")
    assert digest == again, "same readings in any order give the same data version"
    snapshot = next((tmp_path / "snap").glob("share_*.csv")).read_text()
    assert snapshot.splitlines()[1].startswith("2025-10-26T00:30:00Z,110")
    with duckdb.connect(str(db)) as con:
        assert con.execute("select count(*) from raw.share_readings").fetchone()[0] == 2
        assert con.execute("select count(*) from raw.clarity_events").fetchone()[0] == 0
        kind, sha = con.execute("select kind, sha256 from raw.source_files").fetchone()
        assert (kind, sha) == ("dexcom_share", digest)


def test_env_file_values_are_literal(tmp_path: Path, monkeypatch) -> None:
    from selvra_analysis.ingest_supabase import read_env_file
    env = tmp_path / ".env"
    env.write_text('# comment\nX_URL="postgresql://u:p$a#ss@h:5432/db"\nexport X_ID=abc\n')
    monkeypatch.delenv("X_URL", raising=False)
    monkeypatch.delenv("X_ID", raising=False)
    read_env_file(env)
    import os
    assert os.environ["X_URL"] == "postgresql://u:p$a#ss@h:5432/db"
    assert os.environ["X_ID"] == "abc"
