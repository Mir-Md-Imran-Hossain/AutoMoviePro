# BUILD-04G-H প্রি-হার্ডেনিং বেসলাইন (PRE_HARDENING_BASELINE)

**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা  
**বিল্ড:** BUILD-04G-H-BASELINE

---

## compileall

`python -m compileall -q pipeline` — **PASS**

---

## রিগ্রেশন ফলাফল (কোড পরিবর্তনের আগে)

| Suite | ফলাফল |
|-------|--------|
| BUILD-00R | PASS (5/5) |
| BUILD-01 | PASS (18/18) |
| BUILD-02 | PASS (17/17) |
| BUILD-03 | PASS (14/14) |
| BUILD-04A | PASS |
| BUILD-04B | PASS |
| BUILD-04B-H | PASS |
| BUILD-04C | PASS |
| BUILD-04D | PASS (skipped=2) |
| BUILD-04E | PASS |
| BUILD-04F | PASS |
| BUILD-04G | PASS (58/58) |

---

## অডিট P0/P1 — নিশ্চিত সমস্যা

| ID | সমস্যা | অবস্থান |
|----|--------|---------|
| P0-01 | Lock registry race (`if key not in _STORE_LOCKS`) | `pipeline/idempotency/store.py:18-22` |
| P0-02 | Production `use_mock_research=True` default | `video_pipeline.py:154`, `bridge.py:37` |
| P0-03 | Intelligence exception → warning → continue | `video_pipeline.py:162-163` |
| P1-01 | Reserve per work_dir only | `reserve_queue.py:13-14` |
| P1-02 | `refresh_topic_intelligence` শুধু repair, rerank নয় | `orchestrator.py:188-201` |
| P1-03 | Rank before research complete | `orchestrator.py:111-147` |
| P1-04 | No real discovery pipeline | missing |
| P1-06 | `infer_style_family` unknown niche → history | `channel_dna.py:86-88` |
| P1-09 | SEO heuristic as real SEO | `scoring.py`, `trend.py` |
| P1-12 | Invalidation markers only | `provenance.py` |
| P1-13 | FactPack gate too permissive | `factpack_gate.py` |
| P1-17 | Fixed `.tmp` filename | `reserve_queue.py:30`, `store.py:106` |

---

## Hardening scope

Surgical fixes only — no architecture rewrite.

---

## Logical checkpoint

`BUILD-04G-H-BASELINE` (documented; git tag not created unless requested)
