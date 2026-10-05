# Phase 7A — Language Entitlement Report

**Checkpoint:** `PHASE7A-ENTITLEMENT-BLOCKED`  
**Date (UTC):** 2026-09-09  
**Customer:** `c11_marathon_customer`  
**Channel:** `4` / `C11 Marathon Channel`  
**Marathon started:** NO  
**Paid API / provider calls:** **0**  
**Production generation:** NONE  

---

## Current State

| Field | Value |
|-------|-------|
| `channel_languages(4)` | `["en","bn"]` |
| Required | `["en","bn","hi","ur","ta","ml"]` |
| `session` rows | **0** |
| `language_requests` rows | **0** |
| `session.customer.unlocked` | **ABSENT** (no session) |
| Ownership | PASS (`owner_login_id=c11_marathon_customer`, enabled) |
| C04 six-lang write without remote unlock | **FAIL** `language_not_entitled` / `hi` |

---

## Entitlement Architecture Audit

### Two layers (must not be conflated)

| Layer | Authority | Meaning |
|-------|-----------|---------|
| **Product catalog** | `pipeline.lang_config.TARGET_LANG_CODES` | Six codes *supported by software* |
| **Account entitlement** | Remote license `customer.unlocked` (+ sync) | Six codes *this customer may configure* |

**Catalog ≠ entitlement.** This phase treats them as separate.

### Canonical production unlock path (exists)

```
SETUP: en + 1 secondary → channels.languages_json
  → POST /api/languages/request (payment_ref/note) → LicenseClient.language_request
  → Website admin approves → customer.unlocked / language-status.php
  → POST /api/languages/sync OR re-login merge
  → POST /api/channels/{id}/languages
       entitled_unlocked = session.customer.unlocked
       set_channel_languages(...)  [C04]
```

### Key code authorities

| Role | Location |
|------|----------|
| C04 write gate | `app.customer_config.set_channel_languages` |
| Entitled set | `entitled_unlocked ∪ channel_languages(ch)` |
| Login merge | `app/main.py` login handler → merge `customer.unlocked` into channel |
| Sync | `POST /api/languages/sync` → `LicenseClient.language_status()` |
| Purchase request | `POST /api/languages/request` → remote + `language_requests` |
| Local/dev approve | `POST /api/languages/local-approve` (**dev-only**, `AMP_ALLOW_LOCAL_LOGIN`) |
| License gateway | `app.api_client.LicenseClient` (H2) |
| C02 session | `app.customer_auth` / `session.customer_json` |
| Helpers | `pipeline.lang_entitlement` (`can_request`, `unlock_language`, `channel_languages`) |

### Explicitly non-production for entitlement completion

- `local-approve` (dev gate)
- Forged `entitled_unlocked` without remote source
- Offline `language_status()` → `["en"]` only
- Local login `plan:dev` without `unlocked` field
- Direct JSON DB edit of `languages_json`

---

## Authoritative Entitlement Source

**Intended source of truth for secondary packs (hi/ur/ta/ml):**

Remote SaaS license gateway (`/api/me.php`, `/api/language-status.php`, `/api/language-request.php`) → persisted as `session.customer_json.unlocked` → passed into C04 as `entitled_unlocked`.

**Observed for this environment:**

| Source | Present? |
|--------|----------|
| Live session with `customer.unlocked` containing hi/ur/ta/ml | **NO** |
| Approved `language_requests` | **NO** |
| Channel already configured with hi/ur/ta/ml | **NO** |
| Website admin grant already applied | **UNKNOWN / not evidenced locally** |

---

## Before State

```json
["en", "bn"]
```

---

## Action Taken

| Action | Result |
|--------|--------|
| Architecture forensic audit | DONE |
| Re-read ownership / langs / session / requests | DONE |
| Honest C04 attempt without remote unlock | **REJECTED** (`language_not_entitled:hi`) |
| Fake `entitled_unlocked` | **NOT USED** |
| `local-approve` | **NOT USED** |
| Language purchase / payment request | **NOT USED** (requires payment + remote admin; out of Cursor scope here) |
| License login / sync against production API | **NOT PERFORMED** (no usable entitled session in DB; would need real account credentials + remote grant) |
| Channel mutation | **NONE** (state unchanged) |
| Marathon / generation / YouTube | **NONE** |

### Why Cursor cannot complete unlock in this phase

Legitimate next steps require **website/admin language-pack grant** and/or **customer paid language request + remote approval**, then desktop **login/sync**. Those are external to this workspace’s empty session. Completing them here would require fabricating entitlement or running payment flows — both forbidden.

---

## After State

```json
["en", "bn"]
```

(Unchanged.)

---

## Six-Language Verification

| Criterion | Status |
|-----------|--------|
| 1. Channel ownership PASS | **PASS** |
| 2. Real entitlement PASS for en,bn,hi,ur,ta,ml | **FAIL** (hi/ur/ta/ml not entitled) |
| 3. C04 canonical update PASS | **FAIL** (blocked by entitlement) |
| 4. Exact six languages on channel 4 | **FAIL** |
| 5. No duplicate | N/A (not written) |
| 6. No unsupported language | N/A |
| 7. Customer isolation | **PASS** (no cross-customer write) |
| 8. Entitlement source traceable | **FAIL** (source absent) |
| 9. No forged unlock | **PASS** |
| 10. No fake local approval | **PASS** |
| 11. Paid provider usage = 0 | **PASS** |
| 12. No production generation | **PASS** |

---

## Urdu RTL Status

| Check | Result |
|-------|--------|
| `ur` in `RTL_LANGS` | YES |
| `classify_rtl_support("ur")` | `rtl=True`, **status=UNKNOWN**, `support_level=PARTIAL_FONT_ONLY`, `shaping_guaranteed=false` |
| Full shaping verification via rendered media | **NOT RUN** (forbidden this phase) |

**`UR_RTL_SHAPING = UNKNOWN`**

`rtl=True` is **not** treated as full production language PASS.

---

## Blocker Classification

### **B** — Entitlement mechanism exists, but this customer/session has no real entitlement

| Option | Fits? |
|--------|-------|
| A — unlock possible for this customer in this env now | NO |
| **B — mechanism exists; no real entitlement here** | **YES** |
| C — no legitimate unlock mechanism in product | NO (remote request + admin + sync exists) |
| D — entitlement exists but C04 mapping broken | NO (C04 correctly rejects) |

Evidence: empty session; empty `language_requests`; C04 `language_not_entitled` for `hi`; `can_request(hi|ur|ta|ml)` returns ok against current channel langs (purchase *slots* available under max 6 — commercial path, not proof of entitlement).

---

## Tests

| Suite | Result |
|-------|--------|
| `scripts/test_c04_customer_configuration.py` | **OK** (53) |
| `scripts/test_c02_customer_auth.py` | **OK** (35) |
| Paid provider calls | **0** |

No entitlement authority replaced. Failures not ignored.

---

## Paid API Usage

**0** (research/TTS/visual/critic/YouTube: none).  
Language-pack commercial APIs: not invoked.

---

## Files Changed

**None** (report-only; no production code; no lasting DB entitlement writes).

Report path: `docs/marathon/customer_product/PHASE7A_LANGUAGE_ENTITLEMENT_REPORT.md`

---

## Security / Isolation Verification

| Check | Status |
|-------|--------|
| Ownership gate used | PASS |
| Cross-customer language write | NONE |
| Secrets in this report | NONE |
| C04 gate weakened | NO |
| Fake license/subscription | NO |

---

## Remaining Blockers

### P1 — Missing real language-pack entitlement for hi/ur/ta/ml

| Field | Detail |
|-------|--------|
| Missing entitlement source | `session.customer.unlocked` / remote `language-status.php` grant |
| Authority that should supply it | License SaaS admin approve after `language_request`, or direct admin grant on account |
| Absent records | Empty `session`; empty `language_requests` |
| Why C04 cannot configure | Non-en codes must be in `entitled_unlocked ∪ channel_languages`; hi not in either |
| Why Marathon cannot start | Phase 7 requires exact six configured+entitled languages |

### Exact next human/admin/account action

1. On automoviepro.com license/billing: grant `hi`,`ur`,`ta`,`ml` for `c11_marathon_customer` **or** customer submits paid language requests and admin approves.  
2. Desktop: real API login (not offline) as that customer.  
3. `POST /api/languages/sync` (or re-login merge).  
4. `POST /api/channels/4/languages` with canonical six codes via C04.  
5. Verify `channel_languages(4) == ["en","bn","hi","ur","ta","ml"]` (or C04 canonical order from `parse_languages`).  
6. Re-run C04 tests; then Phase 7 Marathon may be considered for readiness — **not auto-started here**.

### Secondary limitation (post-entitlement)

- `UR_RTL_SHAPING` remains **UNKNOWN** until a later phase observes real rendered Urdu subtitles (not this phase).

---

## Phase 7 Marathon Readiness

**NOT READY.**

`PHASE 7 REAL MARATHON = NOT READY`

Do not start Marathon until `PHASE7A-LANGUAGE-CONFIGURATION-READY` is achieved via **real** entitlement + C04 verification.

---

## FINAL CHECKPOINT

# `PHASE7A-ENTITLEMENT-BLOCKED`

## HARD STOP

No Marathon. No generation. No YouTube. No fake unlock. No C04 bypass. No new entitlement engine.
