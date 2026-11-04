"""The 5.5 replication regenerates from tracked files alone, and its raw rows carry no host state.

These run on a fresh clone with no model, no key and no results/: unlike the original sweeps,
the replication's raw rows are committed under replication/raw/.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from envelope_shift.analysis import replication

REPO = Path(__file__).resolve().parents[1]
_UUID = re.compile("[0-9a-f]{8}-[0-9a-f]{4}-" + r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_PATHS = ("/" + "tmp/", "/" + "root/", "/" + "home/")


def _raw_files() -> list[Path]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--", "replication/raw"],
                         check=True, capture_output=True).stdout
    return [REPO / p for p in out.decode().split("\0") if p]


@pytest.mark.replication
def test_every_replication_table_regenerates_byte_for_byte_from_the_committed_raw_rows():
    assert replication.check() == []


def test_the_replication_pools_name_only_committed_sweeps():
    from envelope_shift import pool

    tracked = {p.parent.name for p in _raw_files()}
    for name, sweeps in pool.load_manifest(replication.MANIFEST).items():
        assert set(sweeps) <= tracked, f"pool {name} names an untracked sweep"


def test_committed_raw_rows_carry_no_session_id_uuid_or_host_path():
    files = _raw_files()
    assert files, "no committed replication rows: the guard is vacuous"
    for path in files:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            assert not _UUID.search(line), f"{path.name}:{n} carries a UUID-shaped id"
            assert not any(s in line for s in _PATHS), f"{path.name}:{n} carries a host path"
            assert '"session_id"' not in line and '"signature"' not in line


def test_sanitize_keeps_the_condition_and_drops_ids():
    events = [
        {"type": "system", "subtype": "init", "model": "m", "tools": [], "apiKeySource": "none",
         "session_id": "s", "uuid": "u", "original_cwd": "/x"},
        {"type": "rate_limit_event", "rate_limit_info": {}},
        {"type": "assistant", "message": {"id": "msg_1", "model": "m", "usage": {"output_tokens": 3},
                                          "content": [{"type": "thinking", "signature": "sig"}, {"type": "text", "text": "{}"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "{}", "session_id": "s",
         "modelUsage": {"m": {}}, "uuid": "u"},
    ]
    kept = replication.sanitize_events(events)
    blob = json.dumps(kept)
    assert [e["type"] for e in kept] == ["system", "assistant", "result"]
    assert kept[0] == {"type": "system", "subtype": "init", "model": "m", "tools": [], "apiKeySource": "none"}
    assert kept[1]["message"]["content_types"] == ["thinking", "text"]
    assert "session_id" not in blob and "sig" not in blob and "msg_1" not in blob and "/x" not in blob
    assert kept[2]["modelUsage"] == {"m": {}}
