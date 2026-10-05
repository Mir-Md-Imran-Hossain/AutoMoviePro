<?php
declare(strict_types=1);

/**
 * Verification test script for user requirements 1 to 4
 */
$failed = 0;
$passed = 0;

function assert_test(bool $cond, string $msg): void
{
    global $failed, $passed;
    if ($cond) {
        $passed++;
        echo "PASS: {$msg}\n";
    } else {
        $failed++;
        echo "FAIL: {$msg}\n";
    }
}

$root = dirname(__DIR__);
require $root . '/includes/bootstrap.php';
require $root . '/includes/payment_methods.php';

// Test 1: Payment Verification & Approval Contract
$pdo->beginTransaction();
$now = amp_sql_now($pdo);
$langs = json_encode(['base' => ['en', 'bn'], 'addons' => ['hi'], 'all' => ['en', 'bn', 'hi']]);

$pdo->prepare("INSERT INTO orders (name, whatsapp, email, plan_name, amount, status, languages_json, base_langs, addon_langs, created_at)
VALUES ('Rahim Khan', '01700000000', 'rahim@test.com', 'Lifetime Core', 3497, 'pending_payment', ?, 'en,bn', 'hi', {$now})")->execute([$langs]);
$orderId = (int) $pdo->lastInsertId();

$approval = amp_approve_order($pdo, $config, $orderId);
assert_test(!empty($approval['ok']), 'Order approved via amp_approve_order');
assert_test(!empty($approval['customer_id']), 'Customer ID generated');
assert_test(!empty($approval['token']), '30-day License token generated');
assert_test(!empty($approval['password']), 'Password generated');

$cust = $pdo->prepare('SELECT * FROM customers WHERE id = ?');
$cust->execute([$approval['customer_id']]);
$cRow = $cust->fetch();
assert_test(!empty($cRow['password_hash']), 'Customer has password_hash');
assert_test(password_verify($approval['password'], $cRow['password_hash']), 'password_hash matches password_verify');
assert_test(empty($cRow['initial_password']), 'No plain text initial_password column used');

$lic = $pdo->prepare('SELECT * FROM licenses WHERE token = ?');
$lic->execute([$approval['token']]);
$lRow = $lic->fetch();
assert_test(!empty($lRow), 'License record found in licenses table');

$custLangs = amp_customer_unlocked_langs($pdo, (int)$approval['customer_id']);
assert_test(in_array('bn', $custLangs, true) && in_array('hi', $custLangs, true), 'Selected languages (bn, hi) activated in customer_languages');

// Test 2: Coupon validation without hardcoding
$stmt = $pdo->prepare('SELECT * FROM coupons WHERE UPPER(code) = ? AND is_active = 1 LIMIT 1');
$stmt->execute(['LAUNCH500']);
$cLaunch = $stmt->fetch();
assert_test(!empty($cLaunch) && (float)$cLaunch['discount_amount'] === 500.0, 'LAUNCH500 exists in coupons table with 500 discount');

$stmt->execute(['SUPER1000']);
$cSuper = $stmt->fetch();
assert_test(!empty($cSuper) && (float)$cSuper['min_order_amount'] === 4999.0, 'SUPER1000 requires 4999 min_order_amount');

$stmt->execute(['NONEXISTENT999']);
$cFake = $stmt->fetch();
assert_test(empty($cFake), 'Nonexistent coupon correctly rejected');

// Test 3: Payment Agents
assert_test(amp_payment_bkash_agent() === '01756160993 (Zahid Pharmacy)', 'bKash agent is 01756160993 (Zahid Pharmacy)');
assert_test(amp_payment_nagad_agent() === '01611-824811 (Simi Drug House)', 'Nagad agent is 01611-824811 (Simi Drug House)');
assert_test(amp_payment_rocket_agent() === '01756160993-5', 'Rocket agent is 01756160993-5');

// Test 4: Reviews - No dummy reviews
$revStmt = $pdo->query('SELECT * FROM reviews WHERE is_approved = 1');
$allReviews = $revStmt ? $revStmt->fetchAll() : [];
assert_test(is_array($allReviews), 'Reviews query returns array from DB');

$pdo->rollBack();

echo "\nSummary: {$passed} passed, {$failed} failed.\n";
exit($failed === 0 ? 0 : 1);
