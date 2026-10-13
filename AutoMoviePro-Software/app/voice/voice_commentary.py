"""
AutoMovie Pro - Futuristic Voice Interaction (Jarvis Style) & Live Spoken Commentary
Provides startup briefings, onboarding guidance, and real-time audio commentary
for the pipeline with customizable volume and mute toggles.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("VoiceCommentary")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VOICE_PREFS_FILE = DATA_DIR / "voice_preferences.json"


def _ensure_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not VOICE_PREFS_FILE.exists():
        default_prefs = {
            "is_muted": False,
            "volume": 0.85,
            "voice_style": "Jarvis",
            "default_language": "bn"
        }
        with open(VOICE_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_prefs, f, indent=2)


class FuturisticVoiceEngine:
    """
    Spoken AI assistant providing audio briefings, UI tutorials, and pipeline commentary.
    """

    def __init__(self):
        _ensure_storage()

    def get_preferences(self) -> Dict[str, Any]:
        try:
            with open(VOICE_PREFS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"is_muted": False, "volume": 0.85, "voice_style": "Jarvis", "default_language": "bn"}

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

    def update_settings(self, *, is_muted: Optional[bool] = None, volume: Optional[float] = None) -> Dict[str, Any]:
        prefs = self.get_preferences()
        if is_muted is not None:
            prefs["is_muted"] = bool(is_muted)
        if volume is not None:
            prefs["volume"] = max(0.0, min(1.0, float(volume)))
        with open(VOICE_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
        return prefs

    def get_startup_briefing(
        self,
        user_name: str = "Admin",
        active_channels_count: int = 1,
        scheduled_today: int = 2,
        language: str = "bn"
    ) -> Dict[str, Any]:
        prefs = self.get_preferences()
        if prefs.get("is_muted"):
            return {"speech_active": False, "reason": "muted"}

        if language == "bn":
            speech = (
                f"আসসালামু আলাইকুম {user_name}! অটোমুভি প্রো Jarvis সিস্টেম প্রস্তুত। "
                f"আপনার {active_channels_count}টি চ্যানেল সক্রিয় আছে এবং আজ {scheduled_today}টি ভিডিও শিডিউল করা রয়েছে। "
                f"সকল সিস্টেম স্বাভাবিকভাবে কাজ করছে।"
            )
        else:
            speech = (
                f"Greetings {user_name}! AutoMovie Pro Jarvis online. "
                f"You have {active_channels_count} active channels and {scheduled_today} videos scheduled for today. "
                f"All core systems are operational."
            )

        return {
            "speech_active": True,
            "text": speech,
            "volume": prefs.get("volume", 0.85),
            "style": prefs.get("voice_style", "Jarvis"),
            "timestamp": time.time()
        }

    def get_onboarding_guide(self, screen_id: str, language: str = "bn") -> Dict[str, Any]:
        prefs = self.get_preferences()
        if prefs.get("is_muted"):
            return {"speech_active": False, "reason": "muted"}

        guides = {
            "api_setup": {
                "bn": "এখানে আপনার Grok এবং Google AI কী যুক্ত করুন। একটি কী ব্যর্থ হলে সিস্টেম স্বয়ংক্রিয়ভাবে ব্যাকআপ ব্যবহার করবে।",
                "en": "Add your Grok and Google AI keys here. If one fails, the system automatically falls back."
            },
            "channel_setup": {
                "bn": "আপনার নিশ এবং ভাষা নির্বাচন করুন। শর্টস ও লং ভিডিওর আলাদা সময়সূচী নির্ধারণ করুন।",
                "en": "Select your niche and language. You can set separate schedules for Shorts and Longs."
            },
            "dashboard": {
                "bn": "ড্যাশবোর্ডে আপনি লাইভ ভিডিও প্রসেসিং এবং আপলোড স্ট্যাটাস সরাসরি পর্যবেক্ষণ করতে পারেন।",
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

    def get_pipeline_commentary(self, stage: str, status: str = "success", language: str = "bn") -> Dict[str, Any]:
        """Provides real-time Jarvis voice commentary and live screen display data
        across all video pipeline stages:
        1. টপিক রিসার্চ (Topic Research)
        2. স্ক্রিপ্ট লোকালাইজেশন (Script Localization)
        3. অডিও জেনারেশন (Audio Generation)
        4. সিন রেন্ডারিং (Scene Rendering)
        Respects user volume slider and mute state.
        """
        prefs = self.get_preferences()
        is_muted = bool(prefs.get("is_muted", False))
        volume = float(prefs.get("volume", 0.85))

        audio_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "audio" / "voice_cues"

        stage_messages = {
            # --- 1. টপিক রিসার্চ (Topic Research) ---
            "topic_research": {
                "stage_name_bn": "টপিক রিসার্চ (Topic Research)",
                "bn": "ভিডিও তৈরির জন্য ট্রেন্ডিং টপিক রিসার্চ শুরু করেছি।",
                "en": "Starting trending topic research for video production.",
                "hi": "वीडियो निर्माण के लिए ट्रेंडिंग टॉपिक रिसर्च शुरू की गई है।",
                "ur": "ویڈیو پروڈکشن کے لیے ٹرینڈنگ ٹاپک ریسرچ شروع کر دی گئی ہے۔",
                "ta": "வீடியோ உருவாக்கத்திற்கான ட்ரெண்டிங் தலைப்பு ஆராய்ச்சி தொடங்கப்பட்டது.",
                "ml": "വീഡിയോ നിർമ്മാണത്തിനായി ട്രെൻഡിംഗ് വിഷയ ഗവേഷണം ആരംഭിച്ചു.",
                "file": "cue_topic_research.wav",
                "badge": "RESEARCH",
            },
            "topic_found": {
                "stage_name_bn": "টপিক রিসার্চ (Topic Research)",
                "bn": "একটি উচ্চ রিটেনশন ভাইরাল টপিক পাওয়া গেছে।",
                "en": "A high CTR viral topic has been discovered.",
                "hi": "एक उच्च सीटीआर वायरल टॉपिक मिल गया है।",
                "ur": "ایک وائرل اور پرکشش موضوع مل گیا ہے۔",
                "ta": "அதிக ஈர்ப்பு கொண்ட வைரல் தலைப்பு கண்டறியப்பட்டது.",
                "ml": "ഉയർന്ന പ്രേക്ഷക ശ്രദ്ധ നേടുന്ന വൈറൽ വിഷയം കണ്ടെത്തി.",
                "file": "cue_topic_found.wav",
                "badge": "RESEARCH",
            },
            "topic_evaluating": {
                "stage_name_bn": "টপিক রিসার্চ (Topic Research)",
                "bn": "ভাইরাল ট্রেন্ড ও এন্টি-ডুপ্লিকেট ডাটাবেস যাচাই করে সেরা টপিক নির্বাচন করছি।",
                "en": "Validating viral trends against anti-duplicate registry.",
                "hi": "वायरल रुझानों और डुप्लीकेट रोकथाम डेटाबेस से टॉपिक की पुष्टि की जा रही है।",
                "ur": "وائرل ٹرینڈز اور ڈپلیکیٹ فلٹر کی مدد سے موضوع کی توثیق جاری ہے۔",
                "ta": "டூப்ளிகேட் பதிவேட்டில் வைரல் போக்குகளை சரிபார்க்கிறது.",
                "ml": "ഡ്യൂപ്ലിക്കേറ്റ് ഡാറ്റാബേസിൽ വിഷയം പരിശോധിച്ച് ഉറപ്പാക്കുന്നു.",
                "file": "topic_research_bn.wav",
                "badge": "RESEARCH",
            },

            # --- 2. স্ক্রিপ্ট ও ভিজ্যুয়াল প্ল্যান (Script & Visual Blueprint) ---
            "title_script": {
                "stage_name_bn": "স্ক্রিপ্ট ও টাইটেল (Script & Title)",
                "bn": "টপিক অনুযায়ী SEO ফ্রেন্ডলি টাইটেল ও স্ক্রিপ্ট জেনারেট করছি।",
                "en": "Generating SEO friendly title and high retention script.",
                "hi": "एसईओ अनुकूल शीर्षक और स्क्रिप्ट तैयार की जा रही है।",
                "ur": "ایس ای او پر مبنی ٹائٹل اور اسکرپٹ تیار کی جا رہی ہے۔",
                "ta": "SEO நட்பு தலைப்பு மற்றும் ஸ்கிரிப்ட் உருவாக்கப்படுகிறது.",
                "ml": "SEO അനുയോജ്യമായ തലക്കെട്ടും തിരക്കഥയും തയ്യാറാക്കുന്നു.",
                "file": "cue_title_script.wav",
                "badge": "SCRIPT",
            },
            "script_ready": {
                "stage_name_bn": "স্ক্রিপ্ট প্রস্তুত (Script Ready)",
                "bn": "স্ক্রিপ্ট ও সিন ব্লুপ্রিন্ট জেনারেট সম্পন্ন হয়েছে।",
                "en": "Script and scene blueprint generated successfully.",
                "hi": "स्क्रिप्ट और सीन ब्लूप्रिंट सफलतापूर्वक तैयार हो गया है।",
                "ur": "اسکرپٹ اور مناظر کا خاکہ کامیابی سے تیار ہو گیا ہے۔",
                "ta": "ஸ்கிரிப்ட் மற்றும் காட்சி வரைபடம் வெற்றிகரமாக உருவானது.",
                "ml": "തിരക്കഥയും സീൻ ബ്ലൂപ്രിന്റും വിജയകരമായി തയ്യാറായി.",
                "file": "cue_script_ready.wav",
                "badge": "SCRIPT",
            },
            "script_localization": {
                "stage_name_bn": "স্ক্রিপ্ট লোকালাইজেশন (Script Localization)",
                "bn": "সকল ভাষায় স্ক্রিপ্ট লোকালাইজেশন ও সাংস্কৃতিক অভিযোজন শুরু করছি।",
                "en": "Starting script localization across all languages with cultural nuance.",
                "hi": "सभी भाषाओं में सांस्कृतिक बारीकियों के साथ स्क्रिप्ट का स्थानीयकरण शुरू हो रहा है।",
                "ur": "تمام زبانوں میں اسکرپٹ کا لوکلائزیشن شروع کیا جا رہا ہے۔",
                "ta": "அனைத்து மொழிகளிலும் ஸ்கிரிப்ட் மொழிபெயர்ப்பு தொடங்கப்படுகிறது.",
                "ml": "എല്ലാ ഭാഷകളിലും തിരക്കഥയുടെ പ്രാദേശികവൽക്കരണം ആരംഭിക്കുന്നു.",
                "file": "cue_localize_start.wav",
                "badge": "LOCALIZATION",
            },
            "visual_plan": {
                "stage_name_bn": "ভিজ্যুয়াল প্ল্যানিং (Visual Planning)",
                "bn": "সিন অনুযায়ী এআই ক্যামেরা অ্যাঙ্গেল ও ভিজ্যুয়াল প্রম্পট প্ল্যান তৈরি করছি।",
                "en": "Creating visual render blueprint and dynamic camera angles.",
                "hi": "प्रत्येक दृश्य के लिए दृश्य रेंडर ब्लूप्रिंट और कैमरा एंगल तैयार किए जा रहे हैं।",
                "ur": "ہر منظر کے لیے بصری رینڈر اور کیمرہ اینگلز کی منصوبہ بندی جاری ہے۔",
                "ta": "காட்சி அமைப்புகள் மற்றும் கேமரா கோணங்கள் திட்டமிடப்படுகின்றன.",
                "ml": "ദൃശ്യ ക്രമീകരണങ്ങളും ക്യാമറ ആംഗിളുകളും പ്ലാൻ ചെയ്യുന്നു.",
                "file": "cue_pollinations_image.wav",
                "badge": "PLAN",
            },

            # --- 3. অডিও ও টিটিএস সিন্থেসিস (Audio Generation) ---
            "audio_generation": {
                "stage_name_bn": "অডিও জেনারেশন (Audio Generation)",
                "bn": "ন্যাচারাল হিউম্যান ভয়েসে সকল ভাষার অডিও সিন্থেসিস চলছে।",
                "en": "Synthesizing ultra-natural robotic-free studio narration for all languages.",
                "hi": "सभी भाषाओं के लिए प्राकृतिक मानव आवाज में ऑडियो तैयार किया जा रहा है।",
                "ur": "تمام زبانوں کے لیے معیاری انسانی آواز میں آڈیو ریکارڈنگ تیار ہو رہی ہے۔",
                "ta": "அனைத்து மொழிகளுக்கும் இயல்பான குரலில் ஆடியோ உருவாக்கப்படுகிறது.",
                "ml": "എല്ലാ ഭാഷകൾക്കുമായി റിയലിസ്റ്റിക് വോയ്‌സ് നരേഷൻ തയ്യാറാക്കുന്നു.",
                "file": "cue_audio_gen_start.wav",
                "badge": "AUDIO",
            },

            # --- 4. সিন ও মিডিয়া রেন্ডারিং (Scene Rendering) ---
            "scene_rendering": {
                "stage_name_bn": "সিন রেন্ডারিং (Scene Rendering)",
                "bn": "হাই রেজুলেশন এআই সিন রেন্ডার এবং মোশন ভিজ্যুয়াল তৈরি হচ্ছে।",
                "en": "Rendering cinematic high-resolution visual scenes and animations.",
                "hi": "सिनेमैटिक दृश्यों का एआई रेंडरिंग और मोशन एनिमेशन तैयार किया जा रहा है।",
                "ur": "اعلی معیار کے بصری مناظر اور حرکت پذیر اینیمیشن رینڈر ہو رہے ہیں۔",
                "ta": "உயர்தர சினிமா காட்சிகள் மற்றும் அனிமேஷன்கள் உருவாக்கப்படுகின்றன.",
                "ml": "ഉയർന്ന നിലവാരമുള്ള സിനിമാറ്റിക് ദൃശ്യങ്ങൾ നിർമ്മിക്കുന്നു.",
                "file": "cue_agnes_generating.wav",
                "badge": "RENDER",
            },

            # --- 5. ফাইনাল কম্পোজিশন ও সাবটাইটেল (Final Composition) ---
            "video_composed": {
                "stage_name_bn": "ফাইনাল কম্পোজিশন (Final Assembly)",
                "bn": "ইন্টেল কিউএসভি ও এনভিডিয়া দিয়ে ভিডিও রেন্ডারিং, সাবটাইটেল এবং ব্র্যান্ডিং সম্পন্ন হয়েছে।",
                "en": "Hardware accelerated video assembly, subtitles, and branding completed.",
                "hi": "हार्डवेयर त्वरित वीडियो रेंडरिंग, उपशीर्षक और ब्रांडिंग पूरी हो गई है।",
                "ur": "ہارڈویئر ایکسلریشن کے ساتھ ویڈیو رینڈرنگ، سب ٹائٹلز اور برانڈنگ مکمل ہو گئی۔",
                "ta": "ஹார்டுவேர் வேகத்துடன் வீடியோ தொகுப்பு மற்றும் வசனங்கள் தயாராகின.",
                "ml": "ഹാർഡ്‌വെയർ ആക്സിലറേഷനോടെ വീഡിയോ അസംബ്ലിയും സബ്‌ടൈറ്റിലുകളും പൂർത്തിയായി.",
                "file": "cue_scene1_done.wav",
                "badge": "COMPOSE",
            },
            "quality_gate": {
                "stage_name_bn": "কোয়ালিটি সার্টিফিকেশন (Quality Gate)",
                "bn": "অডিও-ভিডিও সিঙ্ক, সাবটাইটেল এবং রেজুলেশনের ইন্ডাস্ট্রিয়াল কোয়ালিটি চেক সফল।",
                "en": "Industrial quality gate verification and sync certification passed.",
                "hi": "गुणवत्ता सत्यापन और ऑडियो-वीडियो सिंक जांच पूरी तरह सफल रही।",
                "ur": "کوالٹی چیک اور آڈیو ویڈیو مطابقت کی تصدیق کامیاب رہی۔",
                "ta": "தரக் கட்டுப்பாடு மற்றும் ஒத்திசைவு சோதனை வெற்றிகரமாக முடிந்தது.",
                "ml": "ഗുണനിലവാര പരിശോധനയും സിങ്ക് സർട്ടിഫിക്കേഷനും വിജയകരമായി.",
                "file": "notification_chime.wav",
                "badge": "QUALITY",
            },
            "published": {
                "stage_name_bn": "পাবলিশিং প্রস্তুত (Upload Ready)",
                "bn": "ভিডিওটি সকল ভাষায় ইউটিউব এবং সোশ্যাল প্ল্যাটফর্মে আপলোড ও পাবলিশের জন্য সম্পূর্ণ প্রস্তুত।",
                "en": "Video package is fully prepared for YouTube and multi-platform publishing across all languages.",
                "hi": "वीडियो सभी भाषाओं में अपलोड और प्रकाशन के लिए पूरी तरह तैयार है।",
                "ur": "ویڈیو تمام زبانوں میں اپ لوڈ اور پبلش کے لیے مکمل تیار ہے۔",
                "ta": "அனைத்து மொழிகளிலும் பதிவேற்றம் செய்ய வீடியோ முழுமையாக தயாராக உள்ளது.",
                "ml": "എല്ലാ ഭാഷകളിലും പ്രസിദ്ധീകരിക്കാൻ വീഡിയോ പൂർണ്ണമായും തയ്യാറാണ്.",
                "file": "cue_upload_starting.wav",
                "badge": "READY",
            }
        }

        entry = stage_messages.get(stage)
        if not entry:
            # Check normalized stage aliases matching custom_pipeline runner stages
            alias_map = {
                "research": "topic_research",
                "topic": "topic_research",
                "script": "title_script",
                "script_ready": "script_ready",
                "localization": "script_localization",
                "localize": "script_localization",
                "visual": "visual_plan",
                "audio": "audio_generation",
                "tts": "audio_generation",
                "rendering": "scene_rendering",
                "render": "scene_rendering",
                "media": "scene_rendering",
                "compose": "video_composed",
                "assembly": "video_composed",
                "quality": "quality_gate",
                "done": "published",
                "published": "published"
            }
            norm_key = alias_map.get(str(stage).lower().strip(), stage)
            entry = stage_messages.get(norm_key, {
                "stage_name_bn": f"ধাপ {stage}",
                "bn": f"ধাপ {stage} সম্পন্ন হচ্ছে।",
                "en": f"Stage {stage} is in progress.",
                "hi": f"चरण {stage} प्रगति पर है।",
                "ur": f"مرحلہ {stage} جاری ہے۔",
                "ta": f"நிலை {stage} செயல்பாட்டில் உள்ளது.",
                "ml": f"ഘട്ടം {stage} പുരോഗമിക്കുന്നു.",
                "file": "notification_chime.wav",
                "badge": "STAGE"
            })

        audio_file = audio_dir / entry.get("file", "notification_chime.wav")
        text_content = entry.get(language, entry.get("bn", entry.get("en", "")))

        return {
            "speech_active": not is_muted,
            "is_muted": is_muted,
            "stage": stage,
            "stage_title": entry.get("stage_name_bn", stage),
            "badge": entry.get("badge", "PIPELINE"),
            "text": text_content,
            "display_text": text_content,
            "live_screen_text": f"[JARVIS]: {text_content}",
            "audio_file": str(audio_file) if audio_file.exists() else None,
            "volume": volume
        }

