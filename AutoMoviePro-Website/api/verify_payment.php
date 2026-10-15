<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';

$raw = file_get_contents('php://input');
$data = json_decode($raw, true) ?? $_POST;

$orderId = (int) ($data['order_id'] ?? 0);
$method = trim((string) ($data['payment_method'] ?? 'bkash'));
$senderLastDigits = trim((string) ($data['sender_last_digits'] ?? ''));
$txnId = strtoupper(trim((string) ($data['txn_id'] ?? '')));

if ($orderId <= 0 || ($senderLastDigits === '' && $txnId === '')) {
    echo json_encode([
        'ok' => false,
        'error' => 'অর্ডার আইডি এবং ট্রানজেকশন আইডি অথবা নম্বরের শেষ ৩-৪ ডিজিট আবশ্যক।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$stmt = $pdo->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
$stmt->execute([$orderId]);
$order = $stmt->fetch();

if (!$order) {
    echo json_encode([
        'ok' => false,
        'error' => 'অর্ডার খুঁজে পাওয়া যায়নি।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

require_once __DIR__ . '/../includes/billing.php';

// Check if already approved/active
if ($order['status'] === 'active' || $order['status'] === 'approved') {
    $dlToken = amp_create_download_token($pdo, $orderId, (int) ($order['customer_id'] ?? 0));
    $dlLink = '/download.php?token=' . $dlToken;
    echo json_encode([
        'ok' => true,
        'status' => 'already_active',
        'message' => 'আপনার অ্যাকাউন্ট ইতিমধ্যেই সক্রিয় আছে!',
        'download_url' => $dlLink,
        'login_id' => $order['whatsapp'] ?? 'User_' . $order['id']
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// 1. Regex Validation for MFS Transaction IDs (bKash, Nagad, Rocket)
if ($txnId !== '') {
    $methodKey = strtolower($method);
    if (str_contains($methodKey, 'bkash')) {
        if (!preg_match('/^[A-Z0-9]{8,12}$/', $txnId)) {
            echo json_encode([
                'ok' => false,
                'error' => 'বিকাশ ট্রানজেকশন আইডি (TrxID) সাধারণত ৮-১০ ডিজিটের অক্ষর ও সংখ্যার হয়ে থাকে (যেমন: BL92KA871X)। সঠিক TrxID দিন।'
            ], JSON_UNESCAPED_UNICODE);
            exit;
        }
    } elseif (str_contains($methodKey, 'nagad')) {
        if (!preg_match('/^[A-Z0-9]{8,12}$/', $txnId)) {
            echo json_encode([
                'ok' => false,
                'error' => 'নগদ ট্রানজেকশন আইডি (TrxID) সাধারণত ৮-১০ ডিজিটের হয়ে থাকে (যেমন: 71A3BC45)। সঠিক TrxID দিন।'
            ], JSON_UNESCAPED_UNICODE);
            exit;
        }
    } elseif (str_contains($methodKey, 'rocket')) {
        if (!preg_match('/^[A-Z0-9]{8,14}$/', $txnId)) {
            echo json_encode([
                'ok' => false,
                'error' => 'রকেট ট্রানজেকশন আইডি সঠিক ফরম্যাটে দিন (যেমন: 1029384756)।'
            ], JSON_UNESCAPED_UNICODE);
            exit;
        }
    } else {
        if (!preg_match('/^[A-Z0-9_-]{6,24}$/', $txnId)) {
            echo json_encode([
                'ok' => false,
                'error' => 'ট্রানজেকশন আইডিতে অবৈধ চিহ্ন রয়েছে। সঠিক TrxID প্রদান করুন।'
            ], JSON_UNESCAPED_UNICODE);
            exit;
        }
    }

    // 2. Duplicate TrxID Guard: Prevent reuse of previously approved or under-review TrxIDs
    $dupStmt = $pdo->prepare("
        SELECT id, status, name, amount 
        FROM orders 
        WHERE UPPER(txn_id) = ? AND id != ? AND status IN ('approved', 'active', 'under_review')
        LIMIT 1
    ");
    $dupStmt->execute([$txnId, $orderId]);
    $dupOrder = $dupStmt->fetch();

    if ($dupOrder) {
        echo json_encode([
            'ok' => false,
            'code' => 'DUPLICATE_TRX_ID',
            'error' => 'এই ট্রানজেকশন আইডিটি (TrxID: ' . $txnId . ') ইতিমধ্যে অর্ডার #' . $dupOrder['id'] . '-এ ব্যবহৃত বা যাচাইাধীন রয়েছে। প্রতিটি অর্ডারের জন্য ইউনিক TrxID আবশ্যক।'
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }
}

// Automated Reconciliation against agent_sms_inbox
$smsStmt = $pdo->prepare("
    SELECT id, amount, is_matched 
    FROM agent_sms_inbox 
    WHERE (UPPER(txn_id) = ? OR (sender_last_digits = ? AND ABS(amount - ?) < 1.0))
    ORDER BY id DESC LIMIT 1
");
$smsStmt->execute([$txnId, $senderLastDigits, (float) ($order['amount'] ?? 0)]);
$matchedSms = $smsStmt->fetch();

$isAutoApproved = false;
if ($matchedSms) {
    $isAutoApproved = true;
    $pdo->prepare('UPDATE agent_sms_inbox SET is_matched = 1, matched_order_id = ? WHERE id = ?')
        ->execute([$orderId, $matchedSms['id']]);
}

try {
    $now = amp_sql_now($pdo);
    if ($isAutoApproved) {
        // Record payment submission info
        $pdo->prepare("UPDATE orders SET payment_method = ?, txn_id = ?, sender_last_digits = ?, updated_at = {$now} WHERE id = ?")
            ->execute([$method, $txnId, $senderLastDigits, $orderId]);

        // Secure industrial approval via billing workflow: password_hash(), 30-day license token, and customer_languages unlock
        $approval = amp_approve_order($pdo, $config, $orderId);
        if (!$approval['ok']) {
            throw new RuntimeException($approval['error'] ?? 'Approval process failed');
        }

        $isGooglePro = str_contains((string)($order['plan_name'] ?? ''), 'Google AI Pro');
        $newStatus = 'active';
        $loginId = $approval['login_id'] ?? ($order['whatsapp'] ?? ('User_' . $orderId));
        $temporaryPassword = $approval['password'] ?? null;
        $licenseToken = $approval['token'] ?? null;
        $unlockedLangs = $approval['unlocked'] ?? [];
        $message = $isGooglePro 
            ? 'পেমেন্ট যাচাই সফল হয়েছে! গুগল এআই প্রো ও ১৫০ জিবি ক্লাউড স্টোরেজ অ্যাক্টিভেশনের জন্য আপনার জিমেইল আইডি হোয়াটসঅ্যাপে পাঠান।'
            : 'পেমেন্ট যাচাই সফল হয়েছে! আপনার অ্যাকাউন্ট প্রস্তুত ও লাইসেন্স সক্রিয় করা হয়েছে।';
    } else {
        $isGooglePro = str_contains((string)($order['plan_name'] ?? ''), 'Google AI Pro');
        $newStatus = 'under_review';
        $pdo->prepare("UPDATE orders SET payment_method = ?, txn_id = ?, sender_last_digits = ?, status = 'under_review', updated_at = {$now} WHERE id = ?")
            ->execute([$method, $txnId, $senderLastDigits, $orderId]);

        $loginId = $order['whatsapp'] ?? ('User_' . $orderId);
        $temporaryPassword = null;
        $licenseToken = null;
        $unlockedLangs = [];
        $message = 'পেমেন্ট তথ্য গৃহীত হয়েছে। ১-২ মিনিটের মধ্যে স্বয়ংক্রিয়ভাবে যাচাই করে সক্রিয় করা হবে।';
    }

    require_once __DIR__ . '/../includes/whatsapp.php';
    if ($isGooglePro) {
        try {
            $custName = (string) ($order['name'] ?? 'গ্রাহক');
            $custWhatsapp = (string) ($order['whatsapp'] ?? '');
            $customerId = (int) ($order['customer_id'] ?? 0) ?: null;

            // ১. গ্রাহকের হোয়াটসঅ্যাপে জিমেইল চাওয়ার মেসেজ
            $custVerifyMsg = "ধন্যবাদ {$custName}! আপনার Google AI Pro অর্ডারের (#{$orderId}) পেমেন্ট তথ্য গৃহীত হয়েছে। ট্রানজেকশন: {$txnId}। আপনার ১৫০ জিবি ক্লাউড স্টোরেজ ভল্ট ও এআই এপিআই অবিলম্বে সক্রিয় করতে আপনার সচল Gmail Address টি লিখে রিপ্লাই দিন অথবা 01968111593 এ জানান।";
            whatsapp_queue($pdo, $config, $custWhatsapp, $custVerifyMsg, $customerId);

            // ২. অ্যাডমিনের হোয়াটসঅ্যাপে (01968111593) বিস্তারিত অর্ডার নোটিফিকেশন
            $adminWhatsapp = '01968111593';
            $adminVerifyMsg = "💰 Google AI Pro পেমেন্ট নোটিফিকেশন!\nঅর্ডার: #{$orderId}\nনাম: {$custName}\nমোবাইল: {$custWhatsapp}\nমেথড: {$method}\nTxnID: {$txnId}\nস্ট্যাটাস: {$newStatus}\nঅনুগ্রহ করে গ্রাহকের জিমেইল নিশ্চিত করে ১৫০ জিবি ক্লাউড ভল্ট ও এআই এক্সেস কনফিগার করুন।";
            whatsapp_queue($pdo, $config, $adminWhatsapp, $adminVerifyMsg, $customerId);
        } catch (\Throwable $eNotice) {
            error_log("WhatsApp alert dispatch error on verify: " . $eNotice->getMessage());
        }
    }

    $dlToken = amp_create_download_token($pdo, $orderId, (int) ($order['customer_id'] ?? 0));
    $dlLink = '/download.php?token=' . $dlToken;
    $waHandoffMsg = "আমার Google AI Pro অর্ডার আইডি: #{$orderId}, নাম: " . ($order['name'] ?? '') . "। আমার জিমেইল আইডি হলো: [এখানে আপনার জিমেইল লিখুন]। অনুগ্রহ করে আমার ১৫০ জিবি ক্লাউড স্টোরেজ ও এপিআই এক্সেস কনফিগার করে দিন।";
    $waHandoffUrl = "https://wa.me/8801968111593?text=" . urlencode($waHandoffMsg);

    echo json_encode([
        'ok' => true,
        'status' => $newStatus,
        'message' => $message,
        'download_url' => $dlLink,
        'is_google_pro' => $isGooglePro,
        'whatsapp_handoff_url' => $waHandoffUrl,
        'credentials' => [
            'login_id' => $loginId,
            'temporary_password' => $temporaryPassword,
            'license_token' => $licenseToken,
            'unlocked_languages' => $unlockedLangs,
            'hardware_bound' => 'সফটওয়্যার প্রথমবার যে কম্পিউটারে ওপেন করবেন, সেটি স্থায়ীভাবে লক হয়ে যাবে।'
        ]
    ], JSON_UNESCAPED_UNICODE);

} catch (Throwable $e) {
    echo json_encode([
        'ok' => false,
        'error' => 'ডাটাবেস সংরক্ষণ ব্যর্থ: ' . $e->getMessage()
    ], JSON_UNESCAPED_UNICODE);
}
