# C11 Incidents (canonical run mr_89cec56060114780)

## INC-PRE — mr_5c5e3931ff484ff5
- stage: GENERATION
- error: `scene_contract_blocked:...missing_must_show`
- severity: CRITICAL
- resolution: INT-001

## INC-PRE — mr_a077c5b821db4464
- stage: GENERATION
- error: `should_skip_gemini_critic() got an unexpected keyword argument 'visual_passed'`
- severity: CRITICAL
- resolution: INT-002

## INC-FINAL — mr_89cec56060114780 LONG/SHORT
- stage: QUALITY / PUBLISHABILITY
- error: `Publishability gate blocked: creative_regenerate_required (creative=REGENERATE_REQUIRED)`
- contributing: Gemini critic 503/404; Groq/Cerebras model access 404; AV critic exhausted
- severity: CRITICAL
- resolution: NONE (gate correctly fail-closed; provider model update deferred — not safe global provider-contract redesign mid-Marathon)
- classification: PROVIDER_ENVIRONMENT_BLOCK + QUALITY_FAIL_CLOSED
