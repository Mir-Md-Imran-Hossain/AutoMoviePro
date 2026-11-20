<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';

// Authentication Guard: require X-Agent-Key or valid admin session
$agentKeyHeader = trim((string) ($_SERVER['HTTP_X_AGENT_KEY'] ?? $_SERVER['HTTP_AUTHORIZATION'] ?? ''));
if (str_starts_with($agentKeyHeader, 'Bearer ')) {
    $agentKeyHeader = trim(substr($agentKeyHeader, 7));
}
if (empty($agentKeyHeader) && function_exists('getallheaders')) {
    $allHdrs = getallheaders();
    foreach ($allHdrs as $k => $v) {
        if (strcasecmp((string)$k, 'X-Agent-Key') === 0) {
            $agentKeyHeader = trim((string) $v);
            break;
        }
    }
}

$configuredKey = $config['agent_master_secret'] ?? getenv('AMP_AGENT_MASTER_SECRET') ?: '';
if (empty($configuredKey)) {
    $configuredKey = (string) setting($pdo, 'agent_master_secret', '');
}

$raw = file_get_contents('php://input');
$data = json_decode($raw ?: '', true);
if (!is_array($data)) {
    $data = $_POST;
}

// W-04: No query parameter key ($_GET['key']) allowed. Headers or POST body only.
$providedKey = trim((string) ($agentKeyHeader ?: (is_array($data) ? ($data['key'] ?? '') : ($_POST['key'] ?? ''))));
$isAuthorized = false;

if (!empty($configuredKey) && !amp_is_compromised_secret($configuredKey) && !empty($providedKey) && hash_equals($configuredKey, $providedKey)) {
    $isAuthorized = true;
}
// W-03: Use centralized admin_logged_in() helper
if (!$isAuthorized && admin_logged_in()) {
    $isAuthorized = true;
}

if (!$isAuthorized) {
    if (amp_is_compromised_secret($configuredKey) && !admin_logged_in()) {
        http_response_code(503);
        echo json_encode([
            'ok' => false,
            'error' => 'secret_unconfigured',
            'message' => 'মাস্টার এজেন্ট কি (Master Agent Key) কনফিগার করা হয়নি অথবা ডিফল্ট সিক্রেট সনাক্ত হয়েছে।'
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }
    http_response_code(401);
    echo json_encode([
        'ok' => false,
        'error' => 'unauthorized',
        'message' => 'Unauthorized access. Valid Agent Key or Admin Session required.'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'GET') {
    // 1. Calculate total revenue received in agent inbox
    $totalInStmt = $pdo->query('SELECT COALESCE(SUM(amount), 0) FROM agent_sms_inbox');
    $totalIn = (float) $totalInStmt->fetchColumn();

    // 2. Calculate today's received
    $today = date('Y-m-d');
    $todayInStmt = $pdo->prepare('SELECT COALESCE(SUM(amount), 0) FROM agent_sms_inbox WHERE DATE(created_at) = ?');
    $todayInStmt->execute([$today]);
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
    $amount = (float) ($data['amount'] ?? 0);
    $notes = trim((string) ($data['notes'] ?? 'Cash withdrawal'));
    $agentName = trim((string) ($data['agent_name'] ?? 'জাহিদ ফার্মেসী / সিমি ড্রাগ হাউস'));

    if ($amount <= 0) {
        echo json_encode(['ok' => false, 'error' => 'টাকার পরিমাণ শূন্যের চেয়ে বেশি হতে হবে।']);
        exit;
    }

    $nowTime = date('Y-m-d H:i:s');
    $ins = $pdo->prepare('INSERT INTO cash_withdrawals (agent_name, amount, notes, created_at) VALUES (?, ?, ?, ?)');
    $ins->execute([$agentName, $amount, $notes, $nowTime]);

    echo json_encode([
        'ok' => true,
        'message' => "৳ {$amount} টাকা উত্তোলন সফলভাবে লেজারে যুক্ত হয়েছে।",
        'withdrawal_id' => $pdo->lastInsertId()
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

http_response_code(405);
echo json_encode(['ok' => false, 'error' => 'Method Not Allowed']);
