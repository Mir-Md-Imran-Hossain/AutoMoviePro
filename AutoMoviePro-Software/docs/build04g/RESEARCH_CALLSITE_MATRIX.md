# RESEARCH CALLSITE MATRIX (BUILD-04G)

**ভাষা:** বাংলা

| # | ফাইল | ফাংশন | প্রোভাইডার | API | মডেল | query | ইনপুট | আউটপুট | evidence | retry | cache | idempotency | cost | persistence |
|---|------|--------|-----------|-----|------|-------|-------|--------|----------|-------|-------|-------------|------|-------------|
| 1 | `fact_pack.py` | `build_fact_pack()` | local | — | — | notes sentences | topic, notes | claims JSON | research_notes | — | — | — | free | memory |
| 2 | `factpack_bridge.py` | `idempotent_build_fact_pack()` | local | — | — | topic | topic, notes | factpack JSON | claims | BUILD-03 | fingerprint | BUILD-03 | free | work_dir/factpack |
| 3 | `plan_quality.py` | `enforce_plan_quality()` | local | — | — | — | plan, fact_pack | gated plan | claim_allowed | — | — | — | free | inline |
| 4 | `contract_wiring/stages.py` | topic research wire | local/LLM | varies | — | topic title | Topic | TopicResearch | ResearchEvidence | — | — | BUILD-02 | — | canonical |
| 5 | `intelligence/research_runtime.py` | `execute_research_request()` | mock/local | — | research-v1 | normalized query | ResearchRequest | research+fact_pack | classified | BUILD-03 | fingerprint store | BUILD-03 | ApiCostMetrics | work_dir/research |
| 6 | `intelligence/orchestrator.py` | research loop | mock (default) | — | research-v1 | canonical_topic | per candidate | gate result | PRIMARY/SECONDARY | — | reuse | BUILD-03 | tracked | JSON sidecar |

---

## API খরচ নিয়ন্ত্রণ

- Research আগে fingerprint cache check
- Duplicate detection-এ কোনো paid API নেই
- Mock provider offline test-এ ব্যবহৃত
