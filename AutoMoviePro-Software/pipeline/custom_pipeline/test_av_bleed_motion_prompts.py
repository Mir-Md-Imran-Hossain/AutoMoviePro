"""Tests for Agnes audio bleed fix, EN native reuse, motion presets, prompt policy."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from pipeline.custom_pipeline.media_prompts import (
    build_detailed_media_prompt,
    narration_to_visual_cues,
)
from pipeline.custom_pipeline.motion_presets import (
    MOTION_PRESET_IDS,
    build_smooth_kenburns_filter,
    is_trusted_ffmpeg_filter,
    motion_directive_for_shot,
    pick_motion_preset,
)


def test_compose_fit_uses_explicit_av_map():
    """ffmpeg must map 0:v + 1:a so Agnes EN audio never underlays BN TTS."""
    import inspect

    from pipeline.custom_pipeline import media_compose as mc

    src = inspect.getsource(mc.fit_shot_for_language)
    assert '"0:v:0"' in src or "'0:v:0'" in src
    assert '"1:a:0"' in src or "'1:a:0'" in src
    assert "-map" in src


def test_motion_presets_rotate_and_smooth():
    ids = [pick_motion_preset(i) for i in range(1, 9)]
    assert len(set(ids)) >= 4  # variety across shots
    vf = build_smooth_kenburns_filter(w=1080, h=1920, duration=6.0, preset="slow_zoom_in")
    assert "1080x1920" in vf
    assert ":d=150" in vf or ":d=149" in vf or ":d=151" in vf
    assert "0.00045" in vf or "0.0004" in vf
    # Reject shaky truncated Grok filter
    bad = "zoompan=z='min(zoom+0.0012,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=17"
    assert is_trusted_ffmpeg_filter(bad, w=1080, h=1920, duration=6.0) is False
    good = build_smooth_kenburns_filter(w=1080, h=1920, duration=6.0, preset="pan_right")
    assert is_trusted_ffmpeg_filter(good, w=1080, h=1920, duration=6.0) is True


def test_motion_directive_unique_labels():
    labels = []
    for i in range(1, len(MOTION_PRESET_IDS) + 1):
        d = motion_directive_for_shot(i, duration=7.0, w=1080, h=1920)
        labels.append(d["animation_type"])
        assert "d=" in d["ffmpeg_filter"]
    assert len(set(labels)) == len(MOTION_PRESET_IDS)


def test_video_prompt_is_silent_no_dialogue_quote():
    scene = {
        "shot_number": 1,
        "visual_prompt": "Young man holds glowing phone in dark room, cyan LED desk",
        "source_character_details": "25yo male black hoodie",
        "source_camera_angle": "medium close-up",
        "source_lighting": "cyan rim light",
        "source_voiceover_script": "Wow, was this picture really taken with a phone?",
        "motion_directives": {"camera_movement": "slow push in", "character_action": "shows phone"},
    }
    vp = build_detailed_media_prompt(
        scene, aspect_ratio="9:16", for_video=True, narration_text=scene["source_voiceover_script"]
    )
    low = vp.lower()
    assert "silent video" in low
    assert "no speech" in low or "no dialogue" in low
    assert "must show" in low
    assert "visual description" in low
    # Must NOT ask model to speak the VO line as dialogue
    assert "spoken beat / scene intent (match this narration visually)" not in low


def test_image_prompt_has_must_show_and_visual_early():
    scene = {
        "shot_number": 3,
        "visual_prompt": "Phone screen AI night mode UI, darkness behind",
        "source_character_details": "same male hoodie",
        "source_camera_angle": "OTS phone screen",
        "source_lighting": "screen glow",
        "source_voiceover_script": "First up is Super Dark AI Night. It captures daylight-quality photos.",
    }
    ip = build_detailed_media_prompt(
        scene, for_video=False, narration_text=scene["source_voiceover_script"]
    )
    assert "MUST SHOW" in ip
    assert ip.lower().index("visual description") < ip.lower().index("scene intent")
    cues = narration_to_visual_cues(scene["source_voiceover_script"])
    assert "AI" in cues or "Night" in cues or "Dark" in cues


def test_sanitize_master_and_en_reuse(tmp_path):
    from pipeline.custom_pipeline.master_audio import (
        find_native_audio,
        native_audio_dir,
        probe_has_audio,
        sanitize_master_clip,
    )

    clips = tmp_path / "Video Clips"
    clips.mkdir()
    # Fake: write tiny files + mock probe/extract/strip
    master = clips / "S01.mp4"
    master.write_bytes(b"0" * 2000)
    native_dir = native_audio_dir(clips)
    native = native_dir / "S01.m4a"
    native.write_bytes(b"a" * 2000)

    with mock.patch(
        "pipeline.custom_pipeline.master_audio.probe_has_audio",
        side_effect=[True, False],  # before strip True, after False
    ), mock.patch(
        "pipeline.custom_pipeline.master_audio.extract_audio_track",
        return_value=native,
    ), mock.patch(
        "pipeline.custom_pipeline.master_audio.strip_audio_inplace",
        return_value=True,
    ):
        info = sanitize_master_clip(
            master, shot_key="S01", video_clips_dir=clips, provider="agnes"
        )
    assert info["had_audio"] is True
    assert info["native_audio_path"]
    assert find_native_audio(clips, 1) == native


def test_normalize_render_rebuilds_motion():
    from pipeline.custom_pipeline.visual_render import normalize_render_payload

    source = {
        "script_scenes": [
            {
                "shot_number": 1,
                "shot_duration_seconds": 6,
                "visual_prompt": "a",
                "voiceover_script": "hello phone camera",
            },
            {
                "shot_number": 2,
                "shot_duration_seconds": 7,
                "visual_prompt": "b",
                "voiceover_script": "night AI",
            },
        ]
    }
    payload = {
        "production_metadata": {"aspect_ratio": "9:16"},
        "render_scenes": [
            {
                "shot_number": 1,
                "render_type": "IMAGE",
                "visual_prompt": "a",
                "motion_directives": {
                    "ffmpeg_filter": "zoompan=z='min(zoom+0.001,1.2)':d=17:s=1920x1080",
                    "animation_type": "Gentle Pan Right",
                },
            },
            {
                "shot_number": 2,
                "render_type": "IMAGE",
                "visual_prompt": "b",
                "motion_directives": {"animation_type": "Gentle Tilt Up"},
            },
        ],
    }
    out = normalize_render_payload(payload, source, aspect_ratio="9:16")
    m1 = out["render_scenes"][0]["motion_directives"]
    m2 = out["render_scenes"][1]["motion_directives"]
    assert "d=17" not in m1["ffmpeg_filter"]
    assert "1080x1920" in m1["ffmpeg_filter"]
    assert m1["motion_preset"] != m2["motion_preset"] or m1["animation_type"] != m2["animation_type"]
