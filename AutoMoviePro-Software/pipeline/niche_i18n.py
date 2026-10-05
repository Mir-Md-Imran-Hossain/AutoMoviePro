"""Niche name/blurb translations for UI dropdown (amp_ui_lang).

Strategy:
  1) Prefer marathon-written niche_i18n_store / profile.i18n
  2) Else apply curated title glossary + short blurb templates
  3) Optional live LLM translate when AMP_NICHE_I18N_LLM=1
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Tuple

from pipeline.niche_production_profile import UI_LANGS, upsert_i18n

# High-quality curated title translations for common Nish niches (extend via marathon).
TITLE_GLOSSARY: Dict[str, Dict[str, str]] = {
    "Ancient Civilizations": {
        "bn": "প্রাচীন সভ্যতা",
        "hi": "प्राचीन सभ्यताएँ",
        "ur": "قدیم تہذیبیں",
        "ta": "பண்டைய நாகரிகங்கள்",
        "ml": "പുരാതന നാഗരികതകൾ",
    },
    "Lost Kingdoms": {
        "bn": "হারিয়ে যাওয়া রাজ্য",
        "hi": "लुप्त साम्राज्य",
        "ur": "کھوئی ہوئی سلطنتیں",
        "ta": "தொலைந்த அரசுகள்",
        "ml": "നഷ്ടപ്പെട്ട രാജ്യങ്ങൾ",
    },
    "Epic Battles": {
        "bn": "মহাকাব্যিক যুদ্ধ",
        "hi": "महायुद्ध",
        "ur": "عظیم جنگیں",
        "ta": "காவியப் போர்கள்",
        "ml": "മഹായുദ്ധങ്ങൾ",
    },
    "Famous Assassinations": {
        "bn": "বিখ্যাত হত্যাকাণ্ড",
        "hi": "प्रसिद्ध हत्याएँ",
        "ur": "مشہور قتل",
        "ta": "பிரபல படுகொலைகள்",
        "ml": "പ്രശസ്ത കൊലപാതകങ്ങൾ",
    },
    "Royal Scandals": {
        "bn": "রাজকীয় কেলেঙ্কারি",
        "hi": "शाही घोटाले",
        "ur": "شاہی اسکینڈلز",
        "ta": "அரச குடும்ப ஊழல்கள்",
        "ml": "രാജകീയ അഴിമതികൾ",
    },
    "History's Unsolved Mysteries": {
        "bn": "ইতিহাসের অমীমাংসিত রহস্য",
        "hi": "इतिहास के अनसुलझे रहस्य",
        "ur": "تاریخ کے حل نہ ہونے والے اسرار",
        "ta": "வரலாற்றின் விடுபடாத மர்மங்கள்",
        "ml": "ചരിത്രത്തിലെ അപരിഹൃത രഹസ്യങ്ങൾ",
    },
    "Vanished Without Trace": {
        "bn": "নিঃশেষে অদৃশ্য",
        "hi": "बिना निशान गायब",
        "ur": "بے نشان غائب",
        "ta": "சுவடு இல்லாமல் மறைந்தவை",
        "ml": "അടയാളമില്ലാതെ അപ്രത്യക്ഷം",
    },
    "Shipwreck Diaries": {
        "bn": "জাহাজডুবির ডায়েরি",
        "hi": "जहाज़ दुर्घटना डायरी",
        "ur": "جہاز حادثات کی ڈائری",
        "ta": "கப்பல் விபத்து நாட்குறிப்பு",
        "ml": "കപ്പൽ അപകട ഡയറികൾ",
    },
    "Air Crash Mysteries": {
        "bn": "বিমান দুর্ঘটনার রহস্য",
        "hi": "विमान दुर्घटना रहस्य",
        "ur": "ہوائی حادثات کے اسرار",
        "ta": "விமான விபத்து மர்மங்கள்",
        "ml": "വിമാന അപകട രഹസ്യങ്ങൾ",
    },
    "Industrial Catastrophes": {
        "bn": "শিল্প বিপর্যয়",
        "hi": "औद्योगिक आपदाएँ",
        "ur": "صنعتی تباہیاں",
        "ta": "தொழில்துறை பேரழிவுகள்",
        "ml": "വ്യാവസായിക ദുരന്തങ്ങൾ",
    },
    "Nature's Wrath": {
        "bn": "প্রকৃতির রোষ",
        "hi": "प्रकृति का प्रकोप",
        "ur": "قدرت کا قہر",
        "ta": "இயற்கையின் கோபம்",
        "ml": "പ്രകൃതിയുടെ കോപം",
    },
    "Pandemics Through Time": {
        "bn": "কালের মহামারী",
        "hi": "काल के महामारी",
        "ur": "تاریخ کی وباؤں",
        "ta": "காலத்தின் தொற்றுநோய்கள்",
        "ml": "കാലത്തിലൂടെയുള്ള മഹാമാരികൾ",
    },
    "Impossible Survival": {
        "bn": "অসম্ভব বেঁচে থাকা",
        "hi": "असंभव उत्तरजीविता",
        "ur": "ناممکن بقا",
        "ta": "சாத்தியமற்ற உயிர்வாழ்வு",
        "ml": "അസാധ്യമായ അതിജീവനം",
    },
    "Against All Odds": {
        "bn": "সব বাধা ডিঙিয়ে",
        "hi": "सभी बाधाओं के खिलाफ",
        "ur": "تمام مشکلات کے باوجود",
        "ta": "எல்லாத் தடைகளையும் மீறி",
        "ml": "എല്ലാ പ്രതിബന്ധങ്ങളെയും മറികടന്ന്",
    },
    "Legacy of One Day": {
        "bn": "এক দিনের উত্তরাধিকার",
        "hi": "एक दिन की विरासत",
        "ur": "ایک دن کی میراث",
        "ta": "ஒரு நாளின் மரபு",
        "ml": "ഒരു ദിവസത്തിന്റെ പൈതൃകം",
    },
}



BLURB_PREFIX: Dict[str, str] = {
    "en": "Video type: ",
    "bn": "ভিডিও টাইপ: ",
    "hi": "वीडियो प्रकार: ",
    "ur": "ویڈیو کی قسم: ",
    "ta": "வீடியோ வகை: ",
    "ml": "വീഡിയോ തരം: ",
}


def _truncate(text: str, n: int = 160) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= n:
        return t
    return (t[: n - 1].rsplit(" ", 1)[0] or t[: n - 1]) + "…"


def translate_title(name_en: str, lang: str) -> str:
    if lang == "en":
        return name_en
    # Normalize curly/smart apostrophes for glossary lookup
    key = (name_en or "").replace("\u2019", "'").replace("\u2018", "'")
    hit = (TITLE_GLOSSARY.get(name_en) or TITLE_GLOSSARY.get(key) or {}).get(lang)
    if hit:
        return hit
    # Also try curly key variants stored in glossary
    curly = key.replace("'", "\u2019")
    hit = (TITLE_GLOSSARY.get(curly) or {}).get(lang)
    if hit:
        return hit
    return name_en  # honest fallback until marathon fills store


def _load_external_glossary() -> None:
    """Merge pipeline/niche_title_glossary.json into TITLE_GLOSSARY (marathon can expand)."""
    path = Path(__file__).resolve().parent / "niche_title_glossary.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    niches = data.get("niches") if isinstance(data, dict) else None
    if not isinstance(niches, dict):
        return
    for name, langs in niches.items():
        if not isinstance(langs, dict):
            continue
        row = dict(TITLE_GLOSSARY.get(name) or {})
        for lang, title in langs.items():
            if lang in UI_LANGS and lang != "en" and str(title or "").strip():
                row[lang] = str(title).strip()
        TITLE_GLOSSARY[name] = row
        # also index ASCII apostrophe form
        ascii_name = name.replace("\u2019", "'").replace("\u2018", "'")
        if ascii_name != name:
            TITLE_GLOSSARY[ascii_name] = row


_load_external_glossary()


def translate_blurb(blurb_en: str, lang: str) -> str:
    """Keep English factual blurb with localized prefix when full MT unavailable."""
    body = _truncate(blurb_en, 150)
    if lang == "en":
        return body
    # Prefer LLM only when explicitly enabled (marathon can set this)
    if (os.environ.get("AMP_NICHE_I18N_LLM") or "").strip() in ("1", "true", "yes"):
        try:
            from pipeline.localization import translate_text

            out = translate_text(
                body,
                target_lang=lang,
                source_lang="en",
                domain_hint="YouTube niche short description",
                skip_preflight=True,
                localized_validation=False,
            )
            if out and len(out.strip()) > 8 and out.strip().lower() != body.lower():
                return _truncate(out.strip(), 160)
        except Exception:
            pass
        try:
            from pipeline.llm_router import chat_text

            prompt = (
                f"Translate this YouTube niche description into {lang}. "
                f"Keep it under 140 characters. Output ONLY the translation.\n\n{body}"
            )
            out = chat_text(prompt, purpose="translate", json_mode=False)
            if out and len(out.strip()) > 8:
                return _truncate(out.strip(), 160)
        except Exception:
            pass
    return f"{BLURB_PREFIX.get(lang, '')}{body}"


def _translate_title_live(name_en: str, lang: str) -> str:
    try:
        from pipeline.localization import translate_text

        out = translate_text(
            name_en,
            target_lang=lang,
            source_lang="en",
            domain_hint="YouTube niche title short phrase",
            skip_preflight=True,
            localized_validation=False,
        )
        cleaned = (out or "").strip().strip('"').strip("'")
        if cleaned and cleaned.lower() != name_en.lower() and len(cleaned) < 80:
            return cleaned
    except Exception:
        pass
    try:
        from pipeline.llm_router import chat_text

        prompt = (
            f"Translate this YouTube niche title into {lang}. "
            f"Output ONLY the short title translation, no quotes.\n\n{name_en}"
        )
        out = chat_text(prompt, purpose="translate", json_mode=False)
        cleaned = (out or "").strip().strip('"').strip("'").split("\n")[0].strip()
        if cleaned and cleaned.lower() != name_en.lower() and len(cleaned) < 80:
            return cleaned
    except Exception:
        pass
    return name_en


def ensure_translations_for_niche(
    *,
    niche_id: int,
    name_en: str,
    blurb_en: str,
    force_llm: bool = False,
) -> Dict[str, Dict[str, str]]:
    """Build/complete i18n map for one niche and persist to store."""
    if force_llm:
        os.environ["AMP_NICHE_I18N_LLM"] = "1"
    out: Dict[str, Dict[str, str]] = {
        "en": {"name": name_en, "blurb": _truncate(blurb_en, 160)},
    }
    use_live = force_llm or (os.environ.get("AMP_NICHE_I18N_LLM") or "").strip() in (
        "1",
        "true",
        "yes",
    )
    for lang in UI_LANGS:
        if lang == "en":
            continue
        title = translate_title(name_en, lang)
        if use_live and title == name_en:
            title = _translate_title_live(name_en, lang)
        out[lang] = {
            "name": title,
            "blurb": translate_blurb(blurb_en, lang),
        }
    upsert_i18n(niche_id, out)
    return out


def localized_pair(name_en: str, blurb_en: str, lang: str) -> Tuple[str, str]:
    return translate_title(name_en, lang), translate_blurb(blurb_en, lang)
