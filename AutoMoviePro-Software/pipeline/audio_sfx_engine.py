# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Procedural Micro-SFX & Audio Sound Design Engine
-----------------------------------------------------------------
Generates pristine, 100% mathematical procedural audio micro-SFX (WAV 44.1kHz 16-bit PCM):
1. Pop SFX: Resonant downward frequency chirp with exponential decay envelope (bubbly, satisfying card pop).
2. Whoosh SFX: Shaped bandpass air-rush noise with symmetric rise/fall envelope (dynamic slide transition).
3. Digital Click SFX: High-tech HUD transient chirp (2.4kHz damped pulse for cybernetic button/card activation).
4. Glitch SFX: Bit-crushed frequency stepped modulation with micro-dropout bursts (holographic/tech reveal).

Also provides Timeline SFX Event Mixer to synchronize micro-SFX with visual cues (pop-ins, counters, charts).
"""
from __future__ import annotations

import math
import random
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

DEFAULT_SAMPLE_RATE = 44100


@dataclass
class SFXEvent:
    timestamp_sec: float
    sfx_type: str  # 'pop', 'whoosh', 'digital_click', 'glitch'
    gain: float = 0.8  # 0.0 to 1.0


class ProceduralSFXEngine:
    """Zero-dependency procedural acoustic synthesizer for UI and motion graphics sound design."""

    @staticmethod
    def synth_pop(
        duration_sec: float = 0.28,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        start_freq: float = 680.0,
        end_freq: float = 160.0,
        gain: float = 0.85,
    ) -> bytes:
        """Generates an organic UI pop / bubble sound."""
        num_samples = int(duration_sec * sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            # Frequency decay
            freq = (start_freq - end_freq) * math.exp(-t * 22.0) + end_freq
            # Exponential envelope
            envelope = math.exp(-t * 16.0)
            # Second harmonic for round warmth
            wave_val = 0.8 * math.sin(2.0 * math.pi * freq * t) + 0.2 * math.sin(4.0 * math.pi * freq * t)
            sample = int(32767.0 * gain * envelope * wave_val)
            sample = max(-32768, min(32767, sample))
            frames.extend(struct.pack("<h", sample))
        return bytes(frames)

    @staticmethod
    def synth_whoosh(
        duration_sec: float = 0.38,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        gain: float = 0.75,
    ) -> bytes:
        """Generates a smooth aerodynamic whoosh / swipe sound."""
        num_samples = int(duration_sec * sample_rate)
        frames = bytearray()
        rng = random.Random(42)  # Deterministic seed for reproducible whoosh

        # Pre-generate noise buffer
        raw_noise = [rng.uniform(-1.0, 1.0) for _ in range(num_samples)]

        # Two-pole lowpass filter with moving cutoff to simulate air displacement
        cutoff_min = 250.0
        cutoff_max = 2400.0
        filtered = [0.0] * num_samples
        y1 = 0.0
        y2 = 0.0

        for i in range(num_samples):
            t = i / sample_rate
            progress = t / duration_sec
            # Center-peaked cutoff frequency sweep
            center_curve = math.sin(progress * math.pi)
            cutoff = cutoff_min + (cutoff_max - cutoff_min) * (center_curve ** 1.8)
            alpha = min(0.95, (2.0 * math.pi * cutoff) / sample_rate)

            # Simple resonant lowpass
            x = raw_noise[i]
            y1 += alpha * (x - y1)
            y2 += alpha * (y1 - y2)

            # Bell-curve envelope with rapid fade-in and smooth tail
            envelope = (math.sin(progress * math.pi) ** 2.2) * (1.0 - 0.2 * progress)
            sample_val = y2 * envelope * gain
            sample_int = int(32767.0 * sample_val * 2.2)
            sample_int = max(-32768, min(32767, sample_int))
            frames.extend(struct.pack("<h", sample_int))

        return bytes(frames)

    @staticmethod
    def synth_digital_click(
        duration_sec: float = 0.065,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        freq: float = 2400.0,
        gain: float = 0.70,
    ) -> bytes:
        """Generates a high-tech HUD click / chirp."""
        num_samples = int(duration_sec * sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            # Sharp impulse envelope
            env = math.exp(-t * 90.0)
            # Slight pitch drop
            f = freq * (1.0 - 0.4 * (t / duration_sec))
            val = math.sin(2.0 * math.pi * f * t)
            # Add secondary higher resonance
            val += 0.35 * math.sin(4.0 * math.pi * f * t)
            sample = int(32767.0 * gain * env * val)
            sample = max(-32768, min(32767, sample))
            frames.extend(struct.pack("<h", sample))
        return bytes(frames)

    @staticmethod
    def synth_glitch(
        duration_sec: float = 0.22,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        gain: float = 0.65,
    ) -> bytes:
        """Generates a cybernetic glitch / digital reveal sound."""
        num_samples = int(duration_sec * sample_rate)
        frames = bytearray()
        rng = random.Random(1337)

        # Segmented micro-bursts
        step_samples = int(sample_rate * 0.02)
        current_freq = 440.0

        for i in range(num_samples):
            if i % step_samples == 0:
                current_freq = rng.choice([320.0, 640.0, 960.0, 1800.0, 240.0, 1200.0])

            t = i / sample_rate
            progress = t / duration_sec
            env = (1.0 - progress) * (1.0 if (i // (step_samples // 2)) % 3 != 0 else 0.1)

            # Square/saw hybrid with noise jitter
            phase = (t * current_freq) % 1.0
            val = 1.0 if phase < 0.5 else -1.0
            val = 0.7 * val + 0.3 * rng.uniform(-1.0, 1.0)

            sample = int(32767.0 * gain * env * val * 0.6)
            sample = max(-32768, min(32767, sample))
            frames.extend(struct.pack("<h", sample))

        return bytes(frames)

    @classmethod
    def generate_sfx(
        cls,
        sfx_type: str,
        duration_sec: Optional[float] = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        gain: float = 0.8,
    ) -> bytes:
        """Dispatches to the appropriate procedural synthesizer."""
        st = (sfx_type or "pop").lower().strip()
        if "whoosh" in st or "swipe" in st:
            return cls.synth_whoosh(duration_sec or 0.35, sample_rate, gain=gain)
        elif "click" in st or "hud" in st or "tap" in st:
            return cls.synth_digital_click(duration_sec or 0.065, sample_rate, gain=gain)
        elif "glitch" in st or "cyber" in st:
            return cls.synth_glitch(duration_sec or 0.22, sample_rate, gain=gain)
        else:
            return cls.synth_pop(duration_sec or 0.28, sample_rate, gain=gain)

    @classmethod
    def write_wav(
        cls,
        out_path: Union[str, Path],
        raw_pcm16: bytes,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = 1,
    ) -> Path:
        """Writes raw 16-bit PCM bytes to a standard WAV file."""
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(p), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(raw_pcm16)
        return p

    @classmethod
    def render_event_timeline_wav(
        cls,
        events: List[Union[SFXEvent, Dict[str, Any]]],
        total_duration_sec: float,
        out_wav_path: Union[str, Path],
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> Path:
        """
        Mixes multiple procedural micro-SFX events onto a timeline into a single WAV file.
        Perfect for synchronizing with visual pop-ins, counters, and card transitions.
        """
        total_samples = max(1, int(total_duration_sec * sample_rate))
        # 32-bit float mixing buffer
        mix_buffer = [0.0] * total_samples

        for ev in events:
            if isinstance(ev, dict):
                t_sec = float(ev.get("timestamp_sec", ev.get("time", 0.0)))
                sfx_name = str(ev.get("sfx_type", ev.get("type", "pop")))
                g = float(ev.get("gain", 0.8))
            else:
                t_sec = ev.timestamp_sec
                sfx_name = ev.sfx_type
                g = ev.gain

            if t_sec < 0 or t_sec >= total_duration_sec:
                continue

            start_idx = int(t_sec * sample_rate)
            pcm_bytes = cls.generate_sfx(sfx_name, sample_rate=sample_rate, gain=g)
            sample_count = len(pcm_bytes) // 2

            for si in range(sample_count):
                dest_idx = start_idx + si
                if dest_idx >= total_samples:
                    break
                sample_val = struct.unpack_from("<h", pcm_bytes, si * 2)[0] / 32768.0
                mix_buffer[dest_idx] += sample_val

        # Master limiter & convert to 16-bit PCM
        peak = max(max((abs(v) for v in mix_buffer), default=0.0), 1.0)
        norm_factor = 0.95 / peak if peak > 0.95 else 1.0

        out_bytes = bytearray()
        for v in mix_buffer:
            clamped = max(-1.0, min(1.0, v * norm_factor))
            s16 = int(clamped * 32767.0)
            out_bytes.extend(struct.pack("<h", s16))

        return cls.write_wav(out_wav_path, bytes(out_bytes), sample_rate=sample_rate, channels=1)
