# BUILD-04G প্রি-বিল্ড অডিট (PRE_BUILD04G_AUDIT)

**বিল্ড আইডি:** BUILD-04G  
**বেসলাইন:** BUILD-04F = PASS  
**তারিখ:** ২০২৬-০৮-৩১  
**ভাষা:** বাংলা

---

## ১. উদ্দেশ্য

বিদ্যমান Topic + Research পাইপলাইনকে চ্যানেল-সচেতন, প্রমাণ-সচেতন, খরচ-নিয়ন্ত্রিত এবং ডুপ্লিকেট-প্রতিরোধী ইন্টেলিজেন্স সিস্টেমে আপগ্রেড করা — **সম্পূর্ণ পুনর্লিখন ছাড়াই**।

---

## ২. বিদ্যমান মডিউল (পুনঃব্যবহার)

| ক্ষেত্র | ফাইল | অবস্থা |
|--------|------|--------|
| Topic চুক্তি | `domain/topic.py` | বিদ্যমান |
| Research চুক্তি | `domain/research.py` | TopicResearch, ResearchEvidence |
| FactPack | `domain/fact_pack.py`, `pipeline/fact_pack.py` | ক্যানোনিক্যাল |
| FactPack ব্রিজ | `pipeline/idempotency/factpack_bridge.py` | BUILD-03 idempotency |
| Topic স্কোরিং | `pipeline/topic_scoring.py` | ওজনভিত্তিক rank |
| ডুপ্লিকেট (পণ্য) | `pipeline/product_registry.py` | Jaccard, is_duplicate |
| Channel DNA | `pipeline/channel_dna.py` | niche gating |
| Trending | `pipeline/trending_search.py` | find_trending_gadgets |
| এন্ট্রি পয়েন্ট | `pipeline/video_pipeline.py` | topic নির্বাচন, duplicate check |
| Plan quality | `pipeline/plan_quality.py` | Fact gate (পোস্ট-প্রসেস) |

---

## ৩. শনাক্তকৃত ফাঁক (GAP)

1. আলাদা `topic_engine` মডিউল ছিল না → **`pipeline/intelligence/`** তৈরি
2. Long/Short আলাদা reserve queue ছিল না → **`reserve_queue.py`**
3. FactPack ব্রিজ মূল `generate_video()` পথে wired ছিল না → research runtime দিয়ে সংযুক্ত
4. সেমান্টিক duplicate engine ছিল না → **`duplicate.py`** (৪-স্তর)
5. API cost tracking intelligence job-এ ছিল না → **`ApiCostMetrics`**

---

## ৪. নতুন যোগ করা মডিউল

```
pipeline/intelligence/
├── __init__.py
├── contracts.py          # ChannelProfile, TopicCandidate, enums
├── normalization.py      # টেক্সট নরমালাইজেশন
├── duplicate.py          # ৪-স্তর duplicate
├── scoring.py            # বহুমাত্রিক স্কোর
├── trend.py              # ট্রেন্ড + SEO
├── ranking.py            # র‍্যাঙ্কিং + diversity
├── reserve_queue.py      # long/short reserve
├── fingerprint.py        # research/topic identity
├── research_runtime.py   # BUILD-03 idempotent research
├── factpack_gate.py      # FactPack quality gate
├── mock_research_provider.py
├── orchestrator.py       # run_topic_intelligence
├── bridge.py             # video_pipeline সংযোগ
└── provenance.py         # traceability
```

---

## ৫. সংযুক্তি পয়েন্ট

- `pipeline/video_pipeline.py` — BUILD-04G surgical hook (reserve pick + enrich)
- `pipeline/intelligence/bridge.py` — enrich_channel_topic, pick_topic_from_reserve

---

## ৬. অনুপস্থিত authority নথি

কোনো প্রয়োজনীয় authority নথি **তৈরি করা হয়নি** — সব referenced docs বিদ্যমান ছিল।

---

## ৭. সিদ্ধান্ত

- LLM duplicate detection-এ ব্যবহার করা হয়নি (deterministic প্রথম)
- Open-source: Jaccard, unicodedata, existing product_registry similarity
- BUILD-04F creative quality duplicate করা হয়নি — শুধু intelligence input সরবরাহ
