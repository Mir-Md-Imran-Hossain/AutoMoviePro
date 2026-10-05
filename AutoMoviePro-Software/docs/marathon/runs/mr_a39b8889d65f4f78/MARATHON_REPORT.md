# Marathon Forensic Report — `mr_a39b8889d65f4f78`

**Schema:** c10.evidence.v1
**Generated:** 2026-09-06T15:52:59Z
**Paid API calls (recorded):** 7

## 1. Executive Summary
- Session: `ms_9ab8015ff538400b`
- Video type: **LONG**
- Final status: **COMPLETED**
- Anomaly count: 3
- Verdict: **PASS**

## 2. Run Identity
```json
{
  "ok": true,
  "contract": "C10.1",
  "marathon_session_id": "ms_9ab8015ff538400b",
  "run_id": "mr_a39b8889d65f4f78",
  "test_case_id": "MARATHON_LONG",
  "video_type": "LONG",
  "login_id": "c11_marathon_customer",
  "channel_id": 1,
  "niche": "space science",
  "locale": "en",
  "timezone": "UTC",
  "application_version": "0.5.0",
  "source_release_revision": "h5-source",
  "environment": "c11_real_marathon",
  "start_time": "2026-09-06T15:45:18Z",
  "end_time": "2026-09-06T15:52:59Z",
  "status": "COMPLETED",
  "watchdog_interval_sec": 600,
  "maximum_runtime_sec": 21600,
  "target_duration_sec": 480,
  "provider_mode": "offline_mock",
  "production_mode": "customer_canonical_queue",
  "owns_production": false,
  "paid_api_calls": 0,
  "external_provider_calls": 0,
  "baseline": {
    "os": "Windows-11-10.0.26200-SP0",
    "python": "3.12.9",
    "release_version": "0.5.0",
    "release_identity": {
      "app_name": "AutoMovie Pro",
      "release_version": "0.5.0",
      "build_id": "h5-source",
      "build_timestamp": "2026-09-06T15:45:17Z",
      "python_version": "3.12.9",
      "platform": "Windows-11-10.0.26200-SP0",
      "os_name": "nt",
      "supported_deployment": "windows_local_source_venv",
      "checkpoint": "AMP004-H5-RELEASE-OPERATIONAL-READINESS",
      "ffmpeg_available": true,
      "ffprobe_available": true,
      "ffmpeg_source": "bundled",
      "ffprobe_source": "bundled",
      "ffmpeg_version": "ffmpeg version 8.1.1-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers",
      "ffprobe_version": "ffprobe version 8.1.1-full_build-www.gyan.dev Copyright (c) 2007-2026 the FFmpeg developers"
    },
    "media_capability": {
      "FFMPEG_AVAILABLE": true,
      "FFPROBE_AVAILABLE": true,
      "ffmpeg_path": "E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\ffmpeg-8.1.1-full_build\\ffmpeg-8.1.1-full_build\\bin\\ffmpeg.exe",
      "ffprobe_path": "E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\ffmpeg-8.1.1-full_build\\ffmpeg-8.1.1-full_build\\bin\\ffprobe.exe",
      "ffmpeg_source": "bundled",
      "ffprobe_source": "bundled",
      "method": "DETERMINISTIC"
    },
    "media_versions": {
      "ffmpeg_version": "ffmpeg version 8.1.1-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers",
      "ffprobe_version": "ffprobe version 8.1.1-full_build-www.gyan.dev Copyright (c) 2007-2026 the FFmpeg developers"
    },
    "environment": "c11_real_marathon",
    "data_dir": "E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\data",
    "disk_free_gb": 107.03,
    "utc_now": "2026-09-06T15:45:18Z",
    "timezone": "UTC",
    "locale": "en",
    "provider_inventory": {
      "google_keys": 19,
      "agnes_keys": 6,
      "details_presence": [
        {
          "name": "[redacted]",
          "status": "SET",
          "length": 39
        },
        {
          "name": "[redacted]",
          "status": "SET",
          "length": 51
        },
        {
          "name": "AGNES_API_BASE_URL",
          "status": "SET",
          "length": 30
        },
        {
          "name": "[redacted]",
          "status": "SET",
          "length": 39
        },
        {
          "name": "YOUTUBE_CLIENT_ID",
          "status": "SET",
          "length": 72
        },
        {
          "name": "YOUTUBE_CLIENT_SECRET",
          "status": "SET",
          "length": 35
        },
        {
          "name": "[redacted]",
          "status": "EMPTY",
          "length": 0
        },
        {
          "name": "[redacted]",
          "status": "EMPTY",
          "length": 0
        },
        {
          "name": "[redacted]",
          "status": "EMPTY",
          "length": 0
        }
      ]
    },
    "customer_identity": "c11_marathon_customer",
    "entitlement_state": "ACTIVE_ASSUMED_FOR_DEDICATED_TEST_LOGIN",
    "secrets_persisted": "[redacted]"
  },
  "cases": {
    "C11-LONG": "PENDING",
    "C11-SHORT": "PENDING"
  },
  "c11": true,
  "job_id": 2265,
  "work_dir": "E:\\All Updaye Project\\AutoMovie_Pro_SAAS_Final_Update\\AutoMoviePro-Software\\data\\customer_generation_work\\c11_marathon_customer\\job2265"
}
```

## 3. Environment
- environment: `c11_real_marathon`
- application_version: `0.5.0`
- source_release_revision: `h5-source`

## 4. Niche
- `space science`

## 5. Long/Short Type
- `LONG` / test_case `MARATHON_LONG`

## 6. Start/End
- start: `2026-09-06T15:45:18Z`
- end: `2026-09-06T15:52:59Z`

## 7. Total Runtime
- note: `computed_from_identity`
- per-stage ms: `{'SESSION': 0.0, 'C11': 0.0, 'APPROVAL': 0.0, 'GENERATION': 422546.99999999866, 'STATE': 0.0, 'LIFECYCLE': 0.0}`

## 8. Final State
- `COMPLETED`

## 9. Full Timeline
- events: 21
| timestamp | event_type | status | stage |
| --- | --- | --- | --- |
| 2026-09-06T15:45:18Z | SESSION_CREATED | OK | SESSION |
| 2026-09-06T15:45:18Z | C11_SESSION_READY | OK | C11 |
| 2026-09-06T15:45:42Z | SCRIPT_APPROVED | OK | APPROVAL |
| 2026-09-06T15:45:42Z | SUBMIT | OK | GENERATION |
| 2026-09-06T15:45:42Z | STATE_TRANSITION | CLAIMED | STATE |
| 2026-09-06T15:45:42Z | CLAIMED | OK | LIFECYCLE |
| 2026-09-06T15:45:42Z | EXECUTION_START | OK | LIFECYCLE |
| 2026-09-06T15:48:28Z | EXECUTION_FAILED | OK | LIFECYCLE |
| 2026-09-06T15:48:28Z | TERMINAL_FAILED | OK | LIFECYCLE |
| 2026-09-06T15:48:28Z | GENERATION_RESULT | FAIL | GENERATION |
| 2026-09-06T15:48:28Z | PUBLISH_VALIDATION_FAILED | OK | LIFECYCLE |
| 2026-09-06T15:48:43Z | SCRIPT_APPROVED | OK | APPROVAL |
| 2026-09-06T15:48:43Z | SUBMIT | OK | GENERATION |
| 2026-09-06T15:48:43Z | STATE_TRANSITION | CLAIMED | STATE |
| 2026-09-06T15:48:43Z | CLAIMED | OK | LIFECYCLE |
| 2026-09-06T15:48:43Z | EXECUTION_START | OK | LIFECYCLE |
| 2026-09-06T15:52:59Z | EXECUTION_FAILED | OK | LIFECYCLE |
| 2026-09-06T15:52:59Z | TERMINAL_FAILED | OK | LIFECYCLE |
| 2026-09-06T15:52:59Z | GENERATION_RESULT | FAIL | GENERATION |
| 2026-09-06T15:52:59Z | PUBLISH_VALIDATION_FAILED | OK | LIFECYCLE |
| 2026-09-06T15:52:59Z | SESSION_FINISHED | COMPLETED | SESSION |

## 10. API Call Ledger
- count: 7
| timestamp | provider | operation | latency_ms | status | retry |
| --- | --- | --- | --- | --- | --- |
| 2026-09-06T15:45:18Z | build04g_intelligence | run_topic_intelligence | 375.0 | OK | 0 |
| 2026-09-06T15:45:19Z | research_runtime | run_research | 63.00000000192085 | OK | 0 |
| 2026-09-06T15:45:42Z | script_runtime | generate_script | 22969.0000000046 | OK | 0 |
| 2026-09-06T15:48:28Z | customer_generation | execute_claimed_job | 166468.99999999732 | FAIL | 0 |
| 2026-09-06T15:48:29Z | research_runtime | run_research | 46.999999998661224 | OK | 0 |
| 2026-09-06T15:48:42Z | script_runtime | generate_script | 13813.00000000192 | OK | 0 |
| 2026-09-06T15:52:59Z | customer_generation | execute_claimed_job | 256078.00000000134 | FAIL | 0 |

## 11. Prompt Ledger
- count: 0

## 12. Script/Beat Analysis
- scripts: 7; beats: 4

## 13. Visual Asset Ledger
- count: 0

## 14. Audio Ledger
- count: 0

## 15. Subtitle/Localization Ledger
- count: 0

## 16. Quality/Verification
- count: 0

## 17. Repair Ledger
- count: 0

## 18. Render/FFmpeg
- count: 0

## 19. Publishing
- count: 2

## 20. Scheduling
- count: 0

## 21. Watchdog Checks
- count: 12

## 22. Failures
- count: 3

## 23. Retries
- retry_count: 0

## 24. Recovery
- recovery_count: 0

## 25. Bottlenecks
- slowest operations sampled: 7

## 26. Slowest Operations
| provider | operation | latency_ms |
| --- | --- | --- |
| customer_generation | execute_claimed_job | 256078.00000000134 |
| customer_generation | execute_claimed_job | 166468.99999999732 |
| script_runtime | generate_script | 22969.0000000046 |
| script_runtime | generate_script | 13813.00000000192 |
| build04g_intelligence | run_topic_intelligence | 375.0 |
| research_runtime | run_research | 63.00000000192085 |
| research_runtime | run_research | 46.999999998661224 |

## 27. Duplicate/Unexpected Calls
- duplicate findings: 0

## 28. UNKNOWN States
- unknown_count: 0

## 29. Provider Usage
- api_call_count: 7

## 30. Cost Evidence
- monetary cost: NOT_DETERMINABLE (harness does not invent cost)
- paid_call_count: 7

## 31. Artifact Statistics
- images: 0; video clips: 0; audio: 0; subtitles: 0

## 32. Duration Statistics
- p50_ms: 13813.00000000192; p95_ms: 256078.00000000134

## 33. Recommendations
- Use WAITING classification for legitimate provider/scheduler pending states.
- Do not promote UNKNOWN to success.
- Apply only minimal safe fixes via intervention contract (record-only in C10).

## 34. Severity-ranked Findings
- **MEDIUM** `unusually_long_provider_latency` — {'operation': 'execute_claimed_job', 'latency_ms': 166468.99999999732}
- **MEDIUM** `unusually_long_provider_latency` — {'operation': 'execute_claimed_job', 'latency_ms': 256078.00000000134}
- **MEDIUM** `zero_progress_interval` — {'failure_count': 3}

## 35. Final Verdict
**PASS**

---
C10 observation harness — not a production authority.

---

# C11 Extensions

# C11 Certification

**Checkpoint:** `C11-REAL-MARATHON-FAIL`  
**Run ID:** `mr_a39b8889d65f4f78`  
**Session:** `ms_9ab8015ff538400b`  
**Niche:** `space science`  
**Topic:** `How James Webb Space Telescope images reveal early galaxies for space science`  
**Total runtime (sec):** 461.9

## Honesty labels

- TOPIC_INTELLIGENCE research attempted REAL (Google keys present)
- BUILD04G placeholder topic replaced with niche-grounded MANUAL topic
- C11-LONG: approval not available in state FAILED
- C11-LONG: publish used mock provider path (labeled MOCK) — no CAPTCHA/browser bypass
- C11-SHORT: approval not available in state FAILED
- C11-SHORT: publish used mock provider path (labeled MOCK) — no CAPTCHA/browser bypass

## LONG

- status: `FAILED`
- classification: `REAL`
- path: ``
- exists: `False`
- duration: `None`
- resolution: `NonexNone`
- fps: `None`
- codec: `None`
- audio: `None`
- approval: `APPROVAL_BLOCKED`
- publish: `FAIL`

## SHORT

- status: `FAILED`
- classification: `REAL`
- path: ``
- exists: `False`
- duration: `None`
- resolution: `NonexNone`
- fps: `None`
- codec: `None`
- audio: `None`
- approval: `APPROVAL_BLOCKED`
- publish: `FAIL`

## Metrics

```json
{
  "provider_calls": 7,
  "paid_provider_calls": 7,
  "api_calls": 7,
  "failures": 2,
  "retries": 0,
  "repairs": 0,
  "unknown": 2
}
```

## Incidents: 2
## Interventions: 0
## Code changes: NO
## Architectural blocker: NO

## Authority audit

C11 did not create second job/queue/scheduler/retry/idempotency/quality/repair/render/publish/event engines.  
C10 remains observation-only.

## NEXT ACTION

STOP AND REVIEW REPORT
