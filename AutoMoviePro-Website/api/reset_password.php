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

$loginId = trim((string) ($data['login_id'] ?? ''));
$email = trim((string) ($data['email'] ?? ''));
$otp = trim((string) ($data['otp'] ?? ''));
$newPassword = (string) ($data['new_password'] ?? '');

if (($loginId === '' && $email === '') || $otp === '' || $newPassword === '') {
    json_response(['ok' => false, 'error' => 'missing_parameters', 'message' => 'ইউজার আইডি, ওটিপি এবং নতুন পাসওয়ার্ড আবশ্যক।'], 400);
}

if (strlen($newPassword) < 6) {
    json_response(['ok' => false, 'error' => 'password_too_short', 'message' => 'পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।'], 400);
}

if ($loginId !== '') {
    $stmt = $pdo->prepare('SELECT * FROM customers WHERE login_id = ? LIMIT 1');
    $stmt->execute([$loginId]);
} else {
    $stmt = $pdo->prepare('SELECT * FROM customers WHERE email = ? LIMIT 1');
    $stmt->execute([$email]);
}

$customer = $stmt->fetch();
if (!$customer) {
    json_response(['ok' => false, 'error' => 'user_not_found', 'message' => 'অ্যাকাউন্টটি খুঁজে পাওয়া যায়নি।'], 404);
}

if ($customer['status'] !== 'active') {
    json_response(['ok' => false, 'error' => 'account_blocked', 'message' => 'এই অ্যাকাউন্টটি স্থগিত। পাসওয়ার্ড পরিবর্তন সম্ভব নয়।'], 403);
}

// Validate OTP
if (empty($customer['otp_code']) || empty($customer['otp_expires_at'])) {
    json_response(['ok' => false, 'error' => 'no_otp_requested', 'message' => 'কোনো ওটিপি কোড ইস্যু করা হয়নি। প্রথমে ওটিপি রিকোয়েস্ট করুন।'], 400);
}

if (strtotime((string) $customer['otp_expires_at']) < time()) {
    json_response(['ok' => false, 'error' => 'otp_expired', 'message' => 'ওটিপি কোডের মেয়াদ উত্তীর্ণ হয়ে গেছে। দয়া করে নতুন কোড নিন।'], 400);
}

if (trim((string) $customer['otp_code']) !== $otp) {
    log_api($pdo, (int) $customer['id'], 'otp_verify_failed', "entered_otp:{$otp}");
    json_response(['ok' => false, 'error' => 'invalid_otp', 'message' => 'ভুল ওটিপি কোড প্রদান করেছেন। পুনরায় চেষ্টা করুন।'], 400);
}

// Update password hash and clear OTP
$newHash = password_hash($newPassword, PASSWORD_DEFAULT);
$upStmt = $pdo->prepare('UPDATE customers SET password_hash = ?, otp_code = NULL, otp_expires_at = NULL WHERE id = ?');
$upStmt->execute([$newHash, (int) $customer['id']]);

// Revoke older active licenses so user logs in afresh on approved device
$pdo->prepare('UPDATE licenses SET revoked = 1 WHERE customer_id = ?')->execute([(int) $customer['id']]);

log_api($pdo, (int) $customer['id'], 'password_reset_success', 'password_updated_via_otp');

json_response([
    'ok' => true,
    'message' => 'পাসওয়ার্ড সফলভাবে পরিবর্তিত হয়েছে! এখন নতুন পাসওয়ার্ড দিয়ে সফটওয়্যারে লগইন করুন।'
]);
