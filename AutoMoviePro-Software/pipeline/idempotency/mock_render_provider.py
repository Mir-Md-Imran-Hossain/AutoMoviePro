"""Deterministic mock render provider (BUILD-04D)."""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class MockRenderBehavior(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    NETWORK = "network"
    FAILURE = "failure"
    UNKNOWN = "unknown"
    EMPTY = "empty"
    CORRUPT = "corrupt"
    PARTIAL = "partial"
    MISSING_AUDIO = "missing_audio"
    MISSING_VIDEO = "missing_video"
    SLOW = "slow"


def _minimal_mp4(path: Path, *, size_bytes: int = 9000, include_audio_marker: bool = True) -> None:
    """Write a minimal MP4-like container sufficient for container validation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ftyp = struct.pack(">I4s4sI", 24, b"ftyp", b"isom", 512)
    mdat_payload = b"\x00" * max(size_bytes - len(ftyp) - 8, 100)
    mdat = struct.pack(">I", 8 + len(mdat_payload)) + b"mdat" + mdat_payload
    path.write_bytes(ftyp + mdat)


@dataclass
class MockRenderProvider:
    behavior: MockRenderBehavior = MockRenderBehavior.SUCCESS
    slow_delay_sec: float = 0.05
    invocation_count: int = field(default=0, init=False)
    last_generation_id: str = field(default="", init=False)

    def reset(self) -> None:
        self.invocation_count = 0
        self.last_generation_id = ""

    def render(self, *, out_path: Path, manifest_summary: str = "") -> Path:
        self.invocation_count += 1
        self.last_generation_id = f"mock-render-{self.invocation_count:04d}"
        out_path = Path(out_path)

        if self.behavior == MockRenderBehavior.TIMEOUT:
            raise TimeoutError("render timeout — process lost")
        if self.behavior == MockRenderBehavior.NETWORK:
            raise ConnectionError("temporary filesystem failure")
        if self.behavior == MockRenderBehavior.FAILURE:
            raise RuntimeError("ffmpeg render failed")
        if self.behavior == MockRenderBehavior.UNKNOWN:
            raise TimeoutError("render accepted but output state unknown")
        if self.behavior == MockRenderBehavior.SLOW:
            time.sleep(self.slow_delay_sec)
        if self.behavior == MockRenderBehavior.EMPTY:
            out_path.write_bytes(b"")
            return out_path
        if self.behavior == MockRenderBehavior.CORRUPT:
            out_path.write_bytes(b"NOT_MP4_DATA")
            return out_path
        if self.behavior == MockRenderBehavior.PARTIAL:
            _minimal_mp4(out_path, size_bytes=200)
            return out_path

        # Prefer real ffmpeg clip when available for ffprobe-rich tests
        try:
            from pipeline.compose import make_color_clip

            make_color_clip(out_path, seconds=1.0, size="640x360")
            if out_path.is_file() and out_path.stat().st_size >= 8000:
                return out_path
        except Exception:
            pass

        _minimal_mp4(out_path, size_bytes=9000)
        return out_path


_GLOBAL_MOCK = MockRenderProvider()


def get_mock_render_provider() -> MockRenderProvider:
    return _GLOBAL_MOCK


def reset_mock_render_provider() -> None:
    _GLOBAL_MOCK.reset()
