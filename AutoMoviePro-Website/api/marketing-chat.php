<?php
declare(strict_types=1);
/**
 * Marketing chat — LLM sales agent (per UI language) + WhatsApp order handoff.
 */
require dirname(__DIR__) . '/includes/bootstrap.php';
require_once dirname(__DIR__) . '/includes/agent_llm.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'POST only']);
    exit;
}

$raw = file_get_contents('php://input');
$data = json_decode($raw ?: '{}', true);
if (!is_array($data)) {
    $data = $_POST;
}

$lang = strtolower(substr((string) ($data['lang'] ?? 'bn'), 0, 2));
if (!in_array($lang, amp_cms_langs(), true)) {
    $lang = 'bn';
}
$message = trim((string) ($data['message'] ?? ''));
$action = strtolower(trim((string) ($data['action'] ?? 'chat')));
$history = $data['history'] ?? [];
if (!is_array($history)) {
    $history = [];
}
$draft = is_array($data['draft'] ?? null) ? $data['draft'] : [];

$price = (float) setting($pdo, 'price_amount', '3999');
$addon = (float) setting($pdo, 'language_addon_price', '499');

// Dynamic Admin Chat Agent & Discount Settings
$discountAllowed = setting($pdo, 'agent_discount_allowed', '1') === '1';
$initDiscount = (float) setting($pdo, 'agent_initial_discount_amount', '500');
$maxDiscount = (float) setting($pdo, 'agent_max_discount_amount', '1000');
$cfgCouponCode = strtoupper(trim(setting($pdo, 'agent_coupon_prefix', 'VIP500')) ?: 'VIP500');
$freeAddon = setting($pdo, 'agent_free_addon_lang', '1') === '1';
$validityHours = (int) setting($pdo, 'agent_followup_reminder_hours', '24');
$configuredPersona = setting($pdo, 'agent_primary_persona', 'ayesha');

$agentId = (string) ($data['agent_id'] ?? $configuredPersona);
$agentName = (string) ($data['agent_name'] ?? ($agentId === 'nirob' ? 'নীরব (Nirob)' : ($agentId === 'tania' ? 'তানিয়া (Tania)' : 'আয়েশা (Ayesha)')));
$agentRole = (string) ($data['agent_role'] ?? 'সিনিয়র সেলস ও কাস্টমার কনসালট্যান্ট');

// 1. Detect Phone / WhatsApp number from message
$userPhone = null;
if (preg_match('/(?:\+?8801|01)[3-9]\d{8}/', $message, $phoneMatch)) {
    $rawPhone = preg_replace('/\D+/', '', $phoneMatch[0]);
    if (str_starts_with($rawPhone, '8801')) {
        $userPhone = substr($rawPhone, 2);
    } elseif (str_starts_with($rawPhone, '01')) {
        $userPhone = $rawPhone;
    }
}

// 2. Detect objection "pore" or discount request
$isPoreOrDiscount = (bool) preg_match('/(pore|pore\s*kinbo|pore\s*jogajog|pore\s*janabo|পরে|ডিসকাউন্ট|discount|coupon|offer|কম|কুপন|অফার)/iu', $message);
$couponCode = null;
$checkoutUrl = null;

if ($isPoreOrDiscount && $discountAllowed) {
    $couponCode = $cfgCouponCode;
    try {
        $cpStmt = $pdo->prepare("SELECT id FROM coupons WHERE code = ? LIMIT 1");
        $cpStmt->execute([$couponCode]);
        if (!$cpStmt->fetch()) {
            $pdo->prepare("INSERT INTO coupons (code, discount_amount, discount_percent, min_order_amount, is_active) VALUES (?, ?, 0, 0, 1)")
                ->execute([$couponCode, $initDiscount]);
        }
    } catch (\Throwable $e) {}
    $checkoutUrl = "/order.php?coupon=" . rawurlencode($couponCode);
}

if ($action === 'greet' || $message === '') {
    $greetUser = match ($lang) {
        'en' => "Say a short warm hello as {$agentName}, the AutoMovie Pro sales consultant and ask how you can help (features, pricing, packages, or order).",
        'bn' => "আপনি {$agentName}, AutoMovie Pro টিমের একজন আন্তরিক প্রতিনিধি। অত্যন্ত বিনীতভাবে সালাম দিয়ে নিজের নাম বলুন এবং কাস্টমারকে কীভাবে সাহায্য করতে পারেন (প্যাকেজ, দাম বা অর্ডার) তা জানতে চান।",
        'hi' => 'छोटा सा गर्मजोशी भरा नमस्ते दो और पूछो कैसे मदद कर सकते हो (कीमत, भाषा, चैनल, ऑर्डर)।',
        'ur' => 'مختصر گرم جو شی سے سلام کہو اور پوچھو کیسے مدد کر سکتے ہو (قیمت، زبان، چینل، آرڈر)۔',
        'ta' => 'சுருக்கமான அன்பான வணக்கம் சொல்லி எப்படி உதவலாம் என்று கேள் (விலை, மொழி, சேனல், ஆர்டர்).',
        'ml' => 'ചെറിയ ഊഷ്മള നമസ്കാരം പറഞ്ഞ് എങ്ങനെ സഹായിക്കാമെന്ന് ചോദിക്കൂ (വില, ഭാഷ, ചാനൽ, ഓർഡർ).',
        default => 'Greet briefly and offer help.',
    };
    $message = $greetUser;
}

$system = amp_agent_system_prompt($lang, $price, $addon, $agentName, $agentRole, $pdo);
$messages = [];
foreach (array_slice($history, -8) as $h) {
    if (!is_array($h)) {
        continue;
    }
    $role = (($h['role'] ?? '') === 'assistant' || ($h['role'] ?? '') === 'bot') ? 'assistant' : 'user';
    $content = trim((string) ($h['content'] ?? ''));
    if ($content !== '') {
        $messages[] = ['role' => $role, 'content' => $content];
    }
}
$messages[] = ['role' => 'user', 'content' => $message];

$llm = amp_agent_chat_llm($config, $system, $messages, $pdo);

// SMART INTENT-BASED FALLBACK (Guarantees zero repetitive robotic loops)
if ($llm === null || $llm === '') {
    $msgLower = strtolower($message);
    $reply = '';
    $suggestions = [];

    if ($action === 'greet' || $message === '') {
        $reply = "আসসালামু আলাইকুম! আমি {$agentName}, AutoMovie Pro টিম থেকে বলছি।\nআমাদের ৩টি বাণিজ্যিক প্যাকেজ, এআই ভিডিও ফিচার বা অর্ডার সম্পর্কে আপনার যেকোনো প্রশ্ন থাকলে বলুন, আমি বুঝিয়ে দিচ্ছি।";
        $suggestions = ['৩টি সফটওয়্যার প্যাকেজের পার্থক্য কি?', 'দাম কত ও কিভাবে কিনব?', 'সরাসরি WhatsApp-এ কথা বলুন'];
    } elseif ($userPhone) {
        $reply = "অনেক ধন্যবাদ স্যার! আপনার WhatsApp নম্বরটি ({$userPhone}) সফলভাবে সেভ করা হয়েছে। আমাদের সিনিয়র টিম থেকে এখনই আপনার WhatsApp-এ সফটওয়্যারটির লাইভ ফুল ভিডিও ডেমো এবং স্পেশাল ইনস্টলেশন ভাউচার পাঠিয়ে দেওয়া হচ্ছে। 😊\n\nআপনি কি এখনই লাইসেন্স অর্ডার করতে আগ্রহী?";
        $suggestions = ['হ্যাঁ, এখনই অর্ডার করতে চাই', 'প্যাকেজের মূল্য কত?'];
    } elseif (preg_match('/(kothay thako|kothay bash|ki khao|biye|boyos|tumi ke|apni ke|prem|valo laglo|personal|বিয়ে|বয়স|কই থাক|কোথায় থাক|কি খাও|তুমি কে|আপনি কে|বাড়ি কই|বাসা কই)/iu', $msgLower)) {
        $reply = "আমাদের এই চ্যাটিং কর্তৃপক্ষ কর্তৃক সার্বক্ষণিক মনিটর করা হচ্ছে। তাই অনাকাঙ্ক্ষিত বা ব্যক্তিগত কোনো প্রশ্ন না করে, আপনি আমাদের AutoMovie Pro সফটওয়্যার, ফিচার, প্যাকেজ বা অর্ডার সংক্রান্ত যেকোনো প্রশ্ন করুন — আমি আনন্দের সাথে সাহায্য করছি। 😊";
        $suggestions = ['৩টি সফটওয়্যার প্যাকেজের পার্থক্য কি?', 'দাম কত?', 'সরাসরি WhatsApp-এ কথা বলুন'];
    } elseif (preg_match('/(koyta|software|softower|package|প্যাকেজ|কয়টা|সফটওয়্যার|software)/iu', $msgLower)) {
        $reply = "জি ভাইয়া! আমাদের মোট ৩টি টার্নকি সফটওয়্যার ইঞ্জিন রয়েছে:\n\n১. Automovie Pro - Social Media Content Automation Engine (৳৩,৯৯৯) [বেস্ট চয়েস]: সম্পূর্ণ এআই ভিডিও বানায় এবং একসাথে ১৮টি চ্যানেলে (ইউটিউব, ফেসবুক ও টিকটক) অটোমেটিক পাবলিশ করে।\n২. Automovie Pro - FB Business Manager & Ad Automation Engine (৳২,৯৯৯): ফেসবুক বিজ্ঞাপন ও সেলস ব্যানার তৈরির জন্য।\n৩. Automovie Pro - FB Profile & Page Post Automation Engine (৳১,৯৯৯): পার্সোনাল ফেসবুক আইডি ও পেজে অটোমেটিক পোস্ট দেওয়ার জন্য।\n\nআপনি কোন কাজের জন্য সফটওয়্যার খুঁজছেন ভাইয়া?";
        $suggestions = ['ভিডিও স্টুডিও প্যাকেজ নিতে চাই', 'দাম কত?', 'বিকাশে পেমেন্ট করব'];
    } elseif (preg_match('/(dam|koto|price|টাকা|মূল্য|দাম)/iu', $msgLower)) {
        $reply = "জি ভাইয়া! AutoMovie Pro সম্পূর্ণ ওয়ান-টাইম পেমেন্ট, কোনো গোপন মাসিক ফি নেই। 👍\n\n• Social Media Content Automation Engine: মাত্র ৳৩,৯৯৯\n• FB Business Manager & Ad Automation Engine: মাত্র ৳২,৯৯৯\n• FB Profile & Page Post Automation Engine: মাত্র ৳১,৯৯৯\n\nআজকে অর্ডার করলে পাবেন ইনস্ট্যান্ট সফটওয়্যার ডাউনলোড, লাইসেন্স কি এবং ফ্রি লাইফটাইম আপডেট। আপনি কোনটি নিতে চাচ্ছেন?";
        $suggestions = ['৩,৯৯৯ টাকার প্যাকেজ নেব', 'বিকাশ নম্বর দিন', 'পরে যোগাযোগ করব'];
    } elseif ($isPoreOrDiscount) {
        if ($discountAllowed) {
            $reply = "অবশ্যই স্যার! কোনো সমস্যা নেই। আপনি কখন ফ্রি থাকবেন—আজ সন্ধ্যায় নাকি আগামীকাল দুপুরে? যাতে আপনাকে সুন্দরভাবে রিমাইন্ডার দিতে পারি। ✨\n\nআর স্যার, যেহেতু আজ আপনি আমাদের সাথে যোগাযোগ করলেন, আপনার জন্য স্পেশাল একটি সিক্রেট ডিসকাউন্ট কুপন কোড [{$cfgCouponCode}] এক্টিভ করে দিয়েছি। এটি দিয়ে আগামী {$validityHours} ঘণ্টার মধ্যে অর্ডার করলে সরাসরি ৳" . (int)$initDiscount . " নগদ ছাড় পাবেন" . ($freeAddon ? " এবং সাথে ১টি অতিরিক্ত আন্তর্জাতিক ভাষা (মূল্য ৳" . (int)$addon . ") আজীবন ফ্রি পাবেন!" : "!");
            $suggestions = ['কুপন দিয়ে এখনই অর্ডার করব', 'WhatsApp এ বিস্তারিত পাঠান'];
            $checkoutUrl = "/order.php?coupon=" . rawurlencode($cfgCouponCode);
        } else {
            $reply = "অবশ্যই স্যার! কোনো সমস্যা নেই। আপনি সময় নিয়ে বিবেচনা করুন। আমাদের প্যাকেজগুলোতে কোনো মাসিক ফি নেই এবং এটি ওয়ান-টাইম লাইফটাইম লাইসেন্স। যেকোনো সময় যেকোনো প্রশ্ন থাকলে সরাসরি আমাকে জানাতে পারেন। 😊";
            $suggestions = ['প্যাকেজের ফিচার বিস্তারিত বলুন', 'ভিডিও ডেমো দেখতে চাই', 'সরাসরি WhatsApp-এ কথা বলুন'];
            $checkoutUrl = null;
        }
    } else {
        $reply = "জি ভাইয়া, আমি বুঝতে পেরেছি। AutoMovie Pro দিয়ে কোনো কোডিং বা ভিডিও এডিটিং ছাড়া সম্পূর্ণ কম্পিউটার নিজে নিজে স্ক্রিপ্ট, ভয়েস, সিনেমাটিক সিন ও সাবটাইটেল তৈরি করে সোশ্যাল মিডিয়ায় অটো আপলোড করতে পারে। 🚀\n\nআপনি কি সফটওয়্যারটির লাইভ ভিডিও ডেমো দেখতে চান, নাকি সরাসরি ৩,৯৯৯ টাকার লাইফটাইম প্যাকেজটি নিতে চাচ্ছেন?";
        $suggestions = ['লাইভ ভিডিও ডেমো দেখতে চাই', '৩টি প্যাকেজের পার্থক্য বলুন', 'অর্ডার করতে চাই'];
    }

    $fallbackOut = [
        'ok' => true,
        'reply' => $reply,
        'draft' => $draft,
        'suggestions' => $suggestions,
        'checkout_url' => $checkoutUrl,
        'mode' => 'smart_fallback',
    ];

    try {
        $cIp = client_ip();
        $sessId = (string) ($data['session_id'] ?? bin2hex(random_bytes(8)));
        $isWaLead = $userPhone ? 1 : 0;
        $logStmt = $pdo->prepare(
            "INSERT INTO customer_chat_logs (session_id, customer_ip, lang, agent_id, agent_name, user_message, bot_reply, whatsapp_handoff) 
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        );
        $logStmt->execute([
            $sessId,
            $cIp,
            $lang,
            $agentId,
            $agentName,
            $action === 'greet' ? '[স্বাগত সম্ভাষণ]' : $message,
            $reply,
            $isWaLead
        ]);
        if ($userPhone) {
            whatsapp_save_lead(
                $pdo,
                $userPhone,
                $draft['name'] ?? 'ওয়েবসাইট চ্যাট ভিজিটর',
                'chat',
                $draft['package'] ?? 'video_studio',
                'চ্যাট এজেন্টের সাথে কথা বলে নম্বর দিয়েছেন',
                $message
            );
            if (setting($pdo, 'agent_auto_queue_whatsapp_welcome', '1') === '1') {
                $waMsg = "আসসালামু আলাইকুম স্যার! AutoMovie Pro টিম থেকে বলছি। ওয়েবসাইটে আপনার সাথে কথা হয়েছিল। সফটওয়্যারটির লাইভ ফুল ভিডিও ডেমো ও ইনস্টলেশন গাইড দেখতে পারেন: https://automoviepro.com/#features \n\nআপনার যেকোনো প্রশ্ন থাকলে সরাসরি এখানেও জানাতে পারেন।";
                whatsapp_queue($pdo, $config, '88' . $userPhone, $waMsg, null);
            }
        }
    } catch (\Throwable $e) {}

    echo json_encode($fallbackOut, JSON_UNESCAPED_UNICODE);
    exit;
}

$parsed = amp_agent_parse_llm_payload($llm);
$meta = $parsed['meta'];
$newDraft = array_merge($draft, is_array($meta['draft'] ?? null) ? $meta['draft'] : []);

if (!empty($meta['coupon_offered']) && $discountAllowed) {
    $couponCode = strtoupper($meta['coupon_offered']);
    try {
        $cpStmt = $pdo->prepare("SELECT id FROM coupons WHERE code = ? LIMIT 1");
        $cpStmt->execute([$couponCode]);
        if (!$cpStmt->fetch()) {
            $pdo->prepare("INSERT INTO coupons (code, discount_amount, discount_percent, min_order_amount, is_active) VALUES (?, ?, 0, 0, 1)")
                ->execute([$couponCode, $initDiscount]);
        }
    } catch (\Throwable $e) {}
    $checkoutUrl = "/order.php?coupon=" . rawurlencode($couponCode);
}

$out = [
    'ok' => true,
    'reply' => $parsed['reply'],
    'draft' => $newDraft,
    'suggestions' => $meta['suggestions'] ?: [],
    'checkout_url' => $checkoutUrl,
    'mode' => 'llm',
];

$isWaHandoff = 0;
if (!empty($meta['open_whatsapp']) || trim((string) ($meta['wa_prefill'] ?? '')) !== '') {
    $prefill = trim((string) ($meta['wa_prefill'] ?? ''));
    if ($prefill === '') {
        $prefill = 'AutoMovie Pro order from website chat';
    }
    $out['whatsapp_url'] = amp_whatsapp_sales_link($prefill);
    $out['open_whatsapp'] = !empty($meta['open_whatsapp']);
    $isWaHandoff = 1;
}

try {
    $cIp = client_ip();
    $sessId = (string) ($data['session_id'] ?? bin2hex(random_bytes(8)));
    $isWaLead = ($userPhone || $isWaHandoff) ? 1 : 0;
    $logStmt = $pdo->prepare(
        "INSERT INTO customer_chat_logs (session_id, customer_ip, lang, agent_id, agent_name, user_message, bot_reply, whatsapp_handoff) 
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    );
    $logStmt->execute([
        $sessId,
        $cIp,
        $lang,
        $agentId,
        $agentName,
        $action === 'greet' ? '[স্বাগত সম্ভাষণ]' : $message,
        $parsed['reply'],
        $isWaLead
    ]);
    if ($userPhone) {
        whatsapp_save_lead(
            $pdo,
            $userPhone,
            $draft['name'] ?? 'ওয়েবসাইট চ্যাট ভিজিটর',
            'chat',
            $draft['package'] ?? 'video_studio',
            'চ্যাট এজেন্টের সাথে কথা বলে নম্বর দিয়েছেন',
            $message
        );
        if (setting($pdo, 'agent_auto_queue_whatsapp_welcome', '1') === '1') {
            $waMsg = "আসসালামু আলাইকুম স্যার! AutoMovie Pro টিম থেকে বলছি। ওয়েবসাইটে আপনার সাথে কথা হয়েছিল। সফটওয়্যারটির লাইভ ফুল ভিডিও ডেমো ও ইনস্টলেশন গাইড দেখতে পারেন: https://automoviepro.com/#features \n\nআপনার যেকোনো প্রশ্ন থাকলে সরাসরি এখানেও জানাতে পারেন।";
            whatsapp_queue($pdo, $config, '88' . $userPhone, $waMsg, null);
        }
    }
} catch (\Throwable $e) {}

echo json_encode($out, JSON_UNESCAPED_UNICODE);
