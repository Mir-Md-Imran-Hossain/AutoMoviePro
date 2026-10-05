"""
Language output policy for AutoMoviePro-Software.

SOURCE = English master (video + English TTS). See pipeline/master_lang.py for the lock gate.
LOCALIZE = replace audio + subtitles only; keep same Agnes picture.
Inspired by AutoMoviePro/config/lang_output.py but scoped to the 6 languages
requested for this product line.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Master generation language (ISO 639-1 + BCP-47 for dubbing APIs)
SOURCE_LANG = "en"
SOURCE_LANG_BCP47 = "en-US"

# Final delivery languages (English first = automatic master)
TARGET_LANG_CODES: Tuple[str, ...] = ("en", "bn", "hi", "ur", "ta", "ml")

LANG_FOLDERS: Dict[str, str] = {
    "en": "English",
    "bn": "Bangla",
    "hi": "Hindi",
    "ur": "Urdu",
    "ta": "Tamil",
    "ml": "Malayalam",
}

LANG_DISPLAY: Dict[str, str] = {
    "en": "English",
    "bn": "Bangla",
    "hi": "Hindi",
    "ur": "Urdu",
    "ta": "Tamil",
    "ml": "Malayalam",
}

# Locked master narrator: Gemini Charon (male, informative). Same identity on every lang.
MASTER_VOICE_NAME = "Charon"

# Official Gemini TTS female prebuilts — never allowed, even as alts.
_FEMALE_GEMINI_VOICES = frozenset(
    {
        "kore",
        "aoede",
        "leda",
        "zephyr",
        "callirrhoe",
        "autonoe",
        "despina",
        "erinome",
        "laomedeia",
        "achernar",
        "gacrux",
        "pulcherrima",
        "vindemiatrix",
        "sulafat",
    }
)

# Male Gemini voices that are NOT Charon — treat as timbre drift unless contract alt.
_DRIFT_MALE_VOICES = frozenset(
    {
        "fenrir",
        "puck",
        "enceladus",
        "iapetus",
        "algieba",
        "algenib",
        "rasalgethi",
        "alnilam",
        "schedar",
        "zubenelgenubi",
        "sadachbia",
        "sadaltager",
    }
)

_DRIFT_VOICES = _FEMALE_GEMINI_VOICES | _DRIFT_MALE_VOICES

# Edge neural males (quota fallback). Gemini names must never be sent to edge-tts.
EDGE_VOICES: Dict[str, str] = {
    "en": "en-US-GuyNeural",
    "bn": "bn-IN-BashkarNeural",
    "hi": "hi-IN-MadhurNeural",
    "ur": "ur-PK-AsadNeural",
    "ta": "ta-IN-ValluvarNeural",
    "ml": "ml-IN-MidhunNeural",
}

EDGE_VOICE_FALLBACKS: Dict[str, Tuple[str, ...]] = {
    "en": ("en-US-GuyNeural", "en-US-DavisNeural", "en-GB-RyanNeural"),
    "bn": ("bn-IN-BashkarNeural",),
    "hi": ("hi-IN-MadhurNeural",),
    "ur": ("ur-PK-AsadNeural",),
    "ta": ("ta-IN-ValluvarNeural",),
    "ml": ("ml-IN-MidhunNeural",),
}

_EDGE_FEMALE_HINTS = (
    "jenny",
    "aria",
    "sonia",
    "nabanita",
    "tanishaa",
    "swara",
    "ananya",
    "female",
)

# Gemini TTS voices (ported/adapted from AutoMoviePro voice contracts)
LANG_TTS: Dict[str, Dict[str, Any]] = {
    "en": {
        "voice_name": MASTER_VOICE_NAME,
        "voice_alt": ["Achird", "Umbriel"],
        "english_name": "English",
        "register": "Clear cinematic documentary narrator; natural spoken English; SAME male voice throughout",
        "pace_hint": (
            "steady storytelling ~2.3 words/sec; never rush final nouns; "
            "same pitch/timbre as neighboring clips"
        ),
    },
    "bn": {
        "voice_name": MASTER_VOICE_NAME,
        "voice_alt": ["Orus", "Achird"],
        "english_name": "Bangla",
        "register": (
            "Native Bangla documentary narration — emotional gravity, cultural cadence, "
            "SAME consistent male voice; never robotic MT Bangla"
        ),
        "pace_hint": "slightly measured; clear breathing pauses; warm storytelling",
    },
    "hi": {
        "voice_name": MASTER_VOICE_NAME,
        "voice_alt": ["Achird", "Orus"],
        "english_name": "Hindi",
        "register": (
            "Native Hindi documentary narration — dignified spoken Hindi, "
            "SAME consistent male voice; not literal English calque"
        ),
        "pace_hint": "steady conversational; clear nouns",
    },
    "ur": {
        "voice_name": MASTER_VOICE_NAME,
        "voice_alt": ["Orus", "Achird"],
        "english_name": "Urdu",
        "register": (
            "Soft dignified native Urdu documentary narration — cultural grace, "
            "faith-aware respect, SAME consistent male voice"
        ),
        "pace_hint": "gentle pauses; controlled emotion; never rush sacred phrasing",
    },
    "ta": {
        "voice_name": MASTER_VOICE_NAME,
        "voice_alt": ["Achird"],
        "english_name": "Tamil",
        "register": (
            "Native Tamil documentary narration — natural spoken Tamil cadence, "
            "SAME consistent male voice"
        ),
        "pace_hint": "steady storytelling; clear articulation",
    },
    "ml": {
        "voice_name": MASTER_VOICE_NAME,
        "voice_alt": ["Achird"],
        "english_name": "Malayalam",
        "register": (
            "Native Malayalam documentary narration — natural spoken Malayalam, "
            "SAME consistent male voice"
        ),
        "pace_hint": "steady storytelling; warm clarity",
    },
}
# Legacy note: localization remux now always uses setpts stretch (never stream_loop).
# Kept for reference / future clip-fit EDL tooling.
MAX_STRETCH_RATIO = 0.08

# Cultural localization (NOT literal MT). Each locale gets native documentary voice:
# emotion, register, cultural gravity, faith-aware phrasing — so the script feels
# originally written in that language.
LOCALIZATION_CULTURE: Dict[str, Dict[str, Any]] = {
    "en": {
        "script": "Latin",
        "register": "clear cinematic documentary English",
        "emotion": "measured curiosity; confident storytelling without hype",
        "culture": "global documentary voice; plain vivid English",
        "faith_sensitivity": "neutral; avoid mocking any faith",
        "avoid": [
            "Banglish/Hinglish mashups",
            "corporate AI filler",
            "overly literal bilingual calques",
        ],
        "prefer": [
            "natural spoken sentences",
            "one clear claim per beat",
        ],
    },
    "bn": {
        "script": "Bengali (বাংলা)",
        "register": "স্বাভাবিক ডকুমেন্টারি বাংলা — সাহিত্যিক অতিরঞ্জন নয়, কিন্তু ভাবগাম্ভীর্য আছে",
        "emotion": "কোমল আবেগ, বিস্ময় ও গাম্ভীর্য; শ্রোতাকে কাছে টানার মতো বর্ণনা",
        "culture": (
            "বাংলা সংস্কৃতির শব্দচয়ন ও ছন্দ; যেন মূল স্ক্রিপ্টই বাংলায় লেখা। "
            "স্থানীয় উপমা ও স্বাভাবিক কথ্য-ডকুমেন্টারি টোন ব্যবহার করুন।"
        ),
        "faith_sensitivity": (
            "ধর্মীয়/সাংস্কৃতিক অনুভূতিতে সম্মান — অপমানজনক বা হালকাভাবে ধর্মীয় "
            "প্রতীক ব্যবহার করবেন না; প্রয়োজনে নিরপেক্ষ সম্মানজনক ভাষা রাখুন"
        ),
        "avoid": [
            "ইংরেজি শব্দ-শব্দের সরাসরি ক্যাল্ক (word-for-word)",
            "বাংলা+ইংরেজি মিশ্র বাক্য (Banglish) যেখানে বাংলা সম্ভব",
            "রোবোটিক/মেশিন-অনুবাদ শোনা শব্দবিন্যাস",
            "অতিরিক্ত আনুষ্ঠানিক সংবাদপাঠক টোন যা আবেগহীন",
        ],
        "prefer": [
            "নেটিভ বাংলা ছন্দ ও শ্বাসাঘাত",
            "একই তথ্য, কিন্তু বাংলায় স্বাভাবিক প্রকাশ",
            "শুনতে মধুর ও স্পষ্ট — TTS-এ খারাপ না লাগে",
        ],
    },
    "hi": {
        "script": "Devanagari (हिन्दी)",
        "register": "स्पष्ट डॉक्यूमेंटरी हिन्दी — सरल, गरिमापूर्ण, बोलचाल के करीब",
        "emotion": "जिज्ञासा और गंभीरता का संतुलन; ओवर-ड्रामा नहीं",
        "culture": (
            "हिन्दी भाषी दर्शक के लिए मूल-लेखन जैसा लगे। "
            "अनावश्यक अंग्रेज़ी वाक्य-रचना की नकल न करें; देशज मुहावरे संयम से।"
        ),
        "faith_sensitivity": "धर्म/समुदाय का सम्मान; व्यंग्य या हल्के मजाक से बचें",
        "avoid": [
            "शब्द-दर-शब्द अंग्रेज़ी अनुवाद",
            "जबरन Hinglish जहाँ शुद्ध हिन्दी स्वाभाविक हो",
            "रोबोटिक मशीन-अनुवाद शैली",
        ],
        "prefer": [
            "स्वाभाविक मौखिक हिन्दी",
            "स्पष्ट उच्चारण-अनुकूल वाक्य",
            "भाव बनाए रखें, तथ्य न बदलें",
        ],
    },
    "ur": {
        "script": "Arabic-Nastaliq (اردو)",
        "register": "شائستہ، موقر ڈاکیومنٹری اردو — نرم لہجہ، ادبی چاشنی ہلکی سی",
        "emotion": "وقار، نرمی، اور سنجیدہ تجسس؛ جذباتی لیکن غیر مبالغہ آمیز",
        "culture": (
            "اردو تہذیب و ادب کی نزاکت؛ ایسا لگے کہ اسکرپٹ اصلاً اردو میں لکھا گیا۔ "
            "غیر ضروری انگریزی جملہ سازی سے گریز۔"
        ),
        "faith_sensitivity": (
            "مذہبی اور تہذیبی حساسیت کا خیال؛ الفاظ میں احترام؛ "
            "مقدس اصطلاحات کو ہلکا یا طنز آمیز نہ بنائیں"
        ),
        "avoid": [
            "لفظ بہ لفظ انگریزی ترجمہ",
            "روبوٹک مشین-ترجمہ لہجہ",
            "غیر ضروری سخت یا توہین آمیز انداز",
        ],
        "prefer": [
            "شائستہ بول چال اردو",
            "آہستہ وقفے اور واضح جملے (TTS دوست)",
            "اصل جذباتی رنگ برقرار",
        ],
    },
    "ta": {
        "script": "Tamil (தமிழ்)",
        "register": "தெளிவான ஆவணப்படத் தமிழ் — இயல்பான பேச்சு நடை",
        "emotion": "ஆர்வமும் கண்ணியமும்; மிகை நாடகம் இல்லை",
        "culture": (
            "தமிழ் பார்வையாளருக்கு அசல் தமிழ் எழுத்து போல இருக்கட்டும். "
            "ஆங்கில வாக்கிய அமைப்பை அப்படியே பின்பற்ற வேண்டாம்."
        ),
        "faith_sensitivity": "மத/கலாச்சார மரியாதை; புண்படுத்தும் சொல்லாடலைத் தவிர்க்கவும்",
        "avoid": [
            "சொல்லுக்குச் சொல் ஆங்கில மொழிபெயர்ப்பு",
            "இயந்திர மொழிபெயர்ப்பு போன்ற கடின நடை",
        ],
        "prefer": [
            "இயற்கையான பேச்சுத்தமிழ்",
            "TTS-க்கு இனிமையான தெளிவு",
            "உணர்ச்சியை வைத்து உண்மைகளை மாற்றாதீர்கள்",
        ],
    },
    "ml": {
        "script": "Malayalam (മലയാളം)",
        "register": "വ്യക്തമായ ഡോക്യുമെന്ററി മലയാളം — സ്വാഭാവിക സംസാരശൈലി",
        "emotion": "ഗൗരവവും കൗതുകവും; അമിത നാടകീയത ഒഴിവാക്കുക",
        "culture": (
            "മലയാളി കേൾക്കുമ്പോൾ അസൽ മലയാളത്തിൽ എഴുതിയതായി തോന്നണം. "
            "ഇംഗ്ലീഷ് വാക്യഘടനയുടെ നേരിട്ടുള്ള പകർപ്പ് വേണ്ട."
        ),
        "faith_sensitivity": "മത/സാംസ്കാരിക ബഹുമാനം; വ്രണപ്പെടുത്തുന്ന ഭാഷ ഒഴിവാക്കുക",
        "avoid": [
            "വാക്കിന് വാക്ക് ഇംഗ്ലീഷ് വിവർത്തനം",
            "മെഷീൻ-ട്രാൻസ്‌ലേഷൻ ശൈലി",
        ],
        "prefer": [
            "സ്വാഭാവിക സംസാര മലയാളം",
            "TTS-ന് മനോഹരമായ വ്യക്തത",
            "വികാരം നിലനിർത്തി വസ്തുത മാറ്റരുത്",
        ],
    },
}


def localization_culture(code: str) -> Dict[str, Any]:
    key = (code or SOURCE_LANG).lower().strip()[:2]
    return dict(LOCALIZATION_CULTURE.get(key) or LOCALIZATION_CULTURE[SOURCE_LANG])


def localization_culture_brief(code: str) -> str:
    """Compact per-locale brief injected into localization prompts."""
    c = localization_culture(code)
    avoid = "; ".join(c.get("avoid") or [])
    prefer = "; ".join(c.get("prefer") or [])
    return (
        f"Script: {c.get('script')}. "
        f"Register: {c.get('register')}. "
        f"Emotion: {c.get('emotion')}. "
        f"Culture: {c.get('culture')}. "
        f"Faith/respect: {c.get('faith_sensitivity')}. "
        f"Prefer: {prefer}. "
        f"Avoid: {avoid}."
    )


def localize_targets(*, include_source: bool = False) -> List[str]:
    """Languages that need translate+TTS+remux (usually all except source)."""
    if include_source:
        return list(TARGET_LANG_CODES)
    return [c for c in TARGET_LANG_CODES if c != SOURCE_LANG]


def folder_for_lang(code: str) -> str:
    return LANG_FOLDERS.get((code or SOURCE_LANG).lower(), LANG_FOLDERS[SOURCE_LANG])


def tts_contract(code: str) -> Dict[str, Any]:
    return dict(LANG_TTS.get((code or SOURCE_LANG).lower(), LANG_TTS[SOURCE_LANG]))


def _canonical_gemini_voice(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    if raw.lower() == MASTER_VOICE_NAME.lower():
        return MASTER_VOICE_NAME
    return raw[0].upper() + raw[1:] if raw else raw


def locked_voice_chain(language_hint: str = SOURCE_LANG) -> List[str]:
    """Charon first, then male contract alts. Never female."""
    contract = tts_contract(language_hint)
    chain: List[str] = [MASTER_VOICE_NAME]
    locked = str(contract.get("voice_name") or MASTER_VOICE_NAME).strip()
    if locked and locked.lower() not in _FEMALE_GEMINI_VOICES:
        chain.append(_canonical_gemini_voice(locked))
    for alt in contract.get("voice_alt") or []:
        name = _canonical_gemini_voice(str(alt or ""))
        if not name or name.lower() in _FEMALE_GEMINI_VOICES:
            continue
        chain.append(name)
    seen = set()
    out: List[str] = []
    for v in chain:
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out or [MASTER_VOICE_NAME]


def resolve_locked_voice(voice_name: str = "", *, language_hint: str = SOURCE_LANG) -> str:
    """
    One narrator identity across the job: Gemini prebuilt Charon.
    Female / unknown / empty → Charon. Male contract alts only when explicitly requested
    after a Charon failure (Achird/Orus/Umbriel).
    """
    locked = MASTER_VOICE_NAME
    requested = (voice_name or "").strip()
    if not requested:
        return locked
    key = requested.lower()
    if key in _FEMALE_GEMINI_VOICES or key in _DRIFT_VOICES:
        return locked
    if key == locked.lower():
        return locked
    allowed = {v.lower(): v for v in locked_voice_chain(language_hint)}
    if key in allowed:
        return allowed[key]
    return locked


def is_female_or_drift_voice(voice_name: str) -> bool:
    key = (voice_name or "").strip().lower()
    if not key:
        return False
    if key in _FEMALE_GEMINI_VOICES:
        return True
    if any(h in key for h in _EDGE_FEMALE_HINTS):
        return True
    return False


def resolve_edge_voice(voice_name: str = "", *, language_hint: str = SOURCE_LANG) -> str:
    """
    Map Gemini names / empty / female Edge voices to the locked male Neural for the language.
    """
    lang = (language_hint or SOURCE_LANG).lower().strip()[:2]
    primary = EDGE_VOICES.get(lang) or EDGE_VOICES[SOURCE_LANG]
    requested = (voice_name or "").strip()
    if not requested:
        return primary
    key = requested.lower()
    if "neural" not in key:
        # Gemini Charon/Kore/etc. are not Edge voices
        return primary
    if is_female_or_drift_voice(requested):
        return primary
    chain = EDGE_VOICE_FALLBACKS.get(lang) or (primary,)
    for cand in chain:
        if cand.lower() == key:
            return cand
    return primary


def edge_voice_chain(language_hint: str = SOURCE_LANG) -> List[str]:
    lang = (language_hint or SOURCE_LANG).lower().strip()[:2]
    return list(EDGE_VOICE_FALLBACKS.get(lang) or (EDGE_VOICES.get(lang) or EDGE_VOICES[SOURCE_LANG],))
