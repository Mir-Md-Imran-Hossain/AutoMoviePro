<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['ok' => false, 'error' => 'method_not_allowed'], 405);
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

// Single PC Hardware Lock enforcement
if (!empty($customer['hardware_id'])) {
    if (!empty($hardwareId) && strtoupper(trim($customer['hardware_id'])) !== strtoupper(trim($hardwareId))) {
        log_api($pdo, (int) $customer['id'], 'hwid_mismatch', "attempted_hwid:{$hardwareId}");
        json_response([
            'ok' => false,
            'error' => 'device_locked_to_another_pc',
            'message' => 'এই অ্যাকাউন্টটি ইতিমধ্যে অন্য একটি নির্দিষ্ট পিসিতে আবদ্ধ (Locked)। একই সাথে একাধিক পিসিতে ব্যবহার করা সম্পূর্ণ নিষিদ্ধ।'
        ], 403);
    }
} elseif (!empty($hardwareId)) {
    // First time login with this device: bind HWID to this customer
    $nowSql = amp_sql_now($pdo);
    $upHwid = $pdo->prepare("UPDATE customers SET hardware_id = ?, hardware_locked_at = {$nowSql} WHERE id = ?");
    $upHwid->execute([$hardwareId, (int) $customer['id']]);
    $customer['hardware_id'] = $hardwareId;
    log_api($pdo, (int) $customer['id'], 'hwid_bound', "bound_hwid:{$hardwareId}");
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

