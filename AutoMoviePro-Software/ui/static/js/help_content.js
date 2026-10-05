/**
 * Field / section help (i-button). Uses amp_ui_lang; falls back to en.
 */
(function () {
  const EN = {
    yt_name:
      "YouTube channel display name used in titles and branding.\nExample: Tech Gadget Daily\nWhat happens: Shown on uploads and in logs. Does not log you into YouTube by itself — use the YouTube Login button after save.",
    fb_name:
      "Facebook Page name for scheduled posts.\nExample: Gadget Review BD\nWhat happens: Used when publishing to Facebook. Use Facebook Login after save to connect the session.",
    niche:
      "Pick ONE niche for this install (locked after first save).\nExample: #12 Wireless Earbuds\nWhat happens: The director plans topics/scenes only inside this niche. Wrong niche = wrong product videos.",
    niche_search: "Type to filter the niche list by name or number.",
    second_lang:
      "Second video language besides English (setup allows English + 1).\nExample: Bangla\nWhat happens: Localized narration/subtitles are generated for this language. More languages can be purchased later.",
    video_special:
      "Extra creative rules for every video.\nExample: Always mention warranty + avoid medical claims\nWhat happens: Injected into the director prompt so style/constraints stick.",
    long_upload:
      "Daily time to upload Long videos (local clock).\nExample: 18:00\nWhat happens: Scheduler targets this time for long-form publishes.",
    short_upload:
      "Daily time to upload Shorts.\nExample: 12:00\nWhat happens: Scheduler targets this time for short publishes.",
    example_script:
      "Optional sample script/tone the AI should imitate.\nExample: Energetic host, short sentences, end with CTA\nWhat happens: Used as a style reference during generation.",
    gen_special:
      "Technical generation preferences.\nExample: Prefer product close-ups; max 8 scenes\nWhat happens: Guides scene count/visual bias in the pipeline.",
    title_special:
      "Rules for YouTube title & description.\nExample: Title under 70 chars; include niche keyword once\nWhat happens: Applied when writing SEO title/description/tags.",
    logo:
      "PNG/JPG logo overlaid on the final video (optional).\nWhat happens: Composited during ffmpeg compose. Transparent PNG works best.",
    intro:
      "Short intro clip prepended before scenes (optional).\nWhat happens: Normalized and concatenated at the start of the video.",
    api_connection:
      "Connect dedicated API keys per job (Agent Grok, Topic Grok, Image Google, Localization, TTS per unlocked language).\nRequired slots must be filled or the app stays Inactive.\nOptional slots (Image, Agnes, Pollinations, Workers AI): leave empty to skip / use free URL.\nWorkers AI: if you paste an API token, Account ID is mandatory for that row.\nThe same API key cannot be used in two different slots.\nClick the (i) button beside each slot for signup + key-creation steps with links.",
    api_pick: "Choose one provider at a time to fill its key slots.",
    buy_lang:
      "Buy extra localization languages (max 6 total including English).\nSelect languages → pay → enter payment reference → submit → admin approves → Sync Approval.",
    payment_ref:
      "Your payment transaction ID / bKash TrxID / bank ref.\nExample: TXN983746\nWhat happens: Admin verifies this before unlocking languages.",
    note: "Optional note for admin (amount paid, sender number, etc.).",
    gen_short:
      "Generate a Short video now for the saved channel (background job). Watch Live Activity for progress.",
    gen_long: "Generate a Long video now. Same flow as Short but longer duration budget.",
    live_title:
      "Live job status: phase, scene, API calls, events. Use Stop if a process hangs.",
    stop_process: "Requests cancel of the current background generate job.",
    tab_home: "Overview: app active status, generate buttons, channel summary.",
    tab_live: "Watch running generation / API / errors in real time.",
    tab_channel: "One-time niche/language setup + channel settings + API keys.",
    tab_jobs: "Recent generate/upload job history.",
    tab_settings: "Logout and maintenance tools.",
    help_api_google:
      "Google AI Studio key — scripts, planning, TTS, agent vision.\n1) Click Get API\n2) Sign in with Google\n3) Create API key\n4) Paste into Google API 1 and 2 (min 2 required)\nNever share the key publicly.",
    help_api_agent_grok:
      "Agent Grok API (1 key required).\n1) Open xAI Console (or OpenRouter → create key with Grok model access)\n2) Create API key\n3) Paste into Agent API 1\nUsed for in-app agent / troubleshooting actions.",
    help_api_topic_grok:
      "Topic generation Grok (2 keys required for fallback).\n1) https://console.x.ai/ → API keys (or OpenRouter keys with x-ai/grok)\n2) Create two keys\n3) Paste Topic API 1 and API 2\nDrives topic + visual planning stages.",
    help_api_image_google:
      "Image generation — Google AI Studio (optional, recommended).\nSlots: API 1 + API 2 (fallback).\n1) https://aistudio.google.com/apikey\n2) Create API key(s)\n3) Paste here ONLY — these keys are NOT shared with localization/TTS.\nIf empty: Google image is skipped and you get a notification (Pollinations/Agnes/Workers AI may still run).",
    help_api_localize_google:
      "Localization — Google AI Studio (2 keys required).\n1) https://aistudio.google.com/apikey\n2) Create two keys\n3) Paste Localization API 1 and API 2\nDedicated to script translation — keep separate from image/TTS keys.",
    help_api_tts_google_bn:
      "Bangla TTS — Google AI Studio (2 keys required when Bangla is unlocked).\n1) https://aistudio.google.com/apikey\n2) Create two keys\n3) Paste TTS Bangla API 1 / API 2\nEnglish/Hindi/Urdu use free Edge TTS — no Google key needed.",
    help_api_tts_google_ta:
      "Tamil TTS — Google AI Studio (2 keys when Tamil unlocked).\nSame steps as Bangla: aistudio.google.com/apikey → create → paste API 1 & 2.",
    help_api_tts_google_ml:
      "Malayalam TTS — Google AI Studio (2 keys when Malayalam unlocked).\nSame steps: aistudio.google.com/apikey → create → paste API 1 & 2.",
    help_api_groq:
      "Groq — fast free text LLM for agent/script fallback.\nGet API → Create key → paste slots 1–2.",
    help_api_openrouter:
      "OpenRouter — multi-model text fallback (also accepted as Grok transport).\nopenrouter.ai/keys → Create Key → paste.",
    help_api_pollinations:
      "Pollinations — AI image (optional).\nNo key required: free URL works.\nOptional key from auth.pollinations.ai raises limits.",
    help_api_workers_ai:
      "Cloudflare Workers AI — Pollinations fallback (optional).\n1) https://dash.cloudflare.com → Workers AI\n2) Copy Account ID into the Account ID field (mandatory if you paste an API token)\n3) Create API Token (Workers AI Edit)\n4) Paste token as Workers AI API 1 / 2\nEach API row needs its matching Account ID. Same API key cannot be reused in other slots.",
    help_api_pexels:
      "Pexels — free stock video/images (optional).\npexels.com/api → Get Started → copy key → paste.",
    help_api_agnes:
      "Agnes — AI video/image (optional).\nNo key: free URL path is tried.\nPaid key from Agnes developer portal raises quality/limits.",
    help_api_huggingface:
      "Optional Hugging Face token for extra LLM fallback.\nSettings → Access Tokens → New token (Read).",
    help_api_cerebras:
      "Optional Cerebras cloud key for fast LLM fallback.",
    help_api_freetheai:
      "Optional FreeTheAI key for extra chat fallback.",
    get_api: "Get API",
    help_label: "Help",
    screenshot: "Screenshot",
    attach_shot: "Attach screenshot",
    escalate_sent: "Escalated to admin — an app update may be needed.",
    portal_opened: "Opened API page in browser",
  };

  const BN = {
    yt_name:
      "YouTube চ্যানেলের নাম — টাইটেল/ব্র্যান্ডে ব্যবহার হয়।\nউদাহরণ: Tech Gadget Daily\nকী হয়: আপলোড ও লগে দেখায়। আলাদাভাবে YouTube লগইন বাটন দিয়ে সেশন কানেক্ট করতে হয়।",
    fb_name:
      "Facebook পেজের নাম।\nউদাহরণ: Gadget Review BD\nকী হয়: ফেসবুক পাবলিশে ব্যবহার। সেভের পর Facebook লগইন দিন।",
    niche:
      "এই ইনস্টলে একটিই নিশ (সেভের পর লক)।\nউদাহরণ: #12 Wireless Earbuds\nকী হয়: শুধু এই নিশের প্রোডাক্ট/টপিক দিয়ে ভিডিও প্ল্যান হয়।",
    niche_search: "নাম বা নম্বর দিয়ে নিশ খুঁজুন।",
    second_lang:
      "ইংরেজির পাশাপাশি দ্বিতীয় ভাষা (সেটআপে ২টি)।\nউদাহরণ: বাংলা\nকী হয়: এই ভাষায় লোকালাইজড ন্যারেশন/সাবটাইটেল তৈরি হয়। পরে আরও ভাষা কেনা যায়।",
    video_special:
      "প্রতি ভিডিওর জন্য বাড়তি নিয়ম।\nউদাহরণ: ওয়ারেন্টি বলুন; মেডিকেল ক্লেইম এড়িয়ে চলুন\nকী হয়: ডিরেক্টর প্রম্পটে যোগ হয়।",
    long_upload: "লং ভিডিও আপলোডের সময় (লোকাল ঘড়ি)।\nউদাহরণ: 18:00",
    short_upload: "শর্ট আপলোডের সময়।\nউদাহরণ: 12:00",
    example_script:
      "AI যে টোন অনুসরণ করবে তার নমুনা।\nউদাহরণ: ছোট বাক্য, এনার্জেটিক, শেষে CTA",
    gen_special:
      "জেনারেশন টেকনিক্যাল পছন্দ।\nউদাহরণ: ক্লোজ-আপ বেশি; সর্বোচ্চ ৮ সিন",
    title_special:
      "টাইটেল/ডেসক্রিপশন নিয়ম।\nউদাহরণ: টাইটেল ৭০ অক্ষরের কম; নিশ কীওয়ার্ড একবার",
    logo: "ফাইনাল ভিডিওতে লোগো (ঐচ্ছিক)। ট্রান্সপারেন্ট PNG ভালো।",
    intro: "সিনের আগে ইন্ট্রো ক্লিপ (ঐচ্ছিক)।",
    api_connection:
      "প্রতিটি কাজের জন্য আলাদা API কী (Agent Grok, Topic Grok, Image Google, Localization, আনলক করা ভাষার TTS)।\nবাধ্যতামূলক স্লট খালি থাকলে অ্যাপ ইনঅ্যাকটিভ।\nঐচ্ছিক (Image/Agnes/Pollinations/Workers AI): খালি রাখলে স্কিপ বা ফ্রি URL।\nWorkers AI-তে API দিলে Account ID বাধ্যতামূলক। একই API কী দুই স্লটে দেওয়া যাবে না।\nপাশের (i) বাটনে ক্লিক করলে অ্যাকাউন্ট+কী তৈরির পুরো ধাপ ও লিংক দেখাবে।",
    api_pick: "একসাথে একটি প্রোভাইডার সিলেক্ট করে তার কী ভরুন।",
    buy_lang:
      "অতিরিক্ত ভাষা কিনুন (মোট সর্বোচ্চ ৬)। সিলেক্ট → পেমেন্ট → রেফারেন্স → আবেদন → অ্যাডমিন অ্যাপ্রুভ → Sync।",
    payment_ref: "পেমেন্ট ট্রানজেকশন আইডি / bKash TrxID।\nউদাহরণ: TXN983746",
    note: "অ্যাডমিনের জন্য নোট (ঐচ্ছিক)।",
    gen_short: "এখনই Short জেনারেট (ব্যাকগ্রাউন্ড)। লাইভ ট্যাবে অগ্রগতি দেখুন।",
    gen_long: "এখনই Long জেনারেট।",
    live_title: "চলমান জবের ফেইজ/সিন/API/ইভেন্ট। আটকে গেলে Stop চাপুন।",
    stop_process: "চলমান জেনারেশন বন্ধের অনুরোধ।",
    tab_home: "অ্যাপ স্ট্যাটাস, জেনারেট বাটন, চ্যানেল সামারি।",
    tab_live: "রিয়েল-টাইম জেনারেশন/API স্ট্যাটাস।",
    tab_channel: "নিশ/ভাষা সেটআপ, চ্যানেল সেটিং, API কী।",
    tab_jobs: "সাম্প্রতিক জব হিস্টরি।",
    tab_settings: "লগআউট ও মেইনটেনেন্স।",
    help_api_google:
      "Google AI Studio কী — স্ক্রিপ্ট, প্ল্যান, TTS, স্ক্রিনশট বিশ্লেষণ।\n১) Get API\n২) Google দিয়ে লগইন\n৩) Create API key\n৪) Google API ১ ও ২-এ পেস্ট (কমপক্ষে ২টি)\nকী পাবলিক করবেন না।",
    help_api_agent_grok:
      "Agent Grok API (১টি বাধ্যতামূলক)।\n১) xAI Console বা OpenRouter → Grok অ্যাক্সেসসহ কী\n২) Create API key\n৩) Agent API ১-এ পেস্ট\nঅ্যাপ এজেন্ট/ট্রাবলশুটিংয়ের জন্য।",
    help_api_topic_grok:
      "টপিক জেনারেশন Grok (ফলব্যাকসহ ২টি বাধ্যতামূলক)।\n১) https://console.x.ai/ বা OpenRouter\n২) দুটি কী তৈরি\n৩) Topic API ১ ও ২-এ পেস্ট\nটপিক + ভিজুয়াল প্ল্যানিং চালায়।",
    help_api_image_google:
      "ইমেজ জেনারেশন — Google AI Studio (ঐচ্ছিক, সুপারিশকৃত)।\nস্লট: API ১ + API ২ (ফলব্যাক)।\n১) https://aistudio.google.com/apikey\n২) কী তৈরি\n৩) শুধু এখানে পেস্ট — লোকালাইজ/TTS এর সাথে শেয়ার নয়।\nখালি থাকলে Google ইমেজ স্কিপ + নোটিফিকেশন (Pollinations/Agnes/Workers AI চলতে পারে)।",
    help_api_localize_google:
      "লোকালাইজেশন — Google AI Studio (২টি বাধ্যতামূলক)।\n১) https://aistudio.google.com/apikey\n২) দুটি কী\n৩) Localization API ১ ও ২\nস্ক্রিপ্ট অনুবাদের জন্য আলাদা রাখুন।",
    help_api_tts_google_bn:
      "বাংলা TTS — Google (বাংলা আনলক থাকলে ২টি বাধ্যতামূলক)।\n১) aistudio.google.com/apikey\n২) দুটি কী → TTS Bangla API ১/২\nen/hi/ur = ফ্রি Edge TTS — Google কী লাগে না।",
    help_api_tts_google_ta:
      "তামিল TTS — Google (তামিল আনলক হলে ২টি)।\nএকই ধাপ: aistudio → কী → API ১ ও ২।",
    help_api_tts_google_ml:
      "মালায়ালাম TTS — Google (মালায়ালাম আনলক হলে ২টি)।\nএকই ধাপ: aistudio → কী → API ১ ও ২।",
    help_api_groq: "Groq — দ্রুত টেক্সট LLM। Get API → Create key → স্লট ১–২।",
    help_api_openrouter: "OpenRouter — মাল্টি-মডেল ফলব্যাক (Grok ট্রান্সপোর্ট হিসেবেও চলে)। Keys → Create Key → পেস্ট।",
    help_api_pollinations: "Pollinations — AI ছবি (ঐচ্ছিক)। কী ছাড়াই ফ্রি URL কাজ করে। অপশনাল কী: auth.pollinations.ai",
    help_api_workers_ai:
      "Cloudflare Workers AI — Pollinations ফলব্যাক (ঐচ্ছিক)।\n১) dash.cloudflare.com → Workers AI\n২) Account ID কপি করে UI-এর Account ID ফিল্ডে দিন (API দিলে বাধ্যতামূলক)\n৩) API Token (Workers AI Edit)\n৪) Workers AI API ১/২-এ পেস্ট\nপ্রতিটি API সারির সাথে মিলিয়ে Account ID লাগবে। একই API কী অন্য স্লটে আবার ব্যবহার করা যাবে না।",
    help_api_pexels: "Pexels — ফ্রি স্টক (ঐচ্ছিক)। API → Get Started → কী।",
    help_api_agnes: "Agnes — AI ভিডিও/ইমেজ (ঐচ্ছিক)। কী ছাড়া ফ্রি URL চেষ্টা হয়; পেইড কী দিলে কোয়ালিটি বাড়ে।",
    help_api_huggingface: "ঐচ্ছিক HF টোকেন — Settings → Access Tokens।",
    help_api_cerebras: "ঐচ্ছিক Cerebras ক্লাউড কী।",
    help_api_freetheai: "ঐচ্ছিক FreeTheAI কী।",
    get_api: "Get API",
    help_label: "সাহায্য",
    screenshot: "স্ক্রিনশট",
    attach_shot: "স্ক্রিনশট যোগ করুন",
    escalate_sent: "অ্যাডমিনের কাছে পাঠানো হয়েছে — অ্যাপ আপডেট লাগতে পারে।",
    portal_opened: "ব্রাউজারে API পেজ খোলা হয়েছে",
  };

  window.AMP_HELP = { en: EN, bn: BN, hi: EN, ur: EN, ta: EN, ml: EN };
  window.AMP_HELP.bn = BN;

  window.ampHelpT = function ampHelpT(key) {
    const lang = localStorage.getItem("amp_ui_lang") || "bn";
    const pack = window.AMP_HELP[lang] || window.AMP_HELP.bn;
    return (pack && pack[key]) || (window.AMP_HELP.en && window.AMP_HELP.en[key]) || key;
  };

  function closeAllPopovers() {
    document.querySelectorAll(".help-popover").forEach((p) => p.remove());
  }

  function showPopover(anchor, text) {
    closeAllPopovers();
    const pop = document.createElement("div");
    pop.className = "help-popover";
    pop.textContent = text;
    document.body.appendChild(pop);
    const r = anchor.getBoundingClientRect();
    const pad = 8;
    let top = r.bottom + pad + window.scrollY;
    let left = r.left + window.scrollX;
    const maxW = Math.min(360, window.innerWidth - 24);
    pop.style.maxWidth = maxW + "px";
    requestAnimationFrame(() => {
      const pr = pop.getBoundingClientRect();
      if (left + pr.width > window.innerWidth - 12) {
        left = Math.max(12, window.innerWidth - pr.width - 12) + window.scrollX;
      }
      if (r.bottom + pr.height + pad > window.innerHeight) {
        top = r.top + window.scrollY - pr.height - pad;
      }
      pop.style.top = `${Math.max(8, top)}px`;
      pop.style.left = `${Math.max(8, left)}px`;
    });
  }

  window.ampMountHelpTips = function ampMountHelpTips() {
    document.querySelectorAll("[data-help]").forEach((el) => {
      if (el.querySelector(":scope > .info-btn, :scope > .label-row .info-btn")) return;
      const key = el.getAttribute("data-help");
      if (!key) return;
      let row = el.querySelector(":scope > .label-row");
      if (!row) {
        const first = el.firstElementChild;
        if (first && (first.tagName === "SPAN" || first.tagName === "H2" || first.tagName === "H3" || first.tagName === "SUMMARY")) {
          row = document.createElement("span");
          row.className = "label-row";
          el.insertBefore(row, first);
          row.appendChild(first);
        } else {
          row = document.createElement("span");
          row.className = "label-row";
          el.insertBefore(row, el.firstChild);
        }
      }
      if (row.querySelector(".info-btn")) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "info-btn";
      btn.setAttribute("aria-label", window.ampHelpT("help_label"));
      btn.textContent = "i";
      const open = () => showPopover(btn, window.ampHelpT(key));
      btn.addEventListener("mouseenter", open);
      btn.addEventListener("focus", open);
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        open();
      });
      row.appendChild(btn);
    });
  };

  document.addEventListener("click", (e) => {
    if (!(e.target instanceof Element)) return;
    if (e.target.closest(".info-btn") || e.target.closest(".help-popover")) return;
    closeAllPopovers();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllPopovers();
  });
})();
