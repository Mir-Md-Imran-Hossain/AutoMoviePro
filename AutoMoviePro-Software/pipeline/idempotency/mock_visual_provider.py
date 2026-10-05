"""Deterministic mock visual provider for BUILD-04A tests."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MockBehavior(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MALFORMED = "malformed"
    REJECTION = "rejection"
    SLOW = "slow"
    UNKNOWN = "unknown"
    INVALID_ASSET = "invalid_asset"


# Minimal valid MP4-ish blob (ftyp + mdat padding)
_MOCK_MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + (b"\x00" * 9000)


@dataclass
class MockVisualProvider:
    """Simulates external visual provider with invocation counting."""

    behavior: MockBehavior = MockBehavior.SUCCESS
    slow_delay_sec: float = 0.05
    generation_id_prefix: str = "mock-vid"
    invocation_count: int = field(default=0, init=False)
    last_generation_id: str = field(default="", init=False)

    def reset(self) -> None:
        self.invocation_count = 0
        self.last_generation_id = ""

    def generate(
        self,
        *,
        out_path: Path,
        prompt: str = "",
        seed: Optional[int] = None,
    ) -> Path:
        self.invocation_count += 1
        self.last_generation_id = f"{self.generation_id_prefix}-{self.invocation_count:04d}"
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if self.behavior == MockBehavior.TIMEOUT:
            raise TimeoutError("provider timeout — response lost")
        if self.behavior == MockBehavior.NETWORK:
            raise ConnectionError("temporary network failure")
        if self.behavior == MockBehavior.REJECTION:
            raise ValueError("invalid configuration — provider rejected request")
        if self.behavior == MockBehavior.UNKNOWN:
            raise TimeoutError("provider accepted but response lost")
        if self.behavior == MockBehavior.SLOW:
            time.sleep(self.slow_delay_sec)

        if self.behavior == MockBehavior.INVALID_ASSET:
            out_path.write_bytes(b"")
            return out_path
        if self.behavior == MockBehavior.MALFORMED:
            out_path.write_bytes(b"NOT_A_VIDEO")
            return out_path

        out_path.write_bytes(_MOCK_MP4)
        return out_path


# Module-level counter for tests that patch provider globally
_GLOBAL_MOCK = MockVisualProvider()


def get_mock_provider() -> MockVisualProvider:
    return _GLOBAL_MOCK


def reset_mock_provider() -> None:
    _GLOBAL_MOCK.reset()
