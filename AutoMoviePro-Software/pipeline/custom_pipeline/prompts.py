"""Prompt templates for custom pipeline LLM stages.

Format: detailed Bangla documentary prompts (role → inputs → strict rules → JSON),
matching the product owner's original style, plus production learnings from live tests:
  - hook / salam / CTA / quiz / human tone
  - visual_subject (no gratuitous faces on product/UI demos)
  - voice-only localization (shared visuals)
  - silent AI video + STOCK_VIDEO for real UI
  - trusted Ken Burns motion labels (no shaky d=17 zoompan)
"""

from __future__ import annotations

# Short: 40–120s | Long: 240–300s
DURATION_LABEL = {
    "short": "Short (40-120 Seconds)",
    "long": "Long (240-300 Seconds)",
}


NICHE_STORYTELLING_DIRECTIVES = {
    "tech": (
        "💡 টেকনোলজি ও রোবোটিক্স নিস নির্দেশনা: "
        "প্রযুক্তির শুষ্ক স্পেসিফিকেশন মুখস্থ না বলে বাস্তব মানুষের জীবনে এর প্রভাব ও কাজের রোমাঞ্চ দেখাও। "
        "যেমন: মানুষের হাতের স্পর্শের সাথে রোবোটিক সেন্সরের তুলনা, জটিল মেকানিজমকে সাধারণ কাজের সাথে মিলিয়ে সহজ করা।"
    ),
    "science": (
        "🔬 বিজ্ঞান ও আবিষ্কার নিস নির্দেশনা: "
        "বিজ্ঞানের জটিল সূত্র বা ল্যাব টেস্টকে সাধারণ মানুষের চাক্ষুষ উপমায় রূপান্তর করো। "
        "যেমন: অণুর গঠন, তাপমাত্রা বা চাপকে পরিচিত বস্তুর (বেলুন, কফির কাপ, বরফের টুকরো) সাথে তুলনা করে সহজ ভাষায় ব্যাখ্যা করো।"
    ),
    "space": (
        "🌌 মহাকাশ ও জ্যোতির্বিজ্ঞান নিস নির্দেশনা: "
        "মহাবিশ্বের অপার রহস্য, অকল্পনীয় বিশালতা ও সময়ের খেলাকে জীবন্ত করে তোলো। "
        "যেমন: কোটি কোটি কিলোমিটার দূরত্ব বা কৃষ্ণগহ্বরের টানকে পৃথিবীর পরিচিত জিনিসের ওজনের সাথে উপমা দিয়ে তুলে ধরো।"
    ),
    "history": (
        "📜 ইতিহাস ও প্রাচীন রহস্য নিস নির্দেশনা: "
        "শুকনো তারিখ বা সাল মুখস্থ না বলে একটি থ্রিলার বা গোয়েন্দা কাহিনীর মতো রহস্য উন্মোচন করো। "
        "কোনো প্রাচীন সিদ্ধান্ত বা ধ্বংসাবশেষের পেছনের অবিশ্বাস্য আসল সত্যি ও মানবিক নাটকীয়তা ফুটিয়ে তোলো।"
    ),
    "finance": (
        "💰 অর্থনীতি, ব্যবসা ও অর্থ নিস নির্দেশনা: "
        "বড় বড় কর্পোরেশনের গোপন কৌশল, কোটি টাকার ভুল বা সাধারণ মানুষের পকেটের উপর প্রভাব নিয়ে নাটকীয় গল্প বোলো। "
        "জটিল ফিন্যান্সিয়াল টার্ম সহজ কথ্য বাংলায় পানির মতো বুঝিয়ে দাও।"
    ),
    "crime": (
        "🔍 অপরাধ, রহস্য ও তদন্ত নিস নির্দেশনা: "
        "ঘটনার পেছনের রহস্য, অমীমাংসিত সূত্র ও মনস্তাত্ত্বিক কৌতূহল দিয়ে সাসপেন্স ধরে রাখো। প্রতিটি তথ্যে থাকবে রোমাঞ্চকর মোড়।"
    ),
    "health": (
        "🧬 স্বাস্থ্য, মানবদেহ ও জীববিজ্ঞান নিস নির্দেশনা: "
        "আমাদের নিজের শরীরের ভেতরে প্রতি মুহূর্তে কী অবিশ্বাস্য লড়াই চলছে তা সরাসরি দর্শকের সাথে কানেক্ট করে বলো। "
        "যেমন: রোগ প্রতিরোধ কোষকে প্রশিক্ষিত কমান্ডো বাহিনীর সাথে তুলনা।"
    ),
    "wildlife": (
        "🐾 বন্যপ্রাণী ও প্রকৃতি নিস নির্দেশনা: "
        "প্রাণীদের বেঁচে থাকার চরম লড়াই, অদ্ভুত সুপারপাওয়ার ও প্রকৃতির বিস্ময়কর নিয়মকে টানটান রোমাঞ্চ দিয়ে উপস্থাপন করো।"
    ),
    "psychology": (
        "🧠 মানব মনস্তত্ত্ব ও আচরণ নিস নির্দেশনা: "
        "মানুষ কেন এমন আচরণ করে, অবচেতন মনের গোপন চাল এবং প্রতিদিনের জীবনের লুকানো মনস্তাত্ত্বিক সত্য উন্মোচন করো।"
    ),
}


def get_niche_storytelling_directive(niche: str) -> str:
    n = (niche or "").lower()
    if any(k in n for k in ("tech", "robot", "ai", "software", "gadget", "কম্পিউটার", "রোবট", "প্রযুক্তি")):
        return NICHE_STORYTELLING_DIRECTIVES["tech"]
    if any(k in n for k in ("space", "astronomy", "cosmos", "মহাকাশ", "গ্রহ", "নক্ষত্র")):
        return NICHE_STORYTELLING_DIRECTIVES["space"]
    if any(k in n for k in ("history", "ancient", "war", "ইতিহাস", "প্রাচীন", "যুদ্ধ")):
        return NICHE_STORYTELLING_DIRECTIVES["history"]
    if any(k in n for k in ("money", "finance", "business", "economy", "টাকা", "ব্যবসা", "অর্থনীতি")):
        return NICHE_STORYTELLING_DIRECTIVES["finance"]
    if any(k in n for k in ("crime", "mystery", "investigation", "অপরাধ", "রহস্য", "গোয়েন্দা")):
        return NICHE_STORYTELLING_DIRECTIVES["crime"]
    if any(k in n for k in ("health", "medical", "body", "bio", "স্বাস্থ্য", "শরীর", "চিকিৎসা")):
        return NICHE_STORYTELLING_DIRECTIVES["health"]
    if any(k in n for k in ("animal", "wildlife", "nature", "প্রাণী", "বন্য", "প্রকৃতি")):
        return NICHE_STORYTELLING_DIRECTIVES["wildlife"]
    if any(k in n for k in ("psychology", "mind", "behavior", "মনস্তত্ত্ব", "মন", "আচরণ")):
        return NICHE_STORYTELLING_DIRECTIVES["psychology"]
    if any(k in n for k in ("science", "physics", "chemistry", "বিজ্ঞান", "পদার্থ", "রসায়ন")):
        return NICHE_STORYTELLING_DIRECTIVES["science"]
    return (
        "✨ সার্বজনীন স্টোরিটেলিং নির্দেশনা: "
        "যেকোনো বিষয়বস্তুকে শুকনো তথ্যের বদলে একটি কৌতূহলোদ্দীপক গল্প হিসেবে উপস্থাপন করো। "
        "প্রতিটি জটিল পয়েন্টকে সাধারণ মানুষের বোঝার মতো সহজ চাক্ষুষ উপমায় তুলে ধরো।"
    )


def build_topic_research_prompt(
    *,
    niche: str,
    video_type: str,
    audience: str,
    blocked_topics: list[str] | None = None,
    dedupe_note: str = "",
    quality_feedback: str = "",
) -> str:
    """Fill the Main Script & SEO prompt with niche / duration / audience."""
    kind = "short" if str(video_type).strip().lower() in ("short", "shorts", "reel") else "long"
    duration_line = DURATION_LABEL[kind]
    niche_s = (niche or "").strip() or "General"
    audience_s = (audience or "").strip() or "সাধারণ দর্শক"
    niche_directive = get_niche_storytelling_directive(niche_s)
    video_type_json = "Shorts" if kind == "short" else "Long"
    duration_json = "60" if kind == "short" else "270"
    blocked = [str(t).strip() for t in (blocked_topics or []) if str(t).strip()]
    blocked_block = ""
    if blocked or dedupe_note:
        blocked_block = "\n\n" + (dedupe_note or "")
        if blocked and "আগে থেকে থাকা টপিক" not in (dedupe_note or ""):
            blocked_block += "\n🚨 আগে থেকে থাকা টপিক ও নিষিদ্ধ বিষয়সমূহ (STRICT ZERO-DUPLICATE):\n"
            blocked_block += "\n".join(f"{i}. {t}" for i, t in enumerate(blocked[:30], 1))
            blocked_block += (
                "\n\n⛔ কঠোর সতর্কতা: উপরের কোনো টপিক, প্রতিষ্ঠান, প্রডাক্ট বা মডেল নিয়ে পুনরায় ভিডিও বা স্ক্রিপ্ট তৈরি করা সম্পূর্ণ নিষিদ্ধ। "
                "এমনকি ভাষা বা বাক্য পরিবর্তন করেও একই বিষয়ের পুনরাবৃত্তি করা যাবে না। "
                "এই নিসের সম্পূর্ণ নতুন, অপ্রচলিত, ভিন্ন ও চমকপ্রদ অন্য কোনো সাবজেক্ট বা প্রযুক্তি বেছে নাও।\n"
            )
    if quality_feedback:
        blocked_block += (
            f"\n\n[কোয়ালিটি রিট্রাই নির্দেশনা - পূর্বের স্ক্রিপ্ট বাতিল করা হয়েছে]:\n"
            f"{quality_feedback.strip()}\n"
            "এই ত্রুটিগুলো সম্পূর্ণ দূর করে একটি আকর্ষণীয়, সহজবোধ্য, হাই-রিটেনশন স্ক্রিপ্ট দাও।\n"
        )

    return f"""════════════════════════════════════════════════════════════
১. মূল ভিডিও স্ট্র্যাটেজি ও স্ক্রিপ্টিং প্রমপ্ট (Main Script & SEO Prompt)
════════════════════════════════════════════════════════════
কাজ: চ্যানেলের নিস ও নির্দিষ্ট সময়সীমার (Shorts: ৪০-১২০ সেকেন্ড বা Long: ২৪০-৩০০ সেকেন্ড) ওপর ভিত্তি করে SEO-ফ্রেন্ডলি টপিক, ৫টি টাইটেল, হাই-র‍্যাঙ্কিং ট্যাগ/কিওয়ার্ড এবং শট-বাই-শট সম্পূর্ণ প্রফেশনাল ভিডিও স্ক্রিপ্ট (ভয়েস + ভিজুয়াল + সাউন্ড) তৈরি করা।

ভূমিকা ও মেকার রোল:
তুমি একজন অভিজ্ঞ ইউটিউব কন্টেন্ট স্ট্র্যাটেজিস্ট, ইউজার গ্রোথ এক্সপার্ট এবং একজন মাস্টার ভিডিও স্ক্রিপ্টরাইটার। আমার বিভিন্ন নিসের ইউটিউব চ্যানেল রয়েছে। তোমার কাজ হলো নির্দিষ্ট নিসের ওপর ভিত্তি করে ভাইরাল হওয়ার মতো SEO-ফ্রেন্ডলি টপিক নির্বাচন করা এবং সেটির জন্য নির্দিষ্ট টাইমিং মেনে একটি সম্পূর্ণ প্রফেশনাল, মানবিক, অত্যন্ত আকর্ষণীয় ও সহজবোধ্য ভিডিও স্ক্রিপ্ট তৈরি করা।

আজকের ভিডিওর জন্য আমার ইনপুট (User Inputs):

চ্যানেলের নিস (Niche): {niche_s}
ভিডিওর টাইপ ও দৈর্ঘ্য (Target Duration): {duration_line}
টার্গেট অডিয়েন্স: {audience_s}
ভিডিওর মূল ভাষা (Source Language): বাংলা
(অন্য ভাষা পরে আলাদা লোকালাইজেশন স্টেজে হবে — এখানে শুধু বাংলা স্ক্রিপ্ট লিখবে।)
{blocked_block}
[এই নিসের বিশেষ স্টোরিটেলিং নির্দেশনা]:
{niche_directive}

তোমার কাজের ধাপসমূহ:
১. টপিক ও টাইটেল: ওপরের নিসের ওপর ভিত্তি করে বর্তমানে সবচেয়ে ট্রেন্ডিং এবং হাই-সার্চ ভলিউম বিশিষ্ট একটি SEO-ফ্রেন্ডলি ভিডিও টপিক সিলেক্ট করো। এরপর আকর্ষণীয় ৫টি টাইটেল এবং কিছু হাই-র‍্যাঙ্কিং ট্যাগ/কিওয়ার্ড সাজেস্ট করো।
২. JSON আউটপুট জেনারেট করা: আমার অটোমেশন সফটওয়্যারের সুবিধার জন্য সম্পূর্ণ স্ক্রিপ্টটি একটি ভ্যালিড JSON স্ট্রাকচারে রিটার্ন করবে।

স্ক্রিপ্ট তৈরির কঠোর নিয়মাবলী (Strict Rules — প্রতিটি খুঁটিনাটি মানতে হবে):

A) ভিডিও দৈর্ঘ্য, শট অ্যাডজাস্টমেন্ট ও শব্দের ঘনত্ব (Information Density):
* ইনপুটে দেওয়া Target Duration অনুযায়ী মোট ভিডিওর স্ক্রিপ্ট সাজাবে (Short মোট ~৪০-১২০ সে.; Long মোট ~২৪০-৩০০ সে.)।
* প্রতিটি ইন্ডিভিজুয়াল শটের ডিউরেশন হবে নির্দিষ্টভাবে ৫ থেকে ৯ সেকেন্ডের মধ্যে — এর বাইরে নয়।
* প্রতিটি শটে পর্যাপ্ত তথ্যের ঘনত্ব (Word Density) থাকতে হবে — প্রতি ৫-৯ সেকেন্ডের শটে অন্তত ১৫ থেকে ২৫টি অর্থপূর্ণ শব্দ থাকবে। ৫-৮ সেকেন্ডের শটে মাত্র ৭-১০ শব্দের ফাঁকা বাক্য লিখলে ভিডিও খালি ও রোবোটিক শোনায়, যা সম্পূর্ণ নিষিদ্ধ।
* একটি ৬০-৮০ সেকেন্ডের Shorts স্ক্রিপ্টে মোট অন্তত ১৫০ থেকে ২০০টি সমৃদ্ধ তথ্যবহুল শব্দ থাকতে হবে।
* শট সংখ্যা এমন হবে যে সব শটের shot_duration_seconds যোগফল Target Duration রেঞ্জের ভিতরে থাকে।

B) ভাইরাল মেগা-হুক, সহজবোধ্য উপমা, স্টোরিটেলিং ও দর্শক এনগেজমেন্ট (সবচেয়ে গুরুত্বপূর্ণ):

১. তীব্র আকর্ষণীয় মেগা-হুক (First 3 Seconds — Zero Boredom):
   - প্রথম ৩ সেকেন্ডেই দর্শকের মস্তিষ্কে বিদ্যুৎ চমকানোর মতো তীব্র কৌতূহল বা অবিশ্বাস্য বৈপরীত্য সৃষ্টি করতে হবে। 
   - গতানুগতিক, শান্ত বা বইয়ের মতো বাক্য সম্পূর্ণ নিষিদ্ধ (যেমন: "আজকে আমরা জানব...", "আসসালামু আলাইকুম, লিথিয়াম ব্যাটারি ছাড়া বাতাস দিয়ে বিদ্যুৎ তৈরি হচ্ছে..." - এই টাইপের নীরস শুরু ১০০% নিষিদ্ধ!)।
   - ভাইরাল হুকের জন্য নিচের যেকোনো একটি মনস্তাত্ত্বিক প্যাটার্ন ব্যবহার করো:
     * অবিশ্বাস্য বৈপরীত্য বা প্যারাডক্স: "বাতাসকে কি কখনো বরফের মতো জমিয়ে বোতলে ভরে পুরো শহর আলোকিত করা সম্ভব? শুনতে অসম্ভব লাগলেও..."
     * চোখ কপালে তোলার মতো 'কী হতো যদি': "এক মুহূর্তের জন্য কল্পনা করুন, যদি কোনো জ্বালানি ছাড়াই শুধু ঘরের বাতাস আপনার গাড়িকে হাজার মাইল ছুটিয়ে নেয়?"
     * লুকানো সত্যের রোমাঞ্চকর পর্দাফাঁস: "আমরা যে প্রযুক্তিকে এত দিন অসম্ভব বৈজ্ঞানিক গল্প ভাবতাম, বিজ্ঞানীরা সম্পূর্ণ নিঃশব্দে তা বাস্তবে নামিয়ে এনেছেন!"
     * টানটান মানবিক বা বৈজ্ঞানিক ড্রামা: "ইতিহাসে প্রথমবার এমন এক পরীক্ষা চালানো হয়েছে, যা মানুষের চেনা বিজ্ঞানকেই সম্পূর্ণ উল্টে দিল!"
   - সালামের স্মার্ট প্লেসমেন্ট: হুকের আকর্ষণ ধরে রাখতে সালাম বা শুভেচ্ছা হুক বাক্যের ঠিক পরপরই স্বাভাবিকভাবে জুড়ে দেবে (যেমন: "বাতাস জমিয়ে বিদ্যুৎ ব্যাংক? শুনতে অবিশ্বাস্য হলেও, আসসালামু আলাইকুম! বিজ্ঞানীরা সত্যি সত্যিই এমন এক অদ্ভুত প্রযুক্তি..."), যাতে প্রথম ৩ সেকেন্ডের উত্তেজনা একটুও নষ্ট না হয়।

২. রোবটের মতো লাইন-বাই-লাইন তথ্য বলা সম্পূর্ণ নিষিদ্ধ — "বাস্তব চাক্ষুষ উপমা"র নিয়ম:
   - কোনো অবস্থাতেই রোবটের মতো একের পর এক কঠিন নম্বর, মেগাওয়াট বা টেকনিক্যাল স্পেসিফিকেশন মুখস্থ পড়ার মতো বলা যাবে না।
   - প্রতিটি জটিল তথ্যকে সাধারণ দর্শকের পরিচিত বাস্তব জীবনের চাক্ষুষ উপমা দিয়ে পানির মতো সহজ ও চমৎকার করে বোঝাবে:
     * উদাহরণ (বাতাসের আয়তন ৭০০ গুণ কমা): "বাতাস তরল হলে এর আয়তন ৭০০ গুণ সংকুচিত হয় — সহজ কথায়, একটি সুবিশাল ফুটবল মাঠের পুরো বাতাসকে যেন চাপ দিয়ে ছোট একটি কফির কাপে ভরে ফেলা হলো!"
     * উদাহরণ (অগাধ চাপ বা শক্তি): "যেন আপনার হাতের তালুর ওপর একসাথে দশটি বিশালাকার হাতির ওজন চেপে বসেছে!"
     * উদাহরণ (সুপারকম্পিউটারের গতি): "যে বিশাল হিসাব কষতে মানুষের হাজার বছর লেগে যেত, এআই তা চোখের এক নিমেষেই শেষ করে দিচ্ছে!"
   - দর্শক যেন প্রতিটি তথ্যে চমকে ওঠে এবং নিজের চোখে দৃশ্যটি দেখতে পায় এমন জীবন্ত শব্দ ব্যবহার করবে।

৩. গল্প বলার ধারাবাহিকতা ও কানেক্টিং ব্রিজ (Storytelling Flow):
   - কোনো শটের ডায়ালগ যেন বিচ্ছিন্ন বা খাপছাড়া না শোনায়। প্রতিটি বাক্য যেন আগের বাক্যের সাথে একটি রোমাঞ্চকর গল্পের মতো যুক্ত থাকে।
   - স্মার্ট কথ্য কানেক্টিং ব্রিজ ব্যবহার করবে: "কিন্তু আসল টুইস্টটা ঘটে ঠিক এখানেই...", "শুনতে সহজ মনে হলেও বিজ্ঞানীদের সামনে ছিল এক বিশাল বাধা...", "আর সবচেয়ে অদ্ভুত বিষয় কী জানেন?", "একটু ভেবে দেখুন...", "সোজা কথায় বলতে গেলে..."।

৪. মাঝপথে অডিয়েন্স রিটেনশন ধরে রাখার হুক (Mid-Roll Curiosity Hook — শট ৪ থেকে ৭):
   - ভিডিওর মাঝখানে যেন দর্শকের আগ্রহ ঝিমিয়ে না পড়ে, সেজন্য ৪ থেকে ৭ নম্বর শটের মধ্যে একটি অপ্রত্যাশিত চ্যালেঞ্জ, গোপন রহস্য, রোমাঞ্চকর পরীক্ষা বা চমকপ্রদ মোড় উন্মোচন করবে।

৫. বুদ্ধিদীপ্ত অডিয়েন্স কুইজ ও আন্তরিক সমাপ্তি:
   - শেষ শটের ঠিক আগে (শট ৯) একটি চিন্তাশীল ও কৌতূহলোদ্দীপক প্রশ্ন রাখবে এবং দর্শকদের তাদের মতামত কমেন্টে যুক্তি দিয়ে লিখতে বলবে।
   - শেষ শটে আন্তরিকভাবে লাইক, শেয়ার ও চ্যানেল সাবস্ক্রাইব করতে বলবে এবং উষ্ণ বিদায়ী সালাম ("আল্লাহ হাফেজ") জানাবে।

C) ভিজুয়াল ডিটেইলস ও সাবজেক্ট পলিসি (ফেস ওভারইউজ ও বিকৃত/আবোল-তাবোল ইমেজ সম্পূর্ণ নিষিদ্ধ):
প্রতিটি শটে অবশ্যই `visual_subject` সেট করবে — এই চারটি মানের একটি:
* `broll` — মূল বিষয়বস্তুর সরাসরি সিনেম্যাটিক দৃশ্য (যেমন: মেকানিক্যাল হাত, ফ্যাক্টরি ফ্লোর, ল্যাব, গভীর সমুদ্র, মহাকাশ/গ্যালাক্সি, বৈজ্ঞানিক প্রযুক্তি)। ডকুমেন্টারি, সায়েন্স, টেকনোলজি, অটোমেশন ও সাধারণ ইনফরমেশন ভিডিওর ৮০-১০০% শট অবশ্যই `broll` হবে। ভিডিওর হুক, সালাম, CTA এবং কুইজ শটেও মানুষের মুখের বদলে মূল বিষয়ের আকর্ষণীয় সিনেম্যাটিক ভিজ্যুয়াল রাখবে।
* `product_ui` — নির্দিষ্ট সফটওয়্যার / অ্যাপ / ওয়েবসাইট স্ক্রিন ডেমো (মানুষের মুখ সম্পূর্ণ নিষিদ্ধ)।
* `hands_ui` — কোনো যন্ত্র বা ডিভাইসে শুধু হাত দিয়ে কাজ করা (মুখ ফ্রেমের বাইরে)।
* `presenter` — শুধু তখনই ব্যবহার করবে যদি ইউজার স্পষ্টভাবে কোনো পার্সোনাল ভ্লগ বা অন-ক্যামেরা উপস্থাপক ভিডিও চায়। রোবট, বিজ্ঞান, প্রযুক্তি বা তথ্যভিত্তিক ভিডিওতে অহেতুক মানুষের চেহারার ছবি দেওয়া সম্পূর্ণ নিষিদ্ধ।

কঠোর প্রম্পট ইঞ্জিনিয়ারিং ও ভিজ্যুয়াল নিয়মাবলী (আবোল-তাবোল ও অমিল প্রতিরোধ):
* প্রতিটি শটের `visual_prompt` ইংরেজিতে অত্যন্ত সূক্ষ্ম, জীবন্ত ও বিস্তারিতভাবে (৭০-১০০ শব্দে) লিখতে হবে। এতে জেনেরিক কোনো শব্দ ('topic subject', 'action matching dialogue', 'intricate parts') লেখা সম্পূর্ণ নিষিদ্ধ।
* প্রতিটি `visual_prompt`-এ স্পষ্ট ৫টি মূল উপাদান থাকা বাধ্যতামূলক:
  ১. Primary Subject & Material Details: সুনির্দিষ্ট অবজেক্ট বা চরিত্রের বাস্তব গঠন, মেটেরিয়াল, টেক্সচার ও রঙ (যেমন: 'Sleek matte-silver and carbon-black bipedal mechanics with exposed articulated joint mechanics and five-finger dexterous hands')।
  ২. Exact Physical Action Tied to Spoken Dialogue: ডায়ালগের কথার সাথে হুবহু মিল রেখে সে মুহূর্তে কী শারীরিক কাজ ঘটছে (যেমন: ডায়ালগে সুনির্দিষ্ট যে পরীক্ষার কথা বলা হচ্ছে, প্রম্পটে হুবহু সেই নির্দিষ্ট যন্ত্রাংশ বা ল্যাব অ্যাকশন বিস্তারিত থাকবে)।
  ৩. Photorealistic Environment & Depth: ব্যাকগ্রাউন্ডে কী আছে (যেমন: 'inside an ultra-modern automated laboratory with laser alignment benches in far background, clean polished gray concrete floor, safety fencing')।
  ৪. Cinematic Lens, Camera Angle & Lighting: ক্যামেরা অ্যাঙ্গেল ও লেন্সের ফোকাস (যেমন: 'Low-angle cinematic tracking shot, 35mm lens, f/2.0, bright commercial studio high-bay lighting, clean 5600K daylight balanced fill, crystal-clear optics, sharp highlights, zero dark underexposed shadows')।
  ৫. Style & Strict Negatives: '8k photorealistic, Octane Render style, award-winning cinematography, hyper-detailed micro textures, vibrant true-to-life colors, NO human face, NO female face, NO female robot face, NO gynoid, NO mannequin face, NO doll face, NO robot face close-up, NO talking head, no presenter portrait, no cartoon, no text, no watermark --ar {video_type_json}'।
* ইমেজ প্রম্পটে কখনোই অবাস্তব জিনিস চাইবে না — যেমন ল্যাপটপের পর্দায় লেখা নিউজ আর্টিকেল, তুলনামূলক চার্ট/গ্রাফ, অবাস্তব ফ্লোটিং টেক্সট। টেক্সটের বদলে সরাসরি আসল বিষয়বস্তু ও অ্যাকশন দেখাও।
* `character_details`: শুধু যদি ভিডিওটি স্পেসিফিকভাবে presenter-ভিত্তিক হয় তবেই লিখবে, অন্যথায় অবশ্যই `"none"` লিখবে।

D) কন্টিনিউটি ও কনসিসটেন্সি (Consistency):
* পরিবেশ, লাইটিং এবং মূল অবজেক্টের ডিজাইন শট-টু-শট ধারাবাহিক রাখবে।
* অপ্রয়োজনীয় মানুষের মুখের ছবি ঢুকাবে না।
* ভয়েসওভারে যা বলা হচ্ছে (পরীক্ষাগারের টেস্ট, রোবটের সুনির্দিষ্ট কাজ, সফটওয়্যার ডেমো) স্ক্রিনের দৃশ্যে হুবহু সেটাই ঘটতে দেখা যাবে — ডায়লগের সাথে দৃশ্যের ১০০% মিল থাকতে হবে।

E) ভয়েসওভার ও ইমোশন:
* প্রতিটা শটের সাথে সঠিক বাংলা `voiceover_script` লিখবে — স্পষ্ট, কথ্য, TTS-ফ্রেন্ডলি।
* ভয়েসের সঠিক টোন ও এক্সপ্রেশনের জন্য নির্দিষ্ট Emotion Tag যুক্ত করবে (যেমন: Excited, Mysterious, Serious, Whispering, Energetic, Clear & Instructive) — ট্যাগগুলো হিউম্যান কণ্ঠের মতো ন্যাচারাল রাখবে; অতিরিক্ত নাটকীয়/শকড ট্যাগ দিয়ে TTS ভয়েস পারসোনা বদলাবে না।

F) সাউন্ড ডিজাইন:
* প্রতিটি শটের জন্য মানানসই SFX (Sound Effects) এবং BGM (Background Music Direction) উল্লেখ করবে।

প্রত্যাশিত JSON স্ট্রাকচার (এই ফরম্যাটেই আউটপুট দেবে — অন্য কোনো কী যোগ/বাদ করবে না):

{{
  "seo_metadata": {{
    "selected_topic": "বিষয়বস্তুর নাম",
    "suggested_titles": ["টাইটেল ১", "টাইটেল ২", "টাইটেল ৩", "টাইটেল ৪", "টাইটেল ৫"],
    "seo_keywords": ["keyword1", "keyword2", "keyword3"],
    "video_type": "{video_type_json}",
    "target_duration_seconds": {duration_json}
  }},
  "script_scenes": [
    {{
      "shot_number": 1,
      "shot_duration_seconds": 6,
      "visual_subject": "broll",
      "camera_angle": "Cinematic Dynamic Low-Angle Tracking Shot",
      "lighting": "Bright commercial high-bay illumination with clean 5600K daylight balanced fill and sharp highlights",
      "character_details": "none",
      "visual_prompt": "Ultra-detailed cinematic low-angle tracking shot of a sleek matte-silver and carbon-black bipedal humanoid robot walking purposefully between car-body fixtures in a clean brightly-lit high-tech manufacturing plant, subtle motion blur on polished concrete floor, sharp focus on articulated knee and hip actuators, bright clean factory atmosphere, 8k, photoreal, NO human face, NO female face, NO female robot face, NO gynoid, NO doll face, NO portrait, no text --ar 9:16",
      "voiceover_script": "এখানে বাংলা ভয়েসওভারের কথাগুলো থাকবে...",
      "emotion_tag": "Mysterious & Engaging",
      "sfx": "Subtle mechanical servo hum and low cinematic sub whoosh",
      "bgm_style": "Slow ambient synth tension"
    }},
    {{
      "shot_number": 2,
      "shot_duration_seconds": 7,
      "visual_subject": "broll",
      "camera_angle": "Macro Extreme Close-up",
      "lighting": "Clean directional work-light with metallic specular highlights and high contrast",
      "character_details": "none",
      "visual_prompt": "Photoreal macro extreme close-up of two multi-jointed metallic robotic hands with black silicone fingertips carefully gripping and placing a laser-cut automotive sheet metal panel into a chassis jig, shallow depth of field, razor-sharp metallic surface textures, fine industrial dust motes in volumetric light beam, 8k, NO human face, no text --ar 9:16",
      "voiceover_script": "এখানে পরবর্তী ডায়লগ থাকবে...",
      "emotion_tag": "Clear & Instructive",
      "sfx": "Precision mechanical click and pneumatic hiss",
      "bgm_style": "Minimal rhythmic electronic pulse"
    }}
  ]
}}

ওপরের স্ট্রাকচার ও নিয়ম বজায় রেখে আমার ইনপুট অনুযায়ী সম্পূর্ণ আউটপুট প্রদান করো।
শুধু ভ্যালিড JSON রিটার্ন করো — কোনো মার্কডাউন কোড ফেন্স বা অতিরিক্ত ব্যাখ্যা নয়।"""


SYSTEM_JSON_ONLY = (
    "You are a YouTube content strategist and master scriptwriter. "
    "Follow every strict rule in the user prompt (timing, hook/salam/CTA/quiz, "
    "visual_subject / no gratuitous faces, continuity, human tone). "
    "Crucially, inject deep emotion, life, and engaging storytelling into the script. "
    "Avoid robotic info-dumps at all costs. "
    "Respond with a single valid JSON object only — no markdown fences, no commentary."
)

SYSTEM_LOCALIZE_JSON = (
    "You are an expert cultural localizer, international dubbing director, "
    "and voice-over translator. Localize voice + emotion + subtitles + SEO only; "
    "never invent or rewrite visuals. "
    "Respond with a single valid JSON object only — no markdown fences, no commentary."
)

DEFAULT_AUDIENCE_CULTURE = {
    "English": "Global English Reader",
    "Hindi": "North Indian",
    "Urdu": "Pakistani & Urdu Culture",
    "Tamil": "South Indian",
    "Malayalam": "South Indian",
}


def build_localization_prompt(
    *,
    target_language: str,
    audience_culture: str,
    source_json: str,
) -> str:
    """Cultural localization — voice/SEO only; visuals never regenerated."""
    lang = (target_language or "").strip() or "English"
    culture = (audience_culture or "").strip() or DEFAULT_AUDIENCE_CULTURE.get(
        lang, "General audience"
    )
    script_blob = (source_json or "").strip()

    return f"""════════════════════════════════════════════════════════════
২. সাংস্কৃতিক লোকালাইজেশন প্রমপ্ট (Cultural Localization Prompt)
════════════════════════════════════════════════════════════
কাজ: মূল ভিজ্যুয়াল ও টাইমিং ঠিক রেখে অন্য ভাষায় (English, Hindi, Urdu, Tamil, Malayalam) রূপান্তরের সময় কেবল আক্ষরিক অনুবাদ না করে স্থানীয় কালচার, ইমোশন, ধর্মীয়/সামাজিক টিউন ও স্থানীয় বোলচাল অনুযায়ী অডিও স্ক্রিপ্ট + সাবটাইটেল + SEO বদলে দেওয়া।

ভূমিকা ও মেকার রোল:
তুমি একজন এক্সপার্ট কালচারাল লোকালাইজার, আন্তর্জাতিক ডাবিং ডিরেক্টর এবং ভয়েস-ওভার ট্রান্সলেটর। তোমার কাজ হলো মূল ফর্মেটের (বাংলা) ভিডিও ভয়েস স্ক্রিপ্টটিকে সাধারণ অনুবাদ না করে, টার্গেট ভাষার সংস্কৃতি, আবেগ-অনুভূতি, আঞ্চলিক টিউন, ধর্মীয় মূল্যবোধ এবং স্থানীয় বোলচাল (Nuances & Colloquialisms) অক্ষুণ্ণ রেখে একটি প্রাকৃতিক "লোকালাইজড ভয়েস স্ক্রিপ্ট" তৈরি করা।

গুরুত্বপূর্ণ (লাইভ টেস্ট থেকে বাধ্যতামূলক):
* ভিজুয়াল একবারই তৈরি হয় এবং সব ভাষায় একই থাকবে।
* তাই camera_angle, lighting, character_details, visual_prompt, visual_subject, sfx, bgm_style কখনোই আউটপুটে লিখবে না বা নতুন করে তৈরি করবে না।
* শুধু ভয়েস + ইমোশন + সাবটাইটেল + SEO লোকালাইজ করবে।

আজকের লোকালাইজেশন ইনপুট:

টার্গেট ভাষা (Target Language): {lang}
টার্গেট অডিয়েন্স কালচার: {culture}
ইনপুট ডেটা: নিচে দেওয়া বাংলা ভয়েস-ওনলি JSON (visual ফিল্ড ইচ্ছাকৃতভাবে কাটা)।

লোকালাইজেশন ও কনভার্সন নিয়মাবলী (Strict Rules — প্রতিটি খুঁটিনাটি):

১. লোকালাইজেশন বনাম সাধারণ অনুবাদ:
* আক্ষরিক অনুবাদ সম্পূর্ণ নিষিদ্ধ। মূল ভাব ও অর্থ ঠিক রেখে টার্গেট ভাষার মানুষের আবেগ ও কথা বলার ধরণ অনুযায়ী পুরো বাক্য পুনর্গঠন করবে।
* মূল স্ক্রিপ্টের কোনো উদাহরণ, বাগধারা বা শব্দ টার্গেট সংস্কৃতির সাথে অমিল হলে স্থানীয় সংস্কৃতির জনপ্রিয় বিকল্প শব্দ বা কালচারাল রেফারেন্স দিয়ে তা প্রতিস্থাপন করবে।
* হুক / সালাম / CTA / কুইজের অভিপ্রায় ধরে রাখবে — টার্গেট কালচারে প্রাকৃতিক শুভেচ্ছা/আহ্বান ব্যবহার করবে (জোর করে কৃত্রিম ইসলামিক/পশ্চিমা ফর্মুলা লাগাবে না)।

২. আঞ্চলিক টিউন ও ইমোশন ট্যাগ:
* টার্গেট ভাষার কালচারাল একসেন্ট ও আবেগের সাথে মিলিয়ে প্রতিটি শটের emotion_tag আপডেট করবে।
* emotion_tag হিউম্যান ও ন্যাচারাল রাখবে — অতিরিক্ত "shocked/amazed/urgent" দিয়ে TTS ভয়েস পারসোনা ভাঙবে না; delivery-ফ্রেন্ডলি ট্যাগ ব্যবহার করবে (যেমন: Warm & Conversational, Clear & Instructive, Calm Curiosity)।
* ভয়েসওভার স্ক্রিপ্টটি এমনভাবে লিখবে যেন অডিও AI (TTS) থেকে ভয়েস জেনারেট করলে তা স্থানীয় স্পিকারের মতো স্বাভাবিক শোনায় — রোবোটিক বা অতিরিক্ত লিটারারি নয়।

৩. সাবটাইটেল:
* প্রতি শটে `subtitle_text` লিখবে — ভয়েসের সাথে মিল রেখে; মোবাইল স্ক্রিনের জন্য প্রয়োজনে সামান্য সংক্ষিপ্ত; অর্থ হারাবে না।

৪. ভিজুয়াল ও টাইমিং অপরিবর্তিত:
* shot_number এবং shot_duration_seconds ইনপুট থেকে একদম অপরিবর্তিত রাখবে।
* কোনো visual ফিল্ড আউটপুটে আনবে না।

৫. SEO লোকালাইজেশন:
* selected_topic, suggested_titles (কমপক্ষে ৩টি), seo_keywords টার্গেট ভাষায় কালচারাল ও সার্চ-ফ্রেন্ডলিভাবে লোকালাইজ করবে।
* video_type ও target_duration_seconds ইনপুটের সাথে সামঞ্জস্য রেখে রাখবে।

প্রত্যাশিত JSON আউটপুট ফরম্যাট (Strict — শুধু voice + SEO; visuals নয়):

{{
  "target_language": "{lang}",
  "seo_metadata": {{
    "selected_topic": "টার্গেট ভাষায় অনুবাদিত/লোকালাইজড বিষয়বস্তু",
    "suggested_titles": ["লোকালাইজড টাইটেল ১", "লোকালাইজড টাইটেল ২", "লোকালাইজড টাইটেল ৩"],
    "seo_keywords": ["keyword1", "keyword2"],
    "video_type": "Shorts / Long",
    "target_duration_seconds": 60
  }},
  "voice_scenes": [
    {{
      "shot_number": 1,
      "shot_duration_seconds": 6,
      "voiceover_script": "এখানে টার্গেট ভাষার কালচারাল লোকালাইজড অডিও ডায়লগ থাকবে...",
      "emotion_tag": "টার্গেট ভাষার আবেগ অনুযায়ী ন্যাচারাল ইমোশন ট্যাগ",
      "subtitle_text": "টার্গেট ভাষার সাবটাইটেল"
    }}
  ]
}}

মূল ভয়েস ইনপুট JSON:
{script_blob}

শুধু ভ্যালিড JSON রিটার্ন করো — কোনো মার্কডাউন কোড ফেন্স বা অতিরিক্ত ব্যাখ্যা নয়।"""


SYSTEM_VISUAL_RENDER_JSON = (
    "You are a professional AI video production director, VFX animator, "
    "and prompt engineer. Honor visual_subject (no gratuitous faces on product UI). "
    "HARD RULE: product_ui / hands_ui / brand ChatGPT-settings shots MUST be IMAGE or VIDEO "
    "— never STOCK_VIDEO (stock libraries cannot show real product chrome). "
    "STOCK_VIDEO only for generic broll environments. Keep VIDEO silent. "
    "Use only trusted animation_type labels for IMAGE. "
    "Respond with a single valid JSON object only — no markdown fences, no commentary."
)


def build_visual_render_prompt(
    *,
    source_json: str,
    aspect_ratio: str = "16:9",
    art_style: str = "Cinematic Hyper-realistic",
) -> str:
    """IMAGE vs VIDEO vs STOCK_VIDEO production routing prompt."""
    import json
    script_blob = (source_json or "").strip()
    ar = (aspect_ratio or "16:9").strip()
    style = (art_style or "Cinematic Hyper-realistic").strip()

    macro_guide = ""
    try:
        from pipeline.custom_pipeline.visual_intelligence import analyze_macro_topic_and_script
        src_dict = json.loads(script_blob) if isinstance(script_blob, str) else script_blob
        if isinstance(src_dict, dict):
            ctx = analyze_macro_topic_and_script(src_dict)
            macro_guide = f"""
[সামগ্রিক গবেষণা ও মূল দৃশ্যপট নির্দেশিকা (Holistic Visual Reality)]:
* টপিক ডোমেইন: {ctx.visual_domain}
* মূল নির্ধারিত দৃশ্যপট (Locked Primary Setting): {ctx.primary_setting}
* পর্দায় আবশ্যিক বাস্তব উপাদান (Core Physical Entities): {', '.join(ctx.primary_entities[:5])}
* সম্পূর্ণ নিষিদ্ধ দৃশ্য ও বিভ্রান্তি (Strictly Forbidden Tangents): {', '.join(ctx.forbidden_tangents)}
* কঠোর প্রযোজনা নির্দেশ: পুরো ভিডিওটি একসাথে গবেষণা করে ভিজ্যুয়াল নির্ধারণ করবে। কোনো ডায়ালগের বিচ্ছিন্ন শব্দ দেখে ভুল দৃশ্য আনবে না (যেমন বিএমডব্লিউ ফ্যাক্টরি ট্রায়ালে ফ্যাক্টরির রোবটিক্স ও অ্যাসেম্বলি লাইন দেখাবে, রাস্তায় চলা গাড়ি বা বাইক নয়; ৪০০০ মিটার সমুদ্রের রহস্যে পানির নিচে নিমজ্জিত তলদেশ ও ডার্ক অক্সিজেনের পলিমেটালিক নোডিউল দেখাবে, শুকনো মাটির পাথর নয়!)।
"""
    except Exception:
        pass

    return f"""════════════════════════════════════════════════════════════
৩. ভিজ্যুয়াল ইঞ্জিনিয়ারিং ও প্রডাকশন রাউটিং প্রমপ্ট (Visual Production Prompt)
════════════════════════════════════════════════════════════
কাজ: ইনপুট JSON স্ক্রিপ্টের প্রতিটি শটের ডায়লগ ও visual_subject বিশ্লেষণ করে সিদ্ধান্ত নেওয়া IMAGE নাকি VIDEO নাকি STOCK_VIDEO তৈরি হবে; সে অনুযায়ী হাই-কোয়ালিটি visual_prompt এবং motion_directives (FFmpeg অ্যানিমেশন লেবেল অথবা ক্যামেরা/অ্যাকশন) জেনারেট করা।
{macro_guide}
ভূমিকা ও মেকার রোল:
তুমি একজন প্রফেশনাল AI ভিডিও প্রোডাকশন ডিরেক্টর, ভিজ্যুয়াল ইফেক্টস (VFX) অ্যানিমেটর এবং প্রম্পট ইঞ্জিনিয়ার। তোমার কাজ হলো ইনপুট হিসেবে পাওয়া JSON স্ক্রিপ্টের প্রতিটি শট বিশ্লেষণ করে ভিজ্যুয়াল রেন্ডারিং সংক্রান্ত প্রযুক্তিগত সিদ্ধান্ত নেওয়া এবং সে অনুযায়ী নির্দিষ্ট প্রমপ্ট ও FFmpeg/মোশন নির্দেশিকা জেনারেট করা।

প্রোডাকশন কনটেক্সট:
aspect_ratio: {ar}
art_style hint: {style}

তোমার কাজের মূল দায়িত্ব ও সিদ্ধান্ত গ্রহণের নিয়মাবলী (প্রতিটি খুঁটিনাটি):

০০) সামগ্রিক গবেষণা ও দৃশ্যপট একীকরণ (Holistic Script & Topic Coherence):
* পুরো ভিডিওটি একসাথে বিবেচনা করে প্রতিটি শটের ভিজ্যুয়াল নির্ধারণ করবে। কোনো বিচ্ছিন্ন শব্দ দেখে বিভ্রান্তিকর দৃশ্য আনবে না।
* ভিডিওর মূল ভাবগাম্ভীর্য এবং বাস্তব পরিবেশ (Setting) প্রতিটি শটে অক্ষুণ্ণ রাখবে।

০) ভিজুয়াল সাবজেক্ট পলিসি (ফেস ওভারইউজ ও অবাস্তব টেক্সট সম্পূর্ণ নিষিদ্ধ):
* প্রতিটি শটে `visual_subject` সম্মান করো: presenter | product_ui | hands_ui | broll।
* টপিক যদি টেকনোলজি, সায়েন্স, রোবোটিক্স, ডকুমেন্টারি, ফ্যাক্টস ইত্যাদি হয় তবে মানুষের মুখ সম্পূর্ণ অপ্রয়োজনীয় — সব শট `broll` অথবা `hands_ui` হবে।
* broll / product_ui: visual_prompt এ মানুষের মুখ / পোর্ট্রেট / selfie / young man hoodie looking at camera নিষিদ্ধ। সাবজেক্টের রিয়েলিস্টিক অবজেক্ট ও অ্যাকশন দেখাও।
* অবাস্তব টেক্সট/চার্ট নিষিদ্ধ: AI ইমেজ জেনারেটর স্ক্রিনে টেক্সট বা চার্ট রেন্ডার করতে পারে না (ছবি বিকৃত ও আবোল-তাবোল হয়ে যায়)। তাই সংবাদপত্রের হেডলাইন, আর্টিকেল টেক্সট, বা ইউটিউব প্লেয়ার স্ক্রিন চাইতে পারবে না — সরাসরি রিয়েল-ওয়ার্ল্ড সাবজেক্ট/প্রপস/অ্যাকশন দেখাও।
* presenter: শুধুমাত্র তখনই যখন পুরো ভিডিওটি একান্তই একজন মানব উপস্থাপকের পার্সোনাল ভ্লগ। অন্যথায় সায়েন্স/রোবোটিক্স/ডকুমেন্টারিতে প্রেজেন্টার মুখ সম্পূর্ণ নিষিদ্ধ।
* hands_ui: শুধু হাত + সাবজেক্ট অবজেক্ট/যন্ত্রপাতি/কীবোর্ড; মুখ ক্রপ আউট।
* Demo steps → prefer render_type IMAGE (AI still of real UI/subject) অথবা VIDEO (silent AI). STOCK_VIDEO শুধু তখনই যখন ব্র্যান্ড UI নয় এমন বাস্তব পরিবেশ।

১) রেন্ডারিং মোড সিদ্ধান্ত (Image vs Stock Video vs Video):

* IMAGE (Static Image + FFmpeg Animation): যেসব শটে দৃশ্য অপেক্ষাকৃত শান্ত, কেবল ভয়েসওভার বা ডায়লগ প্রাধান্য পায়, ক্যামেরা মুভমেন্ট সামান্য — render_type: "IMAGE"।
  - IMAGE শট ≥৫ সেকেন্ড হলে image_frame_count 2 বা 3 সেট করতে পারো (পাইপলাইন একই seed-এ ২–৩টি still বানিয়ে ডায়লগ বিট ম্যাচ করবে)।
  - Continuity: SAME environment/subject; SAME character শুধু visual_subject=presenter হলে। Spoken props ও অ্যাকশন সরাসরি ম্যাচ করবে।

* STOCK_VIDEO (generic real-world b-roll ONLY): শুধু visual_subject=broll এবং ব্র্যান্ড/প্রোডাক্ট UI নয় এমন বাস্তব পরিবেশ। র‍্যান্ডম মানুষের মুখ/স্টক পোর্ট্রেট সম্পূর্ণ নিষিদ্ধ।

* VIDEO (AI Video Generation): হাই-অ্যাকশন, সাবজেক্টের মোশন, মুভমেন্ট লাগলে render_type: "VIDEO"।
  - VIDEO সবসময় SILENT — কোনো স্পিচ/ডায়লগ/লিপ-সিঙ্ক নেই।
  - SEED/character face continuity শুধু presenter শটে; broll/product_ui তে দৃশ্য ও অবজেক্টের কনসিসটেন্সি।

২) ইমেজ অ্যানিমেশনের জন্য (যদি render_type = "IMAGE" হয়):
* Image Prompt: মিডজার্নি/স্টেবল ডিফিউশন/ফ্লাক্স উপযোগী অত্যন্ত সূক্ষ্ম, জীবন্ত ও প্রফেশনাল ৭০-১০০ শব্দের সিনেম্যাটিক ইংরেজি প্রমপ্ট। 
  - এতে ৫টি মূল উপাদান থাকা আবশ্যক: (১) Primary Subject & Material Details (সুনির্দিষ্ট অবজেক্ট বা চরিত্রের বাস্তব মেটেরিয়াল, টেক্সচার ও মেকানিক্স), (২) Exact Physical Action Tied to Spoken Dialogue (ভয়েসওভার ডায়লগের নির্দিষ্ট কথার সাথে মিলিয়ে সে মুহূর্তে কী শারীরিক কাজ ঘটছে), (৩) Photorealistic Environment & Depth (ব্যাকগ্রাউন্ডের বাস্তব পরিবেশ), (৪) Cinematic Lens, Camera Angle & Lighting (লেন্স, লাইটিং ও ফোকাস), (৫) Style & Strict Negatives (8k photoreal, NO human face, no text, no watermark --ar {ar})।
  - জেনেরিক বা সংক্ষিপ্ত কোনো স্টাব ("shot of topic subject in action", "intricate mechanical action") লেখা সম্পূর্ণ নিষিদ্ধ।
* FFmpeg: কাঁচা zoompan স্ট্রিং invent করবে না। শুধু animation_type সেট করবে — একদম এই লিস্ট থেকে একটি:
  "Slow Center Zoom In" | "Slow Center Zoom Out" | "Gentle Pan Left" | "Gentle Pan Right" | "Gentle Tilt Up" | "Gentle Tilt Down" | "Slow Zoom In + Pan Right" | "Slow Zoom In + Pan Left"
* প্রতিটি IMAGE শটে আলাদা animation_type ব্যবহার করবে। পাইপলাইন নিজে trusted ffmpeg_filter বানাবে।

৩) ভিডিও জেনারেটিং এর জন্য (যদি render_type = "VIDEO" বা "STOCK_VIDEO" হয়):
* VIDEO visual_prompt: Runway / Pika / Luma উপযোগী ডায়নামিক টেক্সট-টু-ভিডিও প্রমপ্ট (৭০-১০০ শব্দ)। MUST include: "SILENT VIDEO ONLY — no speech, no dialogue, no lip-sync"।
* ভয়েসওভার টেক্সট কোট করে বলাবে না — শুধু ভিজ্যুয়াল অ্যাকশন, মেটেরিয়ালস ও প্রপস বিশদভাবে বর্ণনা করবে।
* Visual must MATCH voiceover_script meaning (props/actions on screen) — জেনেরিক স্টুডিও পোজ বা র‍্যান্ডম ফেস নয়।
* STOCK_VIDEO তেও visual_prompt এ সাবজেক্ট কি দেখাবে তা স্পষ্ট লিখবে (সার্চ কোয়েরির জন্য)।

৪) কন্সিস্টেন্সি (Consistency) রক্ষা:
* পরিবেশ, লাইটিং, কালার প্যালেট ধারাবাহিক রাখো।
* মুখ/ওয়্যারড্রোব কনসিসটেন্সি শুধু presenter শটে।
* product_ui / hands_ui / broll শটে মুখ যোগ করো না।
* shot_number এবং shot_duration_seconds ইনপুট স্ক্রিপ্টের সাথে মিল রেখে রাখবে।
* প্রতিটি আউটপুট শটে visual_subject ফিল্ড রাখবে (ইনপুট থেকে কপি বা অনুমান)।

প্রত্যাশিত JSON আউটপুট ফরম্যাট (Strict JSON Only):

{{
  "production_metadata": {{
    "total_shots": 10,
    "aspect_ratio": "{ar}",
    "art_style": "Cinematic Hyper-realistic"
  }},
  "render_scenes": [
    {{
      "shot_number": 1,
      "shot_duration_seconds": 6,
      "render_type": "IMAGE",
      "visual_subject": "broll",
      "visual_prompt": "Ultra-detailed cinematic low-angle tracking shot of a sleek matte-silver and carbon-black bipedal humanoid robot walking purposefully between car-body fixtures in a clean high-tech manufacturing plant, subtle motion blur on polished concrete floor, sharp focus on articulated knee and hip actuators, dramatic atmospheric factory haze, volumetric cyan LED lamps, 8k photoreal, Octane Render style, NO human face, no text, no watermark --ar {ar}",
      "image_frame_count": 2,
      "motion_directives": {{
        "animation_type": "Slow Center Zoom In"
      }}
    }},
    {{
      "shot_number": 2,
      "shot_duration_seconds": 7,
      "render_type": "IMAGE",
      "visual_subject": "broll",
      "visual_prompt": "Photoreal macro extreme close-up of two multi-jointed metallic robotic hands with black silicone fingertips carefully gripping and placing a laser-cut automotive sheet metal panel into a chassis jig, shallow depth of field, razor-sharp metallic surface textures, fine industrial dust motes in volumetric light beam, 8k, Octane Render style, NO human face, no text, no watermark --ar {ar}",
      "image_frame_count": 2,
      "motion_directives": {{
        "animation_type": "Slow Zoom In + Pan Right"
      }}
    }},
    {{
      "shot_number": 3,
      "shot_duration_seconds": 5,
      "render_type": "VIDEO",
      "visual_subject": "hands_ui",
      "visual_prompt": "SILENT VIDEO ONLY — no speech, no dialogue, no lip-sync. Adult dexterous hands in anti-static gloves operating precision digital inspection sensors across an automotive battery housing, face cropped out completely, cinematic cool white overhead workstation lighting, smooth 24fps natural camera push-in, shallow depth of field, 8k photoreal --ar {ar}",
      "motion_directives": {{
        "camera_movement": "Subtle push-in on subject action",
        "character_action": "Hands performing precision task — no face in frame"
      }}
    }}
  ]
}}

ইনপুট JSON স্ক্রিপ্ট:
{script_blob}

ওপরের স্ট্রাকচার ও নিয়ম বজায় রেখে সম্পূর্ণ আউটপুট প্রদান করো।
শুধু ভ্যালিড JSON রিটার্ন করো — কোনো মার্কডাউন কোড ফেন্স বা অতিরিক্ত ব্যাখ্যা নয়।"""
