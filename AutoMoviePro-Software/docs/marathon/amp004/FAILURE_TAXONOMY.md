# Failure Taxonomy — AMP-004 PHASE-4

**Production code changed:** `false`

নীতি: প্রতিটি failure → PREVENTION / DETECTION / REPAIR / BLOCK POLICY  
Confidence: TYPE-1…5 (deterministic → human)

---

## ১. Visual failure taxonomy

| Failure | Prevention | Detection | Repair | Block | Type |
|---------|------------|-----------|--------|-------|------|
| Object substitution | Entity grounding in SceneIntent | entity_grounding / fixture | VISUAL_ASSET | HARD (strict) | 2–4 |
| Object disappearance | required_objects | missing object validator | VISUAL_ASSET | HARD (strict) | 2–4 |
| Object duplication | quantity on SemanticEntity | partial | VISUAL_ASSET | SOFT→HARD if salience | 3–4 |
| Object count changes | quantity field | weak | VISUAL | SOFT | 3–4 |
| Ownership confusion | parent_id / part_of | component_as_separate | VISUAL | HARD | 2–4 |
| Attribute misbinding | attributes + owner id | misbinding check | VISUAL | HARD | 2–4 |
| Phone→standalone camera | infer_phone_camera_entities + negatives | component checks | VISUAL | HARD | 2 |
| Wrong object type | forbidden_objects | validators | VISUAL | HARD | 2–4 |
| Wrong object state | state field | weak | VISUAL | SOFT | 3–4 |
| Impossible interaction | forbidden_actions | conflict pairs | VISUAL | HARD | 2 |
| Impossible simultaneous actions | conflict pairs | CONFLICTING_ACTION | VISUAL | HARD | 2 |
| Wrong actor | actors list | wrong_actor / continuity | VISUAL/SCENE | HARD | 2–4 |
| Wrong posture | posture | POSTURE_MISMATCH | VISUAL | HARD | 2 |
| Wrong location | location | LOCATION_MISMATCH | VISUAL | HARD | 2 |
| Wrong spatial relation | EntityRelation | relation confusion | VISUAL | MEDIUM/HARD | 2–4 |
| Wrong temporal order | TemporalAction | TEMPORAL_CONTRADICTION | VISUAL | HARD | 2 |
| Character identity drift | ContinuityTracker | CONTINUITY_BREAK | VISUAL | HARD if unexplained | 2–4 |
| Wardrobe drift | continuity_refs | weak | VISUAL | SOFT | 3–5 |
| Environment drift | continuity location | CONTINUITY_BREAK | VISUAL | HARD | 2 |
| Lighting drift | — | **GAP** | — | UNKNOWN | 3–5 |
| Camera-style drift | negative DSLR constraints | prompt contradiction | PROMPT/VISUAL | HARD if constrained | 2 |
| Temporal flicker | — | **GAP** | VISUAL | SOFT | 3 |
| Motion deformation | — | **GAP** | VISUAL | UNKNOWN | 3–5 |
| Anatomy errors | — | **GAP** | VISUAL | UNKNOWN | 4–5 |
| Continuity break | flags | tracker | VISUAL | HARD | 2 |
| Scene-to-scene contradiction | tracker | continuity | SCENE | HARD | 2 |

**সারাংশ:** Entity/action/location/posture = partial PREVENT+DETECT (heuristic/offline)। Anatomy/lighting/flicker = mostly UNKNOWN (TYPE-3/4/5)।

---

## ২. Script failure taxonomy

| Failure | Pre-visual detectable? | Detection today | Policy |
|---------|------------------------|-----------------|--------|
| Weak hook | Yes (text) | 04F HOOK_STRENGTH | SOFT/REPAIR |
| Generic opening | Yes | heuristic | SOFT |
| Factual hallucination | Partial vs FactPack | FACTUAL_COHERENCE | HARD if unsupported critical |
| Unsupported claim | Yes if pack present | evaluator | HARD/REPAIR |
| Repeated information | Yes | text overlap | SOFT |
| Poor pacing | Partial | PACING dim | SOFT |
| Unnatural dialogue | Partial | DIALOGUE_NATURALNESS | SOFT |
| Robotic wording | Yes | robot_detector / 04F | SOFT |
| Unnecessary exposition | Weak | heuristic | SOFT |
| Missing context/payoff | Partial | structure | SOFT/REPAIR |
| Weak progression | Partial | retention_architecture | SOFT |
| Wrong emotional progression | Weak | emotion tags | SOFT |
| Visual impossibility from script | Partial | prompt/entity | HARD when detected |
| Audio impossibility | Partial | duration budget | HARD |
| Localization difficulty | Weak | — | SOFT |
| Subtitle density | Yes (length) | 04E | HARD if structural |
| Retention weakness | Heuristic | 04F | SOFT |
| Niche mismatch | Yes | channel DNA / scoring | HARD gate |

---

## ৩. Audio failure taxonomy

| Failure | Detection | Policy |
|---------|-----------|--------|
| Wrong pronunciation | **GAP** (needs ASR) | UNKNOWN |
| Wrong language | keys/meta | HARD |
| Wrong voice / drift | voice profile id | HARD/SOFT |
| Emotion mismatch | heuristic tags | SOFT |
| Unnatural pacing / pauses | speech_pace gates | HARD |
| Dialogue timing mismatch | duration gates | HARD |
| Clipping | weak | SOFT/UNKNOWN |
| Silence gaps | leading_silence / cutoff | HARD |
| Loudness inconsistency | **GAP** | UNKNOWN |
| Music/SFX masking | **GAP** (no music/SFX) | N/A |
| Wrong/missing/repetitive SFX | **GAP** | N/A |
| Inappropriate music | **GAP** | N/A |
| Poor ducking | **GAP** | N/A |
| A/V desync | av_desync_length | HARD |

---

## ৪. Localization / subtitle

| Failure | Detection | Policy |
|---------|-----------|--------|
| Semantic mistranslation | C3 localization_semantic (offline) | HARD when fixture |
| Loss of nuance | weak | SOFT/UNKNOWN |
| Unnatural phrasing | weak | SOFT |
| Timing mismatch | 04E + timeline | HARD |
| Speaker mismatch | dialogue_id | HARD |
| Wrong subtitle / dialogue mismatch | text overlap heuristic | HARD/HIGH |
| Excessive reading speed | partial | SOFT→HARD |
| Line overflow / overlap | structural 04E | HARD |
| Unsafe placement | limited | SOFT |
| Inconsistent terminology | **GAP** | SOFT |

---

## ৫. Text / VFX / effects

| Failure | Status |
|---------|--------|
| Typo / wrong text | Partial burn-in paths; not full OCR |
| Wrong timing / unreadable | limited |
| Excessive animation / random zoom / shake | Fallback motion exists; purposeful-effects policy **missing** |
| Style inconsistency | soft |
| Effect/audio/dialogue mismatch | **GAP** |
| Goal | PURPOSEFUL EFFECTS ONLY — architecture recommendation, not implemented |

---

## PHASE-4 acceptance

- [x] Visual / script / audio / localization / effects taxonomies  
- [x] TYPE honesty  
- [x] No code change  

**→ PHASE-4 PASS.**
