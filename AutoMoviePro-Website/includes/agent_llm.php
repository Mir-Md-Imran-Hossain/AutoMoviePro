<?php
declare(strict_types=1);

/**
 * Sales-agent LLM helpers — Groq / Gemini / OpenRouter.
 * Keys load from config or workspace .env (never commit secrets).
 */

function amp_agent_load_env_file(string $path): array
{
    $out = [];
    if ($path === '' || !is_file($path)) {
        return $out;
    }
    $lines = @file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (!is_array($lines)) {
        return $out;
    }
    foreach ($lines as $line) {
        $line = trim($line);
        if ($line === '' || $line[0] === '#' || !str_contains($line, '=')) {
            continue;
        }
        [$k, $v] = explode('=', $line, 2);
        $k = trim($k);
        $v = trim($v, " \t\"'");
        if ($k !== '' && $v !== '') {
            $out[$k] = $v;
        }
    }
    return $out;
}

function amp_agent_collect_keys(array $config, ?PDO $pdo = null): array
{
    $env = [];
    $paths = [];
    if (!empty($config['agent_env_file'])) {
        $paths[] = (string) $config['agent_env_file'];
    }
    // Workspace .env next to AutoMoviePro-Website and AutoMoviePro-Software
    $paths[] = dirname(__DIR__, 2) . DIRECTORY_SEPARATOR . 'AutoMoviePro-Software' . DIRECTORY_SEPARATOR . '.env';
    $paths[] = dirname(__DIR__, 2) . DIRECTORY_SEPARATOR . '.env';
    $paths[] = dirname(__DIR__) . DIRECTORY_SEPARATOR . '.env';
    $paths[] = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'AutoMoviePro-Website' . DIRECTORY_SEPARATOR . '.env';
    foreach ($paths as $p) {
        foreach (amp_agent_load_env_file($p) as $k => $v) {
            if (!isset($env[$k])) {
                $env[$k] = $v;
            }
        }
    }

    // Load from process environment
    foreach (['GOOGLE_API_KEY', 'GEMINI_API_KEY', 'GROQ_API_KEY', 'OPENROUTER_API_KEY', 'AGENT_API_KEY'] as $gk) {
        $v = getenv($gk) ?: ($_ENV[$gk] ?? '');
        if ($v && !isset($env[$gk])) {
            $env[$gk] = (string) $v;
        }
    }

    // Load from database site_settings if PDO provided
    if ($pdo instanceof PDO) {
        try {
            $dbGemini = setting($pdo, 'gemini_api_key', '');
            if ($dbGemini) { 
                $env['GEMINI_API_KEY'] = $dbGemini;
                foreach (preg_split('/[\r\n,;]+/', $dbGemini) as $idx => $kPart) {
                    $kPart = trim($kPart);
                    if ($kPart !== '') {
                        $env['GEMINI_API_KEY_' . ($idx + 1)] = $kPart;
                        $env['GOOGLE_API_KEY_' . ($idx + 1)] = $kPart;
                    }
                }
            }
            $dbGoogle = setting($pdo, 'google_api_key', '');
            if ($dbGoogle && empty($env['GOOGLE_API_KEY'])) { $env['GOOGLE_API_KEY'] = $dbGoogle; }
            $dbGroq = setting($pdo, 'groq_api_key', '');
            if ($dbGroq) { $env['GROQ_API_KEY'] = $dbGroq; }
            $dbOpenRouter = setting($pdo, 'openrouter_api_key', '');
            if ($dbOpenRouter) { $env['OPENROUTER_API_KEY'] = $dbOpenRouter; }
        } catch (\Throwable $e) {}
    }

    $pick = static function (array $env, string $prefix, int $max = 30): array {
        $keys = [];
        if (!empty($env[$prefix])) {
            $keys[] = $env[$prefix];
        }
        for ($i = 1; $i <= $max; $i++) {
            $k = $prefix . '_' . $i;
            if (!empty($env[$k])) {
                $keys[] = $env[$k];
            }
        }
        return array_values(array_unique($keys));
    };

    $manual = trim((string) ($config['agent_api_key'] ?? ($env['AGENT_API_KEY'] ?? '')));
    $geminiKeys = array_merge(
        $pick($env, 'GOOGLE_API_KEY', 30),
        $pick($env, 'GEMINI_API_KEY', 30),
        $pick($env, 'IMAGE_GOOGLE_API_KEY', 10),
        $pick($env, 'LOCALIZATION_GOOGLE_API_KEY', 10)
    );
    $grokKeys = array_merge(
        $pick($env, 'AGENT_GROK_API_KEY', 10),
        $pick($env, 'TOPIC_GROK_API_KEY', 10),
        $pick($env, 'XAI_API_KEY', 10)
    );
    $groqKeys = $pick($env, 'GROQ_API_KEY', 10);
    $openrouterKeys = array_merge(
        $pick($env, 'OPENROUTER_API_KEY', 10),
        $grokKeys
    );

    return [
        'provider' => strtolower(trim((string) ($config['agent_provider'] ?? 'auto'))),
        'model' => trim((string) ($config['agent_model'] ?? '')),
        'manual' => $manual,
        'gemini' => array_values(array_unique($geminiKeys)),
        'grok' => array_values(array_unique($grokKeys)),
        'groq' => array_values(array_unique($groqKeys)),
        'openrouter' => array_values(array_unique($openrouterKeys)),
    ];
}

function amp_agent_http_json(string $url, array $headers, array $body, int $timeout = 45): array
{
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_POSTFIELDS => json_encode($body, JSON_UNESCAPED_UNICODE),
        CURLOPT_TIMEOUT => $timeout,
        CURLOPT_SSL_VERIFYPEER => false,
    ]);
    $raw = curl_exec($ch);
    $err = curl_error($ch);
    $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($raw === false || $err !== '') {
        return ['ok' => false, 'error' => $err ?: 'curl_failed', 'code' => $code];
    }
    $json = json_decode($raw, true);
    return ['ok' => $code >= 200 && $code < 300, 'code' => $code, 'json' => $json, 'raw' => $raw];
}

function amp_agent_chat_llm(array $config, string $system, array $messages, ?PDO $pdo = null): ?string
{
    $bag = amp_agent_collect_keys($config, $pdo);
    $provider = $bag['provider'];

    $order = ['gemini', 'grok', 'openrouter', 'groq'];
    if ($provider !== '' && $provider !== 'auto' && in_array($provider, $order, true)) {
        $order = array_values(array_unique(array_merge([$provider], $order)));
    }

    foreach ($order as $p) {
        $text = null;
        if ($p === 'gemini') {
            $keys = $bag['gemini'];
            if ($bag['manual'] !== '' && $provider === 'gemini') {
                array_unshift($keys, $bag['manual']);
            }
            $models = ['gemini-3.8-flash', 'gemini-3.5-flash', 'gemini-3.1-flash-lite', 'gemini-flash-latest'];
            if ($bag['model'] !== '') {
                array_unshift($models, $bag['model']);
            }
            $contents = [];
            foreach ($messages as $m) {
                $role = ($m['role'] ?? '') === 'assistant' ? 'model' : 'user';
                $contents[] = ['role' => $role, 'parts' => [['text' => (string) ($m['content'] ?? '')]]];
            }
            foreach ($keys as $key) {
                if (!str_starts_with($key, 'AIza')) {
                    continue;
                }
                foreach ($models as $mName) {
                    $url = 'https://generativelanguage.googleapis.com/v1beta/models/'
                        . rawurlencode($mName) . ':generateContent?key=' . rawurlencode($key);
                    $res = amp_agent_http_json(
                        $url,
                        ['Content-Type: application/json'],
                        [
                            'systemInstruction' => ['parts' => [['text' => $system]]],
                            'contents' => $contents,
                            'generationConfig' => ['temperature' => 0.7, 'maxOutputTokens' => 900],
                        ],
                        25
                    );
                    $text = (string) ($res['json']['candidates'][0]['content']['parts'][0]['text'] ?? '');
                    if ($text !== '') {
                        return trim($text);
                    }
                }
            }
        }

        if ($p === 'grok' || $p === 'openrouter') {
            $keys = ($p === 'grok' && !empty($bag['grok'])) ? $bag['grok'] : $bag['openrouter'];
            if ($bag['manual'] !== '' && ($provider === 'openrouter' || $provider === 'grok')) {
                array_unshift($keys, $bag['manual']);
            }
            $model = $bag['model'] !== '' ? $bag['model'] : 'x-ai/grok-2-1212';
            foreach ($keys as $key) {
                $endpoint = str_starts_with($key, 'xai-') 
                    ? 'https://api.x.ai/v1/chat/completions' 
                    : 'https://openrouter.ai/api/v1/chat/completions';
                $useModel = str_starts_with($key, 'xai-') ? 'grok-beta' : $model;

                $msgs = array_merge([['role' => 'system', 'content' => $system]], $messages);
                $res = amp_agent_http_json(
                    $endpoint,
                    [
                        'Authorization: Bearer ' . $key,
                        'Content-Type: application/json',
                        'HTTP-Referer: https://automoviepro.com',
                        'X-Title: AutoMovie Pro Sales Consultant Ayesha',
                    ],
                    [
                        'model' => $useModel,
                        'temperature' => 0.7,
                        'max_tokens' => 900,
                        'messages' => $msgs,
                    ],
                    25
                );
                $text = (string) ($res['json']['choices'][0]['message']['content'] ?? '');
                if ($text !== '') {
                    return trim($text);
                }
            }
        }

        if ($p === 'groq') {
            $keys = $bag['groq'];
            if ($bag['manual'] !== '' && ($provider === 'groq' || $provider === 'auto')) {
                array_unshift($keys, $bag['manual']);
            }
            $model = $bag['model'] !== '' ? $bag['model'] : 'llama-3.3-70b-versatile';
            foreach ($keys as $key) {
                $msgs = array_merge([['role' => 'system', 'content' => $system]], $messages);
                $res = amp_agent_http_json(
                    'https://api.groq.com/openai/v1/chat/completions',
                    [
                        'Authorization: Bearer ' . $key,
                        'Content-Type: application/json',
                    ],
                    [
                        'model' => $model,
                        'temperature' => 0.7,
                        'max_tokens' => 900,
                        'messages' => $msgs,
                    ],
                    25
                );
                $text = (string) ($res['json']['choices'][0]['message']['content'] ?? '');
                if ($text !== '') {
                    return trim($text);
                }
            }
        }
    }
    return null;
}

function amp_agent_lang_name(string $lang): string
{
    return match ($lang) {
        'bn' => 'Bangla (বাংলা) — natural Bangladeshi conversational Bangla, warm, respectful, polite spoken style',
        'hi' => 'Hindi (हिन्दी) — natural friendly Hindi, polite customer service tone',
        'ur' => 'Urdu (اردو) — clear everyday polite Urdu',
        'ta' => 'Tamil (தமிழ்) — simple polite spoken Tamil for customer marketing',
        'ml' => 'Malayalam (മലയാളം) — simple polite spoken Malayalam',
        default => 'English — clear, friendly, and professional sales English',
    };
}

function amp_agent_system_prompt(
    string $lang, 
    float $price, 
    float $addon, 
    string $agentName = 'আয়েশা (Ayesha)', 
    string $agentRole = 'সিনিয়র সেলস ও কাস্টমার কনসালট্যান্ট',
    ?PDO $pdo = null
): string {
    $langName = amp_agent_lang_name($lang);

    // Dynamic Admin Settings
    $discountAllowed = ($pdo ? setting($pdo, 'agent_discount_allowed', '1') : '1') === '1';
    $discountMode = $pdo ? setting($pdo, 'agent_discount_mode', 'consultative') : 'consultative';
    $discountType = $pdo ? setting($pdo, 'agent_discount_type', 'flat') : 'flat';
    $initDiscount = (float) ($pdo ? setting($pdo, 'agent_initial_discount_amount', '500') : 500);
    $maxDiscount = (float) ($pdo ? setting($pdo, 'agent_max_discount_amount', '1000') : 1000);

    $pkgVideoInit = (float) ($pdo ? setting($pdo, 'agent_pkg_video_studio_init', '500') : 500);
    $pkgVideoMax = (float) ($pdo ? setting($pdo, 'agent_pkg_video_studio_max', '1000') : 1000);

    $pkgFbInit = (float) ($pdo ? setting($pdo, 'agent_pkg_fb_business_init', '300') : 300);
    $pkgFbMax = (float) ($pdo ? setting($pdo, 'agent_pkg_fb_business_max', '600') : 600);

    $pkgProfInit = (float) ($pdo ? setting($pdo, 'agent_pkg_profile_page_init', '200') : 200);
    $pkgProfMax = (float) ($pdo ? setting($pdo, 'agent_pkg_profile_page_max', '400') : 400);

    $freeAddon = ($pdo ? setting($pdo, 'agent_free_addon_lang', '1') : '1') === '1';
    $couponCode = $pdo ? trim(setting($pdo, 'agent_coupon_prefix', 'VIP500')) : 'VIP500';
    $validityHours = (int) ($pdo ? setting($pdo, 'agent_followup_reminder_hours', '24') : 24);
    $customInstructions = $pdo ? trim(setting($pdo, 'agent_custom_instructions', '')) : '';
    $askWaForDemo = ($pdo ? setting($pdo, 'agent_ask_whatsapp_for_demo', '1') : '1') === '1';

    $discountRuleText = $discountAllowed
        ? "DISCOUNTS PERMITTED: You are authorized by admin to offer discounts.\n"
          . "- Negotiation Strategy: {$discountMode} mode.\n"
          . "- Initial Offer: ৳{$initDiscount} flat discount.\n"
          . "- Maximum Absolute Ceiling: ৳{$maxDiscount} (NEVER exceed this ceiling).\n"
          . "- Package-Specific Limits:\n"
          . "  * Omni Video Content Studio (৳৩,৯৯৯): Start with ৳{$pkgVideoInit}, Max allowed ৳{$pkgVideoMax}.\n"
          . "  * FB Business Manager (৳২,৯৯৯): Start with ৳{$pkgFbInit}, Max allowed ৳{$pkgFbMax}.\n"
          . "  * FB Profile Auto Pilot (৳১,৯৯৯): Start with ৳{$pkgProfInit}, Max allowed ৳{$pkgProfMax}.\n"
          . "- Free Addon Language: " . ($freeAddon ? "Yes, you can offer 1 free international language (worth ৳{$addon}) as a closing gift." : "No free addon.") . "\n"
          . "- Secret Coupon Code: [{$couponCode}]\n"
          . "- Validity Window: State that the offer is reserved for the next {$validityHours} hours."
        : "DISCOUNTS DISABLED: Admin has disabled discounts. Politely explain that our packages are already discounted lifetime licenses with zero monthly fees.";

    $customNoteSection = $customInstructions !== ''
        ? "\nADMIN SPECIAL DIRECTIVE:\n{$customInstructions}\n"
        : "";

    return <<<PROMPT
You are {$agentName}, a world-class, top-tier senior sales consultant and customer advisor representing the official AutoMovie Pro team in Bangladesh (https://automoviepro.com).
Your title: {$agentRole}.

CRITICAL IDENTITY & HUMAN AUTHENTICITY:
- You are 100% A REAL HUMAN CONSULTANT. You are NOT an AI, robot, bot, or virtual assistant.
- NEVER EVER say "আমি একটি এআই", "I am an AI", "AI model", "রোবট", "বট" or similar words.
- Speak with warmth, sincere empathy, high business acumen, and polite Bangladeshi etiquette ("জি ভাইয়া/আপু", "আসসালামু আলাইকুম স্যার!", "আমি বিস্তারিত বুঝিয়ে বলছি, একদম চিন্তা করবেন না")।
- Maintain concise, crisp, persuasive responses (2-3 short, powerful paragraphs). Never dump cold, mechanical, boring lists of bullet points.

BANGLISH & MULTI-SCRIPT COMPREHENSION (MANDATORY):
- Visitors will frequently write in Banglish (Bengali written using English/Latin alphabet, for example: "koyta softower ase apnader", "dam koto bhai", "kivabe kinbo", "amar kon package lagbe", "install kivabe korbo", "youtube theke taka income kora jabe?").
- You MUST effortlessly understand Banglish, Roman Urdu, and colloquial phonetic spelling.
- Always reply in pure, elegant, standard Bengali (বাংলা বর্ণমালা) with warmth and utmost clarity.
- Accurately identify their question even from 2-3 words:
  * "koyta softower ase" -> Explain that we have 3 distinct, turnkey software packages tailored for different needs.
  * "dam koto" -> Explain the transparent lifetime pricing (৳৩,৯৯৯ / ৳২,৯৯৯ / ৳১,৯৯৯) with zero monthly fees.
  * "kivabe kaj kore" -> Explain the 1-click turnkey automation (script + voice + visuals + subtitles + 18 channels auto-publish).

PRODUCT SUITE (3 DEDICATED TURNKEY PACKAGES):
1. ৳৩,৯৯৯ -> Omni Video Content Studio (video_studio) [সর্বোচ্চ বিক্রিত ও সেরা চয়েস]:
   - ফুল এআই ভিডিও প্রোডাকশন ইঞ্জিন। কোনো ভিডিও এডিটিং জানা ছাড়া ১-ক্লিকে ভাইরাল স্ক্রিপ্ট, মানুষের মতো কণ্ঠ (Voiceover), সিনেমাটিক ব্যাকগ্রাউন্ড সিন এবং অটোমেটিক বাংলা/ইংরেজি সাবটাইটেল তৈরি।
   - একসাথে ৬টি YouTube চ্যানেল + ৬টি Facebook পেজ/রিলস + ৬টি TikTok অ্যাকাউন্ট (মোট ১৮টি চ্যানেল)-এ স্বয়ংক্রিয় শিডিউলিং ও আপলোড।
   - যারা ইউটিউব ও ফেসবুক থেকে প্যাসিভ ইনকাম করতে চান বা ফেসলেস চ্যানেল চালাতে চান, তাদের জন্য অপরিহার্য।
2. ৳২,৯৯৯ -> Omni FB Business Manager & Ad Content (fb_business):
   - ই-কমার্স, শপ ও ব্যবসায়ের জন্য মেটা বিজনেস স্যুট অটোমেশন।
   - প্রোডাক্টের আকর্ষণীয় ভিডিও বিজ্ঞাপন (Video Ads), প্রোমো ব্যানার এবং ইনবক্স/কমেন্টে স্বয়ংক্রিয় এআই রিপ্লাই এজেন্ট।
3. ৳১,৯৯৯ -> Omni FB Profile & Page Auto Pilot (profile_page):
   - ব্যক্তিগত প্রোফাইল ও পেজের জন্য অটো-পাইলট কনটেন্ট ইঞ্জিন। প্রতিদিন জীবনমুখী উক্তি, ইসলামিক/মোটিভেশনাল ব্যানার ও আকর্ষণীয় টাইমলাইন পোস্ট তৈরি ও শিডিউলিং।
• অতিরিক্ত ভাষা অ্যাড-অন: মাত্র ৳{$addon} (বাংলা ছাড়াও English, हिन्दी, اردو, தமிழ், മലയാളം সাপোর্ট)।
• লাইফটাইম লাইসেন্স: কোনো মাসিক সাবস্ক্রিপশন ফি নেই, সম্পূর্ণ কম্পিউটার সুরক্ষিত ও ওয়ান-টাইম পেমেন্ট।

MANDATORY ADMIN DISCOUNT & NEGOTIATION RULES:
{$discountRuleText}
{$customNoteSection}

WORLD-CLASS SALES PSYCHOLOGY & CONVERSION TECHNIQUES (SPIN & STRAIGHT LINE):
1. Empathy & Problem-Solution:
   - কাস্টমারকে বোঝান যে ম্যানুয়াল ভিডিও এডিটিং করতে দিনে ৪-৬ ঘণ্টা সময় নষ্ট হয় অথবা মাসে ৳১৫,০০০-৳২৫,০০০ দিয়ে এডিটর রাখতে হয়। AutoMovie Pro মাত্র এক ক্লিকে সম্পূর্ণ ফ্রিতে লাইফটাইম সেই কাজটি করে দেয়।
2. Social Proof & Authority:
   - "ইতিমধ্যে ১,২৫০+ কনটেন্ট ক্রিয়েটর ও উদ্যোক্তা এই সফটওয়্যার দিয়ে প্রতিদিন সফলভাবে কাজ করছেন এবং তাদের চ্যানেল ও ব্যবসা গ্রো করছেন।"
3. WhatsApp Number Polite Capture (Lead Gen):
   - কাস্টমার একটু আগ্রহী হলেই বা বিস্তারিত জানতে চাইলে অত্যন্ত বিনীতভাবে তার WhatsApp নম্বরটি চেয়ে নিন:
     "স্যার, সফটওয়্যারটির লাইভ ফুল ভিডিও ডেমো এবং আজকের স্পেশাল ডিসকাউন্ট অফারটি কি আপনার WhatsApp-এ পাঠিয়ে দেব? আপনার WhatsApp নম্বরটি একটু লিখে দিলে আমি এখনই সম্পূর্ণ ফাইলটি পাঠিয়ে দিচ্ছি।"
   - কাস্টমার নম্বর দিলে বলুন: "অনেক ধন্যবাদ স্যার! আপনার নম্বরে আমি সকল ফাইল ও ডেমো পাঠিয়ে দিচ্ছি।"
4. Objection Handling ("পরে যোগাযোগ করব" / "পরে নেব"):
   - কাস্টমার যদি বলে পরে নেবে বা চিন্তা করে জানাবে, তাকে কখনোই জোর করবেন না।
   - প্রথমে সম্মতির সাথে রিমাইন্ডার টাইম চান: "অবশ্যই স্যার! আপনি কখন একটু ফ্রি থাকবেন—আজ সন্ধ্যায় নাকি আগামীকাল দুপুরে? যাতে আপনাকে সুন্দরভাবে মনে করিয়ে দিতে পারি।"
   - সাথে সাথেই অ্যাডমিন পলিসি অনুযায়ী স্পেশাল সিক্রেট ডিসকাউন্ট কুপন কোড [{$couponCode}] অফার করুন।
   - অর্ডার লিংক দিন: https://automoviepro.com/order.php?coupon={$couponCode}

PAYMENT METHODS & INSTANT DELIVERY:
- বিকাশ এজেন্ট ক্যাশ আউট: 01756160993 (Zahid Pharmacy)
- নগদ এজেন্ট ক্যাশ আউট: 01611-824811 (Simi Drug House)
- রকেট এজেন্ট: 01756160993-5 | Binance Pay: ChatEarly Ai
- ক্যাশ আউটের পর ওয়েবসাইটে ট্রানজেকশন আইডি (TxnID) দিলেই ১-ক্লিকে ইনস্ট্যান্ট লাইসেন্স কি ও ডাউনলোড লিংক সক্রিয় হয়ে যায়।

OUTPUT FORMAT (STRICT):
1) First, write your warm, consultative human response as {$agentName} in {$langName}.
2) Then, on a brand-new line at the very end, output EXACTLY ONE JSON object (no markdown code blocks):
{"suggestions":["...","..."],"open_whatsapp":false,"draft":{"name":"","whatsapp":"","personal_lang":"","extras":[]},"wa_prefill":"","coupon_offered":""}

- suggestions: 2-4 smart, highly relevant, clickable question chips that address their next likely curiosity.
- open_whatsapp: true if the user asks to connect to WhatsApp or is ready to order.
- coupon_offered: "{$couponCode}" if user asks for discount or says "পরে যোগাযোগ করব" (only if discounts permitted).
PROMPT;
}



function amp_agent_parse_llm_payload(string $raw): array
{
    $reply = trim($raw);
    $meta = [
        'suggestions' => [],
        'open_whatsapp' => false,
        'draft' => [],
        'wa_prefill' => '',
        'coupon_offered' => '',
    ];
    if (preg_match('/\{[\s\S]*\}\s*$/u', $raw, $m)) {
        $json = json_decode($m[0], true);
        if (is_array($json)) {
            $meta['suggestions'] = array_values(array_filter(array_map('strval', $json['suggestions'] ?? [])));
            $meta['open_whatsapp'] = !empty($json['open_whatsapp']);
            $meta['draft'] = is_array($json['draft'] ?? null) ? $json['draft'] : [];
            $meta['wa_prefill'] = (string) ($json['wa_prefill'] ?? '');
            $meta['coupon_offered'] = trim((string) ($json['coupon_offered'] ?? ''));
            $reply = trim(preg_replace('/\{[\s\S]*\}\s*$/u', '', $raw) ?? $raw);
        }
    }
    return ['reply' => $reply, 'meta' => $meta];
}
