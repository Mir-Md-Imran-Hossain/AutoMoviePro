(function () {
  const LANGS = [
    { code: "bn", name: "বাংলা (BN)" },
    { code: "en", name: "English (EN)" },
    { code: "hi", name: "हिन्दी (HI)" },
    { code: "ur", name: "اردو (UR)" },
    { code: "ta", name: "தமிழ் (TA)" },
    { code: "ml", name: "മലയാളം (ML)" },
  ];

  const PACKS = {
    bn: {
      hero_badge: "🚀 নেক্সট-জেন এআই ভিডিও অটোমেশন v4.2",
      site_tagline: "AI-চালিত অটোমেটেড ভিডিও স্টুডিও — ১টি ক্লিপ থেকে ৬টি ভাষায় ১৮টি চ্যানেলে অটোমেশন",
      hero_desc: "ম্যানুয়াল এডিটিং চিরতরে বন্ধ করুন। নিশ সিলেক্ট করুন একবার — আমাদের প্রো অ্যালগরিদম স্বয়ংক্রিয়ভাবে ভাইরাল স্ক্রিপ্ট, সিনেমাটিক ভিজ্যুয়াল, প্রফেশনাল ভয়েসওভার ও হার্ফবাজ সাবটাইটেল তৈরি করে ইউটিউব, ফেসবুক ও টিকটকে শিডিউল করবে।",
      see_features: "সব ফিচার এক্সপ্লোর করুন",
      buy_now: "এখনই লাইসেন্স নিন",
      chat_whatsapp: "WhatsApp পরামর্শ",
      active_creators_badge: "১,২৫০+ অ্যাক্টিভ কনটেন্ট ক্রিয়েটর",
      studio_badge_live: "🔴 লাইভ স্টুডিও ইঞ্জিন সক্রিয়",
      studio_badge_channels: "⚡ ১৮টি মাল্টি-চ্যানেল অটো স্ট্রিম",
      studio_badge_langs: "🌍 ৬টি গ্লোবাল ভাষায় নিখুঁত সিঙ্ক",

      income_title: "৬×৬×৬ চ্যানেল নেটওয়ার্ক থেকে আলাদা প্যাসিভ ইনকাম",
      income_lead: "একটি মাত্র প্ল্যাটফর্ম থেকে ৬টি YouTube চ্যানেল, ৬টি Facebook পেজ এবং ৬টি TikTok প্রোফাইল একযোগে পরিচালনা করুন। কোনো এডিটর হায়ার করার প্রয়োজন নেই — এক ক্লিকেই গ্লোবাল স্কেলিং।",
      pitch_yt: "৬টি স্বতন্ত্র YouTube চ্যানেল (৬টি ভিন্ন ভাষায়)",
      pitch_fb: "৬টি হাই-গ্রোথ Facebook পেজ ও রিলস স্ট্রিম",
      pitch_tt: "৬টি ভাইরাল TikTok গন্তব্য",
      pitch_auto: "ক্লাউড শিডিউলিং — পিসি অন না রেখেও অটো-পাবলিশিং",

      how_it_works: "কীভাবে কাজ করে",
      how_lead: "অটোমেশনের ৪টি সহজ ধাপ — আইডিয়া থেকে আন্তর্জাতিক রেভিনিউ।",
      step1: "নিশ সিলেক্ট করুন ও আপনার চ্যানেলগুলো নিরাপদে যুক্ত করুন (একবার লগইন)",
      step2: "AI স্বয়ংক্রিয়ভাবে ভাইরাল শর্টস ও লং ভিডিও তৈরি করে (স্ক্রিপ্ট + সিনেমাটিক সিন)",
      step3: "ইংরেজি মাস্টার থেকে স্বয়ংক্রিয়ভাবে নিখুঁত সাবটাইটেল ও লোকাল ভয়েসওভারে রূপান্তর",
      step4: "নির্ধারিত শিডিউল অনুযায়ী YouTube, Facebook এবং TikTok-এ সরাসরি অটো-আপলোড",

      features: "পাওয়ারফুল ইন্ডাস্ট্রিয়াল ফিচারসমূহ",
      features_lead: "বিশ্বমানের কনটেন্ট ক্রিয়েটর ও মিডিয়া এজেন্সির জন্য প্রস্তুত প্রতিটি টুলস।",

      gpro_badge: "স্পেশাল ভিআইপি অফার",
      gpro_title: "কোন ঝামেলা ছাড়াই ভিডিও তৈরির জন্য স্পেশাল গুগল AI Pro প্যাকেজ",
      gpro_lead: "কোটা লিমিটেশন বা রোবোটিক সাউন্ডের কোনো ঝামেলা ছাড়া আনলিমিটেড ক্রিয়েশন! সরাসরি গুগল প্রো ক্লাউড, হাই-রেজুলেশন সিনেমাটিক মডেল ও নিরাপদ ১৫০ জিবি ক্লাউড ড্রাইভ ব্যাকআপ।",
      gpro_feat1_title: "গুগল Nano Banana ও VEO-3 সিনেমাটিক API",
      gpro_feat1_desc: "আল্ট্রা-এইচডি সিনেমাটিক ভিডিও সিন ও স্টুডিও কোয়ালিটি ইমেজ জেনারেশন ফুল এক্সেস।",
      gpro_feat2_title: "আল্ট্রা-ন্যাচারাল রোবোটিকলেস TTS",
      gpro_feat2_desc: "১০০% মানবিক অনুভূতির বাংলা ও বহুভাষিক ভয়েসওভার — রোবোটিক টোনমুক্ত।",
      gpro_feat3_title: "হাই CTR ভাইরাল টপিক ও স্ক্রিপ্ট",
      gpro_feat3_desc: "ইউটিউব ও মেটা অ্যালগরিদম টার্গেটেড ভাইরাল টপিক রিসার্চ ও ক্যাচি হুক জেনারেশন।",
      gpro_feat4_title: "২৪/৭ আনলিমিটেড স্মার্ট চ্যাট ও মনিটরিং",
      gpro_feat4_desc: "যেকোনো টেকনিক্যাল সাপোর্টে সার্বক্ষণিক ডেডিকেটেড এআই কনসালট্যান্ট ও মানব টিম।",
      gpro_feat5_title: "ফুটেজ স্টোরেজের জন্য ১৫০ জিবি গুগল ক্লাউড ড্রাইভ",
      gpro_feat5_desc: "ভিডিও, অডিও ও মেটাডাটা ব্যাকআপের জন্য ডেডিকেটেড হাই-স্পিড গুগল ক্লাউড ড্রাইভ সরাসরি আপনার জিমেইলে কনফিগার হবে।",

      plan_monthly_title: "মাসিক প্ল্যান",
      plan_monthly_sub: "৩০ দিনের ফুল প্রো এক্সেস",
      plan_monthly_btn: "অর্ডার করুন (১২০ ৳)",
      plan_yearly_title: "বাৎসরিক প্ল্যান",
      plan_yearly_sub: "১২ মাসের আনলিমিটেড সার্ভিস",
      plan_yearly_btn: "অর্ডার করুন (৯৯৯ ৳)",
      plan_popular_badge: "সবচেয়ে জনপ্রিয়",
      plan_special_title: "স্পেশাল ভিআইপি প্ল্যান",
      plan_special_sub: "১৮ মাসের দীর্ঘমেয়াদী প্যাকেজ",
      plan_special_btn: "অর্ডার করুন (১২৯৯ ৳)",
      plan_item1: "✓ Nano Banana ও Veo-3 API এক্সেস",
      plan_item2: "✓ রোবোটিকলেস প্রিমিয়াম ন্যাচারাল TTS",
      plan_item3: "✓ ১৫০ জিবি ডেডিকেটেড গুগল ক্লাউড ড্রাইভ",
      plan_item_m_dur: "✓ ১ মাস নিরবচ্ছিন্ন ভ্যালিডিটি",
      plan_item_y_dur: "✓ ১২ মাস ফুল ভ্যালিডিটি",
      plan_item_y_save: "✓ মেগা ডিসকাউন্ট সেভিংস প্যাকেজ",
      plan_item_s_dur: "✓ ১৮ মাস সম্পূর্ণ লাইসেন্স মেয়াদ",
      plan_item_vip: "✓ ভিআইপি প্রায়োরিটি সাপোর্ট",

      purchase: "অর্ডার ও লাইসেন্সিং",
      price_base_note: "লাইফটাইম লাইসেন্স — ইংরেজি + আপনার পছন্দের ১টি ভাষা অন্তর্ভুক্ত",
      price_addon_note: "অতিরিক্ত প্রতি ভাষা মাত্র ৳{n}",
      tab_software: "💻 AutoMovie Pro লাইফটাইম সফটওয়্যার",
      tab_google_pro: "🚀 স্পেশাল গুগল AI Pro প্যাকেজ",
      name: "আপনার পূর্ণ নাম",
      whatsapp: "WhatsApp নম্বর (অ্যাক্টিভেশনের জন্য)",
      email_opt: "ইমেইল অ্যাড্রেস (ঐচ্ছিক)",
      pick_personal_lang: "কোর প্যাকেজে ইংরেজির সাথে আপনার প্রাথমিক ভাষা বেছে নিন",
      en_included: "ইংরেজি ডিফল্টভাবে সব প্যাকেজে সক্রিয় থাকে।",
      pick_addon_langs: "অতিরিক্ত কোনো গ্লোবাল ভাষা আনলক করতে চান? (+৳{n} / ভাষা)",
      coupon_label: "🎟️ ডিসকাউন্ট কুপন কোড (যেমন: LAUNCH500):",
      coupon_placeholder: "কুপন কোড লিখুন",
      coupon_btn: "অ্যাপ্লাই",
      coupon_checking: "যাচাই করা হচ্ছে...",
      coupon_empty_err: "অনুগ্রহ করে একটি কুপন কোড লিখুন।",
      total_due: "সর্বমোট পরিশোধযোগ্য",
      pay_now: "অর্ডার কনফার্ম করুন",
      or_whatsapp: "অথবা WhatsApp-এ সরাসরি অর্ডার সম্পন্ন করুন",

      reviews_title: "🌟 ভেরিফাইড ক্রিয়েটরদের বাস্তব অভিজ্ঞতা",
      reviews_lead: "অটোমুভি প্রো ব্যবহারকারী সফল ইউটিউবার ও কন্টেন্ট ক্রিয়েটরদের সরাসরি মতামত।",

      faq: "সাধারণ জিজ্ঞাসাসমূহ (FAQ)",
      faq1_q: "AutoMovie Pro-এর লাইসেন্স ফি কত?",
      faq1_a: "মূল সফটওয়্যার লাইসেন্স মাত্র ৳২৯৯৮ — এতে ইংরেজি ছাড়াও আপনার ব্যক্তিগত ১টি ভাষা অন্তর্ভুক্ত থাকে। যেকোনো অতিরিক্ত ভাষা মাত্র ৳৪৯৯ দিয়ে আজীবনের জন্য যুক্ত করা যায়।",
      faq2_q: "সর্বোচ্চ কতগুলো সোশ্যাল মিডিয়া চ্যানেল যোগ করা যাবে?",
      faq2_a: "প্রতিটি ভাষা ও বাজার স্ট্র্যাটেজিতে মিলিয়ে আপনি সর্বোচ্চ ৬টি YouTube চ্যানেল + ৬টি Facebook পেজ/প্রোফাইল + ৬টি TikTok গন্তব্য সম্পূর্ণ স্বয়ংক্রিয়ভাবে পরিচালনা করতে পারবেন।",
      faq3_q: "পেমেন্ট করার পর লাইসেন্স কীভাবে পাব?",
      faq3_a: "অর্ডার ফর্ম সাবমিট করার পর আমাদের WhatsApp সাপোর্টে পেমেন্টের স্ক্রিনশট বা ট্রানজেকশন আইডি পাঠিয়ে দিন। আমাদের টিম তাৎক্ষণিকভাবে ভেরিফাই করে সফটওয়্যার ডাউনলোড লিংক ও লাইসেন্স কি পাঠিয়ে দেবে।",
      faq4_q: "লাইসেন্সের মেয়াদ কতদিন? ভবিষ্যতে আপডেট পাব কি?",
      faq4_a: "AutoMovie Pro-এর কোর লাইসেন্স সম্পূর্ণ আজীবন মেয়াদের (Lifetime License)। কোনো গোপন মাসিক ফি নেই। কোর সফটওয়্যারের নিয়মিত বাগফিক্স ও পারফরম্যান্স আপডেট আজীবন ফ্রি পাবেন।",

      footer_note: "Windows ডেস্কটপ সফটওয়্যার — হাই-পারফরম্যান্স কন্টেন্ট অটোমেশন ইঞ্জিন।",
      rights_reserved: "সর্বস্বত্ব সংরক্ষিত।",

      agent_toggle_btn: "💬 লাইভ সাপোর্ট টিম (অনলাইন)",
      agent_name: "আয়েশা (Ayesha)",
      agent_status: "অনলাইন কনসালট্যান্ট",
      agent_placeholder: "প্যাকেজ, ফিচার বা অফার নিয়ে প্রশ্ন করুন…",
      agent_send: "পাঠান",
      agent_wa_link: "📱 সরাসরি WhatsApp-এ বিস্তারিত কথা বলুন",
      agent_suggestion_1: "প্যাকেজের দাম কত?",
      agent_suggestion_2: "পেমেন্ট কিভাবে করব?",
      agent_suggestion_3: "কুপন কোড দিন",
      agent_suggestion_4: "কিভাবে ভিডিও বানায়?",

      payment_title: "পেমেন্ট করবেন যেভাবে",
      order_title: "অর্ডার ফর্ম",
      order_lead: "প্যাকেজ বেছে নিন, তথ্য দিন — পেমেন্ট সম্পন্ন করে দ্রুত এক্সেস বুঝে নিন।",
      order_error: "অনুগ্রহ করে আপনার নাম ও সঠিক WhatsApp নম্বর প্রদান করুন।",
      wait_title: "পেমেন্ট যাচাইয়ের অপেক্ষায়",
      wait_lead: "আপনার অর্ডারটি গৃহীত হয়েছে। আমাদের টিম পেমেন্ট তথ্য পর্যালোচনা করছে।",
      wait_order: "অর্ডার #{id} সফলভাবে জমা হয়েছে। দ্রুত অ্যাক্টিভেশনের জন্য WhatsApp-এ নক দিন।",
      wa_send: "WhatsApp-এ পেমেন্ট কনফার্ম করুন",
      home: "হোমে ফিরুন",
    },

    en: {
      hero_badge: "🚀 Next-Gen AI Video Automation v4.2",
      site_tagline: "AI-Powered Automated Video Studio — Turn 1 Clip into 18 Channels Across 6 Languages",
      hero_desc: "Stop manual video editing forever. Select your niche once — our industrial-grade AI automatically engineers high-retention scripts, generates cinematic visuals, records studio voiceovers, burns perfect HarfBuzz subtitles, and schedules directly to YouTube, Facebook, and TikTok.",
      see_features: "Explore All Features",
      buy_now: "Get Lifetime License",
      chat_whatsapp: "WhatsApp Consultation",
      active_creators_badge: "1,250+ Active Content Creators",
      studio_badge_live: "🔴 Live Automation Studio Active",
      studio_badge_channels: "⚡ 18 Multi-Channel Automated Stream",
      studio_badge_langs: "🌍 6 Global Markets Perfectly Synced",

      income_title: "Scale Passive Income Across a 6×6×6 Channel Matrix",
      income_lead: "Power up to 6 YouTube channels, 6 Facebook pages, and 6 TikTok accounts simultaneously from a single desktop dashboard. Never hire expensive video editors again — scale globally with one click.",
      pitch_yt: "6 Independent YouTube Channels (in 6 distinct languages)",
      pitch_fb: "6 High-Growth Facebook Pages & Reels Streams",
      pitch_tt: "6 Viral TikTok Destinations",
      pitch_auto: "Smart Scheduler — Runs without keeping your PC awake all day",

      how_it_works: "How It Works",
      how_lead: "4 streamlined steps to global content dominance and revenue.",
      step1: "Select your niche & securely connect your channels (one-time login)",
      step2: "AI generates high-retention Short or Long videos (script + cinematic visuals)",
      step3: "English master seamlessly localizes into regional voices & styled subtitles",
      step4: "Automatically publishes to YouTube, Facebook, and TikTok on your timetable",

      features: "Enterprise-Grade Production Features",
      features_lead: "Engineered for high-performing creators, media networks, and automated channels.",

      gpro_badge: "Special VIP Offer",
      gpro_title: "Special Google AI Pro Package for Zero-Hassle Video Creation",
      gpro_lead: "Unlimited creation without API quota limits or robotic audio! Directly harness Google Pro cloud models, high-resolution cinematic video engines, and 150 GB secure Google Drive storage.",
      gpro_feat1_title: "Google Nano Banana & VEO-3 Cinematic API",
      gpro_feat1_desc: "Full access to ultra-HD cinematic video scenes and studio-grade image synthesis.",
      gpro_feat2_title: "Ultra-Natural Non-Robotic TTS",
      gpro_feat2_desc: "100% human-feeling emotional voiceovers across all 6 languages — free of robotic pitch.",
      gpro_feat3_title: "High-CTR Viral Topics & Scripts",
      gpro_feat3_desc: "Algorithm-optimized viral topic discovery with hooks engineered to capture audience attention.",
      gpro_feat4_title: "24/7 Unlimited Smart Chat & Monitoring",
      gpro_feat4_desc: "Round-the-clock dedicated AI consultation and human technical support.",
      gpro_feat5_title: "150 GB Google Cloud Drive Storage",
      gpro_feat5_desc: "High-speed dedicated Google Drive storage for media backups configured straight to your Gmail.",

      plan_monthly_title: "Monthly Plan",
      plan_monthly_sub: "30 Days Full Pro Access",
      plan_monthly_btn: "Order Now (120 ৳)",
      plan_yearly_title: "Yearly Plan",
      plan_yearly_sub: "12 Months Unlimited Service",
      plan_yearly_btn: "Order Now (999 ৳)",
      plan_popular_badge: "Most Popular",
      plan_special_title: "Special VIP Plan",
      plan_special_sub: "18 Months Extended Access",
      plan_special_btn: "Order Now (1299 ৳)",
      plan_item1: "✓ Nano Banana & Veo-3 API Access",
      plan_item2: "✓ Premium Human-like Natural Voiceovers",
      plan_item3: "✓ 150 GB Dedicated Google Cloud Drive",
      plan_item_m_dur: "✓ 1 Month Uninterrupted Validity",
      plan_item_y_dur: "✓ 12 Months Full Pro Validity",
      plan_item_y_save: "✓ Mega Savings Annual Discount",
      plan_item_s_dur: "✓ 18 Months Extended License Term",
      plan_item_vip: "✓ VIP Priority Technical Assistance",

      purchase: "Order & Licensing",
      price_base_note: "Lifetime License — Includes English + 1 native language of your choice",
      price_addon_note: "Additional languages only ৳{n} each",
      tab_software: "💻 AutoMovie Pro Lifetime Software",
      tab_google_pro: "🚀 Special Google AI Pro Package",
      name: "Your Full Name",
      whatsapp: "WhatsApp Number (for license activation)",
      email_opt: "Email Address (optional)",
      pick_personal_lang: "Choose your primary regional language alongside English",
      en_included: "English is permanently included in all packages.",
      pick_addon_langs: "Unlock additional global language markets? (+৳{n} / language)",
      coupon_label: "🎟️ Discount Coupon Code (e.g., LAUNCH500):",
      coupon_placeholder: "Enter Coupon Code",
      coupon_btn: "Apply",
      coupon_checking: "Verifying...",
      coupon_empty_err: "Please enter a valid coupon code.",
      total_due: "Total Amount Due",
      pay_now: "Confirm Order Now",
      or_whatsapp: "Or Complete Order via WhatsApp",

      reviews_title: "🌟 Verified Creator Testimonials",
      reviews_lead: "Real feedback from successful YouTubers and automated channel operators using AutoMovie Pro.",

      faq: "Frequently Asked Questions (FAQ)",
      faq1_q: "How much does the AutoMovie Pro license cost?",
      faq1_a: "The core desktop lifetime license is only ৳2,998, which includes English plus 1 regional language of your choice. Any additional language can be unlocked forever for only ৳499.",
      faq2_q: "How many social channels can I connect?",
      faq2_a: "Across your language strategies, you can connect and auto-publish to up to 6 YouTube channels + 6 Facebook pages/profiles + 6 TikTok destinations simultaneously.",
      faq3_q: "How do I receive my license after payment?",
      faq3_a: "After submitting the order form, send your payment screenshot or transaction ID to our WhatsApp support. Our verification team will immediately deliver your installer download link and license credentials.",
      faq4_q: "How long is the license valid? Do I get future updates?",
      faq4_a: "AutoMovie Pro core license is 100% Lifetime. There are no recurring monthly subscription charges. Performance upgrades and bugfix releases for the core engine are free forever.",

      footer_note: "Windows Desktop Software — High-Performance Video Automation Platform.",
      rights_reserved: "All rights reserved.",

      agent_toggle_btn: "💬 Live Support Team (Online)",
      agent_name: "Ayesha",
      agent_status: "Online Sales Consultant",
      agent_placeholder: "Ask about packages, pricing, or channels…",
      agent_send: "Send",
      agent_wa_link: "📱 Chat Directly with Ayesha on WhatsApp",
      agent_suggestion_1: "What is the price?",
      agent_suggestion_2: "How do I pay?",
      agent_suggestion_3: "Give me a coupon code",
      agent_suggestion_4: "How does it create videos?",

      payment_title: "How to Complete Your Payment",
      order_title: "Order Checkout",
      order_lead: "Choose your package, provide your details, and unlock instant automated content creation.",
      order_error: "Please enter your full name and a valid WhatsApp number.",
      wait_title: "Payment Verification in Progress",
      wait_lead: "Your order has been recorded. Our team is verifying your payment details.",
      wait_order: "Order #{id} received successfully. Contact WhatsApp for instant priority activation.",
      wa_send: "Confirm Payment via WhatsApp",
      home: "Back to Home",
    },

    hi: {
      hero_badge: "🚀 अगली पीढ़ी का AI वीडियो ऑटोमेशन v4.2",
      site_tagline: "AI-संचालित ऑटोमेटेड वीडियो स्टूडियो — 1 क्लिप से 6 भाषाओं में 18 चैनलों पर ऑटोमेशन",
      hero_desc: "मैनुअल वीडियो एडिटिंग को हमेशा के लिए अलविदा कहें। एक बार निश चुनें — हमारा प्रो AI एल्गोरिदम उच्च-रिटेंशन स्क्रिप्ट, सिनेमाई विज़ुअल्स, स्टूडियो वॉयसओवर और निर्दोष सबटाइटल तैयार करके YouTube, Facebook और TikTok पर ऑटो-शेड्यूल करता है।",
      see_features: "सभी फीचर्स देखें",
      buy_now: "लाइफटाइम लाइसेंस लें",
      chat_whatsapp: "WhatsApp पर बात करें",
      active_creators_badge: "1,250+ सक्रिय कंटेंट क्रिएटर्स",
      studio_badge_live: "🔴 लाइव स्टूडियो इंजन सक्रिय",
      studio_badge_channels: "⚡ 18 चैनलों पर ऑटो-स्ट्रीम",
      studio_badge_langs: "🌍 6 वैश्विक भाषाओं में सटीक सिंक",

      income_title: "6×6×6 चैनल नेटवर्क से अलग-अलग पैसिव इनकम",
      income_lead: "एक ही सॉफ्टवेयर से 6 YouTube चैनल, 6 Facebook पेज और 6 TikTok अकाउंट्स एक साथ चलाएँ। किसी एडिटर की जरूरत नहीं — एक क्लिक में ग्लोबल रीच पाएँ।",
      pitch_yt: "6 स्वतंत्र YouTube चैनल (6 अलग-अलग भाषाओं में)",
      pitch_fb: "6 हाई-ग्रोथ Facebook पेज और रील्स स्ट्रीम",
      pitch_tt: "6 वायरल TikTok अकाउंट्स",
      pitch_auto: "स्मार्ट शेड्यूलर — पीसी बंद रहने पर भी ऑटो-पब्लिशिंग",

      how_it_works: "यह कैसे काम करता है",
      how_lead: "ऑटोमेशन के 4 आसान चरण — विचार से लेकर वैश्विक कमाई तक।",
      step1: "निश चुनें और अपने चैनल सुरक्षित रूप से कनेक्ट करें (एक बार लॉगिन)",
      step2: "AI अपने आप वायरल शॉर्ट्स और लॉन्ग वीडियो तैयार करता है (स्क्रिप्ट + सीन्स)",
      step3: "मास्टर वीडियो से क्षेत्रीय भाषाओं में आवाज़ और सबटाइटल का अनुवाद",
      step4: "तय समय पर सीधे YouTube, Facebook और TikTok पर ऑटो-अपलोड",

      features: "औद्योगिक स्तर के पावरफुल फीचर्स",
      features_lead: "शीर्ष क्रिएटर्स और मीडिया एजेंसियों के लिए तैयार किए गए एडवांस्ड टूल्स।",

      gpro_badge: "विशेष वीआईपी ऑफ़र",
      gpro_title: "बिना किसी झंझट के वीडियो निर्माण के लिए विशेष गूगल AI Pro पैकेज",
      gpro_lead: "कोटा लिमिट या रोबोटिक आवाज़ के बिना अनलिमिटेड क्रिएशन! सीधे गूगल प्रो क्लाउड, हाई-रेज़ोल्यूशन मॉडल और 150 जीबी सुरक्षित ड्राइव बैकअप।",
      gpro_feat1_title: "गूगल Nano Banana और VEO-3 सिनेमाई API",
      gpro_feat1_desc: "अल्ट्रा-एचडी वीडियो सीन्स और प्रो-ग्रेड इमेज जनरेशन का फुल एक्सेस।",
      gpro_feat2_title: "अल्ट्रा-नेचुरल रोबोटिक-मुक्त TTS",
      gpro_feat2_desc: "100% मानवीय भावनाओं वाली बहुभाषी आवाज़ें — रोबोटिक टोन से पूरी तरह मुक्त।",
      gpro_feat3_title: "हाई सीटीआर वायरल टॉपिक्स और स्क्रिप्ट्स",
      gpro_feat3_desc: "यूट्यूब और मेटा एल्गोरिदम पर आधारित ट्रेंडिंग रिसर्च और कैची हुक्स।",
      gpro_feat4_title: "24/7 अनलिमिटेड चैट और मॉनिटरिंग",
      gpro_feat4_desc: "किसी भी तकनीकी सहायता के लिए चौबीसों घंटे समर्पित AI और ह्यूमन सपोर्ट।",
      gpro_feat5_title: "फुटेज स्टोरेज के लिए 150 जीबी गूगल क्लाउड ड्राइव",
      gpro_feat5_desc: "वीडियो और ऑडियो बैकअप के लिए सीधे आपके जीमेल पर कॉन्फ़िगर किया गया हाई-स्पीड स्टोरेज।",

      plan_monthly_title: "मासिक प्लान",
      plan_monthly_sub: "30 दिन का फुल प्रो एक्सेस",
      plan_monthly_btn: "ऑर्डर करें (120 ৳)",
      plan_yearly_title: "वार्षिक प्लान",
      plan_yearly_sub: "12 महीने की असीमित सेवा",
      plan_yearly_btn: "ऑर्डर करें (999 ৳)",
      plan_popular_badge: "सबसे लोकप्रिय",
      plan_special_title: "विशेष वीआईपी प्लान",
      plan_special_sub: "18 महीने का दीर्घकालिक पैकेज",
      plan_special_btn: "ऑर्डर करें (1299 ৳)",
      plan_item1: "✓ Nano Banana और Veo-3 API एक्सेस",
      plan_item2: "✓ प्रीमियम नेचुरल ह्यूमन वॉयसओवर",
      plan_item3: "✓ 150 जीबी समर्पित गूगल क्लाउड ड्राइव",
      plan_item_m_dur: "✓ 1 महीना निर्बाध वैधता",
      plan_item_y_dur: "✓ 12 महीने की पूरी प्रो वैधता",
      plan_item_y_save: "✓ भारी बचत वाला वार्षिक पैकेज",
      plan_item_s_dur: "✓ 18 महीने की विस्तारित लाइसेंस अवधि",
      plan_item_vip: "✓ वीआईपी प्राथमिकता तकनीकी सहायता",

      purchase: "ऑर्डर और लाइसेंसिंग",
      price_base_note: "लाइफटाइम लाइसेंस — अंग्रेज़ी + आपकी पसंद की 1 भाषा शामिल",
      price_addon_note: "अतिरिक्त प्रति भाषा केवल ৳{n}",
      tab_software: "💻 AutoMovie Pro लाइफटाइम सॉफ्टवेयर",
      tab_google_pro: "🚀 स्पेशल गूगल AI Pro पैकेज",
      name: "आपका पूरा नाम",
      whatsapp: "WhatsApp नंबर (सक्रियण के लिए)",
      email_opt: "ईमेल आईडी (वैकल्पिक)",
      pick_personal_lang: "अंग्रेज़ी के साथ अपनी मुख्य भाषा चुनें",
      en_included: "अंग्रेज़ी सभी पैकेजों में स्थायी रूप से शामिल है।",
      pick_addon_langs: "अतिरिक्त भाषाएं अनलॉक करना चाहते हैं? (+৳{n} / भाषा)",
      coupon_label: "🎟️ डिस्काउंट कूपन कोड (उदा: LAUNCH500):",
      coupon_placeholder: "कूपन कोड डालें",
      coupon_btn: "लागू करें",
      coupon_checking: "जाँच हो रही है...",
      coupon_empty_err: "कृपया एक वैध कूपन कोड दर्ज करें।",
      total_due: "कुल देय राशि",
      pay_now: "ऑर्डर कन्फर्म करें",
      or_whatsapp: "या WhatsApp पर सीधे ऑर्डर करें",

      reviews_title: "🌟 सत्यापित क्रिएटर्स की वास्तविक समीक्षाएं",
      reviews_lead: "AutoMovie Pro का उपयोग करने वाले सफल यूट्यूबर्स और चैनल स्वामियों की सीधी राय।",

      faq: "अक्सर पूछे जाने वाले सवाल (FAQ)",
      faq1_q: "AutoMovie Pro की कीमत कितनी है?",
      faq1_a: "कोर लाइफटाइम लाइसेंस मात्र ৳2998 का है, जिसमें अंग्रेज़ी और आपकी 1 चुनी हुई भाषा शामिल है। हर अतिरिक्त भाषा सिर्फ ৳499 में लाइफटाइम अनलॉक की जा सकती है।",
      faq2_q: "मैं कितने चैनल जोड़ सकता हूँ?",
      faq2_a: "आप एक साथ 6 YouTube चैनल + 6 Facebook पेज + 6 TikTok अकाउंट्स को ऑटोमेशन से चला सकते हैं।",
      faq3_q: "भुगतान के बाद लाइसेंस कैसे मिलेगा?",
      faq3_a: "ऑर्डर जमा करने के बाद WhatsApp पर पेमेंट का स्क्रीनशॉट भेजें। हमारी टीम तुरंत सत्यापन करके डाउनलोड लिंक और लाइसेंस प्रदान करेगी।",
      faq4_q: "लाइसेंस की वैधता क्या है? क्या अपडेट मुफ्त हैं?",
      faq4_a: "यह 100% लाइफटाइम लाइसेंस है। कोई मासिक शुल्क नहीं है। कोर सॉफ्टवेयर के लिए सभी बगफिक्स और परफॉर्मेंस अपडेट हमेशा मुफ्त मिलेंगे।",

      footer_note: "Windows डेस्कटॉप सॉफ्टवेयर — हाई-परफॉर्मेंस वीडियो ऑटोमेशन प्लेटफॉर्म।",
      rights_reserved: "सर्वाधिकार सुरक्षित।",

      agent_toggle_btn: "💬 लाइव सपोर्ट टीम (ऑनलाइन)",
      agent_name: "आयशा (Ayesha)",
      agent_status: "ऑनलाइन सेल्स कंसल्टेंट",
      agent_placeholder: "पैकेज, कीमत या फीचर्स के बारे में पूछें…",
      agent_send: "भेजें",
      agent_wa_link: "📱 WhatsApp पर सीधे आयशा से बात करें",
      agent_suggestion_1: "कीमत कितनी है?",
      agent_suggestion_2: "पेमेंट कैसे करें?",
      agent_suggestion_3: "कूपन कोड दें",
      agent_suggestion_4: "वीडियो कैसे बनते हैं?",

      payment_title: "भुगतान कैसे पूरा करें",
      order_title: "ऑर्डर चेकआउट",
      order_lead: "पैकेज चुनें, विवरण दें और तुरंत ऑटोमेटेड क्रिएशन शुरू करें।",
      order_error: "कृपया अपना पूरा नाम और वैध WhatsApp नंबर दर्ज करें।",
      wait_title: "पेमेंट सत्यापन जारी है",
      wait_lead: "आपका ऑर्डर दर्ज कर लिया गया है। टीम पेमेंट की पुष्टि कर रही है।",
      wait_order: "ऑर्डर #{id} प्राप्त हुआ। त्वरित सक्रियण के लिए WhatsApp पर संपर्क करें।",
      wa_send: "WhatsApp पर पेमेंट की पुष्टि करें",
      home: "होमपेज पर लौटें",
    },

    ur: {
      hero_badge: "🚀 نیکسٹ جنریشن AI ویڈیو آٹومیشن v4.2",
      site_tagline: "AI پر مبنی خودکار ویڈیو اسٹوڈیو — 1 کلپ سے 6 زبانوں میں 18 چینلز پر آٹومیشن",
      hero_desc: "دستی ویڈیو ایڈیٹنگ کو ہمیشہ کے لیے خیرباد کہیں۔ صرف ایک بار نچ منتخب کریں — ہمارا جدید الگورتھم خودکار طور پر اسکرپٹ، سنیما ویژولز، اسٹوڈیو وائس اوور اور درست سب ٹائٹلز بنا کر یوٹیوب، فیس بک اور ٹک ٹاک پر شیڈول کرتا ہے۔",
      see_features: "تمام خصوصیات دیکھیں",
      buy_now: "لائف ٹائم لائسنس حاصل کریں",
      chat_whatsapp: "WhatsApp پر مشاورت",
      active_creators_badge: "1,250+ فعال مواد تخلیق کار",
      studio_badge_live: "🔴 لائیو اسٹوڈیو انجن فعال ہے",
      studio_badge_channels: "⚡ 18 چینلز پر خودکار سلسلہ",
      studio_badge_langs: "🌍 6 عالمی زبانوں میں مکمل ہم آہنگی",

      income_title: "6×6×6 چینل نیٹ ورک سے الگ الگ غیر فعال آمدنی",
      income_lead: "ایک ہی سافٹ ویئر سے 6 یوٹیوب چینلز، 6 فیس بک پیجز اور 6 ٹک ٹاک اکاؤنٹس ایک ساتھ چلائیں۔ کسی ایڈیٹر کی ضرورت نہیں — ایک کلک پر عالمی وسعت حاصل کریں۔",
      pitch_yt: "6 خود مختار YouTube چینلز (6 مختلف زبانوں میں)",
      pitch_fb: "6 تیزی سے بڑھتے ہوئے Facebook پیجز اور ریلز",
      pitch_tt: "6 وائرل TikTok اکاؤنٹس",
      pitch_auto: "اسمارٹ شیڈیولنگ — پی سی آن رکھے بغیر خودکار پبلشنگ",

      how_it_works: "یہ کیسے کام کرتا ہے",
      how_lead: "خودکار نظام کے 4 آسان مراحل — خیال سے لے کر عالمی آمدنی تک۔",
      step1: "نچ منتخب کریں اور اپنے چینلز کو محفوظ طریقے سے جوڑیں (ایک بار لاگ ان)",
      step2: "AI خودکار طور پر وائرل شارٹس اور لمبی ویڈیوز بناتا ہے (اسکرپٹ + مناظر)",
      step3: "انگریزی ماسٹر سے مختلف علاقائی زبانوں میں آواز اور سب ٹائٹلز کا تبادلہ",
      step4: "طے شدہ وقت پر براہ راست یوٹیوب، فیس بک اور ٹک ٹاک پر خودکار اپ لوڈ",

      features: "صنعتی معیار کے طاقتور فیچرز",
      features_lead: "عالمی معیار کے مواد تخلیق کاروں اور میڈیا ایجنسیوں کے لیے تیار کردہ ٹولز۔",

      gpro_badge: "خصوصی وی آئی پی پیشکش",
      gpro_title: "بغیر کسی پریشانی کے ویڈیو بنانے کے لیے خصوصی گوگل AI Pro پیکیج",
      gpro_lead: "کوٹہ کی حد یا روبوٹک آواز کی پریشانی کے بغیر لامحدود تخلیق! براہ راست گوگل پرو کلاؤڈ، ہائی ریزولوشن ماڈلز اور محفوظ 150 جی بی ڈرائیو بیک اپ۔",
      gpro_feat1_title: "گوگل Nano Banana اور VEO-3 سنیما API",
      gpro_feat1_desc: "الٹرا ایچ ڈی ویڈیو مناظر اور اسٹوڈیو گریڈ امیج جنریشن تک مکمل رسائی۔",
      gpro_feat2_title: "قدرتی غیر روبوٹک وائس اوور (TTS)",
      gpro_feat2_desc: "100% انسانی جذبات سے بھرپور کثیر لسانی آوازیں — روبوٹک لہجے سے بالکل پاک۔",
      gpro_feat3_title: "ہائی سی ٹی آر وائرل موضوعات اور اسکرپٹس",
      gpro_feat3_desc: "یوٹیوب اور میٹا الگورتھم پر مبنی رجحانات کی تحقیق اور پرکشش ہکس۔",
      gpro_feat4_title: "24/7 لامحدود اسمارٹ چیٹ اور نگرانی",
      gpro_feat4_desc: "کسی بھی تکنیکی مدد کے لیے ہمہ وقت AI مشیر اور انسانی ٹیم دستیاب ہے۔",
      gpro_feat5_title: "فوٹیج اسٹوریج کے لیے 150 جی بی گوگل کلاؤڈ ڈرائیو",
      gpro_feat5_desc: "ویڈیو اور آڈیو بیک اپ کے لیے براہ راست آپ کے جی میل پر تیز رفتار کلاؤڈ اسٹوریج۔",

      plan_monthly_title: "ماہانہ پلان",
      plan_monthly_sub: "30 دن کی مکمل پرو رسائی",
      plan_monthly_btn: "آرڈر کریں (120 ৳)",
      plan_yearly_title: "سالانہ پلان",
      plan_yearly_sub: "12 ماہ کی لامحدود سروس",
      plan_yearly_btn: "آرڈر کریں (999 ৳)",
      plan_popular_badge: "سب سے مقبول",
      plan_special_title: "خصوصی وی آئی پی پلان",
      plan_special_sub: "18 ماہ کی توسیعی رسائی",
      plan_special_btn: "آرڈر کریں (1299 ৳)",
      plan_item1: "✓ Nano Banana اور Veo-3 API رسائی",
      plan_item2: "✓ پریمیم قدرتی انسانی وائس اوور",
      plan_item3: "✓ 150 جی بی گوگل کلاؤڈ ڈرائیو",
      plan_item_m_dur: "✓ 1 ماہ کی بلاتعطل میعاد",
      plan_item_y_dur: "✓ 12 ماہ کی مکمل پرو میعاد",
      plan_item_y_save: "✓ بھاری بچت والا سالانہ پیکیج",
      plan_item_s_dur: "✓ 18 ماہ کی لائف ٹائم لائسنس میعاد",
      plan_item_vip: "✓ وی آئی پی ترجیحی تکنیکی معاونت",

      purchase: "آرڈر اور لائسنسنگ",
      price_base_note: "لائف ٹائم لائسنس — انگریزی + آپ کی منتخب کردہ 1 زبان شامل",
      price_addon_note: "اضافی فی زبان صرف ৳{n}",
      tab_software: "💻 AutoMovie Pro لائف ٹائم سافٹ ویئر",
      tab_google_pro: "🚀 خصوصی گوگل AI Pro پیکیج",
      name: "آپ کا پورا نام",
      whatsapp: "WhatsApp نمبر (فعال کرنے کے لیے)",
      email_opt: "ای میل ایڈریس (اختیاری)",
      pick_personal_lang: "انگریزی کے ساتھ اپنی بنیادی علاقائی زبان منتخب کریں",
      en_included: "انگریزی تمام پیکجز میں مستقل طور پر شامل ہے۔",
      pick_addon_langs: "مزید زبانیں انلاک کرنا چاہتے ہیں؟ (+৳{n} / زبان)",
      coupon_label: "🎟️ ڈسکاؤنٹ کوپن کوڈ (مثلاً: LAUNCH500):",
      coupon_placeholder: "کوپن کوڈ درج کریں",
      coupon_btn: "لاگو کریں",
      coupon_checking: "تصدیق کی جا رہی ہے...",
      coupon_empty_err: "براہ کرم درست کوپن کوڈ درج کریں۔",
      total_due: "کل واجب الادا رقم",
      pay_now: "آرڈر کی تصدیق کریں",
      or_whatsapp: "یا WhatsApp پر براہ راست آرڈر مکمل کریں",

      reviews_title: "🌟 تصدیق شدہ صارفین کے حقیقی تاثرات",
      reviews_lead: "AutoMovie Pro استعمال کرنے والے کامیاب یوٹیوبرز اور کریئیٹرز کی رائے۔",

      faq: "عام سوالات (FAQ)",
      faq1_q: "AutoMovie Pro لائسنس کی قیمت کتنی ہے؟",
      faq1_a: "بنیادی ڈیسک ٹاپ لائف ٹائم لائسنس صرف ৳2998 کا ہے جس میں انگریزی کے ساتھ 1 علاقائی زبان شامل ہے۔ ہر اضافی زبان صرف ৳499 میں ہمیشہ کے لیے انلاک ہو سکتی ہے۔",
      faq2_q: "میں کتنے سوشل چینلز شامل کر سکتا ہوں؟",
      faq2_a: "آپ بیک وقت 6 YouTube چینلز + 6 Facebook پیجز + 6 TikTok اکاؤنٹس خودکار طور پر چلا سکتے ہیں۔",
      faq3_q: "ادائیگی کے بعد مجھے لائسنس کیسے ملے گا؟",
      faq3_a: "آرڈر فارم جمع کرانے کے بعد WhatsApp پر ادائیگی کا اسکرین شاٹ بھیجیں۔ ہماری ٹیم فوری تصدیق کر کے ڈاؤن لوڈ لنک اور لائسنس فراہم کرے گی۔",
      faq4_q: "لائسنس کی میعاد کتنی ہے؟ کیا اپ ڈیٹس مفت ہیں؟",
      faq4_a: "یہ 100% لائف ٹائم لائسنس ہے۔ کوئی ماہانہ فیس نہیں ہے۔ بنیادی سافٹ ویئر کے تمام مستقبل کے اپ ڈیٹس ہمیشہ مفت ملیں گے۔",

      footer_note: "Windows ڈیسک ٹاپ سافٹ ویئر — اعلیٰ کارکردگی والا ویڈیو آٹومیشن پلیٹ فارم۔",
      rights_reserved: "جملہ حقوق محفوظ ہیں۔",

      agent_toggle_btn: "💬 لائیو سپورٹ ٹیم (آن لائن)",
      agent_name: "عائشہ (Ayesha)",
      agent_status: "آن لائن سیلز کنسلٹنٹ",
      agent_placeholder: "پیکیج، قیمت یا فیچرز کے بارے میں پوچھیں…",
      agent_send: "بھیجیں",
      agent_wa_link: "📱 براہ راست WhatsApp پر عائشہ سے بات کریں",
      agent_suggestion_1: "پیکیج کی قیمت کتنی ہے؟",
      agent_suggestion_2: "ادائیگی کیسے کروں؟",
      agent_suggestion_3: "کوپن کوڈ دیں",
      agent_suggestion_4: "ویڈیوز کیسے بنتی ہیں؟",

      payment_title: "ادائیگی کا طریقہ کار",
      order_title: "آرڈر فارم",
      order_lead: "پیکیج منتخب کریں، معلومات دیں اور فوراً مواد بنانا شروع کریں۔",
      order_error: "براہ کرم اپنا پورا نام اور درست WhatsApp نمبر درج کریں۔",
      wait_title: "ادائیگی کی تصدیق جاری ہے",
      wait_lead: "آپ کا آرڈر درج ہو چکا ہے۔ ٹیم تصدیق کر رہی ہے۔",
      wait_order: "آرڈر #{id} موصول ہوا۔ فوری فعالیت کے لیے WhatsApp پر رابطہ کریں۔",
      wa_send: "WhatsApp پر ادائیگی کی تصدیق کریں",
      home: "ہوم پیج پر واپس جائیں",
    },

    ta: {
      hero_badge: "🚀 அடுத்த தலைமுறை AI வீடியோ ஆட்டோமேஷன் v4.2",
      site_tagline: "AI தானியங்கி வீடியோ ஸ்டுடியோ — 1 கிளிப்பிலிருந்து 6 மொழிகளில் 18 சேனல்களுக்கு ஆட்டோமேஷன்",
      hero_desc: "கைமுறை வீடியோ எடிட்டிங்கை நிரந்தரமாக நிறுத்துங்கள். ஒரு முறை நிஷ் தேர்ந்தெடுங்கள் — எங்கள் AI தானாகவே சிறந்த ஸ்கிரிப்ட், சினிமா காட்சிகள், ஸ்டுடியோ குரல் மற்றும் துல்லியமான சப்டைட்டில்களை உருவாக்கி YouTube, Facebook மற்றும் TikTok-ல் பதிவேற்றும்.",
      see_features: "அனைத்து அம்சங்களையும் காண்க",
      buy_now: "வாழ்நாள் உரிமம் பெறுங்கள்",
      chat_whatsapp: "WhatsApp ஆலோசனை",
      active_creators_badge: "1,250+ செயலில் உள்ள படைப்பாளர்கள்",
      studio_badge_live: "🔴 நேரடி ஸ்டுடியோ இயங்குகிறது",
      studio_badge_channels: "⚡ 18 சேனல்களில் தானியங்கி ஸ்ட்ரீம்",
      studio_badge_langs: "🌍 6 உலக மொழிகளில் துல்லிய ஒத்திசைவு",

      income_title: "6×6×6 சேனல் நெட்வொர்க்கிலிருந்து தனித்தனி வருமானம்",
      income_lead: "ஒரே மென்பொருளிலிருந்து 6 YouTube சேனல்கள், 6 Facebook பக்கங்கள் மற்றும் 6 TikTok கணக்குகளை ஒரே நேரத்தில் இயக்குங்கள். எடிட்டரை பணியமர்த்த தேவையில்லை.",
      pitch_yt: "6 தனித்துவமான YouTube சேனல்கள் (6 மொழிகளில்)",
      pitch_fb: "6 அதிவேக Facebook பக்கங்கள் & ரீல்ஸ்",
      pitch_tt: "6 வைரல் TikTok கணக்குகள்",
      pitch_auto: "ஸ்மார்ட் ஷெட்யூலர் — பிசி ஆன் செய்யாமலே தானியங்கி பதிவேற்றம்",

      how_it_works: "எவ்வாறு செயல்படுகிறது",
      how_lead: "ஆட்டோமேஷனின் 4 எளிய படிகள் — சிந்தனையிலிருந்து சர்வதேச வருமானம் வரை.",
      step1: "நிஷ் தேர்ந்தெடுத்து உங்கள் சேனல்களை பாதுகாப்பாக இணையுங்கள் (ஒருமுறை உள்நுழைவு)",
      step2: "AI தானாகவே வைரல் ஷார்ட்ஸ் மற்றும் நீண்ட வீடியோக்களை உருவாக்குகிறது",
      step3: "ஆங்கிலத்திலிருந்து பிராந்திய குரல் மற்றும் சப்டைட்டில்களுக்கு துல்லிய மாற்றம்",
      step4: "திட்டமிட்ட நேரத்தில் YouTube, Facebook, TikTok-ல் தானாக பதிவேற்றம்",

      features: "தொழில்துறை அளவிலான சக்திவாய்ந்த அம்சங்கள்",
      features_lead: "சிறந்த படைப்பாளிகள் மற்றும் ஊடக நிறுவனங்களுக்காக உருவாக்கப்பட்ட கருவிகள்.",

      gpro_badge: "சிறப்பு விஐபி சலுகை",
      gpro_title: "எந்த தொந்தரவும் இல்லாமல் வீடியோ உருவாக்க சிறப்பு Google AI Pro தொகுப்பு",
      gpro_lead: "கோட்டா வரம்புகள் அல்லது ரோபோடிக் குரல் இல்லாமல் எல்லையற்ற உருவாக்கம்! கூகிள் ப்ரோ கிளவுட் மற்றும் 150 ஜிபி பாதுகாப்பான டிரைவ் சேமிப்பு.",
      gpro_feat1_title: "Google Nano Banana & VEO-3 சினிமா API",
      gpro_feat1_desc: "அல்ட்ரா-எச்டி சினிமா வீடியோ காட்சிகள் மற்றும் உயர் ரக பட உருவாக்க அணுகல்.",
      gpro_feat2_title: "இயற்கையான ரோபோடிக்-இல்லாத குரல் (TTS)",
      gpro_feat2_desc: "100% மனித உணர்வுமிக்க பலமொழி குரல்கள் — ரோபோ தொனி இல்லாமல்.",
      gpro_feat3_title: "அதிக CTR வைரல் தலைப்புகள் & ஸ்கிரிப்ட்கள்",
      gpro_feat3_desc: "அல்காரிதம் இலக்கு வைரல் தலைப்பு ஆராய்ச்சி மற்றும் சிறந்த ஹூக்குகள்.",
      gpro_feat4_title: "24/7 வரம்பற்ற ஸ்மார்ட் அரட்டை & கண்காணிப்பு",
      gpro_feat4_desc: "தொழில்நுட்ப உதவிக்கு எப்போதும் அர்ப்பணிக்கப்பட்ட AI மற்றும் மனித ஆதரவு.",
      gpro_feat5_title: "150 ஜிபி Google Cloud Drive சேமிப்பகம்",
      gpro_feat5_desc: "நேரடியாக உங்கள் ஜிமெயிலில் கட்டமைக்கப்படும் அதிவேக கிளவுட் டிரைவ்.",

      plan_monthly_title: "மாதாந்திர திட்டம்",
      plan_monthly_sub: "30 நாட்கள் முழு ப்ரோ அணுகல்",
      plan_monthly_btn: "ஆர்டர் செய்க (120 ৳)",
      plan_yearly_title: "வருடாந்திர திட்டம்",
      plan_yearly_sub: "12 மாத வரம்பற்ற சேவை",
      plan_yearly_btn: "ஆர்டர் செய்க (999 ৳)",
      plan_popular_badge: "மிகவும் பிரபலமானது",
      plan_special_title: "சிறப்பு விஐபி திட்டம்",
      plan_special_sub: "18 மாத நீண்டகால தொகுப்பு",
      plan_special_btn: "ஆர்டர் செய்க (1299 ৳)",
      plan_item1: "✓ Nano Banana & Veo-3 API அணுகல்",
      plan_item2: "✓ பிரீமியம் இயற்கை மனித குரல்",
      plan_item3: "✓ 150 ஜிபி கூகிள் கிளவுட் டிரைவ்",
      plan_item_m_dur: "✓ 1 மாத தடையற்ற செல்லுபடி",
      plan_item_y_dur: "✓ 12 மாத முழு ப்ரோ செல்லுபடி",
      plan_item_y_save: "✓ பெரும் சேமிப்பு வருடாந்திர சலுகை",
      plan_item_s_dur: "✓ 18 மாத நீட்டிக்கப்பட்ட உரிம காலம்",
      plan_item_vip: "✓ விஐபி முன்னுரிமை தொழில்நுட்ப உதவி",

      purchase: "ஆர்டர் & உரிமம்",
      price_base_note: "வாழ்நாள் உரிமம் — ஆங்கிலம் + உங்கள் விருப்ப மொழி 1 அடங்கும்",
      price_addon_note: "கூடுதல் மொழி ஒவ்வொன்றும் வெறும் ৳{n}",
      tab_software: "💻 AutoMovie Pro வாழ்நாள் மென்பொருள்",
      tab_google_pro: "🚀 சிறப்பு Google AI Pro தொகுப்பு",
      name: "உங்கள் முழுப் பெயர்",
      whatsapp: "WhatsApp எண் (செயல்படுத்தலுக்கு)",
      email_opt: "மின்னஞ்சல் முகவரி (விருப்பத்திற்கு)",
      pick_personal_lang: "ஆங்கிலத்துடன் உங்கள் முதன்மை மொழியைத் தேர்ந்தெடுக்கவும்",
      en_included: "ஆங்கிலம் அனைத்து தொகுப்புகளிலும் நிரந்தரமாக உள்ளது.",
      pick_addon_langs: "கூடுதல் மொழிகளை அன்லாக் செய்ய வேண்டுமா? (+৳{n} / மொழி)",
      coupon_label: "🎟️ தள்ளுபடி கூப்பன் குறியீடு (उदा: LAUNCH500):",
      coupon_placeholder: "கூப்பன் குறியீட்டை உள்ளிடவும்",
      coupon_btn: "பயன்படுத்து",
      coupon_checking: "சரிபார்க்கப்படுகிறது...",
      coupon_empty_err: "சரியான கூப்பன் குறியீட்டை உள்ளிடவும்.",
      total_due: "மொத்த செலுத்த வேண்டிய தொகை",
      pay_now: "ஆர்டரை உறுதிப்படுத்தவும்",
      or_whatsapp: "அல்லது WhatsApp மூலம் ஆர்டர் செய்யவும்",

      reviews_title: "🌟 சரிபார்க்கப்பட்ட படைப்பாளர்களின் விமர்சனங்கள்",
      reviews_lead: "AutoMovie Pro பயன்படுத்தும் வெற்றிகரமான யூடியூபர்களின் நேரடி கருத்துக்கள்.",

      faq: "அடிக்கடி கேட்கப்படும் கேள்விகள் (FAQ)",
      faq1_q: "AutoMovie Pro உரிமக் கட்டணம் எவ்வளவு?",
      faq1_a: "அடிப்படை வாழ்நாள் உரிமம் வெறும் ৳2998 மட்டுமே (ஆங்கிலம் + 1 பிராந்திய மொழி). கூடுதல் மொழிகளை தலா ৳499-ல் வாழ்நாளுக்கு அன்லாக் செய்யலாம்.",
      faq2_q: "எத்தனை சமூக வலைதள சேனல்களை இணைக்கலாம்?",
      faq2_a: "நீங்கள் ஒரே நேரத்தில் 6 YouTube + 6 Facebook + 6 TikTok சேனல்களை இணைத்து இயக்கலாம்.",
      faq3_q: "பணம் செலுத்திய பிறகு உரிமம் எப்படி கிடைக்கும்?",
      faq3_a: "ஆர்டர் சமர்ப்பித்த பின் WhatsApp-ல் ரசீதை அனுப்பவும். எங்கள் குழு உடனடியாக சரிபார்த்து பதிவிறக்க இணைப்பு மற்றும் உரிமத்தை வழங்கும்.",
      faq4_q: "உரிமத்தின் காலம் என்ன? புதுப்பிப்புகள் இலவசமா?",
      faq4_a: "இது 100% வாழ்நாள் உரிமம். மாதாந்திர கட்டணம் இல்லை. அனைத்து எதிர்கால பிழைத்திருத்தங்கள் மற்றும் புதுப்பிப்புகள் முற்றிலும் இலவசம்.",

      footer_note: "Windows டெஸ்க்டாப் மென்பொருள் — உயர் செயல்திறன் வீடியோ ஆட்டோமேஷன் தளம்.",
      rights_reserved: "அனைத்து உரிமைகளும் பாதுகாக்கப்பட்டவை.",

      agent_toggle_btn: "👩‍💼 ஆயிஷா (நேரடி விற்பனை ஆலோசகர்)",
      agent_name: "ஆயிஷா (Ayesha)",
      agent_status: "ஆன்லைன் விற்பனை ஆலோசகர்",
      agent_placeholder: "தொகுப்புகள், விலை அல்லது அம்சங்கள் பற்றி கேளுங்கள்…",
      agent_send: "அனுப்பு",
      agent_wa_link: "📱 WhatsApp-ல் ஆயிஷாவுடன் நேரடியாக பேசுங்கள்",
      agent_suggestion_1: "விலை எவ்வளவு?",
      agent_suggestion_2: "பணம் செலுத்துவது எப்படி?",
      agent_suggestion_3: "கூப்பன் குறியீடு கொடுங்கள்",
      agent_suggestion_4: "வீடியோக்கள் எப்படி உருவாகின்றன?",

      payment_title: "பணம் செலுத்தும் முறை",
      order_title: "ஆர்டர் படிவம்",
      order_lead: "தொகுப்பைத் தேர்ந்தெடுத்து விவரங்களை வழங்கி உடனே தொடங்கவும்.",
      order_error: "உங்கள் பெயர் மற்றும் சரியான WhatsApp எண்ணை உள்ளிடவும்.",
      wait_title: "பணம் சரிபார்க்கப்படுகிறது",
      wait_lead: "உங்கள் ஆர்டர் பெறப்பட்டது. எங்கள் குழு சரிபார்க்கிறது.",
      wait_order: "ஆர்டர் #{id} வெற்றிகரமாக பெறப்பட்டது. உடனடி செயல்பாட்டிற்கு WhatsApp-ல் தொடர்பு கொள்ளவும்.",
      wa_send: "WhatsApp-ல் உறுதிப்படுத்தவும்",
      home: "முகப்புக்கு திரும்புக",
    },

    ml: {
      hero_badge: "🚀 അടുത്ത തലമുറ AI വീഡിയോ ഓട്ടോമേഷൻ v4.2",
      site_tagline: "AI ഓട്ടോമേറ്റഡ് വീഡിയോ സ്റ്റുഡിയോ — 1 ക്ലിപ്പിൽ നിന്ന് 6 ഭാഷകളിൽ 18 ചാനലുകളിലേക്ക് ഓട്ടോമേഷൻ",
      hero_desc: "മാനുവൽ വീഡിയോ എഡിറ്റിംഗ് എന്നെന്നേക്കുമായി അവസാനിപ്പിക്കൂ. ഒരു നിച്ച് തിരഞ്ഞെടുക്കൂ — ഞങ്ങളുടെ AI സ്ക്രിപ്റ്റ്, സിനിമാറ്റിക് വിഷ്വലുകൾ, സ്റ്റുഡിയോ വോയ്‌സ്ഓവർ, കൃത്യമായ സബ്‌ടൈറ്റിലുകൾ എന്നിവ തയ്യാറാക്കി YouTube, Facebook, TikTok എന്നിവയിലേക്ക് ഷെഡ്യൂൾ ചെയ്യുന്നു.",
      see_features: "എല്ലാ ഫീച്ചറുകളും കാണുക",
      buy_now: "ലൈഫ്‌ടൈം ലൈസൻസ് നേടുക",
      chat_whatsapp: "WhatsApp കൺസൾട്ടേഷൻ",
      active_creators_badge: "1,250+ സജീവ കണ്ടന്റ് ക്രിയേറ്റർമാർ",
      studio_badge_live: "🔴 ലൈവ് സ്റ്റുഡിയോ എഞ്ചിൻ സജീവം",
      studio_badge_channels: "⚡ 18 ചാനലുകളിൽ ഓട്ടോ-സ്ട്രീം",
      studio_badge_langs: "🌍 6 ആഗോള ഭാഷകളിൽ കൃത്യമായ സമന്വയം",

      income_title: "6×6×6 ചാനൽ ശൃംഖലയിൽ നിന്ന് വ്യത്യസ്ത വരുമാനം",
      income_lead: "ഒരു സോഫ്റ്റ്‌വെയറിൽ നിന്ന് 6 YouTube ചാനലുകൾ, 6 Facebook പേജുകൾ, 6 TikTok അക്കൗണ്ടുകൾ ഒരേസമയം നിയന്ത്രിക്കുക. എഡിറ്ററെ ആവശ്യമില്ല — ഒറ്റ ക്ലിക്കിൽ ആഗോള റീച്ച്.",
      pitch_yt: "6 വ്യത്യസ്ത YouTube ചാനലുകൾ (6 ഭാഷകളിൽ)",
      pitch_fb: "6 ഹൈ-ഗ്രോത്ത് Facebook പേജുകളും റീൽസും",
      pitch_tt: "6 വൈറൽ TikTok ലക്ഷ്യങ്ങൾ",
      pitch_auto: "സ്മാർട്ട് ഷെഡ്യൂളർ — കമ്പ്യൂട്ടർ ഓൺ ചെയ്യാതെ തന്നെ ഓട്ടോ-പബ്ലിഷിംഗ്",

      how_it_works: "എങ്ങനെ പ്രവർത്തിക്കുന്നു",
      how_lead: "ഓട്ടോമേഷന്റെ 4 ലളിതമായ ഘട്ടങ്ങൾ — ആശയത്തിൽ നിന്ന് അന്താരാഷ്ട്ര വരുമാനത്തിലേക്ക്.",
      step1: "നിച്ച് തിരഞ്ഞെടുത്ത് നിങ്ങളുടെ ചാനലുകൾ സുരക്ഷിതമായി ബന്ധിപ്പിക്കുക (ഒറ്റ ലോഗിൻ)",
      step2: "AI സ്വയമേവ വൈറൽ ഷോർട്ട്സും ലോംഗ് വീഡിയോകളും നിർമ്മിക്കുന്നു",
      step3: "ഇംഗ്ലീഷിൽ നിന്ന് പ്രാദേശിക ശബ്ദത്തിലേക്കും സബ്‌ടൈറ്റിലുകളിലേക്കും മാറ്റം",
      step4: "നിശ്ചിത സമയത്ത് YouTube, Facebook, TikTok എന്നിവയിലേക്ക് സ്വയം അപ്‌ലോഡ്",

      features: "വ്യാവസായിക തലത്തിലുള്ള കരുത്തുറ്റ ഫീച്ചറുകൾ",
      features_lead: "മികച്ച ക്രിയേറ്റർമാർക്കും മീഡിയ ഏജൻസികൾക്കുമായി രൂപകൽപ്പന ചെയ്ത ടൂളുകൾ.",

      gpro_badge: "പ്രത്യേക വിഐപി ഓഫർ",
      gpro_title: "തടസ്സങ്ങളില്ലാതെ വീഡിയോ നിർമ്മാണത്തിന് പ്രത്യേക ഗൂഗിൾ AI Pro പാക്കേജ്",
      gpro_lead: "ക്വോട്ട പരിധികളോ റോബോട്ടിക് ശബ്ദമോ ഇല്ലാതെ അൺലിമിറ്റഡ് ക്രിയേഷൻ! ഗൂഗിൾ പ്രോ ക്ലൗഡ് മോഡലുകളും 150 ജിബി സുരക്ഷിത ഡ്രൈവ് ബാക്കപ്പും.",
      gpro_feat1_title: "Google Nano Banana & VEO-3 സിനിമാറ്റിക് API",
      gpro_feat1_desc: "അൾട്രാ-എച്ച്ഡി സിനിമാറ്റിക് വീഡിയോ രംഗങ്ങളും പ്രൊഫഷണൽ ഇമേജ് ജനറേഷനും.",
      gpro_feat2_title: "സ്വാഭാവിക റോബോട്ടിക്-രഹിത വോയ്‌സ്ഓവർ (TTS)",
      gpro_feat2_desc: "100% മാനുഷിക വികാരങ്ങൾ നിറഞ്ഞ ബഹുഭാഷാ ശബ്ദങ്ങൾ — റോബോട്ടിക് ടോൺ ഇല്ലാതെ.",
      gpro_feat3_title: "ഉയർന്ന CTR വൈറൽ വിഷയങ്ങളും സ്ക്രിപ്റ്റുകളും",
      gpro_feat3_desc: "അൽഗോരിതം അടിസ്ഥാനമാക്കിയുള്ള ട്രെൻഡിംഗ് വിഷയ ഗവേഷണവും മികച്ച ഹുക്കുകളും.",
      gpro_feat4_title: "24/7 അൺലിമിറ്റഡ് സ്മാർട്ട് ചാറ്റും നിരീക്ഷണവും",
      gpro_feat4_desc: "ഏത് സാങ്കേതിക സഹായത്തിനും എപ്പോഴും സമർപ്പിത AI, ഹ്യൂമൻ സപ്പോർട്ട്.",
      gpro_feat5_title: "ഫൂട്ടേജ് സംഭരണത്തിനായി 150 ജിബി ഗൂഗിൾ ക്ലൗഡ് ഡ്രൈവ്",
      gpro_feat5_desc: "വീഡിയോ, ഓഡിയോ ബാക്കപ്പിനായി നേരിട്ട് നിങ്ങളുടെ ജിമെയിലിൽ ലഭ്യമാകുന്ന അതിവേഗ സംഭരണം.",

      plan_monthly_title: "പ്രതിമാസ പ്ലാൻ",
      plan_monthly_sub: "30 ദിവസത്തെ പൂർണ്ണ പ്രോ ആക്സസ്",
      plan_monthly_btn: "ഓർഡർ ചെയ്യുക (120 ৳)",
      plan_yearly_title: "വാർഷിക പ്ലാൻ",
      plan_yearly_sub: "12 മാസത്തെ അൺലിമിറ്റഡ് സർവീസ്",
      plan_yearly_btn: "ഓർഡർ ചെയ്യുക (999 ৳)",
      plan_popular_badge: "ഏറ്റവും ജനപ്രിയം",
      plan_special_title: "പ്രത്യേക വിഐപി പ്ലാൻ",
      plan_special_sub: "18 മാസത്തെ ദീർഘകാല പാക്കേജ്",
      plan_special_btn: "ഓർഡർ ചെയ്യുക (1299 ৳)",
      plan_item1: "✓ Nano Banana & Veo-3 API ആക്സസ്",
      plan_item2: "✓ പ്രീമിയം സ്വാഭാവിക വോയ്‌സ്ഓവറുകൾ",
      plan_item3: "✓ 150 ജിബി ഡെഡിക്കേറ്റഡ് ഗൂഗിൾ ക്ലൗഡ് ഡ്രൈവ്",
      plan_item_m_dur: "✓ 1 മാസം തടസ്സമില്ലാത്ത സാധുത",
      plan_item_y_dur: "✓ 12 മാസം പൂർണ്ണ പ്രോ സാധുത",
      plan_item_y_save: "✓ വൻ ലാഭമുള്ള വാർഷിക ഡിസ്കൗണ്ട് പാക്കേജ്",
      plan_item_s_dur: "✓ 18 മാസത്തെ വിപുലീകൃത ലൈസൻസ് കാലാവധി",
      plan_item_vip: "✓ വിഐപി മുൻഗണനാ സാങ്കേതിക സഹായം",

      purchase: "ഓർഡറും ലൈസൻസിംഗും",
      price_base_note: "ലൈഫ്‌ടൈം ലൈസൻസ് — ഇംഗ്ലീഷ് + നിങ്ങളുടെ ഇഷ്ടഭാഷ 1 ഉൾപ്പെടുന്നു",
      price_addon_note: "ഓരോ അധിക ഭാഷയ്ക്കും വെറും ৳{n}",
      tab_software: "💻 AutoMovie Pro ലൈഫ്‌ടൈം സോഫ്റ്റ്‌വെയർ",
      tab_google_pro: "🚀 പ്രത്യേക Google AI Pro പാക്കേജ്",
      name: "നിങ്ങളുടെ പൂർണ്ണ നാമം",
      whatsapp: "WhatsApp നമ്പർ (ആക്റ്റിവേഷനായി)",
      email_opt: "ഇമെയിൽ വിലാസം (ഓപ്ഷണൽ)",
      pick_personal_lang: "ഇംഗ്ലീഷിനൊപ്പം നിങ്ങളുടെ പ്രാദേശിക ഭാഷ തിരഞ്ഞെടുക്കുക",
      en_included: "ഇംഗ്ലീഷ് എല്ലാ പാക്കേജുകളിലും സ്ഥിരമായി ഉൾപ്പെടുത്തിയിട്ടുണ്ട്.",
      pick_addon_langs: "കൂടുതൽ ഭാഷകൾ അൺലോക്ക് ചെയ്യണോ? (+৳{n} / ഭാഷ)",
      coupon_label: "🎟️ ഡിസ്കൗണ്ട് കൂപ്പൺ കോഡ് (ഉദാ: LAUNCH500):",
      coupon_placeholder: "കൂപ്പൺ കോഡ് നൽകുക",
      coupon_btn: "അപ്ലൈ ചെയ്യുക",
      coupon_checking: "പരിശോധിക്കുന്നു...",
      coupon_empty_err: "ദയവായി സാധുവായ ഒരു കൂപ്പൺ കോഡ് നൽകുക.",
      total_due: "ആകെ അടയ്ക്കേണ്ട തുക",
      pay_now: "ഓർഡർ സ്ഥിരീകരിക്കുക",
      or_whatsapp: "അല്ലെങ്കിൽ WhatsApp വഴി നേരിട്ട് ഓർഡർ ചെയ്യുക",

      reviews_title: "🌟 പരിശോധിച്ച ക്രിയേറ്റർമാരുടെ അനുഭവങ്ങൾ",
      reviews_lead: "AutoMovie Pro ഉപയോഗിക്കുന്ന വിജയകരമായ യൂട്യൂബർമാരുടെ നേരിട്ടുള്ള അഭിപ്രായങ്ങൾ.",

      faq: "പതിവായി ചോദിക്കുന്ന ചോദ്യങ്ങൾ (FAQ)",
      faq1_q: "AutoMovie Pro ലൈസൻസ് നിരക്ക് എത്രയാണ്?",
      faq1_a: "പ്രധാന ലൈഫ്‌ടൈം ലൈസൻസിന് വെറും ৳2998 മാത്രം (ഇംഗ്ലീഷ് + 1 ഇഷ്ടഭാഷ). ഓരോ അധിക ഭാഷയ്ക്കും ৳499 നൽകി എന്നെന്നേക്കുമായി അൺലോക്ക് ചെയ്യാം.",
      faq2_q: "എനിക്ക് എത്ര ചാനലുകൾ ബന്ധിപ്പിക്കാം?",
      faq2_a: "നിങ്ങൾക്ക് ഒരേസമയം 6 YouTube ചാനലുകൾ + 6 Facebook പേജുകൾ + 6 TikTok അക്കൗണ്ടുകൾ ഓട്ടോമേറ്റ് ചെയ്യാം.",
      faq3_q: "പേയ്‌മെന്റിന് ശേഷം ലൈസൻസ് എങ്ങനെ ലഭിക്കും?",
      faq3_a: "ഓർഡർ നൽകിയ ശേഷം WhatsApp-ൽ സ്ക്രീൻഷോട്ട് അയയ്ക്കുക. ഞങ്ങളുടെ ടീം പരിശോധിച്ചു ഉടൻ തന്നെ ഡൗൺലോഡ് ലിങ്കും ലൈസൻസും നൽകും.",
      faq4_q: "ലൈസൻസിന്റെ കാലാവധി എത്രയാണ്? അപ്ഡേറ്റുകൾ സൗജന്യമാണോ?",
      faq4_a: "ഇത് 100% ലൈഫ്‌ടൈം ലൈസൻസാണ്. പ്രതിമാസ ഫീസുകളില്ല. ഭാവിയിലെ എല്ലാ പ്രകടന അപ്ഡേറ്റുകളും തികച്ചും സൗജന്യമാണ്.",

      footer_note: "Windows ഡെസ്ക്ടോപ്പ് സോഫ്റ്റ്‌വെയർ — ഹൈ-പെർഫോമൻസ് വീഡിയോ ഓട്ടോമേഷൻ പ്ലാറ്റ്‌ഫോം.",
      rights_reserved: "എല്ലാ അവകാശങ്ങളും നിക്ഷിപ്തം.",

      agent_toggle_btn: "💬 ലൈവ് സപ്പോർട്ട് ടീം (ഓൺലൈൻ)",
      agent_name: "ആയിഷ (Ayesha)",
      agent_status: "ഓൺലൈൻ സെയിൽസ് കൺസൾട്ടന്റ്",
      agent_placeholder: "പാക്കേജുകൾ, വില അല്ലെങ്കിൽ സവിശേഷതകൾ ചോദിക്കുക…",
      agent_send: "അയക്കുക",
      agent_wa_link: "📱 WhatsApp-ൽ ആയിഷയോട് നേരിട്ട് സംസാരിക്കുക",
      agent_suggestion_1: "വില എത്രയാണ്?",
      agent_suggestion_2: "പേയ്‌മെന്റ് എങ്ങനെ ചെയ്യാം?",
      agent_suggestion_3: "കൂപ്പൺ കോഡ് തരുമോ?",
      agent_suggestion_4: "വീഡിയോ എങ്ങനെ ഉണ്ടാക്കാം?",

      payment_title: "പേയ്‌മെന്റ് പൂർത്തിയാക്കേണ്ട വിധം",
      order_title: "ഓർഡർ ചെക്ക്ഔട്ട്",
      order_lead: "പാക്കേജ് തിരഞ്ഞെടുത്ത് വിവരങ്ങൾ നൽകി ഉടൻ ആരംഭിക്കുക.",
      order_error: "ദയവായി നിങ്ങളുടെ പേരും കൃത്യമായ WhatsApp നമ്പറും നൽകുക.",
      wait_title: "പേയ്‌മെന്റ് പരിശോധന പുരോഗമിക്കുന്നു",
      wait_lead: "നിങ്ങളുടെ ഓർഡർ രേഖപ്പെടുത്തിയിട്ടുണ്ട്. ടീം പരിശോധിക്കുന്നു.",
      wait_order: "ഓർഡർ #{id} ലഭിച്ചു. വേഗത്തിലുള്ള ആക്റ്റിവേഷനായി WhatsApp-ൽ ബന്ധപ്പെടുക.",
      wa_send: "WhatsApp വഴി സ്ഥിരീകരിക്കുക",
      home: "ഹോംപേജിലേക്ക് മടങ്ങുക",
    },
  };

  function t(key, vars) {
    const lang = localStorage.getItem("amp_ui_lang") || "bn";
    const pack = PACKS[lang] || PACKS.bn || {};
    let s = pack[key];
    if (s === undefined) {
      s = (PACKS.en && PACKS.en[key]) !== undefined ? PACKS.en[key] : (PACKS.bn && PACKS.bn[key]) || key;
    }
    if (vars && typeof vars === "object") {
      Object.keys(vars).forEach((k) => {
        s = String(s).split(`{${k}}`).join(String(vars[k]));
      });
    }
    return s;
  }

  function apply() {
    const lang = localStorage.getItem("amp_ui_lang") || "bn";
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ur" ? "rtl" : "ltr";

    // Text & HTML translations
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (!key) return;
      const varsAttr = el.getAttribute("data-i18n-vars");
      let vars;
      try {
        vars = varsAttr ? JSON.parse(varsAttr) : undefined;
      } catch (_) {
        vars = undefined;
      }
      const val = t(key, vars);
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        if (el.hasAttribute("data-i18n-placeholder")) el.placeholder = val;
      } else if (el.hasAttribute("data-i18n-html")) {
        el.innerHTML = val;
      } else {
        el.textContent = val;
      }
    });

    // Placeholder translations
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      if (key) el.placeholder = t(key);
    });

    // Update order CTA urls with current language
    document.querySelectorAll('a[href*="order.php"]').forEach((a) => {
      try {
        const u = new URL(a.href, window.location.origin);
        u.searchParams.set("lang", lang);
        a.href = u.pathname + u.search;
      } catch (_) {}
    });

    const sel = document.getElementById("siteLangSelect");
    if (sel) sel.value = lang;

    window.dispatchEvent(new CustomEvent("amp-lang-change", { detail: { lang } }));
  }

  function mountSelect() {
    let sel = document.getElementById("siteLangSelect");
    if (!sel) {
      const header = document.querySelector(".site-header");
      if (!header) return;
      const wrap = document.createElement("div");
      wrap.className = "lang-switch";
      sel = document.createElement("select");
      sel.id = "siteLangSelect";
      sel.setAttribute("aria-label", "Language");
      wrap.appendChild(sel);
      const cta = header.querySelector(".btn, .btn-sm");
      if (cta) header.insertBefore(wrap, cta);
      else header.appendChild(wrap);
    }
    const params = new URLSearchParams(window.location.search);
    const urlLang = params.get("lang");
    if (urlLang && PACKS[urlLang]) {
      localStorage.setItem("amp_ui_lang", urlLang);
      document.cookie = "amp_ui_lang=" + encodeURIComponent(urlLang) + ";path=/;max-age=31536000";
    }
    const cur = localStorage.getItem("amp_ui_lang") || "bn";
    sel.innerHTML = LANGS.map((l) => `<option value="${l.code}">${l.name}</option>`).join("");
    sel.value = cur;
    sel.onchange = () => {
      localStorage.setItem("amp_ui_lang", sel.value);
      document.cookie = "amp_ui_lang=" + encodeURIComponent(sel.value) + ";path=/;max-age=31536000";
      const u = new URL(window.location.href);
      u.searchParams.set("lang", sel.value);
      window.location.href = u.toString();
    };
  }

  window.ampSiteT = t;
  window.ampSiteApplyI18n = apply;
  document.addEventListener("DOMContentLoaded", () => {
    mountSelect();
    apply();
  });
})();
