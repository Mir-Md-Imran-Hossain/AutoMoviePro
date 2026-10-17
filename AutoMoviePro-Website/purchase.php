<?php
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    redirect('/');
}
if (!csrf_verify($_POST['csrf'] ?? null)) {
    http_response_code(400);
    exit('Invalid CSRF');
}

$name = trim((string) ($_POST['name'] ?? ''));
$whatsapp = preg_replace('/\D+/', '', (string) ($_POST['whatsapp'] ?? '')) ?? '';
$email = trim((string) ($_POST['email'] ?? ''));
$plan = trim((string) ($_POST['plan_name'] ?? 'Lifetime Core'));
$personal = strtolower(trim((string) ($_POST['personal_lang'] ?? 'bn')));
$extras = $_POST['extra_langs'] ?? [];
if (!is_array($extras)) {
    $extras = [];
}

$catalog = amp_lang_catalog();
if (!isset($catalog[$personal]) || $personal === 'en') {
    $personal = 'bn';
}

$addonCodes = [];
foreach ($extras as $code) {
    $code = strtolower(trim((string) $code));
    if ($code === 'en' || $code === $personal || !isset($catalog[$code])) {
        continue;
    }
    $addonCodes[] = $code;
}
$addonCodes = array_values(array_unique($addonCodes));

$productType = strtolower(trim((string) ($_POST['product_type'] ?? 'video_studio')));
$durationMonths = (int) ($_POST['plan_duration_months'] ?? 1);

if ($productType === 'fb_business' || str_contains($plan, 'FB Business')) {
    $productType = 'fb_business';
    $basePrice = 2999.0;
    $addonPrice = 499.0;
    $amount = $basePrice + ($addonPrice * count($addonCodes));
    $plan = 'AutoMovie Pro - FB Business Manager & Ad Automation Engine (Lifetime License)';
    $baseLangs = 'en,' . $personal;
    $addonLangs = implode(',', $addonCodes);
} elseif ($productType === 'profile_page' || str_contains($plan, 'Profile & Page')) {
    $productType = 'profile_page';
    $basePrice = 1999.0;
    $addonPrice = 499.0;
    $amount = $basePrice + ($addonPrice * count($addonCodes));
    $plan = 'AutoMovie Pro - FB Profile & Page Post Automation Engine (Lifetime License)';
    $baseLangs = 'en,' . $personal;
    $addonLangs = implode(',', $addonCodes);
} elseif ($productType === 'wa_marketing' || str_contains($plan, 'WhatsApp') || str_contains($plan, 'WAManager')) {
    $productType = 'wa_marketing';
    $waChoice = (int) ($_POST['wa_plan_choice'] ?? ($durationMonths >= 36 || $durationMonths === 3 ? 3 : 1));
    if ($waChoice === 3 || $durationMonths === 36 || $durationMonths === 3) {
        $durationMonths = 36;
        $amount = 1999.0;
        $plan = 'WAManager Pro — WhatsApp Marketing & CRM Suite (৩ বছর সাবস্ক্রিপশন + নিয়মিত ফিচার আপডেট)';
    } else {
        $durationMonths = 12;
        $amount = 999.0;
        $plan = 'WAManager Pro — WhatsApp Marketing & CRM Suite (১ বছর সাবস্ক্রিপশন + নিয়মিত ফিচার আপডেট)';
    }
    $baseLangs = 'all';
    $addonLangs = 'wa_bulk_autoreply_leads_crm';
} elseif ($productType === 'google_pro' || str_contains($plan, 'Google AI Pro') || str_contains($plan, 'Gemini Pro')) {
    $productType = 'google_pro';
    if ($durationMonths === 24) {
        $amount = 1999.0;
        $plan = 'Special Gemini Pro API — Relax Business (2 Accounts, 18 Months)';
    } elseif ($durationMonths === 18) {
        $amount = 1299.0;
        $plan = 'Special Gemini Pro API — Business Account (18 Months)';
    } elseif ($durationMonths === 12) {
        $amount = 999.0;
        $plan = 'Special Gemini Pro API — Startup Account (12 Months)';
    } else {
        $durationMonths = 1;
        $amount = 120.0;
        $plan = 'Special Gemini Pro API — Test Account (1 Month)';
    }
    $baseLangs = 'all_unlimited';
    $addonLangs = 'google_pro_vault_150gb';
} else {
    // Default: video_studio / Social Media Content Automation Engine
    $productType = 'video_studio';
    $basePrice = 3999.0;
    $addonPrice = 499.0;
    $amount = $basePrice + ($addonPrice * count($addonCodes));
    $plan = 'AutoMovie Pro - Social Media Content Automation Engine (Lifetime License)';
    $baseLangs = 'en,' . $personal;
    $addonLangs = implode(',', $addonCodes);
}

$couponCode = strtoupper(trim((string) ($_POST['coupon_code'] ?? '')));
$discount = 0.0;
if ($couponCode !== '') {
    try {
        $cStmt = $pdo->prepare('SELECT * FROM coupons WHERE UPPER(code) = ? AND is_active = 1 LIMIT 1');
        $cStmt->execute([$couponCode]);
        $cRow = $cStmt->fetch(PDO::FETCH_ASSOC);
        if ($cRow) {
            $minOrder = (float) ($cRow['min_order_amount'] ?? 0);
            if ($minOrder <= 0 || $amount >= $minOrder) {
                if (!empty($cRow['discount_percent'])) {
                    $discount = ($amount * (float) $cRow['discount_percent']) / 100.0;
                } else {
                    $discount = (float) ($cRow['discount_amount'] ?? 0);
                }
            }
        }
    } catch (Throwable) {}

    if ($discount > 0) {
        $amount = max(0.0, $amount - $discount);
        $plan .= " [Coupon: {$couponCode}, -৳" . (int)$discount . "]";
    }
}

$languagesJson = json_encode([
    'product_type' => $productType,
    'plan_duration_months' => $durationMonths,
    'base' => ($productType === 'google_pro') ? ['all'] : ['en', $personal],
    'addons' => ($productType === 'google_pro') ? ['google_pro_vault_150gb'] : $addonCodes,
    'coupon' => $couponCode !== '' ? $couponCode : null,
    'discount' => $discount > 0 ? $discount : 0,
], JSON_UNESCAPED_UNICODE);

$paymentMethod = strtolower(trim((string) ($_POST['payment_method'] ?? 'bkash')));
$senderLastDigits = trim((string) ($_POST['sender_last_digits'] ?? ''));
$txnId = strtoupper(trim((string) ($_POST['txn_id'] ?? '')));
$paymentScreenshotPath = null;

// Handle screenshot file upload if submitted
if (!empty($_FILES['payment_screenshot']) && is_uploaded_file($_FILES['payment_screenshot']['tmp_name'])) {
    $f = $_FILES['payment_screenshot'];
    if ($f['error'] === UPLOAD_ERR_OK && $f['size'] > 0 && $f['size'] <= 10 * 1024 * 1024) {
        $ext = strtolower(pathinfo((string)$f['name'], PATHINFO_EXTENSION));
        if (in_array($ext, ['jpg', 'jpeg', 'png', 'webp'], true)) {
            $uploadDir = __DIR__ . '/uploads/receipts';
            if (!is_dir($uploadDir)) {
                @mkdir($uploadDir, 0755, true);
            }
            $safeName = 'receipt_' . time() . '_' . bin2hex(random_bytes(6)) . '.' . $ext;
            $destPath = $uploadDir . '/' . $safeName;
            if (move_uploaded_file($f['tmp_name'], $destPath)) {
                $paymentScreenshotPath = '/uploads/receipts/' . $safeName;
            }
        }
    }
}

// If TrxID or screenshot or sender digits provided, mark under_review, otherwise pending_payment
$initialStatus = ($txnId !== '' || $paymentScreenshotPath !== null || $senderLastDigits !== '') ? 'under_review' : 'pending_payment';

if ($name === '' || strlen($whatsapp) < 10) {
    redirect('/?error=1#buy');
}

$driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
$nowSql = ($driver === 'sqlite') ? "datetime('now')" : "NOW()";

$pdo->beginTransaction();
try {
    $stmt = $pdo->prepare(
        "INSERT INTO customers (name, whatsapp, email, status, created_at)
         VALUES (?, ?, ?, ?, {$nowSql})"
    );
    $stmt->execute([$name, $whatsapp, $email !== '' ? $email : null, 'pending']);
    $customerId = (int) $pdo->lastInsertId();

    $stmt = $pdo->prepare(
        "INSERT INTO orders (
            customer_id, name, whatsapp, email, plan_name, amount, status,
            languages_json, base_langs, addon_langs, payment_method, sender_last_digits, txn_id, payment_screenshot, created_at
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {$nowSql})"
    );
    $stmt->execute([
        $customerId,
        $name,
        $whatsapp,
        $email !== '' ? $email : null,
        $plan,
        $amount,
        $initialStatus,
        $languagesJson,
        $baseLangs,
        $addonLangs !== '' ? $addonLangs : null,
        $paymentMethod,
        $senderLastDigits !== '' ? $senderLastDigits : null,
        $txnId !== '' ? $txnId : null,
        $paymentScreenshotPath,
    ]);
    $orderId = (int) $pdo->lastInsertId();

    if ($productType === 'google_pro') {
        $subStmt = $pdo->prepare(
            "INSERT INTO google_pro_subscriptions (
                customer_id, order_id, plan_duration_months, price, status, target_email, created_at
             ) VALUES (?, ?, ?, ?, 'pending_activation', ?, {$nowSql})"
        );
        $subStmt->execute([
            $customerId,
            $orderId,
            $durationMonths,
            $amount,
            $email !== '' ? $email : null,
        ]);
    }

    $pdo->commit();

    // Auto Save Lead into WhatsApp Marketing Hub
    try {
        whatsapp_save_lead($pdo, $whatsapp, $name, 'order', $productType, "অর্ডার #{$orderId} তৈরি হয়েছে ({$plan})");
        
        // Auto WhatsApp notification to customer upon order placement
        if (setting($pdo, 'wa_auto_order_placed', '1') === '1' && $productType !== 'google_pro') {
            $bkashAgent = setting($pdo, 'bkash_agent_number', '01756160993');
            $nagadAgent = setting($pdo, 'nagad_agent_number', '01611-824811');
            whatsapp_queue($pdo, $config, $whatsapp, $orderMsg, $customerId);

            try {
                $dispId = 'disp_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                $pdo->prepare("INSERT INTO request_dispatches (id, trigger_type, customer_name, phone, order_id, package_name, message_content, status, sent_at, created_at) VALUES (?, 'order_placed', ?, ?, ?, ?, ?, 'sent', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
                    ->execute([$dispId, $name, $whatsapp, (string)$orderId, $plan, $orderMsg]);

                $cleanDig = preg_replace('/\D+/', '', $whatsapp);
                if (str_starts_with($cleanDig, '01')) $cleanDig = '880' . substr($cleanDig, 1);
                $normPhone = '+' . $cleanDig;
                $cId = 'cnt_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                $pdo->prepare("INSERT OR REPLACE INTO contacts (id, name, phone, country_code, source, consent_status, created_at, updated_at) VALUES (?, ?, ?, '880', 'website_order', 'opted_in', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
                    ->execute([$cId, $name, $normPhone]);
                $pdo->prepare("INSERT OR IGNORE INTO contact_group_members (group_id, contact_id, added_at) VALUES ('pending_leads', ?, CURRENT_TIMESTAMP)")
                    ->execute([$cId]);
            } catch (\Throwable $eReg) {}
        }
    } catch (\Throwable $eLead) {}

    // 2-Way WhatsApp Alert for Google AI Pro
    if ($productType === 'google_pro' || str_contains($plan, 'Google AI Pro')) {
        try {
            // ১. কাস্টমারের হোয়াটসঅ্যাপে জিমেইল চাওয়ার মেসেজ
            $custMsg = "অভিনন্দন {$name}! AutoMovie Pro-এর 'Google AI Pro প্যাকেজ' (#{$orderId})-এর অর্ডার সফলভাবে তৈরি হয়েছে। এটি একটি ডেডিকেটেড প্রিমিয়াম সার্ভিস হওয়ায় আপনার জন্য ১৫০ জিবি ক্লাউড ভল্ট ও এপিআই এক্সেস প্রস্তুত করা হচ্ছে। অনুগ্রহ করে আপনার যে জিমেইল (Gmail) অ্যাকাউন্টে ১৫০ জিবি ক্লাউড স্টোরেজ ও এপিআই এক্সেস নিতে চান, সেই ইমেইল অ্যাড্রেসটি লিখে এখনই আমাদের এই হোয়াটসঅ্যাপে মেসেজ পাঠান।";
            whatsapp_queue($pdo, $config, $whatsapp, $custMsg, $customerId);

            // ২. অ্যাডমিনের হোয়াটসঅ্যাপ নম্বরে বিস্তারিত অর্ডার নোটিফিকেশন
            $adminWhatsapp = setting($pdo, 'admin_notify_whatsapp', '8801968111593');
            $adminMsg = "🚨 নতুন Google AI Pro অর্ডার! অর্ডার আইডি: #{$orderId}, গ্রাহকের নাম: {$name}, মোবাইল: {$whatsapp}, প্ল্যান: {$plan} (৳" . (int)$amount . ")। গ্রাহককে জিমেইল চেয়ে ম্যানুয়ালি ১৫০ জিবি ক্লাউড ভল্ট ও এপিআই এক্সেস বুঝিয়ে দিন।";
            whatsapp_queue($pdo, $config, $adminWhatsapp, $adminMsg, $customerId);
        } catch (\Throwable $eNotice) {
            error_log("WhatsApp alert dispatch error: " . $eNotice->getMessage());
        }
    }
} catch (Throwable $e) {
    $pdo->rollBack();
    // Fallback if columns missing on very old DB
    try {
        $pdo->beginTransaction();
        $stmt = $pdo->prepare(
            'INSERT INTO customers (name, whatsapp, email, status, created_at)
             VALUES (?, ?, ?, ?, NOW())'
        );
        $stmt->execute([$name, $whatsapp, $email !== '' ? $email : null, 'pending']);
        $customerId = (int) $pdo->lastInsertId();
        $stmt = $pdo->prepare(
            'INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, status, created_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, NOW())'
        );
        $stmt->execute([
            $customerId,
            $name,
            $whatsapp,
            $email !== '' ? $email : null,
            $plan . ' [' . $baseLangs . ($addonLangs !== '' ? '+' . $addonLangs : '') . ']',
            $amount,
            'pending_payment',
        ]);
        $orderId = (int) $pdo->lastInsertId();
        $pdo->commit();

        if ($productType === 'google_pro' || str_contains($plan, 'Google AI Pro')) {
            try {
                $custMsg = "অভিনন্দন {$name}! AutoMovie Pro-এর 'Google AI Pro প্যাকেজ' (#{$orderId})-এর অর্ডার সফলভাবে তৈরি হয়েছে। অনুগ্রহ করে আপনার যে জিমেইল (Gmail) অ্যাকাউন্টে ১৫০ জিবি ক্লাউড স্টোরেজ ও এপিআই এক্সেস নিতে চান, সেই ইমেইল অ্যাড্রেসটি লিখে আমাদের হোয়াটসঅ্যাপে মেসেজ পাঠান।";
                whatsapp_queue($pdo, $config, $whatsapp, $custMsg, $customerId);

                $adminMsg = "🚨 নতুন Google AI Pro অর্ডার! অর্ডার আইডি: #{$orderId}, নাম: {$name}, মোবাইল: {$whatsapp}, প্ল্যান: {$plan} (৳" . (int)$amount . ")।";
                whatsapp_queue($pdo, $config, '01968111593', $adminMsg, $customerId);
            } catch (\Throwable) {}
        }
    } catch (Throwable $e2) {
        $pdo->rollBack();
        throw $e2;
    }
}

redirect('/pending.php?order=' . $orderId);
