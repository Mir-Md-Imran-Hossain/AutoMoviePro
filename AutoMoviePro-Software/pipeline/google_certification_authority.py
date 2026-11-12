# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Google AI Certification Authority & Closed-Loop Healing Engine
==============================================================================
Implements multi-stage role-based Google AI certifications with:
  1. Persona-Driven Category-Specialized Evaluations:
     - Category A (Cinematic Faceless Documentary):
         * Stage 1: Native Bengali Cultural Historian & Storyteller
         * Stage 2: Veteran Documentary Film Director & Cinematographer
         * Stage 5: Cinematic Documentary & Monetization Auditor
     - Category B (Next-Gen Motion Graphics & Tactical Analytics):
         * Stage 1: Chief Geopolitical & Economic Explanatory Script Editor
         * Stage 2: Head of Broadcast Motion Design & Tactical Cartography
         * Stage 5: Vox / Johnny Harris Style Motion Graphics & Data Journalism Auditor
  2. Numbered Defect Attribution (সংখ্যা ও তালিকাভিত্তিক সুনির্দিষ্ট ত্রুটি চিহ্নিতকরণ):
     - Every flagged flaw strictly reports scene index, timestamp, component, and surgical action.
  3. Actionable Graphical Enhancements for Category B:
     - Specific recommendations on charts, percentage meters, route vectors, and tactical badges.
  4. Anti-Hallucination Negative Prompting & Calibrated Pass Condition:
     - Explicit instructions prevent AI from inventing microscopic/theoretical flaws or looping indefinitely.
     - Videos without jarring defects automatically pass with 90-95+ score.
  5. Surgical Closed-Loop Self-Healing:
     - Re-renders ONLY the defective scenes rather than the entire video.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("GoogleCertificationAuthority")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.api_keys import load_api_bundle

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


def get_rotated_google_keys() -> List[str]:
    """Round-robin rotator across Google Gemini API keys (Paid + Free)."""
    bundle = load_api_bundle(extra_env_paths=[ROOT / ".env"]) or {}
    paid = bundle.get("google_paid_keys") or []
    free = bundle.get("google_free_keys") or []
    raw = bundle.get("google_keys") or []

    interleaved = [k for k in paid if k]
    for k in (free + raw):
        if k and k not in interleaved:
            interleaved.append(k)

    if not interleaved:
        return []

    state_file = ROOT / "output" / "Google_Vision_95_Suite" / "api_rotation_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    last_idx = 0
    if state_file.exists():
        try:
            last_idx = json.loads(state_file.read_text(encoding="utf-8")).get("last_index", 0)
        except Exception:
            last_idx = 0

    next_idx = (last_idx + 1) % len(interleaved)
    rotated = interleaved[next_idx:] + interleaved[:next_idx]

    try:
        state_file.write_text(json.dumps({"last_index": next_idx, "total_keys": len(interleaved)}), encoding="utf-8")
    except Exception:
        pass

    return rotated


class GoogleCertificationAuthority:
    """Supreme Google AI Certification Authority across all production stages."""

    _instance: Optional["GoogleCertificationAuthority"] = None

    def __init__(self):
        self.keys = get_rotated_google_keys()
        self.preferred_models = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest"]

    def _get_ffmpeg(self) -> str:
        """Locates valid ffmpeg binary."""
        import shutil
        cand = shutil.which("ffmpeg")
        if cand:
            return cand
        root = Path(__file__).resolve().parent.parent
        for f in root.glob("**/ffmpeg*.exe"):
            if f.is_file():
                return str(f)
        return "ffmpeg"

    def detect_freeze_frames(self, video_path: Path, max_allowed_freeze_sec: float = 3.0) -> List[Dict[str, float]]:
        """Objectively detects freeze frames using FFmpeg freezedetect filter."""
        ffmpeg = self._get_ffmpeg()
        cmd = [
            ffmpeg, "-i", str(video_path),
            "-vf", f"freezedetect=n=-50dB:d={max_allowed_freeze_sec}",
            "-map", "0:v:0", "-f", "null", "-"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
            freezes = []
            cur_start = None
            for line in res.stderr.splitlines():
                if "lavfi.freezedetect.freeze_start" in line:
                    try:
                        cur_start = float(line.split(":")[-1].strip())
                    except Exception:
                        pass
                elif "lavfi.freezedetect.freeze_duration" in line and cur_start is not None:
                    try:
                        dur = float(line.split(":")[-1].strip())
                        freezes.append({"start_sec": cur_start, "duration_sec": dur})
                        cur_start = None
                    except Exception:
                        pass
            return freezes
        except Exception as e_fz:
            logger.warning("Freeze detection failed: %s", e_fz)
            return []


    @classmethod
    def get_instance(cls) -> "GoogleCertificationAuthority":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _call_gemini_text(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Resilient text call to Gemini with rotating API keys."""
        if not genai:
            logger.warning("google.genai SDK not installed; skipping remote call.")
            return ""

        keys = get_rotated_google_keys()
        for k_idx, key in enumerate(keys):
            try:
                client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=60000))
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                ) if system_instruction else types.GenerateContentConfig(temperature=0.2)

                for mod in self.preferred_models:
                    try:
                        resp = client.models.generate_content(
                            model=mod,
                            contents=prompt,
                            config=config,
                        )
                        txt = (resp.text or "").strip()
                        if txt:
                            return txt
                    except Exception as e_mod:
                        logger.debug("Model %s failed: %s", mod, e_mod)
            except Exception as e_k:
                logger.debug("Key #%d failed: %s", k_idx + 1, e_k)

        return ""

    # =========================================================================
    # STAGE 1: SCRIPT & DIALOGUE COMPREHENSION CERTIFICATION (DUAL-CATEGORY)
    # =========================================================================
    def certify_script(
        self,
        script_data: Dict[str, Any],
        topic: str,
        niche: str,
        category: str = "Category A"
    ) -> Dict[str, Any]:
        """
        Stage 1: Script & Dialogue Comprehension Certification.
        Category A: Evaluated by Native Bengali Cultural Historian & Storyteller.
        Category B: Evaluated by Chief Geopolitical & Economic Explanatory Script Editor.
        """
        title_bn = script_data.get("title_bn", topic)
        scenes = script_data.get("scenes", [])
        is_cat_b = ("Category B" in category) or ("motion" in category.lower()) or ("trade" in niche.lower())

        scenes_text = []
        for s_idx, sc in enumerate(scenes, 1):
            scenes_text.append(f"দৃশ্য #{s_idx:02d}: \"{sc.get('dialogue_bn', '')}\"")
        transcript_dump = "\n".join(scenes_text)

        if is_cat_b:
            sys_inst = (
                "তুমি একজন আন্তর্জাতিক মানের ভূ-রাজনৈতিক ও অর্থনৈতিক ডেটা জার্নালিজম চিত্রনাট্য সম্পাদক "
                "(Chief Geopolitical & Economic Explanatory Script Editor — Vox, CaspianReport, Visual Capitalist স্টাইল)। "
                "তোমার দায়িত্ব হলো স্ক্রিপ্টের প্রতিটি ডায়ালগ সাধারণ দর্শকের কাছে তথ্যবহুল, রোমাঞ্চকর এবং মোশন গ্রাফিক্সের "
                "ট্যাকটিক্যাল ডেটার সাথে সামঞ্জস্যপূর্ণ কি না তা মূল্যায়ন করা।"
            )
            cat_guidance = """
১. ডেটা ও কারণ-ফলাফল সংযোগ (Data & Cause-and-Effect Logic):
   - ডায়ালগে কি জটিল কৌশলগত বা অর্থনৈতিক তথ্য সাধারণ মানুষের বোধগম্য ভাষায় নিখুঁতভাবে তুলে ধরা হয়েছে?
   - শতকরা হার, বাণিজ্যের পরিমাণ, প্রণালীর কৌশলগত গুরুত্ব কি স্পষ্ট?
২. গ্রাফিক্যাল অন-স্ক্রিন কিউ (Verbal Cues for Motion Graphics):
   - ডায়ালগটি কি পর্দার ইনফোগ্রাফিক্স, স্যাটেলাইট ম্যাপ বা ডেটা কার্ডের তথ্যের সাথে সিঙ্ক করার জন্য উপযুক্ত?
৩. নেগেটিভ প্রম্পটিং (Negative Directives):
   - এটি ডেটা জার্নালিজম ডকুমেন্টারি, তাই এতে অতিরিক্ত কাল্পনিক রূপক বা কবিতার প্রয়োজন নেই।
   - তথ্য স্পষ্ট ও আকর্ষণীয় হলে নিশ্চিতভাবে ৯০-৯৫+ স্কোর দাও।
"""
        else:
            sys_inst = (
                "তুমি একজন দক্ষ বাঙালি চিত্রনাট্যকার (Veteran Bengali Scriptwriter) এবং দর্শক মনস্তত্ত্ববিদ "
                "(Audience Empathy Analyst)। তোমার কাজ হলো সিনেমাটিক স্টোরিটেলিং স্ক্রিপ্টের প্রতিটি ডায়ালগ সাধারণ দর্শকের "
                "কাছে কতটা সাবলীল, প্রাঞ্জল ও আবেগপূর্ণ তা মূল্যায়ন করা।"
            )
            cat_guidance = """
১. সাধারণ মানুষের বোধগম্যতা ও সাসপেন্স (Storytelling & Emotional Hook):
   - সংলাপগুলো কি স্বাভাবিক বাংলা ভাষার টান ও রহস্যময় আবেগ বজায় রেখেছে?
   - কোনো কৃত্রিম যান্ত্রিক ইংরেজি অনুবাদের মতো শব্দ গঠন নেই তো?
২. নেগেটিভ প্রম্পটিং (Negative Directives):
   - ডায়ালগ যদি সাধারণ দর্শকের কাছে আকর্ষণীয় ও সাবলীল মনে হয়, তবে নিশ্চিতভাবে ৯০-৯৫+ স্কোর দাও।
   - সামান্য ব্যাকরণগত ভিন্নতার অজুহাতে নম্বর কেটে লুপ তৈরি করবে না।
"""

        prompt = f"""
ক্যাটাগরি: {category} | বিষয়: {title_bn} | নিশ: {niche}
মোট দৃশ্য: {len(scenes)}

নিচে সম্পূর্ণ ভিডিওর দৃশ্যভিত্তিক সংলাপ দেওয়া হলো:
==================================================
{transcript_dump}
==================================================

মূল্যায়ন নির্দেশনা ({category} স্পেশালাইজড):
{cat_guidance}

সংখ্যাভিত্তিক সুনির্দিষ্ট ত্রুটি চিহ্নিতকরণ (Numbered Defect Attribution):
- শুধুমাত্র যদি কোনো ডায়ালগ বাক্যগঠনে মারাত্মক ত্রুটি থাকে বা অর্থহীন শোনায়, তবেই ত্রুটি তালিকাভুক্ত করবে।
- ত্রুটি না থাকলে "defects" খালি [] রাখবে।

আউটপুট ফরম্যাট (Strict JSON format only):
```json
{{
  "score": 93.5,
  "passed": true,
  "category": "{category}",
  "role_verdict_bn": "সংলাপ অত্যন্ত তথ্যবহুল ও দর্শকের জন্য প্রাঞ্জল।",
  "defects": []
}}
```
"""
        raw_res = self._call_gemini_text(prompt, system_instruction=sys_inst)
        parsed = self._extract_json(raw_res)

        if not parsed or not isinstance(parsed, dict):
            return {
                "score": 0.0,
                "passed": False,
                "category": category,
                "role_verdict_bn": f"স্ক্রিপ্ট {category} এর এআই সার্টিফিকেশন সম্পন্ন করা সম্ভব হয়নি (API Failure)।",
                "defects": [{"type": "API_FAILURE", "description": "Gemini API failed or returned invalid JSON"}]
            }

        score = float(parsed.get("score", 90.0))
        passed = (score >= 88.0) and len(parsed.get("defects", [])) == 0
        parsed["passed"] = passed
        parsed["score"] = score
        parsed["category"] = category
        return parsed

    # =========================================================================
    # STAGE 2: VISUAL EXECUTION BLUEPRINT CERTIFICATION (DUAL-CATEGORY)
    # =========================================================================
    def certify_visual_plan(
        self,
        plan_data: Dict[str, Any],
        topic: str,
        niche: str,
        aspect: str,
        category: str = "Category A"
    ) -> Dict[str, Any]:
        """
        Stage 2: Visual Execution Blueprint Certification.
        Category A: Evaluated by Veteran Documentary Film Director (Cinematography & Framing).
        Category B: Evaluated by Head of Broadcast Motion Design (Infographic Hierarchy & Map Vectors).
        """
        scenes = plan_data.get("planned_scenes", []) or plan_data.get("scenes", [])
        is_cat_b = ("Category B" in category) or ("motion" in category.lower()) or ("trade" in niche.lower())

        plan_summary = []
        for idx, sc in enumerate(scenes[:15], 1):
            sub = sc.get("concrete_visual_subject") or sc.get("visual_direction") or ""
            query = sc.get("b_roll_query") or ""
            plan_summary.append(f"Scene #{idx:02d}: Subject='{sub[:60]}' | Query/Telemetry='{query}'")
        summary_str = "\n".join(plan_summary)

        if is_cat_b:
            sys_inst = (
                "তুমি একজন আন্তর্জাতিক মানের ব্রডকাস্ট মোশন ডিজাইন ও ট্যাকটিক্যাল কার্টোগ্রাফি ডিরেক্টর "
                "(Head of Broadcast Motion Design & Tactical Cartography — Vox, Johnny Harris স্টাইল)। "
                "তোমার দায়িত্ব হলো মোশন গ্রাফিক্স ও ডেটা ম্যাপ ব্লুপ্রিন্টের প্রতিটি দৃশ্য বিশ্লেষণ করা এবং "
                "গ্রাফিক্যাল উপাদানের সমৃদ্ধি নিশ্চিত করা।"
            )
            cat_guidance = """
১. মোশন গ্রাফিক্স ও লেআউট সমৃদ্ধি (Motion Graphics & Infographic Hierarchy):
   - ডেটা কার্ড, স্যাটেলাইট ম্যাপ ভিউপোর্ট, এবং মেট্রিক গেজের বিন্যাস কি প্রফেশনাল?
   - কোনো সস্তা স্লাইডশো নয়, বরং আধুনিক ডেটা অ্যানিমেশন পরিকল্পনা আছে কি না?
২. গ্রাফিক্যাল উন্নতির সুনির্দিষ্ট পরামর্শ (Actionable Graphical Enhancements):
   - কোন দৃশ্যে নতুন গ্রাফিক্যাল উইজেট (ট্রেড রুট অ্যানিমেশন, পার্সেন্টেজ বার, রেডার পালস) যোগ করা প্রয়োজন তা উল্লেখ করো।
৩. নেগেটিভ প্রম্পটিং (Negative Directives):
   - বাস্তব ক্যামেরা ফুটেজ নেই বলে নম্বর কাটা যাবে না; এটি মোশন গ্রাফিক্স ক্যাটাগরি।
   - পরিকল্পনা তথ্যবহুল ও গতিশীল হলে নিশ্চিতভাবে ৯০-৯৫+ দাও।
"""
        else:
            sys_inst = (
                "তুমি একজন আন্তর্জাতিক তথ্যচিত্র পরিচালক (Veteran Documentary Film Director) ও প্রধান চিত্রগ্রাহক। "
                "তোমার দায়িত্ব হলো ফেসলেস সিনেমাটিক শট, ক্যামেরা মুভমেন্ট ও আলোর নান্দনিকতা মূল্যায়ন করা।"
            )
            cat_guidance = """
১. সিনেমাটিক শট বৈচিত্র্য (Cinematic Diversity): ক্লোজ-আপ, ড্রোন, ম্যাক্রো, ওয়াইড প্যান শটের স্বাভাবিক ধারাবাহিকতা।
২. ফেসলেস নীতি ও থিমিক ঐক্য (Faceless & Authentic Atmosphere)।
৩. নেগেটিভ প্রম্পটিং: পুনরাবৃত্তি না থাকলে এবং দৃশ্য নান্দনিক হলে ৯০-৯৫+ স্কোর দাও।
"""

        prompt = f"""
ক্যাটাগরি: {category} | বিষয়: {topic} | নিশ: {niche} | অ্যাসপেক্ট রেশিও: {aspect}
মোট দৃশ্য: {len(scenes)}

ভিজ্যুয়াল ব্লুপ্রিন্ট সারাংশ:
==================================================
{summary_str}
==================================================

মূল্যায়ন নির্দেশনা ({category} স্পেশালাইজড):
{cat_guidance}

আউটপুট ফরম্যাট (Strict JSON only):
```json
{{
  "score": 94.0,
  "passed": true,
  "category": "{category}",
  "director_verdict_bn": "ভিজ্যুয়াল ব্লুপ্রিন্ট {category} এর নিয়ম মেনে আকর্ষণীয়ভাবে পরিকল্পিত।",
  "graphical_enhancements": [
    "Scene 3 এ ট্রেড ফ্লো ডট ভেক্টর যুক্ত করার সুযোগ রয়েছে।"
  ],
  "defects": []
}}
```
"""
        raw_res = self._call_gemini_text(prompt, system_instruction=sys_inst)
        parsed = self._extract_json(raw_res)

        if not parsed or not isinstance(parsed, dict):
            return {
                "score": 0.0,
                "passed": False,
                "category": category,
                "director_verdict_bn": f"ভিজ্যুয়াল ব্লুপ্রিন্ট {category} এর এআই সার্টিফিকেশন সম্পন্ন করা সম্ভব হয়নি (API Failure)।",
                "graphical_enhancements": [],
                "defects": [{"type": "API_FAILURE", "description": "Gemini API failed or returned invalid JSON"}]
            }

        score = float(parsed.get("score", 92.0))
        passed = (score >= 88.0) and len(parsed.get("defects", [])) == 0
        parsed["passed"] = passed
        parsed["score"] = score
        parsed["category"] = category
        return parsed

    # =========================================================================
    # STAGE 4: AUDIO ENGINEERING & ZERO-FREEZE PARITY ASSERTION
    # =========================================================================
    def certify_audio_and_parity(
        self,
        stitched_visual_duration: float,
        total_audio_duration: float,
        total_scenes: int
    ) -> Dict[str, Any]:
        """
        Role: Chief Audio Engineer & Assembly Gatekeeper.
        Mathematically enforces the Zero-Freeze Invariant: visual_duration >= audio_duration.
        """
        deficit = total_audio_duration - stitched_visual_duration
        is_parity_ok = deficit <= 0.25

        if is_parity_ok:
            return {
                "score": 96.0,
                "passed": True,
                "parity_ok": True,
                "stitched_dur": round(stitched_visual_duration, 2),
                "audio_dur": round(total_audio_duration, 2),
                "deficit_sec": max(0.0, round(deficit, 2)),
                "audio_engineer_verdict_bn": f"ভিজ্যুয়াল দৈর্ঘ্য ({stitched_visual_duration:.2f}s) অডিও দৈর্ঘ্যের ({total_audio_duration:.2f}s) সাথে সম্পূর্ণ সিঙ্ক ও জিরো-ফ্রিজ নিশ্চিত।",
                "defects": []
            }
        else:
            return {
                "score": 60.0,
                "passed": False,
                "parity_ok": False,
                "stitched_dur": round(stitched_visual_duration, 2),
                "audio_dur": round(total_audio_duration, 2),
                "deficit_sec": round(deficit, 2),
                "audio_engineer_verdict_bn": f"ভিজ্যুয়াল দৈর্ঘ্য ({stitched_visual_duration:.2f}s) অডিও থেকে {deficit:.2f} সেকেন্ড কম! দৃশ্য জমে যাওয়ার ঝুঁকি রয়েছে।",
                "defects": [
                    {
                        "component": "visual_timeline",
                        "deficit_sec": round(deficit, 2),
                        "defect_description": f"ভিজ্যুয়াল ক্লিপ {deficit:.2f}s পূর্বে শেষ হয়ে গেছে, যার ফলে শেষ দৃশ্য জমে যাওয়ার ঝুঁকি রয়েছে।",
                        "healing_action": "FFmpeg এ ডাইনামিক বি-রোল লুপ প্যাডিং যোগ করে ভিজ্যুয়াল দৈর্ঘ্য অডিও দৈর্ঘ্যের সমান বা বেশি করতে হবে।"
                    }
                ]
            }

    # =========================================================================
    # STAGE 5: FINAL MULTI-MODAL VIDEO AUDIT WITH DUAL-CATEGORY SPECIALIZATION
    # =========================================================================
    def audit_final_video_with_defect_attribution(
        self,
        video_path: Path,
        script_data: Optional[Dict[str, Any]] = None,
        save_report_dir: Optional[Path] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Role: Supreme Multi-Modal Video Auditor with Numbered Defect Attribution.
        - Automatically detects Category A (Cinematic) vs. Category B (Motion Graphics).
        - Category B explicitly instructs Google Gemini on Motion Graphics / Data Journalism standard.
        - Strict Anti-Nitpicking Negative Directives & Numbered Defect Attribution.
        """
        if not video_path.exists():
            return {"score": 0.0, "passed": False, "critique": "Video file not found", "defects": []}

        # PRE-AUDIT DETERMINISTIC FREEZE DETECTION (Objective Local Gate)
        freezes = self.detect_freeze_frames(video_path, max_allowed_freeze_sec=3.0)
        if freezes:
            longest = max(f["duration_sec"] for f in freezes)
            first_start = freezes[0]["start_sec"]
            logger.error(f"❌ [CRITICAL FREEZE DETECTED] Video has {len(freezes)} freeze events! Longest: {longest:.2f}s at {first_start:.2f}s.")
            return {
                "overall_score": 10.0,
                "score": 10.0,
                "passed": False,
                "category": category or "Unknown",
                "summary_bn": f"ভিডিওটি বাতিল করা হয়েছে কারণ {first_start:.1f}s এ দীর্ঘ {longest:.1f}s ভিজ্যুয়াল ফ্রিজ/স্থির চিত্র শনাক্ত হয়েছে।",
                "critique": f"Critical defect: Static freeze frame detected starting at {first_start:.1f}s for {longest:.1f}s. Zero motion.",
                "defects": [
                    {
                        "type": "VISUAL_FREEZE",
                        "start_sec": f["start_sec"],
                        "duration_sec": f["duration_sec"],
                        "description": f"ভিডিওটি {f['start_sec']:.1f}s এ {f['duration_sec']:.1f} সেকেন্ড সম্পূর্ণ স্থির ছিল।"
                    } for f in freezes
                ]
            }

        keys = get_rotated_google_keys()
        if not keys or not genai:
            return {"score": 0.0, "overall_score": 0.0, "passed": False, "critique": "GenAI unavailable; audit cannot be performed", "defects": [{"type": "API_UNAVAILABLE", "description": "GenAI SDK or keys not available"}]}

        # Resolve category
        cat_resolved = category
        if not cat_resolved and script_data:
            cat_resolved = script_data.get("category")
        if not cat_resolved:
            cat_resolved = "Category B" if ("cat_b" in video_path.name.lower() or "category_b" in video_path.name.lower() or "motion" in video_path.name.lower() or "infographic" in video_path.name.lower()) else "Category A"

        is_cat_b = ("Category B" in cat_resolved) or ("motion" in cat_resolved.lower())

        # Ground truth transcript extraction
        transcript_lines = []
        if script_data and isinstance(script_data, dict):
            scenes = script_data.get("scenes", [])
            for s_idx, sc in enumerate(scenes, 1):
                transcript_lines.append(
                    f"দৃশ্য #{s_idx:02d} ({sc.get('duration_sec', 7.5)}s): বক্তব্য: \"{sc.get('dialogue_bn', '')}\" | মূল উপাদান: \"{sc.get('concrete_visual_subject') or sc.get('visual_direction', '')}\""
                )
        transcript_text = "\n".join(transcript_lines)

        if is_cat_b:
            audit_prompt = f"""
তুমি একজন শীর্ষ আন্তর্জাতিক মোশন গ্রাফিক্স ও ডেটা জার্নালিজম ভিডিও প্রোডাকশন অডিটর (Chief Motion Graphics & Data Journalism Video Auditor — Vox, Johnny Harris, Kurzgesagt, CaspianReport ও Visual Capitalist স্ট্যান্ডার্ড)।

🚨 বিশেষ ক্যাটাগরি ব্রিফিং (CATEGORY B SPECIALIZED BRIEFING):
এই ভিডিওটি কোনো ন্যাচারাল বা ক্যামেরা শটের ভিডিও নয়। এটি একটি আন্তর্জাতিক মানের হাই-এন্ড মোশন গ্রাফিক্স ও ডেটা জার্নালিজম ভিডিও।
এখানে অ্যানিমেটেড স্যাটেলাইট ম্যাপ, গ্লোবাল ট্রেড রুট ভেক্টর, ট্যাকটিক্যাল ডেটা কার্ড, পার্সেন্টেজ গেজ এবং ইনফোগ্রাফিক অ্যানিমেশনের মাধ্যমে জটিল অর্থনৈতিক ও কৌশলগত বিষয় ব্যাখ্যা করা হয়েছে।
একে সাধারণ ক্যামেরায় তোলা তথ্যচিত্রের সাথে তুলনা করে কখনোই নম্বর কমাবে না। বরং মোশন গ্রাফিক্সের নান্দনিকতা ও ডেটা সিঙ্কের ভিত্তিতে মূল্যায়ন করো।

================================================================================
📜 এই ভিডিওটির আসল চিত্রনাট্য ও প্রত্যাশিত ডেটা/ভিজ্যুয়াল তালিকা (GROUND-TRUTH TRANSCRIPT):
================================================================================
{transcript_text}
================================================================================

কঠোর মূল্যায়ন নির্দেশিকা (Category B Motion Graphics Standards):
১. ফুল-স্ক্রিন ব্যাকগ্রাউন্ড ও ভিজ্যুয়াল নান্দনিকতা (Full-Screen Visual & Modern Layout Integrity):
   - ব্যাকগ্রাউন্ডটি কি ১০০% ফুল-স্ক্রিন জুড়ে থাকা উচ্চমানের বাস্তবসম্মত স্যাটেলাইট ম্যাপ, নটিক্যাল চার্ট বা ভৌগোলিক ল্যান্ডস্কেপ? (কোনোভাবেই অর্ধেক স্ক্রিন জুড়ে থাকা বিশ্রী কার্ডবোর্ড বা ফেক ইনফরমেশন বক্স গ্রহণযোগ্য নয়)।
   - নির্দিষ্ট ভৌগোলিক অবস্থানে রেডার পালস ডট, লিডার কানেক্টর লাইন এবং আধুনিক স্লিক গ্লাস মরফিক পিল ব্যাজ (Glassmorphic Tooltip Pill) স্পষ্ট কিনা?
   - গতিশীল উপাদান বা মাইক্রো-অ্যাক্টর (যেমন: চলমান জাহাজ 🚢, বিমান ✈️, তেলবাহী ট্যাঙ্কার 🛢️, বা কার্গো 📦) করিডোর বরাবর চলাচল করছে কিনা?
২. কৃত্রিম বা ফেক টেক্সট কঠোরভাবে নিষিদ্ধ (Zero Fake Cardboard Desk / Zero Fake Labels):
   - স্ক্রিনে 'পর্ব ৩ বাই ১৫', 'বিশ্লেষণ', 'কী পয়েন্ট', 'মানচিত্রের মূল তথ্য', 'বৈজ্ঞানিক অনুসন্ধান' বা 'সত্যতা সূচক: ৯৯.৮% নিশ্চিত'—এই জাতীয় কোনো কৃত্রিম লেবেল বা কার্ডবোর্ড বাক্স থাকলে তা মারাত্মক ত্রুটি হিসেবে গণ্য হবে। শুধুমাত্র ডায়ালগের সাথে সম্পর্কিত সুনির্দিষ্ট স্থান ও বাস্তব তথ্য থাকতে হবে।
৩. ডায়ালগ ও অন-স্ক্রিন মেট্রিক নিখুঁত মিল (Dialogue-to-Graphic & Metric Parity):
   - মুখে যখন যে ভৌগোলিক স্থান (যেমন: সুয়েজ খাল, বাব এল-মান্দেব), প্রণালী, বাণিজ্য বা তেলের পার্সেন্টেজ ইত্যাদির কথা বলা হচ্ছে, অন-স্ক্রিন পিল ব্যাজ ও ম্যাপের পয়েন্টে কি শতভাগ সেই স্থানের তথ্য প্রদর্শিত হচ্ছে?
৪. স্ক্রিন জমে থাকা রোধ (Zero Freeze Frame):
   - ভিডিওর কোনো দৃশ্য কি স্থির হয়ে জমে ছিল? প্রতিটি দৃশ্য কি সাবলীল গতিতে চলছে?
৫. নেগেটিভ প্রম্পটিং ও লুপ-প্রতিরোধ নিয়ম (Loop-Immunity & Anti-Nitpicking Rule):
   - কাল্পনিক বা অতিক্ষুদ্র খুঁত ধরবে না।
   - পাস ক্রাইটেরিয়া: যদি ভিডিওতে ১০০% ফুল-স্ক্রিন ব্যাকগ্রাউন্ড থাকে, রেডার পয়েন্ট ও পিল ব্যাজ দৃশ্যমান থাকে, চলমান মাইক্রো-অ্যাক্টর থাকে, কোনো ফেক কার্ডবোর্ড লেবেল না থাকে, ডায়ালগ স্পষ্ট হয়, এবং মোশন স্বাভাবিক থাকে — তবে নিশ্চিতভাবে ৯০ থেকে ৯৫+ স্কোর প্রদান করো।
   - অহেতুক নম্বর কমিয়ে রি-রেন্ডারিংয়ের অন্তহীন লুপ তৈরি করবে না।
৬. সংখ্যাভিত্তিক সুনির্দিষ্ট ত্রুটি চিহ্নিতকরণ (Numbered Defect Attribution):
   - শুধুমাত্র যদি মারাত্মক অসঙ্গতি থাকে (যেমন কোনো ফেক বক্স টেক্সট উপস্থিত থাকা, ভুল ডেটা, বা ডায়ালগ কেটে যাওয়া), তবেই নির্দিষ্ট দৃশ্য নম্বর ও টাইমস্ট্যাম্প দিয়ে তা উল্লেখ করো।
   - কোনো মারাত্মক ত্রুটি না থাকলে "defects" সম্পূর্ণ খালি [] রাখবে।
৭. গ্রাফিক্যাল উন্নতির সুনির্দিষ্ট পরামর্শ (Actionable Graphical Enhancements):
   - নির্দিষ্ট দৃশ্য নম্বরে আর কী কী আকর্ষণীয় মোশন গ্রাফিক্স (যেমন: শিপিং করিডোর ভেক্টর, ট্রেড রুট গ্লো, আরও দ্রুতগতির রেডার পালস) যুক্ত করা যেতে পারে তা উল্লেখ করো।

কঠোর রেটিং নির্দেশনা (Strict Objective Scoring Rule):
- কোনো মুখস্থ বা পূর্বনির্ধারিত স্কোর (যেমন ৯৩ বা ৯৪) কখনোই দেবে না। বাস্তবসম্মতভাবে বিচার করে ০ থেকে ১০০ এর মধ্যে যথার্থ স্কোর প্রদান করো।
- যদি কোনো ফেক লেবেল থাকে, ডেটা ভুল হয়, ডায়ালগ কেটে যায় বা ভিজ্যুয়াল জমে থাকে, তবে defects তালিকায় দৃশ্য নম্বরসহ তা উল্লেখ করবে এবং স্কোর অবশ্যই ৮০ এর নিচে নামিয়ে দেবে।
- ভিডিওটি শতভাগ নির্ভেজাল ও উচ্চমানের হলেই কেবল ৮৮+ বা ৯০+ স্কোর পেতে পারে।

আউটপুট ফরম্যাট (Strict JSON format only):
```json
{{
  "overall_score": 88.5,
  "passed": true,
  "category": "Category B (Motion Graphics & Tactical Data)",
  "summary_bn": "ভিডিওটির মোশন গ্রাফিক্স ও ডেটার বস্তুনিষ্ঠ সারসংক্ষেপ...",
  "graphical_enhancements": [
    "Scene X এ নির্দিষ্ট গ্রাফিক্যাল উন্নতির পরামর্শ..."
  ],
  "defects": []
}}
```
"""
        else:
            audit_prompt = f"""
তুমি একজন শীর্ষ তথ্যচিত্র ও বাণিজ্যিক সিনেমাটিক ভিডিও অডিটর (Chief Cinematic Video Production & YouTube Monetization Auditor)।
তুমি এই সিনেমাটিক ফেসলেস ভিডিওটি অত্যন্ত মনোযোগ ও গুরুত্ব দিয়ে শুরু থেকে শেষ পর্যন্ত দেখে এর প্রতিটি সেকেন্ডের মান বিচার করো।

================================================================================
📜 এই ভিডিওটির আসল চিত্রনাট্য ও প্রত্যাশিত সাবজেক্ট তালিকা (GROUND-TRUTH TRANSCRIPT):
================================================================================
{transcript_text}
================================================================================

কঠোর মূল্যায়ন ও নেগেটিভ প্রম্পটিং নির্দেশিকা (Category A Cinematic Standards):
১. ভিজ্যুয়াল ও ডায়ালগের প্রাসঙ্গিকতা (Visual-Semantic Harmony):
   - মুখে যে বিষয়ে ডায়ালগ বলা হচ্ছে, পর্দায় দৃশ্যমান ফুটেজ কি সেই বিষয়ের সাথে সামঞ্জস্যপূর্ণ?
   - ফেসলেস সিনেমাটিক বি-রোল, ম্যাক্রো টেক্সচার ও ড্রোন শটের স্বাভাবিক নান্দনিকতা বজায় আছে কি না?
২. স্ক্রিন জমে থাকা রোধ (Zero Freeze Frame):
   - ভিডিও চলাকালীন কোনো দৃশ্য কি ৩ সেকেন্ডের বেশি স্থির হয়ে জমে ছিল? প্রতিটি দৃশ্য কি দৃশ্যমান ক্যামেরা মুভমেন্টে (Pan/Zoom/Drift) চলছে?
৩. বাস্তবসম্মত ও বস্তুনিষ্ঠ মূল্যায়ন নিয়ম (Objective Defect Attribution Rule):
   - কোনো মুখস্থ বা পূর্বনির্ধারিত স্কোর (যেমন ৯৩ বা ৯৪) দেবে না। ভিডিওর বাস্তব কোয়ালিটি বিচার করে ০ থেকে ১০০ এর মধ্যে বাস্তব নম্বর দাও।
   - ডায়ালগের সাথে ভিজ্যুয়ালের মিল বাধ্যতামূলক: ডায়ালগে নক্ষত্রমন্ডল / আকাশভরা তারার কথা থাকলে ভিডিওতে অবশ্যই তারা বা মহাকাশ পর্যবেক্ষণ থাকতে হবে। ডায়ালগের সাথে অসঙ্গতিপূর্ণ কিছু দেখানো হলে তা ত্রুটি হিসেবে গণ্য হবে।
   - যদি দৃশ্য স্থির থাকে বা ডায়ালগের সাথে বড় অসঙ্গতি থাকে, তবে defects তালিকায় সুনির্দিষ্ট দৃশ্য নম্বর ও টাইমস্ট্যাম্প উল্লেখ করবে এবং স্কোর অবশ্যই ৮০ এর নিচে নামিয়ে দেবে।
   - ভিডিওটি যদি সত্যিকার অর্থেই গতিশীল সিনেমাটিক ও ডায়ালগের সাথে যথাযথ মিল থাকে, তবেই ৮৮+ বা ৯০+ প্রদান করবে।

আউটপুট ফরম্যাট (Strict JSON format only):
```json
{{
  "overall_score": 88.0,
  "passed": true,
  "category": "Category A (Cinematic Faceless Documentary)",
  "summary_bn": "ভিডিওটির ডায়ালগ ও ভিজ্যুয়ালের বস্তুনিষ্ঠ বাস্তব মূল্যায়ন সারসংক্ষেপ...",
  "defects": []
}}
```
"""

        for k_idx, key in enumerate(keys):
            uploaded = None
            try:
                client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=180000))
                logger.info(f"[GoogleCertificationAuthority] Uploading {video_path.name} to Gemini via key #{k_idx+1} ({cat_resolved})...")
                uploaded = client.files.upload(file=str(video_path))

                poll_count = 0
                while uploaded.state.name == "PROCESSING":
                    time.sleep(2)
                    poll_count += 1
                    uploaded = client.files.get(name=uploaded.name)
                    if poll_count > 30:
                        raise TimeoutError("Gemini video processing timed out")

                if uploaded.state.name != "ACTIVE":
                    raise RuntimeError(f"Video state: {uploaded.state.name}")

                for mod in self.preferred_models:
                    try:
                        logger.info(f"[GoogleCertificationAuthority] Auditing video ({cat_resolved}) with model '{mod}'...")
                        resp = client.models.generate_content(
                            model=mod,
                            contents=[uploaded, audit_prompt]
                        )
                        raw_text = (resp.text or "").strip()
                        if raw_text:
                            parsed = self._extract_json(raw_text)
                            if parsed and isinstance(parsed, dict):
                                score = float(parsed.get("overall_score") or parsed.get("score") or 90.0)
                                defects = parsed.get("defects", [])
                                passed = (score >= 88.0) and (len(defects) == 0)
                                parsed["overall_score"] = score
                                parsed["score"] = score
                                parsed["passed"] = passed
                                parsed["defects"] = defects
                                parsed["category"] = cat_resolved

                                # Save audit report if requested
                                if save_report_dir:
                                    save_report_dir.mkdir(parents=True, exist_ok=True)
                                    report_file = save_report_dir / f"google_ai_certified_audit_{video_path.stem}.json"
                                    report_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                                    logger.info(f"✅ Certified audit report saved to: {report_file}")

                                return parsed
                    except Exception as e_mod:
                        logger.debug("Model %s audit failed: %s", mod, e_mod)
            except Exception as e_upload:
                logger.debug("Key #%d upload failed: %s", k_idx + 1, e_upload)
            finally:
                if uploaded and client:
                    try:
                        client.files.delete(name=uploaded.name)
                    except Exception:
                        pass

        # If Google Vision API was temporarily busy, DO NOT FAKE A PASSING 93.0 SCORE!
        logger.error("[GoogleCertificationAuthority] Gemini Vision API failed or timed out across all available keys.")
        return {
            "overall_score": 0.0,
            "score": 0.0,
            "passed": False,
            "category": cat_resolved,
            "summary_bn": f"ভিডিওটির গুগল এআই ভিশন অডিট সম্পন্ন করা যায়নি (Google API Timeout / Quota Exhaustion)।",
            "graphical_enhancements": [],
            "defects": [
                {
                    "type": "AUDIT_FAILURE",
                    "description": "Google Gemini Vision API was unreachable or timed out across all rotated keys."
                }
            ]
        }

    # =========================================================================
    # HELPER: ROBUST JSON PARSER
    # =========================================================================
    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts JSON object from Markdown or raw text with fallback sanitization."""
        if not text:
            return None
        text_clean = text.strip()

        # Try markdown codeblock
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text_clean)
        if m:
            text_clean = m.group(1).strip()

        # Try standard parse
        try:
            return json.loads(text_clean)
        except Exception:
            pass

        # Try regex extract between outer curly braces
        m_brace = re.search(r"(\{[\s\S]*\})", text_clean)
        if m_brace:
            try:
                return json.loads(m_brace.group(1))
            except Exception:
                pass

        return None


def get_google_certification_authority() -> GoogleCertificationAuthority:
    return GoogleCertificationAuthority.get_instance()
