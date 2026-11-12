"""
AutoMovie Pro - Voice Interaction & Live Spoken Commentary
Provides startup briefings, onboarding guidance, and real-time audio commentary
for the pipeline with customizable volume, mute toggles, and multi-stage voice cues.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger("VoiceCommentary")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VOICE_PREFS_FILE = DATA_DIR / "voice_preferences.json"


DEFAULT_VOICE_PREFS = {
    "is_muted": False,
    "volume": 0.85,
    "voice_style": "AutoMovie Pro AI",
    "default_language": "bn",
    "sectors": {
        "live_pipeline_commentary": True,      # লাইভ পাইপলাইন কমেন্ট্রি (ভিডিও তৈরি ও আপলোড প্রগ্রেস)
        "interactive_field_guidance": True,    # ফিল্ড ও সেটিংস সহায়িকা (ইনপুটে ক্লিক করলে ভয়েস নির্দেশনা)
        "system_advisory_alerts": True,        # সিস্টেম অ্যালার্ট ও প্রি-ফ্লাইট অ্যাডভাইজরি (চ্যানেল/এপিআই ওয়ার্নিং)
        "milestone_only_notifications": False  # শুধুমাত্র মাইলস্টোন নোটিফিকেশন (ভিডিও তৈরি ও পাবলিশ শেষ হলে)
    }
}

LANG_NAME_MAP = {
    "bn": {"bn": "বাংলা", "en": "Bengali"},
    "en": {"bn": "ইংরেজি", "en": "English"},
    "hi": {"bn": "হিন্দি", "en": "Hindi"},
    "ur": {"bn": "উর্দু", "en": "Urdu"},
    "es": {"bn": "স্প্যানিশ", "en": "Spanish"},
    "ar": {"bn": "আরবি", "en": "Arabic"},
    "fr": {"bn": "ফরাসি", "en": "French"},
    "de": {"bn": "জার্মান", "en": "German"},
    "pt": {"bn": "পর্তুগিজ", "en": "Portuguese"},
    "ru": {"bn": "রুশ", "en": "Russian"},
    "ja": {"bn": "জাপানি", "en": "Japanese"},
    "zh": {"bn": "চীনা", "en": "Chinese"},
    "ko": {"bn": "কোরিয়ান", "en": "Korean"},
    "tr": {"bn": "তুর্কি", "en": "Turkish"},
    "id": {"bn": "ইন্দোনেশীয়", "en": "Indonesian"},
    "ms": {"bn": "মালয়", "en": "Malay"},
    "ta": {"bn": "তামিল", "en": "Tamil"},
    "te": {"bn": "তেলেগু", "en": "Telugu"},
    "ml": {"bn": "মালয়ালাম", "en": "Malayalam"},
    "it": {"bn": "ইতালীয়", "en": "Italian"},
}


def resolve_lang_display(lang_code: Optional[str]) -> tuple[str, str]:
    """Resolves language code or name to (Bengali Name, English Name)"""
    if not lang_code:
        return "বাংলা", "Bengali"
    clean = str(lang_code).lower().strip()
    if clean in LANG_NAME_MAP:
        return LANG_NAME_MAP[clean]["bn"], LANG_NAME_MAP[clean]["en"]
    for k, v in LANG_NAME_MAP.items():
        if clean in (v["bn"].lower(), v["en"].lower(), k):
            return v["bn"], v["en"]
    return clean.capitalize(), clean.capitalize()


def _ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not VOICE_PREFS_FILE.exists():
        with open(VOICE_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_VOICE_PREFS, f, indent=2)


class FuturisticVoiceEngine:
    """
    Spoken AI assistant providing audio briefings, UI tutorials, pre-flight diagnostics,
    and granular pipeline commentary with sector-based toggles.
    """

    def __init__(self):
        _ensure_storage()

    def get_preferences(self) -> Dict[str, Any]:
        try:
            with open(VOICE_PREFS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all default sectors exist
                if "sectors" not in data or not isinstance(data["sectors"], dict):
                    data["sectors"] = dict(DEFAULT_VOICE_PREFS["sectors"])
                else:
                    for k, v in DEFAULT_VOICE_PREFS["sectors"].items():
                        if k not in data["sectors"]:
                            data["sectors"][k] = v
                return data
        except Exception:
            return dict(DEFAULT_VOICE_PREFS)

    def set_mute_state(self, muted: bool) -> Dict[str, Any]:
        prefs = self.get_preferences()
        prefs["is_muted"] = bool(muted)
        with open(VOICE_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
        return prefs

    def set_volume(self, volume: float) -> Dict[str, Any]:
        prefs = self.get_preferences()
        prefs["volume"] = max(0.0, min(1.0, float(volume)))
        with open(VOICE_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
        return prefs

    def update_settings(
        self,
        *,
        is_muted: Optional[bool] = None,
        volume: Optional[float] = None,
        default_language: Optional[str] = None,
        sectors: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        prefs = self.get_preferences()
        if is_muted is not None:
            prefs["is_muted"] = bool(is_muted)
        if volume is not None:
            prefs["volume"] = max(0.0, min(1.0, float(volume)))
        if default_language is not None:
            prefs["default_language"] = str(default_language).lower().strip()
        if sectors is not None and isinstance(sectors, dict):
            current_sectors = prefs.get("sectors", {})
            current_sectors.update(sectors)
            prefs["sectors"] = current_sectors
        with open(VOICE_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
        return prefs

    def speak_cue_desktop(self, stage_key: str, language: str = "bn") -> bool:
        """
        Plays audio cue directly through Windows desktop speakers asynchronously.
        Guaranteed zero lag and non-blocking for background workflows.
        """
        prefs = self.get_preferences()
        if prefs.get("is_muted"):
            return False
        try:
            import winsound
            comm = self.get_pipeline_commentary(stage=stage_key, language=language)
            loc = comm.get("local_audio_path")
            if loc and os.path.exists(loc):
                winsound.PlaySound(loc, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
        except Exception as e:
            logger.debug(f"Desktop voice playback skipped: {e}")
        return False

    def get_startup_briefing(
        self,
        user_name: str = "স্যার",
        active_channels_count: int = 1,
        scheduled_today: int = 2,
        language: str = "bn"
    ) -> Dict[str, Any]:
        prefs = self.get_preferences()
        if prefs.get("is_muted"):
            return {"speech_active": False, "reason": "muted"}

        if language == "bn":
            speech = (
                f"আসসালামু আলাইকুম {user_name}! অটোমুভি প্রো এআই সিস্টেম অনলাইন। "
                f"আপনার {active_channels_count}টি চ্যানেল সক্রিয় আছে এবং আজ {scheduled_today}টি ভিডিও শিডিউল করা রয়েছে। "
                f"সকল কোর সিস্টেম প্রস্তুত রয়েছে।"
            )
        else:
            speech = (
                f"Greetings! AutoMovie Pro AI online. "
                f"You have {active_channels_count} active channels and {scheduled_today} videos scheduled for today. "
                f"All core systems are operational."
            )

        audio_file = Path(__file__).resolve().parent.parent.parent / "assets" / "audio" / "voice_cues" / ("welcome_bn.wav" if language == "bn" else "welcome_en.wav")

        return {
            "speech_active": True,
            "text": speech,
            "display_text": speech,
            "audio_file": f"/assets/audio/voice_cues/{'welcome_bn.wav' if language == 'bn' else 'welcome_en.wav'}",
            "local_audio_path": str(audio_file) if audio_file.exists() else None,
            "volume": prefs.get("volume", 0.85),
            "style": prefs.get("voice_style", "AutoMovie Pro AI"),
            "timestamp": time.time()
        }

    def get_onboarding_guide(self, screen_id: str, language: str = "bn") -> Dict[str, Any]:
        prefs = self.get_preferences()
        if prefs.get("is_muted"):
            return {"speech_active": False, "reason": "muted"}

        guides = {
            "api_setup": {
                "bn": "এখানে আপনার Groq, Gemini এবং Google AI কী যুক্ত করুন। একটি কী শেষ হলে সিস্টেম স্বয়ংক্রিয়ভাবে ব্যাকআপ ব্যবহার করবে।",
                "en": "Add your Groq, Gemini and Google AI keys here. If one reaches its quota, the system will seamlessly fall back to backups."
            },
            "channel_setup": {
                "bn": "আপনার নিশ এবং ভাষা নির্বাচন করুন। শর্টস ও লং ভিডিওর আলাদা সময়সূচী নির্ধারণ করতে পারেন।",
                "en": "Select your niche and language. You can set customized schedules for Shorts and Long videos."
            },
            "dashboard": {
                "bn": "ড্যাশবোর্ডে আপনি লাইভ ভিডিও প্রসেসিং, স্ক্রিপ্ট জেনারেশন এবং আপলোড স্ট্যাটাস সরাসরি পর্যবেক্ষণ করতে পারেন।",
                "en": "On the dashboard, you can monitor live video rendering and publishing in real-time."
            }
        }

        entry = guides.get(screen_id, {
            "bn": "সহায়তার জন্য স্ক্রিনের ডানদিকের তথ্য বাটনে ক্লিক করুন।",
            "en": "Click the info button on the right for immediate assistance."
        })

        text = entry.get(language, entry["en"])
        return {
            "speech_active": True,
            "screen_id": screen_id,
            "text": text,
            "volume": prefs.get("volume", 0.85)
        }

    def get_pipeline_commentary(
        self,
        stage: str,
        target_language: Optional[str] = None,
        status: str = "success",
        language: str = "bn"
    ) -> Dict[str, Any]:
        """Provides real-time voice commentary and live screen display data
        across all granular stages and sub-stages:
        1. Startup & Welcome
        2. Topic Research (Start -> In-Progress -> Done -> Transition)
        3. Script & Hook (Start -> In-Progress -> Done -> Transition)
        4. Localization (Start -> In-Progress -> Done -> Transition)
        5. Audio & Voiceover (Start -> In-Progress -> Done -> Transition)
        6. Short Video 9:16 (Start -> In-Progress -> Done -> Transition)
        7. Long Video 16:9 (Start -> In-Progress -> Done -> Transition)
        8. Facebook Page Upload (Start -> In-Progress -> Done -> Transition)
        9. YouTube Channel Upload (Start -> In-Progress -> Done -> Idle)
        10. Health Sentinels & Alerts (Captcha, Key Failover)
        """
        prefs = self.get_preferences()
        is_muted = bool(prefs.get("is_muted", False))
        volume = float(prefs.get("volume", 0.85))

        audio_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "audio" / "voice_cues"

        stage_messages = {
            # --- 1. স্টার্টআপ ও স্বাগতম (Startup & System Online) ---
            "welcome": {
                "stage_name_bn": "সিস্টেম স্বাগতম (System Online)",
                "bn": "আসসালামু আলাইকুম। অটোমুভি প্রো এআই সিস্টেমে আপনাকে স্বাগতম। সকল কোর সিস্টেম অনলাইন এবং সম্পূর্ণ প্রস্তুত।",
                "en": "Greetings. Welcome to AutoMovie Pro AI system. All core systems are operational and ready.",
                "file": "welcome_bn.wav",
                "badge": "ONLINE"
            },
            "welcome_bn": {
                "stage_name_bn": "সিস্টেম স্বাগতম (System Online)",
                "bn": "আসসালামু আলাইকুম। অটোমুভি প্রো এআই সিস্টেমে আপনাকে স্বাগতম। সকল কোর সিস্টেম অনলাইন এবং সম্পূর্ণ প্রস্তুত।",
                "en": "Greetings. Welcome to AutoMovie Pro AI system. All core systems are operational and ready.",
                "file": "welcome_bn.wav",
                "badge": "ONLINE"
            },
            "welcome_en": {
                "stage_name_bn": "System Online",
                "bn": "Welcome to AutoMovie Pro AI system. All core systems are online.",
                "en": "Greetings. Welcome to AutoMovie Pro AI system. All core systems are operational and ready.",
                "file": "welcome_en.wav",
                "badge": "ONLINE"
            },
            "startup_ready": {
                "stage_name_bn": "সিস্টেম প্রস্তুত (Ready)",
                "bn": "সিস্টেম রেডি। ডেটাবেজ সিঙ্ক সম্পন্ন হয়েছে এবং ব্যাকগ্রাউন্ড অটোমেশন সক্রিয় রয়েছে।",
                "en": "System ready. Database synchronization complete and background automation active.",
                "file": "startup_ready.wav",
                "badge": "READY"
            },

            # --- 2. টপিক রিসার্চ ও ট্রেন্ড অ্যানালাইসিস (Topic Research) ---
            "topic_research_start": {
                "stage_name_bn": "টপিক রিসার্চ সূচনা (Topic Research Start)",
                "bn": "ভিডিও তৈরির জন্য ট্রেন্ডিং টপিক রিসার্চ ও কম্পিটিটর অ্যানালাইসিস শুরু করছি।",
                "en": "Starting trending topic research and competitor analysis for video production.",
                "file": "cue_topic_research.wav",
                "badge": "RESEARCH"
            },
            "topic_research_progress": {
                "stage_name_bn": "টপিক ফিল্টারিং (Topic Research In-Progress)",
                "bn": "গুগল ট্রেন্ডস ও ইউটিউব অ্যালগরিদম স্ক্যান করে হাই-রিটেনশন ভাইরাল টপিক ফিল্টার করা হচ্ছে।",
                "en": "Scanning Google Trends and YouTube algorithms to filter high-retention viral topics.",
                "file": "cue_topic_research_progress.wav",
                "badge": "RESEARCH"
            },
            "topic_research_done": {
                "stage_name_bn": "টপিক নির্বাচিত (Topic Selected)",
                "bn": "অ্যালগরিদম স্ক্যান সফল। একটি উচ্চ রিটেনশন এবং লাভজনক ভাইরাল টপিক নির্বাচন সম্পন্ন হয়েছে।",
                "en": "Algorithm scan succeeded. A high-retention, high-CTR viral topic has been selected.",
                "file": "cue_topic_found.wav",
                "badge": "RESEARCH"
            },
            "topic_to_script": {
                "stage_name_bn": "স্ক্রিপ্ট প্রস্তুতি (Transition to Script)",
                "bn": "টপিক রিসার্চ ডেটা লক করা হয়েছে। এখন এআই স্ক্রিপ্ট রাইটিং ইঞ্জিনের প্রস্তুতি নিচ্ছি।",
                "en": "Topic research data locked. Transitioning to AI script writing engine.",
                "file": "cue_topic_to_script.wav",
                "badge": "TRANSITION"
            },

            # --- 3. স্ক্রিপ্ট রচনা ও হুক জেনারেশন (Script Writing) ---
            "script_start": {
                "stage_name_bn": "স্ক্রিপ্ট রচনা শুরু (Script Writing Start)",
                "bn": "নির্বাচিত টপিকের ওপর প্রথম ৩ সেকেন্ডের প্যাটার্ন ইন্টারাপ্ট হুক এবং সম্পূর্ণ ভিডিও স্ক্রিপ্ট লেখা শুরু করছি।",
                "en": "Crafting 3-second pattern interrupt retention hook and high engagement video script.",
                "file": "cue_title_script.wav",
                "badge": "SCRIPT"
            },
            "script_progress": {
                "stage_name_bn": "সিন বিভাজন ও ডায়ালগ (Script In-Progress)",
                "bn": "গল্পের নাটকীয়তা ও অডিয়েন্স এনগেজমেন্ট ধরে রাখতে হাই-রিটেনশন দৃশ্য বিভাজন ও ডায়ালগ রচনা চলছে।",
                "en": "Developing dramatic pacing, scene breakdown, and engaging dialogues.",
                "file": "script_generating_bn.wav",
                "badge": "SCRIPT"
            },
            "script_done": {
                "stage_name_bn": "স্ক্রিপ্ট প্রস্তুত (Script Completed)",
                "bn": "ভিডিও স্ক্রিপ্ট, সিন বাই সিন প্রম্পট এবং এসইও অপ্টিমাইজড টাইটেল লেখা সফলভাবে সম্পন্ন হয়েছে।",
                "en": "Full video script, scene-by-scene prompts, and SEO optimized title successfully generated.",
                "file": "cue_script_ready.wav",
                "badge": "SCRIPT"
            },
            "script_to_localization": {
                "stage_name_bn": "লোকালাইজেশন প্রস্তুতি (Transition to Localization)",
                "bn": "মূল স্ক্রিপ্ট প্রস্তুত। এবার নির্বাচিত ভাষার সংস্কৃতি অনুযায়ী লোকালাইজেশন ও অনুবাদ মডিউল সক্রিয় করা হচ্ছে।",
                "en": "Master script validated. Activating cultural localization and translation module for the selected language.",
                "file": "cue_script_to_localization.wav",
                "badge": "TRANSITION"
            },

            # --- 4. গ্লোবাল লোকালাইজেশন ও অনুবাদ (Multilingual Localization) ---
            "localization_start": {
                "stage_name_bn": "গ্লোবাল লোকালাইজেশন শুরু (Localization Start)",
                "bn": "অডিও স্ক্রিপ্টটি 'বাংলা' ভাষার সংস্কৃতি ও ভাবগাম্ভীর্য অনুযায়ী লোকালাইজেশন ও ট্রান্সলেশন শুরু করছি।",
                "en": "Starting script localization and translation adapted to Bengali culture and nuances.",
                "file": "cue_localize_start.wav",
                "badge": "LOCALIZATION"
            },
            "localization_progress": {
                "stage_name_bn": "আঞ্চলিক ডায়ালগ রূপান্তর (Localization In-Progress)",
                "bn": "'বাংলা' ভাষার স্থানীয় সংস্কৃতি ও আঞ্চলিক উচ্চারণভঙ্গি অনুযায়ী ডায়ালগ রূপান্তর চলছে।",
                "en": "Adapting cultural nuances and native dialect pronunciation for Bengali.",
                "file": "cue_localize_bn_progress.wav",
                "badge": "LOCALIZATION"
            },
            "localization_done": {
                "stage_name_bn": "লোকালাইজেশন সম্পন্ন (Localization Completed)",
                "bn": "'বাংলা' ভাষার সংস্কৃতি অনুযায়ী নিখুঁত লোকালাইজেশন সম্পন্ন হয়েছে।",
                "en": "Flawless localization for Bengali culture and nuances completed.",
                "file": "cue_localize_bn_done.wav",
                "badge": "LOCALIZATION"
            },
            "localization_to_audio": {
                "stage_name_bn": "ভয়েসওভার প্রস্তুতি (Transition to Audio)",
                "bn": "লোকালাইজড স্ক্রিপ্ট প্রস্তুত। এবার স্টুডিও কোয়ালিটি ন্যাচারাল ভয়েসওভার সিন্থেসিস শুরু হচ্ছে।",
                "en": "Localized scripts ready. Initializing studio quality human-like voiceover synthesis.",
                "file": "cue_localization_to_audio.wav",
                "badge": "TRANSITION"
            },

            # --- 5. ভয়েসওভার ও স্টুডিও অডিও (Voiceover & Audio Synthesis) ---
            "audio_start": {
                "stage_name_bn": "ভয়েসওভার শুরু (Voiceover Start)",
                "bn": "হিউম্যান লাইক ভয়েসওভার ও স্টুডিও কোয়ালিটি অডিও সিন্থেসিস প্রক্রিয়া শুরু করছি।",
                "en": "Starting studio-grade human narration synthesis and emotional vocal tuning.",
                "file": "cue_audio_gen_start.wav",
                "badge": "AUDIO"
            },
            "audio_progress": {
                "stage_name_bn": "মিউজিক সিঙ্ক ও ডাকিং (Audio Ducking In-Progress)",
                "bn": "ভয়েসওভারের সাথে ব্যাকগ্রাউন্ড মিউজিক সিঙ্ক করা হচ্ছে এবং সাইডচেইন অডিও ডাকিং প্রয়োগ চলছে।",
                "en": "Synchronizing background music and applying dynamic sidechain ducking.",
                "file": "cue_audio_progress.wav",
                "badge": "AUDIO"
            },
            "audio_done": {
                "stage_name_bn": "অডিও সম্পন্ন (Audio Ready)",
                "bn": "ক্রিস্টাল ক্লিয়ার অডিও রেন্ডারিং, নয়েজ ক্যান্সেলেশন এবং ব্যাকগ্রাউন্ড মিউজিক মিক্সিং সম্পন্ন হয়েছে।",
                "en": "Crystal-clear studio audio rendering, noise filtering, and music mix completed.",
                "file": "cue_audio_done.wav",
                "badge": "AUDIO"
            },
            "audio_to_video": {
                "stage_name_bn": "ভিডিও রেন্ডারিং প্রস্তুতি (Transition to Video)",
                "bn": "সম্পূর্ণ সাউন্ডট্র্যাক প্রস্তুত। এবার ভিজ্যুয়াল সিন ও মোশন ভিডিও রেন্ডারিংয়ে প্রবেশ করছি।",
                "en": "Master soundtrack ready. Transitioning to visual scenes and motion video rendering.",
                "file": "cue_audio_to_video.wav",
                "badge": "TRANSITION"
            },

            # --- 6. শর্ট ভিডিও রেন্ডারিং (Short Video / Reel Rendering) ---
            "short_video_start": {
                "stage_name_bn": "শর্ট ভিডিও রেন্ডার শুরু (Short Video Start)",
                "bn": "ইউটিউব শর্টস ও ফেসবুক রিলসের জন্য ৯:১৬ ভার্টিক্যাল এইচডি ভিডিও রেন্ডারিং শুরু করছি।",
                "en": "Initiating 9:16 vertical HD video rendering for YouTube Shorts and Facebook Reels.",
                "file": "cue_short_video_start.wav",
                "badge": "SHORT_VIDEO"
            },
            "short_video_progress": {
                "stage_name_bn": "দৃশ্য ও সাবটাইটেল বার্নিং (Short In-Progress)",
                "bn": "হাই রেজুলেশন সিনেমাটিক সিন, মোশন এফেক্টস ও ডায়নামিক সাবটাইটেল ফ্রেম বাই ফ্রেম বার্নিং চলছে।",
                "en": "Rendering cinematic scenes, kinetic motion effects, and burn-in dynamic subtitles.",
                "file": "cue_agnes_generating.wav",
                "badge": "SHORT_VIDEO"
            },
            "short_video_done": {
                "stage_name_bn": "শর্ট ভিডিও প্রস্তুত (Short Video Completed)",
                "bn": "আলহামদুলিল্লাহ! ৯:১৬ ফরম্যাটের ফুল এইচডি শর্ট ভিডিও সফলভাবে তৈরি সম্পন্ন হয়েছে।",
                "en": "Praise be to God! Full HD 9:16 vertical short video successfully rendered.",
                "file": "cue_scene1_done.wav",
                "badge": "SHORT_VIDEO"
            },
            "short_to_long": {
                "stage_name_bn": "লং ভিডিও প্রস্তুতি (Transition to Long Video)",
                "bn": "শর্ট ভিডিও এনকোডিং সফল। এবার ইউটিউবের জন্য ফুল লেংথ ১৬:৯ লং ভিডিও কম্পোজিশন শুরু হচ্ছে।",
                "en": "Short video encoded. Transitioning to full-length 16:9 widescreen video composition.",
                "file": "cue_short_to_long.wav",
                "badge": "TRANSITION"
            },

            # --- 7. লং ভিডিও কম্পোজিশন ও ফাইনাল অ্যাসেম্বলি (Long Video Rendering) ---
            "long_video_start": {
                "stage_name_bn": "লং ভিডিও রেন্ডার শুরু (Long Video Start)",
                "bn": "ফুল লেন্থ ১৬:৯ হরিজন্টাল ভিডিওর সিনেমেটিক রেন্ডারিং ও সিন অ্যাসেম্বলি শুরু করছি।",
                "en": "Initiating cinematic 16:9 full-length widescreen assembly and timeline muxing.",
                "file": "cue_long_video_start.wav",
                "badge": "LONG_VIDEO"
            },
            "long_video_progress": {
                "stage_name_bn": "হার্ডওয়্যার অ্যাক্সিলারেশন (Long In-Progress)",
                "bn": "হার্ডওয়্যার অ্যাক্সিলারেশন দিয়ে প্রতিটি দৃশ্যের কালার গ্রেডিং, সাউন্ড সিঙ্ক এবং আল্ট্রা এইচডি কম্পোজিশন চলছে।",
                "en": "Hardware accelerated timeline composition, color grading, and ultra-HD rendering active.",
                "file": "cue_long_video_progress.wav",
                "badge": "LONG_VIDEO"
            },
            "long_video_done": {
                "stage_name_bn": "লং ভিডিও প্রস্তুত (Long Video Completed)",
                "bn": "অসাধারণ! সম্পূর্ণ লং ভিডিও নিখুঁত কোয়ালিটিতে রেন্ডার ও প্রস্তুত সম্পন্ন হয়েছে।",
                "en": "Outstanding! Long widescreen video rendered and assembled with maximum visual fidelity.",
                "file": "video_composed_bn.wav",
                "badge": "LONG_VIDEO"
            },
            "video_to_publish": {
                "stage_name_bn": "পাবলিশিং প্রস্তুতি (Transition to Publishing)",
                "bn": "ভিডিওর কোয়ালিটি গেট ভেরিফিকেশন পাস হয়েছে। এবার স্বয়ংক্রিয় সোশ্যাল মিডিয়া পাবলিশিং শুরু করছি।",
                "en": "Quality gate passed. Initializing automated social media distribution and publishing.",
                "file": "cue_video_to_publish.wav",
                "badge": "TRANSITION"
            },

            # --- 8. ফেসবুক পেজে ভাষাভিত্তিক আপলোড (Facebook Page Publishing) ---
            "facebook_upload_start": {
                "stage_name_bn": "ফেসবুক আপলোড শুরু (Facebook Upload Start)",
                "bn": "ফেসবুকে ভাষাভিত্তিক পেজগুলোতে স্বয়ংক্রিয় শিডিউলিং ও আপলোড শুরু করছি।",
                "en": "Starting automated multi-language page scheduling and upload to Facebook.",
                "file": "cue_facebook_upload_start.wav",
                "badge": "FACEBOOK"
            },
            "facebook_upload_progress": {
                "stage_name_bn": "ফেসবুক ট্রান্সফার (Facebook Uploading)",
                "bn": "বাংলা পেজের জন্য বাংলা ক্যাপশন, হ্যাশট্যাগ ও কমেন্টরি সহ ফেসবুক পেজে ভিডিও আপলোড চলছে।",
                "en": "Uploading localized video package, viral description, and tags to Facebook Page.",
                "file": "cue_facebook_upload_progress.wav",
                "badge": "FACEBOOK"
            },
            "facebook_upload_done": {
                "stage_name_bn": "ফেসবুকে সফল (Facebook Published)",
                "bn": "ফেসবুক পেজে ভিডিওটি সফলভাবে পাবলিশ ও শিডিউল সম্পন্ন হয়েছে।",
                "en": "Video successfully published and scheduled on Facebook Page.",
                "file": "cue_facebook_upload_done.wav",
                "badge": "FACEBOOK"
            },
            "facebook_to_youtube": {
                "stage_name_bn": "ইউটিউব প্রস্তুতি (Transition to YouTube)",
                "bn": "ফেসবুক আপলোড শেষ। এবার ইউটিউব চ্যানেলে আপলোড প্রক্রিয়া শুরু হচ্ছে।",
                "en": "Facebook publishing finalized. Transitioning to YouTube channel upload.",
                "file": "cue_facebook_to_youtube.wav",
                "badge": "TRANSITION"
            },

            # --- 9. ইউটিউব চ্যানেলে আপলোড ও পাবলিশ (YouTube Publishing) ---
            "youtube_upload_start": {
                "stage_name_bn": "ইউটিউব আপলোড শুরু (YouTube Upload Start)",
                "bn": "ইউটিউব চ্যানেলে ভিডিও, এসইও টাইটেল ও ভাইরাল থাম্বনেইল সহ আপলোড প্রক্রিয়া শুরু করছি।",
                "en": "Starting YouTube upload pipeline with high-CTR thumbnail and optimized metadata.",
                "file": "cue_upload_starting.wav",
                "badge": "YOUTUBE"
            },
            "youtube_upload_progress": {
                "stage_name_bn": "ইউটিউব ফাইল ট্রান্সফার (YouTube Uploading)",
                "bn": "ভিডিওর মেটাডেটা, চ্যাপ্টার্স, প্লেলিস্ট এবং আল্ট্রা এইচডি রেন্ডার ফাইল ইউটিউবে ট্রান্সফার হচ্ছে।",
                "en": "Transferring full-resolution video assets, chapters, and playlists to YouTube.",
                "file": "cue_youtube_upload_progress.wav",
                "badge": "YOUTUBE"
            },
            "youtube_upload_done": {
                "stage_name_bn": "ইউটিউবে সফল (YouTube Published)",
                "bn": "আলহামদুলিল্লাহ স্যার! ইউটিউব চ্যানেলে ভিডিওটি সফলভাবে আপলোড ও শিডিউল সম্পন্ন হয়েছে।",
                "en": "Praise be to God! Video successfully published and scheduled on YouTube Channel.",
                "file": "published_bn.wav",
                "badge": "YOUTUBE"
            },
            "cycle_complete_idle": {
                "stage_name_bn": "মিশন সম্পন্ন (All Missions Complete)",
                "bn": "আজকের ভিডিও তৈরি ও সকল প্ল্যাটফর্মে পাবলিশিং মিশন সফলভাবে সম্পন্ন হয়েছে। সিস্টেম পরবর্তী শিডিউলের জন্য প্রস্তুত।",
                "en": "Today's video generation and cross-platform publishing cycle is complete. Standing by.",
                "file": "cue_cycle_complete_idle.wav",
                "badge": "IDLE"
            },

            # --- 10. সিস্টেম অ্যালার্ট ও নোটিফিকেশন (Alerts & Health) ---
            "captcha_alert": {
                "stage_name_bn": "ক্যাপচা অ্যালার্ট (Captcha Alert)",
                "bn": "মনোযোগ দিন স্যার! স্ক্রিনে একটি ক্যাপচা সনাক্ত হয়েছে। মোবাইল অ্যাপ বা স্ক্রিন থেকে ক্যাপচাটি ভেরিফাই করুন।",
                "en": "Attention Sir! Captcha detected on screen. Please verify via companion app or screen.",
                "file": "captcha_alert.wav",
                "badge": "CAPTCHA"
            },
            "key_failover": {
                "stage_name_bn": "এআই ব্যাকআপ সুইচ (AI Key Failover)",
                "bn": "সিস্টেম স্বয়ংক্রিয়ভাবে ব্যাকআপ এআই ইঞ্জিনে সুইচ করেছে।",
                "en": "System seamlessly rotated to healthy backup AI engine.",
                "file": "cue_agnes_fallback_google.wav",
                "badge": "FAILOVER"
            }
        }

        # -------------------------------------------------------------
        # Coarse Aliases & Fuzzy Stage Resolver
        # -------------------------------------------------------------
        alias_map = {
            # Topic Aliases
            "topic_research": "topic_research_start",
            "topic_found": "topic_research_done",
            "topic_evaluating": "topic_research_progress",
            "research": "topic_research_start",
            "topic": "topic_research_start",
            "trs": "topic_research_start",

            # Script Aliases
            "title_script": "script_start",
            "script": "script_start",
            "script_generating": "script_progress",
            "script_ready": "script_done",
            "scenes": "script_progress",
            "humanize": "script_progress",
            "director": "script_progress",

            # Localization Aliases
            "script_localization": "localization_start",
            "localization": "localization_start",
            "localize": "localization_progress",
            "localize_done": "localization_done",

            # Audio Aliases
            "audio_generation": "audio_start",
            "audio": "audio_start",
            "tts": "audio_progress",
            "voice": "audio_start",

            # Short Video Aliases
            "scene_rendering": "short_video_progress",
            "short_video": "short_video_start",
            "short": "short_video_start",
            "reels": "short_video_start",
            "render": "short_video_progress",
            "rendering": "short_video_progress",
            "visual": "short_video_progress",
            "scene": "short_video_progress",

            # Long Video Aliases
            "video_composed": "long_video_done",
            "long_video": "long_video_start",
            "long": "long_video_start",
            "compose": "long_video_progress",
            "assembly": "long_video_progress",
            "final": "long_video_done",
            "quality_gate": "video_to_publish",
            "quality": "video_to_publish",

            # Upload & Publish Aliases
            "upload_starting": "facebook_upload_start",
            "facebook_upload": "facebook_upload_start",
            "facebook": "facebook_upload_progress",
            "fb": "facebook_upload_progress",
            "fb_done": "facebook_upload_done",
            "youtube_upload": "youtube_upload_start",
            "youtube": "youtube_upload_progress",
            "yt": "youtube_upload_progress",
            "yt_done": "youtube_upload_done",
            "published": "youtube_upload_done",
            "upload_done": "cycle_complete_idle",
            "done": "cycle_complete_idle",
            "idle": "cycle_complete_idle"
        }

        s_clean = str(stage).lower().strip()
        matched_key = stage_messages.get(s_clean)
        resolved_key = s_clean
        if not matched_key:
            norm_key = alias_map.get(s_clean)
            if norm_key and norm_key in stage_messages:
                entry = stage_messages[norm_key]
                resolved_key = norm_key
            else:
                # Substring matching for resilient dynamic phase tagging
                if "fb" in s_clean or "facebook" in s_clean:
                    resolved_key = "facebook_upload_progress"
                elif "yt" in s_clean or "youtube" in s_clean:
                    resolved_key = "youtube_upload_progress"
                elif "upload" in s_clean:
                    resolved_key = "youtube_upload_start"
                elif "short" in s_clean or "reel" in s_clean:
                    resolved_key = "short_video_start"
                elif "long" in s_clean:
                    resolved_key = "long_video_start"
                elif "audio" in s_clean or "tts" in s_clean:
                    resolved_key = "audio_start"
                elif "localiz" in s_clean:
                    resolved_key = "localization_start"
                elif "script" in s_clean or "scene" in s_clean:
                    resolved_key = "script_start"
                elif "topic" in s_clean or "research" in s_clean:
                    resolved_key = "topic_research_start"
                else:
                    resolved_key = "welcome"
                entry = stage_messages.get(resolved_key, stage_messages["welcome"])
        else:
            entry = matched_key

        # Dynamic language localization formatting
        if resolved_key in ("localization_start", "localization_progress", "localization_done", "script_to_localization"):
            target_bn, target_en = resolve_lang_display(target_language)
            entry = dict(entry)
            if resolved_key == "localization_start":
                entry["bn"] = f"অডিও স্ক্রিপ্টটি '{target_bn}' ভাষার সংস্কৃতি ও ভাবগাম্ভীর্য অনুযায়ী লোকালাইজেশন ও ট্রান্সলেশন শুরু করছি।"
                entry["en"] = f"Starting script localization and translation adapted to {target_en} culture and nuances."
            elif resolved_key == "localization_progress":
                entry["bn"] = f"'{target_bn}' ভাষার স্থানীয় সংস্কৃতি ও আঞ্চলিক উচ্চারণভঙ্গি অনুযায়ী ডায়ালগ রূপান্তর চলছে।"
                entry["en"] = f"Adapting cultural nuances and native dialect pronunciation for {target_en}."
            elif resolved_key == "localization_done":
                entry["bn"] = f"'{target_bn}' ভাষার সংস্কৃতি অনুযায়ী নিখুঁত লোকালাইজেশন সম্পন্ন হয়েছে।"
                entry["en"] = f"Flawless localization for {target_en} culture and nuances completed."
            elif resolved_key == "script_to_localization":
                entry["bn"] = f"মূল স্ক্রিপ্ট প্রস্তুত। এবার '{target_bn}' ভাষার সংস্কৃতি অনুযায়ী লোকালাইজেশন ও অনুবাদ মডিউল সক্রিয় করা হচ্ছে।"
                entry["en"] = f"Master script validated. Activating cultural localization and translation module for {target_en}."

        # Sector controls & Milestone gating
        MILESTONE_KEYS = {
            "short_video_done",
            "long_video_done",
            "facebook_upload_done",
            "youtube_upload_done",
            "cycle_complete_idle",
            "welcome",
            "welcome_bn",
            "welcome_en",
            "startup_ready"
        }
        sectors = prefs.get("sectors", {})
        live_pipeline_enabled = bool(sectors.get("live_pipeline_commentary", True))
        milestone_only = bool(sectors.get("milestone_only_notifications", False))

        speech_active = not is_muted
        if not live_pipeline_enabled:
            speech_active = False
        elif milestone_only and resolved_key not in MILESTONE_KEYS:
            speech_active = False

        filename = entry.get("file", "notification_chime.wav")
        local_path = audio_dir / filename
        web_url = f"/assets/audio/voice_cues/{filename}"
        text_content = entry.get(language, entry.get("bn", entry.get("en", "")))

        return {
            "speech_active": speech_active,
            "is_muted": is_muted,
            "stage": stage,
            "resolved_stage": resolved_key,
            "stage_title": entry.get("stage_name_bn", stage),
            "badge": entry.get("badge", "PIPELINE"),
            "text": text_content,
            "display_text": text_content,
            "live_screen_text": f"[AutoMovie Pro AI]: {text_content}",
            "audio_file": web_url if local_path.exists() else None,
            "local_audio_path": str(local_path) if local_path.exists() else None,
            "volume": volume
        }

    def get_preflight_advisory(self, language: str = "bn", channels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Performs pre-flight diagnostic checks before video creation or on demand.
        Returns detailed voice commentary, blocked/warning status, and recommendations:
        - No channel: BLOCKED
        - No API keys: BLOCKED
        - All systems ready: OK
        """
        prefs = self.get_preferences()
        is_muted = bool(prefs.get("is_muted", False))
        volume = float(prefs.get("volume", 0.85))
        sectors = prefs.get("sectors", {})
        advisory_enabled = bool(sectors.get("system_advisory_alerts", True))

        # 1. Channel check
        if channels is None:
            try:
                from app.customer_config import list_owned_channels
                from app.db import store
                session = store.get_session() or {}
                lid = session.get("login_id")
                channels = list_owned_channels(lid) if lid else []
            except Exception:
                channels = []

        if not channels:
            text_bn = "কোনো চ্যানেল সেটআপ করা নেই। দয়া করে চ্যানেল সেটআপ অপশনে গিয়ে আপনার চ্যানেল ও নিশ যুক্ত করুন, অথবা ওপরে কুইক সেটআপ সম্পন্ন করুন।"
            text_en = "No channel is configured. Please navigate to Channel Setup to configure your channel, or click the Quick Setup button at the top to complete setup."
            text = text_bn if language == "bn" else text_en
            return {
                "ok": False,
                "status": "blocked",
                "issue": "no_channel",
                "speech_active": False,
                "is_muted": is_muted,
                "title": "চ্যানেল সেটআপ প্রয়োজন" if language == "bn" else "Channel Setup Required",
                "text": text,
                "display_text": text,
                "recommended_action": "open_channel_setup",
                "volume": volume
            }

        # 2. API Keys check
        first_ch = channels[0] if channels else {}
        total_keys = 0
        try:
            from pipeline.api_keys import load_api_bundle
            bundle = load_api_bundle(channel=first_ch)
            counts = bundle.get("counts", {})
            total_keys = sum(int(v) for k, v in counts.items() if isinstance(v, (int, float)))
        except Exception as e:
            logger.warning(f"Preflight: failed to load api bundle: {e}")

        if total_keys == 0:
            text_bn = "বর্তমানে সিস্টেমে কোনো এআই চাবি যুক্ত নেই। ভিডিও তৈরির জন্য অন্তত একটি ফ্রি AI চাবি (Gemini বা Groq) যুক্ত করুন অথবা কুইক সেটআপ সম্পন্ন করুন।"
            text_en = "No API keys are currently configured. Please go to API Settings to add your keys or click Quick Setup at the top to complete setup."
            text = text_bn if language == "bn" else text_en
            return {
                "ok": False,
                "status": "blocked",
                "issue": "no_api_keys",
                "speech_active": False,
                "is_muted": is_muted,
                "title": "এআই কী প্রয়োজন" if language == "bn" else "API Keys Required",
                "text": text,
                "display_text": text,
                "recommended_action": "open_api_settings",
                "volume": volume
            }

        # 3. All systems ready (Pollinations warning completely removed, image generation works automatically)
        text_bn = "সকল প্রি-ফ্লাইট চেক সফল। চ্যানেল এবং এআই ইঞ্জিন সম্পূর্ণ প্রস্তুত।"
        text_en = "All pre-flight checks passed. Channel and AI engines are fully operational."
        text = text_bn if language == "bn" else text_en
        return {
            "ok": True,
            "status": "ok",
            "issue": None,
            "speech_active": False,
            "is_muted": is_muted,
            "title": "সিস্টেম প্রস্তুত" if language == "bn" else "System Ready",
            "text": text,
            "display_text": text,
            "recommended_action": None,
            "volume": volume
        }

    def get_field_guidance(self, field_key: str, language: str = "bn") -> Dict[str, Any]:
        """
        Interactive form field voice guidance triggered on cursor focus or click.
        Provides clear spoken instruction explaining what to enter and why.
        """
        prefs = self.get_preferences()
        is_muted = bool(prefs.get("is_muted", False))
        volume = float(prefs.get("volume", 0.85))
        sectors = prefs.get("sectors", {})
        guidance_enabled = bool(sectors.get("interactive_field_guidance", True))

        field_kb = {
            "channel_name": {
                "bn": "এখানে আপনার চ্যানেলের নাম দিন।",
                "en": "Enter your channel name here."
            },
            "channel_niche": {
                "bn": "নিচের ড্রপডাউন থেকে চ্যানেলের নিশ সিলেক্ট করুন।",
                "en": "Select your channel niche from the dropdown below."
            },
            "channel_logo": {
                "bn": "এই ফিল্ডে আপনার চ্যানেলের লোগোটি আপলোড করুন যেন ভিডিওতে লোগোটির দেখানো সম্ভব হয়।",
                "en": "Upload your channel logo here so it can be seamlessly embedded into your videos."
            },
            "api_provider": {
                "bn": "এখান থেকে এআই প্রদানকারী নির্বাচন করুন।",
                "en": "Select your AI provider from this list."
            },
            "api_key": {
                "bn": "এখানে আপনার নির্বাচিত এআই প্রদানকারীর সিক্রেট এপিআই কী পেস্ট করুন।",
                "en": "Paste your selected AI provider secret API key here."
            },
            "schedule_time": {
                "bn": "এখানে আপনার চ্যানেলে দৈনিক ভিডিও আপলোডের নির্দিষ্ট সময় নির্ধারণ করুন।",
                "en": "Set your channel's daily automated video upload schedule time here."
            },
            "target_language": {
                "bn": "ভিডিওর মূল এবং লক্ষ্য ভাষা নির্ধারণ করুন।",
                "en": "Select the primary target language for your video audience."
            },
            "custom_topic": {
                "bn": "এখানে আপনার ভিডিওর নির্দিষ্ট বিষয়বস্তু বা টপিক লিখুন।",
                "en": "Enter your specific video topic or custom instruction prompt here."
            },
            "youtube_connect": {
                "bn": "আপনার ইউটিউব চ্যানেলটি নিরাপদভাবে সংযুক্ত করতে এই বাটনে ক্লিক করুন।",
                "en": "Click this button to securely connect and authenticate your YouTube channel."
            },
            "facebook_connect": {
                "bn": "আপনার ফেসবুক পেজটি কানেক্ট করুন যেন ভিডিও স্বয়ংক্রিয়ভাবে পাবলিশ হতে পারে।",
                "en": "Connect your Facebook page here to enable automated video publishing."
            }
        }

        key = str(field_key).lower().strip()
        info = field_kb.get(key)
        if not info:
            info = {
                "bn": "এই ইনপুটে প্রয়োজনীয় তথ্য প্রদান করুন।",
                "en": "Please provide the requested information in this input field."
            }

        text = info.get(language, info["en"])
        return {
            "ok": True,
            "field_key": key,
            "speech_active": False,
            "is_muted": is_muted,
            "text": text,
            "display_text": text,
            "volume": volume
        }
