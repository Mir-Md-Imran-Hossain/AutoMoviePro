"""
Chernobyl 30-clip AV-sync training mission.
Per clip: TTS → Agnes from visualization → agent critique → regen if needed
→ human/meta audit → train rules. Saves side-by-side compare folder.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "output" / "Chernobyl_30_TrainCompare"
OUT.mkdir(parents=True, exist_ok=True)
COMPARE = OUT / "COMPARE_SIDE_BY_SIDE"
COMPARE.mkdir(parents=True, exist_ok=True)
CASES_PATH = OUT / "cases_30.json"
PROGRESS_PATH = OUT / "progress.json"
RESULTS_PATH = OUT / "results.jsonl"
REPORT_PATH = OUT / "TRAINING_REPORT.md"
LOCK_PATH = OUT / "chernobyl.lock"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUT / "chernobyl30.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("chernobyl30")

from app import db as store
from pipeline.av_sync_critic import (
    apply_training_rule,
    critique_scene_clip,
    meta_audit_critique,
    precheck_generation_prompt,
)
from pipeline.media_assets import generate_agnes_dialogue_clip
from pipeline.scene_builder import _mux_scene, resolve_bengali_fontfile
from pipeline.compose import ffprobe_duration
from pipeline.tts_google import synthesize_narration


def _cases() -> List[Dict[str, Any]]:
    raw = [
        (
            1,
            "এপ্রিলের ২৬ তারিখ, ১৯৮৬। ইউক্রেনের একটি ছোট শহর প্রিপিয়াত। রাত প্রায় ১টা ২৩ মিনিট। সবাই ঘুমিয়ে পড়েছে, আকাশ পরিষ্কার। তবে ওই রাতেই ইতিহাসের ভয়াবহতম বিপর্যয়ের ঘড়ি টিক-টিক করছিল।",
            "রাতের আকাশ, তারায় ভরা; দূর থেকে কোনো পারমাণবিক বিদ্যুৎ কেন্দ্রের ম্লান আলো; ঘুমন্ত শহরের উপর দিয়ে ধীরে ধীরে ক্যামেরা সরানো।",
            "Cinematic night sky full of stars over quiet Pripyat town, distant nuclear power plant glow on horizon, slow aerial camera drift, dark teal grade, no text no watermark",
            ["night sky", "stars", "nuclear plant glow", "Pripyat", "slow camera"],
            "hook",
        ),
        (
            2,
            "চেরনোবিল পারমাণবিক বিদ্যুৎ কেন্দ্রের চতুর্থ রিঅ্যাক্টরে সেই রাতে একটি নিরাপত্তা পরীক্ষা চলছিল। কিন্তু একটা ভুল, একটা সুইচ, আর একগুঁয়ে নিয়মের কারনে খেলা শুরু হয়ে গিয়েছিল মৃত্যুর সাথে।",
            "একটি কন্ট্রোল রুমের অ্যাবস্ট্রাক্ট ফুটেজ (ডায়াল, সুইচ, মানুষ দৌড়াচ্ছে); ডার্ক অ্যান্ড গ্রিটি টোন।",
            "Dark gritty Soviet control room, glowing dials and switches, blurred figures rushing, tension lighting, cinematic, no talking head, no text",
            ["control room", "switches", "dials", "dark gritty"],
            "reveal",
        ),
        (
            3,
            "থার্মাল এক্সপ্লোশন! রিঅ্যাক্টরের ভেতর তাপমাত্রা আকাশ ছোঁয়া। ১টা ২৩ মিনিট ৪৫ সেকেন্ডে পৃথিবী থেমে গেল। ধোঁয়া নয়, আগুন নয়—বেরোলো অদৃশ্য এক শত্রু, যার নাম তেজস্ক্রিয়তা।",
            "এক্সপ্লোশনের ড্রামাটিক ডিজিটাল আর্ট/অ্যানিমেশন; ধোঁয়ার পরিবর্তে উজ্জ্বল নীল আলোর ঝলকানি।",
            "Dramatic digital art thermal explosion inside reactor, bright blue radioactive light flash instead of smoke, cinematic shockwave, no text",
            ["thermal explosion", "blue light flash", "reactor", "radiation"],
            "metaphor",
        ),
        (
            4,
            "সে রাতে কয়েকজন ইঞ্জিনিয়ার দৌড়ে বেরিয়ে এল। তাদের চোখে আতঙ্ক। কিন্তু তারা জানত না, এই মারণ কণাগুলো বাতাসে মিশে গেছে—যা দেখার নয়, শুধু অনুভব করার বিষয়।",
            "মানুষের ছায়া দৌড়াচ্ছে; লাল-কমলা অগ্নিশিখার প্রতিফলন; শীতল রাতের কুয়াশা।",
            "Silhouettes of engineers running through cold night fog, red-orange fire glow reflecting, cinematic mystery, faceless preferred, no lip-sync",
            ["running silhouettes", "fire glow", "fog", "night"],
            "metaphor",
        ),
        (
            5,
            "দুপুরের পরেই প্রিপিয়াত শহরে লাগানো হলো মাইক। অজানা ভাষায় ঘোষণা: 'সবাই নিজ নিজ বাড়িতে থাকুন, জানালা বন্ধ করুন।' কিন্তু কোন ব্যাখ্যা নেই, কোন সতর্কবার্তা নেই।",
            "ফাঁকা শহরের রাস্তা; সোভিয়েত-যুগের একটি স্পিকার পোস্ট; নিস্তব্ধ আবাসিক ভবন।",
            "Empty Pripyat street, Soviet-era loudspeaker post, silent residential buildings, desaturated documentary grade, no text",
            ["empty street", "loudspeaker", "Soviet buildings", "silence"],
            "reveal",
        ),
        (
            6,
            "কিন্তু কয়েক ঘণ্টার মধ্যেই আতঙ্ক ছড়াল। কেউ বলল 'পারমাণবিক দুর্ঘটনা', কেউ বলল 'উড়ন্ত উল্কা'। সত্যিটা ছিল আরও বেশি ভয়াবহ—আমাদের নিজের হাতের তৈরি আগুন আমাদেরই গ্রাস করছিল।",
            "ভাঙা কাঁচ, উড়ে যাওয়া কাগজ; মানুষজন উদ্বিগ্ন মুখে রাস্তায় দাঁড়িয়ে; ফিসফিস শব্দের জন্য ভিজ্যুয়াল লো-লাইট।",
            "Broken glass and papers blowing, anxious people standing on street low-light, whispers atmosphere, cinematic documentary, no talking-head lip-sync",
            ["broken glass", "papers blowing", "anxious crowd", "low light"],
            "reveal",
        ),
        (
            7,
            "অগ্নিনির্বাপকরা প্রথম লাইনে গেল। তারা জানত না সেখানে সাধারণ আগুন নয়—তারা লড়ছিল অদৃশ্য এক দানবের সাথে, যার তেজস্ক্রিয়তা তখনই তাদের দেহে প্রবেশ করছিল।",
            "অগ্নিনির্বাপকদের সিলুয়েট; ধোঁয়া ও আলোর মধ্যে দিয়ে হাঁটা; পুরনো সোভিয়েত ফায়ার ট্রাক।",
            "Firefighter silhouettes walking through smoke and light, old Soviet fire truck, heroic documentary tone, no lip-sync avatar",
            ["firefighter silhouette", "smoke", "Soviet fire truck"],
            "hook",
        ),
        (
            8,
            "সেই কয়েক ঘণ্টায় ২৮ জনের বেশি অগ্নিনির্বাপক অ্যাকিউট রেডিয়েশন সিকনেসে আক্রান্ত হয়। তাদের শরীর ফুলে যাচ্ছিল, চুল পড়ে যাচ্ছিল। তবুও তারা পিছু হটেনি। কারণ তেজস্ক্রিয়তার চেয়েও বড় ছিল তাদের দায়িত্ব।",
            "হাসপাতালের অ্যাবস্ট্রাক্ট ফুটেজ; সাদা শিটে ঢাকা মানুষ; ধূসর, বিষণ্ণ পরিবেশ।",
            "Abstract hospital ward, figures under white sheets, gray somber atmosphere, respectful documentary, no graphic gore, no text",
            ["hospital", "white sheets", "somber", "gray"],
            "reveal",
        ),
        (
            9,
            "ইউক্রেন, বেলারুশ, এমনকি স্ক্যান্ডিনেভিয়া পর্যন্ত পৌঁছালো সেই বিষাক্ত মেঘ। প্রকৃতি নিঃশব্দে জানিয়ে দিল—এটা শুধু একটি বিদ্যুৎ কেন্দ্রের দুর্ঘটনা নয়, এটা সভ্যতার আত্মহত্যার এক নৃশংস ডকুমেন্টারি।",
            "ধূসর মেঘলা আকাশ; দূর থেকে ধোঁয়ার পথ; উড়ন্ত পাখির পালা হঠাৎ ছত্রভঙ্গ হয়ে যাওয়া।",
            "Gray cloudy sky, distant smoke trail, flock of birds suddenly scattering, wide cinematic landscape, no text",
            ["gray clouds", "smoke trail", "scattering birds"],
            "metaphor",
        ),
        (
            10,
            "ওই ঘটনার মাত্র ৩৬ ঘণ্টা পর সোভিয়েত ইউনিয়ন স্বীকার করল—'আমরা কিছু জানি না, আমরা কিছু বলতে চাই না।' তথ্যের অন্ধকারে পৃথিবী আরও আতঙ্কিত হলো। কারণ অজানা সত্যের চেয়ে ভয়ঙ্কর কিছু নেই।",
            "ক্রেমলিনের অ্যাবস্ট্রাক্ট ছবি; টেলিভিশনের স্থির-শব্দ (স্ট্যাটিক); বন্ধ দরজা।",
            "Abstract Kremlin silhouette, TV static noise visual, closed heavy doors, cold secrecy mood, no text no watermark",
            ["Kremlin", "TV static", "closed doors", "secrecy"],
            "reveal",
        ),
        (
            11,
            "এবার আসা যাক 'লিকুইডেটরস'—যারা রাজি হয়েছিল মৃত্যুর মুখোমুখি দাঁড়াতে। তারা সারা বিশ্ব থেকে ছুটে এসেছিল। নাম ছিল না, পরিচয় ছিল না, শুধু ছিল একটি মিশন: উৎসটি ঢেকে ফেলা।",
            "পুরুষদের দল হ্যাজমেট স্যুট পরে হাঁটছে; ক্যামেরা তাদের পিছন থেকে অনুসরণ করছে; ধূসর-কালো মাটির দৃশ্য।",
            "Group of liquidators in hazmat suits walking away, camera follows from behind, gray-black radioactive ground, documentary cinematic",
            ["hazmat suits", "liquidators walking", "gray ground"],
            "hook",
        ),
        (
            12,
            "হেলিকপ্টার থেকে ফেলা হলো বালি, বোরন, কাদামাটি। ৫০০০ টনের বেশি উপাদান ফেলা হলো সেই খোলা চুল্লির ভেতর—যেন এক জ্বলন্ত আগ্নেয়গিরির মুখে থুতু ফেলার চেষ্টা।",
            "হেলিকপ্টার থেকে ধোঁয়ার মধ্যে কিছু ফেলা হচ্ছে; বড় বড় ব্যাগ বাতাসে উড়ছে; ড্রামাটিক শট।",
            "Helicopter dropping sand bags into smoking open reactor, dramatic aerial shot, bags falling through smoke, cinematic",
            ["helicopter", "dropping bags", "smoke", "reactor"],
            "metaphor",
        ),
        (
            13,
            "কিন্তু সেই ঢাকনা তৈরি করতে গেল আরও ২০০,০০০ মানুষের জীবন ও স্বাস্থ্য। লিকুইডেটরদের কারো কারো হাতে বাঁচার সময় ছিল মাত্র কয়েক সপ্তাহ। তবু তারা শুধু কাজ করে গেল—নিঃশব্দে, অভিযোগহীন।",
            "ক্লান্ত মানুষের মুখ; হাতের ক্লোজ-আপ; ধীরগতির অনুভূতি তৈরি করা ফুটেজ।",
            "Slow-motion close-up of exhausted worker hands and weary faces, silent sacrifice mood, cinematic documentary, no lip-sync talking head",
            ["exhausted hands", "weary face", "slow motion"],
            "reveal",
        ),
        (
            14,
            "তেজস্ক্রিয়তার প্রভাবে চেরনোবিলের কাছাকাছি গ্রামগুলো থেকে মানুষ সরিয়ে নেওয়া হলো। তারা পিছনে তাকিয়ে দেখল—যে শহরে বড় হয়েছেন, সেই শহর ধীরে ধীরে বাসিন্দাশূন্য হয়ে যাচ্ছে।",
            "একটি পুরনো বাস বা ট্রেনে মানুষ উঠছে; কাঁদতে কাঁদতে পেছনে তাকানো; খালি স্ট্রিট।",
            "People boarding old Soviet bus looking back crying, emptying streets of home town, emotional documentary cinematic",
            ["evacuation bus", "looking back", "empty street"],
            "reveal",
        ),
        (
            15,
            "প্রিপিয়াত শহর এখন ভূতের শহর। দোলনাচড়া থেমে গেছে, স্কুলের ঘণ্টা আর বাজে না। কেবল বাতাস আর ওই অদৃশ্য বিষ—যা আজও অদৃশ্য কিন্তু থেমে নেই।",
            "পরিত্যক্ত ফেরিস হুইল; মরিচা পড়া দোলনা; ধুলো ওড়া ফাঁকা খেলার মাঠ।",
            "Abandoned Pripyat Ferris wheel, rusty swings, dusty empty playground, ghost town atmosphere, cinematic",
            ["Ferris wheel", "rusty swings", "empty playground", "ghost town"],
            "metaphor",
        ),
        (
            16,
            "আন্তর্জাতিক বিজ্ঞানীরা পরে বলেছেন—চেরনোবিলের তেজস্ক্রিয়তা হিরোশিমার ৪০০টি বোমার সমান। কিন্তু এখানে কোনো বোমা পড়েনি, পড়েছে মানুষের অদক্ষতা আর অহংকার।",
            "গ্রাফ, চার্ট, পারমাণবিক কণার অ্যানিমেশন; বৈজ্ঞানিক ল্যাবের ফুটেজ।",
            "Scientific lab with radiation particle animation, charts and graphs glowing teal, cinematic science grade, no readable fake text",
            ["science lab", "particle animation", "charts", "radiation"],
            "reveal",
        ),
        (
            17,
            "সে ঘটনার কয়েক মাস পর, গ্রীষ্ম এলো কিন্তু ফুল ফোটেনি। পাতা হলুদ হয়ে গেল। গাভির দুধ বিক্রি বন্ধ, ফলমূল বিষাক্ত। প্রকৃতি নিজেই সেই অপরাধের সাক্ষী হয়ে গেল।",
            "শুকনো গাছ, মরা পাতা; বৃষ্টির ফোঁটা ধূসর মাটিতে পড়ছে; সূর্যের আলো কুয়াশার ভেতর দিয়ে ফুটেছে।",
            "Dead trees yellow leaves, rain on gray soil, sunlight through toxic fog, nature dying cinematic",
            ["dead trees", "yellow leaves", "rain", "fog sun"],
            "metaphor",
        ),
        (
            18,
            "একটি শিশুর জন্ম হলো চেরনোবিল থেকে মাত্র কয়েক কিলোমিটার দূরে। তার শরীরে ছিল তেজস্ক্রিয়তার ছাপ। সে চোখ মেলল এক ভয়াবহ পৃথিবীতে—যেখানে নিরাপত্তা ছিল শুধু কাগজে-কলমে।",
            "হাসপাতালের নবজাতক ওয়ার্ডের ঝাপসা ফুটেজ; শিশুর হাত; মায়ের অশ্রুভেজা চোখ।",
            "Soft-focus hospital newborn ward, baby hand close-up, mother's tearful eyes, respectful emotional documentary, no graphic medical detail",
            ["newborn ward", "baby hand", "mother tears"],
            "reveal",
        ),
        (
            19,
            "অন্য দিকে ইউরোপের অনেক দেশ খাদ্য আমদানি বন্ধ করে দিল। এক অদৃশ্য সীমানা তৈরি হলো—এই সীমানা রাজনীতির নয়, বরং মৃত্যুর। যতই পালিয়ে যাওয়া যায়, তেজস্ক্রিয়তা তো বাতাসে মিশে থাকে।",
            "মানচিত্রে ছড়িয়ে পড়া লাল দাগ; বন্দর বা কাস্টমসের ছবি; মানুষ মাস্ক পরে আছে।",
            "Europe map with spreading red radiation stain, port customs checkpoint, people in masks, cinematic documentary",
            ["map red stain", "customs port", "masks"],
            "reveal",
        ),
        (
            20,
            "১৯৮৭ সালে বিদ্যুৎ কেন্দ্রের চারপাশে তৈরি করা হলো 'সারকোফাগাস'—একটি বিশাল কংক্রিটের ঢাকনা। কয়েক হাজার মানুষ মিলে তৈরি করল, কিন্তু এই ঢাকনা পারে কি ওই মৃত্যুর হাসি আটকাতে?",
            "ভারী কংক্রিট ব্লক নামানো; ক্রেন ও নির্মাণশ্রমিক; বিশাল ধূসর কাঠামোর দিকে ক্যামেরা প্যান।",
            "Heavy concrete blocks lowered by crane onto Chernobyl sarcophagus, construction workers, camera pan across huge gray structure",
            ["concrete blocks", "crane", "sarcophagus", "construction"],
            "reveal",
        ),
        (
            21,
            "বিজ্ঞানীরা ঘোষণা করলেন—এই রিঅ্যাক্টরের নিচে এখনও ২০০ টন পারমাণবিক জ্বালানি জমে আছে। সেটা যে কোনো সময় বিক্রিয়া করতে পারে। অর্থাৎ, চেরনোবিলের কাহিনি এখনও শেষ হয়নি।",
            "ডায়াগ্রাম, ইউরেনিয়াম কণার অ্যানিমেশন; ইনফ্রারেড ক্যামেরার ফুটেজ; ডার্ক টানেল।",
            "Dark tunnel under reactor, infrared glow of uranium fuel mass, particle diagram animation, eerie science mystery grade",
            ["uranium animation", "infrared", "dark tunnel", "reactor fuel"],
            "metaphor",
        ),
        (
            22,
            "প্রায় ৩৫ বছর পর—২০২১ সালে ইউক্রেন, রাশিয়া, যুক্তরাষ্ট্র ও ইউরোপীয় ইউনিয়ন মিলে পুরনো সারকোফাগাসকে আরও শক্তিশালী নিউ সেফ কনফাইনমেন্ট দিয়ে প্রতিস্থাপন করল। কিন্তু সেটাও কি চিরস্থায়ী সমাধান?",
            "মেশিনারি, স্টিলের গম্বুজ; অ্যাবস্ট্রাক্ট ইঞ্জিনিয়ারিং ফুটেজ; চলমান মানুষ ও ক্রেন।",
            "New Safe Confinement steel arch dome machinery, engineering footage, workers and cranes, modern industrial cinematic",
            ["steel dome", "machinery", "crane", "New Safe Confinement"],
            "reveal",
        ),
        (
            23,
            "কারণ তেজস্ক্রিয়তার আয়ু ২৪,০০০ বছর। ২৪,০০০ বছর! সেই সময়ের মাপকাঠিতে আমাদের সভ্যতা কতবার উত্থিত ও ধ্বংস হবে, কে জানে?",
            "কসমিক টাইমল্যাপ্স; নক্ষত্রপুঞ্জ; পৃথিবী দূর থেকে আবর্তিত হচ্ছে; সময়ের অ্যাবস্ট্রাক্ট ধারণা।",
            "Cosmic timelapse star fields, Earth rotating from space, abstract time passage, epic cinematic scale",
            ["cosmic timelapse", "stars", "Earth from space", "time"],
            "metaphor",
        ),
        (
            24,
            "এই বিপর্যয় শুধু এক দেশের নয়, পুরো মানবজাতির আত্মার কালো দাগ। এটি প্রমাণ করে যে প্রযুক্তি যত শক্তিশালী, তার দায়িত্বও তত বেশি। এবং সে দায়িত্ব পালনে আমরা কতটা ব্যর্থ।",
            "ধীরে ধীরে ঘুরতে থাকা গ্লোব; তার উপর কালো দাগ; ধোঁয়ার আভাস; ম্লান সূর্যালোক।",
            "Slowly rotating globe with dark stain over Europe, smoke haze, dim sunlight, symbolic cinematic",
            ["globe", "dark stain", "smoke haze", "dim sun"],
            "metaphor",
        ),
        (
            25,
            "তথ্যচিত্র, সিনেমা, আত্মজীবনী—চেরনোবিল নিয়ে হাজারো কাজ হয়েছে। কিন্তু প্রতিটি কাজেই সেই একই প্রশ্ন থেকে যায়: 'আমরা কি আবারও সেই ভুল করতে পারি?'",
            "ক্যামেরার রিল, ফিল্ম রিল ঘুরছে; পুরনো সংবাদপত্র; বইয়ের স্তূপ।",
            "Spinning film reels, old newspapers stack, books about disaster, archival documentary mood, no readable fake headlines",
            ["film reel", "newspapers", "books"],
            "reveal",
        ),
        (
            26,
            "বর্তমানে চেরনোবিলের জোন একটি পর্যটন কেন্দ্রে পরিণত হয়েছে। পর্যটকরা ছবি তোলে, সেলফি দেয়। কিন্তু প্রকৃতি সেখানে ধীরে ধীরে ফিরে এসেছে—নেকড়ে, ভালুক, এমনকি বিরল প্রজাতির পাখিও দেখা যায়।",
            "ভাঙা জানালার ভেতর দিয়ে ঘাস গজানো; একটি নেকড়ে দূর থেকে তাকিয়ে আছে; সবুজ প্রকৃতির সাথে ধ্বংসের মিশেল।",
            "Grass growing through broken window, wolf watching from distance, green nature reclaiming ruins of Chernobyl zone",
            ["broken window grass", "wolf", "nature reclaiming ruins"],
            "metaphor",
        ),
        (
            27,
            "কিন্তু সেই সবুজ প্রকৃতিও তেজস্ক্রিয়। ফুলগুলো যেন কালো রঙ ধারণ করেছে। প্রাণীরা শরীরে বহন করছে সিজিয়াম-১৩৭। প্রকৃতি বাঁচার চেষ্টা করছি, কিন্তু সে বাঁচা কি আদৌ বাঁচা?",
            "অদ্ভুত রঙের ফুল; ক্যামেরা ধীরে ধীরে জুম ইন করছে; অন্ধকার বন।",
            "Strange dark-colored flowers in radioactive forest, slow zoom-in, eerie green-black woodland, cinematic mystery",
            ["strange flowers", "dark forest", "slow zoom", "radiation nature"],
            "metaphor",
        ),
        (
            28,
            "এই গল্পের সবচেয়ে মর্মান্তিক অংশ হলো—আমরা শিখিনি। ফুকুশিমা, থ্রি মাইল আইল্যান্ড—একই প্যাটার্ন। একই অহংকার। একই 'আমার সাথে হবে না' ভাবনা।",
            "ফুকুশিমার ধোঁয়া; অন্য দুর্ঘটনার স্টক ফুটেজ; আবহাওয়ার মানচিত্র; টাইমলাইন।",
            "Fukushima smoke plume montage with Three Mile Island metaphor, weather radiation map, timeline documentary style, no text overlays",
            ["Fukushima smoke", "radiation map", "timeline", "nuclear accidents"],
            "reveal",
        ),
        (
            29,
            "চেরনোবিলের পথে আজও মোমবাতি জ্বলে। যারা মৃত তাদের জন্য, যারা বেঁচে আছে কিন্তু প্রতিদিন মৃত্যুর সাথে লড়ে তাদের জন্য। আর যারা এখনও বোঝেনি তাদের জাগানোর জন্য।",
            "স্মৃতিসৌধে মোমবাতি; অজ্ঞাত মানুষের ছবি; ধোঁয়ার মিছিল; রাতের আকাশে তারা।",
            "Memorial candles burning, silent photo frames, smoke from procession, night sky stars, solemn remembrance cinematic",
            ["candles", "memorial", "stars", "remembrance"],
            "outro",
        ),
        (
            30,
            "পরিশেষে, এই একটি কথাই বলার থাকে—পারমাণবিক শক্তি যেমন আলো দিতে পারে, তেমনি অন্ধকারও। সেই অন্ধকার যেন আমাদের প্রতিটি সিদ্ধান্তকে প্রজ্বলিত রাখে। কারণ পৃথিবীটি আমাদের একমাত্র বাড়ি, আর তেজস্ক্রিয়তা জানে না সীমানা। শুনে ধন্যবাদ।",
            "পৃথিবী স্পেস থেকে; ধীরে ধীরে আলো ফুটছে; শান্ত সমুদ্র, উদীয়মান সূর্য; সম্পূর্ণ ফেড-টু-ব্ল্যাক।",
            "Earth from space slowly lit by sunrise, calm ocean horizon, warm hope then fade to black, cinematic ending, no text no watermark",
            ["Earth from space", "sunrise", "calm ocean", "fade to black"],
            "outro",
        ),
    ]
    # Fix typo in clip 27 narration from user (বাঁচার চেষ্টা করছি -> করছে) for TTS quality
    cases = []
    for cid, narr, vis_bn, prompt, kws, element in raw:
        if cid == 27:
            narr = narr.replace("বাঁচার চেষ্টা করছি", "বাঁচার চেষ্টা করছে")
        cases.append(
            {
                "id": cid,
                "niche": "History Channel",
                "topic": "Chernobyl Disaster Documentary",
                "element": element,
                "narration": narr,
                "visualization_bn": vis_bn,
                "exact_ai_video_prompt": prompt,
                "visual_prompt": prompt,
                "visual_query": " ".join(kws[:3]),
                "keyword_triggers": kws,
            }
        )
    return cases


def _acquire_lock() -> None:
    if LOCK_PATH.exists():
        try:
            old = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
            pid = int(old.get("pid") or 0)
            import os

            os.kill(pid, 0)
            raise SystemExit(f"Another chernobyl30 running pid={pid}")
        except SystemExit:
            raise
        except Exception:
            pass
    LOCK_PATH.write_text(
        json.dumps({"pid": __import__("os").getpid(), "ts": datetime.now().isoformat()}),
        encoding="utf-8",
    )


def _release_lock() -> None:
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _save_progress(p: Dict[str, Any]) -> None:
    p["updated_at"] = datetime.now().isoformat(timespec="seconds")
    PROGRESS_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_result(row: Dict[str, Any]) -> None:
    with RESULTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _copy_compare(
    clip_dir: Path,
    cid: int,
    first_path: Optional[Path],
    final_path: Optional[Path],
    row: Dict[str, Any],
) -> None:
    dest = COMPARE / f"clip_{cid:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    if first_path and first_path.exists():
        shutil.copy2(first_path, dest / "01_FIRST_GENERATION.mp4")
    if final_path and final_path.exists():
        shutil.copy2(final_path, dest / "02_FINAL_AFTER_AGENT.mp4")
    # also copy audio
    for audio in clip_dir.glob("narration.*"):
        shutil.copy2(audio, dest / f"00_AUDIO{audio.suffix}")
        break
    # prompts & critiques
    for name in (
        "scene_00_precheck.json",
        "scene_00_prompt_attempt1.txt",
        "scene_00_prompt_attempt2.txt",
        "scene_00_prompt_attempt3.txt",
        "scene_00_prompt_attempt4.txt",
        "scene_00_critique_attempt1.json",
        "scene_00_critique_attempt2.json",
        "scene_00_critique_attempt3.json",
        "scene_00_critique_attempt4.json",
        "meta_audit.json",
        "my_meta_notes.json",
        "case.json",
        "result.json",
    ):
        src = clip_dir / name
        if src.exists():
            shutil.copy2(src, dest / name)
    readme = f"""# ক্লিপ {cid:02d} — তুলনা গাইড

## কী দেখবেন
1. `00_AUDIO.*` — Google TTS অডিও
2. `01_FIRST_GENERATION.mp4` — এজেন্টের **প্রথম** Agnes ক্লিপ (muxed)
3. `02_FINAL_AFTER_AGENT.mp4` — এজেন্ট অ্যানালাইসিস/রিজেনের **শেষ** ক্লিপ

## এজেন্ট ফলাফল
- score: {row.get('agent_score')}
- passed: {row.get('agent_passed')}
- attempts: {row.get('attempts')}
- issues: {json.dumps(row.get('issues') or [], ensure_ascii=False)}
- meta_error: {row.get('meta_error')}
- training_rule_added: {row.get('training_rule_added') or '(none)'}

## ভিজুয়ালাইজেশন (বাংলা)
{row.get('visualization_bn') or ''}
"""
    (dest / "README_BN.md").write_text(readme, encoding="utf-8")


def run_one(case: Dict[str, Any], channel: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    cid = int(case["id"])
    work = OUT / f"clip_{cid:02d}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "case.json").write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

    # TTS
    audio_base = work / "narration"
    audio = None
    for ext in (".m4a", ".wav", ".mp3"):
        cand = audio_base.with_suffix(ext)
        if cand.exists() and cand.stat().st_size > 1000:
            audio = cand
            break
    if audio is None:
        audio = synthesize_narration(
            case["narration"],
            audio_base,
            google_api_keys=keys,
            voice_name="Kore",
            language_hint="bn",
        )

    dur = max(2.0, ffprobe_duration(audio))
    prompt = case["exact_ai_video_prompt"]
    keywords = case.get("keyword_triggers") or []
    niche = case["niche"]
    element = case["element"]
    narration = case["narration"]

    # Precheck
    pre = precheck_generation_prompt(
        narration_bn=narration,
        exact_ai_video_prompt=prompt,
        keyword_triggers=keywords,
        niche=niche,
        element=element,
        product_name=case["topic"],
        google_api_keys=keys,
    )
    (work / "scene_00_precheck.json").write_text(
        json.dumps(pre, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not pre.get("passed") and pre.get("fixed_prompt"):
        prompt = str(pre["fixed_prompt"]).strip()
        logger.info("Clip %s precheck fixed prompt score=%s", cid, pre.get("prompt_score"))

    first_mux: Optional[Path] = None
    final_mux: Optional[Path] = None
    best_score = -1
    best_critique: Dict[str, Any] = {}
    last_critique: Dict[str, Any] = {}
    max_attempts = 3  # 1 + 2 regen

    for attempt in range(1, max_attempts + 1):
        agnes_out = work / (
            f"agnes_00_{element}.mp4" if attempt == 1 else f"agnes_00_{element}_r{attempt}.mp4"
        )
        if agnes_out.exists() and attempt > 1:
            try:
                agnes_out.unlink()
            except Exception:
                pass

        path = generate_agnes_dialogue_clip(
            api_key=channel.get("agnes_api") or "",
            product_name=case["topic"],
            element=element,
            visual_prompt=prompt,
            out_path=agnes_out,
            narration_hint=narration,
            size="1080x1920",
            duration_hint=min(dur, 8.0),
            max_poll=40,
            override_prompt=prompt,
            niche=niche,
            keyword_triggers=keywords,
            use_catalog_image=False,
        )
        if not path or not path.exists():
            raise RuntimeError(f"Agnes failed for clip {cid} attempt {attempt}")

        mux = work / f"scene_00_{element}_a{attempt}.mp4"
        _mux_scene(
            video_src=path,
            narration_audio=audio,
            dest=mux,
            duration=dur,
            size="1080x1920",
            subtitle_text=narration[:80],
        )
        (work / f"scene_00_prompt_attempt{attempt}.txt").write_text(prompt, encoding="utf-8")
        if attempt == 1:
            first_mux = mux

        critique = critique_scene_clip(
            video_path=mux,
            audio_path=audio,
            narration_bn=narration,
            keyword_triggers=keywords,
            exact_ai_video_prompt=prompt,
            niche=niche,
            element=element,
            google_api_keys=keys,
            product_name=case["topic"],
        )
        # Quota: re-critique same clip, don't fake-fail regen
        if (critique.get("raw") or {}).get("fallback"):
            logger.warning("Clip %s critic outage — cool 60s and retry critique", cid)
            time.sleep(60)
            critique = critique_scene_clip(
                video_path=mux,
                audio_path=audio,
                narration_bn=narration,
                keyword_triggers=keywords,
                exact_ai_video_prompt=prompt,
                niche=niche,
                element=element,
                google_api_keys=keys,
                product_name=case["topic"],
            )

        (work / f"scene_00_critique_attempt{attempt}.json").write_text(
            json.dumps(critique, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        last_critique = critique
        score = int(critique.get("match_score") or 0)
        logger.info(
            "Clip %s attempt %s score=%s passed=%s issues=%s",
            cid,
            attempt,
            score,
            critique.get("passed"),
            critique.get("issues"),
        )
        if score > best_score:
            best_score = score
            best_critique = critique
            final_mux = mux

        if critique.get("passed"):
            final_mux = mux
            break
        if (critique.get("raw") or {}).get("fallback"):
            final_mux = mux
            break

        revised = str(critique.get("revised_prompt") or "").strip()
        if revised and attempt < max_attempts:
            prompt = revised[:900]
            continue
        break

    # Copy final canonical
    final_path = work / f"scene_00_{element}.mp4"
    if final_mux and final_mux.exists():
        shutil.copy2(final_mux, final_path)

    # Meta audit (second opinion)
    meta: Dict[str, Any] = {}
    training_rule = ""
    if final_path.exists() and best_critique:
        meta = meta_audit_critique(
            video_path=final_path,
            narration_bn=narration,
            agent_critique=best_critique,
            keyword_triggers=keywords,
            google_api_keys=keys,
        )
        (work / "meta_audit.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        training_rule = str(meta.get("training_rule") or "").strip()
        if meta.get("agent_was_correct") is False and training_rule:
            apply_training_rule(training_rule, source=f"chernobyl_clip_{cid}")

    # My structured meta notes (for training mission visibility)
    my_notes = {
        "clip_id": cid,
        "agent_score": best_critique.get("match_score"),
        "agent_passed": best_critique.get("passed"),
        "agent_issues": best_critique.get("issues"),
        "meta_correct": meta.get("agent_was_correct"),
        "meta_error_type": meta.get("error_type"),
        "meta_explanation": meta.get("explanation"),
        "training_rule": training_rule,
        "visualization_bn": case.get("visualization_bn"),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    (work / "my_meta_notes.json").write_text(
        json.dumps(my_notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    passed = bool(best_critique.get("passed")) and meta.get("error_type") not in {
        "false_pass",
        "missed_critical",
    }
    attempts = len(list(work.glob("scene_00_critique_attempt*.json")))
    row = {
        "id": cid,
        "element": element,
        "agent_score": best_critique.get("match_score"),
        "agent_passed": best_critique.get("passed"),
        "issues": best_critique.get("issues") or [],
        "attempts": attempts,
        "meta_correct": meta.get("agent_was_correct"),
        "meta_error": meta.get("error_type"),
        "final_passed": passed,
        "training_rule_added": training_rule,
        "visualization_bn": case.get("visualization_bn"),
        "first_clip": str(first_mux) if first_mux else "",
        "final_clip": str(final_path) if final_path.exists() else "",
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    (work / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    _copy_compare(work, cid, first_mux, final_path if final_path.exists() else final_mux, row)
    return row


def _write_report(progress: Dict[str, Any]) -> None:
    rows = []
    if RESULTS_PATH.exists():
        for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    by = {int(r["id"]): r for r in rows if "id" in r and "error" not in r}
    lines = [
        "# Chernobyl ৩০-ক্লিপ ট্রেনিং রিপোর্ট",
        "",
        f"- সম্পন্ন: {len(progress.get('completed_ids') or [])}/30",
        f"- পাস: {progress.get('passed')}",
        f"- ফেইল: {progress.get('failed')}",
        f"- এজেন্ট ভুল (meta): {progress.get('agent_errors')}",
        "",
        "## তুলনা ফোল্ডার",
        f"`{COMPARE}` — প্রতিটি ক্লিপে `01_FIRST_GENERATION.mp4` vs `02_FINAL_AFTER_AGENT.mp4`",
        "",
        "## ক্লিপ সারাংশ",
        "",
        "| ক্লিপ | স্কোর | পাস | অ্যাটেম্পট | মেটা | ট্রেনিং রুল |",
        "|---|---:|:---:|:---:|:---:|---|",
    ]
    for i in range(1, 31):
        r = by.get(i) or {}
        lines.append(
            f"| {i:02d} | {r.get('agent_score','-')} | {r.get('final_passed','-')} | "
            f"{r.get('attempts','-')} | {r.get('meta_error','-')} | "
            f"{(r.get('training_rule_added') or '')[:60]} |"
        )
    lines.append("")
    lines.append("## শেখা নিয়মসমূহ")
    from pipeline.av_sync_critic import load_training_rules

    for rule in load_training_rules():
        lines.append(f"- {rule}")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    (COMPARE / "INDEX_BN.md").write_text(
        "\n".join(
            [
                "# সাইড-বাই-সাইড তুলনা ইনডেক্স",
                "",
                "প্রতিটি `clip_XX` ফোল্ডারে:",
                "1. প্রথম জেনারেশন",
                "2. এজেন্ট ঠিক করার পর ফাইনাল",
                "3. অডিও + critique JSON",
                "",
                f"মোট পাস: {progress.get('passed')} / 30",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    _acquire_lock()
    try:
        if not CASES_PATH.exists():
            cases = _cases()
            CASES_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

        channels = store.list_channels()
        if not channels:
            logger.error("No channel")
            return 2
        ch = channels[0]
        keys = [k for k in [ch.get("google_api_1") or "", ch.get("google_api_2") or ""] if k.strip()]
        if not keys or not (ch.get("agnes_api") or "").strip():
            logger.error("Missing Google or Agnes keys")
            return 2

        # Seed history/science training rules for this mission
        apply_training_rule(
            "Chernobyl/history beats: prefer documentary metaphors matching narration (reactor, Pripyat Ferris wheel, hazmat, blue radiation flash) — never gadget product B-roll.",
            source="chernobyl_mission_seed",
        )
        apply_training_rule(
            "Silent cinematic humans OK for history/disaster niches; talking-head lip-sync still forbidden.",
            source="chernobyl_mission_seed",
        )

        progress = {
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "completed_ids": [],
            "passed": 0,
            "failed": 0,
            "agent_errors": 0,
            "last_id": 0,
        }
        if PROGRESS_PATH.exists():
            progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        done = set(progress.get("completed_ids") or [])

        logger.info("Chernobyl 30 start: %s/30 done", len(done))
        for case in cases:
            cid = int(case["id"])
            if cid in done:
                continue
            logger.info("===== CLIP %s/30 %s =====", cid, case["element"])
            try:
                row = run_one(case, ch, keys)
                _append_result(row)
                done.add(cid)
                progress["completed_ids"] = sorted(done)
                progress["last_id"] = cid
                if row.get("final_passed"):
                    progress["passed"] = int(progress.get("passed") or 0) + 1
                else:
                    progress["failed"] = int(progress.get("failed") or 0) + 1
                if row.get("meta_correct") is False:
                    progress["agent_errors"] = int(progress.get("agent_errors") or 0) + 1
                _save_progress(progress)
                _write_report(progress)
                logger.info(
                    "CLIP %s done score=%s final=%s meta=%s",
                    cid,
                    row.get("agent_score"),
                    row.get("final_passed"),
                    row.get("meta_error"),
                )
                time.sleep(35)  # Agnes ~2/min + Google breathe
            except Exception as exc:
                logger.error("CLIP %s FAILED: %s\n%s", cid, exc, traceback.format_exc()[-600:])
                _append_result({"id": cid, "error": str(exc), "ts": datetime.now().isoformat()})
                progress["failed"] = int(progress.get("failed") or 0) + 1
                progress["last_id"] = cid
                work = OUT / f"clip_{cid:02d}"
                work.mkdir(parents=True, exist_ok=True)
                fails = work / "_hard_fails.txt"
                n = int(fails.read_text(encoding="utf-8")) + 1 if fails.exists() else 1
                fails.write_text(str(n), encoding="utf-8")
                if n >= 3:
                    done.add(cid)
                    progress["completed_ids"] = sorted(done)
                _save_progress(progress)
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                    time.sleep(60)
                else:
                    time.sleep(15)

        _write_report(progress)
        logger.info(
            "Chernobyl 30 finished passed=%s failed=%s agent_errors=%s",
            progress.get("passed"),
            progress.get("failed"),
            progress.get("agent_errors"),
        )
        return 0
    finally:
        _release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
