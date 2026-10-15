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

if ($visitorProfile || !empty($pastLogs)) {
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
        }
    }
}

$pastPkgLabel = match ($pastPackage) {
    'video_studio' => '৩,৯৯৯ টাকার ফুল ভিডিও অটোমেশন স্টুডিও প্যাকেজ',
    'fb_business' => '২,৯৯৯ টাকার ফেসবুক বিজনেস ও অ্যাড অটোমেশন প্যাকেজ',
    'profile_page' => '১,৯৯৯ টাকার ফেসবুক প্রোফাইল ও পেজ অটো পাইলট প্যাকেজ',
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
$visitCount = (int) (($visitorProfile['visit_count'] ?? 1) + 1);

$returningContext = [
    'is_returning' => $isReturning,
    'visit_count' => $visitCount,
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
        $greetUser = "You are {$agentName}. The customer has RETURNED to the website for visit #{$visitCount}! Previously you two talked about {$pastPkgLabel} (" . ($pastTopic ?: "their automation goals") . "). Warmly welcome them back as their recognized consultant without introducing yourself like a stranger. Remind them of what you discussed, address any lingering doubts they might have, and offer helpful decision support so they can confidently choose their package today.";
    } else {
        $greetUser = match ($lang) {
            'en' => "Say a short warm hello as {$agentName}, the AutoMovie Pro sales consultant and ask how you can help (features, pricing, packages, or order). Always address the customer respectfully as Sir.",
            'bn' => "আপনি {$agentName}, AutoMovie Pro টিমের একজন আন্তরিক প্রতিনিধি। অত্যন্ত সংক্ষেপে 'আসসালামু আলাইকুম স্যার, আমি AutoMoviePro টিম থেকে {$agentName} বলছি, আপনাকে কীভাবে সহযোগিতা করতে পারি?' বলুন। কোনো অতিরিক্ত লম্বা কথা বলবেন না।",
            'hi' => 'छोटा सा गर्मजोशी भरा नमस्ते दो और पूछो कैसे मदद कर सकते हो सर।',
            'ur' => 'مختصر گرم جو شی سے سلام کہو اور پوچھো کیسے مدد کر سکتے ہو سر۔',
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
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে আবার স্বাগতম। আমি আপনার কনসালট্যান্ট {$agentName}। আগের চ্যাটে আপনি ৩,৯৯৯ টাকার ভিডিও অটোমেশন স্টুডিও প্যাকেজটি নিয়ে কথা বলেছিলেন। আজ কি লাইসেন্সটি সক্রিয় করতে সাহায্য করতে পারি স্যার?";
                $suggestions = ['৩,৯৯৯ টাকার প্যাকেজটি অর্ডার করব', 'কুপনটি কি প্রযোজ্য?', 'সরাসরি WhatsApp-এ কথা বলব'];
            } elseif ($pastPackage === 'fb_business') {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে আবারও স্বাগতম। আমি আপনার কনসালট্যান্ট {$agentName}। পূর্বে ২,৯৯৯ টাকার ফেসবুক বিজনেস ও অ্যাড অটোমেশন নিয়ে আলোচনা হয়েছিল। এই প্যাকেজে কি আজ সহযোগিতা প্রয়োজন স্যার?";
                $suggestions = ['২,৯৯৯ টাকার প্যাকেজ অর্ডার করব', 'ভিডিও ডেমো দেখতে চাই', 'বিকাশে পেমেন্ট করব'];
            } elseif ($pastPackage === 'profile_page') {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে আবার পেয়ে ভালো লাগলো। আমি আপনার কনসালট্যান্ট {$agentName}। আগের চ্যাটে ১,৯৯৯ টাকার ফেসবুক প্রোফাইল ও পেজ অটো পাইলট প্যাকেজ নিয়ে কথা হয়েছিল। এই বিষয়ে কি সিদ্ধান্ত নিয়েছেন স্যার?";
                $suggestions = ['১,৯৯৯ টাকার প্যাকেজ অর্ডার করব', 'পেমেন্ট নম্বর দিন', 'অন্য প্যাকেজ সম্পর্কে বলুন'];
            } else {
                $reply = "আসসালামু আলাইকুম স্যার! আপনাকে আবারও আমাদের AutoMovie Pro-তে স্বাগতম। আমি আপনার পূর্বের কনসালট্যান্ট {$agentName}। আপনাকে আজ কীভাবে সহযোগিতা করতে পারি স্যার?";
                $suggestions = ['৩টি প্যাকেজের পার্থক্য বলুন', '৩,৯৯৯ টাকার প্যাকেজ নেব', 'সরাসরি WhatsApp-এ কথা বলব'];
            }
        } else {
            $reply = "আসসালামু আলাইকুম স্যার, আমি AutoMoviePro টিম থেকে {$agentName} বলছি, আপনাকে কীভাবে সহযোগিতা করতে পারি?";
            $suggestions = ['প্যাকেজগুলোর দাম কত?', 'ভিডিও কীভাবে তৈরি করে?', 'সরাসরি WhatsApp-এ কথা বলব'];
        }
    } elseif ($userPhone) {
        $reply = "অনেক ধন্যবাদ স্যার! আপনার WhatsApp নম্বরটি ({$userPhone}) সেভ করা হয়েছে। আমাদের টিম থেকে এখনই আপনার WhatsApp-এ লাইভ ভিডিও ডেমো এবং স্পেশাল ইনস্টলেশন ভাউচার পাঠিয়ে দেওয়া হচ্ছে। 😊\n\nআপনি কি এখনই লাইসেন্স অর্ডার করতে আগ্রহী স্যার?";
        $suggestions = ['হ্যাঁ, এখনই অর্ডার করতে চাই', 'প্যাকেজের মূল্য কত?'];
    } elseif (preg_match('/(apnar nam|tomar nam|nam ki|nam kii|naam ki|who are you|who is this|ke bolchen|ke apni|tumi k|apni k|নাম কি|নাম কী|কে বলছেন|আপনার নাম|তোমার নাম)/iu', $msgLower)) {
        $reply = "জি স্যার, আমার নাম {$agentName}। আমি AutoMovie Pro টিম থেকে বলছি। আপনাকে কীভাবে সহযোগিতা করতে পারি স্যার?";
        $suggestions = ['প্যাকেজগুলোর দাম কত?', 'সফটওয়্যার কীভাবে কাজ করে?', 'সরাসরি WhatsApp-এ কথা বলব'];
    } elseif (preg_match('/(kothay thako|kothay bash|ki khao|biye|boyos|prem|valo laglo|personal|বিয়ে|বয়স|কই থাক|কোথায় থাক|কি খাও|বাড়ি কই|বাসা কই)/iu', $msgLower)) {
        $reply = "আমাদের এই চ্যাটিং কর্তৃপক্ষ কর্তৃক মনিটর করা হচ্ছে স্যার। আপনি আমাদের AutoMovie Pro সফটওয়্যার, ফিচার বা অফার সংক্রান্ত যেকোনো প্রশ্ন করুন — আমি আনন্দের সাথে সাহায্য করছি। 😊";
        $suggestions = ['৩টি প্যাকেজের দাম কত?', 'সফটওয়্যার কীভাবে কাজ করে?', 'সরাসরি WhatsApp-এ কথা বলুন'];
    } elseif (preg_match('/(bistarito|bistarit|details|বিস্তারিত|ডিটেইলস|সবকিছু|feature|ফিচার)/iu', $msgLower)) {
        $reply = "জি স্যার! AutoMovie Pro-এর ৩টি প্যাকেজের বিস্তারিত:\n\n১. Social Media Content Automation Engine (৳৩,৯৯৯): ১-ক্লিকে ফুল এআই ভিডিও তৈরি এবং একসাথে ১৮টি চ্যানেলে (YouTube, Facebook, TikTok) স্বয়ংক্রিয় শিডিউলিং ও আপলোড।\n২. FB Business & Ads Engine (৳২,৯৯৯): ফেসবুক বিজ্ঞাপন ব্যানার ও প্রোডাক্ট প্রমোশন অটোমেশন।\n৩. Profile Auto Pilot (৳১,৯৯৯): পার্সোনাল ফেসবুক আইডি ও পেজের পোস্ট অটোমেশন।\n\nসবগুলোই লাইফটাইম লাইসেন্স। আপনি কোন কাজের জন্য সফটওয়্যার খুঁজছেন স্যার?";
        $suggestions = ['৩,৯৯৯ টাকার ভিডিও প্যাকেজ নেব', 'দাম কত?', 'বিকাশে পেমেন্ট করব'];
    } elseif (preg_match('/(koyta|software|softower|package|প্যাকেজ|কয়টা|সফটওয়্যার|software)/iu', $msgLower)) {
        $reply = "জি স্যার! আমাদের ৩টি লাইফটাইম প্যাকেজ রয়েছে:\n• সোশ্যাল মিডিয়া ফুল ভিডিও ইঞ্জিন: ৳৩,৯৯৯\n• ফেসবুক বিজনেস ও বিজ্ঞাপন ইঞ্জিন: ৳২,৯৯৯\n• প্রোফাইল ও পেজ পোস্ট অটো পাইলট: ৳১,৯৯৯\n\nআপনি কোন কাজের জন্য সফটওয়্যার খুঁজছেন স্যার?";
        $suggestions = ['৩,৯৯৯ টাকার ভিডিও প্যাকেজ নেব', 'প্যাকেজের বিস্তারিত ফিচার বলুন', 'বিকাশে পেমেন্ট করব'];
    } elseif (preg_match('/(dam|koto|price|টাকা|মূল্য|দাম)/iu', $msgLower)) {
        $reply = "জি স্যার! AutoMovie Pro সম্পূর্ণ ওয়ান-টাইম পেমেন্ট, কোনো মাসিক ফি নেই। 👍\n• ভিডিও কনটেন্ট ইঞ্জিন: মাত্র ৳৩,৯৯৯\n• ফেসবুক বিজনেস ইঞ্জিন: মাত্র ৳২,৯৯৯\n• প্রোফাইল অটো পাইলট: মাত্র ৳১,৯৯৯\n\nআজকে অর্ডার করলে পাবেন ইনস্ট্যান্ট লাইসেন্স কি ও ফ্রি লাইফটাইম আপডেট। কোনটি নিতে চাচ্ছেন স্যার?";
        $suggestions = ['৩,৯৯৯ টাকার প্যাকেজ নেব', 'বিকাশ নম্বর দিন', 'পরে যোগাযোগ করব'];
    } elseif ($isPoreOrDiscount) {
        if ($discountAllowed) {
            $reply = "অবশ্যই স্যার! আপনি কখন একটু ফ্রি থাকবেন—আজ সন্ধ্যায় নাকি আগামীকাল দুপুরে? যাতে আপনাকে মনে করিয়ে দিতে পারি। ✨\n\nআর স্যার, আপনার জন্য স্পেশাল একটি সিক্রেট ডিসকাউন্ট কুপন কোড [{$cfgCouponCode}] এক্টিভ করে দেওয়া হয়েছে। এটি দিয়ে অর্ডার করলে সরাসরি ৳" . (int)$initDiscount . " নগদ ছাড় পাবেন!";
            $suggestions = ['কুপন দিয়ে এখনই অর্ডার করব', 'WhatsApp এ বিস্তারিত পাঠান'];
            $checkoutUrl = "/order.php?coupon=" . rawurlencode($cfgCouponCode);
        } else {
            $reply = "অবশ্যই স্যার! কোনো সমস্যা নেই। আপনি সময় নিয়ে বিবেচনা করুন। আমাদের প্যাকেজগুলোতে কোনো মাসিক ফি নেই এবং এটি ওয়ান-টাইম লাইফটাইম লাইসেন্স। যেকোনো সময় যেকোনো প্রশ্ন থাকলে সরাসরি আমাকে জানাতে পারেন স্যার। 😊";
            $suggestions = ['প্যাকেজের ফিচার বিস্তারিত বলুন', 'ভিডিও ডেমো দেখতে চাই', 'সরাসরি WhatsApp-এ কথা বলুন'];
            $checkoutUrl = null;
        }
    } else {
        $reply = "জি স্যার, আমি বুঝতে পেরেছি। AutoMovie Pro দিয়ে কোনো কোডিং বা ভিডিও এডিটিং ছাড়াই সম্পূর্ণ এআই ভিডিও তৈরি করে সোশ্যাল মিডিয়ায় অটো আপলোড করা যায়। আপনি কি সফটওয়্যারটির ভিডিও ডেমো দেখতে চান, নাকি কোনো প্যাকেজ সম্পর্কে জানতে চাচ্ছেন স্যার?";
        $suggestions = ['লাইভ ভিডিও ডেমো দেখতে চাই', '৩টি প্যাকেজের পার্থক্য বলুন', 'অর্ডার করতে চাই'];
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
