"""Point-5 deep tests: media_call_guard persistence + release + circuits."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from pipeline.custom_pipeline.media_call_guard import (
    claim_create,
    is_circuit_open,
    open_circuit,
    prompt_fingerprint,
    release_claim,
    reset_runtime_state,
)


def _iso_guard() -> Path:
    root = Path(tempfile.mkdtemp())
    path = root / "media_call_guard.json"
    os.environ["AMP_MEDIA_GUARD_STATE"] = str(path)
    reset_runtime_state()
    return path


def test_claim_dedupe_same_process():
    path = _iso_guard()
    fp = prompt_fingerprint("hello world", aspect="9:16", duration=5)
    assert claim_create("agnes", fp) is True
    assert claim_create("agnes", fp) is False
    assert path.is_file()


def test_persist_survives_process_reset():
    path = _iso_guard()
    fp = prompt_fingerprint("persist me", aspect="9:16", duration=4)
    assert claim_create("kling", fp) is True
    # Simulate new process
    reset_runtime_state()
    assert claim_create("kling", fp) is False
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data.get("created"), dict)
    assert any("kling:" in k for k in data["created"])


def test_release_allows_retry():
    _iso_guard()
    fp = prompt_fingerprint("retry after fail", aspect="9:16", duration=6)
    assert claim_create("agnes", fp) is True
    release_claim("agnes", fp, reason="test_fail")
    assert claim_create("agnes", fp) is True


def test_circuit_blocks_and_persists():
    path = _iso_guard()
    open_circuit("openrouter_video", 30, reason="403")
    assert is_circuit_open("openrouter_video") is True
    fp = prompt_fingerprint("blocked", aspect="9:16", duration=5)
    assert claim_create("openrouter_video", fp) is False
    reset_runtime_state()
    assert is_circuit_open("openrouter_video") is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "openrouter_video" in data.get("circuits", {})


def test_atomic_write_valid_json_under_claims():
    path = _iso_guard()
    for i in range(20):
        fp = prompt_fingerprint(f"batch {i}", aspect="9:16", duration=3)
        claim_create("google_image", fp)
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert len(data["created"]) == 20


def test_legacy_list_created_loads():
    path = _iso_guard()
    path.write_text(
        json.dumps({"created": ["agnes:abc123"], "circuits": {}}),
        encoding="utf-8",
    )
    reset_runtime_state()
    # fingerprint in legacy key is full key after provider:
    # claim_create builds provider:fp — use exact legacy key via release path
    # Direct: claiming agnes:abc123 equivalent
    assert claim_create("agnes", "abc123") is False


def test_corrupt_file_does_not_crash():
    path = _iso_guard()
    path.write_text("{broken", encoding="utf-8")
    reset_runtime_state()
    fp = prompt_fingerprint("after corrupt", aspect="9:16", duration=1)
    assert claim_create("luma", fp) is True


def test_different_fingerprints_independent():
    _iso_guard()
    a = prompt_fingerprint("shot A", aspect="9:16", duration=5)
    b = prompt_fingerprint("shot B", aspect="9:16", duration=5)
    assert a != b
    assert claim_create("agnes", a) is True
    assert claim_create("agnes", b) is True


def test_industrial_regression_claim_still_works():
    """Keep compatibility with earlier industrial test pattern."""
    path = _iso_guard()
    fp = prompt_fingerprint("same prompt", aspect="9:16", duration=5)
    assert claim_create("testprov", fp) is True
    assert claim_create("testprov", fp) is False
    reset_runtime_state()
    assert claim_create("testprov", fp) is False


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed.append((fn.__name__, exc))
            print(f"FAIL {fn.__name__}: {exc}")
    if failed:
        raise SystemExit(f"{len(failed)}/{len(tests)} failed")
    print(f"all {len(tests)} point-5 tests passed")
