<?php
declare(strict_types=1);
/**
 * Marketing chat — Multi-agent sales consultant with persistent visitor recognition,
 * sticky agent recall, past choice memory, decision guidance, and WhatsApp order handoff.
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

// ---------------------------------------------------------------------------
// 1. Persistent Visitor Detection & Recall via Browser / Cookie
// ---------------------------------------------------------------------------
$visitorId = trim((string) ($data['visitor_id'] ?? ($_COOKIE['amp_vid'] ?? '')));
if ($visitorId === '') {
    $visitorId = 'vid_' . bin2hex(random_bytes(10)) . '_' . time();
}

// Ensure 365-day persistent browser cookie
if (empty($_COOKIE['amp_vid']) || $_COOKIE['amp_vid'] !== $visitorId) {
    @setcookie('amp_vid', $visitorId, [
        'expires' => time() + 31536000,
        'path' => '/',
        'httponly' => false,
        'samesite' => 'Lax'
    ]);
}

$cIp = client_ip();
$isReturning = false;
$visitorProfile = null;
$pastLogs = [];

try {
    // A. Direct lookup by visitor_id in visitor profiles
    $profStmt = $pdo->prepare("SELECT * FROM customer_visitor_profiles WHERE visitor_id = ? LIMIT 1");
    $profStmt->execute([$visitorId]);
    $visitorProfile = $profStmt->fetch();

    // B. IP fallback within 7 days if fresh browser profile
    if (!$visitorProfile && $cIp) {
        $ipStmt = $pdo->prepare("SELECT visitor_id FROM customer_chat_logs WHERE customer_ip = ? AND visitor_id IS NOT NULL ORDER BY id DESC LIMIT 1");
        $ipStmt->execute([$cIp]);
        $foundVid = $ipStmt->fetchColumn();
        if ($foundVid) {
            $profStmt = $pdo->prepare("SELECT * FROM customer_visitor_profiles WHERE visitor_id = ? LIMIT 1");
            $profStmt->execute([$foundVid]);
            $visitorProfile = $profStmt->fetch();
            if ($visitorProfile) {
                $visitorId = (string) $foundVid;
            }
        }
    }

    // C. Retrieve past chat logs for conversational memory
    $logsStmt = $pdo->prepare("SELECT user_message, bot_reply, agent_id, agent_name, chosen_package, created_at FROM customer_chat_logs WHERE visitor_id = ? ORDER BY id DESC LIMIT 8");
    $logsStmt->execute([$visitorId]);
    $pastLogs = array_reverse($logsStmt->fetchAll() ?: []);
} catch (\Throwable $e) {}

if ($visitorProfile || !empty($pastLogs) || !empty($data['is_returning'])) {
    $isReturning = true;
}

// ---------------------------------------------------------------------------
// 2. Strict Sticky Agent Pinning (Requirement: Always connect to same agent)
// ---------------------------------------------------------------------------
$agentId = (string) ($data['agent_id'] ?? $configuredPersona);
if ($isReturning) {
    if (!empty($visitorProfile['assigned_agent_id'])) {
        $agentId = $visitorProfile['assigned_agent_id'];
    } elseif (!empty($pastLogs)) {
        foreach (array_reverse($pastLogs) as $pl) {
            if (!empty($pl['agent_id'])) {
                $agentId = $pl['agent_id'];
                break;
            }
        }
    }
}
$agentName = $agentId === 'nirob' ? 'নীরব (Nirob)' : ($agentId === 'tania' ? 'তানিয়া (Tania)' : 'আয়েশা (Ayesha)');
$agentRole = $agentId === 'nirob' ? 'টেকনিক্যাল ও প্রোডাক্ট স্পেশালিস্ট' : ($agentId === 'tania' ? 'অনবোর্ডিং ও লাইসেন্স ম্যানেজার' : 'সিনিয়র সেলস ও কাস্টমার কনসালট্যান্ট');

// ---------------------------------------------------------------------------
// 3. Past Choices & Preferences Extraction
// ---------------------------------------------------------------------------
$pastPackage = $visitorProfile['last_interested_package'] ?? null;
if (!$pastPackage && !empty($pastLogs)) {
    foreach (array_reverse($pastLogs) as $pl) {
        $blob = ($pl['user_message'] ?? '') . ' ' . ($pl['bot_reply'] ?? '') . ' ' . ($pl['chosen_package'] ?? '');
        if (preg_match('/(3999|৩,৯৯৯|ভিডিও|video_studio)/iu', $blob)) {
            $pastPackage = 'video_studio';
            break;
        } elseif (preg_match('/(2999|২,৯৯৯|বিজনেস|business|fb_business)/iu', $blob)) {
            $pastPackage = 'fb_business';
            break;
        } elseif (preg_match('/(1999|১,৯৯৯|প্রোফাইল|profile_page)/iu', $blob)) {
            $pastPackage = 'profile_page';
            break;
        } elseif (preg_match('/(wamanager|wa_marketing|whatsapp|হোয়াটসঅ্যাপ|হোয়াটসঅ্যাপ|বাল্ক|999|৯৯৯)/iu', $blob)) {
            $pastPackage = 'wa_marketing';
            break;
        }
    }
}

$pastPkgLabel = match ($pastPackage) {
    'video_studio' => '৩,৯৯৯ টাকার ফুল ভিডিও অটোমেশন স্টুডিও প্যাকেজ',
    'fb_business' => '২,৯৯৯ টাকার ফেসবুক বিজনেস ও অ্যাড অটোমেশন প্যাকেজ',
    'profile_page' => '১,৯৯৯ টাকার ফেসবুক প্রোফাইল ও পেজ অটো পাইলট প্যাকেজ',
    'wa_marketing' => 'WAManager Pro হোয়াটসঅ্যাপ মার্কেটিং সফটওয়্যার (৳৯৯৯/৳১,৯৯৯)',
    default => 'AutoMovie Pro সফটওয়্যার প্যাকেজ'
};

$pastTopic = $visitorProfile['conversation_summary'] ?? '';
if (!$pastTopic && !empty($pastLogs)) {
    $lastUserMsg = '';
    foreach (array_reverse($pastLogs) as $pl) {
        if (!empty($pl['user_message']) && $pl['user_message'] !== '[স্বাগত সম্ভাষণ]') {
            $lastUserMsg = $pl['user_message'];
            break;
        }
    }
    if ($lastUserMsg) {
        $pastTopic = "পূর্বে আলোচনা করেছিলেন: \"" . mb_substr($lastUserMsg, 0, 75) . "\"";
    }
}

$pastObjection = $visitorProfile['last_objection'] ?? '';
$clientVisitCount = (int) ($data['visit_count'] ?? 0);
$serverVisitCount = (int) ($visitorProfile['visit_count'] ?? 0);
if ($isReturning) {
    $visitCount = max(2, $clientVisitCount, $serverVisitCount + 1);
} else {
    $visitCount = 1;
}

$ordinalMap = [
    1 => 'প্রথমবার',
    2 => 'দ্বিতীয়বার',
    3 => 'তৃতীয়বার',
    4 => 'চতুর্থবার',
    5 => 'পঞ্চমবার',
    6 => 'ষষ্ঠবার',
    7 => 'সপ্তমবার',
    8 => 'অষ্টমবার',
    9 => 'নবমবার',
    10 => 'দশমবার',
];
$visitOrdinal = $ordinalMap[$visitCount] ?? ($visitCount . 'তম বার');

$returningContext = [
    'is_returning' => $isReturning,
    'visit_count' => $visitCount,
    'visit_ordinal' => $visitOrdinal,
    'past_package' => $pastPackage,
    'past_package_label' => $pastPkgLabel,
    'past_topic' => $pastTopic,
    'past_objection' => $pastObjection,
    'summary' => $visitorProfile['conversation_summary'] ?? '',
    'name' => $visitorProfile['customer_name'] ?? '',
];

// ---------------------------------------------------------------------------
// 4. Intent & Objection Detection (Current Message)
// ---------------------------------------------------------------------------
$userPhone = null;
if (preg_match('/(?:\+?8801|01)[3-9]\d{8}/', $message, $phoneMatch)) {
    $rawPhone = preg_replace('/\D+/', '', $phoneMatch[0]);
    if (str_starts_with($rawPhone, '8801')) {
        $userPhone = substr($rawPhone, 2);
    } elseif (str_starts_with($rawPhone, '01')) {
        $userPhone = $rawPhone;
    }
}

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

// ---------------------------------------------------------------------------
// 5. Greeting Formulation (New Visitor vs Returning Visitor)
// ---------------------------------------------------------------------------
if ($action === 'greet' || $message === '') {
    if ($isReturning) {
        $greetUser = "You are {$agentName}. The customer has RETURNED to our website for their {$visitOrdinal} visit (Visit #{$visitCount})!
        MANDATORY GREETING FORMULA:
        Greet them respectfully addressing them as 'স্যার' and explicitly welcoming them for their {$visitOrdinal} visit in Bengali:
        'আসসালামু আলাইকুম স্যার! আপনাকে {$visitOrdinal} আমাদের ওয়েবসাইটে আন্তরিক স্বাগতম। আপনি তো এর আগেও কিছু বিষয় আমাদের এখানে জানতে চেয়েছিলেন। আজ নতুন আর কী বিষয়ে আপনাকে সহযোগিতা করতে পারি স্যার? আমাকে বলুন, আমি একদম সহজে বুঝিয়ে বলছি। 😊'
        (If you remember they discussed {$pastPkgLabel}, you can warmly acknowledge: 'আপনি তো এর আগেও আমাদের {$pastPkgLabel} নিয়ে কিছু বিষয় জানতে চেয়েছিলেন। আজ নতুন আর কী বিষয়ে আপনাকে সহযোগিতা করতে পারি স্যার? আমাকে বলুন, আমি একদম সহজে বুঝিয়ে বলছি। 😊').
        Keep it warm, polite, and human. Do not sound like a robot. Do not re-introduce yourself like a stranger.";
    } else {
        $greetUser = match ($lang) {
            'en' => "Say a short warm hello as {$agentName}, the AutoMovie Pro sales consultant and ask how you can help (features, pricing, packages, or order). Always address the customer respectfully as Sir.",
            'bn' => "আপনি {$agentName}, AutoMovie Pro টিমের একজন আন্তরিক প্রতিনিধি। অত্যন্ত সংক্ষেপে 'আসসালামু আলাইকুম স্যার, আমি AutoMoviePro টিম থেকে {$agentName} বলছি, আপনাকে কীভাবে সহযোগিতা করতে পারি?' বলুন। কোনো অতিরিক্ত লম্বা কথা বলবেন না।",
            'hi' => 'छोटा सा गर्मजोशी भरा नमस्ते दो और पूछो कैसे मदद कर सकते हो सर।',
            'ur' => 'مختصر گرم جو شی سے سلام کہو اور پوچھো کیسے مدد কর سکتے ہو سر।',
            'ta' => 'சுருக்கமான அன்பான வணக்கம் சொல்லி எப்படி உதவலாம் என்று கேள்.',
            'ml' => 'ചെറിയ ഊഷ്മള നമസ്കാരം പറഞ്ഞ് എങ്ങനെ സഹായിക്കാമെന്ന് ചോദിക്കൂ.',
            default => 'Greet briefly and offer help to Sir.',
        };
    }
    $message = $greetUser;
}

$system = amp_agent_system_prompt($lang, $price, $addon, $agentName, $agentRole, $pdo, $returningContext);
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

// ---------------------------------------------------------------------------
// 6. Intelligent Fallback with Returning Memory (Guarantees zero downtime)
// ---------------------------------------------------------------------------
if ($llm === null || $llm === '') {
    $msgLower = strtolower($message);
    $reply = '';
    $suggestions = [];

    if ($action === 'greet' || $message === '') {
        if ($isReturning) {
            if ($pastPackage === 'video_studio') {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে {$visitOrdinal} আমাদের ওয়েবসাইটে আন্তরিক স্বাগতম। আপনি তো এর আগেও আমাদের ৩,৯৯৯ টাকার ভিডিও অটোমেশন স্টুডিও প্যাকেজটি নিয়ে কিছু বিষয় জানতে চেয়েছিলেন। আজ নতুন আর কী বিষয়ে আপনাকে সহযোগিতা করতে পারি স্যার? আমাকে বলুন, আমি একদম সহজে বুঝিয়ে বলছি। 😊";
                $suggestions = ['৩,৯৯৯ টাকার প্যাকেজটি অর্ডার করব', '৳৫০০ ডিসকাউন্ট কুপন দিন', 'সরাসরি WhatsApp-এ কথা বলব'];
            } elseif ($pastPackage === 'fb_business') {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে {$visitOrdinal} আমাদের ওয়েবসাইটে আন্তরিক স্বাগতম। আপনি তো এর আগেও আমাদের ২,৯৯৯ টাকার ফেসবুক বিজনেস ও অ্যাড অটোমেশন নিয়ে কিছু বিষয় জানতে চেয়েছিলেন। আজ নতুন আর কী বিষয়ে আপনাকে সহযোগিতা করতে পারি স্যার? আমাকে বলুন, আমি একদম সহজে বুঝিয়ে বলছি। 😊";
                $suggestions = ['২,৯৯৯ টাকার প্যাকেজ অর্ডার করব', 'ভিডিও ডেমো দেখতে চাই', 'বিকাশে পেমেন্ট করব'];
            } elseif ($pastPackage === 'profile_page') {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে {$visitOrdinal} আমাদের ওয়েবসাইটে আন্তরিক স্বাগতম। আপনি তো এর আগেও আমাদের ১,৯৯৯ টাকার ফেসবুক প্রোফাইল ও পেজ অটো পাইলট প্যাকেজ নিয়ে কিছু বিষয় জানতে চেয়েছিলেন। আজ নতুন আর কী বিষয়ে আপনাকে সহযোগিতা করতে পারি স্যার? আমাকে বলুন, আমি একদম সহজে বুঝিয়ে বলছি। 😊";
                $suggestions = ['১,৯৯৯ টাকার প্যাকেজ অর্ডার করব', 'পেমেন্ট নম্বর দিন', 'অন্য প্যাকেজ সম্পর্কে বলুন'];
            } elseif ($pastPackage === 'wa_marketing') {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে {$visitOrdinal} আমাদের ওয়েবসাইটে আন্তরিক স্বাগতম। আপনি তো এর আগেও আমাদের WAManager Pro হোয়াটসঅ্যাপ মার্কেটিং সফটওয়্যারটি নিয়ে কিছু বিষয় জানতে চেয়েছিলেন। আজ নতুন আর কী বিষয়ে আপনাকে সহযোগিতা করতে পারি স্যার? আমাকে বলুন, আমি একদম সহজে বুঝিয়ে বলছি। 😊";
                $suggestions = ['৯৯৯ টাকার ১ বছর সাবস্ক্রিপশন নেব', '১৯৯৯ টাকার ৩ বছর সাবস্ক্রিপশন নেব', 'সরাসরি WhatsApp-এ কথা বলব'];
            } else {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে {$visitOrdinal} আমাদের ওয়েবসাইটে আন্তরিক স্বাগতম। আপনি তো এর আগেও কিছু বিষয় আমাদের এখানে জানতে চেয়েছিলেন। আজ নতুন আর কী বিষয়ে আপনাকে সহযোগিতা করতে পারি স্যার? আমাকে বলুন, আমি একদম সহজে বুঝিয়ে বলছি। 😊";
                $suggestions = ['৪টি সফটওয়্যারের পার্থক্য বলুন', '৩,৯৯৯ টাকার ভিডিও প্যাকেজ নেব', 'সরাসরি WhatsApp-এ কথা বলব'];
            }
        } else {
            $reply = "আসসালামু আলাইকুম স্যার, আমি AutoMoviePro টিম থেকে {$agentName} বলছি, আপনাকে কীভাবে সহযোগিতা করতে পারি?";
            $suggestions = ['প্যাকেজগুলোর দাম কত?', 'ভিডিও কীভাবে তৈরি করে?', 'WhatsApp মার্কেটিং সফটওয়্যার আছে?'];
        }
    } elseif ($userPhone) {
        $reply = "অনেক ধন্যবাদ স্যার! আপনার WhatsApp নম্বরটি ({$userPhone}) আমাদের ভিআইপি ডিরেক্টরিতে সেভ করা হয়েছে এবং আমাদের কনসালট্যান্ট টিম থেকে এখনই সম্পূর্ণ ভিডিও ডেমো ও ইনস্টলেশন গাইডলাইন পাঠিয়ে দেওয়া হচ্ছে। 😊\n\nস্যার, আপনি মূলত কোন কাজের জন্য সফটওয়্যার খুঁজছেন — ইউটিউব/ফেসবুক থেকে ভিডিও বানিয়ে ইনকাম (৳৩,৯৯৯), ফেসবুক বিজনেস ও সেলস অটোমেশন (৳২,৯৯৯), নাকি আনলিমিটেড হোয়াটসঅ্যাপ মার্কেটিং (৳৯৯৯)? আমাকে বলুন, আমি আপনাকে সেরা প্যাকেজটি বেছে নিতে সাহায্য করছি।";
        $suggestions = ['৩,৯৯৯ টাকার ভিডিও প্যাকেজ নেব', '৯৯৯ টাকার WhatsApp প্যাকেজ নেব', '২,৯৯৯ টাকার বিজনেস প্যাকেজ নেব', '৳৫০০ ডিসকাউন্ট কুপন দিন'];
    } elseif (preg_match('/(apnar nam|tomar nam|nam ki|nam kii|naam ki|who are you|who is this|ke bolchen|ke apni|tumi k|apni k|নাম কি|নাম কী|কে বলছেন|আপনার নাম|তোমার নাম)/iu', $msgLower)) {
        $reply = "জি স্যার, আমার নাম {$agentName}। আমি AutoMovie Pro টিম থেকে বলছি। আপনাকে কীভাবে সহযোগিতা করতে পারি স্যার?";
        $suggestions = ['প্যাকেজগুলোর দাম কত?', 'সফটওয়্যার কীভাবে কাজ করে?', 'সরাসরি WhatsApp-এ কথা বলব'];
    } elseif (preg_match('/(kothay thako|kothay bash|ki khao|biye|boyos|prem|valo laglo|personal|বিয়ে|বয়স|কই থাক|কোথায় থাক|কি খাও|বাড়ি কই|বাসা কই)/iu', $msgLower)) {
        $reply = "আমাদের এই চ্যাটিং কর্তৃপক্ষ কর্তৃক মনিটর করা হচ্ছে স্যার। আপনি আমাদের AutoMovie Pro সফটওয়্যার, ফিচার বা অফার সংক্রান্ত যেকোনো প্রশ্ন করুন — আমি আনন্দের সাথে সাহায্য করছি। 😊";
        $suggestions = ['৪টি সফটওয়্যারের দাম কত?', 'সফটওয়্যার কীভাবে কাজ করে?', 'সরাসরি WhatsApp-এ কথা বলুন'];
    } elseif (preg_match('/(whatsapp|wa|wamanager|bulk|lead scraper|হোয়াটসঅ্যাপ|হোয়াটসঅ্যাপ|বাল্ক|লিড স্ক্র্যাপার)/iu', $msgLower)) {
        $reply = "জি স্যার! WAManager Pro হলো আমাদের আধুনিক WhatsApp Marketing & CRM Suite। 🚀\n\n• ১ বছরের সাবস্ক্রিপশন: মাত্র ৳৯৯৯\n• ৩ বছরের সাবস্ক্রিপশন: মাত্র ৳১,৯৯৯ (সবচেয়ে জনপ্রিয় ডিল)\n\nপ্রধান ফিচারসমূহ:\n✓ আনলিমিটেড বাল্ক হোয়াটসঅ্যাপ মেসেজিং ও অ্যান্টি-ব্যান সুরক্ষা\n✓ Google Maps ও ওয়েবসাইট থেকে আনলিমিটেড ভেরিফাইড B2B লিড স্ক্র্যাপার\n✓ যেকোনো হোয়াটসঅ্যাপ গ্রুপ থেকে মেম্বারদের ফোন নম্বর এক্সট্রাক্টর\n✓ এআই ও কিওয়ার্ডভিত্তিক অটোমেটিক রিপ্লাই বট\n✓ সাবস্ক্রিপশন চলাকালীন নিয়মিত নতুন নতুন ফিচার আপডেট সম্পূর্ণ ফ্রি!\n\nআপনি কি ১ বছর নাকি ৩ বছরের প্ল্যানটি অর্ডার করতে চাচ্ছেন স্যার?";
        $suggestions = ['৯৯৯ টাকার ১ বছরের প্ল্যান নেব', '১৯৯৯ টাকার ৩ বছরের প্ল্যান নেব', 'বিকাশে পেমেন্ট করব'];
    } elseif (preg_match('/(gemini|pro subscription|google pro|ক্লাউড|জেমিনি|গুগল প্রো|১২০|১২৯৯)/iu', $msgLower)) {
        $reply = "জি স্যার! আমাদের অফিশিয়াল Google Gemini Pro সাবস্ক্রিপশন প্ল্যানসমূহ:\n• ট্রায়াল প্রো (১ মাস): ৳১২০\n• স্ট্যান্ডার্ড প্রো (১২ মাস): ৳৯৯৯ (১ বছর ফুল ওয়ারেন্টি)\n• আলটিমেট প্রো (১৮ মাস): ৳১,২৯৯ (দেড় বছর ফুল ওয়ারেন্টি)\n• রিল্যাক্স বিজনেস (৪৮ মাস / ৪ বছর): ৳১,৯৯৯ (২টি আলাদা অ্যাকাউন্ট)\n\nইনস্ট্যান্ট ডেলিভারি ও ফুল কমার্শিয়াল সুবিধা। কোনটি আপনার প্রয়োজন স্যার?";
        $suggestions = ['১২০ টাকার ট্রায়াল প্রো নেব', '৯৯৯ টাকার ১২ মাস প্রো নেব', '১৯৯৯ টাকার বিজনেস প্ল্যান নেব'];
    } elseif (preg_match('/(bistarito|bistarit|details|বিস্তারিত|ডিটেইলস|সবকিছু|feature|ফিচার)/iu', $msgLower)) {
        $reply = "জি স্যার! AutoMovie Pro-এর ৪টি স্বতন্ত্র সফটওয়্যার ইঞ্জিনের বিস্তারিত:\n\n১. Social Media Video Content Engine (৳৩,৯৯৯ — লাইফটাইম): ১-ক্লিকে ভাইরাল স্ক্রিপ্ট, মানুষের কণ্ঠ, সিনেমাটিক সিন ও সাবটাইটেল তৈরি এবং ১৮টি চ্যানেলে অটো আপলোড।\n২. FB Business & Ads Engine (৳২,৯৯৯ — লাইফটাইম): সেলস ব্যানার, কাইনেটিক বিজ্ঞাপন ভিডিও ও মেসেঞ্জার রিপ্লাই বট।\n৩. Profile Auto Pilot (৳১,৯৯৯ — লাইফটাইম): ইসলামিক ও মোটিভেশনাল কোট ব্যানার ও নিরাপদ টাইমলাইন পোস্টিং।\n৪. WAManager Pro WhatsApp Suite (৳৯৯৯/১ বছর, ৳১,৯৯৯/৩ বছর): আনলিমিটেড বাল্ক মেসেজিং, B2B লিড স্ক্র্যাপার ও নিয়মিত সফটওয়্যার আপডেট।\n\nআপনি কোন কাজের জন্য সফটওয়্যার খুঁজছেন স্যার?";
        $suggestions = ['৩,৯৯৯ টাকার ভিডিও প্যাকেজ নেব', '৯৯৯ টাকার WhatsApp সফটওয়্যার নেব', 'বিকাশে পেমেন্ট করব'];
    } elseif (preg_match('/(koyta|software|softower|package|প্যাকেজ|কয়টা|সফটওয়্যার)/iu', $msgLower)) {
        $reply = "জি স্যার! আমাদের ৪টি প্রফেশনাল সফটওয়্যার এবং Google Pro ক্লাউড প্ল্যান রয়েছে:\n• সোশ্যাল মিডিয়া ফুল ভিডিও ইঞ্জিন: ৳৩,৯৯৯ (লাইফটাইম)\n• ফেসবুক বিজনেস ও বিজ্ঞাপন ইঞ্জিন: ৳২,৯৯৯ (লাইফটাইম)\n• প্রোফাইল ও পেজ পোস্ট অটো পাইলট: ৳১,৯৯৯ (লাইফটাইম)\n• WAManager Pro হোয়াটসঅ্যাপ মার্কেটিং: ৳৯৯৯ (১ বছর) / ৳১,৯৯৯ (৩ বছর)\n• Google Gemini Pro সাবস্ক্রিপশন: ৳১২০ থেকে ৳১,৯৯৯\n\nআপনি কোনটি দিয়ে শুরু করতে চান স্যার?";
        $suggestions = ['৩,৯৯৯ টাকার ভিডিও প্যাকেজ নেব', '৯৯৯ টাকার WhatsApp সফটওয়্যার নেব', 'বিকাশে পেমেন্ট করব'];
    } elseif (preg_match('/(dam|koto|price|টাকা|মূল্য|দাম)/iu', $msgLower)) {
        $reply = "জি স্যার! আমাদের সকল প্রোডাক্টের স্বচ্ছ প্রাইসিং লিস্ট:\n• ভিডিও কনটেন্ট ইঞ্জিন: মাত্র ৳৩,৯৯৯ (এককালীন লাইফটাইম)\n• ফেসবুক বিজনেস ইঞ্জিন: মাত্র ৳২,৯৯৯ (এককালীন লাইফটাইম)\n• প্রোফাইল অটো পাইলট: মাত্র ৳১,৯৯৯ (এককালীন লাইফটাইম)\n• WAManager Pro হোয়াটসঅ্যাপ মার্কেটিং: ৳৯৯৯ (১ বছর) / ৳১,৯৯৯ (৩ বছর — রেগুলার আপডেট সহ)\n• গুগল জেমিনি প্রো: ৳১২০ (১ মাস), ৳৯৯৯ (১২ মাস), ৳১,২৯৯ (১৮ মাস), ৳১,৯৯৯ (৪৮ মাস)\n\nআজকে অর্ডার করলে ইনস্ট্যান্ট লাইসেন্স সক্রিয় হবে। কোনটি নিতে চাচ্ছেন স্যার?";
        $suggestions = ['৩,৯৯৯ টাকার ভিডিও প্যাকেজ নেব', '৯৯৯ টাকার WhatsApp প্যাকেজ নেব', 'পরে যোগাযোগ করব'];
    } elseif ($isPoreOrDiscount) {
        if ($discountAllowed) {
            $reply = "অবশ্যই স্যার! আপনি কখন একটু ফ্রি থাকবেন—আজ সন্ধ্যায় নাকি আগামীকাল দুপুরে? যাতে আপনাকে মনে করিয়ে দিতে পারি। ✨\n\nআর স্যার, আপনার জন্য স্পেশাল একটি সিক্রেট ডিসকাউন্ট কুপন কোড [{$cfgCouponCode}] এক্টিভ করে দেওয়া হয়েছে। এটি দিয়ে অর্ডার করলে সরাসরি ৳" . (int)$initDiscount . " নগদ ছাড় পাবেন!";
            $suggestions = ['কুপন দিয়ে এখনই অর্ডার করব', 'WhatsApp এ বিস্তারিত পাঠান'];
            $checkoutUrl = "/order.php?coupon=" . rawurlencode($cfgCouponCode);
        } else {
            $reply = "অবশ্যই স্যার! কোনো সমস্যা নেই। আপনি সময় নিয়ে বিবেচনা করুন। আমাদের প্যাকেজগুলোতে কোনো লুকায়িত ফি নেই এবং সফটওয়্যারগুলো ওয়ান-টাইম লাইফটাইম লাইসেন্স। যেকোনো সময় যেকোনো প্রশ্ন থাকলে সরাসরি আমাকে জানাতে পারেন স্যার। 😊";
            $suggestions = ['প্যাকেজের ফিচার বিস্তারিত বলুন', 'ভিডিও ডেমো দেখতে চাই', 'সরাসরি WhatsApp-এ কথা বলুন'];
            $checkoutUrl = null;
        }
    } else {
        $reply = "জি স্যার, আমি বুঝতে পেরেছি। AutoMovie Pro এবং WAManager Pro দিয়ে আপনার ডিজিটাল কনটেন্ট তৈরি, ফেসবুক ও হোয়াটসঅ্যাপ মার্কেটিং সম্পূর্ণ স্বয়ংক্রিয় করা যায়। আপনি কি সফটওয়্যারটির লাইভ ভিডিও ডেমো দেখতে চান, নাকি কোনো বিশেষ প্যাকেজ সম্পর্কে জানতে চাচ্ছেন স্যার?";
        $suggestions = ['লাইভ ভিডিও ডেমো দেখতে চাই', '৪টি প্যাকেজের পার্থক্য বলুন', 'অর্ডার করতে চাই'];
    }

    $fallbackOut = [
        'ok' => true,
        'reply' => $reply,
        'draft' => $draft,
        'suggestions' => $suggestions,
        'checkout_url' => $checkoutUrl,
        'mode' => 'smart_fallback',
        'visitor_id' => $visitorId,
        'is_returning' => $isReturning,
        'assigned_agent_id' => $agentId,
        'assigned_agent_name' => $agentName,
    ];

    // Persist log & update profile
    amp_record_visitor_chat_turn(
        $pdo,
        $visitorId,
        (string) ($data['session_id'] ?? bin2hex(random_bytes(8))),
        $cIp,
        $lang,
        $agentId,
        $agentName,
        $action === 'greet' ? '[স্বাগত সম্ভাষণ]' : $message,
        $reply,
        $pastPackage,
        $userPhone ? 1 : 0,
        $draft,
        $userPhone,
        $isPoreOrDiscount
    );

    echo json_encode($fallbackOut, JSON_UNESCAPED_UNICODE);
    exit;
}

// ---------------------------------------------------------------------------
// 7. LLM Payload Handling & Memory Recording
// ---------------------------------------------------------------------------
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
    'visitor_id' => $visitorId,
    'is_returning' => $isReturning,
    'assigned_agent_id' => $agentId,
    'assigned_agent_name' => $agentName,
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

// Persist chat turn & update visitor profile
amp_record_visitor_chat_turn(
    $pdo,
    $visitorId,
    (string) ($data['session_id'] ?? bin2hex(random_bytes(8))),
    $cIp,
    $lang,
    $agentId,
    $agentName,
    $action === 'greet' ? '[স্বাগত সম্ভাষণ]' : $message,
    $parsed['reply'],
    $pastPackage,
    ($userPhone || $isWaHandoff) ? 1 : 0,
    $newDraft,
    $userPhone,
    $isPoreOrDiscount
);

echo json_encode($out, JSON_UNESCAPED_UNICODE);

// ---------------------------------------------------------------------------
// Helper: Record Chat Turn & Synchronize Visitor Profile
// ---------------------------------------------------------------------------
function amp_record_visitor_chat_turn(
    PDO $pdo,
    string $visitorId,
    string $sessId,
    string $cIp,
    string $lang,
    string $agentId,
    string $agentName,
    string $userMsg,
    string $botReply,
    ?string $currentPackage,
    int $isWaLead,
    array $draft,
    ?string $userPhone,
    bool $isPoreOrDiscount
): void {
    try {
        // Detect package mention from user or bot message
        $detectedPkg = $currentPackage;
        $combinedText = $userMsg . ' ' . $botReply;
        if (preg_match('/(3999|৩,৯৯৯|video|স্টুডিও|studio|video_studio)/iu', $combinedText)) {
            $detectedPkg = 'video_studio';
        } elseif (preg_match('/(2999|২,৯৯৯|business|বিজনেস|ad|বিজ্ঞাপন|fb_business)/iu', $combinedText)) {
            $detectedPkg = 'fb_business';
        } elseif (preg_match('/(1999|১,৯৯৯|profile|প্রোফাইল|profile_page)/iu', $combinedText)) {
            $detectedPkg = 'profile_page';
        } elseif (preg_match('/(wamanager|wa_marketing|whatsapp|হোয়াটসঅ্যাপ|হোয়াটসঅ্যাপ|বাল্ক|লিড স্ক্র্যাপার|999|৯৯৯)/iu', $combinedText)) {
            $detectedPkg = 'wa_marketing';
        }

        // 1. Insert chat log
        $logStmt = $pdo->prepare(
            "INSERT INTO customer_chat_logs (visitor_id, session_id, customer_ip, lang, agent_id, agent_name, user_message, bot_reply, chosen_package, whatsapp_handoff) 
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        );
        $logStmt->execute([
            $visitorId,
            $sessId,
            $cIp,
            $lang,
            $agentId,
            $agentName,
            $userMsg,
            $botReply,
            $detectedPkg,
            $isWaLead
        ]);

        // 2. Synchronize Visitor Profile
        $now = date('Y-m-d H:i:s');
        $custName = $draft['name'] ?? null;
        $custPhone = $userPhone ?: ($draft['whatsapp'] ?? null);
        $objection = $isPoreOrDiscount ? 'পরে সিদ্ধান্ত নেবেন / ডিসকাউন্ট চেয়েছিলেন' : null;
        $convSummary = "সর্বশেষ কথোপকথন: " . mb_substr($userMsg, 0, 90);

        $chkStmt = $pdo->prepare("SELECT visitor_id, visit_count, customer_name, customer_phone, last_interested_package, last_objection FROM customer_visitor_profiles WHERE visitor_id = ? LIMIT 1");
        $chkStmt->execute([$visitorId]);
        $existing = $chkStmt->fetch();

        if ($existing) {
            $finalPkg = $detectedPkg ?: ($existing['last_interested_package'] ?: null);
            $finalObj = $objection ?: ($existing['last_objection'] ?: null);
            $finalName = $custName ?: ($existing['customer_name'] ?: null);
            $finalPhone = $custPhone ?: ($existing['customer_phone'] ?: null);
            $finalSummary = ($userMsg !== '[স্বাগত সম্ভাষণ]' && trim($userMsg) !== '')
                ? ("সর্বশেষ কথোপকথন: " . mb_substr($userMsg, 0, 90))
                : ($existing['conversation_summary'] ?: 'পূর্ববর্তী চ্যাট সেশন সম্পন্ন');

            $updStmt = $pdo->prepare(
                "UPDATE customer_visitor_profiles 
                 SET last_seen_at = ?, 
                     visit_count = visit_count + 1,
                     customer_name = ?, 
                     customer_phone = ?, 
                     last_interested_package = ?, 
                     last_objection = ?, 
                     conversation_summary = ? 
                 WHERE visitor_id = ?"
            );
            $updStmt->execute([$now, $finalName, $finalPhone, $finalPkg, $finalObj, $finalSummary, $visitorId]);
        } else {
            $insStmt = $pdo->prepare(
                "INSERT INTO customer_visitor_profiles 
                 (visitor_id, customer_name, customer_phone, first_seen_at, last_seen_at, visit_count, assigned_agent_id, assigned_agent_name, last_interested_package, last_objection, conversation_summary)
                 VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)"
            );
            $insStmt->execute([
                $visitorId,
                $custName,
                $custPhone,
                $now,
                $now,
                $agentId,
                $agentName,
                $detectedPkg,
                $objection,
                $convSummary
            ]);
        }

        // 3. Save WhatsApp lead if phone provided
        if ($userPhone) {
            whatsapp_save_lead(
                $pdo,
                $userPhone,
                $draft['name'] ?? 'ওয়েবসাইট চ্যাট ভিজিটর',
                'chat',
                $detectedPkg ?? 'video_studio',
                'চ্যাট এজেন্টের সাথে কথা বলে নম্বর দিয়েছেন',
                $userMsg
            );
            if (setting($pdo, 'agent_auto_queue_whatsapp_welcome', '1') === '1') {
                $waMsg = "আসসালামু আলাইকুম স্যার! AutoMovie Pro টিম থেকে বলছি। ওয়েবসাইটে আপনার সাথে কথা হয়েছিল। সফটওয়্যারটির লাইভ ফুল ভিডিও ডেমো ও ইনস্টলেশন গাইড দেখতে পারেন: https://automoviepro.com/#features \n\nআপনার যেকোনো প্রশ্ন থাকলে সরাসরি এখানেও জানাতে পারেন।";
                whatsapp_queue($pdo, $config, '88' . $userPhone, $waMsg, null);
            }
        }
    } catch (\Throwable $e) {}
}
