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
$whatsapp = trim((string) ($data['whatsapp'] ?? ''));
$channel = strtolower(trim((string) ($data['channel'] ?? 'whatsapp'))); // whatsapp | telegram | email

$target = $whatsapp !== '' ? $whatsapp : ($loginId !== '' ? $loginId : $email);

if ($target === '') {
    json_response(['ok' => false, 'error' => 'missing_account_identifier', 'message' => 'ইউজার আইডি, WhatsApp নম্বর অথবা ইমেইল প্রদান করুন।'], 400);
}

// Clean phone digits if applicable
$digits = preg_replace('/\D+/', '', $target);
$digitsQuery = strlen($digits) >= 10 ? "%{$digits}%" : $target;

$stmt = $pdo->prepare(
    'SELECT * FROM customers 
     WHERE login_id = ? OR email = ? OR whatsapp = ? OR whatsapp LIKE ? 
     LIMIT 1'
);
$stmt->execute([$target, $target, $target, $digitsQuery]);
$customer = $stmt->fetch();

if (!$customer) {
    // Return friendly response without leaking user existence
    json_response([
        'ok' => true,
        'message' => 'যদি অ্যাকাউন্টটি বিদ্যমান থাকে, তবে আপনার WhatsApp/ইমেইলে ৬-ডিজিটের ভেরিফিকেশন কোড পাঠানো হয়েছে।'
    ]);
}

if ($customer['status'] !== 'active') {
    json_response([
        'ok' => false,
        'error' => 'account_blocked',
        'message' => 'এই অ্যাকাউন্টটি স্থগিত অবস্থায় রয়েছে। পাসওয়ার্ড রিসেট সম্ভব নয়।'
    ], 403);
}

// Generate 6-digit cryptographic OTP
$otp = (string) random_int(100000, 999999);
$now = amp_sql_now($pdo);

// 15 minutes expiration
$pdo->prepare(
    "UPDATE customers 
     SET otp_code = ?, otp_expires_at = DATE_ADD({$now}, INTERVAL 15 MINUTE) 
     WHERE id = ?"
)->execute([$otp, (int) $customer['id']]);

log_api($pdo, (int) $customer['id'], 'otp_requested', "target:{$target}, channel:{$channel}");

// 1. Deliver OTP via WhatsApp queue
$waNum = trim((string) ($customer['whatsapp'] ?? ''));
$cleanWa = preg_replace('/\D+/', '', $waNum);
if (str_starts_with($cleanWa, '01')) {
    $cleanWa = '88' . $cleanWa;
}
$waMsg = "AutoMovie Pro পাসওয়ার্ড রিসেট ভেরিফিকেশন কোড: {$otp}\nএই কোডটির মেয়াদ ১৫ মিনিট। অনুগ্রহ করে কারো সাথে কোডটি শেয়ার করবেন না।";

if (!empty($waNum)) {
    try {
        whatsapp_queue($pdo, $config, $waNum, $waMsg, (int) $customer['id']);
    } catch (\Throwable $e) {}
}

// 2. Deliver OTP via Email if present
$toEmail = trim((string) ($customer['email'] ?? ''));
if (!empty($toEmail) && filter_var($toEmail, FILTER_VALIDATE_EMAIL)) {
    $subject = "AutoMovie Pro - পাসওয়ার্ড রিসেট ভেরিফিকেশন কোড";
    $msgBody = "আসসালামু আলাইকুম,\n\nআপনার AutoMovie Pro অ্যাকাউন্টের পাসওয়ার্ড পরিবর্তনের জন্য ওটিপি কোড: {$otp}\nএই কোডটির মেয়াদ ১৫ মিনিট।\n\nআপনি যদি এটি অনুরোধ না করে থাকেন, তবে এই ইমেইলটি উপেক্ষা করুন।\n\nধন্যবাদ,\nAutoMovie Pro টিম";
    $headers = "From: noreply@automoviepro.com\r\nReply-To: support@automoviepro.com\r\nContent-Type: text/plain; charset=UTF-8\r\n";
    @mail($toEmail, $subject, $msgBody, $headers);
}

$adminWa = $config['whatsapp_admin_number'] ?? '8801968111593';
$waDirectUrl = "https://wa.me/{$adminWa}?text=" . rawurlencode("AutoMovie Pro Password Reset OTP for account: {$customer['login_id']}");

json_response([
    'ok' => true,
    'message' => 'আপনার WhatsApp নম্বর ও ইমেইলে ৬-সংখ্যার ওটিপি কোড পাঠানো হয়েছে।',
    'login_id' => $customer['login_id'],
    'wa_support_url' => $waDirectUrl,
    'delivered_to' => !empty($waNum) ? substr($waNum, 0, 4) . '***' . substr($waNum, -3) : 'registered_contacts',
    'debug_otp' => (defined('AMP_DEBUG') && AMP_DEBUG) ? $otp : null,
]);
