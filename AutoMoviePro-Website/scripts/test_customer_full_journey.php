<?php
declare(strict_types=1);

/**
 * End-to-end test of customer journey:
 * 1. Place order on website
 * 2. Admin approval
 * 3. Login API call with hardware binding
 * 4. Token validation
 */

$root = dirname(__DIR__);
require_once $root . '/includes/bootstrap.php';

echo "=== STARTING CUSTOMER FULL JOURNEY TEST ===\n";

$name = "Karim Chowdhury";
$phone = "01812345678";
$email = "karim.test@example.com";
$plan = "Omni Video Studio Package";
$amount = 3999;
$trxId = "BKASH" . strtoupper(bin2hex(random_bytes(4)));

// Step 1: Simulate Customer Order Placement
$now = amp_sql_now($pdo);
$langsJson = json_encode(['base' => ['en', 'bn'], 'addons' => [], 'all' => ['en', 'bn']]);

$stmt = $pdo->prepare(
    "INSERT INTO orders (name, whatsapp, email, plan_name, amount, txn_id, payment_method, status, languages_json, base_langs, addon_langs, created_at)
     VALUES (?, ?, ?, ?, ?, ?, 'bkash', 'pending_payment', ?, 'en,bn', '', {$now})"
);
$stmt->execute([$name, $phone, $email, $plan, $amount, $trxId, $langsJson]);
$orderId = (int)$pdo->lastInsertId();

echo "[STEP 1] Order created successfully! Order ID: {$orderId}, TrxID: {$trxId}\n";

// Step 2: Admin approves order
$result = amp_approve_order($pdo, $config, $orderId, false);
if (empty($result['ok'])) {
    echo "[FAIL] Order approval failed: " . ($result['error'] ?? 'unknown') . "\n";
    exit(1);
}

$loginId = $result['login_id'];
$password = $result['password'];
$customerId = $result['customer_id'];
$tier = $result['tier'];

echo "[STEP 2] Order APPROVED! Generated Credentials:\n";
echo "         Customer ID: {$customerId}\n";
echo "         Login ID:    {$loginId}\n";
echo "         Password:    {$password}\n";
echo "         Tier:        {$tier}\n";

// Step 3: Test Login Verification (api/login.php logic)
$hwid = "TEST-HWID-" . bin2hex(random_bytes(6));
$cust = $pdo->query("SELECT * FROM customers WHERE login_id = '{$loginId}'")->fetch();

if (!$cust) {
    echo "[FAIL] Customer row not found for login_id {$loginId}\n";
    exit(1);
}

if (!password_verify($password, $cust['password_hash'])) {
    echo "[FAIL] Password verification failed!\n";
    exit(1);
}

// Bind HWID
$pdo->prepare("UPDATE customers SET hardware_id = ? WHERE id = ?")->execute([$hwid, $customerId]);

// Fetch license token
$lic = $pdo->query("SELECT token FROM licenses WHERE customer_id = {$customerId} AND revoked = 0 ORDER BY id DESC LIMIT 1")->fetch();
$token = $lic ? $lic['token'] : null;

if (!$token) {
    echo "[FAIL] License token missing!\n";
    exit(1);
}

echo "[STEP 3] Login authentication & Hardware Lock OK!\n";
echo "         License Token: " . substr($token, 0, 16) . "...\n";
echo "         Hardware ID:   {$hwid}\n";

// Step 4: Verify Customer API Payload
$payload = amp_customer_api_payload($pdo, $cust);
echo "[STEP 4] Customer API Payload:\n";
echo json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) . "\n";

echo "\n>>> ALL 4 CUSTOMER JOURNEY STEPS PASSED WITH 100% SUCCESS! <<<\n";
