# RV-008 প্রতিবেদন — Channel DNA + Niche Relevance

**Protocol:** AMP-002  
**Maps to:** AMP-001 TASK-008  
**Verdict:** VERIFIED_PASS  
**Checkpoint:** RV-008-PASS  
**তারিখ:** ২০২৬-০৮-৩১

---

## ১. Objective

AutoMoviePro Topic Intelligence যেন প্রতিটি channel-এর প্রকৃত niche / content identity অনুযায়ী topic নির্বাচন ও ranking করে, এবং একটি niche-এর signal অন্য niche-এ leak না করে—এটি independent runtime verification।

মূল chain:

```
User Channel Profile → Channel DNA → Niche Identity → Topic Relevance → Candidate Scoring → Ranking
```

---

## ২. Pre-Audit

AMP-001 PASS claim evidence হিসেবে গ্রহণ করা হয়নি। বর্তমান codebase source of truth।

### অডিট করা মডিউল

| Module | Role |
|--------|------|
| `pipeline/channel_dna.py` | `ChannelDNA`, `infer_style_family()`, `from_channel_row()`, `validate_topic_against_dna()` |
| `pipeline/intelligence/contracts.py` | `ChannelProfile`, `TopicCandidate`, `TopicScoreResult` |
| `pipeline/intelligence/normalization.py` | `normalize_topic_text()`, `canonical_topic_key()` |
| `pipeline/intelligence/scoring.py` | `channel_profile_from_row()`, `score_candidate()` → `CHANNEL_RELEVANCE` |
| `pipeline/intelligence/ranking.py` | `rank_candidates()` |
| `pipeline/intelligence/candidates.py` | `candidate_from_dict()` |
| `pipeline/intelligence/orchestrator.py` | `run_topic_intelligence()` |
| `pipeline/intelligence/bridge.py` | `enrich_channel_topic()` — production bridge |
| `pipeline/topic_scoring.py` | `score_topic()` — legacy channel_fit engine |
| `pipeline/intelligence/cache_registry.py` | `bump_channel_version()`, `ranking_cache_key()` |
| `pipeline/video_pipeline.py` | `run_intelligence_gate()` → bridge |

### অন্যান্য callsite

- `pipeline/intelligence/discovery.py` — `profile.forbidden_topics` filter
- `pipeline/golden_harness.py` — DNA gate harness (TEST_ONLY helper)

---

## ৩. Current Architecture

```
channels row (niche, video_special, …)
    → from_channel_row() → ChannelDNA (style_family, preferred/forbidden topics)
    → channel_profile_from_row() → ChannelProfile
    → score_candidate() → score_topic(dna) → CHANNEL_RELEVANCE dimension
    → rank_candidates()
```

Production entry:

```
video_pipeline.run_intelligence_gate()
    → bridge.enrich_channel_topic()
        → channel_profile_from_row(channel)
        → run_topic_intelligence(profile, candidates)
            → score_candidate(profile, dna)
            → rank_candidates()
```

---

## ৪. Channel DNA Flow (প্রতি ধাপ)

| Step | INPUT | TRANSFORMATION | OUTPUT | IDENTITY | VALIDATION |
|------|-------|----------------|--------|----------|------------|
| 1. User config | `channels.niche`, `video_special` | `infer_style_family()` | `style_family` (gadget/history/finance/…) | channel_id | deterministic marker rules |
| 2. Channel DNA | channel row | `from_channel_row()` | `ChannelDNA` | channel_id + niche | `validate_topic_against_dna()` |
| 3. Profile | ChannelDNA | `channel_profile_from_row()` | `ChannelProfile` | channel_id | forbidden/preferred topics propagated |
| 4. Candidate | title, format | `candidate_from_dict()` | `TopicCandidate` | topic_id, channel_id | metadata carries niche |
| 5. Scoring | topic + dna | `score_topic()` → channel_fit | `CHANNEL_RELEVANCE` (17% weight) | per candidate+channel | relevant > irrelevant runtime |
| 6. Ranking | scores dict | `rank_candidates()` | ordered list | per orchestrator run | channel_version in metadata |

**নিশ্চিতকরণ:** niche শুধু DB/UI-তে থাকলেই নয় — `channel_profile_from_row()` ও `score_candidate()`-এ runtime-এ পৌঁছায়।

---

## ৫. Niche Classification

`infer_style_family()` inventory:

| Input niche / markers | style_family |
|----------------------|--------------|
| tech, technology, gadget, smartphone | `gadget` |
| finance, stock, crypto | `finance` |
| history, ancient, archaeology | `history` |
| science, physics, chemistry | `science` |
| education, tutorial | `education` |
| health, medical | `health` |
| entertainment, gaming | `entertainment` |
| mystery, unexplained | `mystery` |
| empty / whitespace | `general` |
| unknown string | `general` (forced to history/finance নয়) |

**TECH → HISTORY bug:** `infer_style_family("tech")` → `"gadget"` (≠ history) — VERIFIED_PASS।

---

## ৬. Relevance Scoring

`CHANNEL_RELEVANCE` = `score_topic().components.channel_fit` (weight 17%)

### Calculation chain (`topic_scoring.py`)

1. `validate_topic_against_dna()` gate (forbidden / gadget-on-nongadget)
2. Base channel_fit: 0.85 (preferred topic hit) or 0.65
3. History ancient-word boost → 1.0
4. `_apply_niche_mismatch_penalty()` — cross-niche marker mismatch cap (≤0.35)
5. `_niche_context_adjustment()` — borderline topic per-family boost

### Deterministic evidence (runtime)

| Channel | Topic | CHANNEL_RELEVANCE |
|---------|-------|-------------------|
| TECH | New smartphone processor architecture | > 0.5 (relevant) |
| TECH | Ancient Roman political history | < relevant score |
| HISTORY | Causes of the French Revolution | > 0.5 |
| HISTORY | Latest GPU benchmark | < history relevant |
| TECH | The technology of ancient Roman weapons | < real tech topic (keyword trap mitigated) |

---

## ৭. Production Call Graph

```
video_pipeline.py
  run_intelligence_gate()
    bridge.enrich_channel_topic(work_dir, channel, topic)
      channel_profile_from_row(channel)          ← niche reaches here
      run_topic_intelligence(work_dir, profile, [candidate])
        score_candidate(c, profile)              ← dna from profile.niche
        rank_candidates(...)
```

`evaluate_candidates(do_research=False)` — **TEST_ONLY** legacy API; production uses `do_research=True` via bridge।

---

## ৮. Problems Found

| # | Issue | Severity |
|---|-------|----------|
| P1 | Keyword trap: "technology of ancient Roman weapons" on TECH channel could score same as genuine tech topic | P1 |
| P2 | Borderline topic ("history of AI") scored identically for TECH vs HISTORY channels | P2 |

---

## ৯. Root Causes

1. **Keyword trap:** `channel_fit` base score did not penalize cross-niche semantic markers when a misleading keyword ("technology") appeared in a history-framed topic.
2. **Borderline parity:** No per-`style_family` context adjustment — both channels received default 0.65.

---

## ১০. Code Changes

| File | Change |
|------|--------|
| `pipeline/topic_scoring.py` | Added `_apply_niche_mismatch_penalty()`, `_niche_context_adjustment()` |
| `scripts/test_reverification_rv008.py` | New dedicated RV-008 test suite (21 tests) |

**Scope:** surgical fix only in `topic_scoring.py`. No rewrite of research, visual, audio, script, rendering, or browser automation.

---

## ১১. Test Matrix

| ID | Test | Result |
|----|------|--------|
| TEST-01 | TECH relevant topic | PASS |
| TEST-02 | TECH irrelevant topic | PASS |
| TEST-03 | HISTORY relevant topic | PASS |
| TEST-04 | HISTORY irrelevant topic | PASS |
| TEST-05 | FINANCE relevant topic | PASS |
| TEST-06 | SCIENCE relevant topic | PASS |
| TEST-07 | unknown/empty niche → general | PASS |
| TEST-08 | invalid niche not forced to history/finance | PASS |
| TEST-09 | cross-channel isolation (concurrent) | PASS |
| TEST-10 | same candidate / different channels → different scores | PASS |
| TEST-11 | multilingual normalization preserves identity | PASS |
| TEST-12 | keyword trap / semantic mismatch | PASS |
| TEST-13 | channel DNA change affects score | PASS |
| TEST-14 | cache invalidation on channel bump | PASS |
| TEST-15 | production integration via orchestrator | PASS |
| + | TECH≠HISTORY classification | PASS |
| + | HISTORY blocks gadget topic | PASS |
| + | LONG/SHORT same CHANNEL_RELEVANCE | PASS |

**Dedicated suite:** `scripts/test_reverification_rv008.py` — **21/21 PASS**

---

## ১২. Negative Tests

- TECH channel + ancient Roman history → lower than tech-relevant topic
- HISTORY channel + GPU benchmark → lower than history-relevant topic
- HISTORY channel + iPhone unboxing → `validate_topic_against_dna()` FAIL (`forbidden_topic`)
- Keyword trap topic scores below genuine tech topic

---

## ১৩. Cross-Channel Tests

- Concurrent TECH / HISTORY / FINANCE orchestrator runs — each result retains correct `channel_id`
- Same borderline topic scored differently per channel profile (0.82 history vs 0.78 tech for "history of artificial intelligence")

---

## ১৪. Multilingual Tests

- Bengali topic `কেন Bitcoin পড়ে গেল?` → normalized identity contains `bitcoin`
- `canonical_topic_key()` preserves semantic token across EN/BN variants

---

## ১৫. Cache Tests

- `bump_channel_version()` increments version
- `is_ranking_stale(cid, old_version)` → True after bump
- `ranking_cache_key()` embeds channel version — identity change invalidates stale key

---

## ১৬. Integration Tests

- `run_topic_intelligence()` with TECH profile produces evaluated + ranked output
- `from_channel_row(tech)` → `style_family=gadget` used in orchestrator path
- LONG vs SHORT: identical `CHANNEL_RELEVANCE` for same topic (format does not corrupt niche signal)

---

## ১৭. Regression Tests

| Suite | Result |
|-------|--------|
| RV-006 (`test_reverification_rv006.py`) | 13/13 PASS |
| RV-007 (`test_reverification_rv007.py`) | 20/20 PASS |
| BUILD-04G-H (`test_build04g_hardening.py`) | 21/21 PASS |
| BUILD-04G-H1 (`test_build04g_h1_idempotency_concurrency.py`) | 6/6 PASS |
| BUILD-04G (`test_build04g_topic_research.py`) | 58/58 PASS |

---

## ১৮. Evidence Mapping

| Criterion | Code | Production | Test | Evidence |
|-----------|------|------------|------|----------|
| Channel profile reaches intelligence | `scoring.channel_profile_from_row` | `bridge.enrich_channel_topic` | TEST-15 | PASS |
| Channel DNA used in scoring | `score_topic(dna)` | `score_candidate` | TEST-01–06 | PASS |
| Niche classification deterministic | `infer_style_family` | `from_channel_row` | classification tests | PASS |
| TECH correct | `channel_dna.py` | all paths | TEST-01, tech≠history | PASS |
| HISTORY correct | `channel_dna.py` | all paths | TEST-03, gadget block | PASS |
| Other niches | markers in `channel_dna.py` | scoring | TEST-05,06 | PASS |
| Unknown niche explicit | `infer_style_family("")` → general | `from_channel_row` | TEST-07,08 | PASS |
| Relevant > irrelevant scores | `topic_scoring.py` | orchestrator | TEST-01–04 | PASS |
| Cross-channel isolation | orchestrator per-run state | bridge | TEST-09 | PASS |
| Multi-channel isolation | thread-local work dirs | bridge | TEST-09 | PASS |
| Keyword trap documented+mitigated | `_apply_niche_mismatch_penalty` | score_topic | TEST-12 | PASS (heuristic) |
| Multilingual identity | `normalization.py` | scoring | TEST-11 | PASS |
| Cache invalidation | `cache_registry.py` | orchestrator metadata | TEST-14 | PASS |
| Production path connected | `video_pipeline` → bridge | live path | TEST-15 | PASS |
| Negative tests | — | — | §12 | PASS |
| Dedicated report | this file | — | — | PASS |

---

## ১৯. Limitations

1. **Heuristic semantic scoring:** `_apply_niche_mismatch_penalty` ও `_niche_context_adjustment` marker-based — full LLM semantic understanding নয়। জটিল edge case-এ false positive/negative সম্ভব।
2. **Keyword trap mitigation partial:** "technology" শব্দযুক্ত history topic TECH-এ cap পায়, কিন্তু সব semantic trap cover করে না।
3. **NEWS / SPORTS:** explicit style_family নেই — `general` বা marker match-এ পড়ে।
4. **SPORTS / NEWS inventory:** codebase-এ dedicated family নেই — `ENTERTAINMENT`/`GENERAL` fallback।

---

## ২০. Deferred Issues

| ID | Issue |
|----|-------|
| RV-DEF-001 | External live research API — RV-008 scope বাইরে |
| DEF-001 | Multi-process locks thread-only — RV-008 scope বাইরে |
| RV-008-DEF-001 | Deep semantic niche model (beyond marker heuristics) — future enhancement |

---

## ২১. Final Verdict

**RV-008 = VERIFIED_PASS**

সব mandatory acceptance criterion runtime evidence সহ পূরণ হয়েছে। Dedicated test 21/21 PASS, regression suites PASS, surgical fix applied for keyword-trap ও borderline scoring gap।

---

*AMP-002 RV-008 সম্পন্ন — RV-009 শুরু হয়নি। পরবর্তী task-এর জন্য user command প্রয়োজন।*
