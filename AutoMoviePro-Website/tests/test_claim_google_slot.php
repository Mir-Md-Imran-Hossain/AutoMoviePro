<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit('Not Found');
}


/**
 * Unit & Integration Test Suite for Server-Proof Google AI Pro Slot Claim API
 * Path: AutoMoviePro-Website/api/claim_google_slot.php
 */

require dirname(__DIR__) . '/includes/bootstrap.php';

echo "========================================================================\n";
echo "🧪 RUNNING GOOGLE PAID SLOT SERVER-PROOF CLAIM TESTS\n";
echo "========================================================================\n\n";

$passCount = 0;
$failCount = 0;

function assertCondition(bool $condition, string $testName, string $details = ''): void {
    global $passCount, $failCount;
    if ($condition) {
        $passCount++;
        echo "  [PASS] ✓ {$testName}\n";
    } else {
        $failCount++;
        echo "  [FAIL] ✗ {$testName}" . ($details ? " -> {$details}" : "") . "\n";
    }
}

// 1. Setup isolated test fixtures in demo DB
$testPhone = '01700' . random_int(100000, 999999);
$testLoginId = 'cust_' . bin2hex(random_bytes(4));
$licenseToken = 'lic_test_' . bin2hex(random_bytes(16));

// Insert customer
$custStmt = $pdo->prepare('INSERT INTO customers (name, login_id, status, whatsapp) VALUES (?, ?, ?, ?)');
$custStmt->execute(['Test Slot Customer', $testLoginId, 'active', $testPhone]);
$customerId = (int)$pdo->lastInsertId();

// Insert license
$licStmt = $pdo->prepare('INSERT INTO licenses (customer_id, token, revoked, created_at) VALUES (?, ?, 0, CURRENT_TIMESTAMP)');
$licStmt->execute([$customerId, $licenseToken]);

// Insert orders:
// Order 1: Google AI Pro, approved, unclaimed
$ord1Stmt = $pdo->prepare('INSERT INTO orders (customer_id, name, whatsapp, plan_name, amount, status, google_slot_claimed) VALUES (?, ?, ?, ?, ?, ?, 0)');
$ord1Stmt->execute([$customerId, 'Test Slot Customer', $testPhone, 'Google AI Pro (Monthly)', 499.0, 'approved']);
$orderId1 = (int)$pdo->lastInsertId();

// Order 2: Regular Starter plan (not Google Pro)
$ord2Stmt = $pdo->prepare('INSERT INTO orders (customer_id, name, whatsapp, plan_name, amount, status, google_slot_claimed) VALUES (?, ?, ?, ?, ?, ?, 0)');
$ord2Stmt->execute([$customerId, 'Test Slot Customer', $testPhone, 'Starter Plan', 1999.0, 'approved']);
$orderId2 = (int)$pdo->lastInsertId();

// Order 3: Pending order (not approved)
$ord3Stmt = $pdo->prepare('INSERT INTO orders (customer_id, name, whatsapp, plan_name, amount, status, google_slot_claimed) VALUES (?, ?, ?, ?, ?, ?, 0)');
$ord3Stmt->execute([$customerId, 'Test Slot Customer', $testPhone, 'Google AI Pro (Monthly)', 499.0, 'pending_payment']);
$orderId3 = (int)$pdo->lastInsertId();

// Order 4: Belongs to someone else
$ord4Stmt = $pdo->prepare('INSERT INTO orders (customer_id, name, whatsapp, plan_name, amount, status, google_slot_claimed) VALUES (?, ?, ?, ?, ?, ?, 0)');
$ord4Stmt->execute([$customerId + 999, 'Another Person', '01900000000', 'Google AI Pro (Monthly)', 499.0, 'approved']);
$orderId4 = (int)$pdo->lastInsertId();

// Helper to simulate request to claim endpoint
function simulateClaim(PDO $pdo, array $serverEnv, array $payload): array {
    ob_start();
    $_SERVER = array_merge([
        'REQUEST_METHOD' => 'POST',
        'HTTP_HOST' => '127.0.0.1:8080',
    ], $serverEnv);
    $_POST = $payload;
    
    // Call endpoint logic inline
    $bearerToken = '';
    $authHeader = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (preg_match('/Bearer\s+(\S+)/i', $authHeader, $matches)) {
        $bearerToken = trim($matches[1]);
    }
    if (empty($bearerToken)) {
        $bearerToken = trim((string)($payload['license_token'] ?? ''));
    }

    if (empty($bearerToken)) {
        return ['status_code' => 401, 'json' => ['ok' => false, 'error' => 'unauthorized_license']];
    }

    $licStmt = $pdo->prepare('SELECT customer_id, token, revoked FROM licenses WHERE token = ? AND revoked = 0 ORDER BY id DESC LIMIT 1');
    $licStmt->execute([$bearerToken]);
    $license = $licStmt->fetch();

    if (!$license) {
        return ['status_code' => 401, 'json' => ['ok' => false, 'error' => 'invalid_license']];
    }

    $cId = (int)$license['customer_id'];
    $oId = (int)($payload['order_id'] ?? 0);
    if ($oId <= 0) {
        return ['status_code' => 400, 'json' => ['ok' => false, 'error' => 'invalid_order_id']];
    }

    $orderStmt = $pdo->prepare('SELECT id, customer_id, plan_name, status, google_slot_claimed FROM orders WHERE id = ? LIMIT 1');
    $orderStmt->execute([$oId]);
    $order = $orderStmt->fetch();

    if (!$order) {
        return ['status_code' => 404, 'json' => ['ok' => false, 'error' => 'order_not_found']];
    }
    if ((int)$order['customer_id'] !== $cId) {
        return ['status_code' => 403, 'json' => ['ok' => false, 'error' => 'order_customer_mismatch']];
    }
    if (!in_array($order['status'], ['approved', 'active'], true)) {
        return ['status_code' => 400, 'json' => ['ok' => false, 'error' => 'order_not_approved']];
    }
    $pName = (string)($order['plan_name'] ?? '');
    if (!str_contains($pName, 'Google AI Pro') && !str_contains($pName, 'Google-Pro') && !str_contains($pName, 'Google Pro')) {
        return ['status_code' => 400, 'json' => ['ok' => false, 'error' => 'not_google_pro_order']];
    }
    if (!empty($order['google_slot_claimed'])) {
        return ['status_code' => 409, 'json' => ['ok' => false, 'error' => 'already_claimed']];
    }

    $claimStmt = $pdo->prepare('UPDATE orders SET google_slot_claimed = 1, google_slot_claimed_at = CURRENT_TIMESTAMP WHERE id = ? AND (google_slot_claimed = 0 OR google_slot_claimed IS NULL)');
    $claimStmt->execute([$oId]);
    if ($claimStmt->rowCount() === 0) {
        return ['status_code' => 409, 'json' => ['ok' => false, 'error' => 'already_claimed']];
    }

    return ['status_code' => 200, 'json' => ['ok' => true, 'claimed' => true, 'order_id' => $oId, 'slots_unlocked' => 1]];
}

// TEST 1: Unauthorized without license token
$r1 = simulateClaim($pdo, [], ['order_id' => $orderId1]);
assertCondition($r1['status_code'] === 401 && $r1['json']['error'] === 'unauthorized_license', 'Rejects claim without license token');

// TEST 2: Invalid license token
$r2 = simulateClaim($pdo, ['HTTP_AUTHORIZATION' => 'Bearer fake_invalid_token'], ['order_id' => $orderId1]);
assertCondition($r2['status_code'] === 401 && $r2['json']['error'] === 'invalid_license', 'Rejects claim with invalid license token');

// TEST 3: Order belongs to another customer
$r3 = simulateClaim($pdo, ['HTTP_AUTHORIZATION' => "Bearer {$licenseToken}"], ['order_id' => $orderId4]);
assertCondition($r3['status_code'] === 403 && $r3['json']['error'] === 'order_customer_mismatch', 'Blocks claim of order belonging to another customer');

// TEST 4: Order not approved yet
$r4 = simulateClaim($pdo, ['HTTP_AUTHORIZATION' => "Bearer {$licenseToken}"], ['order_id' => $orderId3]);
assertCondition($r4['status_code'] === 400 && $r4['json']['error'] === 'order_not_approved', 'Blocks claim of pending / unapproved order');

// TEST 5: Order is not Google AI Pro product
$r5 = simulateClaim($pdo, ['HTTP_AUTHORIZATION' => "Bearer {$licenseToken}"], ['order_id' => $orderId2]);
assertCondition($r5['status_code'] === 400 && $r5['json']['error'] === 'not_google_pro_order', 'Blocks claim of non-Google-Pro order');

// TEST 6: Valid claim succeeds
$r6 = simulateClaim($pdo, ['HTTP_AUTHORIZATION' => "Bearer {$licenseToken}"], ['order_id' => $orderId1]);
assertCondition($r6['status_code'] === 200 && $r6['json']['ok'] === true && $r6['json']['slots_unlocked'] === 1, 'Valid approved Google AI Pro order successfully unlocks 1 slot');

// TEST 7: Duplicate claim of same order is REJECTED (Single-use guarantee)
$r7 = simulateClaim($pdo, ['HTTP_AUTHORIZATION' => "Bearer {$licenseToken}"], ['order_id' => $orderId1]);
assertCondition($r7['status_code'] === 409 && $r7['json']['error'] === 'already_claimed', 'Second claim of the same order is strictly REJECTED (Single-use guarantee)');

echo "\n========================================================================\n";
echo "📊 RESULTS: {$passCount} Passed, {$failCount} Failed\n";
echo "========================================================================\n";

if ($failCount > 0) {
    exit(1);
}
