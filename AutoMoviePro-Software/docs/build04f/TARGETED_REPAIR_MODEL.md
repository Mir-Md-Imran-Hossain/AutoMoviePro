# TARGETED_REPAIR_MODEL

Repair scopes (smallest first): DIALOGUE → SCRIPT_SECTION → VISUAL_PLAN → VISUAL_ASSET → AUDIO_PLAN → AUDIO_ASSET → SUBTITLE → RENDER

`plan_repair()` selects scope from highest-severity issue evidence.

`execute_repair_request()` provides idempotent repair execution with revision tracking.

Scene-05 visual failure does NOT regenerate entire script/audio.
