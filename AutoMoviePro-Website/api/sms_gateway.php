<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';
require __DIR__ . '/../includes/billing.php';

$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'GET') {
    // Return recent SMS history for agent UI
    $limit = min(50, max(5, (int) ($_GET['limit'] ?? 20)));
    $stmt = $pdo->prepare('SELECT id, provider, sender_phone, sender_last_digits, txn_id, amount, is_matched, matched_order_id, created_at FROM agent_sms_inbox ORDER BY id DESC LIMIT ?');
    $stmt->bindValue(1, $limit, PDO::PARAM_INT);
    $stmt->execute();
    $rows = $stmt->fetchAll();
    echo json_encode(['ok' => true, 'sms_logs' => $rows], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($method !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method Not Allowed']);
    exit;
}

$raw = file_get_contents('php://input');
$data = json_decode($raw, true) ?? $_POST;

$provider = strtolower(trim((string) ($data['provider'] ?? 'bkash')));
$senderPhone = trim((string) ($data['sender_phone'] ?? ''));
$senderLastDigits = trim((string) ($data['sender_last_digits'] ?? ''));
if ($senderLastDigits === '' && strlen($senderPhone) >= 4) {
    $senderLastDigits = substr($senderPhone, -4);
}
$txnId = strtoupper(trim((string) ($data['txn_id'] ?? '')));
$amount = (float) ($data['amount'] ?? 0);
$rawMessage = trim((string) ($data['raw_message'] ?? ''));

if ($txnId === '' || $amount <= 0) {
    echo json_encode(['ok' => false, 'error' => 'Valid TxnID and Amount are required.']);
    exit;
}

// 1. Check if this SMS was already received
$check = $pdo->prepare('SELECT id, is_matched, matched_order_id FROM agent_sms_inbox WHERE txn_id = ? LIMIT 1');
$check->execute([$txnId]);
$existing = $check->fetch();

if ($existing) {
    echo json_encode([
        'ok' => true,
        'message' => 'SMS already ingested',
        'sms_id' => $existing['id'],
        'is_matched' => (bool) $existing['is_matched'],
        'matched_order_id' => $existing['matched_order_id']
    ]);
    exit;
}

// 2. Insert into agent_sms_inbox
$ins = $pdo->prepare('
    INSERT INTO agent_sms_inbox (provider, sender_phone, sender_last_digits, txn_id, amount, raw_message, is_matched, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 0, NOW())
');
$ins->execute([$provider, $senderPhone, $senderLastDigits, $txnId, $amount, $rawMessage]);
$smsId = (int) $pdo->lastInsertId();

// 3. Automated Reconciliation: Find matching pending_payment orders
$matchedOrderId = null;

// Try match by Txn ID first
$orderStmt = $pdo->prepare("SELECT id, customer_id, plan_name, amount, languages_json FROM orders WHERE status = 'pending_payment' AND UPPER(txn_id) = ? LIMIT 1");
$orderStmt->execute([$txnId]);
$order = $orderStmt->fetch();

// Fallback: match by sender last digits and exact amount
if (!$order && $senderLastDigits !== '') {
    $orderStmt2 = $pdo->prepare("SELECT id, customer_id, plan_name, amount, languages_json FROM orders WHERE status = 'pending_payment' AND sender_last_digits = ? AND ABS(amount - ?) < 1.0 LIMIT 1");
    $orderStmt2->execute([$senderLastDigits, $amount]);
    $order = $orderStmt2->fetch();
}

if ($order) {
    $matchedOrderId = (int) $order['id'];
    
    // Auto-approve the order using existing billing workflow
    $appRes = amp_approve_order($pdo, $matchedOrderId);
    
    // Update order status to active
    $upOrder = $pdo->prepare("UPDATE orders SET status = 'active', payment_method = ?, txn_id = ?, sender_last_digits = ?, updated_at = NOW() WHERE id = ?");
    $upOrder->execute([$provider, $txnId, $senderLastDigits, $matchedOrderId]);

    // Mark SMS as matched
    $upSms = $pdo->prepare('UPDATE agent_sms_inbox SET is_matched = 1, matched_order_id = ? WHERE id = ?');
    $upSms->execute([$matchedOrderId, $smsId]);
}

echo json_encode([
    'ok' => true,
    'sms_id' => $smsId,
    'txn_id' => $txnId,
    'amount' => $amount,
    'is_matched' => $matchedOrderId !== null,
    'matched_order_id' => $matchedOrderId,
    'message' => $matchedOrderId ? "অর্ডার #{$matchedOrderId} সফলভাবে অটো-ভেরিফাই ও অ্যাক্টিভ করা হয়েছে!" : "এসএমএস সফলভাবে সার্ভারে সংরক্ষিত হয়েছে। পেন্ডিং অর্ডার আসা মাত্র অটো-ম্যাচ হবে।"
], JSON_UNESCAPED_UNICODE);
