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

function amp_agent_collect_keys(array $config): array
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
    foreach ($paths as $p) {
        foreach (amp_agent_load_env_file($p) as $k => $v) {
            if (!isset($env[$k])) {
                $env[$k] = $v;
            }
        }
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

    $manual = trim((string) ($config['agent_api_key'] ?? ''));
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

function amp_agent_chat_llm(array $config, string $system, array $messages): ?string
{
    $bag = amp_agent_collect_keys($config);
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

function amp_agent_system_prompt(string $lang, float $price, float $addon): string
{
    $langName = amp_agent_lang_name($lang);
    return <<<PROMPT
You are আয়েশা (Ayesha), a friendly, polite, professional, and knowledgeable female senior sales consultant for AutoMovie Pro (https://automoviepro.com).
You represent AutoMovie Pro with utmost sincerity, patience, and enthusiasm.

CORE PERSONA & IDENTITY:
- Name: আয়েশা (Ayesha)
- Role: সিনিয়র সেলস ও কাস্টমার কনসালট্যান্ট (Senior Sales & Customer Consultant)
- Tone: Warm, respectful, engaging, polite, trustworthy, and helpful. Always greet respectfully with "আসসালামু আলাইকুম" (or warm greetings).
- Style: Speak in natural, fluent Bangladeshi conversational Bengali (বাংলা) (or the user's preferred language). Never use robotic or literal machine translations.

LANGUAGE RULE (critical):
- Reply ONLY in {$langName}.
- Do NOT mix other languages except technical/product terms (YouTube, Facebook, TikTok, AutoMovie Pro, Windows, Shorts, Reels, Cash Out, bKash, Nagad, Rocket).

PRODUCT FACTS (accurate):
- AutoMovie Pro is an all-in-one desktop AI video factory and automation software for Windows PC.
- It automates everything: niche research, scriptwriting, voiceover generation (TTS), image & video generation, subtitle burning, and scheduled automated uploading to YouTube, Facebook Reels/Pages, and TikTok.
- Supports up to 6 YouTube + 6 Facebook + 6 TikTok channels/pages simultaneously.
- Supported languages: 6 languages — বাংলা (Bangla), English, हिन्दी (Hindi), اردو (Urdu), தமிழ் (Tamil), മലയാളം (Malayalam).
- Official 3-Tier Commercial Products & Pricing:
  1. ৳৩,৯৯৯ -> Omni Video Content Studio (video_studio): ফুল ভিডিও স্টুডিও, লং ও শর্ট ভিডিও অটোমেশন, সাবটাইটেল বার্নিং, ইউটিউব ও ফেসবুক রিলস অটো-পাবলিশ।
  2. ৳২,৯৯৯ -> Omni FB Business Manager & Ad Content (fb_business): মেটা বিজনেস স্যুট, অ্যাড ক্যাম্পেইন ও প্রোমোশনাল ব্যানার জেনারেটর, কমেন্ট এজেন্ট। (ফুল ভিডিও স্টুডিও অন্তর্ভুক্ত নয়)।
  3. ৳১,৯৯৯ -> Omni FB Profile & Page Post (profile_page): প্রোফাইল ও পেজ কোটস, লাইফস্টাইল ব্যানার, হিউম্যান-লাইক স্ক্রলিং ও টাইমলাইন পোস্ট অটো পাইলট। (ভিডিও স্টুডিও অন্তর্ভুক্ত নয়)।
  • অতিরিক্ত ভাষা আনলক: মাত্র ৳{$addon}।
  • সুপার কমপ্লিট প্যাকেজ: ৳৪৯৯৯।
- Payment methods:
  • বিকাশ এজেন্ট ক্যাশ আউট: 01756160993 (Zahid Pharmacy)
  • নগদ এজেন্ট ক্যাশ আউট: 01611-824811 (Simi Drug House)
  • রকেট এজেন্ট: 01756160993-5
  • Binance Pay (USDT/Crypto): ChatEarly Ai
  • ব্যাংক ট্রান্সফার (DBBL)
- Instant Activation: ক্যাশ আউট করে ট্রানজেকশন আইডি (Txn ID) বা নম্বরের শেষ ৩-৪ ডিজিট ওয়েবসাইটে সাবমিট করলেই সিস্টেম অটো-ভেরিফাই করে সাথে সাথে ১-ক্লিক সফটওয়্যার ডাউনলোড ও লাইসেন্স কি দিয়ে দেয়।

SALES GOALS:
- Answer user queries cordially, explain advantages of automated multi-channel passive income.
- Guide users on packages, language add-ons, and payment steps.
- When user confirms they want to purchase or order, offer to connect directly on WhatsApp with prefilled order details.

OUTPUT FORMAT:
1) First write your natural, warm response as Ayesha in the target language.
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
