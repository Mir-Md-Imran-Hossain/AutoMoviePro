# TOPIC CALLSITE MATRIX (BUILD-04G)

**ভাষা:** বাংলা

| # | ফাইল | ফাংশন | কলার | প্রোভাইডার | মডেল | prompt_version | ইনপুট | আউটপুট | persistence | cache | idempotency | retry | duplicate | ranking | validation |
|---|------|--------|------|-----------|------|----------------|-------|--------|-------------|-------|-------------|-------|-----------|---------|------------|
| 1 | `video_pipeline.py` | `generate_video()` | scheduler/manual | LLM (director) | niche_director | prompt_registry | channel, niche, topic | director_plan | work_dir JSON | generation_cache | BUILD-03 partial | retry_policy | product_registry | topic_scoring | plan validation |
| 2 | `video_pipeline.py` | trending block | generate_video | Google CSE | — | — | google_keys, exclude | topic name | — | — | — | — | blocked_names | — | niche gate |
| 3 | `trending_search.py` | `find_trending_gadgets()` | video_pipeline | Google API | — | — | keys, count | gadget list | — | — | — | — | exclude_names | — | — |
| 4 | `product_registry.py` | `is_duplicate()` | video_pipeline | local | — | — | topic, channel_id | bool+match | reviewed_products DB | — | — | — | Jaccard | — | — |
| 5 | `topic_scoring.py` | `score_topic()` | golden_harness | local | — | — | title, DNA | score dict | — | — | — | — | is_duplicate flag | rank_topics | threshold |
| 6 | `niche_director` | plan generation | video_pipeline | LLM | gemini/etc | prompt_registry | channel DNA | plan JSON | director_plan.json | cache | BUILD-03 script | yes | blocked_products | — | scene count |
| 7 | `intelligence/bridge.py` | `enrich_channel_topic()` | video_pipeline (04G) | mock/local | research-v1 | 1.0.0 | topic, channel | score+research | intelligence/ | idempotency store | BUILD-03 | retry_policy | analyze_duplicate | rank | factpack_gate |
| 8 | `intelligence/orchestrator.py` | `run_topic_intelligence()` | tests/bridge | mock | research-v1 | 1.0.0 | candidates | ranked+reserve | intelligence/ | fingerprint | BUILD-03 | — | layered | rank_candidates | hard blocks |

---

## নোট

- প্রধান production callsite: `video_pipeline.generate_video()` — BUILD-04G hook যোগ করা হয়েছে।
- Director LLM rewrite করা হয়নি — intelligence layer আগে চলে।
