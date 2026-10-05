# H3 Pre-Audit — Performance & Cost Control

**Date:** 2026-09-03  
**Mode:** READ-ONLY (no source/test changes; no paid APIs; no H3 implementation)  
**Baseline checkpoints:**  
- H2: `AMP004-H2-PRODUCTION-SECURITY-CONFIG-PASS-WITH-LIMITATION`  
- H1: `H1-PRODUCTION-RELIABILITY-PASS` / `AMP004-H1-PRODUCTION-RELIABILITY-PASS`  
- Phase-10: `AMP004-FINAL-PRODUCTION-CERTIFICATION-PASS` / `AMP004-PHASE10-PASS`  
**Audit checkpoint:** `AMP004-H3-PRE-AUDIT-PASS`

---

## 1. Executive Summary

Production cost controls are **substantially present but fragmented and partially measured**. BUILD-03 idempotency + H1 locking prevent duplicate provider claim under contention. `google_api_gate` hard-caps Google vault spray (sticky key, hourly budget, circuit). Scene Agnes creates are budgeted (≤2/scene). Repair cycles are capped (typically 3). TTS reuse sidecars exist.

**No P0** and **no proven unbounded retry / duplicate paid-execution P1** under current production paths. Remaining issues are **P2/P3**: nested retry multiplication (bounded but expensive), dual TTS/FFmpeg call paths, localization × language linear cost, critic cost-skip (quality tradeoff), missing financial cost accounting, and incomplete latency telemetry.

**Recommendation:** `H3_PRE_AUDIT_GO_WITH_LIMITATIONS` — proceed to bounded H3 that **extends** existing authorities (idempotency metrics, google_api_gate, TTS reuse, render_bridge) — do **not** create CostEngine2 / Cache2 / RetryEngine2.

---

## 2. Baseline

| Item | Evidence |
|------|----------|
| H2 | `H2_FINAL_REPORT.md` — PASS-WITH-LIMITATION; channel keys at-rest; critic cost-skip unchanged |
| H1 | Dual-lock race fixed; `normalize_lock_key` + `exclusive_path_lock`; DEF-AMP004-011 RESOLVED |
| Phase-10 | Certification PASS; FFMPEG/FFPROBE available; publishability AND |
| Deferred | DEF-H2-007 plaintext keys; DEF-AMP004-006 av_self_repair vs repair_runtime overlap; DEF-T004-C4 fallback visual_runtime |
| Prior cost claim | `google_api_gate.py` documents historical “18-key wipe”; gate is the containment |
| Git | No `.git` in workspace — branch/status unavailable |

This audit does **not** re-claim Phase-10 quality PASS as a performance certificate.

---

## 3. Existing Authority Map

| Concern | Canonical authority | Notes |
|---------|---------------------|-------|
| Idempotency | BUILD-03 `IdempotentExecutor` + `IdempotencyStore` | H1 locking intact |
| Fingerprint | `pipeline.idempotency.fingerprint` | Unchanged |
| Retry class | `pipeline.idempotency.retry_policy` | max_attempts default 3 |
| GenerationCache | `pipeline.generation_cache.GenerationCache` | **Legacy nested**; not second BUILD-03 |
| Checkpoint | `CheckpointStore` | H1 locked RMW |
| Visual/Agnes | `agnes_bridge` → executor | Pre-provider semantic bypass guard |
| TTS | `tts_bridge.idempotent_*` + `tts_reuse` | Direct `synthesize_narration` fallback remains |
| Render/compose | `render_bridge.idempotent_compose_final_video` | Calls existing scene_builder/compose provider |
| FFmpeg exec | `pipeline.ffmpeg_exec` (+ Phase-08 `run_controlled_ffmpeg`) | Structured timeout/kill |
| Google LLM/TTS burn | `pipeline.google_api_gate` | Sticky key, circuit, hourly budget |
| Creative score/repair | BUILD-04F `quality.bridge` / publishability | Sole creative score authority |
| Continuity | ContinuityTracker | Unchanged |
| Artifact observation | Artifact Verification | Unchanged |
| Publishability | `quality.publishability` | Unchanged |
| Intelligence/research | `intelligence.config` + gate | MOCK/LIVE; fail-closed PRODUCTION |
| Critic skip | `agent_playbook.should_skip_gemini_critic` | Cost save when agent passed |

**Authority change since Phase-10/H2:** config/auth/skip/redaction (H2) only — **not** a new cost/idempotency/render engine.

---

## 4. Provider / API Cost Audit

### Classification (code inspection only — **0 paid calls**)

| Operation | Class | Path |
|-----------|-------|------|
| Agnes video create | **PAID-capable** | `media_assets` / agnes_bridge |
| Google generateContent (text/critic/TTS) | **PAID-capable** (free-tier sensitive) | `google_api_gate.gated_generate_content` |
| OpenRouter / Groq / Cerebras chat | **PAID-capable** | `llm_router.chat_text` |
| Pollinations / FreetheAI / Kling / Luma / Seedance | **PAID / potentially paid** | image/video adapters |
| Edge TTS | **free/local-ish** | `edge_tts_fallback` |
| FFmpeg / ffprobe | **local** | `ffmpeg_exec` / `compose` |
| Mock providers | **test/mock** | `idempotency/mock_*` |
| Heuristic AV gates | **free local** | `av_quality_gates`, playbook |

### Necessity / reuse (summary)

| Path | Necessary? | Idempotent? | Cached/reuse? | Retry bounded? | Concurrent duplicate? |
|------|------------|-------------|---------------|----------------|------------------------|
| Visual/Agnes | Yes for scenes | Yes via BUILD-03 | Store reuse + GenerationCache legacy | Executor ≤3; Agnes budget ≤2/scene | H1 claim lock |
| Google gated | When LLM/TTS/critic | Partial (caller + gate) | Sticky key; circuit | Keys ≤2; models ≤1 (or 2 if multi); hourly budget | Process-wide budget |
| TTS | Per language/scene | Bridge + `tts_reuse` sidecar | Sidecar fingerprint | `max_retries_per_key=2` | Same work_dir lock |
| Translate | Per target lang | Via chat_text | Not durable cache proven | Router/gate | N× langs |
| Critic | Optional if agent passed | N/A | Skip path | Gate | Per scene |
| Repair regen | Targeted by stage | Fingerprint if via executor | Cycle files | Cycle max 3 | Per work_dir |

**User retry / job re-run:** Same fingerprint → reuse if SUCCEEDED artifact validates; `force_regenerate` can bypass (caller-controlled).

---

## 5. Cost Amplification Analysis

| Trigger | Multiplicative factors (actual) | Cap | Cache/idem | Classification |
|---------|----------------------------------|-----|------------|----------------|
| Short job scenes | ~8–14 scenes (duration budget) | Duration planner | Per-scene fingerprint | **BOUNDED** |
| Long narration split | Chunks ≤ ~9s Agnes AV | Agnes budget 2/scene; split path | Per part | **BOUNDED** / **POTENTIALLY EXPENSIVE** if many chunks |
| AV retries | `max_av_retries=min(1, …)` | 1 | — | **BOUNDED** |
| Idempotency retries | `max_attempts=3` | 3 | Claim/reuse | **BOUNDED** |
| Google gate | keys ≤2 × models ≤1–2 | Hourly budget 40; circuit ~20h | Sticky | **BOUNDED** |
| TTS per key | `max_retries_per_key=2` | 2 | Sidecar reuse | **BOUNDED** |
| Localization | × channel languages (translate + TTS + remux) | Channel entitlement | TTS reuse | **BOUNDED** / **POTENTIALLY EXPENSIVE** (linear in langs) |
| Repair cycles (creative/RI/loc/audio/artifact) | ≤3 cycles each stage | Cycle JSON | Targeted repair plans | **BOUNDED** |
| Nested: executor × gate × TTS × AV × repair | Product of above | Each layer capped | Partial | **POTENTIALLY EXPENSIVE** (not UNBOUNDED) |
| Historical vault spray | Documented blocked | Gate | — | **SAFE** (contained) |

No production path was proven **UNBOUNDED**. Residual **UNKNOWN**: adapters that might bypass `gated_generate_content` (search shows gate is intended chokepoint; not every HTTP client fully proven in this audit pass).

---

## 6. Idempotency Audit

- Identical inputs → stable fingerprint (`FingerprintTests` PASS this audit).  
- Concurrent claim → duplicate prevented (`ExecutorTests.test_duplicate_prevented_concurrent` PASS).  
- H1: `normalize_lock_key` strips `\\?\`; `exclusive_path_lock` process-safe — verified by H1 tests this session.  
- Failed attempts: retry policy; UNKNOWN does not blind-retry as success.  
- Provider execution after claim — critical section protected.  
- **Do not create second idempotency authority in H3.**

---

## 7. Cache Audit

| Cache | Key | Survives restart | Avoids paid work | Concurrency | Risk |
|-------|-----|------------------|------------------|-------------|------|
| IdempotencyStore | fingerprint | Yes (JSON) | Yes on SUCCEEDED | H1 lock | Primary |
| CheckpointStore | job checkpoints | Yes | Resume skip | H1 lock | Primary |
| GenerationCache | scene generation_key | Yes | Yes if artifact ≥1KB | H1 lock | **Legacy nested** — dual bookkeeping risk if callers diverge |
| TTS sidecar `.m4a.txt` | sha1(text)+voice | Yes | Yes | File-local | Good |
| Google circuit/pool/quota JSON | process/machine | Yes | Prevents burn | Thread lock | Cost protection |
| Intelligence reserve | topic reserve | Yes | Avoids duplicate topics | H1 lock | Research |

**Stale-data:** Invalid reuse detected → mark FAILED_RETRYABLE and regenerate.  
**Cross-project:** work_dir scoped — OK if work_dirs isolated.

---

## 8. Retry / Timeout Audit

| Layer | Max | Non-retry | Notes |
|-------|-----|-----------|-------|
| `retry_policy` | 3 | auth/config/invalid keywords | Default unmatched → **RETRYABLE** (amplification risk if message poorly labeled) |
| Idempotency store attempt | record.max_attempts | Cap on claim | |
| Google gate | keys≤2, models≤1–2 | Circuit / budget raise | |
| TTS Google | 2/key | Quota cool-down | ThreadPool timeout |
| FFmpeg | timeout_sec (e.g. 120–300) | Kill tree | |
| Render integrity retry | capped | Classification-based | |
| Repair cycles | 3 | Exhaust → no more repair | |
| Quota ladder | ≤1h sleep | Per-key 20m cool | Not infinite loop |

**Invariant:** Deterministic auth/config failures matching keyword list → NON_RETRYABLE.  
**Gap:** Errors without keywords may still retry (≤3) — **POTENTIALLY AMPLIFIED**, not unbounded.

Nested worst-case (theoretical upper bound, same scene):  
`≤ 3 (executor) × 2 (keys) × 2 (models if multi) × 2 (TTS) × 2 (Agnes) × 1 (AV) × 3 (repair stage)` — **expensive but finite**.

---

## 9. Critic / Intelligence Cost Audit

| Path | Type | When | Repeat? |
|------|------|------|---------|
| `should_skip_gemini_critic(agent_passed)` | **Skips paid-capable critic** | Agent report passed | Cost ↓ ; quality coverage ↓ (H2 limitation) |
| Multimodal / semantic | Heuristic + optional provider | Pre-provider for production identity | Contained |
| BUILD-04F scoring | Local creative gate | End of pipeline | Not a paid VLM by default |
| Research LIVE | Provider-capable | Topic planning | Fail-closed PRODUCTION; MOCK for tests |
| VLM/ASR | Deferred / partial | Not assumed in cost model | DEF-AMP004-001 |

**H2 note confirmed:** critic cost-skip **unchanged** — reduces spend; does not create second quality engine.

---

## 10. Repair Cost Audit

- Stage gates (creative, RI, localization, audio, artifact) use **cycle caps (3)** and repair bridges.  
- BUILD-04F remains creative score + targeted repair authority.  
- `av_self_repair_agent` vs formal repair_runtime = **DEF-AMP004-006 overlap** (deferred) — risk of **duplicate local repair work**, usually FFmpeg not paid.  
- Scene-level Agnes regen capped by budget/retries — not whole-project by default.  
- Full recompose via `idempotent_compose_final_video` when final assembly invalid — fingerprint reuse if unchanged.

---

## 11. FFmpeg / Rendering Performance Audit

- **Canonical final compose:** `render_bridge.idempotent_compose_final_video`.  
- **Execution boundary:** `ffmpeg_exec.run_ffmpeg` (timeout, kill tree).  
- Phase-08 `run_controlled_ffmpeg` adds provenance redaction.  
- **Legacy:** `scene_builder` still performs many direct compose/ffprobe/`shutil.copy2` steps per scene — **repeated probing/copy** observed in code (performance P2, not second FFmpeg “engine”).  
- Idempotent render prevents duplicate final assembly for same manifest fingerprint.  
- FiltergraphContract partial; string graphs still ACTIVE (DEF-AMP004-008) — complexity, not proven cost blowup.

---

## 12. Media / Filesystem Work Audit

- Frequent `ffprobe_duration` and multi-copy of scene masters during agent repair (scene_builder).  
- Temp `.tmp` + `os.replace` for JSON stores (H1-safe).  
- Localization remux per language — linear media work.  
- No proven O(N²) algorithm; work scales ~**O(scenes × langs × repair cycles)**.

---

## 13. Concurrency / Throughput Audit

- No large production thread/process pool for multi-scene parallel generation found (TTS uses `max_workers=1`).  
- Contended safety: H1 path locks + idempotency claim.  
- Google gate process-wide hourly budget serializes burn risk.  
- DEF-AMP004-011 remains fixed (H1 tests PASS this session).  
- Throughput: **single-threaded scene loop** in `generate_video` style paths → latency bound, lower duplicate risk.

---

## 14. Memory / Resource Lifecycle Audit

- FFmpeg: PIPE + timeout + kill tree — good.  
- Circuit/quota JSON on disk — bounded.  
- Temp lock files may remain after crash (advisory lock released on handle close) — H1 limitation.  
- Unbounded in-memory media: not evidenced as systemic; large jobs write to disk.  
- Exception paths generally warn-and-continue on archive/localize — may leave orphans (P3 cleanup).

---

## 15. Batch / Long-Video Scalability

| Dimension | Scaling | Notes |
|-----------|---------|-------|
| Scenes | ~LINEAR | Duration budget |
| Languages | ~LINEAR | Translate+TTS+remux |
| Retries/repairs | ~LINEAR × small constants | Caps |
| Long narration | SUPERLINEAR risk if many Agnes chunks without reuse | Mitigated by budget 2/scene |
| Multi-project same host | UNKNOWN contention on Google budget/circuit (shared process files) | Ops concern |

Batch production **out of H3 implement scope** — document only.

---

## 16. Performance Measurement Audit

| Metric | Status |
|--------|--------|
| Idempotency generation_started / retry_count / result_reused | **MEASURED** (store metrics) |
| Mock/visual provider invocation_count | **MEASURED** (tests/E2E) |
| E2E `provider_call_count` | **PARTIALLY MEASURED** |
| FFmpeg `elapsed_sec` | **MEASURED** per `FFmpegResult` |
| Google gate attempts / budget | **PARTIALLY MEASURED** (state files, not unified dashboard) |
| End-to-end job latency | **UNMEASURED** as first-class telemetry |
| Queue wait / CPU / memory | **UNMEASURED** |
| Critic vs skip counts | **UNMEASURED** systematically |

---

## 17. Cost Accounting Audit

| Field | Exists? |
|-------|---------|
| Provider / model on GateResult | Yes (key_tag, model, attempts) |
| Idempotency metrics counters | Yes (not dollars) |
| Token usage | **Not systematically persisted** across providers |
| Estimated USD cost | **Absent** |

**COST_NOT_DETERMINABLE_FROM_REPOSITORY** (no pricing tables / billing integration).

---

## 18. Failure / Abort Safety

| Failure | Duplicate paid risk | Notes |
|---------|---------------------|-------|
| Provider timeout | Bounded retry / UNKNOWN reconcile | |
| Circuit open | Fail to OpenRouter/local | Cost divert |
| Budget exceeded | Raise — stop Google spray | |
| Cancel / crash mid-claim | H1 reclaim; may retry once | |
| Render fail | RI retry/repair cycles | Local FFmpeg mostly |
| Cache unavailable | May regenerate | Expensive but bounded |

H1 locking **not weakened** by H2.

---

## 19. Existing Test Coverage

| Command (this audit) | Purpose | Result |
|----------------------|---------|--------|
| `python -m unittest scripts.test_amp004_h1_reliability.H1ReliabilityTests.test_01_… test_02_…` | H1 lock identity | **PASS** |
| `python -m unittest scripts.test_build03_idempotency` | Fingerprint, claim, reuse, bounded retry, crash resume | **16 PASS** |

**Not re-run in this audit (available from H1/H2 history):** H1 full 9/9, Phase-02→10 398, BUILD-04A/G — prior PASS; not re-executed fully here to avoid long mutation-adjacent load.  
**Unavailable:** dedicated production cost-accounting suite; financial estimator tests.

Paid APIs this audit: **0**.

---

## 20. Findings by Severity

### Evidence table

| ID | Finding | Severity | Evidence | Reachability | Action |
|----|---------|----------|----------|--------------|--------|
| — | Unbounded paid retry / vault spray | — | Gate + caps | Contained | None (monitor) |
| DEF-H3-001 | Nested retry layers multiply attempts (bounded) | **P2** | executor×gate×TTS×AV×repair caps | Production | Unify attempt accounting; log product of attempts |
| DEF-H3-002 | Dual TTS path (idempotent + direct fallback) | **P2** | `video_pipeline` / authority_audit | Production on bridge failure | Prefer sole bridge; measure fallback rate |
| DEF-H3-003 | Localization linear paid work × languages | **P2** | `localization.py` translate+TTS | Multi-lang channels | Cap/parallel policy; stronger reuse metrics |
| DEF-H3-004 | Repeated ffprobe/copy in scene_builder | **P2** | scene_builder copies/probes | Every scene | Cache probe results; reduce copies |
| DEF-H3-005 | Legacy GenerationCache alongside BUILD-03 | **P2** | `generation_cache.py` docstring | Callers using both | Document single write path; deprecate dual writes |
| DEF-H3-006 | Cost/latency accounting incomplete | **P2** | No USD/token ledger | Ops | Extend idempotency/gate metrics — no CostEngine2 |
| DEF-H3-007 | Default RETRYABLE for unlabeled errors | **P2** | `retry_policy.classify_error` fallback | Production | Tighten NON_RETRYABLE classes |
| DEF-H3-008 | Critic skip when agent passed | **P3** | `should_skip_gemini_critic` | Production | Quality/cost policy explicit (H2 known) |
| DEF-H3-009 | Shared Google circuit across jobs on host | **P3** | `google_circuit_state.json` | Multi-job same process/host | Document ops isolation |
| DEF-H3-010 | DEF-AMP004-006 repair overlap | **P3** | Deferred issues | Production local repair | Merge later (not H3 must) |

**P0:** 0  
**P1:** 0  
**P2:** 7  
**P3:** 3  

---

## 21. Minimal H3 Actions (future implementation only)

1. **Extend** idempotency + `google_api_gate` metrics: per-job provider call counts, retry product, critic skip counts.  
2. **Instrument** TTS bridge vs direct fallback rate; eliminate unnecessary fallback when safe.  
3. **Reduce** redundant ffprobe/copy in scene path without new FFmpeg engine.  
4. **Tighten** retry classification for unlabeled config/auth failures.  
5. **Clarify** GenerationCache vs BUILD-03 ownership (migrate callers; do not add Cache2).  
6. Localization: optional concurrency/caps with call-count telemetry.  
7. Do **not** invent USD pricing; do **not** create CostEngine2 / RetryEngine2 / second render authority.

---

## 22. Known Limitations

- Financial cost not determinable from repository.  
- Channel keys at-rest plaintext (H2 DEF-H2-007).  
- Critic cost-skip is intentional cost control with quality tradeoff.  
- Full Phase-02→10 suite not re-run in this pre-audit session (prior PASS retained as baseline).  
- Network/NFS lock semantics uncertified (H1).  
- Some provider adapters may still call HTTP outside gate — residual UNKNOWN (not proven vault spray).

---

## 23. H3 Scope Decision

```
H3_PRE_AUDIT_GO_WITH_LIMITATIONS
```

**Rationale:** No P0; no proven unbounded/duplicate-paid P1; H1 duplicate protection intact; cost containment exists (`google_api_gate`, budgets, cycle caps). Remaining work is bounded efficiency/measurement under existing authorities.

---

## 24. Exact Checkpoint

```
AMP004-H3-PRE-AUDIT-PASS
```

---

```
H3_PRE_AUDIT_STATUS: GO_WITH_LIMITATIONS
```

**CHECKPOINT:** `AMP004-H3-PRE-AUDIT-PASS`

**STOP** — do not implement H3; do not start H4/H5/Phase-11.
