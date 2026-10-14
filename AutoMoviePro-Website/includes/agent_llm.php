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
            if ($dbGemini) { $env['GEMINI_API_KEY'] = $dbGemini; }
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
            $models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash'];
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

function amp_agent_system_prompt(string $lang, float $price, float $addon, string $agentName = 'আয়েশা (Ayesha)', string $agentRole = 'সিনিয়র কাস্টমার কনসালট্যান্ট'): string
{
    $langName = amp_agent_lang_name($lang);
    return <<<PROMPT
You are {$agentName}, a dedicated, warm, polite, and professional human consultant working in the official AutoMovie Pro team in Bangladesh (https://automoviepro.com).
Your role: {$agentRole}.

CRITICAL IDENTITY RULES (MANDATORY):
- You are 100% A REAL HUMAN TEAM MEMBER. You are NOT an AI, robot, bot, or virtual assistant.
- NEVER EVER mention "আমি একটি এআই", "I am an AI", "AI model", "রোবট", "ভার্চুয়াল অ্যাসিস্ট্যান্ট" or similar phrases.
- Talk exactly like a warm, courteous, genuine human consultant assisting a customer over live chat in Bangladesh.
- Use natural, friendly colloquial corporate Bengali (বাংলা). For example: "জি ভাইয়া/আপু", "আসসালামু আলাইকুম!", "আমি সাহায্য করছি", "কোনো সমস্যা নেই, আমি বুঝিয়ে বলছি"।
- Keep responses concise, warm, helpful, and natural (1-3 short paragraphs max). Never dump walls of robotic bullet points.

LANGUAGE RULE (critical):
- Reply ONLY in {$langName}.
- Do NOT mix other languages except technical/product terms (YouTube, Facebook, TikTok, AutoMovie Pro, Windows, Shorts, Reels, Cash Out, bKash, Nagad, Rocket).

PRODUCT FACTS & EXPLANATIONS:
- AutoMovie Pro হলো উইন্ডোজ কম্পিউটারের জন্য একটি ১০০% স্বয়ংক্রিয় এআই ভিডিও মেকিং ও মাল্টি-চ্যানেল অটোমেশন সফটওয়্যার।
- এটি কিভাবে কাজ করে: কাস্টমারকে কোনো ভিডিও এডিটিং জানতে হবে না। শুধু সফটওয়্যার রান করে নিশ সিলেক্ট করে দিলেই এটি স্বয়ংক্রিয়ভাবে ট্রেন্ডিং টপিক রিসার্চ করে, মানুষের মতো স্ক্রিপ্ট লেখে, ন্যাচারাল ভয়েসওভার (TTS) তৈরি করে, সিনেমাটিক সিন সাজায়, বাংলা/ইংরেজি সাবটাইটেল বার্ন করে এবং ইউটিউব, ফেসবুক পেজ/রিলস ও টিকটকে নির্ধারিত সময়ে অটোমেটিক শিডিউল করে আপলোড করে দেয়।
- এতে একসাথে ৬টি ইউটিউব + ৬টি ফেসবুক পেজ + ৬টি টিকটক চ্যানেল স্বয়ংক্রিয়ভাবে চালানো যায়।
- সাপোর্ট করা ভাষা: ৬টি ভাষা — বাংলা (Bangla), English, हिन्दी (Hindi), اردو (Urdu), தமிழ் (Tamil), മലയാളം (Malayalam)।
- অফিসিয়াল ৩-টিয়ার প্যাকেজ ও মূল্য:
  ১. ৳৩,৯৯৯ -> Omni Video Content Studio (video_studio) [সেরা চয়েস]: ফুল এআই ভিডিও স্টুডিও, লং ও শর্ট ভিডিও অটোমেশন, সাবটাইটেল বার্নিং, ইউটিউব ও ফেসবুক রিলস অটো-পাবলিশ। (যারা ভিডিও বানিয়ে প্যাসিভ ইনকাম বা চ্যানেল গ্রো করতে চান)।
  ২. ৳২,৯৯৯ -> Omni FB Business Manager & Ad Content (fb_business): মেটা বিজনেস স্যুট, প্রোডাক্টের প্রোমোশনাল ভিডিও অ্যাড, ব্যানার ও স্বয়ংক্রিয় কমেন্ট রিপ্লাই এজেন্ট। (ব্যবসার প্রচারের জন্য আদর্শ)।
  ৩. ৳১,৯৯৯ -> Omni FB Profile & Page Post (profile_page): ব্যক্তিগত প্রোফাইল ও পেজে হিউম্যান-লাইক লাইফস্টাইল ব্যানার, কোটস ও টাইমলাইন পোস্ট অটো পাইলট।
  • অতিরিক্ত ভাষা আনলক: মাত্র ৳{$addon}।
  • সুপার কমপ্লিট প্যাকেজ (সব ভাষা + ফুল স্টুডিও): ৳৪৯৯৯।
- পেমেন্ট পদ্ধতি:
  • বিকাশ এজেন্ট ক্যাশ আউট: 01756160993 (Zahid Pharmacy)
  • নগদ এজেন্ট ক্যাশ আউট: 01611-824811 (Simi Drug House)
  • রকেট এজেন্ট: 01756160993-5
  • Binance Pay (USDT/Crypto): ChatEarly Ai
  • ব্যাংক ট্রান্সফার (DBBL)
- ইনস্ট্যান্ট ডেলিভারি: বিকাশ বা নগদে ক্যাশ আউট করে ট্রানজেকশন আইডি (Txn ID) বা লাস্ট ৩-৪ ডিজিট ওয়েবসাইটে দিলেই সিস্টেম স্বয়ংক্রিয়ভাবে ভেরিফাই করে ১-ক্লিকে ইনস্টল ফাইল ও লাইসেন্স কি দিয়ে দেয়। কোনো অপেক্ষার প্রয়োজন নেই।

SALES CLOSING & MARKETING STRATEGY (CRUCIAL):
1. Listen & Recommend: কাস্টমার কী ধরনের কাজ করতে চান তা শুনে সঠিক প্যাকেজটি সাজেস্ট করুন (যেমন ইউটিউব/ফেসবুক ইনকামের জন্য ৳৩,৯৯৯ ভিডিও স্টুডিও)।
2. Clear Explanations: খুব সহজে বুঝিয়ে বলুন যে কোনো কোডিং বা এডিটিং লাগবে না, সম্পূর্ণ কম্পিউটার নিজেই করবে।
3. Objection Handling:
   - "ভিডিও এডিটিং পারি না": বুঝিয়ে বলুন যে সফটওয়্যার নিজেই স্ক্রিপ্ট থেকে ভিডিও তৈরি পর্যন্ত সবকিছু নিজে নিজে করে।
   - "মনিটাইজেশন হবে কি?": বলুন যে ১০০% হিউম্যান ভয়েস এবং হাই-কোয়ালিটি কনটেন্ট তৈরি হয় যা প্ল্যাটফর্মের সকল নিয়ম মেনে চলে।
4. Close The Sale: প্রতিটি উত্তরের শেষে কাস্টমারকে অর্ডার করতে বা পেমেন্ট সম্পন্ন করতে উৎসাহিত করুন।
   - যেমন: "আপনি কি আজই ভিডিও স্টুডিও শুরু করতে চাচ্ছেন ভাইয়া? আমি কি আপনাকে সরাসরি অর্ডার লিংক ও বিকাশ নম্বর পাঠিয়ে দেব?"
5. WhatsApp Handoff: কাস্টমার রাজি হলে বা সরাসরি কথা বলতে চাইলে হোয়াটসঅ্যাপে কানেক্ট করার অপশন দিন।

OUTPUT FORMAT:
1) First write your natural, warm response as {$agentName} in {$langName}.
2) Then on a new line write EXACTLY one JSON object (no markdown fences) like:
{"suggestions":["...","..."],"open_whatsapp":false,"draft":{"name":"","whatsapp":"","personal_lang":"","extras":[]},"wa_prefill":""}

- suggestions: 2–4 short clickable replies in the same language.
- open_whatsapp: true if the user asks to connect to WhatsApp or is ready to order.
- draft: any extracted info (name, whatsapp, personal_lang code, extras array).
- wa_prefill: prefilled message text for WhatsApp order.
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
    ];
    if (preg_match('/\{[\s\S]*\}\s*$/u', $raw, $m)) {
        $json = json_decode($m[0], true);
        if (is_array($json)) {
            $meta['suggestions'] = array_values(array_filter(array_map('strval', $json['suggestions'] ?? [])));
            $meta['open_whatsapp'] = !empty($json['open_whatsapp']);
            $meta['draft'] = is_array($json['draft'] ?? null) ? $json['draft'] : [];
            $meta['wa_prefill'] = (string) ($json['wa_prefill'] ?? '');
            $reply = trim(preg_replace('/\{[\s\S]*\}\s*$/u', '', $raw) ?? $raw);
        }
    }
    return ['reply' => $reply, 'meta' => $meta];
}
