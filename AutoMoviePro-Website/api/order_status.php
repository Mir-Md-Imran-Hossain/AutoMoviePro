<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require dirname(__DIR__) . '/includes/bootstrap.php';

$orderId = (int) ($_GET['order_id'] ?? $_POST['order_id'] ?? 0);
if ($orderId <= 0) {
    echo json_encode([
        'ok' => false,
        'error' => 'invalid_order_id'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$stmt = $pdo->prepare('SELECT id, customer_id, name, whatsapp, plan_name, amount, status, payment_method, txn_id, sender_last_digits FROM orders WHERE id = ? LIMIT 1');
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

$response = [
    'ok' => true,
    'order_id' => (int) $order['id'],
    'status' => $status,
    'is_approved' => $isApproved,
    'payment_method' => $order['payment_method'],
    'txn_id' => $order['txn_id'],
];

if ($isApproved) {
    $customerId = (int) ($order['customer_id'] ?? 0);
    $custStmt = $pdo->prepare('SELECT id, name, login_id, status FROM customers WHERE id = ? LIMIT 1');
    $custStmt->execute([$customerId]);
    $customer = $custStmt->fetch();

    $licStmt = $pdo->prepare('SELECT token, expires_at FROM licenses WHERE customer_id = ? AND revoked = 0 ORDER BY id DESC LIMIT 1');
    $licStmt->execute([$customerId]);
    $license = $licStmt->fetch();

    $unlocked = $customerId > 0 ? amp_customer_unlocked_langs($pdo, $customerId) : [];
    $isGooglePro = str_contains((string)($order['plan_name'] ?? ''), 'Google AI Pro');

    $response['customer'] = [
        'name' => $customer['name'] ?? $order['name'],
        'login_id' => $customer['login_id'] ?? null,
        'status' => $customer['status'] ?? 'active',
    ];
    $response['license_token'] = $license['token'] ?? null;
    $response['expires_at'] = $license['expires_at'] ?? null;
    $response['unlocked_languages'] = $unlocked;
    $response['download_url'] = '/downloads/AutoMoviePro_Installer_Latest.exe';
    $response['is_google_pro'] = $isGooglePro;
}

echo json_encode($response, JSON_UNESCAPED_UNICODE);
