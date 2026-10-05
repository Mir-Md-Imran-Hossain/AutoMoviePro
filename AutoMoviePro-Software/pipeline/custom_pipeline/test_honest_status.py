"""Point-4 deep tests: honest ok / partial / failed / shippable (no soft-ok)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from pipeline.custom_pipeline.honest_status import (
    finalize_language_results,
    honest_completion,
    honest_shippable,
)
from pipeline.custom_pipeline.job_state import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_SUCCEEDED,
    compute_shippable,
    new_job_state,
)
from pipeline.custom_pipeline.media_stage import run_media_stage


def test_honest_completion_matrix():
    assert honest_completion(success_count=0, expected_count=3)["failed"] is True
    assert honest_completion(success_count=0, expected_count=3)["ok"] is False
    p = honest_completion(success_count=2, expected_count=3)
    assert p["partial"] is True and p["ok"] is False
    f = honest_completion(success_count=3, expected_count=3)
    assert f["ok"] is True and f["partial"] is False
    # expected 0 never ok
    assert honest_completion(success_count=0, expected_count=0)["ok"] is False


def test_soft_ok_forbidden_one_lang():
    ship = honest_shippable(
        shared_success=3,
        shared_expected=3,
        finals_ok=["English"],
        expected_languages=["English", "Hindi"],
    )
    assert ship["shippable"] is False
    assert ship["partial"] is True
    assert ship["ok"] is False


def test_skip_compose_never_shippable():
    ship = honest_shippable(
        shared_success=3,
        shared_expected=3,
        finals_ok=[],
        expected_languages=[],
        skip_compose=True,
    )
    assert ship["shippable"] is False
    assert ship["partial"] is True  # shared succeeded


def test_errors_block_shippable():
    ship = honest_shippable(
        shared_success=3,
        shared_expected=3,
        finals_ok=["English"],
        expected_languages=["English"],
        shared_errors={"S02": "fail"},
    )
    assert ship["shippable"] is False


def test_cancel_blocks_shippable():
    ship = honest_shippable(
        shared_success=3,
        shared_expected=3,
        finals_ok=["English"],
        expected_languages=["English"],
        cancel_requested=True,
    )
    assert ship["shippable"] is False


def test_full_ship_ok():
    ship = honest_shippable(
        shared_success=2,
        shared_expected=2,
        finals_ok=["English", "Hindi"],
        expected_languages=["English", "Hindi"],
    )
    assert ship["shippable"] is True
    assert ship["ok"] is True
    assert ship["partial"] is False


def test_compute_shippable_syncs_state_status():
    st = new_job_state(package_root=Path("."), video_type="short")
    compute_shippable(
        st,
        shared_success=1,
        shared_expected=2,
        finals_ok=["English"],
        expected_languages=["English", "Hindi"],
    )
    assert st["status"] == STATUS_PARTIAL
    compute_shippable(
        st,
        shared_success=2,
        shared_expected=2,
        finals_ok=["English", "Hindi"],
        expected_languages=["English", "Hindi"],
    )
    assert st["status"] == STATUS_SUCCEEDED
    compute_shippable(
        st,
        shared_success=0,
        shared_expected=2,
        finals_ok=[],
        expected_languages=["English"],
    )
    assert st["status"] == STATUS_FAILED


def test_compose_any_is_not_ok():
    """Regression: compose_and_assemble_all must not ok=True on any()."""
    from pipeline.custom_pipeline.honest_status import honest_completion

    langs = ["English", "Hindi"]
    finals_ok = ["English"]
    status = honest_completion(success_count=len(finals_ok), expected_count=len(langs))
    assert status["ok"] is False
    assert status["partial"] is True


def test_media_stage_mocked_partial():
    with mock.patch(
        "pipeline.custom_pipeline.media_stage.generate_shared_media",
        return_value={
            "ok": False,
            "partial": True,
            "shot_count": 3,
            "success_count": 2,
            "errors": {"S03": "x"},
            "degraded": [],
        },
    ), mock.patch(
        "pipeline.custom_pipeline.media_stage.compose_and_assemble_all",
        return_value={
            "ok": False,
            "finals": {"English": {"ok": True}, "Hindi": {"ok": False}},
            "errors": {"final_Hindi": "x"},
        },
    ), mock.patch(
        "pipeline.custom_pipeline.media_stage.open_package"
    ) as op, mock.patch(
        "pipeline.custom_pipeline.media_stage.write_json"
    ):
        class P:
            image = Path(".")
            video_clips = Path(".")
            final_video = Path(".")
            file_dir = Path(".")

        op.return_value = P()
        report = run_media_stage(
            Path("."), languages=["English", "Hindi"], include_bangla=False
        )
    assert report["ok"] is False
    assert report["shippable"] is False
    assert report["partial"] is True


def test_media_stage_skip_compose_not_shippable():
    with mock.patch(
        "pipeline.custom_pipeline.media_stage.generate_shared_media",
        return_value={
            "ok": True,
            "shot_count": 2,
            "success_count": 2,
            "errors": {},
            "degraded": [],
        },
    ), mock.patch(
        "pipeline.custom_pipeline.media_stage.open_package"
    ) as op, mock.patch(
        "pipeline.custom_pipeline.media_stage.write_json"
    ):
        class P:
            image = Path(".")
            video_clips = Path(".")
            final_video = Path(".")
            file_dir = Path(".")

        op.return_value = P()
        report = run_media_stage(Path("."), skip_compose=True, languages=["English"])
    assert report["shippable"] is False


def test_finalize_language_results():
    results = {
        "English": {"ok": True, "shot_count": 2, "success_count": 2},
        "Hindi": {"ok": True, "shot_count": 2, "success_count": 1},
    }
    out = finalize_language_results(results, expected=["English", "Hindi"])
    assert out["ok"] is False
    assert out["partial"] is True
    assert "English" in out["ok_languages"]
    assert "Hindi" not in out["ok_languages"]


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
    print(f"all {len(tests)} point-4 tests passed")
