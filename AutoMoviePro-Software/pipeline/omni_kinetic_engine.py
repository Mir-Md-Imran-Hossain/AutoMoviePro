# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Forwarding Bridge to Proprietary AutoMovie Kinetic Engine
========================================================================
Maintains 100% backward compatibility with existing codebase callers
while delegating all execution to pipeline.automovie_kinetic_engine.
"""

from __future__ import annotations

from pipeline.automovie_kinetic_engine import (
    AutoMovieKineticEngine,
    AutoMovieKineticEngine as OmniKineticEngine,
    DialogueBeat,
    compile_multicard_kinetic_video,
    fetch_cinematic_motion_clip,
    generate_cyber_ambient_motion_clip,
    render_beat_glass_cards,
    split_dialogue_into_kinetic_beats,
)

__all__ = [
    "AutoMovieKineticEngine",
    "OmniKineticEngine",
    "DialogueBeat",
    "generate_cyber_ambient_motion_clip",
    "fetch_cinematic_motion_clip",
    "split_dialogue_into_kinetic_beats",
    "render_beat_glass_cards",
    "compile_multicard_kinetic_video",
]
