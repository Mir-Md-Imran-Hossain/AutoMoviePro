# AMP-004 Deferred Issues

| ID | Sev | Issue | Owner phase |
|----|-----|-------|-------------|
| DEF-AMP004-001 | P0 | Layer-D/E production artifact semantic verification incomplete | **PARTIAL Phase-04** (technical L0/L1 + gate wired; VLM/ASR still PHASE-06+) |
| DEF-AMP004-002 | P0 | Multimodal BLOCKED → publishability AND | **RESOLVED Phase-02** |
| DEF-AMP004-003 | P1 | SFX / music / ducking / loudness absent | **PARTIAL Phase-05** (plan+preflight+mix/duck policy+loudness observe wired; full stem synthesis library still later) |
| DEF-AMP004-013 | P1 | Script narrative quality (original freeze PHASE-05) | **PARTIAL Phase-07** (hook/purpose/preflight/retention wired; 04F remains score authority) |
| DEF-AMP004-004 | P1 | ContinuityTracker not always production-passed | **RESOLVED Phase-03** |
| DEF-AMP004-005 | P1 | prompt_engineering vs SceneIntent compiler duplication | MERGE later |
| DEF-AMP004-006 | P1 | av_self_repair_agent vs repair_runtime overlap | MERGE later |
| DEF-AMP004-007 | P2 | Typography / purposeful VFX contract | **PARTIAL Phase-06+08** (TextPlan + VFX purpose/transition governance; deep VFX library still later) |
| DEF-AMP004-008 | P2 | Formal FFmpeg FiltergraphContract | **PARTIAL Phase-08** (FiltergraphContract + stream maps + preflight; scene_builder string graphs still legacy ACTIVE) |
| DEF-AMP004-014 | P2 | Full FriBidi/HarfBuzz RTL shaping + OCR burned-text verify | Deferred — Phase-06 returns honest UNKNOWN/PARTIAL |
| DEF-AMP004-015 | P2 | Byte-identical deterministic encodes | Documented limitation — structural/fingerprint determinism only (x264) |
| DEF-AMP004-016 | P1 | Host missing ffmpeg/ffprobe blocks complete industrial Layer-E verification | **RESOLVED Phase-10** — bundled `ffmpeg-8.1.1-full_build` discovered via `compose._bundled_bin` |
| DEF-AMP004-009 | P2 | Lighting/camera/anatomy CV | PHASE-04 / user PHASE-08 L3 |
| DEF-AMP004-010 | — | Product-plan PDF missing in repo | External |
| DEF-AMP004-011 | — | BUILD-04A test_06 concurrent flake | **RESOLVED H1** — root cause Windows `\\?\` dual lock keys; `normalize_lock_key` + `exclusive_path_lock`; stress 0/50; test_06 ×100 PASS |
| DEF-H2-007 | P2 | Channel API keys plaintext at rest (SQLite) | **OPEN / outside H5** — encrypt-at-rest/KMS not in release packaging scope; API responses remain masked |
| DEF-H3-008 | P3 | Critic cost-skip when AV agent passed | **OPEN / H3 limitation** — intentional cost control; quality tradeoff |
| DEF-H3-009 | P3 | Shared Google circuit/budget across jobs on host | **OPEN / H3 limitation** — ops isolation |
| DEF-H3-010 | P3 | av_self_repair vs repair_runtime overlap | Same as DEF-AMP004-006 — deferred merge |
| DEF-H5-001 | P2 | PyInstaller media packaging incomplete | **PARTIAL H5** — spec includes ffmpeg/ffprobe; frozen smoke NOT CERTIFIED |
| DEF-H5-003 | P2 | Dependency determinism | **PARTIAL H5** — direct pins in requirements.txt; no transitive lock |
| DEF-H4-001 | P2 | ready_to_upload before multilingual localize packages | **CLOSED H4** — localize + `localization_packages_complete` before ready; multilingual fail-closed |
| DEF-H4-002 | P2 | E2E SceneIntent soft handoff unlabeled | **CLOSED H4** — `allow_soft_handoff` + evidence flags; production never soft-handoffs; publishability still mandatory |
| DEF-H4-003 | P2 | VLM/ASR semantic observation incomplete | **OPEN / H4 limitation** — same as DEF-AMP004-001 PARTIAL |
| DEF-H4-004 | P2 | Long-form / batch not fully certified | **OPEN / H4 limitation** — PARTIALLY_SUPPORTED |
| DEF-H4-005 | P3 | Dual prompt LEGACY compilers | **OPEN** — merge later (DEF-AMP004-005) |
| DEF-H4-006 | P3 | TTS legacy adapter | **N/A H4** — H3 disciplined; no duplicate TTS |
| DEF-AMP004-012 | P0 | Production `skip_semantic_validation` containment | **RESOLVED Phase-02** |
| DEF-T004-C4 | — | Fallback visual_runtime unification | Not started |
| DEF-T004-D/E | — | Audio / localization AMP-003 tasks | **PARTIAL** (audio P05; localization P06 foundation) |

**Unexplained P0:** 0
