"""Script Quality Gate Agent — ensures high-retention, information-dense, human-tone scripts.

Fixes identified from live testing (Package 006 Humanoid Robot):
1. Weak / abrupt hooks (e.g. 11 words starting abruptly, salam dangling at the end)
2. Low information density (e.g. 110 words across 70 seconds — empty platitudes)
3. Robotic monotone dialogue (4-5 disconnected textbook statements)
4. Missing core premise / purpose

This agent gates Stage 1 generation before any downstream media or voice production.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

# Minimum acceptable word counts by video type
MIN_WORDS_SHORT = 130      # For ~60-75s short: at least 130 words (target 150-200)
OPTIMAL_WORDS_SHORT = 160
MIN_WORDS_LONG = 500       # For ~240-300s long: at least 500 words (target 600-800)

# Generic / weak opening markers in Bengali
GENERIC_BN_HOOKS = (
    r"আজকে\s*আমরা",
    r"আজকের\s*ভিডিওতে",
    r"এই\s*ভিডিওতে",
    r"স্বাগতম\s*আমাদের\s*চ্যানেলে",
    r"হ্যালো\s*বন্ধুরা",
    r"কেমন\s*আছেন\s*সবাই",
    r"চলুন\s*শুরু\s*করা\s*যাক",
    r"দেরি\s*না\s*করে",
)

# High-impact curiosity / hook markers in Bengali
HIGH_IMPACT_BN_CUES = (
    r"জানেন\s*কি",
    r"ভাবতে\s*পারেন",
    r"চমকে\s*যাবেন",
    r"ইতিহাসে\s*প্রথম",
    r"সত্যিটা\s*কী",
    r"পুরোপুরি\s*প্রস্তুত",
    r"ভয়ংকর",
    r"অবিশ্বাস্য",
    r"বদলে\s*দিচ্ছে",
    r"আসল\s*রহস্য",
    r"সবচেয়ে\s*বড়",
    r"এমন\s*একটি",
    r"\?",
    r"\!",
)

def _normalize_bn_text(text: str) -> str:
    """Normalize decomposed Bengali unicode characters (e.g. য় vs য়, ড় vs ড়, etc.)."""
    if not text:
        return ""
    t = text.replace("\u09AF\u09BC", "\u09DF")  # য়
    t = t.replace("\u09A1\u09BC", "\u09DC")  # ড়
    t = t.replace("\u09A2\u09BC", "\u09DD")  # ঢ়
    return t


# Conversational connective words in Bengali (signs of human conversational flow)
CONVERSATIONAL_MARKERS = (
    r"আসলে",
    r"কিন্তু",
    r"তবে",
    r"জানেন\s*তো",
    r"সোজা\s*কথা[য়য়]",
    r"সহজ\s*কথা[য়য়]",
    r"বাস্তবে",
    r"সবচেয়ে\s*মজার",
    r"সবচেয়ে\s*মজার",
    r"সবচেয়ে\s*অদ্ভুত",
    r"সবচেয়ে\s*অদ্ভুত",
    r"সবচেয়ে\s*(বড়|আশ্চর্যজনক|রহস্যময়|রহস্যময়)",
    r"সবচেয়ে\s*(বড়|আশ্চর্যজনক|রহস্যময়|রহস্যময়)",
    r"এখানেই\s*শেষ\s*ন[য়য়]",
    r"এখানেই\s*আসল",
    r"আর\s*এখানেই",
    r"এবার\s*ভাবুন",
    r"একটু\s*ভেবে\s*দেখুন",
    r"একটু\s*ভাবুন",
    r"একবার\s*ভাবুন",
    r"এক\s*মুহূর্তের\s*জন্য",
    r"কল্পনা\s*করুন",
    r"শুনতে\s*(সহজ|অবিশ্বাস্য|অবাক|অদ্ভুত|কাল্পনিক|কল্পবিজ্ঞান)",
    r"সত্যি\s*বলতে",
    r"এর\s*পেছনে",
    r"এর\s*কারণ",
    r"আসল\s*টুইস্ট",
    r"খেয়াল\s*করলে",
    r"খেয়াল\s*করলে",
    r"এর\s*মানে\s*কী",
    r"ঠিক\s*শুনছেন",
    r"এমনকি",
    r"অথচ",
    r"বলা\s*যা[য়য়]",
)

# Storytelling, visual analogies, and mental movie markers in Bengali
STORYTELLING_ANALOGY_MARKERS = (
    r"ভাবুন\s*তো",
    r"একটু\s*ভেবে\s*দেখুন",
    r"একটু\s*ভাবুন",
    r"যেমন",
    r"যেন",
    r"ঠিক\s*যেন",
    r"এক\s*চুলে",
    r"চোখের\s*পলকে",
    r"এক\s*নিমেষে",
    r"কাঁচা\s*ডিম",
    r"তুলনায়",
    r"তুলনা\s*করলে",
    r"সোজা\s*কথায়",
    r"সহজ\s*কথায়",
    r"সহজ\s*ভাষায়",
    r"আসল\s*রহস্য",
    r"আসল\s*কারণ",
    r"এর\s*মানে\s*কী",
    r"কেন\s*গুরুত্বপূর্ণ",
    r"চরম\s*চ্যালেঞ্জ",
    r"অভাবনীয়",
    r"চমকে\s*যাওয়ার\s*মতো",
    r"নিজের\s*চোখকেই",
    r"কল্পনা\s*করুন",
    r"স্বপ্নেও\s*ভাবেননি",
    r"পানির\s*মতো",
    r"পাহাড়ের\s*মতো",
    r"ছোট্ট\s*একটি",
    r"বিশাল\s*একটি",
    r"হাতের\s*তালুর",
    r"ফুটবল\s*(মাঠ|স্টেডিয়াম|স্টেডিয়াম)",
    r"কফির\s*কাপ",
    r"চামচ",
    r"উদাহরণস্বরূপ",
    r"মতো\s*সহজ",
    r"মতোই\s*অদ্ভুত",
    r"জেট|বিমান|রকেট|গাড়ি|ট্রাক",
    r"হাতি|তিমি|ডাইনোসর",
    r"সমান",
    r"গুণ\s*(বেশি|কম|বড়|ভারী)",
    r"চেয়েও\s*(বেশি|বড়|দ্রুত|ভারী)",
    r"টুইস্ট|টুইস্টটা",
    r"অবিশ্বাস্য\s*হলেও",
    r"আশ্চর্যজনক\s*বিষয়",
    r"সবচেয়ে\s*অদ্ভুত\s*বিষয়",
    r"সবচেয়ে\s*অদ্ভুত\s*বিষয়",
    r"বাস্তবে\s*যদি",
)

# Dry technical spec / datasheet dump patterns
DRY_SPEC_PATTERNS = (
    r"\d+\s*ডিগ্রি",
    r"\d+\s*(কেজি|গ্রাম|টন)",
    r"\d+\s*(মিলিমিটার|সেন্টিমিটার|মিটার)",
    r"\d+\s*(গিগাহার্টজ|মেগাপিক্সেল|মেগাওয়াট|কিলোওয়াট|ভোল্ট)",
)

# High stakes contrast hooks in Bengali
CONTRAST_HOOK_PATTERNS = (
    r"কিন্তু.*(কেউ\s*নেই|মানুষ\s*নেই|অসম্ভব|উল্টো|স্তব্ধ|রহস্য)",
    r"কোটি|হাজার|বিলিয়ন",
    r"প্রথমবার|ইতিহাসে|অভাবনীয়|স্তব্ধ|উল্টে\s*দিল",
)

# Greeting patterns in Bengali
GREETING_PATTERNS = (
    r"আসসালামু\s*আলাইকুম",
    r"সালাম",
    r"নমস্কার",
    r"আদাব",
)

OUTRO_GREETING_PATTERNS = (
    r"আল্লাহ\s*হাফেজ",
    r"খোদা\s*হাফেজ",
    r"দেখা\s*হবে\s*পরবর্তী",
    r"ভালো\s*থাকবেন",
    r"বিদায়",
)


def _count_words(text: str) -> int:
    """Accurate word count for mixed Bengali and English text."""
    if not text:
        return 0
    words = re.findall(r"[\u0980-\u09FF\w]+", text)
    return len(words)


count_bengali_words = _count_words


def evaluate_hook_quality(
    shot_1: Dict[str, Any] | str,
    *,
    topic: str = "",
) -> Dict[str, Any]:
    """Evaluate the opening shot (Hook) for punchiness, salam placement, and length."""
    if isinstance(shot_1, str):
        vo = shot_1.strip()
    else:
        vo = str(shot_1.get("voiceover_script") or "").strip()
    words_list = re.findall(r"[\u0980-\u09FF\w]+", vo)
    words = len(words_list)
    issues: List[str] = []
    score = 1.0

    if not vo:
        return {
            "ok": False,
            "score": 0.0,
            "issues": ["empty_shot_1_voiceover"],
            "reason": "Shot 1 has no voiceover text",
        }

    # 1. Word count check for hook (should be 15-28 words for a 6-8s shot)
    if words < 12:
        issues.append(f"দুর্বল হুক (hook_too_short): only {words} words (minimum 14 words needed for high retention)")
        score -= 0.35
    elif words < 15:
        issues.append(f"দুর্বল হুক (hook_sparse): {words} words (recommended 16-24 words)")
        score -= 0.15

    # 2. Check for weak generic openers
    for pat in GENERIC_BN_HOOKS:
        if re.search(pat, vo[:40], re.I):
            issues.append(f"গতানুগতিক শুরুর বাক্য (weak_generic_opening_phrase): matches {pat}")
            score -= 0.30
            break

    # 3. Check for awkward greeting placement: only flag if greeting is isolated without a rich hook
    has_any_greeting = any(re.search(pat, vo, re.I) for pat in GREETING_PATTERNS)
    # A greeting is misplaced only if the shot lacks any substantive hook before it (e.g. fewer than 10 words before greeting)
    if has_any_greeting and words < 12:
        issues.append(
            "ভুল জায়গায় সালাম (isolated_greeting): greeting is isolated without a rich hook punchline"
        )
        score -= 0.20

    # 4. Check for lame cliché question opener without dramatic contrast
    is_lame_cliche_q = bool(re.search(r"^(আসসালামু\s*আলাইকুম[!\s]+)?(আপনি\s*কি\s*জানেন|জানেন\s*কি|আজকে\s*আমরা\s*জানব)", vo.strip(), re.I))
    has_contrast = any(re.search(pat, vo, re.I) for pat in CONTRAST_HOOK_PATTERNS)
    if is_lame_cliche_q and not has_contrast:
        issues.append(
            "দুর্বল ও গতানুগতিক প্রশ্ন হুক (lame_cliche_question_opener): 'আপনি কি জানেন' জাতীয় দুর্বল ভূমিকা বর্জন করে চাঞ্চল্যকর বৈপরীত্য বা নাটকীয় তথ্য দিয়ে শুরু করুন"
        )
        score -= 0.25

    # 5. Check for curiosity / high stakes marker
    has_curiosity = any(re.search(pat, vo, re.I) for pat in HIGH_IMPACT_BN_CUES) or has_contrast
    if not has_curiosity and "?" not in vo and "!" not in vo:
        issues.append("কৌতূহলোদ্দীপক উপাদানের অভাব (hook_lacks_curiosity_or_stakes): missing provocative question, contrast, or curiosity gap")
        score -= 0.20

    # 6. Front-loaded curiosity check: The first 25 words or first 130 chars MUST contain an active curiosity trigger, paradox, or question
    front_raw = vo[:130]
    front_words = " ".join(words_list[:25])
    front_has_curiosity = (
        any(re.search(pat, front_words, re.I) for pat in HIGH_IMPACT_BN_CUES)
        or any(re.search(pat, front_words, re.I) for pat in CONTRAST_HOOK_PATTERNS)
        or ("?" in front_raw or "!" in front_raw)
        or any(k in front_words for k in (
            "অসম্ভব", "রহস্য", "চমকে", "অবিশ্বাস্য", "কেন", "কীভাবে", "কখনো", "কল্পনা",
            "যদি", "আসল", "গোপন", "বিস্ময়কর", "বিপ্লব", "সত্যি", "ভাবতে", "বরফ", "রক্ত",
            "অন্ধকার", "শীতল", "ভয়ঙ্কর", "বিশাল", "অদ্ভুত"
        ))
    )
    if not front_has_curiosity:
        issues.append(
            "হুকের শুরুতে কৌতূহলের অভাব (hook_lacks_frontloaded_curiosity): প্রথম ৩ সেকেন্ডেই দর্শককে চমকে দেওয়ার মতো কৌতূহল, প্যারাডক্স বা প্রশ্ন নেই"
        )
        score -= 0.25

    final_score = max(0.0, min(1.0, score))
    return {
        "ok": final_score >= 0.68 and ("hook_too_short" not in " ".join(issues)),
        "score": round(final_score, 3),
        "word_count": words,
        "issues": issues,
        "has_greeting": has_any_greeting,
        "has_curiosity": has_curiosity,
        "has_front_curiosity": front_has_curiosity,
    }


def evaluate_information_density(
    scenes: Sequence[Dict[str, Any]],
    video_type: str = "short",
    *,
    target_duration: int = 70,
) -> Dict[str, Any]:
    """Verify that the script contains deep substance, factual specifics, and sufficient words."""
    is_short = str(video_type).lower() in ("short", "shorts", "reel")
    min_total_words = MIN_WORDS_SHORT if is_short else MIN_WORDS_LONG
    optimal_words = OPTIMAL_WORDS_SHORT if is_short else 650

    total_words = 0
    shot_words: List[Dict[str, Any]] = []
    thin_shots: List[int] = []

    for sc in scenes:
        n = int(sc.get("shot_number") or len(shot_words) + 1)
        dur = float(sc.get("shot_duration_seconds") or 6.0)
        vo = str(sc.get("voiceover_script") or "").strip()
        cnt = _count_words(vo)
        total_words += cnt
        shot_words.append({"shot": n, "duration": dur, "words": cnt})

        # A shot of 6s+ should have at least 12 words in conversational Bengali
        if dur >= 5.5 and cnt < 11:
            thin_shots.append(n)

    issues: List[str] = []
    score = 1.0

    # 1. Total word count check
    if total_words < (min_total_words - 20):
        issues.append(f"শব্দ সংখ্যা অত্যন্ত কম (critically_low_word_count): {total_words} words across {target_duration}s (minimum {min_total_words} words required)")
        score -= 0.50
    elif total_words < min_total_words:
        issues.append(f"কম শব্দ সংখ্যা (low_word_count): {total_words} words (recommended {optimal_words}+ words)")
        score -= 0.25

    # 2. Too many thin shots
    if thin_shots:
        ratio = len(thin_shots) / max(1, len(scenes))
        if ratio > 0.3:
            issues.append(f"খুব ছোট শট (too_many_thin_shots): shots {thin_shots} have under 11 words each ({ratio:.0%} of script)")
            score -= 0.30
        else:
            issues.append(f"খুব ছোট শট (sparse_shots): shots {thin_shots} have fewer than 11 words")
            score -= 0.15

    # 3. Check for factual specifics (numbers, English terms, technical words)
    combined_text = _normalize_bn_text(" ".join(str(s.get("voiceover_script") or "") for s in scenes))
    numbers_present = bool(re.search(r"\d+|[০-৯]+|(এক|দুই|তিন|চার|পাঁচ|ছয়|সাত|আট|নয়|দশ|শ|হাজার|কোটি|লাখ)", combined_text))
    named_entities_present = bool(re.search(r"[A-Z][a-zA-Z]+|[০-৯]+%|\b(AI|GPT|BMW|Tesla|Figure|Robot|NASA|MIT)\b", combined_text, re.I))
    concrete_terms_present = bool(re.search(r"(লিটার|কিলোমিটার|মিটার|ডিগ্রি|শতাংশ|গ্রাম|কেজি|গবেষক|বিজ্ঞানী|ল্যাব|বিশ্ববিদ্যালয়|মডেল|কোম্পানি|যন্ত্র|কার্তুজ|প্রযুক্তি|স্ফটিক|অণু|ব্যাটারি)", combined_text))

    if not numbers_present and not named_entities_present and not concrete_terms_present:
        issues.append("বাস্তব তথ্যের অভাব (lacks_concrete_facts): script has zero numbers, statistics, or named technological specifics")
        score -= 0.20

    final_score = max(0.0, min(1.0, score))
    return {
        "ok": final_score >= 0.65 and ("critically_low_word_count" not in " ".join(issues)),
        "score": round(final_score, 3),
        "total_words": total_words,
        "min_required": min_total_words,
        "thin_shots": thin_shots,
        "shot_breakdown": shot_words,
        "issues": issues,
    }


def evaluate_human_tone_and_flow(scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Check for conversational markers and penalize repetitive robotic sentence starters."""
    issues: List[str] = []
    score = 1.0

    combined_text = _normalize_bn_text(" ".join(str(s.get("voiceover_script") or "") for s in scenes))
    conversational_hits = sum(1 for pat in CONVERSATIONAL_MARKERS if re.search(pat, combined_text, re.I))

    if conversational_hits < 2:
        issues.append(f"robotic_monotone_flow: found only {conversational_hits} conversational connective phrases")
        score -= 0.25

    # Detect repetitive sentence starters (e.g. starts 3+ sentences with "এটা...", "তাই...", etc.)
    starters = []
    for sc in scenes:
        vo = str(sc.get("voiceover_script") or "").strip()
        words = vo.split()
        if words:
            first = words[0].strip("—-,.")
            if len(first) >= 2:
                starters.append(first)

    # Check for excessive repetition of the same opening word
    starter_counts = {}
    for st in starters:
        starter_counts[st] = starter_counts.get(st, 0) + 1
    repetitive = [k for k, v in starter_counts.items() if v >= 3 and k in ("এটা", "তাই", "বাস্তবতা", "এই", "এখানে")]
    if repetitive:
        issues.append(f"repetitive_robotic_sentence_starters: multiple sentences start with {repetitive}")
        score -= 0.20

    final_score = max(0.0, min(1.0, score))
    return {
        "ok": final_score >= 0.70,
        "score": round(final_score, 3),
        "conversational_hits": conversational_hits,
        "issues": issues,
    }


def evaluate_structure_and_outro(scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify presence of intelligent audience engagement question and warm closing CTA."""
    issues: List[str] = []
    score = 1.0

    if not scenes:
        return {"ok": False, "score": 0.0, "issues": ["no_scenes"]}

    # Penultimate or late shot should have an audience question
    late_shots = scenes[-3:-1] if len(scenes) >= 4 else scenes[-1:]
    late_text = " ".join(str(s.get("voiceover_script") or "") for s in late_shots)
    has_question = ("?" in late_text or "কমেন্টে" in late_text or "উত্তর" in late_text or "মতামত" in late_text)

    if not has_question:
        issues.append("missing_audience_question_or_quiz: late shots lack an engaging question asking viewers to comment")
        score -= 0.25

    # Last shot should have CTA + closing greeting
    last_shot = scenes[-1]
    last_vo = str(last_shot.get("voiceover_script") or "")
    has_cta = any(k in last_vo for k in ("সাবস্ক্রাইব", "লাইক", "শেয়ার", "শেয়ার", "ফলো"))
    has_closing_greeting = any(re.search(pat, last_vo, re.I) for pat in OUTRO_GREETING_PATTERNS) or any(re.search(pat, last_vo, re.I) for pat in GREETING_PATTERNS)

    if not has_cta:
        issues.append("missing_cta: final shot lacks like/share/subscribe call to action")
        score -= 0.20

    if not has_closing_greeting:
        issues.append("missing_closing_greeting: final shot lacks warm closing farewell/greeting (e.g. আল্লাহ হাফেজ)")
        score -= 0.15

    final_score = max(0.0, min(1.0, score))
    return {
        "ok": final_score >= 0.70,
        "score": round(final_score, 3),
        "has_question": has_question,
        "has_cta": has_cta,
        "has_closing_greeting": has_closing_greeting,
        "issues": issues,
    }


def evaluate_storytelling_and_presentation(scenes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify that information is presented simply, visually, and engagingly using analogies,
    and detect dry robotic datasheet dumping.
    """
    issues: List[str] = []
    score = 1.0

    if not scenes:
        return {"ok": False, "score": 0.0, "issues": ["no_scenes"]}

    combined_text = " ".join(str(s.get("voiceover_script") or "") for s in scenes)

    # 1. Check for everyday visual analogies and simplified mental movie explanations
    analogy_hits = sum(1 for pat in STORYTELLING_ANALOGY_MARKERS if re.search(pat, combined_text, re.I))
    if analogy_hits < 1 and len(scenes) >= 6:
        issues.append(
            "সহজবোধ্য চাক্ষুষ উপমার অভাব (lacks_storytelling_analogies): তথ্যের সাথে কোনো চাক্ষুষ উপমা বা বাস্তব তুলনা নেই, ফলে তথ্য কঠিন শোনাচ্ছে"
        )
        score -= 0.30
    elif analogy_hits < 2 and len(scenes) >= 6:
        issues.append(
            "চাক্ষুষ উপমার স্বল্পতা (sparse_storytelling_analogies): তথ্যের গভীরতার তুলনায় বাস্তব চাক্ষুষ উপমা মাত্র ১টি পাওয়া গেছে, অন্তত ২টি উপমা ব্যবহার করুন"
        )
        score -= 0.15

    # 2. Anti-datasheet detection: check if consecutive shots dump specs without context
    spec_dump_consecutive = 0
    max_consecutive_spec = 0
    for sc in scenes:
        vo = str(sc.get("voiceover_script") or "")
        has_spec = any(re.search(pat, vo, re.I) for pat in DRY_SPEC_PATTERNS)
        if has_spec:
            spec_dump_consecutive += 1
            max_consecutive_spec = max(max_consecutive_spec, spec_dump_consecutive)
        else:
            spec_dump_consecutive = 0

    if max_consecutive_spec >= 2:
        issues.append(
            f"রোবোটিক ডেটাশিট ডাম্পিং (dry_datasheet_dumping): {max_consecutive_spec}টি ধারাবাহিক শটে শুষ্ক স্পেসিফিকেশন মুখস্থ বলার মতো উপস্থাপন করা হয়েছে"
        )
        score -= 0.25

    # 3. Mid-roll retention hooks check (shots 3 to 7)
    if len(scenes) >= 6:
        mid_scenes = scenes[2:min(7, len(scenes) - 1)]
        mid_text = " ".join(str(s.get("voiceover_script") or "") for s in mid_scenes)
        has_mid_hook = any(k in mid_text for k in ("রহস্য", "চমক", "আসল", "প্রশ্ন", "গোপন", "কিন্তু", "কেন", "বাধা", "অবিশ্বাস্য", "তবে", "রোমাঞ্চকর", "ভাবুন", "বিপ্লব", "চ্যালেঞ্জ", "সত্যি", "গবেষণা"))
        if not has_mid_hook:
            issues.append(
                "মাঝপথে কৌতূহলের ঘাটতি (lacks_mid_roll_retention_hook): ৩ থেকে ৭ নম্বর শটের মধ্যে দর্শক ধরে রাখার মতো রহস্য বা আকর্ষণীয় প্রশ্ন নেই"
            )
            score -= 0.15

    final_score = max(0.0, min(1.0, score))
    return {
        "ok": final_score >= 0.70,
        "score": round(final_score, 3),
        "analogy_hits": analogy_hits,
        "max_consecutive_specs": max_consecutive_spec,
        "issues": issues,
    }


def evaluate_script_quality(
    payload: Dict[str, Any],
    *,
    video_type: str = "short",
) -> Dict[str, Any]:
    """Comprehensive Agent Quality Gate for Stage 1 scripts.

    Returns:
      ok: bool (True if passes all quality standards)
      score: float (0.0 to 1.0)
      issues: list of all detected flaws
      action: "accept" | "rewrite_and_regenerate"
      rewrite_feedback: human-readable Bengali prompt directives for the LLM retry
    """
    scenes = payload.get("script_scenes") or []
    if not scenes or not isinstance(scenes, list):
        return {
            "ok": False,
            "score": 0.0,
            "action": "rewrite_and_regenerate",
            "issues": ["empty_or_invalid_script_scenes"],
            "rewrite_feedback": "স্ক্রিপ্টে কোনো দৃশ্য পাওয়া যায়নি। সম্পূর্ণ শট-বাই-শট JSON প্রদান করুন।",
        }

    meta = payload.get("seo_metadata") or {}
    topic = str(meta.get("selected_topic") or "")
    dur = int(meta.get("target_duration_seconds") or (70 if video_type == "short" else 270))

    # Evaluate all dimensions
    hook_eval = evaluate_hook_quality(scenes[0], topic=topic)
    density_eval = evaluate_information_density(scenes, video_type=video_type, target_duration=dur)
    storytelling_eval = evaluate_storytelling_and_presentation(scenes)
    tone_eval = evaluate_human_tone_and_flow(scenes)
    struct_eval = evaluate_structure_and_outro(scenes)

    # Weighted aggregate score: Hook (25%), Density (30%), Storytelling (25%), Tone (10%), Structure (10%)
    composite_score = (
        0.25 * float(hook_eval.get("score") or 0)
        + 0.30 * float(density_eval.get("score") or 0)
        + 0.25 * float(storytelling_eval.get("score") or 0)
        + 0.10 * float(tone_eval.get("score") or 0)
        + 0.10 * float(struct_eval.get("score") or 0)
    )

    all_issues = (
        hook_eval.get("issues", [])
        + density_eval.get("issues", [])
        + storytelling_eval.get("issues", [])
        + tone_eval.get("issues", [])
        + struct_eval.get("issues", [])
    )

    # Hard rejection conditions:
    # 1. Hook too short / critically weak
    # 2. Critically low word count (empty script)
    # 3. Overall composite score < 0.70
    hard_fail = (
        not hook_eval.get("ok")
        or not density_eval.get("ok")
        or composite_score < 0.68
    )

    # Build actionable feedback for LLM retry if failed
    feedback_points: List[str] = []
    if not hook_eval.get("ok") or hook_eval.get("issues"):
        feedback_points.append(
            "১. শুরুর হুক অনেক বেশি আকর্ষণীয় ও কৌতূহলোদ্দীপক করুন: প্রথম শটেই অন্তত ১৫-২৫ শব্দের শক্তিশালী বৈপরীত্য বা চাঞ্চল্যকর প্রশ্ন দিয়ে শুরু করুন। শুভেচ্ছা/সালাম শুরুতে স্বাভাবিকভাবে দিন, বাক্যের শেষে জোর করে ঝুলিয়ে রাখবেন না।"
        )
    if not density_eval.get("ok") or density_eval.get("issues"):
        req_words = density_eval.get("min_required", 140)
        feedback_points.append(
            f"২. তথ্যের গভীরতা বাড়ান (Information Depth): সাধারণ ফাঁকা বুলি বাদ দিয়ে আসল কোম্পানি, মডেলের নাম, বাস্তব ঘটনা, পরিসংখ্যান ও সুনির্দিষ্ট কাজের বর্ণনা দিন। পুরো স্ক্রিপ্টে মোট অন্তত {req_words}–১৮০ শব্দ থাকতে হবে (প্রতি ৫-৮ সেকেন্ডের শটে ১৫-২৫ শব্দ)।"
        )
    if not storytelling_eval.get("ok") or storytelling_eval.get("issues"):
        feedback_points.append(
            "৩. তথ্যকে সহজবোধ্য ও আকর্ষণীয় উপমায় উপস্থাপন করুন: শুষ্ক ডেটাশিট মুখস্থ বলার মতো নম্বর বা স্পেসিফিকেশন বলবেন না। সাধারণ দর্শকের চাক্ষুষভাবে বোঝার মতো বাস্তব উপমা (যেমন: 'কাঁচা ডিম না ভেঙে তুলে নেওয়া', 'চোখের পলকে হাজার বার') ব্যবহার করুন এবং মাঝের শটগুলোতে কৌতূহল বজায় রাখুন।"
        )
    if not tone_eval.get("ok") or tone_eval.get("issues"):
        feedback_points.append(
            "৩. রোবটিক ভাব দূর করে মানুষের মতো প্রাণবন্ত কথ্য ভাষা ব্যবহার করুন: প্রতিটি বাক্য যেন আগের বাক্যের সাথে একটি গল্পের মতো যুক্ত থাকে। বইয়ের মতো শুকনো বক্তব্যের বদলে প্রাঞ্জল কথ্য ভঙ্গি ('আসলে', 'ভাবতে পারেন?', 'সোজা কথায়') বজায় রাখুন।"
        )
    if not struct_eval.get("ok") or struct_eval.get("issues"):
        feedback_points.append(
            "৪. শেষের দিকে বুদ্ধিদীপ্ত দর্শক প্রশ্ন/কুইজ এবং ভিডিওর শেষে শেয়ার/সাবস্ক্রাইব করার সুন্দর আহ্বান ও বিদায়ী সালাম অন্তর্ভুক্ত করুন।"
        )

    rewrite_feedback = "\n".join(feedback_points)

    result = {
        "ok": not hard_fail,
        "score": round(composite_score, 3),
        "action": "accept" if not hard_fail else "rewrite_and_regenerate",
        "issues": all_issues,
        "breakdown": {
            "hook_score": round(float(hook_eval.get("score") or 0), 3),
            "density_score": round(float(density_eval.get("score") or 0), 3),
            "storytelling_score": round(float(storytelling_eval.get("score") or 0), 3),
            "human_tone_score": round(float(tone_eval.get("score") or 0), 3),
            "structure_score": round(float(struct_eval.get("score") or 0), 3),
        },
        "evaluations": {
            "hook": hook_eval,
            "density": density_eval,
            "storytelling": storytelling_eval,
            "tone": tone_eval,
            "structure": struct_eval,
        },
        "rewrite_feedback": rewrite_feedback,
    }

    if hard_fail:
        logger.warning(
            "ScriptQualityGate REJECTED script (score=%.2f): %s",
            composite_score,
            all_issues,
        )
    else:
        logger.info(
            "ScriptQualityGate ACCEPTED script (score=%.2f, words=%s)",
            composite_score,
            density_eval.get("total_words"),
        )

    return result
