<?php
declare(strict_types=1);

/**
 * Order approval + purchased language unlocks (website ↔ desktop app).
 */
function amp_order_lang_codes(array $order): array
{
    $codes = [];
    if (!empty($order['languages_json'])) {
        $decoded = json_decode((string) $order['languages_json'], true);
        if (is_array($decoded)) {
            if (!empty($decoded['all']) && is_array($decoded['all'])) {
                $codes = $decoded['all'];
            } else {
                $codes = array_merge(
                    is_array($decoded['base'] ?? null) ? $decoded['base'] : [],
                    is_array($decoded['addons'] ?? null) ? $decoded['addons'] : []
                );
            }
        }
    }
    if (!$codes) {
        foreach (['base_langs', 'addon_langs'] as $field) {
            foreach (explode(',', (string) ($order[$field] ?? '')) as $c) {
                $c = strtolower(trim($c));
                if ($c !== '') {
                    $codes[] = $c;
                }
            }
        }
    }
    $catalog = amp_lang_catalog();
    $out = [];
    foreach ($codes as $c) {
        $c = strtolower(trim((string) $c));
        if ($c !== '' && $c !== 'en' && isset($catalog[$c]) && !in_array($c, $out, true)) {
            $out[] = $c;
        }
    }
    return $out;
}

function amp_apply_purchased_languages(PDO $pdo, int $customerId, array $order): array
{
    $unlocked = [];
    foreach (amp_order_lang_codes($order) as $code) {
        amp_unlock_customer_lang($pdo, $customerId, $code, 'order_purchase');
        $unlocked[] = $code;
    }
    return $unlocked;
}

function amp_sql_now(PDO $pdo): string
{
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    if ($driver === 'sqlite') {
        return "datetime('now')";
    }
    return 'NOW()';
}

function amp_issue_license(PDO $pdo, int $customerId, int $days = 30): string
{
    $token = bin2hex(random_bytes(24));
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    if ($driver === 'sqlite') {
        $stmt = $pdo->prepare(
            "INSERT INTO licenses (customer_id, token, expires_at, revoked, created_at)
             VALUES (?, ?, datetime('now', '+' || ? || ' days'), 0, datetime('now'))"
        );
        $stmt->execute([$customerId, $token, $days]);
    } else {
        $stmt = $pdo->prepare(
            'INSERT INTO licenses (customer_id, token, expires_at, revoked, created_at)
             VALUES (?, ?, DATE_ADD(NOW(), INTERVAL ? DAY), 0, NOW())'
        );
        $stmt->execute([$customerId, $token, $days]);
    }
    return $token;
}

function amp_refresh_license(PDO $pdo, string $token, int $days = 30): void
{
    if ($token === '') {
        return;
    }
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    if ($driver === 'sqlite') {
        $stmt = $pdo->prepare(
            "UPDATE licenses 
             SET expires_at = datetime('now', '+' || ? || ' days') 
             WHERE token = ? AND revoked = 0"
        );
        $stmt->execute([$days, $token]);
    } else {
        $stmt = $pdo->prepare(
            'UPDATE licenses 
             SET expires_at = DATE_ADD(NOW(), INTERVAL ? DAY) 
             WHERE token = ? AND revoked = 0'
        );
        $stmt->execute([$days, $token]);
    }
}

function amp_determine_order_tier(array $order): string
{
    $amt = (float) ($order['amount'] ?? 0);
    $plan = strtolower((string) ($order['plan_name'] ?? ''));

    // ৳3,999 -> video_studio (Full Omni Social Media Content Automation)
    if (abs($amt - 3999.0) < 50 || str_contains($plan, 'video') || str_contains($plan, 'omni social') || str_contains($plan, 'studio')) {
        return 'video_studio';
    }
    // ৳2,999 -> fb_business (Omni FB Business Manager & Ad Content Automation)
    if (abs($amt - 2999.0) < 50 || str_contains($plan, 'fb business') || str_contains($plan, 'business manager') || str_contains($plan, 'business_ad') || str_contains($plan, 'business') || str_contains($plan, 'ad')) {
        return 'fb_business';
    }
    // ৳1,999 -> profile_page (Omni FB Profile & Page Post Automation)
    if (abs($amt - 1999.0) < 50 || str_contains($plan, 'profile') || str_contains($plan, 'page') || str_contains($plan, 'autopilot')) {
        return 'profile_page';
    }
    // Tier threshold fallbacks
    if ($amt >= 3500.0) {
        return 'video_studio';
    }
    if ($amt >= 2500.0) {
        return 'fb_business';
    }
    if ($amt >= 1500.0) {
        return 'profile_page';
    }
    return 'video_studio';
}

function amp_customer_api_payload(PDO $pdo, array $customer): array
{
    $customerId = (int) ($customer['id'] ?? 0);
    $unlocked = amp_customer_unlocked_langs($pdo, $customerId);
    $tier = (string) ($customer['tier'] ?? $customer['plan'] ?? 'video_studio');
    if ($tier === 'lifetime' || $tier === '' || $tier === 'standard') {
        $tier = 'video_studio';
    }
    return [
        'id' => $customerId,
        'name' => (string) ($customer['name'] ?? ''),
        'login_id' => (string) ($customer['login_id'] ?? ''),
        'status' => (string) ($customer['status'] ?? 'active'),
        'plan' => $tier,
        'tier' => $tier,
        'unlocked' => $unlocked,
        'activated_at' => $customer['activated_at'] ?? null,
        'days_active' => days_since($customer['activated_at'] ?? ($customer['created_at'] ?? null)),
    ];
}

/**
 * Approve a pending payment order: activate customer, unlock langs, issue login & 30-day license.
 *
 * @return array{ok:bool,login_id?:string,password?:string,customer_id?:int,token?:string,tier?:string,plan?:string,unlocked?:array,error?:string}
 */
function amp_approve_order(PDO $pdo, array|int $configOrOrderId, ?int $orderId = null, bool $sendNotifications = true): array
{
    global $config;
    if (is_int($configOrOrderId) && $orderId === null) {
        $orderId = $configOrOrderId;
        $cfg = is_array($config) ? $config : [];
    } else {
        $cfg = is_array($configOrOrderId) ? $configOrOrderId : (is_array($config) ? $config : []);
        $orderId = (int) $orderId;
    }

    $stmt = $pdo->prepare('SELECT * FROM orders WHERE id = ?');
    $stmt->execute([$orderId]);
    $order = $stmt->fetch();
    if (!$order) {
        return ['ok' => false, 'error' => 'order_not_found'];
    }
    if (!in_array($order['status'] ?? '', ['pending_payment', 'under_review'], true)) {
        return ['ok' => false, 'error' => 'not_pending'];
    }

    $now = amp_sql_now($pdo);
    $tier = amp_determine_order_tier($order);
    $customerId = (int) ($order['customer_id'] ?? 0);
    if ($customerId <= 0) {
        $ins = $pdo->prepare(
            "INSERT INTO customers (name, whatsapp, email, status, tier, plan, created_at)
             VALUES (?, ?, ?, 'pending', ?, ?, {$now})"
        );
        $ins->execute([$order['name'], $order['whatsapp'], $order['email'] ?? null, $tier, $tier]);
        $customerId = (int) $pdo->lastInsertId();
        $pdo->prepare('UPDATE orders SET customer_id = ? WHERE id = ?')->execute([$customerId, $orderId]);
    }

    $loginId = generate_login_id();
    $plainPass = random_password(10);
    $hash = password_hash($plainPass, PASSWORD_DEFAULT);
    $pdo->prepare(
        "UPDATE customers SET login_id = ?, password_hash = ?, status = 'active', tier = ?, plan = ?, activated_at = {$now}
         WHERE id = ?"
    )->execute([$loginId, $hash, $tier, $tier, $customerId]);

    // Core subscription is LIFETIME (100 years / 36500 days) — updates & addons charged separately
    $days = 36500;
    $token = amp_issue_license($pdo, $customerId, $days);
    amp_apply_purchased_languages($pdo, $customerId, $order);

    $pdo->prepare("UPDATE orders SET status = 'approved', approved_at = {$now} WHERE id = ?")
        ->execute([$orderId]);

    // Check if order is for Google AI Pro package
    $isGooglePro = false;
    $proSub = null;
    try {
        $subCheck = $pdo->prepare('SELECT * FROM google_pro_subscriptions WHERE order_id = ? LIMIT 1');
        $subCheck->execute([$orderId]);
        $proSub = $subCheck->fetch(PDO::FETCH_ASSOC);
        if ($proSub || str_contains((string)($order['plan_name'] ?? ''), 'Google AI Pro')) {
            $isGooglePro = true;
        }
    } catch (\Throwable) {}

    $siteUrl = rtrim((string) ($cfg['site_url'] ?? 'https://automoviepro.com'), '/');

    // Generate 72-hour one-time cryptographic download token
    $dlToken = amp_create_download_token($pdo, $orderId, $customerId, 'software', 72);
    $dlUrl = $siteUrl . '/download.php?token=' . $dlToken;

    if ($sendNotifications) {
        if ($isGooglePro) {
            $planMonths = $proSub ? (int) $proSub['plan_duration_months'] : 1;
            if ($planMonths <= 0) {
                if (str_contains((string)$order['plan_name'], '18')) $planMonths = 18;
                elseif (str_contains((string)$order['plan_name'], '12')) $planMonths = 12;
                else $planMonths = 1;
            }
            $priceVal = number_format((float) ($order['amount'] ?? 120.0), 0, '.', '');
            $custName = (string) $order['name'];
            $custWhatsapp = (string) $order['whatsapp'];

            // ক. ক্রেতার হোয়াটসঅ্যাপে মেসেজ যাবে
            $customerMsg = "অভিনন্দন! আপনার AutoMovie Pro এর 'Google AI Pro প্যাকেজ'-এর পেমেন্ট সফলভাবে গৃহীত হয়েছে। এটি একটি ডেডিকেটেড প্রিমিয়াম সার্ভিস হওয়ায় আমরা আপনাকে ম্যানুয়ালি অ্যাকাউন্টটি কনফিগার করে দিচ্ছি। অনুগ্রহ করে আপনার যে জিমেইল (Gmail) অ্যাকাউন্টে ১৫০ জিবি ক্লাউড স্টোরেজ ও এপিআই এক্সেস নিতে চান, সেই ইমেইল অ্যাড্রেসটি লিখে আমাদের এই হোয়াটসঅ্যাপে মেসেজ পাঠান। আমাদের টিম খুব দ্রুত আপনার অ্যাকাউন্টটি অ্যাক্টিভ করে এপিআই কি ও ড্রাইভ এক্সেস বুঝিয়ে দেবে।";
            whatsapp_queue($pdo, $cfg, $custWhatsapp, $customerMsg, $customerId);

            // খ. অ্যাডমিনের হোয়াটসঅ্যাপ নম্বরে অ্যালার্ট মেসেজ যাবে
            $adminWhatsapp = $cfg['whatsapp_admin_number'] ?? '01684355055';
            $adminMsg = "🚨 নতুন Google AI Pro অর্ডার! অর্ডার আইডি: #{$orderId}, গ্রাহকের নাম: {$custName}, মোবাইল: {$custWhatsapp}, প্ল্যান: {$planMonths} মাস ({$priceVal} ৳)। গ্রাহককে জিমেইল চেয়ে ম্যানুয়ালি অ্যাকাউন্ট বুঝিয়ে দিন।";
            whatsapp_queue($pdo, $cfg, $adminWhatsapp, $adminMsg, null);
        } else {
            $body = "Assalamu Alaikum {$order['name']},\n\n"
                  . "আপনার AutoMovie Pro অর্ডার #{$orderId} সফলভাবে অনুমোদিত হয়েছে এবং আজীবন লাইসেন্স সক্রিয় হয়েছে! 🎉\n\n"
                  . "লগইন ID: {$loginId}\n"
                  . "পাসওয়ার্ড: {$plainPass}\n"
                  . "লাইসেন্স টোকেন: {$token}\n\n"
                  . "🔒 সিকিউর ওয়ান-টাইম ডাউনলোড লিংক (মেয়াদ ৭২ ঘণ্টা):\n"
                  . "{$dlUrl}\n\n"
                  . "ইনস্টলের পর উপরের ID/পাসওয়ার্ড দিয়ে লগইন করুন। যেকোনো সহায়তায় আমাদের সাথে যোগাযোগ করুন।";
            whatsapp_queue($pdo, $cfg, (string) $order['whatsapp'], $body, $customerId);

            // ইমেইল ডেলিভারি (যদি গ্রাহকের ইমেইল থাকে)
            $custEmail = trim((string) ($order['email'] ?? ''));
            if (!empty($custEmail) && filter_var($custEmail, FILTER_VALIDATE_EMAIL)) {
                $emailSub = "AutoMovie Pro — আপনার লাইফটাইম লাইসেন্স ও সিকিউর ডাউনলোড লিংক (#{$orderId})";
                $emailBody = "আসসালামু আলাইকুম {$order['name']},\n\n"
                           . "AutoMovie Pro-তে আপনাকে স্বাগতম! আপনার অর্ডার #{$orderId} সফলভাবে অনুমোদিত হয়েছে এবং আজীবন মেয়াদের (Lifetime) লাইসেন্স অ্যাক্টিভ করা হয়েছে। 🎉\n\n"
                           . "আপনার লগইন তথ্য:\n"
                           . "------------------------------------\n"
                           . "👤 Login ID: {$loginId}\n"
                           . "🔑 Password: {$plainPass}\n"
                           . "🎫 License Token: {$token}\n"
                           . "------------------------------------\n\n"
                           . "🔒 সিকিউর ওয়ান-টাইম ইনস্টলার ডাউনলোড লিংক (৭২ ঘণ্টার মধ্যে ডাউনলোড করুন):\n"
                           . "📥 {$dlUrl}\n\n"
                           . "সফটওয়্যারটি ডাউনলোড করে ইনস্টল করুন এবং উপরোক্ত Login ID ও Password দিয়ে লগইন করুন। একক পিসিতে হার্ডওয়্যার লক স্বয়ংক্রিয়ভাবে সক্রিয় হবে।\n\n"
                           . "কোনো সহায়তা বা ওটিপির জন্য আমাদের সাথে WhatsApp-এ যোগাযোগ করুন।\n\n"
                           . "ধন্যবাদ,\nAutoMovie Pro টিম";
                $headers = "From: noreply@automoviepro.com\r\nReply-To: support@automoviepro.com\r\nContent-Type: text/plain; charset=UTF-8\r\n";
                @mail($custEmail, $emailSub, $emailBody, $headers);
            }
        }
    }

    return [
        'ok' => true,
        'token' => $token,
        'login_id' => $loginId,
        'password' => $plainPass,
        'customer_id' => $customerId,
        'tier' => $tier,
        'plan' => $tier,
        'download_token' => $dlToken,
        'download_url' => $dlUrl,
        'unlocked' => amp_customer_unlocked_langs($pdo, $customerId),
        'email_sent' => !empty($custEmail),
    ];
}

/**
 * Create a 72-hour one-time cryptographic expiring download token.
 */
function amp_create_download_token(PDO $pdo, ?int $orderId = null, ?int $customerId = null, string $product = 'software', int $validHours = 72): string
{
    $token = bin2hex(random_bytes(32));
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    $validHours = max(1, $validHours);

    if ($driver === 'sqlite') {
        $stmt = $pdo->prepare(
            "INSERT INTO download_tokens (token, order_id, customer_id, product, expires_at, is_used, download_count, max_downloads, created_at)
             VALUES (?, ?, ?, ?, datetime('now', '+' || ? || ' hours'), 0, 0, 1, datetime('now'))"
        );
        $stmt->execute([$token, $orderId, $customerId, $product, $validHours]);
    } else {
        $stmt = $pdo->prepare(
            "INSERT INTO download_tokens (token, order_id, customer_id, product, expires_at, is_used, download_count, max_downloads, created_at)
             VALUES (?, ?, ?, ?, DATE_ADD(NOW(), INTERVAL ? HOUR), 0, 0, 1, NOW())"
        );
        $stmt->execute([$token, $orderId, $customerId, $product, $validHours]);
    }
    return $token;
}

/**
 * Verify a download token (format, existence, 72h expiry, and one-time status).
 */
function amp_verify_download_token(PDO $pdo, string $token): array
{
    $token = trim($token);
    if ($token === '' || !preg_match('/^[a-f0-9]{64}$/i', $token)) {
        return ['valid' => false, 'reason' => 'invalid_format', 'record' => null, 'seconds_left' => 0];
    }

    $stmt = $pdo->prepare('SELECT * FROM download_tokens WHERE token = ? LIMIT 1');
    $stmt->execute([$token]);
    $rec = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$rec) {
        return ['valid' => false, 'reason' => 'not_found', 'record' => null, 'seconds_left' => 0];
    }

    $now = time();
    $expTime = strtotime((string) $rec['expires_at']) ?: 0;
    $secondsLeft = max(0, $expTime - $now);

    if ($secondsLeft <= 0) {
        return ['valid' => false, 'reason' => 'expired', 'record' => $rec, 'expires_at' => $rec['expires_at'], 'seconds_left' => 0];
    }

    if (!empty($rec['is_used']) || (int) ($rec['download_count'] ?? 0) >= (int) ($rec['max_downloads'] ?? 1)) {
        return ['valid' => false, 'reason' => 'already_used', 'record' => $rec, 'expires_at' => $rec['expires_at'], 'seconds_left' => $secondsLeft];
    }

    return ['valid' => true, 'reason' => 'ok', 'record' => $rec, 'expires_at' => $rec['expires_at'], 'seconds_left' => $secondsLeft];
}

/**
 * Mark a download token as consumed (one-time download protection).
 */
function amp_consume_download_token(PDO $pdo, string $token): bool
{
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    $nowSql = ($driver === 'sqlite') ? "datetime('now')" : "NOW()";
    $stmt = $pdo->prepare(
        "UPDATE download_tokens 
         SET is_used = 1, download_count = download_count + 1, used_at = {$nowSql} 
         WHERE token = ? AND is_used = 0"
    );
    $stmt->execute([$token]);
    return $stmt->rowCount() > 0;
}

function amp_approve_language_order(PDO $pdo, array $config, int $orderId): array
{
    $stmt = $pdo->prepare('SELECT * FROM language_orders WHERE id = ?');
    $stmt->execute([$orderId]);
    $order = $stmt->fetch();
    if (!$order) {
        return ['ok' => false, 'error' => 'order_not_found'];
    }
    if (($order['status'] ?? '') !== 'pending_payment') {
        return ['ok' => false, 'error' => 'not_pending'];
    }

    $customerId = (int) $order['customer_id'];
    $lang = (string) $order['lang_code'];
    $now = amp_sql_now($pdo);
    amp_unlock_customer_lang($pdo, $customerId, $lang, 'admin_approve');
    $pdo->prepare("UPDATE language_orders SET status = 'approved', approved_at = {$now} WHERE id = ?")
        ->execute([$orderId]);

    $cust = $pdo->prepare('SELECT name, whatsapp FROM customers WHERE id = ?');
    $cust->execute([$customerId]);
    $c = $cust->fetch();
    if ($c && !empty($c['whatsapp'])) {
        $catalog = amp_lang_catalog();
        $langName = $catalog[$lang] ?? $lang;
        $body = "AutoMovie Pro: আপনার {$langName} ভাষা অ্যাপ্রুভ হয়েছে। সফটওয়্যারে Language Sync চাপুন — বা অ্যাপ রিস্টার্ট করুন।";
        whatsapp_queue($pdo, $config, (string) $c['whatsapp'], $body, $customerId);
    }

    return [
        'ok' => true,
        'customer_id' => $customerId,
        'lang_code' => $lang,
        'unlocked' => amp_customer_unlocked_langs($pdo, $customerId),
    ];
}
