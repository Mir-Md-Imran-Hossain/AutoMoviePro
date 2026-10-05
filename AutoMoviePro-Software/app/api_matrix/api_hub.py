"""AutoMovie Pro — API Setup, Central Hub & Failover Matrix Engine.

Strictly manages and executes:
1. Grok API: Primary and Fallback keys for Agent, Topic Research, and Scriptwriting.
2. Google AI Studio API:
    - Language-specific TTS & Localization keys (dedicated keys per unlocked language).
    - Separate dedicated Google Pro API key for Image & Veo Video generation.
    - Fallback Agent capability when Grok is unavailable or rate-limited.
3. OpenRouter API: Third-layer fallback backup.
4. Agnes API: Dedicated AI video and image synthesis.
5. Pexels API: Stock image and video fallback when Agnes/Google fails.
6. Pollinations API: Fallback image generation and dynamic YouTube/FB thumbnail creator.
7. Automated Failover Resolution, Rate-limit Quota Guard & Zero-Crash Key Rotation.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ApiMatrixConfig:
    # Grok
    grok_primary_key: str = ""
    grok_fallback_key: str = ""
    # Google
    google_media_key: str = ""  # Google Pro (Veo Video & Pro Image)
    google_tts_keys: Dict[str, List[str]] = field(default_factory=lambda: {
        "en": [], "bn": [], "hi": [], "ur": [], "ta": [], "ml": []
    })
    # Special Google AI Pro package key (Nano Banana, VEO-3, Roboticless TTS)
    google_pro_key: str = ""
    google_pro_keys_by_lang: Dict[str, str] = field(default_factory=lambda: {
        "en": "", "bn": "", "hi": "", "ur": "", "ta": "", "ml": ""
    })
    # Fallbacks & Visuals
    openrouter_key: str = ""
    agnes_key: str = ""
    pexels_key: str = ""
    pollinations_key: str = ""


@dataclass
class KeyQuotaStatus:
    provider: str
    key_masked: str
    is_exhausted: bool = False
    exhausted_at: float = 0.0
    cooldown_until: float = 0.0
    fail_count: int = 0
    last_error: str = ""


class KeyQuotaGuard:
    """Tracks rate limits, quota exhaustion (429/403/ResourceExhausted),
    and cooldown periods across all API keys without crashing customer runs.
    """

    def __init__(self, default_cooldown_seconds: int = 300):
        self.default_cooldown_seconds = default_cooldown_seconds
        self._key_records: Dict[str, KeyQuotaStatus] = {}

    @staticmethod
    def mask_key(k: str) -> str:
        if not k:
            return ""
        if len(k) <= 8:
            return "***"
        return f"{k[:4]}...{k[-4:]}"

    def _key_id(self, provider: str, key: str) -> str:
        k_clean = str(key or "").strip()
        prefix = k_clean[:6] if len(k_clean) >= 6 else k_clean
        suffix = k_clean[-4:] if len(k_clean) >= 4 else ""
        return f"{provider}:{prefix}:{suffix}"

    def is_available(self, provider: str, key: str) -> bool:
        if str(provider).startswith("google_pro"):
            # Google AI Pro bypasses regular free rate limits and quota limitations
            return True
        kid = self._key_id(provider, key)
        rec = self._key_records.get(kid)
        if not rec:
            return True
        if not rec.is_exhausted:
            return True
        if time.time() >= rec.cooldown_until:
            rec.is_exhausted = False
            return True
        return False

    def mark_exhausted(
        self,
        provider: str,
        key: str,
        error_msg: str,
        cooldown_seconds: Optional[int] = None,
    ) -> None:
        cooldown = cooldown_seconds if cooldown_seconds is not None else self.default_cooldown_seconds
        kid = self._key_id(provider, key)
        rec = self._key_records.setdefault(
            kid,
            KeyQuotaStatus(provider=provider, key_masked=self.mask_key(key)),
        )
        rec.is_exhausted = True
        rec.exhausted_at = time.time()
        rec.cooldown_until = time.time() + cooldown
        rec.fail_count += 1
        rec.last_error = str(error_msg)[:300]
        logger.warning(
            "[API Quota Guard] Key '%s' (%s) exhausted/rate-limited for %ds. Reason: %s",
            rec.key_masked, provider, cooldown, rec.last_error
        )

    def mark_success(self, provider: str, key: str) -> None:
        kid = self._key_id(provider, key)
        if kid in self._key_records:
            rec = self._key_records[kid]
            rec.is_exhausted = False
            rec.fail_count = 0
            rec.last_error = ""

    def reset_all(self) -> None:
        self._key_records.clear()

    def get_status_report(self) -> Dict[str, Any]:
        now = time.time()
        report = {}
        for kid, rec in self._key_records.items():
            report[kid] = {
                "provider": rec.provider,
                "key_masked": rec.key_masked,
                "is_exhausted": rec.is_exhausted and now < rec.cooldown_until,
                "cooldown_remaining_sec": max(0, int(rec.cooldown_until - now)) if rec.is_exhausted else 0,
                "fail_count": rec.fail_count,
                "last_error": rec.last_error,
            }
        return report


class ApiHub:
    """Central authority for API credentials, health testing, failover chains,
    and 100% error-handled execution with automated key rotation.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent / "data" / "api_matrix"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / "api_matrix.json"
        self.config: ApiMatrixConfig = self._load()
        self.quota_guard = KeyQuotaGuard(default_cooldown_seconds=300)

    def _load(self) -> ApiMatrixConfig:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return ApiMatrixConfig(
                        grok_primary_key=data.get("grok_primary_key", ""),
                        grok_fallback_key=data.get("grok_fallback_key", ""),
                        google_media_key=data.get("google_media_key", ""),
                        google_tts_keys=data.get("google_tts_keys", {
                            "en": [], "bn": [], "hi": [], "ur": [], "ta": [], "ml": []
                        }),
                        google_pro_key=data.get("google_pro_key", ""),
                        google_pro_keys_by_lang=data.get("google_pro_keys_by_lang", {
                            "en": "", "bn": "", "hi": "", "ur": "", "ta": "", "ml": ""
                        }),
                        openrouter_key=data.get("openrouter_key", ""),
                        agnes_key=data.get("agnes_key", ""),
                        pexels_key=data.get("pexels_key", ""),
                        pollinations_key=data.get("pollinations_key", ""),
                    )
            except Exception as exc:
                logger.error("Failed to load api matrix config: %s", exc)
        return ApiMatrixConfig()

    def save(self) -> None:
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(asdict(self.config), f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error("Failed to save api matrix config: %s", exc)

    def update_keys(
        self,
        *,
        grok_primary_key: Optional[str] = None,
        grok_fallback_key: Optional[str] = None,
        google_media_key: Optional[str] = None,
        google_tts_keys: Optional[Dict[str, List[str]]] = None,
        google_pro_key: Optional[str] = None,
        google_pro_keys_by_lang: Optional[Dict[str, str]] = None,
        openrouter_key: Optional[str] = None,
        agnes_key: Optional[str] = None,
        pexels_key: Optional[str] = None,
        pollinations_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates and persists API credentials."""
        if grok_primary_key is not None:
            self.config.grok_primary_key = grok_primary_key.strip()
        if grok_fallback_key is not None:
            self.config.grok_fallback_key = grok_fallback_key.strip()
        if google_media_key is not None:
            self.config.google_media_key = google_media_key.strip()
        if google_tts_keys is not None:
            for lang, keys in google_tts_keys.items():
                clean_keys = [k.strip() for k in keys if k and k.strip()]
                self.config.google_tts_keys[lang] = clean_keys
        if google_pro_key is not None:
            self.config.google_pro_key = google_pro_key.strip()
        if google_pro_keys_by_lang is not None:
            for lang, k in google_pro_keys_by_lang.items():
                self.config.google_pro_keys_by_lang[lang] = str(k or "").strip()
        if openrouter_key is not None:
            self.config.openrouter_key = openrouter_key.strip()
        if agnes_key is not None:
            self.config.agnes_key = agnes_key.strip()
        if pexels_key is not None:
            self.config.pexels_key = pexels_key.strip()
        if pollinations_key is not None:
            self.config.pollinations_key = pollinations_key.strip()

        self.save()
        return self.get_summary()

    def get_google_pro_key(self, lang_code: Optional[str] = None) -> str:
        """Retrieves Google Pro key for language or globally, with seamless fallback to SetupManager."""
        if lang_code:
            l = lang_code.lower().strip()
            k = str(self.config.google_pro_keys_by_lang.get(l) or "").strip()
            if k:
                return k
        if self.config.google_pro_key:
            return self.config.google_pro_key.strip()
        try:
            from app.setup.channel_setup import SetupManager
            mgr = SetupManager()
            if lang_code:
                k = mgr.get_google_pro_key(lang_code)
                if k:
                    return k
            for l in mgr.get_profile().get("unlocked_languages", []):
                k = mgr.get_google_pro_key(l)
                if k:
                    return k
        except Exception:
            pass
        return ""

    def set_google_pro_key(self, lang_code: Optional[str], key: str) -> None:
        """Sets Google Pro API Key for a language or globally and persists config."""
        clean_key = str(key or "").strip()
        if lang_code:
            l = lang_code.lower().strip()
            self.config.google_pro_keys_by_lang[l] = clean_key
        else:
            self.config.google_pro_key = clean_key
        self.save()

    def get_summary(self) -> Dict[str, Any]:
        """Returns safe status indicating whether keys are present without leaking them."""
        def _mask(k: str) -> str:
            return KeyQuotaGuard.mask_key(k)

        tts_status = {}
        for lang, keys in self.config.google_tts_keys.items():
            tts_status[lang] = {
                "count": len(keys),
                "configured": len(keys) > 0,
                "masked": [_mask(k) for k in keys],
            }

        return {
            "grok": {
                "primary_configured": bool(self.config.grok_primary_key),
                "primary_masked": _mask(self.config.grok_primary_key),
                "fallback_configured": bool(self.config.grok_fallback_key),
                "fallback_masked": _mask(self.config.grok_fallback_key),
            },
            "google": {
                "media_key_configured": bool(self.config.google_media_key),
                "media_key_masked": _mask(self.config.google_media_key),
                "tts_by_language": tts_status,
            },
            "google_pro": {
                "global_configured": bool(self.config.google_pro_key),
                "global_masked": _mask(self.config.google_pro_key),
                "keys_by_lang": {
                    l: bool(k) for l, k in self.config.google_pro_keys_by_lang.items()
                },
            },
            "openrouter": {
                "configured": bool(self.config.openrouter_key),
                "masked": _mask(self.config.openrouter_key),
            },
            "agnes": {
                "configured": bool(self.config.agnes_key),
                "masked": _mask(self.config.agnes_key),
            },
            "pexels": {
                "configured": bool(self.config.pexels_key),
                "masked": _mask(self.config.pexels_key),
            },
            "pollinations": {
                "configured": bool(self.config.pollinations_key),
                "masked": _mask(self.config.pollinations_key),
            },
            "quota_status": self.quota_guard.get_status_report(),
        }

    # --- Failover Resolver Chains with Google Pro Priority ---
    def resolve_agent_llm_chain(self, lang_code: Optional[str] = None) -> List[Tuple[str, str]]:
        """Returns ordered fallback list of (provider, api_key) for Agent & Script generation.
        0. Google AI Pro (Top Priority if configured)
        1. Grok Primary Key
        2. Grok Fallback Key
        3. Google AI Studio (Media/Pro key or language TTS key fallback)
        4. OpenRouter Backup Key
        """
        chain = []
        pro_key = self.get_google_pro_key(lang_code)
        if pro_key:
            chain.append(("google_pro", pro_key))

        if self.config.grok_primary_key:
            chain.append(("grok_primary", self.config.grok_primary_key))
        if self.config.grok_fallback_key:
            chain.append(("grok_fallback", self.config.grok_fallback_key))
        # Google AI Studio as fallback agent
        if self.config.google_media_key:
            chain.append(("google_agent_fallback", self.config.google_media_key))
        elif any(self.config.google_tts_keys.values()):
            for keys in self.config.google_tts_keys.values():
                if keys:
                    chain.append(("google_agent_fallback", keys[0]))
                    break
        # OpenRouter as final LLM fallback
        if self.config.openrouter_key:
            chain.append(("openrouter_fallback", self.config.openrouter_key))
        return chain

    def resolve_video_generation_chain(self, lang_code: Optional[str] = None) -> List[Tuple[str, str]]:
        """Returns ordered fallback list of (provider, api_key) for video generation.
        0. Google AI Pro (Veo-3 Special API - Top Priority)
        1. Google Pro Media Key (Veo 2 / Media Key)
        2. Agnes Video Key
        3. Pexels Stock Video Fallback Key
        """
        chain = []
        pro_key = self.get_google_pro_key(lang_code)
        if pro_key:
            chain.append(("google_pro_veo3", pro_key))

        if self.config.google_media_key:
            chain.append(("google_veo", self.config.google_media_key))
        if self.config.agnes_key:
            chain.append(("agnes_video", self.config.agnes_key))
        if self.config.pexels_key:
            chain.append(("pexels_stock_video", self.config.pexels_key))
        return chain

    def resolve_image_generation_chain(self, lang_code: Optional[str] = None) -> List[Tuple[str, str]]:
        """Returns ordered fallback list of (provider, api_key) for visual images.
        0. Google AI Pro (Nano Banana Pro Image - Top Priority)
        1. Google Pro Media Key (Imagen 3 / Pro Image)
        2. Agnes Image Key
        3. Pollinations Image Key (or free tier)
        4. Pexels Stock Image Fallback Key
        """
        chain = []
        pro_key = self.get_google_pro_key(lang_code)
        if pro_key:
            chain.append(("google_pro_nano_banana", pro_key))

        if self.config.google_media_key:
            chain.append(("google_image", self.config.google_media_key))
        if self.config.agnes_key:
            chain.append(("agnes_image", self.config.agnes_key))
        if self.config.pollinations_key:
            chain.append(("pollinations_image", self.config.pollinations_key))
        else:
            chain.append(("pollinations_free", ""))
        if self.config.pexels_key:
            chain.append(("pexels_stock_image", self.config.pexels_key))
        return chain

    def resolve_tts_keys_for_language(self, lang_code: str) -> List[str]:
        """Returns keys configured for this specific language, falling back to general Google key."""
        lang = lang_code.lower().strip()
        keys = list(self.config.google_tts_keys.get(lang) or [])
        pro_k = self.get_google_pro_key(lang)
        if pro_k and pro_k not in keys:
            keys.insert(0, pro_k)
        if not keys and self.config.google_media_key:
            keys.append(self.config.google_media_key)
        return keys

    def resolve_tts_chain_for_language(self, lang_code: str) -> List[Tuple[str, str]]:
        """Returns comprehensive fallback chain of (provider, key) for TTS in a specific language:
        0. Google AI Pro TTS (Ultra-Natural Roboticless Voice - Top Priority)
        1. Dedicated Google AI Studio keys configured for that language
        2. Google Pro Media Key (shared fallback)
        3. Other available Google Studio keys from remaining languages
        """
        lang = lang_code.lower().strip()
        chain: List[Tuple[str, str]] = []

        # 0. Google Pro TTS Priority
        pro_key = self.get_google_pro_key(lang)
        if pro_key:
            chain.append(("google_pro_tts", pro_key))

        # 1. Dedicated keys for this language
        dedicated = self.config.google_tts_keys.get(lang) or []
        for idx, k in enumerate(dedicated, 1):
            if k and k != pro_key:
                chain.append((f"google_tts_{lang}_{idx}", k))

        # 2. Shared Google Media Key fallback
        if self.config.google_media_key and self.config.google_media_key != pro_key:
            if not any(k == self.config.google_media_key for _, k in chain):
                chain.append(("google_tts_media_fallback", self.config.google_media_key))

        # 3. Cross-language Google AI Studio fallback keys
        for other_lang, other_keys in self.config.google_tts_keys.items():
            if other_lang != lang:
                for idx, ok in enumerate(other_keys, 1):
                    if ok and not any(k == ok for _, k in chain):
                        chain.append((f"google_tts_{other_lang}_backup_{idx}", ok))

        return chain

    def validate_readiness_for_languages(self, unlocked_languages: List[str]) -> Dict[str, Any]:
        """Verifies if all required keys are present for active languages."""
        errors = []
        warnings = []

        if not self.config.grok_primary_key:
            errors.append("Grok Primary API key is missing (Required for Agent & Topic Research).")
        elif not self.config.grok_fallback_key:
            warnings.append("Grok Fallback API key is recommended to prevent rate limits.")

        for lang in unlocked_languages:
            keys = self.resolve_tts_keys_for_language(lang)
            if not keys:
                errors.append(f"Missing Google AI Studio key for language '{lang}' (Required for TTS & Localization).")

        if not self.config.google_media_key and not self.config.agnes_key and not self.config.pexels_key:
            errors.append("No video provider configured (Please provide Google Pro, Agnes, or Pexels API key).")

        return {
            "ready": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    # =========================================================================
    # --- 100% Robust Failover Execution Engine with Automated Key Rotation ---
    # =========================================================================

    def execute_with_failover(
        self,
        chain_name: str,
        chain: List[Tuple[str, str]],
        action_fn: Callable[[str, str], Any],
        cooldown_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Executes action_fn(provider, api_key) across an ordered fallback chain.
        100% Error-handled:
        - Automatically detects rate limits / HTTP 429 / 403 / ResourceExhausted.
        - Puts exhausted keys on cooldown and logs warning without halting customer pipeline.
        - Automatically advances to the next provider/key in the chain.
        - Returns a structured status dict; NEVER raises unhandled exceptions.
        """
        if not chain:
            return {
                "ok": False,
                "provider": None,
                "key_masked": "",
                "error": "empty_chain",
                "message": f"No providers or keys configured for {chain_name}.",
                "failover_history": [],
            }

        # Filter candidates not currently on cooldown
        available_candidates = [
            (p, k) for p, k in chain if self.quota_guard.is_available(p, k)
        ]
        # If all candidates are on cooldown, reset cooldowns to allow an immediate fresh retry
        if not available_candidates:
            logger.warning(
                "[API Failover] All candidates in '%s' are on cooldown. Resetting cooldowns for immediate retry.",
                chain_name,
            )
            for p, k in chain:
                self.quota_guard.mark_success(p, k)
            available_candidates = list(chain)

        history: List[Dict[str, Any]] = []

        for provider, key in available_candidates:
            masked = KeyQuotaGuard.mask_key(key)
            try:
                logger.info("[API Matrix] Attempting %s via %s (key: %s)...", chain_name, provider, masked)
                res = action_fn(provider, key)
                # Successful execution!
                self.quota_guard.mark_success(provider, key)
                return {
                    "ok": True,
                    "provider": provider,
                    "key_masked": masked,
                    "data": res,
                    "failover_history": history,
                }
            except Exception as exc:
                err_text = str(exc)
                logger.warning(
                    "[API Matrix Failover] %s provider '%s' (key: %s) failed: %s. Auto-failing over to next in chain...",
                    chain_name, provider, masked, err_text
                )
                self.quota_guard.mark_exhausted(
                    provider, key, err_text, cooldown_seconds=cooldown_seconds
                )
                history.append({
                    "provider": provider,
                    "key_masked": masked,
                    "status": "failed",
                    "error": err_text,
                })
                # Proceed to next provider/key in chain

        logger.error(
            "[API Matrix Failover] All %d providers in chain '%s' exhausted or failed.",
            len(available_candidates), chain_name
        )
        return {
            "ok": False,
            "provider": None,
            "key_masked": "",
            "error": "all_providers_exhausted",
            "message": f"All {len(available_candidates)} providers in {chain_name} chain failed or exhausted quota.",
            "failover_history": history,
        }

    # --- High-Level Chain Executors ---

    def execute_agent_llm(
        self,
        prompt: str,
        system_prompt: str = "You are AutoMovie Pro content engine.",
        model: Optional[str] = None,
        lang_code: Optional[str] = None,
        caller_override: Optional[Callable[[str, str], Any]] = None,
    ) -> Dict[str, Any]:
        """Executes Agent LLM / Script Generation across:
        Google AI Pro -> Grok Primary -> Grok Fallback -> Google AI Studio -> OpenRouter
        """
        chain = self.resolve_agent_llm_chain(lang_code)

        def _default_caller(provider: str, key: str) -> Any:
            if caller_override:
                return caller_override(provider, key)

            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            if provider == "google_pro":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or 'gemini-2.0-pro-exp'}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": f"SYSTEM DIRECTIVE (High CTR, Viral SEO Hook):\n{system_prompt}\n\nUSER PROMPT:\n{prompt}"}]}]
                }
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]

            elif provider in ("grok_primary", "grok_fallback"):
                url = "https://api.x.ai/v1/chat/completions"
                payload = {"model": model or "grok-2", "messages": messages, "temperature": 0.7}
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]

            elif provider == "google_agent_fallback":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or 'gemini-2.0-flash'}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}]
                }
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]

            elif provider == "openrouter_fallback":
                url = "https://openrouter.ai/api/v1/chat/completions"
                payload = {"model": model or "google/gemini-2.0-flash-exp:free", "messages": messages}
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]

            raise ValueError(f"Unknown LLM provider: {provider}")

        return self.execute_with_failover("Agent_LLM_Chain", chain, _default_caller)

    def execute_tts(
        self,
        lang_code: str,
        text: str,
        voice_name: Optional[str] = None,
        caller_override: Optional[Callable[[str, str], Any]] = None,
    ) -> Dict[str, Any]:
        """Executes Text-to-Speech using dedicated language keys with automated rotation
        and fallback to Google Media Pro and cross-language keys when quota is exhausted.
        """
        chain = self.resolve_tts_chain_for_language(lang_code)

        def _default_caller(provider: str, key: str) -> Any:
            if caller_override:
                return caller_override(provider, key)

            if provider == "google_pro_tts":
                url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
                payload = {
                    "input": {"text": text},
                    "voice": {
                        "languageCode": lang_code,
                        "name": voice_name or f"{lang_code}-Neural2-A",
                    },
                    "audioConfig": {"audioEncoding": "MP3", "speakingRate": 1.0, "pitch": 0.0},
                }
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    return resp.json()

            # Standard Google TTS / AI Studio voice API request
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
            payload = {
                "input": {"text": text},
                "voice": {
                    "languageCode": lang_code,
                    "name": voice_name or f"{lang_code}-Standard-A",
                },
                "audioConfig": {"audioEncoding": "MP3"},
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()

        return self.execute_with_failover(f"TTS_Chain_{lang_code}", chain, _default_caller)

    def execute_video(
        self,
        prompt: str,
        duration_sec: float = 4.0,
        lang_code: Optional[str] = None,
        caller_override: Optional[Callable[[str, str], Any]] = None,
    ) -> Dict[str, Any]:
        """Executes Video Generation across:
        Google AI Pro (Veo-3) -> Google Veo 2 -> Agnes Video -> Pexels Stock Video
        """
        chain = self.resolve_video_generation_chain(lang_code)

        def _default_caller(provider: str, key: str) -> Any:
            if caller_override:
                return caller_override(provider, key)

            if provider == "google_pro_veo3":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/veo-3.0-generate-video:predictLongRunning?key={key}"
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, json={"prompt": prompt, "duration_sec": duration_sec, "resolution": "1080p"})
                    resp.raise_for_status()
                    return resp.json()

            elif provider == "google_veo":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/veo-2.0-generate-video:predictLongRunning?key={key}"
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, json={"prompt": prompt, "duration_sec": duration_sec})
                    resp.raise_for_status()
                    return resp.json()

            elif provider == "agnes_video":
                url = "https://api.agnes.ai/v1/video/generate"
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, headers={"Authorization": f"Bearer {key}"}, json={"prompt": prompt})
                    resp.raise_for_status()
                    return resp.json()

            elif provider == "pexels_stock_video":
                encoded_q = urllib.parse.quote(prompt)
                url = f"https://api.pexels.com/videos/search?query={encoded_q}&per_page=5"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, headers={"Authorization": key})
                    resp.raise_for_status()
                    return resp.json()

            raise ValueError(f"Unknown video provider: {provider}")

        return self.execute_with_failover("Video_Generation_Chain", chain, _default_caller)

    def execute_image(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        lang_code: Optional[str] = None,
        caller_override: Optional[Callable[[str, str], Any]] = None,
    ) -> Dict[str, Any]:
        """Executes Visual Image / Thumbnail Generation across:
        Google AI Pro (Nano Banana Pro) -> Google Image -> Agnes Image -> Pollinations Image -> Pexels
        """
        chain = self.resolve_image_generation_chain(lang_code)

        def _default_caller(provider: str, key: str) -> Any:
            if caller_override:
                return caller_override(provider, key)

            if provider == "google_pro_nano_banana":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/nano-banana-pro-image:predict?key={key}"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, json={"prompt": prompt, "aspect_ratio": aspect_ratio, "quality": "ultra_hd"})
                    resp.raise_for_status()
                    return resp.json()

            elif provider == "google_image":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={key}"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, json={"prompt": prompt, "aspect_ratio": aspect_ratio})
                    resp.raise_for_status()
                    return resp.json()

            elif provider == "agnes_image":
                url = "https://api.agnes.ai/v1/image/generate"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, headers={"Authorization": f"Bearer {key}"}, json={"prompt": prompt})
                    resp.raise_for_status()
                    return resp.json()

            elif provider in ("pollinations_image", "pollinations_free"):
                encoded_p = urllib.parse.quote(prompt)
                width = 1920 if aspect_ratio == "16:9" else 1080
                height = 1080 if aspect_ratio == "16:9" else 1920
                url = f"https://image.pollinations.ai/prompt/{encoded_p}?width={width}&height={height}&nologo=true"
                headers = {"Authorization": f"Bearer {key}"} if key else {}
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, headers=headers)
                    resp.raise_for_status()
                    return {"url": url, "status_code": resp.status_code}

            elif provider == "pexels_stock_image":
                encoded_q = urllib.parse.quote(prompt)
                url = f"https://api.pexels.com/v1/search?query={encoded_q}&per_page=5"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, headers={"Authorization": key})
                    resp.raise_for_status()
                    return resp.json()

            raise ValueError(f"Unknown image provider: {provider}")

        return self.execute_with_failover("Image_Generation_Chain", chain, _default_caller)


_api_hub_instance: Optional[ApiHub] = None


def get_api_hub() -> ApiHub:
    global _api_hub_instance
    if _api_hub_instance is None:
        _api_hub_instance = ApiHub()
    return _api_hub_instance

