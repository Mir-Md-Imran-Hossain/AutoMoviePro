<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require dirname(__DIR__) . '/includes/bootstrap.php';

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
    http_response_code(405);
    echo json_encode([
        'ok' => false,
        'error' => 'method_not_allowed',
        'message' => 'শুধুমাত্র POST মেথড গ্রহণযোগ্য।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// 1. Extract Bearer license token
$authHeader = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
$bearerToken = '';
if (preg_match('/Bearer\s+(\S+)/i', $authHeader, $matches)) {
    $bearerToken = trim($matches[1]);
}

$rawInput = file_get_contents('php://input');
$body = [];
if (!empty($rawInput)) {
    $decoded = json_decode($rawInput, true);
    if (is_array($decoded)) {
        $body = $decoded;
    }
}

if (empty($bearerToken)) {
    $bearerToken = trim((string)($body['license_token'] ?? $_POST['license_token'] ?? ''));
}

if (empty($bearerToken)) {
    http_response_code(401);
    echo json_encode([
        'ok' => false,
        'error' => 'unauthorized_license',
        'message' => 'অননুমোদিত: বৈধ লাইসেন্স Bearer টোকেন আবশ্যক।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// 2. Validate license token against database
$licStmt = $pdo->prepare('SELECT customer_id, token, revoked, expires_at FROM licenses WHERE token = ? AND revoked = 0 ORDER BY id DESC LIMIT 1');
$licStmt->execute([$bearerToken]);
$license = $licStmt->fetch();

if (!$license) {
    http_response_code(401);
    echo json_encode([
        'ok' => false,
        'error' => 'invalid_license',
        'message' => 'অবৈধ অথবা বাতিলকৃত লাইসেন্স টোকেন।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

if (!empty($license['expires_at']) && strtotime((string)$license['expires_at']) < time()) {
    http_response_code(401);
    echo json_encode([
        'ok' => false,
        'error' => 'license_expired',
        'message' => 'লাইসেন্সের মেয়াদ উত্তীর্ণ হয়ে গেছে।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$customerId = (int)$license['customer_id'];
$orderId = (int)($body['order_id'] ?? $_POST['order_id'] ?? 0);

if ($orderId <= 0) {
    http_response_code(400);
    echo json_encode([
        'ok' => false,
        'error' => 'invalid_order_id',
        'message' => 'অবৈধ অর্ডার আইডি প্রদান করা হয়েছে।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// 3. Find and verify order ownership & status
$orderStmt = $pdo->prepare('SELECT id, customer_id, plan_name, status, google_slot_claimed, google_slot_claimed_at FROM orders WHERE id = ? LIMIT 1');
$orderStmt->execute([$orderId]);
$order = $orderStmt->fetch();

if (!$order) {
    http_response_code(404);
    echo json_encode([
        'ok' => false,
        'error' => 'order_not_found',
        'message' => 'অর্ডারটি সিস্টেমে পাওয়া যায়নি।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

if ((int)$order['customer_id'] !== $customerId) {
    http_response_code(403);
    echo json_encode([
        'ok' => false,
        'error' => 'order_customer_mismatch',
        'message' => 'অর্ডারটি আপনার গ্রাহক অ্যাকাউন্টের সাথে সম্পর্কযুক্ত নয়।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$status = (string)($order['status'] ?? '');
if (!in_array($status, ['approved', 'active'], true)) {
    http_response_code(400);
    echo json_encode([
        'ok' => false,
        'error' => 'order_not_approved',
        'status' => $status,
        'message' => 'অর্ডারটি এখনো অনুমোদিত হয়নি।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$planName = (string)($order['plan_name'] ?? '');
if (!str_contains($planName, 'Google AI Pro') && !str_contains($planName, 'Google-Pro') && !str_contains($planName, 'Google Pro')) {
    http_response_code(400);
    echo json_encode([
        'ok' => false,
        'error' => 'not_google_pro_order',
        'plan_name' => $planName,
        'message' => 'এই অর্ডারটি Google AI Pro স্লট বৃদ্ধির জন্য প্রযোজ্য নয়।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

if (!empty($order['google_slot_claimed'])) {
    http_response_code(409);
    echo json_encode([
        'ok' => false,
        'error' => 'already_claimed',
        'claimed_at' => $order['google_slot_claimed_at'],
        'message' => 'এই অর্ডারের জন্য Google AI Pro স্লট ইতিমধ্যে একবার ক্লেইম করা হয়েছে। একই অর্ডার অন্য কোনো ডিভাইসে পুনরায় ব্যবহারযোগ্য নয়।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// 4. Atomically claim the slot (single-use guarantee)
$claimStmt = $pdo->prepare('UPDATE orders SET google_slot_claimed = 1, google_slot_claimed_at = CURRENT_TIMESTAMP WHERE id = ? AND (google_slot_claimed = 0 OR google_slot_claimed IS NULL)');
$claimStmt->execute([$orderId]);

if ($claimStmt->rowCount() === 0) {
    http_response_code(409);
    echo json_encode([
        'ok' => false,
        'error' => 'already_claimed',
        'message' => 'কনকারেন্ট রিকোয়েস্টে অর্ডারটি ইতিমধ্যে ক্লেইম করা হয়েছে।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// 5. Successful claim response
echo json_encode([
    'ok' => true,
    'claimed' => true,
    'order_id' => $orderId,
    'customer_id' => $customerId,
    'product' => $planName,
    'slots_unlocked' => 1,
    'message' => 'সার্ভার ভেরিফিকেশন সফল! ১টি Google AI Pro স্লট অনুমোদিত হয়েছে।'
], JSON_UNESCAPED_UNICODE);
