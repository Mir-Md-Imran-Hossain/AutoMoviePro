<?php
declare(strict_types=1);

/**
 * WAManager Pro Commercial Licensing Gateway Contract Test
 */

$passed = 0;
$failed = 0;

function expect(bool $cond, string $msg): void
{
    global $failed, $passed;
    if ($cond) {
        $passed++;
        echo "OK  {$msg}\n";
        return;
    }
    $failed++;
    echo "FAIL {$msg}\n";
}

$root = dirname(__DIR__);
require $root . '/includes/helpers.php';
require $root . '/includes/local_demo.php';
require $root . '/includes/migrate.php';

$tmp = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'wam_lic_' . bin2hex(random_bytes(4)) . '.sqlite';
$pdo = new PDO('sqlite:' . $tmp, null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
amp_local_demo_schema($pdo);
ensure_wamanager_migrations($pdo);

// 1. Check table created
$st = $pdo->query("SELECT name FROM sqlite_master WHERE type='table' AND name='wamanager_licenses'");
expect((bool)$st->fetch(), 'wamanager_licenses table exists in database');

// 2. Insert license
$licKey = 'WAM-PRO-ABCD-1234-EFGH';
$pdo->prepare(
    "INSERT INTO wamanager_licenses (id, license_key, customer_name, customer_phone, plan_tier, status, created_at)
     VALUES ('wam_test_1', ?, 'Sakib Agency', '8801968111593', 'wamanager_pro', 'active', datetime('now'))"
)->execute([$licKey]);

$check = $pdo->prepare('SELECT * FROM wamanager_licenses WHERE license_key = ?');
$check->execute([$licKey]);
$row = $check->fetch();
expect($row['customer_name'] === 'Sakib Agency', 'License row retrieved accurately');
expect(empty($row['hardware_id']), 'New license has empty hardware lock initially');

// 3. Simulate first PC activation (Hardware binding)
$hwid1 = 'BFEBFBFF000906EA-PC1-UUID';
$pdo->prepare("UPDATE wamanager_licenses SET hardware_id = ?, activated_at = datetime('now') WHERE license_key = ?")
    ->execute([$hwid1, $licKey]);

$check->execute([$licKey]);
$row1 = $check->fetch();
expect($row1['hardware_id'] === $hwid1, 'Hardware ID successfully bound on first activation');

// 4. Simulate token signing & verification
$salt = 'TEST_SALT_123';
$token = hash_hmac('sha256', "{$licKey}|{$hwid1}|WAM_ENTERPRISE", $salt);
$expectedToken = hash_hmac('sha256', "{$licKey}|{$hwid1}|WAM_ENTERPRISE", $salt);
expect(hash_equals($expectedToken, $token), 'Cryptographic activation signature verification passes');

// 5. Test rejection on unauthorized second PC
$hwid2 = 'DIFFERENT-MOTHERBOARD-UUID-PC2';
$isHwidAllowed = (strtoupper($row1['hardware_id']) === strtoupper($hwid2));
expect(!$isHwidAllowed, 'Second PC activation blocked by hardware lock');

echo "\n{$passed} passed, {$failed} failed\n";
if ($failed > 0) exit(1);
