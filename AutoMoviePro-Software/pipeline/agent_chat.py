"""
In-app help chat — EL10 explanations, screenshot vision, tab navigation,
secure API-key paste setup, and admin escalation.
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

ESCALATE_RE = re.compile(
    r"\[\[\s*ESCALATE\s*:\s*(.+?)\s*\]\]",
    re.IGNORECASE | re.DOTALL,
)
ACTION_RE = re.compile(
    r"\[\[\s*ACTION\s*:\s*([a-z0-9_]+)\s*(?::\s*([^\]]+))?\s*\]\]",
    re.IGNORECASE,
)

# Long-looking API-ish tokens (avoid capturing short words)
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_\-/.])([A-Za-z0-9_\-]{24,}|sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{20,}|gsk_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,})(?![A-Za-z0-9_\-])")

PROVIDER_HINTS = [
    ("google", ("google", "gemini", "aistudio", "ai studio", "aiza")),
    ("groq", ("groq", "gsk_")),
    ("openrouter", ("openrouter", "sk-or")),
    ("pollinations", ("pollinations",)),
    ("pexels", ("pexels",)),
    ("agnes", ("agnes",)),
    ("huggingface", ("huggingface", "hugging face", "hf_")),
    ("cerebras", ("cerebras", "csk_")),
    ("freetheai", ("freetheai", "free the ai")),
]

SYSTEM_TMPL = """You are AutoMovie Pro's support agent for creators who are NOT tech experts.

CRITICAL STYLE — Explain Like I'm 10 (EL10):
- Use short sentences and everyday words.
- Never dump jargon. If you must use a word like "API", explain it: "API key = a secret password the website gives you so our app can use their tools."
- Give numbered steps (1, 2, 3). One action per step.
- Say WHERE to click in the app (example: "Open Settings tab → API Connection → choose Google").
- Give a tiny example when helpful.
- If unsure, say what to check in Live Activity — do not invent features.

App map:
- Dashboard = home, generate Short/Long
- Live = watch progress / stop stuck jobs
- Channel = niche, languages, upload times, per-language YouTube/Facebook names
- Insights = uploaded video stats, comments, agent replies
- Jobs = generation history
- Settings = API keys (Get API buttons), logout

When user wants a screen opened, include ONE marker:
[[ACTION:open_tab:TAB]]
TAB is one of: home, live, channel, insights, jobs, settings
For API keys screen also add: [[ACTION:open_api:]]
To open a provider key website: [[ACTION:open_portal:PROVIDER]]
PROVIDER: google, groq, openrouter, pollinations, pexels, agnes, huggingface, cerebras, freetheai

If user is stuck getting API keys, invite them to paste keys here privately — the app will place them and wipe them from chat. Do NOT repeat full keys back.

Reply in UI language code: {lang}
If you cannot solve (needs new app update), end with:
[[ESCALATE: short reason]]
"""

LOCAL_FAQ = [
    (
        ("api key", "এপিআই কী", "api কী", "api", "inactive", "ইনঅ্যাকটিভ"),
        {
            "en": "API keys are like secret passwords from other websites.\n\n1) Open Settings\n2) Open API Connection\n3) Pick a provider (example: Google)\n4) Press Get API — browser opens their site\n5) Copy the key\n6) Paste into slot 1 and 2 (need at least 2)\n7) Press Save APIs\n\nWhen every required provider has 2 keys, the red Inactive banner goes away.\n\nStuck? Paste your keys here — I can place them for you, then I delete them from chat.",
            "bn": "API কী মানে অন্য ওয়েবসাইটের গোপন পাসওয়ার্ড।\n\n১) Settings ট্যাব খুলুন\n২) API Connection খুলুন\n৩) প্রোভাইডার বাছুন (যেমন Google)\n৪) Get API চাপুন — সাইট খুলবে\n৫) কী কপি করুন\n৬) স্লট ১ ও ২-এ পেস্ট করুন (কমপক্ষে ২টি)\n৭) Save APIs চাপুন\n\nসব প্রয়োজনীয় প্রোভাইডারে ২টি কী থাকলে ইনঅ্যাকটিভ ব্যানার চলে যাবে।\n\nআটকে গেলে কী এখানে পেস্ট করুন — আমি সঠিক জায়গায় বসিয়ে চ্যাট থেকে মুছে দেব।",
        },
    ),
    (
        ("youtube", "facebook", "লগইন", "login", "browser", "ব্রাউজার"),
        {
            "en": "YouTube/Facebook login opens a real browser window.\n\n1) Go to Channel tab\n2) For each language, fill YouTube channel name / Facebook page name\n3) Press YouTube Login or Facebook Login\n4) Sign in in the browser window\n5) Wait until the button says Saved (about 1–3 minutes)\n\nIf no window appears, install Google Chrome and try again.",
            "bn": "YouTube/Facebook লগইন আসল ব্রাউজার উইন্ডো খোলে।\n\n১) Channel ট্যাবে যান\n২) প্রতি ভাষায় YouTube চ্যানেল / Facebook পেজ নাম দিন\n৩) YouTube Login বা Facebook Login চাপুন\n৪) ব্রাউজার উইন্ডোতে লগইন করুন\n৫) Saved না দেখা পর্যন্ত অপেক্ষা (১–৩ মিনিট)\n\nউইন্ডো না খুললে Chrome ইনস্টল করে আবার চেষ্টা করুন।",
        },
    ),
    (
        ("plan", "প্ল্যান", "দাম", "price", "প্যাকেজ", "সাবস্ক্রিপশন", "subscription", "cost", "টাকা"),
        {
            "en": "AutoMovie Pro Plans & Pricing:\n\n1) Core License: ৳2,998 (Includes English + 1 primary language pack).\n2) Extra Language Addon: ৳499 per language.\n\n👑 Special Google AI Pro Packages (Nano Banana + Veo-3 + Charon TTS + 150GB Drive):\n- 1 Month (30 Days): ৳120\n- 12 Months (1 Year): ৳999 (Popular)\n- 18 Months (1.5 Years): ৳1,299 (Best Value)\n\nEach Google Pro account purchased unlocks 1 dedicated Google Master API key slot automatically after admin approval!",
            "bn": "AutoMovie Pro এর বর্তমান প্ল্যান এবং প্রাইস লিস্ট:\n\n১) মূল সফটওয়্যার প্যাকেজ: ৳২,৯৯৮ (ইংরেজি + যেকোনো ১টি পছন্দের ভাষা অন্তর্ভুক্ত)।\n২) অতিরিক্ত ভাষা প্যাক: প্রতি ভাষা মাত্র ৳৪৯৯।\n\n👑 স্পেশাল গুগল AI Pro প্যাকেজ (Nano Banana, Veo-3, Charon স্টুডিও TTS এবং ১৫০ জিবি ক্লাউড ড্রাইভ):\n• মাসিক প্ল্যান (৩০ দিন): ১২০ ৳\n• বাৎসরিক প্ল্যান (১২ মাস): ৯৯৯ ৳ (সবচেয়ে জনপ্রিয়)\n• স্পেশাল প্ল্যান (১৮ মাস): ১২৯৯ ৳ (সেরা ভ্যালু)\n\nআমাদের কাছ থেকে প্রতিবার একটি করে গুগল প্রো অ্যাকাউন্ট নিলে অ্যাডমিন এক্সেপ্ট করার সাথে সাথে সফটওয়্যারে ১টি করে নতুন স্পেশাল এপিআই স্লট আনলক হয়ে যাবে (সর্বোচ্চ ৩টি)!",
        },
    ),
    (
        ("google pro", "গুগল প্রো", "স্পেশাল অ্যাকাউন্ট", "special account", "google_paid", "veo", "nano banana", "drive", "ড্রাইভ"),
        {
            "en": "Special Google AI Pro Account:\n- Features: Veo-3 full-scene video generation, Nano Banana prompt enhancer, Charon natural studio voice, 150GB Google Cloud Drive vault.\n- Pricing: 1 Month: ৳120 | 12 Months: ৳999 | 18 Months: ৳1299.\n- How it works: Order from Website/App with your Gmail -> Admin manually connects account -> 1 API key slot unlocks -> Paste your key and start making videos!",
            "bn": "স্পেশাল গুগল AI Pro অ্যাকাউন্ট সম্পর্কিত তথ্য:\n- সুবিধাসমূহ: Veo-3 ফুল-সিন ভিডিও ক্লিপ জেনারেশন, Nano Banana প্রম্পট এনহ্যান্সার, Charon ন্যাচারাল স্টুডিও ভয়েস, এবং ১৫০ জিবি গুগল ক্লাউড ড্রাইভ ভল্ট ব্যাকআপ।\n- প্রাইস: ১ মাস ১২০ ৳ | ১২ মাস ৯৯৯ ৳ | ১৮ মাস ১২৯৯ ৳।\n- প্রসেস: আপনার জিমেইল দিয়ে অর্ডার করুন -> অ্যাডমিন অ্যাকাউন্ট কানেক্ট করে অর্ডার এক্সেপ্ট করবেন -> সফটওয়্যারে এপিআই কী বসানোর ১টি স্লট স্বয়ংক্রিয়ভাবে আনলক হয়ে যাবে!",
        },
    ),
]


def _lang_pack(lang: str) -> str:
    return "bn" if (lang or "bn").startswith("bn") else "en"


def try_local_faq(message: str, ui_lang: str) -> str:
    text = (message or "").lower()
    if len(text) < 3:
        return ""
    pack = _lang_pack(ui_lang)
    for keys, answers in LOCAL_FAQ:
        hits = sum(1 for k in keys if k.lower() in text)
        if hits >= 1 and any(k in text for k in keys[:4]):
            # Prefer stronger matches
            if hits >= 1:
                return answers.get(pack) or answers["en"]
    return ""


def extract_provider_keys(message: str) -> Dict[str, List[str]]:
    """Pull API-looking tokens from chat; map to providers using nearby labels."""
    from pipeline.channel_api_slots import empty_slot_map

    text = message or ""
    found = empty_slot_map()
    lower = text.lower()

    # Labeled lines: "google: KEY" / "Groq KEY"
    for pid, hints in PROVIDER_HINTS:
        for hint in hints:
            for m in re.finditer(
                rf"{re.escape(hint)}\s*[:=\-]?\s*({_TOKEN_RE.pattern})",
                text,
                flags=re.IGNORECASE,
            ):
                tok = m.group(1).strip()
                if tok and tok not in found[pid]:
                    found[pid].append(tok)

    # Unlabeled tokens — guess by prefix
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(1).strip()
        if not tok:
            continue
        already = any(tok in vals for vals in found.values())
        if already:
            continue
        pid = ""
        if tok.startswith("AIza") or tok.startswith("AI"):
            pid = "google"
        elif tok.startswith("gsk_"):
            pid = "groq"
        elif tok.startswith("sk-or") or "openrouter" in lower:
            pid = "openrouter"
        elif tok.startswith("hf_"):
            pid = "huggingface"
        elif "pexels" in lower[max(0, m.start() - 40) : m.start()]:
            pid = "pexels"
        elif "agnes" in lower[max(0, m.start() - 40) : m.start()]:
            pid = "agnes"
        if pid and tok not in found[pid]:
            found[pid].append(tok)

    return {k: v for k, v in found.items() if v}


def redact_keys(text: str) -> str:
    from pipeline.api_keys import redact_sensitive_text

    return redact_sensitive_text(text)


def _describe_screenshot(image_b64: str, mime: str = "image/png") -> str:
    raw = (image_b64 or "").strip()
    if "," in raw and raw.lower().startswith("data:"):
        header, raw = raw.split(",", 1)
        if "image/" in header:
            mime = header.split("image/")[1].split(";")[0] or mime
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception:
        return ""
    if not data or len(data) > 6_000_000:
        return ""
    # Google vision skipped by default (translate/localize-only policy)
    import os

    if (os.environ.get("AMP_ALLOW_GOOGLE_AGENT_VISION") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        return ""
    try:
        from pipeline.api_keys import load_api_bundle
        from pipeline.google_api_gate import GoogleCircuitOpen, gated_generate_content
        from google.genai import types

        keys = list((load_api_bundle() or {}).get("google_keys") or [])
        if not keys:
            return ""
        part = types.Part.from_bytes(data=data, mime_type=mime or "image/png")
        prompt = (
            "Describe this AutoMovie Pro screenshot for a beginner. "
            "List visible tabs, errors, red banners, and field names. Max 10 short sentences."
        )
        result = gated_generate_content(
            api_keys=keys,
            contents=[prompt, part],
            model="gemini-flash-latest",
            purpose="text",
        )
        return (result.text or "").strip()
    except Exception as exc:
        logger.warning("screenshot vision failed: %s", exc)
        return ""


def _parse_markers(reply: str) -> Dict[str, Any]:
    actions: List[Dict[str, str]] = []
    escalate_reason = ""
    clean = reply or ""
    for m in ACTION_RE.finditer(clean):
        actions.append({"type": m.group(1).lower(), "arg": (m.group(2) or "").strip()})
    em = ESCALATE_RE.search(clean)
    if em:
        escalate_reason = em.group(1).strip()
    clean = ACTION_RE.sub("", clean)
    clean = ESCALATE_RE.sub("", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return {"reply": clean, "actions": actions, "escalate_reason": escalate_reason}


def agent_chat_reply(
    message: str,
    *,
    history: List[Dict[str, str]] | None = None,
    activity_hint: str = "",
    ui_lang: str = "bn",
    image_base64: str = "",
    image_mime: str = "image/png",
) -> Dict[str, Any]:
    text = (message or "").strip()
    extracted = extract_provider_keys(text)
    caption = ""
    if image_base64:
        caption = _describe_screenshot(image_base64, image_mime)
        if caption:
            text = (text + "\n\n[Screenshot analysis]\n" + caption).strip()
        elif not text and not extracted:
            text = "[Screenshot attached but could not be read. Ask user to type the red error text.]"

    # If keys were pasted, prefer setup path (no key echo)
    if extracted:
        safe_msg = redact_keys(text)
        counts = {k: len(v) for k, v in extracted.items()}
        pack = _lang_pack(ui_lang)
        if pack == "bn":
            reply = (
                "ধন্যবাদ — আপনার API কী পেয়েছি। আমি এগুলো Settings-এর সঠিক ঘরে বসিয়ে দিচ্ছি।\n"
                f"প্রাপ্ত: {', '.join(f'{k}×{n}' for k, n in counts.items())}\n"
                "কীগুলো চ্যাট থেকে লুকানো/মুছে দেওয়া হবে। Save হলে Dashboard-এ Active চেক করুন।\n"
                "[[ACTION:open_tab:settings]][[ACTION:open_api:]]"
            )
        else:
            reply = (
                "Got it — I received your API keys and will place them in the right Settings slots.\n"
                f"Received: {', '.join(f'{k}×{n}' for k, n in counts.items())}\n"
                "Keys will be hidden/removed from chat. Then check Dashboard for Active.\n"
                "[[ACTION:open_tab:settings]][[ACTION:open_api:]]"
            )
        parsed = _parse_markers(reply)
        return {
            "ok": True,
            "reply": parsed["reply"],
            "actions": parsed["actions"],
            "apply_keys": extracted,
            "redact_user": True,
            "escalate": False,
            "escalate_reason": "",
            "screenshot_caption": caption,
            "provider": "local_key_setup",
        }

    if not text:
        return {"ok": False, "error": "empty_message"}

    # Fast local FAQ for common questions (EL10, no LLM nonsense)
    local = try_local_faq(text, ui_lang)
    if local and len(text) < 160:
        # Suggest opening the right tab
        actions = []
        low = text.lower()
        if any(x in low for x in ("api", "কী", "key", "inactive")):
            actions = [{"type": "open_tab", "arg": "settings"}, {"type": "open_api", "arg": ""}]
        elif any(x in low for x in ("youtube", "facebook", "login", "লগইন")):
            actions = [{"type": "open_tab", "arg": "channel"}]
        elif any(x in low for x in ("generate", "short", "long", "জেনারেট")):
            actions = [{"type": "open_tab", "arg": "home"}]
        return {
            "ok": True,
            "reply": local,
            "actions": actions,
            "escalate": False,
            "escalate_reason": "",
            "screenshot_caption": caption,
            "provider": "local_faq",
        }

    from pipeline.llm_router import chat_text

    lang = (ui_lang or "bn").strip().lower()[:8] or "bn"
    hist = history or []
    lines = [SYSTEM_TMPL.format(lang=lang)]
    if activity_hint:
        lines.append(f"Current live activity snapshot:\n{activity_hint}")
    for h in hist[-6:]:
        role = (h.get("role") or "user").strip()
        content = redact_keys((h.get("content") or "").strip())
        if content:
            lines.append(f"{role.upper()}: {content}")
    lines.append(f"USER: {redact_keys(text)}")
    lines.append("ASSISTANT:")
    prompt = "\n\n".join(lines)
    try:
        out = chat_text(prompt, purpose="agent")
        reply = ""
        if isinstance(out, dict):
            reply = str(out.get("text") or out.get("content") or "").strip()
        else:
            reply = str(out or "").strip()
        if not reply:
            raise RuntimeError("empty_agent_reply")
        # Soft guard: if reply too short/weird, fall back to local tip
        if len(reply) < 25 and local:
            reply = local
        parsed = _parse_markers(reply)
        return {
            "ok": True,
            "reply": parsed["reply"],
            "actions": parsed["actions"],
            "escalate": bool(parsed["escalate_reason"]),
            "escalate_reason": parsed["escalate_reason"],
            "screenshot_caption": caption,
            "provider": (out.get("provider") if isinstance(out, dict) else ""),
        }
    except Exception as exc:
        logger.warning("agent chat failed: %s", exc)
        fallback = local or (
            "আমি এখন LLM দিয়ে উত্তর দিতে পারিনি।\n"
            "১) Live ট্যাব দেখুন কোন ধাপে আটকে\n"
            "২) Settings → API Connection — প্রয়োজনীয় কী আছে?\n"
            "৩) Channel সেটআপ হয়েছে?\n"
            f"(error: {str(exc)[:80]})\n"
            "[[ESCALATE: agent LLM unavailable]]"
        )
        parsed = _parse_markers(fallback)
        return {
            "ok": True,
            "reply": parsed["reply"],
            "actions": parsed["actions"],
            "escalate": True,
            "escalate_reason": parsed["escalate_reason"] or str(exc)[:200],
            "fallback": True,
            "screenshot_caption": caption,
        }
