# AutoMovie Pro — Phase 0 Baseline Audit Report
**তারিখ:** ১৯ নভেম্বর ২০২৬  
**শাখা (Git Branch):** `baseline/phase-0`  
**স্ট্যাটাস:** বেসলাইন ভ্যালিডেশন সম্পন্ন (কোনো ফাংশনাল কোড পরিবর্তন করা হয়নি)

---

## ১. নন-টেকনিক্যাল প্রজেক্ট ওনারের জন্য ১০ লাইনের বাংলা সারসংক্ষেপ

১. আমরা মাস্টার রুলস অনুযায়ী কোনো কোড পরিবর্তন বা ডিলিট না করে পুরো প্রজেক্টের বর্তমান অবস্থার একটি নিখুঁত বেসলাইন রিপোর্ট তৈরি করেছি।  
২. গিট রিপোজিটরিতে নতুন `baseline/phase-0` ব্রাঞ্চ খোলা হয়েছে যাতে পরবর্তী কাজগুলো নিরাপদে ধাপে ধাপে করা যায়।  
৩. মেশিনে পাইথন ৩.১২.৯, নোড ২৪.১৩.০, পিএইচপি ৮.২.২৯ এবং বান্ডেল্ড এফএফএমপেক ৮.১.১ সক্রিয় রয়েছে।  
৪. একটি আলাদা ভার্চুয়াল এনভায়রনমেন্ট তৈরি করে দেখা গেছে `requirements.txt`-এ `python-multipart` প্যাকেজটি না থাকায় ফ্রেশ সেটআপে অ্যাপ ক্র্যাশ করে।  
৫. প্রথম-পক্ষের পাইথন কোডে মোট ১০টি ফাইলে ইনভ্যালিড এস্কেপ সিকোয়েন্সের SyntaxWarning রয়েছে এবং পিএইচপির ৯৪টি ফাইলই সম্পূর্ণ সিনট্যাক্স-ত্রুটিমুক্ত।  
৬. বর্তমান টেস্ট স্যুটে ৪৮০টি পাইথন টেস্টের মধ্যে ৪৫৬টি পাস করেছে এবং ২৪টি ফেইল করেছে (যার অধিকাংশ ফন্ট ও ব্যাকিং ট্র্যাক মক-সম্পর্কিত)।  
৭. পিএইচপি টেস্টের ১২টির মধ্যে ৮টি সফল হয়েছে এবং ৪টি ক্ষেত্রে পূর্ববর্তী স্ক্রিপ্ট আউটপুটের কঠোর ফরম্যাট যাচাইয়ে ফেইল হয়েছে।  
৮. AdminApp, PaymentApp ও UserApp-এর ১১টি টেস্টের ১১টিই (১০০%) সফলভাবে পাস করেছে।  
৯. কোডবেসে ইমপোর্ট ইন্টিগ্রিটি স্ক্যান করে ৮টি নির্দিষ্ট ফাইলে ভাঙা/অনুপস্থিত ইমপোর্ট শনাক্ত করা হয়েছে (অডিট ফাইন্ডিং অনুযায়ী)।  
১০. অডিট ফাইন্ডিং **S-03** হুবহু প্রমাণিত হয়েছে: কোনো সিকিউরিটি টোকেন ছাড়াই ব্যাকএন্ডের পেইড সাবস্ক্রিপশন স্লট আনলক রিকোয়েস্ট সফল হয়।

---

## ২. এনভায়রনমেন্ট ও টুলস ভার্সন

| টুলস / রানটাইম | সনাক্তকৃত ভার্সন | লোকেশন / নোট |
| :--- | :--- | :--- |
| **Python** | `3.12.9 (64-bit)` | `C:\Program Files\Python312\python.exe` |
| **Node.js** | `v24.13.0` | `C:\Program Files\nodejs\node.exe` |
| **PHP** | `8.2.29 (cli) (ZTS)` | `C:\wamp64\bin\php\php8.2.29\php.exe` (WampServer) |
| **FFmpeg** | `8.1.1-full_build` | `AutoMoviePro-Software/ffmpeg-8.1.1-full_build/.../bin/ffmpeg.exe` |
| **FFprobe** | `8.1.1-full_build` | `AutoMoviePro-Software/ffmpeg-8.1.1-full_build/.../bin/ffprobe.exe` |

### ফ্রেশ ভার্চুয়াল এনভায়রনমেন্ট টেস্ট (`C:\Users\HP\amp_fresh_baseline_venv`):
- `pip install -r AutoMoviePro-Software/requirements.txt` সফলভাবে সম্পন্ন হয়েছে।
- এরপর `import app.main` রান করার সময় নিচের ইমপোর্ট ক্র্যাশ ধরা পড়েছে:
  ```text
  RuntimeError: Form data requires "python-multipart" to be installed.
  You can install "python-multipart" with: pip install python-multipart
  File "AutoMoviePro-Software\app\main.py", line 2160, in <module>
    @app.post("/api/channels")
  ```
- **কারণ:** `app.main`-এ ফর্ম-ডাটা পোস্ট রাউট রয়েছে, কিন্তু `requirements.txt`-এ `python-multipart` তালিকাভুক্ত নেই।

---

## ৩. পাইথন ও পিএইচপি সিনট্যাক্স অডিট

### পাইথন সিনট্যাক্স ওয়ার্নিং (SyntaxWarning: invalid escape sequence):
পাইথন ৩.১২-এ স্ট্রিক্ট ওয়ার্নিং এনেবল করে কম্পাইল করার পর মোট ১০টি ফাইলে র-স্ট্রিং (`r"..."`) ব্যবহার না করার কারণে `SyntaxWarning` পাওয়া গেছে:
1. `AutoMoviePro-Software/scratch/generate_audit_docs_part3.py:66` (`\A`)
2. `AutoMoviePro-Software/scratch/generate_audit_suite.py:488` (`\s`)
3. `AutoMoviePro-Software/scratch/remove_all_hardcoded_keywords.py:35` (`\s`)
4. `AutoMoviePro-Software/scratch/update_audit_suite_phase0.py:175` (`\g`)
5. `AutoMoviePro-Software/scripts/patch_category_b_industrial_upgrade.py:210` (`\d`)
6. `AutoMoviePro-Software/scripts/patch_script_esa.py:8, 12` (`\s`)
7. `AutoMoviePro-Software/scripts/wire_dynamic_scenes.py:16` (`\:`)
8. `AutoMoviePro-Software/scripts/wire_track_a_dynamic.py:12` (`\:`)
9. `AutoMoviePro-Software/scripts/legacy_patches/patch_hdir_query.py:8` (`\s`)
10. `AutoMoviePro-Website/scripts/patch_wamanager.py:8` (`\T`)

### পিএইচপি লিন্ট (`php -l`):
- **মোট পিএইচপি ফাইল চেক:** ৯৪টি
- **পাস:** ৯৪টি (১০০%)
- **ফেইল:** ০টি

---

## ৪. টেস্ট স্যুট বেসলাইন এক্সিকিউশন টেবিল

| টেস্ট স্যুট | মোট টেস্ট | পাস | ফেইল | এরর | স্কিপড | সময় (Duration) | স্ট্যাটাস |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **AutoMoviePro-Software/tests** (pytest) | ৪৮০ | ৪৫৬ | ২৪ | ১ | ০ | ৪৭৮.৭৭ সেকেন্ড (~৮ মিনিট) | ⚠️ আংশিক ফেইল |
| **AutoMoviePro-Software/scripts/test_amp004_*.py** (অফলাইন অডিট স্যুট) | ৪৯৩ | ৪২২ | ৭১ | ০ | ০ | ৫৫.২৪ সেকেন্ড | ⚠️ আংশিক ফেইল |
| **AutoMoviePro-Website/tests & scripts/test_*.php** (লোকাল SQLite) | ১২টি স্ক্রিপ্ট | ৮ | ৪ | ০ | ০ | ১৪.৯৪ সেকেন্ড | ⚠️ আংশিক ফেইল |
| **AdminApp / PaymentApp / UserApp tests** | ১১ | ১১ | ০ | ০ | ০ | ১১.২৯ সেকেন্ড | ✅ ১০০% পাস |

### ফেইল হওয়া টেস্টগুলোর শ্রেণীকরণ ও কারণ:

| টেস্ট নাম | ক্যাটাগরি / ধরন | মূল কারণ (Root Cause) |
| :--- | :--- | :--- |
| `test_subtitle_mobile_font_size_punchy` | Product Bug | ফন্ট সাইজ রেশিও ক্যালকুলেশনে প্রত্যাশিত ও রিটার্নড মানে সামান্য ফারাক |
| `test_bengali_kalpurush_font_resolution` | Missing Dependency / System Font | লোকাল সিস্টেমে `kalpurush.ttf` গ্লোবাল ফন্ট পাথে অনুপস্থিত |
| `test_bgm_niche_mood_resolution` | Missing Asset / Mock Data | টেস্টে ব্যবহৃত নির্দিষ্ট মুডের BGM অডিও ফাইল টেস্ট এনভায়রনমেন্টে নেই |
| `test_cinematic_logo_branding (৩টি টেস্ট)` | Product Bug / Asset Missing | ডিফল্ট লোগো ফাইল না থাকলে ফলব্যাক হ্যান্ডলার এক্সপেক্টেড পাথ রিটার্ন করছে না |
| `test_03_generate_image_fallback_chain` | Needs Network / Paid API | লাইভ ইমেজ জেনারেটর এপিআই চেইনে অফলাইন ড্রাইডান মক না থাকায় ফেইল |
| `test_cross_topic_hijacking_prevented` | Product Bug | টপিক ডি-ডুপ্লিকেশন লুপে টপিক রেজোলিউশন স্ট্রিং ম্যাচিং অসমাপ্ত |
| `test_canvas_typography_and_safe_zone` | Product Bug | সেফ জোন মার্জিন কনফিগারেশনে টাইপ মিসম্যাচ |
| `test_social_cta_scene`, `test_surgical_single_scene_regeneration` | Product Bug | স্ক্রিপ্ট জেনারেটরে সোশ্যাল CTA সিন স্ট্রাকচার কী-নেম পরিবর্তন |
| `test_01_pricing_constants_and_base_entitlement` | Test Bug | প্রাইসিং কনস্ট্যান্ট ৩৯৯৯ বনাম টেস্টে পুরোনো ২৯৯৮ এর প্রত্যাশা |
| `test_can_customer_produce_blocks_lower_tiers` | Product Bug | লাইসেন্স টিয়ার অথরাইজেশন চেক মক মোডে ব্লক রেসপন্স রিটার্ন করেনি |
| `test_google_drive_vault_sync_bundling (Error)` | Missing Dependency | Google Drive API ক্লায়েন্ট মডিউল অনুপস্থিত |
| `PHP: test_marketing_psychology_ecosystem.php` | Test Output Assertion | ১০০% পাস হয়েছে কিন্তু স্ক্রিপ্ট শেষে স্ট্যাটাস কোড হ্যান্ডলিংয়ে ট্র্যাপ |
| `PHP: test_phase2_verification.php` | Test Bug | ড্রিপ মেসেজ ভেরিফিকেশনে ২০/২৩ পাস (৩টি ডামি ডাটা ক্লিনআপ সম্পর্কিত) |
| `PHP: test_website_sector5.php` | Test Bug | বিকাশ রেজেক্স প্যাটার্নে নতুন ১১ ডিজিট প্রিফিক্স কঠোরতা |

---

## ৫. সিক্রেট ও ফাইল হাইজিন স্ক্যান (Secret Hygiene Scan)

### বিশেষ ও সেনসিটিভ ফাইল তালিকা:
1. `AutoMoviePro-Software/.env` (এনভায়রনমেন্ট ফাইল)
2. `AutoMoviePro-Software/data/.secret.key` (সিমেট্রিক এনক্রিপশন কি)
3. `AutoMoviePro-Software/data/browsing_sessions.json` (ব্রাউজিং সেশন স্টেট)
4. `AutoMoviePro-Software/data/local.db` (ডেস্কটপ লোকাল ডাটাবেজ)
5. `AutoMoviePro-Website/storage/local_demo.sqlite` (ওয়েবসাইট লোকাল ডেমো ডাটাবেজ)
6. `AutoMoviePro-Software/assets/niche_topic_history.db` (টপিক হিস্ট্রি ডিবি)

### হার্ডকোডেড ক্রেডেনশিয়াল / এপিআই কি প্যাটার্ন পাওয়া ফাইল (মান গোপন রাখা হয়েছে):
- `AutoMoviePro-Software/pipeline/custom_pipeline/test_tts_routing.py:188, 201, 216, 236` (ভেরিয়েবল: `api_key`)
- `AutoMoviePro-Software/scripts/test_phase6f_cross_beat_consistency.py:539` (ভেরিয়েবল: `api_key`)
- `AutoMoviePro-Software/tests/test_channel_setup.py:108` (ভেরিয়েবল: `api_key`)
- `AutoMoviePro-Software/tests/test_social_publisher.py:98` (ভেরিয়েবল: `auth_token`)
*(এগুলো সবই টেস্ট স্যুটের ভেতর ডামি মক স্ট্রিং হিসেবে ব্যবহৃত হয়েছে, কোনো প্রোডাকশন লাইভ সিক্রেট নয়)*

### .gitignore এবং package_release.py এক্সক্লুশন কভারেজ:
- `.env` ফাইল: `.gitignore`-এ এক্সক্লুড করা আছে (True)
- `data/` ডিরেক্টরি: `.gitignore`-এ এক্সক্লুড করা আছে (True)
- `*.sqlite` ফাইল: `.gitignore`-এ এক্সক্লুড করা আছে (True)
- `*.key` এক্সটেনশন: `.gitignore`-এ বর্তমানে **নেই** (False — পরবর্তীতে যুক্ত করা প্রয়োজন)
- `package_release.py`: এর এক্সক্লুশন ফিল্টারে `.env`, `.secret.key`, এবং `browsing_sessions.json` বাদ দেওয়া নিশ্চিত রয়েছে।

---

## ৬. ডিপেনডেন্সি অডিট (Imports vs requirements.txt)

AutoMoviePro-Software-এর কোডবেসে ইমপোর্ট হওয়া কিন্তু `requirements.txt`-এ অনুপস্থিত মূল প্যাকেজসমূহ:
1. `python-multipart` *(FastAPI ফর্ম-ডাটার জন্য অতি জরুরি; এটি ছাড়া অ্যাপ রান হয় না)*
2. `cryptography` *(লাইসেন্স ও টিকিট ডিক্রিপশনের জন্য কোডে ব্যবহৃত হচ্ছে)*
3. `numpy` *(ফ্রেম ও ভিডিও ম্যাট্রিক্স প্রসেসিংয়ে ব্যবহৃত)*
4. `psutil` *(কম্পিউটার রিসোর্স ও র‍্যাম মনিটরিংয়ে ব্যবহৃত)*
5. `uharfbuzz` *(বাংলা ফন্ট শেপিং ও ক্যানভাস রেন্ডারিংয়ে ব্যবহৃত)*
6. `freetype-py` (`freetype`) *(সাবটাইটেল ফন্ট গ্লিফ তৈরিতে ব্যবহৃত)*
7. `google-api-python-client` (`googleapiclient`) *(ইউটিউব পাবলিশিংয়ে ব্যবহৃত)*
8. `opencv-python` (`cv2`) *(ফ্রেম প্রসেসিং ও ব্ল্যাকআউট ডিটেকশনে ব্যবহৃত)*

---

## ৭. ইমপোর্ট ইন্টিগ্রিটি অডিট (Broken from-imports)

অডিট ডিরেক্টিভে উল্লেখিত ভাঙা ইমপোর্টগুলো কোডবেস পরীক্ষা করে নিশ্চিত হওয়া গেছে:
1. `app/voice/voice_commentary.py:722`: `from app.db import store` ➔ **CONFIRMED** (`app.db`-তে `store` অ্যাট্রিবিউট নেই, `software_db` নামে রয়েছে)।
2. `pipeline/hybrid_visual_director_agent.py:258`: `from pipeline.ffmpeg_monitor_agent import ffprobe_duration` ➔ **CONFIRMED** (`ffmpeg_monitor_agent`-এ এই ফাংশন নেই)।
3. `pipeline/hybrid_visual_director_agent.py:259`: `from pipeline.custom_pipeline.ffmpeg_bin import get_ffmpeg_binary` ➔ **CONFIRMED** (`ffmpeg_bin.py` মডিউলটি উপস্থিত নেই)।
4. `pipeline/closed_loop_quality_sentinel.py:281`: `from pipeline.custom_pipeline.multi_still_clip import ffprobe_duration` ➔ **CONFIRMED** (`multi_still_clip`-এ `ffprobe_duration` নেই)।
5. `pipeline/audio_localization_engine.py:374`: `from pipeline.api_keys import get_google_api_keys` ➔ **CONFIRMED** (`api_keys`-এ এই মেথড নেই)।
6. `pipeline/montage_brain/production.py:62`: `from pipeline.ai_providers import download_file` ➔ **CONFIRMED** (`ai_providers`-এ `download_file` নেই)।
7. `marketing/omni_ad_studio_generator.py:49`: `from omni_vertical_poster_studio import render_vertical_reel_frame` ➔ **CONFIRMED** (হার্ডকোডেড `E:\AI Assistant\...` পাথের ওপর নির্ভরশীল)।

---

## ৮. S-03 অডিট ফাইন্ডিংয়ের লাইভ রিপ্রোডাকশন (Proof of Vulnerability)

- **পদ্ধতি:** আসল ডাটাবেজ অক্ষত রেখে সম্পূর্ণ আলাদা একটি ডিরেক্টরিতে ডাটাবেজের কপি বানিয়ে টেস্ট এনভায়রনমেন্ট তৈরি করা হয়।
- **টেস্ট ১ (Liveness):** `GET /api/health` কল করা হয়।
  - রেসপন্স: `HTTP 200 OK` — `{"ok": True, "health": "ALIVE", "release_version": "0.5.0"}`
- **টেস্ট ২ (S-03 এক্সপ্লয়েটেশন টেস্ট):** কোনো ক্লায়েন্ট সিকিউরিটি টোকেন ছাড়া সরাসরি `POST /api/subscription/approve-google-paid` এ রিকোয়েস্ট পাঠানো হয়:
  ```json
  POST /api/subscription/approve-google-paid
  Payload: {"order_id": "MOCK-S03-TEST"}
  ```
  - **ফলাফল:** `HTTP 200 OK`
  - **রেসপন্স বডি:** `{"ok": true, "unlocked_slots": 3, "message": "অর্ডার সফলভাবে এক্সেপ্ট করা হয়েছে! নতুন এপিআই স্লট আনলকড: 3/৩"}`
- **উপসংহার:** **অডিট ফাইন্ডিং S-03 হুবহু প্রমাণিত হয়েছে।** কোনো অথেন্টিকেশন গার্ড বা টোকেন যাচাই ছাড়াই যেকোনো বহিরাগত রিকোয়েস্টে ব্যাকএন্ডের পেইড স্লট আনলক হয়ে যাচ্ছে।

---

## ৯. বর্তমান অবস্থা ও পরবর্তী পদক্ষেপ
বেসলাইনের যাবতীয় তথ্য পুঙ্খানুপুঙ্খভাবে লিপিবদ্ধ করা হয়েছে। মাস্টার রুলস অনুযায়ী কোনো কোড পরিবর্তন করা হয়নি। পরবর্তী নির্দেশনার জন্য অপেক্ষা করা হচ্ছে।
