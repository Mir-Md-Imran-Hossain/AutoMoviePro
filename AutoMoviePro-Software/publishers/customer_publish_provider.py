"""C07-PUB — Provider-neutral publishing adapters (official API boundary only).

No browser automation. No CAPTCHA. Mock is explicitly labeled.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Protocol


def _now() -> str:
    return datetime.now().isoformat()


@dataclass
class ProviderUploadAccepted:
    provider_video_id: str
    provider_url: Optional[str] = None
    observation_status: str = "UPLOAD_ACCEPTED"  # not PUBLISHED
    mock: bool = False
    raw_safe: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderObservation:
    provider_video_id: str
    status: str  # UPLOAD_ACCEPTED|PROCESSING|PROCESSING_SUCCEEDED|PROCESSING_FAILED|PUBLISHED|UNKNOWN
    provider_url: Optional[str] = None
    observed_at: str = field(default_factory=_now)
    mock: bool = False
    detail: str = ""


class PublishProvider(Protocol):
    name: str

    def validate_configuration(self, channel: Dict[str, Any]) -> Dict[str, Any]: ...

    def authorize(self, channel: Dict[str, Any]) -> Dict[str, Any]: ...

    def upload(self, package: Dict[str, Any], channel: Dict[str, Any]) -> ProviderUploadAccepted: ...

    def observe(self, provider_video_id: str, channel: Dict[str, Any]) -> ProviderObservation: ...

    def classify_error(self, exc: BaseException) -> str: ...


# In-memory mock store for deterministic tests (process-local)
_MOCK_LOCK = threading.Lock()
_MOCK_VIDEOS: Dict[str, Dict[str, Any]] = {}


class MockPublishProvider:
    """Deterministic offline provider — never pretends to be real YouTube."""

    name = "mock"

    def __init__(self, *, scenario: str = "happy_path"):
        self.scenario = str(scenario or "happy_path")

    def validate_configuration(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        if self.scenario == "config_failure":
            return {"ok": False, "error": "invalid_provider_config", "error_code": "CONFIG_FAILURE"}
        return {"ok": True, "provider": self.name, "mock": True}

    def authorize(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        if self.scenario == "auth_failure":
            return {"ok": False, "error": "oauth_required", "error_code": "AUTH_FAILURE", "mock": True}
        return {"ok": True, "authorized": True, "mock": True, "token_exposed": False}

    def upload(self, package: Dict[str, Any], channel: Dict[str, Any]) -> ProviderUploadAccepted:
        if self.scenario == "auth_failure":
            raise RuntimeError("AUTH_FAILURE:oauth_required")
        if self.scenario == "provider_rejected":
            raise RuntimeError("PROVIDER_REJECTED:policy")
        if self.scenario == "transient":
            raise RuntimeError("TRANSIENT_PROVIDER_FAILURE:429")
        if self.scenario == "network_ambiguous":
            # Simulates: request may have been accepted but client lost response
            raise RuntimeError("NETWORK_FAILURE:ambiguous_after_possible_accept")
        if self.scenario == "permanent":
            raise RuntimeError("PROVIDER_REJECTED:permanent")

        vid = "mock_" + uuid.uuid4().hex[:12]
        with _MOCK_LOCK:
            # Always start at UPLOAD_ACCEPTED — observe() advances; never collapse to PUBLISHED on upload
            _MOCK_VIDEOS[vid] = {
                "status": "UPLOAD_ACCEPTED",
                "url": f"https://example.invalid/watch?v={vid}",
                "package_fp": package.get("fingerprint"),
                "created_at": _now(),
                "scenario": self.scenario,
            }
        return ProviderUploadAccepted(
            provider_video_id=vid,
            provider_url=f"https://example.invalid/watch?v={vid}",
            observation_status="UPLOAD_ACCEPTED",
            mock=True,
            raw_safe={"scenario": self.scenario, "note": "MOCK — not real provider"},
        )

    def observe(self, provider_video_id: str, channel: Dict[str, Any]) -> ProviderObservation:
        with _MOCK_LOCK:
            rec = _MOCK_VIDEOS.get(provider_video_id)
        if not rec:
            if self.scenario == "processing_failed":
                return ProviderObservation(
                    provider_video_id=provider_video_id,
                    status="PROCESSING_FAILED",
                    mock=True,
                    detail="mock processing failed",
                )
            return ProviderObservation(
                provider_video_id=provider_video_id,
                status="UNKNOWN",
                mock=True,
                detail="unknown video id",
            )
        st = str(rec.get("status") or "UNKNOWN")
        scen = self.scenario or rec.get("scenario") or "happy_path"
        if scen == "processing":
            # One step per observe: UPLOAD_ACCEPTED → PROCESSING (stay until published_immediate)
            if st == "UPLOAD_ACCEPTED":
                st = "PROCESSING"
                rec["status"] = st
            # remain PROCESSING — do not auto-publish
        elif scen == "published_immediate":
            st = "PUBLISHED"
            rec["status"] = st
        elif scen == "processing_failed":
            st = "PROCESSING_FAILED"
            rec["status"] = st
        elif scen == "happy_path":
            # First observe → PROCESSING; second with published_immediate needed for PUBLISHED
            if st == "UPLOAD_ACCEPTED":
                st = "PROCESSING"
                rec["status"] = st
        return ProviderObservation(
            provider_video_id=provider_video_id,
            status=st,
            provider_url=rec.get("url"),
            mock=True,
            detail="MOCK observation",
        )

    def classify_error(self, exc: BaseException) -> str:
        msg = str(exc)
        for code in (
            "AUTH_FAILURE",
            "CONFIG_FAILURE",
            "VALIDATION_FAILURE",
            "OWNERSHIP_FAILURE",
            "ARTIFACT_FAILURE",
            "PROVIDER_REJECTED",
            "RATE_LIMITED",
            "TRANSIENT_PROVIDER_FAILURE",
            "NETWORK_FAILURE",
            "REMOTE_PROCESSING_FAILURE",
            "UNKNOWN_PROVIDER_FAILURE",
        ):
            if code in msg:
                return code
        low = msg.lower()
        if "oauth" in low or "token" in low or "auth" in low:
            return "AUTH_FAILURE"
        if "429" in low or "rate" in low:
            return "RATE_LIMITED"
        if "network" in low or "ambiguous" in low:
            return "NETWORK_FAILURE"
        if "reject" in low or "policy" in low:
            return "PROVIDER_REJECTED"
        return "UNKNOWN_PROVIDER_FAILURE"


class YouTubeDataApiProvider:
    """Official YouTube Data API boundary only — no browser/CAPTCHA.

    Live calls are NEVER made unless explicitly enabled AND token present.
    Default path for C07-PUB offline: use MockPublishProvider.
    """

    name = "youtube"

    def validate_configuration(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        token = (
            channel.get("youtube_access_token")
            or channel.get("youtube_oauth_token")
            or channel.get("youtube_api_token")
            or ""
        ).strip()
        # Never return the token
        if not token:
            # Session cookie alone is NOT sufficient for this customer API path
            sess = bool(str(channel.get("youtube_session") or "").strip())
            return {
                "ok": False,
                "error": "youtube_oauth_token_required",
                "error_code": "AUTH_FAILURE",
                "has_session_cookie": sess,
                "note": "Customer publish requires OAuth token; browser session is LEGACY_COMPAT only",
            }
        return {"ok": True, "provider": self.name, "oauth_configured": True, "token_exposed": False}

    def authorize(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        return self.validate_configuration(channel)

    def upload(self, package: Dict[str, Any], channel: Dict[str, Any]) -> ProviderUploadAccepted:
        # Explicit live gate — fail closed unless allow_live_provider
        if not package.get("allow_live_provider"):
            raise RuntimeError(
                "CONFIG_FAILURE:live_youtube_disabled — use mock provider or set allow_live_provider for isolated smoke"
            )
        from pathlib import Path
        from publishers.youtube_api_uploader import upload_youtube_api

        path = Path(str(package.get("artifact_path") or ""))
        if not path.is_file():
            raise RuntimeError("ARTIFACT_FAILURE:missing_media")
        job = {
            "title": package.get("title"),
            "description": package.get("description"),
            "tags": package.get("tags"),
            "thumbnail": package.get("thumbnail_path"),
            "lang_code": package.get("language"),
        }
        url = upload_youtube_api(path, job, channel)
        # Extract id from URL if possible
        vid = ""
        if "v=" in url:
            vid = url.split("v=", 1)[-1].split("&", 1)[0]
        return ProviderUploadAccepted(
            provider_video_id=vid or uuid.uuid4().hex[:11],
            provider_url=url,
            observation_status="UPLOAD_ACCEPTED",
            mock=False,
            raw_safe={"note": "upload accepted — not yet published"},
        )

    def observe(self, provider_video_id: str, channel: Dict[str, Any]) -> ProviderObservation:
        if not channel.get("_allow_live_observe"):
            return ProviderObservation(
                provider_video_id=provider_video_id,
                status="UNKNOWN",
                detail="live observe disabled in default product path",
                mock=False,
            )
        # Live observation would call videos().list(part=status,processingDetails)
        # Kept fail-closed unless explicitly enabled for isolated smoke.
        return ProviderObservation(
            provider_video_id=provider_video_id,
            status="UNKNOWN",
            detail="live observe not enabled",
            mock=False,
        )

    def classify_error(self, exc: BaseException) -> str:
        return MockPublishProvider().classify_error(exc)


def get_publish_provider(
    provider: str = "mock",
    *,
    scenario: str = "happy_path",
    allow_live: bool = False,
    require_live_in_production: bool = False,
) -> Any:
    name = str(provider or "mock").lower().strip()
    if name in ("youtube", "yt") and allow_live:
        return YouTubeDataApiProvider()

    # In production runtime, if live was required, refuse silent fallback to mock
    try:
        from app.config import is_production_runtime
        is_prod = is_production_runtime()
    except Exception:
        is_prod = False

    if name in ("youtube", "yt"):
        if is_prod and require_live_in_production and not allow_live:
            raise RuntimeError(
                "LIVE_PUBLISH_REQUIRED: Production YouTube publishing requested but live provider is not enabled. "
                "Silent fallback to mock uploader is strictly forbidden."
            )
        # YouTube named but live disabled → mock with youtube label for offline tests
        p = MockPublishProvider(scenario=scenario)
        p.name = "youtube_mock"
        return p

    return MockPublishProvider(scenario=scenario)


def resolve_publish_provider(
    provider: str,
    channel: Optional[Dict[str, Any]] = None,
    allow_live: Optional[bool] = None,
) -> Any:
    """Safe provider resolver that checks credentials and environment."""
    ch = channel or {}
    prov_name = str(provider or ch.get("platform") or "mock").lower().strip()

    # Determine live eligibility based on credentials
    has_credentials = False
    if prov_name in ("youtube", "yt"):
        has_credentials = bool(
            ch.get("oauth_token")
            or ch.get("refresh_token")
            or ch.get("client_secret_json")
        )

    if allow_live is None:
        try:
            from app.config import is_production_runtime
            allow_live = is_production_runtime() and has_credentials
        except Exception:
            allow_live = has_credentials

    return get_publish_provider(
        prov_name,
        allow_live=allow_live,
        require_live_in_production=has_credentials,
    )


def reset_mock_store() -> None:
    with _MOCK_LOCK:
        _MOCK_VIDEOS.clear()
