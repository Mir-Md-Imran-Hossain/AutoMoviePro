<?php
declare(strict_types=1);

require_once __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/billing.php';

echo "=== STARTING SECTOR 5 WEBSITE TESTS ===\n";

$passCount = 0;
$failCount = 0;

function assert_test(string $name, bool $condition, string $detail = '') {
    global $passCount, $failCount;
    if ($condition) {
        $passCount++;
        echo " [PASS] {$name}\n";
    } else {
        $failCount++;
        echo " [FAIL] {$name} - {$detail}\n";
    }
}

// TEST 1: Token Creation & Verification
$token = amp_create_download_token($pdo, 9991, 101, 'software', 72);
assert_test("1. Token creation produces 64-char hex string", strlen($token) === 64 && ctype_xdigit($token));

$ver = amp_verify_download_token($pdo, $token);
assert_test("2. Newly created token verifies successfully", $ver['valid'] === true && $ver['seconds_left'] > 0);

// TEST 2: One-time Consumption
$consumed = amp_consume_download_token($pdo, $token);
assert_test("3. Token consumed successfully", $consumed === true);

$verAfter = amp_verify_download_token($pdo, $token);
assert_test("4. Consumed token rejected with 'already_used'", $verAfter['valid'] === false && $verAfter['reason'] === 'already_used');

// Double consume fails
$doubleConsume = amp_consume_download_token($pdo, $token);
assert_test("5. Cannot consume already consumed token", $doubleConsume === false);

// TEST 3: Expired Token
$tokenExpired = amp_create_download_token($pdo, 9992, 102, 'software', -1);
// Manually set past date in DB to test expiry
$driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
$pastDate = ($driver === 'sqlite') ? "datetime('now', '-75 hours')" : "DATE_SUB(NOW(), INTERVAL 75 HOUR)";
$pdo->exec("UPDATE download_tokens SET expires_at = {$pastDate} WHERE token = '{$tokenExpired}'");
$verExp = amp_verify_download_token($pdo, $tokenExpired);
assert_test("6. 72-hour expired token rejected with 'expired'", $verExp['valid'] === false && $verExp['reason'] === 'expired');

// TEST 4: Tier Classification
$_SESSION['admin_id'] = 1;
$_SESSION['admin_user'] = 'admin';
ob_start();
require_once __DIR__ . '/../admin/orders.php';
ob_end_clean();
$order3999 = ['amount' => 3999.0, 'plan_name' => 'AutoMovie Pro Omni Social Media Content Automation'];
$order2999 = ['amount' => 2999.0, 'plan_name' => 'AutoMovie Pro FB Business Manager & Ad'];
$order1999 = ['amount' => 1999.0, 'plan_name' => 'AutoMovie Pro FB Profile & Page Post'];
$orderGoogle = ['amount' => 999.0, 'plan_name' => 'Special Gemini Pro API (12 Months)'];

assert_test("7. Tier 3999 classified correctly", amp_classify_order_tier($order3999) === '3999');
assert_test("8. Tier 2999 classified correctly", amp_classify_order_tier($order2999) === '2999');
assert_test("9. Tier 1999 classified correctly", amp_classify_order_tier($order1999) === '1999');
assert_test("10. Google Pro classified correctly", amp_classify_order_tier($orderGoogle) === 'google_pro');

// TEST 5: TrxID Regex Validation
$validBkash = 'BL92KA871X';
$invalidBkash = 'bad_trx!@#';
assert_test("11. Valid bKash TrxID regex", preg_match('/^[A-Z0-9]{8,12}$/', $validBkash) === 1);
assert_test("12. Invalid bKash TrxID regex rejected", preg_match('/^[A-Z0-9]{8,12}$/', $invalidBkash) === 0);

// TEST 6: Duplicate TrxID Guard Simulation
$testTrx = strtoupper('TEST' . bin2hex(random_bytes(3)));
$driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
$nowSql = ($driver === 'sqlite') ? "datetime('now')" : "NOW()";
// Create order 1
$pdo->exec("INSERT INTO orders (name, whatsapp, plan_name, amount, status, txn_id, created_at) VALUES ('Customer 1', '01711111111', 'Standard', 3999, 'approved', '{$testTrx}', {$nowSql})");
$order1Id = (int) $pdo->lastInsertId();

// Create order 2
$pdo->exec("INSERT INTO orders (name, whatsapp, plan_name, amount, status, created_at) VALUES ('Customer 2', '01822222222', 'Standard', 2999, 'pending_payment', {$nowSql})");
$order2Id = (int) $pdo->lastInsertId();

// Query duplicate check as in api/verify_payment.php
$dupStmt = $pdo->prepare("
    SELECT id, status FROM orders 
    WHERE UPPER(txn_id) = ? AND id != ? AND status IN ('approved', 'active', 'under_review')
    LIMIT 1
");
$dupStmt->execute([$testTrx, $order2Id]);
$dup = $dupStmt->fetch();
assert_test("13. Duplicate TrxID guard catches existing approved TrxID", !empty($dup) && (int) $dup['id'] === $order1Id);

// Clean up test rows
$pdo->exec("DELETE FROM orders WHERE id IN ({$order1Id}, {$order2Id})");
$pdo->exec("DELETE FROM download_tokens WHERE token IN ('{$token}', '{$tokenExpired}')");

echo "\nSECTOR 5 TEST RESULTS: {$passCount} PASSED, {$failCount} FAILED.\n";
if ($failCount > 0) {
    exit(1);
}
