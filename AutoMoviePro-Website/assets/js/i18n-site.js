(function () {
  const PACKS = {
    en: {
      how_it_works: "How it works",
      features: "What you get",
      purchase: "Buy",
      faq: "Common questions",
      name: "Your name",
      whatsapp: "WhatsApp number",
      email_opt: "Email (optional)",
      pay_now: "Confirm order",
      wait_title: "Please wait a moment",
      wait_lead: "We got your order. Payment will be checked by our team.",
      wait_order: "Order #{id} received. Our team will verify payment.",
      wa_send: "Send payment screenshot on WhatsApp",
      home: "Back to home",
      footer_note: "Windows desktop software.",
      how_lead: "Set it up once. After that, videos can make and upload on their own.",
      features_lead: "Plain benefits — what each part does for you.",
      site_tagline: "Pick a niche — videos create and upload automatically",
      buy_now: "Buy now",
      lifetime: "One-time purchase",
      price_base_note: "One-time buy — English + your chosen language",
      price_addon_note: "Want more languages? ৳{n} each",
      pick_personal_lang: "Which language with English?",
      en_included: "English is always included.",
      pick_addon_langs: "Add more languages?",
      total_due: "Total",
      or_whatsapp: "Chat on WhatsApp instead",
      see_features: "See what you get",
      chat_whatsapp: "WhatsApp",
      income_title: "Earn from many channels, not just one",
      income_lead: "One software can feed up to 6 YouTube, 6 Facebook and 6 TikTok places — so income can come from different markets while you don’t sit all day editing.",
      pitch_yt: "Up to 6 YouTube channels",
      pitch_fb: "Up to 6 Facebook pages/profiles",
      pitch_tt: "Up to 6 TikTok destinations",
      pitch_auto: "Schedule once — no all-day editing",
      step1: "Choose niche and connect your channels (login once)",
      step2: "Software makes short or long videos for you",
      step3: "Same video in other languages with matching voice & text",
      step4: "Auto send to YouTube / Facebook / TikTok on schedule",
      faq1_q: "How much does it cost?",
      faq1_a: "৳2998 for English + 1 language you choose. Each extra language is ৳499.",
      faq2_q: "How many channels can I add?",
      faq2_a: "Up to 6 YouTube + 6 Facebook + 6 TikTok destinations.",
      faq3_q: "How do I pay?",
      faq3_a: "Place the order, then send the payment screenshot on WhatsApp. We activate after checking.",
      agent_open: "Need help?",
      agent_title: "Sales helper",
      agent_placeholder: "Ask about price, languages, order…",
      agent_send: "Send",
      order_title: "Place your order",
      order_lead: "Choose languages, fill your details, then send payment proof on WhatsApp.",
      order_error: "Please enter your name and a valid WhatsApp number.",
      ui_language: "Language",
      payment_wait_title: "Waiting for payment",
    },
    bn: {
      how_it_works: "কীভাবে কাজ করে",
      features: "কী কী পাবেন",
      purchase: "কেনাকাটা",
      faq: "সাধারণ প্রশ্ন",
      name: "আপনার নাম",
      whatsapp: "WhatsApp নম্বর",
      email_opt: "ইমেইল (চাইলে)",
      pay_now: "অর্ডার কনফার্ম করুন",
      wait_title: "একটু অপেক্ষা করুন",
      wait_lead: "অর্ডার পেয়েছি। পেমেন্ট আমাদের টিম চেক করবে।",
      wait_order: "অর্ডার #{id} পেয়েছি। পেমেন্ট যাচাই করে অ্যাক্টিভ করা হবে।",
      wa_send: "WhatsApp-এ পেমেন্টের স্ক্রিনশট পাঠান",
      home: "হোমে ফিরুন",
      footer_note: "Windows কম্পিউটারের সফটওয়্যার।",
      how_lead: "একবার সেটআপ করলেই হয়। এরপর ভিডিও নিজেই বানাতে ও আপলোড করতে পারে।",
      features_lead: "সহজ ভাষায় — প্রতিটা সুবিধা আপনার জন্য কী করে।",
      site_tagline: "নিশ বেছে নিন — ভিডিও বানানো থেকে আপলোড, সব অটো",
      buy_now: "এখনই কিনুন",
      lifetime: "একবার কিনলেই চলবে",
      price_base_note: "একবার কিনলেই — ইংরেজি + আপনার পছন্দের ১টা ভাষা",
      price_addon_note: "আরও ভাষা চাইলে প্রতিটায় ৳{n}",
      pick_personal_lang: "ইংরেজির সাথে কোন ভাষা রাখবেন?",
      en_included: "ইংরেজি সব প্যাকেজেই থাকে।",
      pick_addon_langs: "আরও ভাষা খুলবেন?",
      total_due: "মোট টাকা",
      or_whatsapp: "সরাসরি WhatsApp-এ কথা বলুন",
      see_features: "কী কী পাবেন",
      chat_whatsapp: "WhatsApp",
      income_title: "এক জায়গা নয় — অনেক চ্যানেল থেকে ইনকাম",
      income_lead: "এক সফটওয়্যারেই সর্বোচ্চ ৬টা YouTube, ৬টা Facebook আর ৬টা TikTok চালাতে পারেন। সারাদিন এডিট না করেও আলাদা আলাদা বাজার থেকে আয়ের সুযোগ।",
      pitch_yt: "সর্বোচ্চ ৬টা YouTube চ্যানেল",
      pitch_fb: "সর্বোচ্চ ৬টা Facebook পেজ/প্রোফাইল",
      pitch_tt: "সর্বোচ্চ ৬টা TikTok অ্যাকাউন্ট",
      pitch_auto: "সময় ঠিক করে দিন — সারাদিন PC-তে বসতে হবে না",
      step1: "নিশ বেছে চ্যানেল কানেক্ট করুন (একবার লগইন)",
      step2: "সফটওয়্যার শর্ট বা লং ভিডিও বানিয়ে দেয়",
      step3: "একই ভিডিও অন্য ভাষায় — মিল রেখে ভয়েস ও লেখা",
      step4: "ঠিক করা সময়ে YouTube / Facebook / TikTok-এ চলে যায়",
      faq1_q: "দাম কত?",
      faq1_a: "৳২৯৯৮-এ ইংরেজি + আপনার পছন্দের ১টা ভাষা। তারপর প্রতিটা অতিরিক্ত ভাষা ৳৪৯৯।",
      faq2_q: "কয়টা চ্যানেল যোগ করা যায়?",
      faq2_a: "সর্বোচ্চ ৬টা YouTube + ৬টা Facebook + ৬টা TikTok।",
      faq3_q: "পেমেন্ট কীভাবে করব?",
      faq3_a: "আগে অর্ডার করুন, তারপর WhatsApp-এ পেমেন্টের স্ক্রিনশট পাঠান। চেক করে আমরা অ্যাক্টিভ করে দিই।",
      agent_open: "সাহায্য চাই",
      agent_title: "সেলস হেল্পার",
      agent_placeholder: "দাম, ভাষা বা অর্ডার নিয়ে জিজ্ঞাসা করুন…",
      agent_send: "পাঠান",
      order_title: "অর্ডার করুন",
      order_lead: "ভাষা বেছে তথ্য দিন — পরে WhatsApp-এ পেমেন্টের প্রমাণ পাঠাবেন।",
      order_error: "নাম ও সঠিক WhatsApp নম্বর দিন।",
      ui_language: "ভাষা",
      payment_wait_title: "পেমেন্ট অপেক্ষা",
    },
    hi: {
      how_it_works: "कैसे काम करता है",
      features: "आपको क्या मिलेगा",
      purchase: "खरीदें",
      faq: "आम सवाल",
      name: "आपका नाम",
      whatsapp: "WhatsApp नंबर",
      email_opt: "ईमेल (ज़रूरी नहीं)",
      pay_now: "ऑर्डर कन्फ़र्म करें",
      wait_title: "थोड़ा इंतज़ार करें",
      wait_lead: "ऑर्डर मिल गया। पेमेंट हमारी टीम चेक करेगी।",
      wait_order: "ऑर्डर #{id} मिल गया। पेमेंट चेक के बाद एक्टिव होगा।",
      wa_send: "WhatsApp पर पेमेंट स्क्रीनशॉट भेजें",
      home: "होम पर जाएँ",
      footer_note: "Windows कंप्यूटर का सॉफ़्टवेयर।",
      how_lead: "एक बार सेटअप करें। उसके बाद वीडियो खुद बन और अपलोड हो सकते हैं।",
      features_lead: "आसान भाषा में — हर सुविधा आपके काम की कैसे है।",
      site_tagline: "निश चुनें — वीडियो बनाना से अपलोड तक ऑटो",
      buy_now: "अभी खरीदें",
      lifetime: "एक बार खरीद काफी",
      price_base_note: "एक बार खरीद — अंग्रेज़ी + आपकी चुनी 1 भाषा",
      price_addon_note: "और भाषा चाहिए? हर एक ৳{n}",
      pick_personal_lang: "अंग्रेज़ी के साथ कौन सी भाषा रखेंगे?",
      en_included: "अंग्रेज़ी हर पैकेज में रहती है।",
      pick_addon_langs: "और भाषाएँ खोलेंगे?",
      total_due: "कुल राशि",
      or_whatsapp: "सीधे WhatsApp पर बात करें",
      see_features: "क्या-क्या मिलेगा",
      chat_whatsapp: "WhatsApp",
      income_title: "एक नहीं — कई चैनलों से कमाई",
      income_lead: "एक सॉफ़्टवेयर से अधिकतम 6 YouTube, 6 Facebook और 6 TikTok चला सकते हैं। दिन भर एडिट किए बिना अलग-अलग बाज़ार से कमाई का मौका।",
      pitch_yt: "अधिकतम 6 YouTube चैनल",
      pitch_fb: "अधिकतम 6 Facebook पेज/प्रोफ़ाइल",
      pitch_tt: "अधिकतम 6 TikTok अकाउंट",
      pitch_auto: "समय सेट करें — दिन भर PC के सामने बैठना ज़रूरी नहीं",
      step1: "निश चुनकर चैनल जोड़ें (एक बार लॉगिन)",
      step2: "सॉफ़्टवेयर शॉर्ट या लॉन्ग वीडियो बना देता है",
      step3: "वही वीडियो दूसरी भाषा में — आवाज़ और टेक्स्ट मिलाकर",
      step4: "तय समय पर YouTube / Facebook / TikTok पर चला जाता है",
      faq1_q: "कीमत क्या है?",
      faq1_a: "৳2998 में अंग्रेज़ी + आपकी 1 भाषा। हर अतिरिक्त भाषा ৳499।",
      faq2_q: "कितने चैनल जोड़ सकते हैं?",
      faq2_a: "अधिकतम 6 YouTube + 6 Facebook + 6 TikTok।",
      faq3_q: "पेमेंट कैसे करें?",
      faq3_a: "पहले ऑर्डर करें, फिर WhatsApp पर पेमेंट स्क्रीनशॉट भेजें। चेक करके हम एक्टिव कर देते हैं।",
      agent_open: "मदद चाहिए?",
      agent_title: "सेल्स हेल्पर",
      agent_placeholder: "कीमत, भाषा या ऑर्डर पूछें…",
      agent_send: "भेजें",
      order_title: "ऑर्डर करें",
      order_lead: "भाषा चुनें, डिटेल भरें — फिर WhatsApp पर पेमेंट प्रूफ़ भेजें।",
      order_error: "नाम और सही WhatsApp नंबर डालें।",
      ui_language: "भाषा",
      payment_wait_title: "पेमेंट इंतज़ार",
    },
    ur: {
      how_it_works: "کیسے کام کرتا ہے",
      features: "آپ کو کیا ملے گا",
      purchase: "خریدیں",
      faq: "عام سوالات",
      name: "آپ کا نام",
      whatsapp: "WhatsApp نمبر",
      email_opt: "ای میل (اختیاری)",
      pay_now: "آرڈر تصدیق کریں",
      wait_title: "ذرا انتظار کریں",
      wait_lead: "آرڈر مل گیا۔ ادائیگی ہماری ٹیم چیک کرے گی۔",
      wait_order: "آرڈر #{id} مل گیا۔ ادائیگی چیک کے بعد ایکٹیو ہوگا۔",
      wa_send: "WhatsApp پر ادائیگی کا اسکرین شاٹ بھیجیں",
      home: "ہوم پر جائیں",
      footer_note: "Windows کمپیوٹر سافٹ ویئر۔",
      how_lead: "ایک بار سیٹ اپ کریں۔ پھر ویڈیو خود بن اور اپلوڈ ہو سکتی ہیں۔",
      features_lead: "آسان زبان میں — ہر فائدہ آپ کے لیے کیا کرتی ہے۔",
      site_tagline: "نچ منتخب کریں — ویڈیو بنانے سے اپلوڈ تک آٹو",
      buy_now: "ابھی خریدیں",
      lifetime: "ایک بار خرید کافی",
      price_base_note: "ایک بار خرید — انگریزی + آپ کی منتخب 1 زبان",
      price_addon_note: "مزید زبانیں؟ ہر ایک ৳{n}",
      pick_personal_lang: "انگریزی کے ساتھ کون سی زبان رکھیں گے؟",
      en_included: "انگریزی ہر پیکیج میں شامل ہے۔",
      pick_addon_langs: "مزید زبانیں کھولیں گے؟",
      total_due: "کل رقم",
      or_whatsapp: "براہ راست WhatsApp پر بات کریں",
      see_features: "کیا کیا ملے گا",
      chat_whatsapp: "WhatsApp",
      income_title: "ایک نہیں — کئی چینلز سے کمائی",
      income_lead: "ایک سافٹ ویئر سے زیادہ سے زیادہ 6 YouTube، 6 Facebook اور 6 TikTok چلا سکتے ہیں۔ دن بھر ایڈٹ کیے بغیر الگ الگ مارکیٹ سے آمدنی کا موقع۔",
      pitch_yt: "زیادہ سے زیادہ 6 YouTube چینل",
      pitch_fb: "زیادہ سے زیادہ 6 Facebook صفحات",
      pitch_tt: "زیادہ سے زیادہ 6 TikTok اکاؤنٹ",
      pitch_auto: "وقت سیٹ کریں — دن بھر PC کے سامنے بیٹھنا ضروری نہیں",
      step1: "نچ چن کر چینل جوڑیں (ایک بار لاگ اِن)",
      step2: "سافٹ ویئر شارٹ یا لانگ ویڈیو بنا دیتا ہے",
      step3: "وہی ویڈیو دوسری زبان میں — آواز اور ٹیکسٹ کے ساتھ",
      step4: "مقررہ وقت پر YouTube / Facebook / TikTok پر چلا جاتا ہے",
      faq1_q: "قیمت کیا ہے؟",
      faq1_a: "৳2998 میں انگریزی + آپ کی 1 زبان۔ ہر اضافی زبان ৳499۔",
      faq2_q: "کتنے چینل جوڑ سکتے ہیں؟",
      faq2_a: "زیادہ سے زیادہ 6 YouTube + 6 Facebook + 6 TikTok۔",
      faq3_q: "ادائیگی کیسے کریں؟",
      faq3_a: "پہلے آرڈر کریں، پھر WhatsApp پر ادائیگی کا اسکرین شاٹ بھیجیں۔ چیک کر کے ہم ایکٹیو کر دیتے ہیں۔",
      agent_open: "مدد چاہیے؟",
      agent_title: "سیلز ہیلپر",
      agent_placeholder: "قیمت، زبان یا آرڈر پوچھیں…",
      agent_send: "بھیجیں",
      order_title: "آرڈر کریں",
      order_lead: "زبان منتخب کریں، تفصیل بھریں — پھر WhatsApp پر ادائیگی کا ثبوت بھیجیں۔",
      order_error: "نام اور درست WhatsApp نمبر دیں۔",
      ui_language: "زبان",
      payment_wait_title: "ادائیگی انتظار",
    },
    ta: {
      how_it_works: "எப்படி வேலை செய்கிறது",
      features: "உங்களுக்கு என்ன கிடைக்கும்",
      purchase: "வாங்க",
      faq: "பொதுவான கேள்விகள்",
      name: "உங்கள் பெயர்",
      whatsapp: "WhatsApp எண்",
      email_opt: "மின்னஞ்சல் (விருப்பம்)",
      pay_now: "ஆர்டர் உறுதிப்படுத்து",
      wait_title: "சிறிது காத்திருங்கள்",
      wait_lead: "ஆர்டர் கிடைத்தது. பணம் எங்கள் குழு சரிபார்க்கும்.",
      wait_order: "ஆர்டர் #{id} கிடைத்தது. பணம் சரிபார்த்து ஆக்டிவ் செய்வோம்.",
      wa_send: "WhatsApp-இல் பண ஸ்கிரீன்ஷாட் அனுப்புங்கள்",
      home: "முகப்புக்கு",
      footer_note: "Windows கணினி மென்பொருள்.",
      how_lead: "ஒருமுறை அமைத்தால் போதும். பிறகு வீடியோ தானே உருவாகி பதிவேறலாம்.",
      features_lead: "எளிய மொழியில் — ஒவ்வொரு வசதியும் உங்களுக்கு என்ன செய்கிறது.",
      site_tagline: "நிஷ் தேர்வு — வீடியோ உருவாக்கம் முதல் அப்லோட் வரை ஆட்டோ",
      buy_now: "இப்போது வாங்க",
      lifetime: "ஒருமுறை வாங்கினால் போதும்",
      price_base_note: "ஒருமுறை வாங்கல் — ஆங்கிலம் + நீங்கள் தேர்ந்த 1 மொழி",
      price_addon_note: "மேலும் மொழி வேண்டுமா? ஒன்றுக்கு ৳{n}",
      pick_personal_lang: "ஆங்கிலத்துடன் எந்த மொழி வைப்பீர்கள்?",
      en_included: "ஆங்கிலம் எல்லா பேக்கேஜிலும் உண்டு.",
      pick_addon_langs: "மேலும் மொழிகளைத் திறப்பீர்களா?",
      total_due: "மொத்தம்",
      or_whatsapp: "நேரடியாக WhatsApp-இல் பேசுங்கள்",
      see_features: "என்னென்ன கிடைக்கும்",
      chat_whatsapp: "WhatsApp",
      income_title: "ஒன்று அல்ல — பல சேனல்களில் வருமானம்",
      income_lead: "ஒரு மென்பொருளில் அதிகபட்சம் 6 YouTube, 6 Facebook, 6 TikTok இயக்கலாம். நாள் முழுவதும் எடிட் செய்யாமல் வெவ்வேறு சந்தைகளில் வருமான வாய்ப்பு.",
      pitch_yt: "அதிகபட்சம் 6 YouTube சேனல்கள்",
      pitch_fb: "அதிகபட்சம் 6 Facebook பக்கங்கள்",
      pitch_tt: "அதிகபட்சம் 6 TikTok கணக்குகள்",
      pitch_auto: "நேரம் அமைக்கவும் — நாள் முழு PC முன் உட்கார வேண்டாம்",
      step1: "நிஷ் தேர்ந்து சேனல் இணைக்கவும் (ஒருமுறை உள்நுழைவு)",
      step2: "மென்பொருள் ஷார்ட் அல்லது லாங் வீடியோ உருவாக்கும்",
      step3: "அதே வீடியோ மற்ற மொழியில் — குரல் + உரை உடன்",
      step4: "திட்டமிட்ட நேரத்தில் YouTube / Facebook / TikTok-க்கு செல்லும்",
      faq1_q: "விலை என்ன?",
      faq1_a: "৳2998-இல் ஆங்கிலம் + உங்கள் 1 மொழி. ஒவ்வொரு கூடுதல் மொழி ৳499.",
      faq2_q: "எத்தனை சேனல் சேர்க்கலாம்?",
      faq2_a: "அதிகபட்சம் 6 YouTube + 6 Facebook + 6 TikTok.",
      faq3_q: "பணம் எப்படி செலுத்துவது?",
      faq3_a: "முதலில் ஆர்டர் செய்யுங்கள், பிறகு WhatsApp-இல் பண ஸ்கிரீன்ஷாட் அனுப்புங்கள். சரிபார்த்து ஆக்டிவ் செய்கிறோம்.",
      agent_open: "உதவி வேண்டுமா?",
      agent_title: "விற்பனை உதவியாளர்",
      agent_placeholder: "விலை, மொழி அல்லது ஆர்டர் கேளுங்கள்…",
      agent_send: "அனுப்பு",
      order_title: "ஆர்டர் செய்யுங்கள்",
      order_lead: "மொழி தேர்வு செய்து விவரம் நிரப்புங்கள் — பிறகு WhatsApp-இல் பண ஆதாரம் அனுப்புங்கள்.",
      order_error: "பெயர் மற்றும் சரியான WhatsApp எண் கொடுங்கள்.",
      ui_language: "மொழி",
      payment_wait_title: "பணம் காத்திருப்பு",
    },
    ml: {
      how_it_works: "എങ്ങനെ പ്രവർത്തിക്കുന്നു",
      features: "നിങ്ങൾക്ക് എന്ത് ലഭിക്കും",
      purchase: "വാങ്ങുക",
      faq: "പൊതുവായ ചോദ്യങ്ങൾ",
      name: "നിങ്ങളുടെ പേര്",
      whatsapp: "WhatsApp നമ്പർ",
      email_opt: "ഇമെയിൽ (ഐച്ഛികം)",
      pay_now: "ഓർഡർ സ്ഥിരീകരിക്കുക",
      wait_title: "കുറച്ച് കാത്തിരിക്കുക",
      wait_lead: "ഓർഡർ ലഭിച്ചു. പേയ്‌മെന്റ് ഞങ്ങളുടെ ടീം പരിശോധിക്കും.",
      wait_order: "ഓർഡർ #{id} ലഭിച്ചു. പേയ്‌മെന്റ് പരിശോധിച്ച് ആക്ടീവ് ചെയ്യും.",
      wa_send: "WhatsApp-ൽ പേയ്‌മെന്റ് സ്ക്രീൻഷോട്ട് അയയ്ക്കുക",
      home: "ഹോമിലേക്ക്",
      footer_note: "Windows കമ്പ്യൂട്ടർ സോഫ്റ്റ്‌വെയർ.",
      how_lead: "ഒരിക്കൽ സെറ്റപ്പ് മതി. അതിനുശേഷം വീഡിയോ സ്വയം ഉണ്ടാകുകയും അപ്‌ലോഡ് ചെയ്യുകയും ചെയ്യാം.",
      features_lead: "ലളിതമായ ഭാഷയിൽ — ഓരോ സൗകര്യവും നിങ്ങൾക്ക് എന്ത് ചെയ്യുന്നു.",
      site_tagline: "നിച്ച് തിരഞ്ഞെടുക്കുക — വീഡിയോ മുതൽ അപ്‌ലോഡ് വരെ ഓട്ടോ",
      buy_now: "ഇപ്പോൾ വാങ്ങുക",
      lifetime: "ഒരിക്കൽ വാങ്ങിയാൽ മതി",
      price_base_note: "ഒരിക്കൽ വാങ്ങൽ — ഇംഗ്ലീഷ് + നിങ്ങൾ തിരഞ്ഞ 1 ഭാഷ",
      price_addon_note: "കൂടുതൽ ഭാഷ വേണോ? ഓരോന്നിനും ৳{n}",
      pick_personal_lang: "ഇംഗ്ലീഷിനൊപ്പം ഏത് ഭാഷ വയ്ക്കും?",
      en_included: "ഇംഗ്ലീഷ് എല്ലാ പാക്കേജിലും ഉണ്ട്.",
      pick_addon_langs: "കൂടുതൽ ഭാഷകൾ തുറക്കുമോ?",
      total_due: "ആകെ തുക",
      or_whatsapp: "നേരിട്ട് WhatsApp-ൽ സംസാരിക്കുക",
      see_features: "എന്തൊക്കെ ലഭിക്കും",
      chat_whatsapp: "WhatsApp",
      income_title: "ഒന്നല്ല — പല ചാനലുകളിൽ നിന്ന് വരുമാനം",
      income_lead: "ഒരു സോഫ്റ്റ്‌വെയറിൽ പരമാവധി 6 YouTube, 6 Facebook, 6 TikTok ഓടിക്കാം. ദിവസം മുഴുവൻ എഡിറ്റ് ചെയ്യാതെ വ്യത്യസ്ത മാർക്കറ്റുകളിൽ നിന്ന് വരുമാന അവസരം.",
      pitch_yt: "പരമാവധി 6 YouTube ചാനലുകൾ",
      pitch_fb: "പരമാവധി 6 Facebook പേജുകൾ",
      pitch_tt: "പരമാവധി 6 TikTok അക്കൗണ്ടുകൾ",
      pitch_auto: "സമയം സെറ്റ് ചെയ്യുക — ദിവസം മുഴുവൻ PC മുന്നിൽ ഇരിക്കേണ്ട",
      step1: "നിച്ച് തിരഞ്ഞ് ചാനൽ കണക്റ്റ് ചെയ്യുക (ഒരിക്കൽ ലോഗിൻ)",
      step2: "സോഫ്റ്റ്‌വെയർ ഷോർട്ട് അല്ലെങ്കിൽ ലോംഗ് വീഡിയോ ഉണ്ടാക്കും",
      step3: "അതേ വീഡിയോ മറ്റ് ഭാഷയിൽ — വോയ്‌സും ടെക്സ്റ്റും ഒപ്പം",
      step4: "നിശ്ചിത സമയത്ത് YouTube / Facebook / TikTok-ലേക്ക് പോകും",
      faq1_q: "വില എത്ര?",
      faq1_a: "৳2998-ൽ ഇംഗ്ലീഷ് + നിങ്ങളുടെ 1 ഭാഷ. ഓരോ അധിക ഭാഷ ৳499.",
      faq2_q: "എത്ര ചാനൽ ചേർക്കാം?",
      faq2_a: "പരമാവധി 6 YouTube + 6 Facebook + 6 TikTok.",
      faq3_q: "പേയ്‌മെന്റ് എങ്ങനെ?",
      faq3_a: "ആദ്യം ഓർഡർ ചെയ്യുക, പിന്നെ WhatsApp-ൽ പേയ്‌മെന്റ് സ്ക്രീൻഷോട്ട് അയയ്ക്കുക. പരിശോധിച്ച് ഞങ്ങൾ ആക്ടീവ് ചെയ്യും.",
      agent_open: "സഹായം വേണോ?",
      agent_title: "സെയിൽസ് ഹെൽപ്പർ",
      agent_placeholder: "വില, ഭാഷ അല്ലെങ്കിൽ ഓർഡർ ചോദിക്കൂ…",
      agent_send: "അയയ്ക്കുക",
      order_title: "ഓർഡർ ചെയ്യുക",
      order_lead: "ഭാഷ തിരഞ്ഞ് വിവരം നൽകുക — പിന്നെ WhatsApp-ൽ പേയ്‌മെന്റ് തെളിവ് അയയ്ക്കുക.",
      order_error: "പേരും ശരിയായ WhatsApp നമ്പറും നൽകുക.",
      ui_language: "ഭാഷ",
      payment_wait_title: "പേയ്‌മെന്റ് കാത്തിരിപ്പ്",
    },
  };

  const LANGS = [
    { code: "en", name: "English" },
    { code: "bn", name: "বাংলা" },
    { code: "hi", name: "हिन्दी" },
    { code: "ur", name: "اردو" },
    { code: "ta", name: "தமிழ்" },
    { code: "ml", name: "മലയാളം" },
  ];

  function t(key, vars) {
    const lang = localStorage.getItem("amp_ui_lang") || "bn";
    const pack = PACKS[lang] || PACKS.bn;
    let s = pack[key] || PACKS.en[key] || key;
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
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
    });
    // Keep order CTAs pointing at current language
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
