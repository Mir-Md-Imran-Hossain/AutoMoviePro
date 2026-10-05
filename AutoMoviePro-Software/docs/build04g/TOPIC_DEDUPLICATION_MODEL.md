# TOPIC DEDUPLICATION MODEL (BUILD-04G)

**ভাষা:** বাংলা

## ৪-স্তর কৌশল

1. **Exact** — canonical key, normalized title
2. **Token** — Jaccard ≥ 0.85
3. **Semantic** — product_registry similarity + intent similarity
4. **Entity+Event** — shared entity + action synonym overlap

## Verdict

- UNIQUE / POSSIBLE_DUPLICATE / DUPLICATE / UNKNOWN
- UNKNOWN কখনো স্বয়ংক্রিয়ভাবে UNIQUE হয় না

## LLM ব্যবহার

নিষিদ্ধ — duplicate detection সম্পূর্ণ deterministic।
