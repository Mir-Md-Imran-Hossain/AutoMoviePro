# PHASE7 — Language Configuration Completion

**Checkpoint:** `PHASE7-LANGUAGE-CONFIGURATION-BLOCKED`  
**Date (UTC):** 2026-09-09  
**Customer:** `c11_marathon_customer`  
**Channel:** `4` / `C11 Marathon Channel`  
**Marathon started:** NO  
**Paid API calls:** **0**

---

## FINAL CHECKPOINT

### `PHASE7-LANGUAGE-CONFIGURATION-BLOCKED`

Exact six-language configuration was **not** verified as entitled + configured.

`configured_languages` remains:

```json
["en", "bn"]
```

Required for READY:

```json
["en", "bn", "hi", "ur", "ta", "ml"]
```

Phase 7 Marathon is **NOT READY**.

---

## STEP 0 — Audit

| # | Check | Result |
|---|-------|--------|
| 1 | Channel ownership | **PASS** — `owner_login_id=c11_marathon_customer`, `enabled=1`, `require_owned_channel(4, login)` OK |
| 2 | Current channel languages | **`["en","bn"]`** |
| 3 | Product target languages | **`("en","bn","hi","ur","ta","ml")`** via `pipeline.lang_config.TARGET_LANG_CODES` |
| 4 | Entitlement state | **MISSING for hi/ur/ta/ml** — no session `customer.unlocked`; `language_requests` empty; `session` table empty |
| 5 | Language readiness / provider capability (catalog) | Product TTS/Edge voice entries exist for all six in `lang_config` (capability catalog only — **not** entitlement) |
| 6 | C04 canonical path | `app.customer_config.set_channel_languages` ← `POST /api/channels/{id}/languages` with `entitled_unlocked` from session remote unlocks |
| 7 | Language-pack / localization rules | `channel_languages` drives `localize_master_clip`; max 6; setup pair = en + 1 secondary |
| 8 | `ur` RTL | Listed in `RTL_LANGS`; `classify_rtl_support("ur")` → **rtl=True**, status **UNKNOWN**, `shaping_guaranteed=false` (PARTIAL_FONT_ONLY) — **not** full RTL PASS |
| 9 | Per-language TTS/subtitle/text readiness | Catalog voices present for en/bn/hi/ur/ta/ml; subtitle RTL shaping for `ur` remains UNKNOWN |
| 10 | Customer/channel isolation | Configuration gated by `require_owned_channel`; no cross-customer write attempted |

### Authoritative entitlement attempt (honest)

```text
set_channel_languages(
  4, "c11_marathon_customer",
  ["en","bn","hi","ur","ta","ml"],
  entitled_unlocked=None,
  allow_setup_pair=False,
)
→ {
  "ok": false,
  "error": "language_not_entitled",
  "lang_code": "hi",
  "state": "NOT_ENTITLED",
  "message": "This language is not entitled for this account."
}
```

**Missing authority / configuration:** real account entitlement for secondary languages **`hi`, `ur`, `ta`, `ml`** (license/session `customer.unlocked` or approved paid language unlock flow).  
Without that, C04 correctly refuses to write six languages.

### Declined (forbidden) paths

| Path | Status |
|------|--------|
| `entitled_unlocked=["bn","hi","ur","ta","ml"]` invented locally | **NOT USED for completion** |
| `/api/languages/local-approve` | **NOT USED** |
| Payment / subscription unlock test | **NOT USED** |
| JSON-only DB edit to fake PASS | **NOT USED** |
| English-only fallback labeled as six-lang PASS | **NOT USED** |

### Diagnostic note (not a completion)

A one-shot diagnostic confirmed that *passing forged* `entitled_unlocked` would make `set_channel_languages` return ok. That write was **immediately rolled back** to `["en","bn"]`. Final DB state verified `["en","bn"]`. This does **not** count as configuration completion.

---

## Before / After

| | Languages |
|--|-----------|
| **Before** | `["en","bn"]` |
| **After** | `["en","bn"]` (unchanged) |

---

## Entitlement evidence

| Language | Configured on ch4 | Entitled (real) | Production-safe claim |
|----------|-------------------|-----------------|------------------------|
| en | YES | YES (source) | catalog OK |
| bn | YES | YES (on channel / setup pair) | catalog OK |
| hi | NO | **NO** | N/A |
| ur | NO | **NO** | RTL UNKNOWN even if entitled later |
| ta | NO | **NO** | N/A |
| ml | NO | **NO** | N/A |

---

## Readiness evidence

- Product supports six codes in `TARGET_LANG_CODES` / Edge + Gemini TTS contracts.
- **Account entitlement does not currently unlock hi/ur/ta/ml** for `c11_marathon_customer`.
- `ur` RTL: recognized RTL language; shaping **not** guaranteed → readiness for full Urdu subtitle production remains **UNKNOWN** even after future entitlement.

---

## Exact files changed

**None lasting.** No production code changes. Channel languages JSON not left in a six-language state.

---

## Exact tests

| Suite | Result |
|-------|--------|
| `scripts/test_c04_customer_configuration.py` | **OK** (53) |
| Paid provider calls during this phase | **0** |

(C01–C06 full matrix not re-run end-to-end; C04 focused gate executed. No workflow generation started.)

---

## Limitations

1. Cannot complete six-language C04 configuration without real unlock entitlement.  
2. Payment testing forbidden in this command → cannot purchase unlocks here.  
3. Local approve forbidden → cannot fabricate unlocks.  
4. `ur` RTL shaping remains UNKNOWN (system honesty).  

---

## Phase 7 Marathon READY?

**NO.**

Do not start Phase 7 Marathon until:

1. Real entitlement grants `hi`,`ur`,`ta`,`ml` for this customer (license/session unlock or legitimate paid unlock approval), **and**
2. C04 `set_channel_languages` succeeds with `entitled_unlocked` from that real source, **and**
3. `channel_languages(channel_4) == ["en","bn","hi","ur","ta","ml"]` exactly, **and**
4. Re-verification + C04 tests PASS.

---

## HARD STOP

Configuration completion **BLOCKED**. Marathon **not** started. No YouTube. No paid APIs. No new engines. No gate weakening.
