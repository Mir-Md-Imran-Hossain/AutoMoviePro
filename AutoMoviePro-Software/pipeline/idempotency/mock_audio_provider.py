"""Deterministic mock audio/TTS provider (BUILD-04B)."""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class MockAudioBehavior(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MALFORMED = "malformed"
    EMPTY = "empty"
    REJECTION = "rejection"
    SLOW = "slow"
    UNKNOWN = "unknown"


def _minimal_wav(path: Path, *, duration_ms: int = 500) -> None:
    sample_rate = 22050
    n_samples = int(sample_rate * duration_ms / 1000)
    data = b"\x00\x01" * n_samples
    riff = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        len(data),
    )
    path.write_bytes(riff + data)


@dataclass
class MockAudioProvider:
    behavior: MockAudioBehavior = MockAudioBehavior.SUCCESS
    slow_delay_sec: float = 0.05
    invocation_count: int = field(default=0, init=False)
    last_generation_id: str = field(default="", init=False)

    def reset(self) -> None:
        self.invocation_count = 0
        self.last_generation_id = ""

    def synthesize(self, *, out_path: Path, text: str = "") -> Path:
        self.invocation_count += 1
        self.last_generation_id = f"mock-audio-{self.invocation_count:04d}"
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wav = out_path.with_suffix(".wav")

        if self.behavior == MockAudioBehavior.TIMEOUT:
            raise TimeoutError("TTS timeout — response lost")
        if self.behavior == MockAudioBehavior.NETWORK:
            raise ConnectionError("temporary network failure")
        if self.behavior == MockAudioBehavior.REJECTION:
            raise ValueError("invalid voice configuration")
        if self.behavior == MockAudioBehavior.UNKNOWN:
            raise TimeoutError("provider accepted but response lost")
        if self.behavior == MockAudioBehavior.SLOW:
            time.sleep(self.slow_delay_sec)
        if self.behavior == MockAudioBehavior.EMPTY:
            wav.write_bytes(b"")
            return wav
        if self.behavior == MockAudioBehavior.MALFORMED:
            wav.write_bytes(b"NOT_AUDIO")
            return wav

        _minimal_wav(wav)
        return wav


_GLOBAL_MOCK = MockAudioProvider()


def get_mock_audio_provider() -> MockAudioProvider:
    return _GLOBAL_MOCK


def reset_mock_audio_provider() -> None:
    _GLOBAL_MOCK.reset()
