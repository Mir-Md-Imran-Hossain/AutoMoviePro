"""Naturalness preflight — deterministic heuristics (PASS/BLOCK/UNKNOWN)."""
from __future__ import annotations

import re
from typing import Any


def naturalness_preflight(dialogue_text: str) -> dict[str, Any]:
    """
    Deterministic checks for common artificial dialogue problems.
    Does NOT claim human naturalness mathematically.
    """
    text = (dialogue_text or "").strip()
    issues: list[str] = []
    status = "PASS"

    if not text:
        return {"status": "BLOCK", "issues": ["empty_dialogue"], "method": "DETERMINISTIC"}

    # Robotic instruction leakage
    leak_pats = [
        r"\bplease speak\b",
        r"\bssml\b",
        r"\btts\b",
        r"\bpronounce as\b.*\bipa\b",
        r"\[emphasis\]",
        r"<speak>",
    ]
    for pat in leak_pats:
        if re.search(pat, text, re.I):
            issues.append(f"instruction_leakage:{pat}")

    _YEARISH = {
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "nineteen",
        "eighteen",
        "seventeen",
        "sixteen",
        "fifteen",
        "fourteen",
        "thirteen",
        "twelve",
        "eleven",
        "ten",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "zero",
        "oh",
    }

    words = re.findall(r"[A-Za-z0-9']+", text)
    if len(words) >= 4:
        for i in range(len(words) - 1):
            a = words[i].lower()
            b = words[i + 1].lower()
            if a == b and len(a) > 2:
                # Allow year speech: "twenty twenty-six" / "twenty twenty"
                if a in _YEARISH:
                    continue
                issues.append(f"duplicated_word:{words[i]}")
                break
        # Repeated phrase (4+ word ngram twice) — 3-grams false-fire on technical
        # entity names (e.g. "jwst miri mid" in documentary narration).
        for n in (4, 5):
            if len(words) >= n * 2:
                grams = [" ".join(words[i : i + n]).lower() for i in range(len(words) - n + 1)]
                seen = set()
                for g in grams:
                    if g in seen:
                        issues.append(f"repeated_phrase:{g}")
                        break
                    seen.add(g)

    # True sentence-length gate (not total narration length). Master/localize
    # scripts are multi-sentence and routinely exceed 600 chars overall.
    for sent in re.split(r"[.!?]+", text):
        chunk = sent.strip()
        if len(chunk) > 600:
            issues.append("excessive_sentence_length")
            break
    # Still block pathological single-blob dialogue with almost no sentence breaks.
    if len(text) > 2500 and len(re.findall(r"[.!?]", text)) < 2:
        if "excessive_sentence_length" not in issues:
            issues.append("excessive_sentence_length")

    # Broken boundaries: many ellipses / impossible pause markers
    if text.count("...") > 5 or text.count("—") > 8:
        issues.append("excessive_pause_markers")
    if re.search(r"\[\s*pause\s+\d{4,}", text, re.I):
        issues.append("impossible_pause_marker")

    # Unnatural punctuation clusters
    if re.search(r"[!?]{4,}", text) or re.search(r",{3,}", text):
        issues.append("unnatural_punctuation")

    # Emphasis marker spam
    if text.count("*") > 10 or text.count("_") > 12:
        issues.append("excessive_emphasis_markers")

    if issues:
        # Hard blocks for leakage / impossible markers; others BLOCK for prevention
        status = "BLOCK"

    return {
        "status": status,
        "issues": issues,
        "method": "DETERMINISTIC",
        "claim": "naturalness_heuristic_not_human_guarantee",
    }
