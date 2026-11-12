<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require dirname(__DIR__) . '/includes/bootstrap.php';

$orderId = (int) ($_GET['order_id'] ?? $_POST['order_id'] ?? 0);
$token = trim((string) ($_GET['token'] ?? $_POST['token'] ?? ''));
if ($orderId <= 0) {
    echo json_encode([
        'ok' => false,
        'error' => 'invalid_order_id'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$stmt = $pdo->prepare('SELECT id, customer_id, name, whatsapp, plan_name, amount, status, payment_method, txn_id, sender_last_digits, order_token FROM orders WHERE id = ? LIMIT 1');
$stmt->execute([$orderId]);
$order = $stmt->fetch();

if (!$order) {
    echo json_encode([
        'ok' => false,
        'error' => 'order_not_found'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$status = (string) ($order['status'] ?? 'pending_payment');
$isApproved = in_array($status, ['approved', 'active'], true);
$hasValidToken = amp_verify_order_token($pdo, $order, $token);

$response = [
    'ok' => true,
    'order_id' => (int) $order['id'],
    'status' => $status,
    'is_approved' => $isApproved,
    'payment_method' => $order['payment_method'],
    'txn_id' => $hasValidToken ? $order['txn_id'] : (!empty($order['txn_id']) ? 'REDACTED' : null),
];

if (!$hasValidToken) {
    $response['auth_required'] = true;
    if ($isApproved) {
        $response['error'] = 'unauthorized_token_required';
        $response['message'] = 'Valid order token is required to view credentials and license key.';
        $response['customer'] = [
            'name' => $order['name'],
            'login_id' => 'REDACTED',
            'status' => 'active',
        ];
        $response['license_token'] = null;
        $response['download_url'] = null;
        echo json_encode($response, JSON_UNESCAPED_UNICODE);
        exit;
    }
}

if ($isApproved) {

    $customerId = (int) ($order['customer_id'] ?? 0);
    $custStmt = $pdo->prepare('SELECT id, name, login_id, status, tier, plan FROM customers WHERE id = ? LIMIT 1');
    $custStmt->execute([$customerId]);
    $customer = $custStmt->fetch();

    $licStmt = $pdo->prepare('SELECT token, expires_at FROM licenses WHERE customer_id = ? AND revoked = 0 ORDER BY id DESC LIMIT 1');
    $licStmt->execute([$customerId]);
    $license = $licStmt->fetch();

    $unlocked = $customerId > 0 ? amp_customer_unlocked_langs($pdo, $customerId) : [];
    $isGooglePro = str_contains((string)($order['plan_name'] ?? ''), 'Google AI Pro');
    $tier = $customer['tier'] ?? $customer['plan'] ?? amp_determine_order_tier($order);
    $dlToken = amp_get_active_download_token($pdo, (int)$order['id'], $customerId);

    $response['customer'] = [
        'name' => $customer['name'] ?? $order['name'],
        'login_id' => $customer['login_id'] ?? null,
        'status' => $customer['status'] ?? 'active',
        'tier' => $tier,
        'plan' => $tier,
    ];
    $response['license_token'] = $license['token'] ?? null;
    $response['expires_at'] = $license['expires_at'] ?? null;
    $response['unlocked_languages'] = $unlocked;
    $response['download_token'] = $dlToken;
    $response['download_url'] = '/download.php?token=' . $dlToken;
    $response['is_google_pro'] = $isGooglePro;
}

echo json_encode($response, JSON_UNESCAPED_UNICODE);
