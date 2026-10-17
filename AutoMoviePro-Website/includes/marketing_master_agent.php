<?php
declare(strict_types=1);

/**
 * =============================================================================
 * AutoMovie Pro - Central Master Marketing AI Agent (চিফ মার্কেটিং ও সেলস ডিরেক্টর এআই)
 * =============================================================================
 * High-performance central marketing intelligence that oversees the entire customer
 * acquisition, nurturing, and conversion lifecycle across:
 * 1. Website Live Chat (আয়েশা, নীরব, তানিয়া)
 * 2. WhatsApp Live CRM & Broadcasts (টু-ওয়ে স্মার্ট সেলস ক্লোজিং)
 * 3. Facebook / Social Media Comments & Inboxes (অটোনমাস এনগেজমেন্ট)
 * 
 * Embedded Elite Persuasion & Direct-Response Frameworks:
 * - Eugene Schwartz: 5 Stages of Customer Awareness (Unaware -> Problem Aware -> Solution Aware -> Product Aware -> Most Aware)
 * - Robert Cialdini: 6 Principles of Influence (Reciprocity, Commitment, Social Proof, Authority, Liking, Scarcity)
 * - Alex Hormozi: $100M Offers & Value Equation (Dream Outcome, Perceived Likelihood, Time Delay, Effort/Sacrifice, Grand Slam Guarantees)
 * - Russell Brunson: Hook-Story-Offer (Epiphany Bridge, Vehicle of Change, Vehicle/Internal/External False Beliefs)
 * - Chris Voss: Tactical Empathy & Black Swan Negotiation (Emotional Labeling, Mirroring, Calibrated 'How'/'What' Questions)
 * =============================================================================
 */

require_once __DIR__ . '/agent_llm.php';

class MarketingMasterBrain
{
    public const STAGE_UNAWARE = 'unaware';
    public const STAGE_PROBLEM_AWARE = 'problem_aware';
    public const STAGE_SOLUTION_AWARE = 'solution_aware';
    public const STAGE_PRODUCT_AWARE = 'product_aware';
    public const STAGE_MOST_AWARE = 'most_aware';

    public const AGENT_DIRECTOR = 'master_director';
    public const AGENT_AYESHA = 'ayesha';
    public const AGENT_NIROB = 'nirob';
    public const AGENT_TANIA = 'tania';

    /**
     * Detect Eugene Schwartz 5 Stages of Awareness from conversation and text.
     */
    public static function detectAwarenessStage(string $input, array $history = []): string
    {
        $text = mb_strtolower(trim($input));
        $fullContext = $text;
        foreach ($history as $h) {
            $msg = is_array($h) ? ($h['text'] ?? $h['message'] ?? '') : (string) $h;
            $fullContext .= ' ' . mb_strtolower($msg);
        }

        // Stage 5: Most Aware (Ready to buy, asking for bKash/Nagad number, TxnID, discount, how to pay)
        if (preg_match('/(কেনার নিয়ম|অর্ডার করব|টাকা পাঠাব|বিকাশ|নগদ|রকেট|পেমেন্ট|ট্রানজেকশন|ক্যাশ আউট|অর্ডার লিংক|ডিসকাউন্ট দিন|কুপন|অ্যাকাউন্ট নম্বর|payment|bkash|nagad|checkout)/u', $text)) {
            return self::STAGE_MOST_AWARE;
        }

        // Stage 4: Product Aware (Asking about specific packages, 3999 vs 2999 vs 1999 vs 999, features of AutoMovie Pro / WAManager)
        if (preg_match('/(৩,৯৯৯|৩৯৯৯|২,৯৯৯|২৯৯৯|১,৯৯৯|১৯৯৯|৯৯৯|প্যাকেজ|ফিচার|ভিডিও স্টুডিও|মেটা বিজনেস|প্রোফাইল পোস্ট|wamanager|দাম কত|প্রাইস|লাইসেন্স কি|পার্থক্য কি|কোনটা ভালো)/u', $text)) {
            return self::STAGE_PRODUCT_AWARE;
        }

        // Stage 3: Solution Aware (Knows they want automation / AI video / bulk WhatsApp, but comparing solutions or asking how it works)
        if (preg_match('/(কিভাবে কাজ করে|স্বয়ংক্রিয়|অটোমেশন|এআই দিয়ে|ভিডিও তৈরি|বাল্ক মেসেজ|গ্রুপ থেকে নম্বর|চ্যানেল গ্রোথ|প্যাসিভ ইনকাম|ইউটিউব অটোমেশন|সফটওয়্যার কি|how it works|automation)/u', $text)) {
            return self::STAGE_SOLUTION_AWARE;
        }

        // Stage 2: Problem Aware (Suffering from manual editing, time loss, WhatsApp number bans, low views, hiring costly editors)
        if (preg_match('/(সময় পাই না|এডিটিং পারি না|ভিডিও বানাতে কষ্ট|নম্বর ব্যান|ভিউ হয় না|ফলোয়ার বাড়ে না|টাকা নষ্ট|কষ্ট হচ্ছে|এডিটর পাচ্ছি না|সমস্যা|ব্যর্থ)/u', $text)) {
            return self::STAGE_PROBLEM_AWARE;
        }

        // Stage 1: Unaware (Casual greeting, hello, hi, ki koren, just exploring)
        return self::STAGE_UNAWARE;
    }

    /**
     * Choose the optimal Sub-Agent specialist based on user psychology and intent.
     */
    public static function routeToSpecialist(string $input, string $stage, string $requested = 'auto'): string
    {
        if (in_array($requested, [self::AGENT_AYESHA, self::AGENT_NIROB, self::AGENT_TANIA, self::AGENT_DIRECTOR], true)) {
            return $requested;
        }

        $text = mb_strtolower(trim($input));

        // Nirob: Technical Specialist (PC specs, Windows, RAM, GPU, API keys, FFmpeg, Chrome locks, Anti-ban tech)
        if (preg_match('/(কম্পিউটার|ল্যাপটপ|উইন্ডোজ|র‍্যাম|গ্রাফিক্স|কনফিগারেশন|এপিআই|কি|কী|সেটআপ|ইন্সটল|টেকনিক্যাল|বাগ|সমস্যা|সিস্টেম রিকোয়ারমেন্ট|pc|ram|gpu|windows|spec|install|api key)/u', $text)) {
            return self::AGENT_NIROB;
        }

        // Tania: Closer & Deal Negotiator (Price, discount, offers, bKash, comparison, objection handling "pore nibo")
        if ($stage === self::STAGE_MOST_AWARE || preg_match('/(দাম|ডিসকাউন্ট|ছাড়|অফার|কুপন|বিকাশ|নগদ|টাকা|অর্ডার|পরে নিব|পরে যোগাযোগ|বাজেট কম|price|cost|discount|coupon|offer)/u', $text)) {
            return self::AGENT_TANIA;
        }

        // Ayesha: Warm Greeter, Lead Capturer & Consultative Advisor (Welcoming, demos, questions, initial care)
        return self::AGENT_AYESHA;
    }

    /**
     * Construct the Master Persuasion Directive for the LLM.
     */
    public static function buildPersuasionSystemPrompt(
        string $channel,
        string $agentRole,
        string $stage,
        array $context = []
    ): string {
        $agentTitle = 'চিফ মার্কেটিং ও সেলস ডিরেক্টর';
        $agentName = 'AutoMovie Pro Master Marketing Brain';
        if ($agentRole === self::AGENT_AYESHA) {
            $agentName = 'আয়েশা (কাস্টমার ওয়েলকাম ও কনসালটেশন ম্যানেজার)';
            $agentTitle = 'Customer Care & Consultation Specialist';
        } elseif ($agentRole === self::AGENT_NIROB) {
            $agentName = 'নীরব (টেকনিক্যাল আর্কিটেক্ট ও প্রোডাক্ট স্পেশালিস্ট)';
            $agentTitle = 'Technical Solutions & Setup Architect';
        } elseif ($agentRole === self::AGENT_TANIA) {
            $agentName = 'তানিয়া (সেলস স্ট্র্যাটেজি ও পেমেন্ট অনবোর্ডিং লিড)';
            $agentTitle = 'Sales Closer & Onboarding Director';
        }

        $channelDirective = match ($channel) {
            'whatsapp_crm' => "চ্যানেল: WhatsApp Live CRM।\n- মেসেজ হতে হবে পয়েন্ট-টু-পয়েন্ট, অত্যন্ত প্রফেশনাল, মোবাইল ফ্রেন্ডলি ও স্পষ্ট প্যারাগ্রাফে বিভক্ত।\n- অপ্রয়োজনীয় দীর্ঘ ভূমিকা বাদ দিন। কাস্টমারকে স্পেসিফিক ডেমো লিংক বা সিদ্ধান্তমূলক পরবর্তী পদক্ষেপ দিন।",
            'social_media' => "চ্যানেল: Facebook / Social Media Comments।\n- কমেন্ট হবে সংক্ষেপ, কৌতূহলোদ্দীপক এবং সোশ্যাল প্রুফ সমৃদ্ধ।\n- মূল বিস্তারিত ও ফ্রি ডেমো পাঠানোর জন্য কাস্টমারকে ইনবক্স বা হোয়াটসঅ্যাপে (+8801968111593) আসার আমন্ত্রণ জানান।",
            default => "চ্যানেল: Website Live Chat (ওয়েবসাইট লাইভ চ্যাট)।\n- উষ্ণ, আন্তরিক এবং সরাসরি সাহায্যকারী টোনে কথা বলুন।\n- লক্ষ্য: ৩-৪ বাক্যের মধ্যে কাস্টমারের প্রশ্নের উত্তর দেওয়া এবং বিনীতভাবে তার WhatsApp নম্বরটি সংগ্রহ করা যাতে স্পেশাল অফার ও ফাইল পাঠানো যায়।"
        };

        $stageInstruction = match ($stage) {
            self::STAGE_UNAWARE => "কাস্টমার অ্যাওয়ারনেস স্টেজ: UNAWARE (অনবহিত)।\n- হুক (Hook) ব্যবহার করে কৌতূহল তৈরি করুন।\n- প্যাসিভ ইনকাম বা ব্যবসার অটোমেশনের রোমাঞ্চকর ফলাফল তুলে ধরুন।",
            self::STAGE_PROBLEM_AWARE => "কাস্টমার অ্যাওয়ারনেস স্টেজ: PROBLEM AWARE (সমস্যা সচেতন)।\n- ক্রিস ভস-এর ট্যাকটিক্যাল এম্প্যাথি: কাস্টমারের যন্ত্রণা স্বীকার করুন ('আমি বুঝতে পারছি ম্যানুয়ালি প্রতিদিন ভিডিও বানানো বা নম্বর ব্যান হওয়া কতটা হতাশার...')।\n- সমস্যার সমাধান হিসেবে অটোমেশনের প্রয়োজনীয়তা তুলে ধরুন।",
            self::STAGE_SOLUTION_AWARE => "কাস্টমার অ্যাওয়ারনেস স্টেজ: SOLUTION AWARE (সমাধান সচেতন)।\n- রাসেল ব্রানসনের Epiphany Bridge: কীভাবে আমাদের ১-ক্লিক সফটওয়্যার কাজ সহজ করে দেয়।\n- হরমুজির Value Equation: জিরো এডিটিং স্কিল, চোখের পলকে আউটপুট, ১০০% লোকাল পিসি নিরাপত্তা।",
            self::STAGE_PRODUCT_AWARE => "কাস্টমার অ্যাওয়ারনেস স্টেজ: PRODUCT AWARE (পণ্য সচেতন)।\n- সঠিক প্যাকেজ রিকমেন্ডেশন: ভিডিও ক্রিয়েটরদের জন্য ৳৩,৯৯৯ ভিডিও স্টুডিও, ব্যবসায়ীদের জন্য ৳২,৯৯৯ ফেসবুক বিজনেস, এবং হোয়াটসঅ্যাপ মার্কেটিংয়ের জন্য ৳৯৯৯ WAManager Pro।\n- স্পষ্ট তুলনা ও সোশ্যাল প্রুফ (১,২৫০+ অ্যাক্টিভ ইউজার)।",
            self::STAGE_MOST_AWARE => "কাস্টমার অ্যাওয়ারনেস স্টেজ: MOST AWARE (ক্রয় প্রস্তুত)।\n- সিয়ালদিনির Scarcity & Urgency + হরমুজির Grand Slam Guarantee।\n- সরাসরি বিকাশ/নগদ পেমেন্ট প্রক্রিয়া বুঝিয়ে দিন এবং ১০০% ইনস্ট্যান্ট ডেলিভারি ও ফুল রিপ্লেসমেন্ট ওয়ারেন্টির নিশ্চয়তা দিন।"
        };

        return <<<PROMPT
You are {$agentName}, the {$agentTitle} of AutoMovie Pro (https://automoviepro.com).
Your mission is to guide visitors with highest empathy, elite consultative psychology, and convert them into enthusiastic lifelong customers.

{$channelDirective}

{$stageInstruction}

GLOBAL PERSUASION FRAMEWORKS (MANDATORY IN EVERY CONVERSATION):
1. ROBERT CIALDINI (Influence Principles):
   - Social Proof: "ইতিমধ্যে ১,২৫০+ কনটেন্ট ক্রিয়েটর ও ব্যবসায়ী প্রতিদিন আমাদের সফটওয়্যারগুলো ব্যবহার করে সফলভাবে রিচ ও সেলস বাড়াচ্ছেন।"
   - Authority: "সম্পূর্ণ অফিশিয়াল এআই এপিআই সমর্থিত এবং নিজস্ব কম্পিউটারে ১০০% ডেটা সিকিউরিটি।"
   - Scarcity: "আজকের স্পেশাল অফারে ৫০% পর্যন্ত বিশেষ ডিসকাউন্ট এবং আনলিমিটেড লাইসেন্স অ্যাক্টিভেশন প্রযোজ্য।"

2. ALEX HORMOZI ($100M Offers & Lead Nurturing):
   - Dream Outcome: মাসে লক্ষাধিক টাকা প্যাসিভ ইনকাম বা ব্যবসার সেলস ৫ গুণ বৃদ্ধি।
   - Perceived Likelihood: প্রুভেন ১-ক্লিক অটোমেশন এবং ফুল ভিডিও গাইডলাইন।
   - Time Delay: অর্ডার শেষ হওয়ার মাত্র ৫ মিনিটের মধ্যে ফুল ইনস্টলেশন ও রেডি-টু-রান।
   - Effort & Sacrifice: জিরো ভিডিও এডিটিং দক্ষতা, জিরো কোডিং, জিরো টেকনিক্যাল জ্ঞান।

3. CHRIS VOSS (Tactical Empathy):
   - "মনে হচ্ছে আপনি..." (Labeling) দিয়ে কাস্টমারের মনের অনুভূতি প্রকাশ করুন।
   - প্রশ্ন জিজ্ঞাসা করতে 'কেন' বাদ দিয়ে 'কী' বা 'কীভাবে' ব্যবহার করুন (Calibrated Questions: "কীভাবে আপনার কনটেন্ট তৈরির কাজটি সবচেয়ে সহজ করা যায়?").

4. RUSSELL BRUNSON (Hook - Story - Offer):
   - আকর্ষণীয় শুরু -> বাস্তবসম্মত সমাধান -> অতুলনীয় কম্বো অফার ও লাইফটাইম ডিল।

CORE PRODUCTS & OFFICIAL PRICING:
১. AutoMovie Pro - Social Media Content Automation Engine: ৳৩,৯৯৯ (লাইফটাইম ডিল, বেস্টসেলার)
   - ফুল এআই ভিডিও তৈরি + ১৮টি চ্যানেলে অটোমেটিক আপলোড (৬টি YouTube + ৬টি Facebook + ৬টি TikTok)।
২. AutoMovie Pro - FB Business Manager & Ad Automation Engine: ৳২,৯৯৯ (লাইফটাইম ডিল)
   - ই-কমার্স ও শপ ওনারদের জন্য অটো অ্যাড ব্যানার, কাইনেটিক প্রডাক্ট রিলস, গ্রুপ শেয়ারিং ও চ্যাটবট।
৩. AutoMovie Pro - FB Profile & Page Post Automation Engine: ৳১,৯৯৯ (লাইফটাইম ডিল)
   - ব্যক্তিগত প্রোফাইল ও পেজের জন্য হাদিস/কোরআন/অনুপ্রেরণামূলক অটো-পোস্টিং ও অর্গানিক গ্রোথ।
৪. WAManager Pro — Official WhatsApp Marketing & CRM Suite:
   - ১ বছর: মাত্র ৳৯৯৯ | ৩ বছর: মাত্র ৳১,৯৯৯ (রেগুলার ৳৫,৫০০)
   - আনলিমিটেড বাল্ক হোয়াটসঅ্যাপ সেন্ডার, অ্যান্টি-ব্যান স্পিনট্যাক্স, B2B লিড স্ক্র্যাপার, গ্রুপ মেম্বার এক্সট্রাক্টর।
৫. Google Gemini Pro Official Cloud API Subscriptions:
   - ট্রায়াল ১ মাস: ৳১২০ | ১ বছর: ৳৯৯৯ | ১৮ মাস: ৳১,২৯৯ | ৪ বছর: ৳১,৯৯৯

PAYMENT CHANNELS (INSTANT AUTOMATED ACTIVATION):
- bKash Agent (Cash Out): 01756160993 (Zahid Pharmacy)
- Nagad Agent (Cash Out): 01611-824811 (Simi Drug House)
- Rocket Agent: 01756160993-5 | 24/7 Hotline WhatsApp: +8801968111593

OUTPUT FORMAT RULES (STRICT):
1. First, provide your consultative Bengali reply. Keep it natural, authentic, persuasive, and warm.
2. At the end, on a brand-new line, output a single JSON metadata block:
{"selected_agent":"{$agentRole}","awareness_stage":"{$stage}","persuasion_technique":"...","suggestions":["...","..."],"open_whatsapp":false,"coupon_offered":""}
PROMPT;
    }

    /**
     * Master generation dispatch method: Calls LLM with key-rotation failover, or uses smart heuristic fallback.
     */
    public static function process(
        PDO $pdo,
        array $config,
        array $params
    ): array {
        $channel = trim((string) ($params['channel'] ?? 'website_chat'));
        $userMsg = trim((string) ($params['user_message'] ?? ''));
        $history = (array) ($params['conversation_history'] ?? []);
        $leadName = trim((string) ($params['lead_name'] ?? 'সম্মানিত অতিথি'));
        $leadPhone = trim((string) ($params['lead_phone'] ?? ''));
        $requestedAgent = trim((string) ($params['requested_agent'] ?? 'auto'));

        // 1. Detect awareness stage
        $stage = self::detectAwarenessStage($userMsg, $history);

        // 2. Route to specialist persona
        $activeAgent = self::routeToSpecialist($userMsg, $stage, $requestedAgent);

        // 3. Collect LLM keys from environment & site_settings
        $keys = amp_agent_collect_keys($config, $pdo);

        // 4. Build system prompt
        $systemPrompt = self::buildPersuasionSystemPrompt($channel, $activeAgent, $stage, [
            'lead_name' => $leadName,
            'lead_phone' => $leadPhone,
        ]);

        $promptMessages = [];
        $promptMessages[] = ['role' => 'system', 'content' => $systemPrompt];
        foreach (array_slice($history, -6) as $h) {
            $r = is_array($h) ? ($h['role'] ?? 'user') : 'user';
            $c = is_array($h) ? ($h['text'] ?? $h['content'] ?? '') : (string) $h;
            if ($c !== '') {
                $promptMessages[] = ['role' => $r === 'assistant' ? 'assistant' : 'user', 'content' => $c];
            }
        }
        $promptMessages[] = ['role' => 'user', 'content' => $userMsg];

        // 5. Attempt LLM Generation
        $rawOutput = '';
        $usedProvider = 'heuristic_fallback';

        // Try Gemini Pool first
        if (!empty($keys['gemini'])) {
            try {
                $gemKey = $keys['gemini'][array_rand($keys['gemini'])];
                $gemRes = self::callGeminiDirect($gemKey, $systemPrompt, $userMsg, $history);
                if (!empty($gemRes)) {
                    $rawOutput = $gemRes;
                    $usedProvider = 'gemini_pro_pool';
                }
            } catch (\Throwable $e) {}
        }

        // Try Groq / OpenRouter fallback
        if (empty($rawOutput) && (!empty($keys['groq']) || !empty($keys['openrouter']))) {
            try {
                $callRes = amp_agent_call_llm($config, $promptMessages, $keys);
                if (!empty($callRes['content'])) {
                    $rawOutput = $callRes['content'];
                    $usedProvider = $callRes['provider'] ?? 'external_llm';
                }
            } catch (\Throwable $e) {}
        }

        // 6. If LLM unavailable or timed out, invoke Smart Persuasive Heuristic Engine
        if (empty($rawOutput)) {
            $parsed = self::generateHeuristicPersuasion($activeAgent, $stage, $userMsg, $leadName);
            $parsed['meta']['provider'] = 'smart_persuasive_heuristic';
            return $parsed;
        }

        // 7. Parse LLM JSON payload
        $parsed = amp_agent_parse_llm_payload($rawOutput);
        $meta = $parsed['meta'];
        $meta['provider'] = $usedProvider;
        $meta['selected_agent'] = $meta['selected_agent'] ?? $activeAgent;
        $meta['awareness_stage'] = $meta['awareness_stage'] ?? $stage;

        return [
            'reply' => $parsed['reply'],
            'meta' => $meta,
        ];
    }

    /**
     * Direct Gemini 1.5/2.0 API Caller with timeout protection.
     */
    private static function callGeminiDirect(string $apiKey, string $systemPrompt, string $userMsg, array $history): ?string
    {
        $url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=' . urlencode($apiKey);

        $contents = [];
        $contents[] = [
            'role' => 'user',
            'parts' => [['text' => $systemPrompt . "\n\nUser Message: " . $userMsg]]
        ];

        $payload = [
            'contents' => $contents,
            'generationConfig' => [
                'temperature' => 0.65,
                'maxOutputTokens' => 800,
            ]
        ];

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
            CURLOPT_POSTFIELDS => json_encode($payload),
            CURLOPT_TIMEOUT => 8,
            CURLOPT_CONNECTTIMEOUT => 3,
        ]);
        $res = curl_exec($ch);
        $err = curl_error($ch);
        $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($err !== '' || $code < 200 || $code >= 300) {
            return null;
        }

        $data = json_decode((string) $res, true);
        $text = $data['candidates'][0]['content']['parts'][0]['text'] ?? '';
        return trim((string) $text) ?: null;
    }

    /**
     * Smart Heuristic Persuasion Engine — Guaranteed zero-latency, 100% authentic Bengali response.
     */
    public static function generateHeuristicPersuasion(
        string $agent,
        string $stage,
        string $input,
        string $leadName
    ): array {
        $text = mb_strtolower(trim($input));

        // 1. STAGE: MOST AWARE (Ordering, bKash, Payment, Checkout)
        if ($stage === self::STAGE_MOST_AWARE || preg_match('/(অর্ডার|বিকাশ|নগদ|টাকা|পেমেন্ট|payment|bkash)/u', $text)) {
            $reply = "ধন্যবাদ স্যার! অর্ডার সম্পন্ন করা একদম সহজ এবং মাত্র ৫ মিনিটে সম্পূর্ণ প্যাকেজটি সক্রিয় হয়ে যায়।\n\n"
                   . "💳 **পেমেন্ট অপশন (ক্যাশ আউট):**\n"
                   . "• বিকাশ এজেন্ট: `01756160993` (Zahid Pharmacy)\n"
                   . "• নগদ এজেন্ট: `01611-824811` (Simi Drug House)\n"
                   . "• রকেট এজেন্ট: `01756160993-5`\n\n"
                   . "ক্যাশ আউট করার পর ট্রানজেকশন আইডি (TxnID) এবং আপনার ইমেইল দিয়ে নিচের লিংকে অর্ডার কনফার্ম করলেই ইনস্ট্যান্ট ডাউনলোড ও লাইসেন্স পাবেন:\n"
                   . "👉 https://automoviepro.com/order.php\n\n"
                   . "কোনো সহায়তার প্রয়োজন হলে আমাদের অফিশিয়াল হোয়াটসঅ্যাপেও জানাতে পারেন: +8801968111593";
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Most Aware (ক্রয় প্রস্তুত)',
                    'persuasion_technique' => 'Risk Reversal + Frictionless Checkout',
                    'suggestions' => ['অর্ডার লিংক দিন', 'বিকাশ এজেন্ট নম্বর কপি', 'হোয়াটসঅ্যাপে কথা বলব'],
                    'open_whatsapp' => false,
                    'coupon_offered' => 'SPECIAL500'
                ]
            ];
        }

        // 2. STAGE: PRODUCT AWARE & PRICING
        if ($stage === self::STAGE_PRODUCT_AWARE || preg_match('/(দাম|প্যাকেজ|খরচ|price|cost)/u', $text)) {
            $reply = "আমাদের সফটওয়্যারগুলোর অফিশিয়াল প্যাকেজ ও অফার মূল্য:\n\n"
                   . "১. **AutoMovie Pro Video Studio (৳৩,৯৯৯ - লাইফটাইম ডিল)**: ফুল এআই ভিডিও তৈরি ও একসাথে ১৮টি চ্যানেলে অটো আপলোড।\n"
                   . "২. **AutoMovie Pro FB Business Manager (৳২,৯৯৯ - লাইফটাইম ডিল)**: ফেসবুক শপ, অ্যাড ব্যানার, রিলস ও গ্রুপ মার্কেটিং।\n"
                   . "৩. **AutoMovie Pro Profile Post (৳১,৯৯৯ - লাইফটাইম ডিল)**: ইসলামিক/মোটিভেশনাল অটো পোস্ট ও স্টোরি শিডিউলার।\n"
                   . "৪. **WAManager Pro WhatsApp Suite (৳৯৯৯/১ বছর | ৳১,৯৯৯/৩ বছর)**: আনলিমিটেড বাল্ক হোয়াটসঅ্যাপ সেন্ডার ও B2B লিড স্ক্র্যাপার।\n\n"
                   . "স্যার, আপনি কি ভিডিও বানিয়ে প্যাসিভ ইনকাম করতে চাচ্ছেন নাকি ব্যবসার জন্য হোয়াটসঅ্যাপ মার্কেটিং খুঁজছেন?";
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_AYESHA,
                    'awareness_stage' => 'Product Aware (পণ্য সচেতন)',
                    'persuasion_technique' => 'Value Ladder & Targeted Diagnosis',
                    'suggestions' => ['ভিডিও স্টুডিও ডেমো দেখান', 'হোয়াটসঅ্যাপ মার্কেটিং কীভাবে কাজ করে?', 'ডিসকাউন্ট কুপন আছে?'],
                    'open_whatsapp' => false
                ]
            ];
        }

        // 3. TECHNICAL INQUIRIES (PC specs, Windows, RAM, GPU, API keys)
        if ($agent === self::AGENT_NIROB || preg_match('/(পিসি|ল্যাপটপ|কম্পিউটার|র‍্যাম|উইন্ডোজ|গ্রাফিক্স|api|ram|gpu|spec)/u', $text)) {
            $reply = "AutoMovie Pro অত্যন্ত লাইটওয়েট ও অপ্টিমাইজড করে তৈরি করা হয়েছে, তাই যেকোনো সাধারণ কম্পিউটারে অনায়াসে চলে।\n\n"
                   . "💻 **কম্পিউটার রিকোয়ারমেন্ট:**\n"
                   . "• অপারেটিং সিস্টেম: Windows 10 অথবা Windows 11 (64-bit)\n"
                   . "• র‍্যাম: নূন্যতম 4GB (8GB বা তদূর্ধ্ব হলে অত্যন্ত দ্রুত ভিডিও রেন্ডার হয়)\n"
                   . "• গ্রাফিক্স কার্ড: ডেডিকেটেড GPU বাধ্যতামূলক নয় (সাধারণ CPU দিয়েই ফুল ভিডিও তৈরি হয়)\n"
                   . "• ফ্রি স্পেস: মাত্র 5GB ডিস্ক স্পেস\n\n"
                   . "ইনস্টলেশন সম্পূর্ণ ১-ক্লিক পোর্টেবল। আপনার কম্পিউটারে কোনো কোডিং বা অতিরিক্ত সফটওয়্যার সেটআপ করতে হয় না।";
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_NIROB,
                    'awareness_stage' => 'Solution Aware (টেকনিক্যাল যাচাই)',
                    'persuasion_technique' => 'Friction Removal & Technical Certainty',
                    'suggestions' => ['ফ্রি ডেমো ভিডিও দেখান', 'ইনস্টল করতে কতক্ষণ লাগে?', 'কী কী এপিআই দরকার?'],
                    'open_whatsapp' => false
                ]
            ];
        }

        // 4. WHATSAPP MARKETING / WAMANAGER SPECIFIC
        if (preg_match('/(whatsapp|wamanager|হোয়াটসঅ্যাপ|বাল্ক|গ্রুপ|স্ক্র্যাপ)/u', $text)) {
            $reply = "আমাদের **WAManager Pro** হলো বাংলাদেশের সবচেয়ে নিরাপদ ও ফিচার-সমৃদ্ধ হোয়াটসঅ্যাপ মার্কেটিং পাওয়ারহাউজ!\n\n"
                   . "🔥 **মূল ফিচারসমূহ:**\n"
                   . "• **অ্যান্টি-ব্যান হিউম্যান স্পিনট্যাক্স**: মানুষের মতো স্বয়ংক্রিয় বিরতি ও রোটেশনে মেসেজ পাঠায়, ফলে নম্বর শতভাগ নিরাপদ থাকে।\n"
                   . "• **গ্রুপ কন্টাক্ট গ্র্যাবার**: যেকোনো হোয়াটসঅ্যাপ গ্রুপ থেকে ১-ক্লিকে সকল মেম্বারের ফোন নম্বর সংগ্রহ।\n"
                   . "• **নম্বর ফিল্টার ও ভ্যালিডেটর**: ক্যাম্পেইনের আগেই সক্রিয় হোয়াটসঅ্যাপ নম্বর বাছাই করে নেওয়া যায়।\n"
                   . "• **আনলিমিটেড B2B লিড স্ক্র্যাপার**: গুগল ম্যাপস থেকে যেকোনো এলাকা ও ক্যাটাগরির ভেরিফাইড ক্লায়েন্ট নম্বর বের করা।\n\n"
                   . "বর্তমানে স্পেশাল অফারে ১ বছরের ফুল লাইসেন্স মাত্র ৳৯৯৯ এবং ৩ বছরের লাইসেন্স মাত্র ৳১,৯৯৯ (রেগুলার ৳৫,৫০০)।";
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_AYESHA,
                    'awareness_stage' => 'Solution Aware (হোয়াটসঅ্যাপ স্পেশাল)',
                    'persuasion_technique' => 'Feature-Benefit Stacking & Anti-Ban Assurance',
                    'suggestions' => ['গ্রুপ গ্র্যাবার কীভাবে কাজ করে?', 'নম্বর ব্যান হবে না তো?', 'অর্ডার করতে চাই'],
                    'open_whatsapp' => false
                ]
            ];
        }

        // 5. DEFAULT WARM CONSULTATIVE WELCOME
        $reply = "আসসালামু আলাইকুম স্যার! AutoMovie Pro-তে আপনাকে স্বাগতম। আমি আয়েশা, আপনার কনটেন্ট ও মার্কেটিং অ্যাসিস্ট্যান্ট।\n\n"
               . "আমাদের এআই সফটওয়্যারের সাহায্যে আপনি কোনো ভিডিও এডিটিং জানা ছাড়াই মাত্র ১-ক্লিকে ভাইরাল ভিডিও তৈরি করে YouTube, Facebook ও TikTok-এ স্বয়ংক্রিয়ভাবে শিডিউল করতে পারবেন, অথবা WAManager দিয়ে আনলিমিটেড হোয়াটসঅ্যাপ মার্কেটিং পরিচালনা করতে পারবেন।\n\n"
               . "স্যার, আপনি কি সোশ্যাল মিডিয়া কনটেন্ট তৈরি করতে সময় বাঁচাতে চাচ্ছেন, নাকি ব্যবসার সেলস বৃদ্ধি করতে চাচ্ছেন? আপনার মূল উদ্দেশ্য জানালে আমি সঠিক গাইডলাইন দিতে পারব।";
        return [
            'reply' => $reply,
            'meta' => [
                'selected_agent' => self::AGENT_AYESHA,
                'awareness_stage' => 'Unaware / Welcome (উষ্ণ সম্ভাষণ)',
                'persuasion_technique' => 'SPIN Diagnosis & Warm Rapport',
                'suggestions' => ['সফটওয়্যারটির দাম কত?', 'ভিডিও স্টুডিও কীভাবে কাজ করে?', 'হোয়াটসঅ্যাপ মার্কেটিং সফটওয়্যার'],
                'open_whatsapp' => false
            ]
        ];
    }
}
