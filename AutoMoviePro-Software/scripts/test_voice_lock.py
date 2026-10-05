"""Feature 2 tests: Charon / male voice lock (no network required)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.lang_config import (  # noqa: E402
    MASTER_VOICE_NAME,
    edge_voice_chain,
    locked_voice_chain,
    resolve_edge_voice,
    resolve_locked_voice,
)
from pipeline.master_lang import narration_sidecar_matches  # noqa: E402
from pipeline.tts_google import _speak_prompt  # noqa: E402
from pipeline.tts_reuse import tts_matches_text, write_tts_sidecar  # noqa: E402


def test_resolve_locked_voice_rewrites_female_and_empty():
    assert resolve_locked_voice("") == "Charon"
    assert resolve_locked_voice("Kore") == "Charon"
    assert resolve_locked_voice("kore") == "Charon"
    assert resolve_locked_voice("Aoede") == "Charon"
    assert resolve_locked_voice("Leda") == "Charon"
    assert resolve_locked_voice("Zephyr") == "Charon"
    assert resolve_locked_voice("Puck") == "Charon"
    assert resolve_locked_voice("Fenrir") == "Charon"
    assert resolve_locked_voice("Charon") == "Charon"
    assert resolve_locked_voice("charon") == "Charon"
    assert resolve_locked_voice("UnknownVoice") == "Charon"


def test_male_contract_alts_allowed_explicitly():
    assert resolve_locked_voice("Achird", language_hint="en") == "Achird"
    assert resolve_locked_voice("Orus", language_hint="bn") == "Orus"
    # Female cannot sneak in via alt request
    assert resolve_locked_voice("Kore", language_hint="en") == "Charon"
    chain = locked_voice_chain("en")
    assert chain[0] == "Charon"
    assert "Kore" not in chain
    assert "Aoede" not in chain


def test_edge_voice_never_female_or_gemini_name():
    assert resolve_edge_voice("Charon", language_hint="en") == "en-US-GuyNeural"
    assert resolve_edge_voice("Kore", language_hint="en") == "en-US-GuyNeural"
    assert resolve_edge_voice("en-US-JennyNeural", language_hint="en") == "en-US-GuyNeural"
    assert resolve_edge_voice("bn-IN-NabanitaNeural", language_hint="bn") == "bn-IN-BashkarNeural"
    assert resolve_edge_voice("", language_hint="hi") == "hi-IN-MadhurNeural"
    assert resolve_edge_voice("en-US-GuyNeural", language_hint="en") == "en-US-GuyNeural"
    for lang in ("en", "bn", "hi", "ur", "ta", "ml"):
        for v in edge_voice_chain(lang):
            assert "Neural" in v
            assert "Jenny" not in v
            assert "Nabanita" not in v


def test_speak_prompt_locks_charon_identity():
    prompt = _speak_prompt(
        "Today we review the Pixel 9a.",
        lang="en",
        contract={"register": "documentary", "pace_hint": "steady"},
        voice_name="Charon",
    )
    assert "Charon" in prompt
    assert "adult male" in prompt
    assert "Kore" in prompt  # mentioned as forbidden


def test_tts_sidecar_requires_matching_voice(tmp_path: Path | None = None):
    work = ROOT / "output" / "_voice_lock_test"
    work.mkdir(parents=True, exist_ok=True)
    audio = work / "narration.m4a"
    audio.write_bytes(b"fake" * 300)
    write_tts_sidecar(audio, "Today we review the Pixel 9a.", voice_name="Charon")
    assert tts_matches_text(audio, "Today we review the Pixel 9a.", voice_name="Charon")
    assert not tts_matches_text(audio, "Today we review the Pixel 9a.", voice_name="Kore")
    assert not tts_matches_text(audio, "Different line.", voice_name="Charon")
    stored = (work / "narration.m4a.txt").read_text(encoding="utf-8")
    assert narration_sidecar_matches(stored, "Today we review the Pixel 9a.")
    audio.unlink(missing_ok=True)
    (work / "narration.m4a.txt").unlink(missing_ok=True)


def test_master_voice_constant():
    assert MASTER_VOICE_NAME == "Charon"


if __name__ == "__main__":
    test_resolve_locked_voice_rewrites_female_and_empty()
    test_male_contract_alts_allowed_explicitly()
    test_edge_voice_never_female_or_gemini_name()
    test_speak_prompt_locks_charon_identity()
    test_tts_sidecar_requires_matching_voice()
    test_master_voice_constant()
    print("OK feature2 charon voice lock")
