<?php
declare(strict_types=1);

$root = dirname(__DIR__);
require_once $root . '/includes/bootstrap.php';

$loginId = "testuser_pro";
$plainPassword = "MoviePro@2026";
$hash = password_hash($plainPassword, PASSWORD_DEFAULT);
$tier = "video_studio";
$now = amp_sql_now($pdo);

// Delete existing test user if present
$pdo->prepare("DELETE FROM customers WHERE login_id = ?")->execute([$loginId]);

// Insert fresh customer with hardware_id = NULL
$stmt = $pdo->prepare(
    "INSERT INTO customers (name, whatsapp, email, login_id, password_hash, status, tier, plan, hardware_id, created_at, activated_at)
     VALUES ('Test Studio Master', '01968111593', 'test.master@automoviepro.com', ?, ?, 'active', ?, ?, NULL, {$now}, {$now})"
);
$stmt->execute([$loginId, $hash, $tier, $tier]);
$cid = (int)$pdo->lastInsertId();

// Issue 36500-day lifetime license token
$token = amp_issue_license($pdo, $cid, 36500);

// Unlock languages
amp_unlock_customer_lang($pdo, $cid, 'en', 'admin_grant');
amp_unlock_customer_lang($pdo, $cid, 'bn', 'admin_grant');
amp_unlock_customer_lang($pdo, $cid, 'hi', 'admin_grant');

echo "SUCCESSFULLY CREATED FRESH TEST CUSTOMER:\n";
echo "Customer ID: {$cid}\n";
echo "Login ID:    {$loginId}\n";
echo "Password:    {$plainPassword}\n";
echo "Tier:        {$tier}\n";
echo "Hardware ID: NULL (ready for automatic binding on first login)\n";
echo "License:     " . substr($token, 0, 16) . "...\n";
