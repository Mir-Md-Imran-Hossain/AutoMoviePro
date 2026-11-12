<?php
declare(strict_types=1);
/**
 * Marketing chat — Multi-agent sales consultant powered by Central Master Marketing AI Brain,
 * with psychological profiling, Anti-Nagging Guard, Discount Gatekeeper, and direct In-Chat Order Processing.
 */
require dirname(__DIR__) . '/includes/bootstrap.php';
require_once dirname(__DIR__) . '/includes/agent_llm.php';
require_once dirname(__DIR__) . '/includes/marketing_master_agent.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'POST only']);
    exit;
}

if (!check_rate_limit($pdo, 'marketing_chat', 30, 60)) {
    http_response_code(429);
    echo json_encode([
        'ok' => false,
        'error' => 'too_many_requests',
        'message' => 'অতিরিক্ত বার মেসেজ পাঠানোর কারণে সাময়িকভাবে স্থগিত। কিছুক্ষণ পর পুনরায় চেষ্টা করুন।'
    ], JSON_UNESCAPED_UNICODE);
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
$configuredPersona = setting($pdo, 'agent_primary_persona', 'nirob');

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

// ---------------------------------------------------------------------------
// 3. Direct In-Chat Order Submission Handler (1-Click Chat Checkout)
// ---------------------------------------------------------------------------
if ($action === 'submit_in_chat_order') {
    $orderName = trim((string) ($data['customer_name'] ?? ($visitorProfile['customer_name'] ?? 'ওয়েবসাইট গ্রাহক')));
    $orderPhone = trim((string) ($data['customer_phone'] ?? ($visitorProfile['customer_phone'] ?? '')));
    $orderEmail = trim((string) ($data['customer_email'] ?? ''));
    $orderProduct = strtolower(trim((string) ($data['product_type'] ?? 'video_studio')));
    $orderTxn = strtoupper(trim((string) ($data['txn_id'] ?? '')));
    $orderMethod = trim((string) ($data['payment_method'] ?? 'bKash Agent'));
    $orderCoupon = strtoupper(trim((string) ($data['coupon_code'] ?? '')));
    $orderDiscount = (float) ($data['discount_amount'] ?? 0);

    $serverUpgradeMode = setting($pdo, 'agent_server_upgrade_mode', '1') === '1';
    if ($serverUpgradeMode) {
        $waitlistReply = "আলহামদুলিল্লাহ স্যার! আপনার তথ্যটি আমাদের **ভিআইপি প্রি-লঞ্চ প্রায়োরিটি ওয়েটিং লিস্টে** সফলভাবে নথিভুক্ত করা হয়েছে। 📋✨\n\n"
                       . "আমাদের হাই-স্পিড ভিডিও সার্ভার শিফটিং ও মাইগ্রেশন সম্পন্ন হওয়া মাত্রই আগামী এক সপ্তাহের মধ্যে আমাদের টিম সরাসরি আপনার হোয়াটসঅ্যাপে (" . ($orderPhone ?: 'নম্বর') . ") যোগাযোগ করবে এবং আপনি বিশেষ রি-লঞ্চ অফারে সবার আগে সফটওয়্যারটি পেয়ে যাবেন।\n\n"
                       . "AutoMovie Pro-এর সাথে থাকার জন্য আন্তরিক ধন্যবাদ!";

        try {
            $pdo->prepare("UPDATE customer_psychology_profiles SET in_chat_order_state = 'waitlist_registered', customer_phone = COALESCE(?, customer_phone), customer_name = COALESCE(?, customer_name), last_seen_at = CURRENT_TIMESTAMP WHERE visitor_id = ?")
                ->execute([$orderPhone !== '' ? $orderPhone : null, $orderName !== '' ? $orderName : null, $visitorId]);
        } catch (\Throwable $e) {}

        if ($orderPhone) {
            $waitlistMsg = "আসসালামু আলাইকুম " . ($orderName ?: 'স্যার') . "! AutoMovie Pro-এর প্রি-লঞ্চ প্রায়োরিটি ওয়েটিং লিস্টে যুক্ত হওয়ার জন্য আন্তরিক ধন্যবাদ। আমাদের হাই-স্পিড ভিডিও সার্ভার আপগ্রেড ও ক্লাউড মাইগ্রেশন সম্পন্ন হওয়া মাত্রই আগামী এক সপ্তাহের মধ্যে আমাদের টিম আপনার সাথে যোগাযোগ করে বিশেষ রি-লঞ্চ অফারে সফটওয়্যারটি বুঝিয়ে দেবে। 🚀";
            try {
                whatsapp_queue($pdo, $config, $orderPhone, $waitlistMsg, null);
            } catch (\Throwable $e) {}
        }

        amp_record_visitor_chat_turn(
            $pdo,
            $visitorId,
            (string) ($data['session_id'] ?? bin2hex(random_bytes(8))),
            $cIp,
            $lang,
            $agentId,
            $agentName,
            '[ভিআইপি ওয়েটিং লিস্টে সাবমিট]',
            $waitlistReply,
            $orderProduct,
            1,
            $draft,
            $orderPhone,
            false
        );

        echo json_encode([
            'ok' => true,
            'waitlist' => true,
            'reply' => $waitlistReply,
            'assigned_agent_id' => $agentId,
            'assigned_agent_name' => $agentName,
            'suggestions' => ['সফটওয়্যারের ফিচারসমূহ বলুন', 'কম্পিউটার রিকোয়ারমেন্ট কী?', 'ফেসবুক পেজ অটোমেশন ডেমো']
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $res = MarketingMasterBrain::createInChatOrder($pdo, [
        'visitor_id' => $visitorId,
        'name' => $orderName,
        'phone' => $orderPhone,
        'email' => $orderEmail,
        'product_type' => $orderProduct,
        'txn_id' => $orderTxn,
        'payment_method' => $orderMethod,
        'agent_id' => $agentId,
        'coupon_used' => $orderCoupon,
        'discount_amount' => $orderDiscount
    ]);

    if ($res['ok']) {
        $reply = "🎉 **অভিনন্দন স্যার! আপনার অর্ডারটি চ্যাট থেকে সরাসরি সম্পন্ন হয়েছে!**\n\n"
               . "📦 **অর্ডার আইডি:** #AMP-{$res['order_id']}\n"
               . "💳 **প্যাকেজ:** {$res['plan_name']}\n"
               . "💰 **পরিশোধিত মূল্য:** ৳" . number_format($res['amount']) . "\n"
               . "🔑 **TrxID:** {$res['txn_id']}\n\n"
               . "আমাদের সার্ভার পেমেন্ট যাচাই করে পরবর্তী ৩ থেকে ৫ মিনিটের মধ্যে আপনার লাইসেন্স ও ডাউনলোড ফাইল স্বয়ংক্রিয়ভাবে সক্রিয় করে দিচ্ছে।\n\n"
               . "আমাদের সাথে থাকার জন্য আন্তরিক ধন্যবাদ! যেকোনো সহায়তায় আমাদের হোয়াটসঅ্যাপে জানাতে পারেন: +8801968111593 😊";

        amp_record_visitor_chat_turn(
            $pdo,
            $visitorId,
            (string) ($data['session_id'] ?? bin2hex(random_bytes(8))),
            $cIp,
            $lang,
            $agentId,
            $agentName,
            '[ইন-চ্যাট অর্ডার সাবমিট]',
            $reply,
            $orderProduct,
            1,
            $draft,
            $orderPhone,
            false
        );

        echo json_encode([
            'ok' => true,
            'reply' => $reply,
            'order_receipt' => $res,
            'assigned_agent_id' => $agentId,
            'assigned_agent_name' => $agentName,
            'suggestions' => ['ডাউনলোড গাইডলাইন দিন', 'হোয়াটসঅ্যাপে যোগাযোগ করব', 'লাইসেন্স কী কতক্ষণে পাব?'],
            'mode' => 'in_chat_order_complete'
        ], JSON_UNESCAPED_UNICODE);
        exit;
    } else {
        echo json_encode([
            'ok' => false,
            'error' => $res['error'] ?? 'অর্ডার প্রক্রিয়া করতে সমস্যা হয়েছে। অনুগ্রহ করে TrxID ও নম্বর চেক করুন।'
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }
}

// ---------------------------------------------------------------------------
// 4. Central Master Marketing AI Brain Execution
// ---------------------------------------------------------------------------
$leadPhone = $visitorProfile['customer_phone'] ?? '';
if (preg_match('/(?:\+?8801|01)[3-9]\d{8}/', $message, $phoneMatch)) {
    $rawP = preg_replace('/\D+/', '', $phoneMatch[0]);
    $leadPhone = str_starts_with($rawP, '8801') ? substr($rawP, 2) : (str_starts_with($rawP, '01') ? $rawP : $rawP);
}

$brainResult = MarketingMasterBrain::process($pdo, $config, [
    'channel' => 'website_chat',
    'user_message' => ($action === 'greet' && $message === '') ? '' : $message,
    'conversation_history' => $history,
    'lead_name' => $visitorProfile['customer_name'] ?? 'সম্মানিত অতিথি',
    'lead_phone' => $leadPhone,
    'visitor_id' => $visitorId,
    'requested_agent' => $agentId
]);

$reply = $brainResult['reply'];
$meta = $brainResult['meta'];
$psychology = $meta['psychology'] ?? [];

// Assign specialist if brain recommended routing
if (!empty($meta['selected_agent']) && in_array($meta['selected_agent'], ['nirob', 'ayesha', 'tania'], true)) {
    $agentId = $meta['selected_agent'];
    $agentName = $agentId === 'nirob' ? 'নীরব (Nirob)' : ($agentId === 'tania' ? 'তানিয়া (Tania)' : 'আয়েশা (Ayesha)');
}

// Checkout URL handling if coupon is authorized
$checkoutUrl = null;
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

$newDraft = array_merge($draft, is_array($meta['draft'] ?? null) ? $meta['draft'] : []);
if ($leadPhone) {
    $newDraft['whatsapp'] = $leadPhone;
}

$out = [
    'ok' => true,
    'reply' => $reply,
    'draft' => $newDraft,
    'suggestions' => $meta['suggestions'] ?: [],
    'checkout_url' => $checkoutUrl,
    'mode' => $meta['provider'] ?? 'master_brain',
    'visitor_id' => $visitorId,
    'is_returning' => $isReturning,
    'assigned_agent_id' => $agentId,
    'assigned_agent_name' => $agentName,
    'order_receipt' => $meta['order_receipt'] ?? null,
    'psychology' => [
        'archetype' => $psychology['archetype'] ?? 'hesitant_shopper',
        'temperature' => $psychology['temperature'] ?? 20,
        'stage' => $psychology['stage'] ?? 'unaware',
        'turns_count' => $psychology['turns_count'] ?? 1,
        'discount_status' => $psychology['discount_status'] ?? 'NOT_REQUESTED',
        'recommended_next' => $psychology['recommended_next'] ?? 'video_studio',
        'do_not_nag_products' => $psychology['do_not_nag_products'] ?? []
    ]
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
    ($action === 'greet' && $message === '') ? '[স্বাগত সম্ভাষণ]' : $message,
    $reply,
    $psychology['recommended_next'] ?? null,
    ($leadPhone || $isWaHandoff) ? 1 : 0,
    $newDraft,
    $leadPhone,
    !empty($meta['coupon_offered'])
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
            $cleanUserPhone = whatsapp_clean_phone($userPhone, true);
            whatsapp_save_lead(
                $pdo,
                $cleanUserPhone,
                $draft['name'] ?? 'ওয়েবসাইট চ্যাট ভিজিটর',
                'chat',
                $detectedPkg ?? 'video_studio',
                'চ্যাট এজেন্টের সাথে কথা বলে নম্বর দিয়েছেন',
                $userMsg
            );
            $serverUpgradeMode = setting($pdo, 'agent_server_upgrade_mode', '1') === '1';
            // Only auto-queue generic welcome message if NOT in server upgrade mode (waitlist confirmation is already queued in upgrade mode)
            if (!$serverUpgradeMode && setting($pdo, 'agent_auto_queue_whatsapp_welcome', '1') === '1') {
                $waMsg = "আসসালামু আলাইকুম স্যার! AutoMovie Pro টিম থেকে বলছি। ওয়েবসাইটে আপনার সাথে কথা হয়েছিল। সফটওয়্যারটির লাইভ ফুল ভিডিও ডেমো ও ইনস্টলেশন গাইড দেখতে পারেন: https://automoviepro.com/#features \n\nআপনার যেকোনো প্রশ্ন থাকলে সরাসরি এখানেও জানাতে পারেন।";
                whatsapp_queue($pdo, $GLOBALS['config'] ?? [], $cleanUserPhone, $waMsg, null);
            }
        }
    } catch (\Throwable $e) {}
}
