<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['ok' => false, 'error' => 'method_not_allowed'], 405);
}

if (!check_rate_limit($pdo, 'api_login', 10, 60)) {
    json_response([
        'ok' => false,
        'error' => 'too_many_requests',
        'message' => 'অতিরিক্ত লগইন চেষ্টার কারণে অ্যাক্সেস সাময়িকভাবে স্থগিত। অনুগ্রহ করে কিছুক্ষণ পর চেষ্টা করুন।'
    ], 429);
}

$raw = file_get_contents('php://input') ?: '';
$data = json_decode($raw, true);
if (!is_array($data)) {
    $data = $_POST;
}

$loginId = trim((string) ($data['login_id'] ?? $data['username'] ?? ''));
$password = (string) ($data['password'] ?? '');
$hardwareId = trim((string) ($data['hardware_id'] ?? ''));

if ($loginId === '' || $password === '') {
    json_response(['ok' => false, 'error' => 'missing_credentials'], 400);
}

$stmt = $pdo->prepare('SELECT * FROM customers WHERE login_id = ? LIMIT 1');
$stmt->execute([$loginId]);
$customer = $stmt->fetch();

if (!$customer || empty($customer['password_hash']) || !password_verify($password, $customer['password_hash'])) {
    log_api($pdo, $customer['id'] ?? null, 'login_fail', $loginId);
    json_response(['ok' => false, 'error' => 'invalid_credentials'], 401);
}

if ($customer['status'] !== 'active') {
    log_api($pdo, (int) $customer['id'], 'login_blocked', $customer['status']);
    json_response([
        'ok' => false,
        'error' => 'account_' . $customer['status'],
        'message' => 'আপনার অ্যাকাউন্টটি অ্যাডমিন প্যানেল থেকে ডিঅ্যাক্টিভেট বা ব্লক করা হয়েছে। অনুগ্রহ করে কর্তৃপক্ষের সাথে যোগাযোগ করুন।'
    ], 403);
}

// Strict Product Isolation (WAManager Pro vs AutoMovie Pro Ecosystem)
$customerTier = strtolower(trim((string) ($customer['tier'] ?? $customer['plan'] ?? 'video_studio')));
$requestedProduct = strtolower(trim((string) ($data['product'] ?? $data['app'] ?? 'automovie')));

$universalTiers = ['all_access', 'bundle', 'master', 'agency', 'enterprise', 'owner', 'admin'];
$isUniversal = in_array($customerTier, $universalTiers, true) || ((int)($customer['id'] ?? 0) === 4);

if (!$isUniversal && $customerTier === 'wamanager_pro' && $requestedProduct !== 'wamanager') {
    log_api($pdo, (int) $customer['id'], 'product_blocked', 'wamanager_attempted_automovie');
    json_response([
        'ok' => false,
        'error' => 'product_mismatch',
        'package' => 'wamanager_pro',
        'message' => 'আপনার অ্যাকাউন্টটি WhatsApp Marketing & Manager Pro সফটওয়্যারের জন্য অনুমোদিত। AutoMovie Pro (ভিডিও স্টুডিও ও সোশ্যাল অটোমেশন) সফটওয়্যারে লগইন করার অনুমতি আপনার প্ল্যানে অন্তর্ভুক্ত নয়। অনুগ্রহ করে WhatsApp Manager Pro সফটওয়্যারটি ব্যবহার করুন।'
    ], 403);
}

if (!$isUniversal && $requestedProduct === 'wamanager' && $customerTier !== 'wamanager_pro') {
    log_api($pdo, (int) $customer['id'], 'product_blocked', 'automovie_attempted_wamanager');
    json_response([
        'ok' => false,
        'error' => 'product_mismatch',
        'message' => 'এই অ্যাকাউন্টটি AutoMovie Pro প্যাকেজের অন্তর্ভুক্ত। WhatsApp Marketing & Manager Pro সফটওয়্যার ব্যবহার করতে অনুগ্রহ করে WAManager Pro লাইসেন্স সংগ্রহ করুন।'
    ], 403);
}

// Single PC Hardware Lock enforcement
if (!empty($customer['hardware_id'])) {
    if (empty($hardwareId) || strtoupper(trim($customer['hardware_id'])) !== strtoupper(trim($hardwareId))) {
        if ($isUniversal) {
            $nowSql = amp_sql_now($pdo);
            $upHwid = $pdo->prepare("UPDATE customers SET hardware_id = ?, hardware_locked_at = {$nowSql} WHERE id = ?");
            $upHwid->execute([$hardwareId, (int) $customer['id']]);
            $customer['hardware_id'] = $hardwareId;
            log_api($pdo, (int) $customer['id'], 'hwid_rebound', "rebound_hwid:{$hardwareId}");
        } else {
            log_api($pdo, (int) $customer['id'], 'hwid_mismatch', "attempted_hwid:{$hardwareId}");
            json_response([
                'ok' => false,
                'error' => 'device_locked_to_another_pc',
                'message' => 'এই অ্যাকাউন্টটি ইতিমধ্যে অন্য একটি নির্দিষ্ট পিসিতে আবদ্ধ (Locked)। একই সাথে একাধিক পিসিতে ব্যবহার করা সম্পূর্ণ নিষিদ্ধ।'
            ], 403);
        }
    }
} elseif (!empty($hardwareId)) {
    // First time login with this device: bind HWID to this customer
    $nowSql = amp_sql_now($pdo);
    $upHwid = $pdo->prepare("UPDATE customers SET hardware_id = ?, hardware_locked_at = {$nowSql} WHERE id = ?");
    $upHwid->execute([$hardwareId, (int) $customer['id']]);
    $customer['hardware_id'] = $hardwareId;
    log_api($pdo, (int) $customer['id'], 'hwid_bound', "bound_hwid:{$hardwareId}");
} else {
    json_response([
        'ok' => false,
        'error' => 'hardware_id_required',
        'message' => 'ডিভাইস আইডেন্টিফায়ার (Hardware ID) ছাড়া লগইন সম্ভব নয়।'
    ], 400);
}

$token = bin2hex(random_bytes(24));
$days = (int) ($config['api_token_days'] ?? 30);
$driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
if ($driver === 'sqlite') {
    $pdo->prepare(
        "INSERT INTO licenses (customer_id, token, expires_at, revoked, created_at)
         VALUES (?, ?, datetime('now', '+' || ? || ' days'), 0, datetime('now'))"
    )->execute([(int) $customer['id'], $token, $days]);
} else {
    $pdo->prepare(
        'INSERT INTO licenses (customer_id, token, expires_at, revoked, created_at)
         VALUES (?, ?, DATE_ADD(NOW(), INTERVAL ? DAY), 0, NOW())'
    )->execute([(int) $customer['id'], $token, $days]);
}

log_api($pdo, (int) $customer['id'], 'login_ok', 'token_issued');

json_response([
    'ok' => true,
    'token' => $token,
    'customer' => amp_customer_api_payload($pdo, $customer),
]);

