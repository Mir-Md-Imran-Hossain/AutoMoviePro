<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';

$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'GET') {
    // 1. Calculate total revenue received in agent inbox
    $totalInStmt = $pdo->query('SELECT COALESCE(SUM(amount), 0) FROM agent_sms_inbox');
    $totalIn = (float) $totalInStmt->fetchColumn();

    // 2. Calculate today's received
    $todayInStmt = $pdo->query('SELECT COALESCE(SUM(amount), 0) FROM agent_sms_inbox WHERE DATE(created_at) = CURDATE()');
    $todayIn = (float) $todayInStmt->fetchColumn();

    // 3. Calculate total withdrawn
    $withdrawnStmt = $pdo->query('SELECT COALESCE(SUM(amount), 0) FROM cash_withdrawals');
    $totalWithdrawn = (float) $withdrawnStmt->fetchColumn();

    // Net balance
    $netBalance = max(0.0, $totalIn - $totalWithdrawn);

    // Recent withdrawals
    $withListStmt = $pdo->query('SELECT id, agent_name, amount, notes, created_at FROM cash_withdrawals ORDER BY id DESC LIMIT 10');
    $withdrawals = $withListStmt->fetchAll();

    // Recent SMS
    $smsListStmt = $pdo->query('SELECT id, provider, sender_phone, sender_last_digits, txn_id, amount, is_matched, matched_order_id, created_at FROM agent_sms_inbox ORDER BY id DESC LIMIT 15');
    $recentSms = $smsListStmt->fetchAll();

    echo json_encode([
        'ok' => true,
        'ledger' => [
            'total_received' => $totalIn,
            'today_received' => $todayIn,
            'total_withdrawn' => $totalWithdrawn,
            'current_balance' => $netBalance,
        ],
        'withdrawals' => $withdrawals,
        'recent_transactions' => $recentSms
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($method === 'POST') {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true) ?? $_POST;

    $amount = (float) ($data['amount'] ?? 0);
    $notes = trim((string) ($data['notes'] ?? 'Cash withdrawal'));
    $agentName = trim((string) ($data['agent_name'] ?? 'জাহিদ ফার্মেসী / সিমি ড্রাগ হাউস'));

    if ($amount <= 0) {
        echo json_encode(['ok' => false, 'error' => 'টাকার পরিমাণ শূন্যের চেয়ে বেশি হতে হবে।']);
        exit;
    }

    $ins = $pdo->prepare('INSERT INTO cash_withdrawals (agent_name, amount, notes, created_at) VALUES (?, ?, ?, NOW())');
    $ins->execute([$agentName, $amount, $notes]);

    echo json_encode([
        'ok' => true,
        'message' => "৳ {$amount} টাকা উত্তোলন সফলভাবে লেজারে যুক্ত হয়েছে।",
        'withdrawal_id' => $pdo->lastInsertId()
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

http_response_code(405);
echo json_encode(['ok' => false, 'error' => 'Method Not Allowed']);
