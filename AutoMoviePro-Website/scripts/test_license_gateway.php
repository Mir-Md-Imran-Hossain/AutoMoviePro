<?php
declare(strict_types=1);

/**
 * License / subscription / app-gateway contract tests (SQLite, no Hostinger).
 * Run: C:\wamp64\bin\php\php8.3.28\php.exe scripts/test_license_gateway.php
 */
$failed = 0;
$passed = 0;

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

$_SERVER['HTTP_HOST'] = '127.0.0.1';
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
$_SERVER['REQUEST_METHOD'] = 'POST';

$root = dirname(__DIR__);
require $root . '/includes/helpers.php';
require $root . '/includes/local_demo.php';
require $root . '/includes/migrate.php';
require $root . '/includes/auth.php';
require $root . '/includes/whatsapp.php';
require $root . '/includes/billing.php';

$tmp = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'amp_gw_' . bin2hex(random_bytes(4)) . '.sqlite';
$pdo = new PDO('sqlite:' . $tmp, null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$pdo->exec('PRAGMA foreign_keys = ON');
amp_local_demo_schema($pdo);

$config = [
    'site_url' => 'https://automoviepro.com',
    'site_name' => 'AutoMovie Pro',
    'download_url' => 'https://automoviepro.com/downloads/AutoMoviePro-Setup.exe',
    'install_guide_url' => 'https://automoviepro.com/guide.html',
    'whatsapp_token' => '',
    'whatsapp_phone_id' => '',
    'api_token_days' => 3650,
];

$now = amp_sql_now($pdo);
$pdo->prepare(
    "INSERT INTO customers (name, whatsapp, email, status, created_at)
     VALUES ('Test Buyer', '8801684355055', 't@example.com', 'pending', {$now})"
)->execute();
$cid = (int) $pdo->lastInsertId();

$langsJson = json_encode([
    'base' => ['en', 'bn'],
    'addons' => ['hi'],
    'all' => ['en', 'bn', 'hi'],
], JSON_UNESCAPED_UNICODE);

$pdo->prepare(
    "INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, status, languages_json, base_langs, addon_langs, created_at)
     VALUES (?, 'Test Buyer', '8801684355055', 't@example.com', 'Lifetime Core', 3497, 'pending_payment', ?, 'en,bn', 'hi', {$now})"
)->execute([$cid, $langsJson]);
$orderId = (int) $pdo->lastInsertId();

$parsed = amp_order_lang_codes([
    'languages_json' => $langsJson,
    'base_langs' => 'en,bn',
    'addon_langs' => 'hi',
]);
expect($parsed === ['bn', 'hi'], 'order lang codes skip English and keep purchase langs');

$approved = amp_approve_order($pdo, $config, $orderId);
expect(!empty($approved['ok']), 'approve order ok');
expect(!empty($approved['login_id']) && str_starts_with((string) $approved['login_id'], 'AMP'), 'login id issued');
expect(strlen((string) $approved['password']) >= 8, 'password issued');

$unlocked = amp_customer_unlocked_langs($pdo, (int) $approved['customer_id']);
expect($unlocked === ['en', 'bn', 'hi'], 'purchase langs unlocked for app (en+bn+hi)');

$custRow = $pdo->query('SELECT * FROM customers WHERE id = ' . (int) $approved['customer_id'])->fetch();
expect($custRow['status'] === 'active', 'customer active after approve');
expect(password_verify((string) $approved['password'], (string) $custRow['password_hash']), 'password_verify matches desktop login');

$days = 3650;
$token = amp_issue_license($pdo, (int) $approved['customer_id'], $days);
expect(strlen($token) === 48, 'license token length');

$fromHeader = api_customer_from_token($pdo, $token);
expect(is_array($fromHeader) && (int) $fromHeader['id'] === (int) $approved['customer_id'], 'Bearer token resolves customer');

$_GET['token'] = $token;
expect(api_bearer_token() === $token, 'token fallback from query string (Hostinger header strip)');
unset($_GET['token']);

$payload = amp_customer_api_payload($pdo, $custRow);
expect(($payload['unlocked'] ?? []) === ['en', 'bn', 'hi'], 'login/me payload includes unlocked langs');
expect(($payload['plan'] ?? '') === 'lifetime', 'payload plan is lifetime');

amp_refresh_license($pdo, $token, 10);
$lic = $pdo->prepare('SELECT expires_at FROM licenses WHERE token = ?');
$lic->execute([$token]);
$exp = (string) $lic->fetchColumn();
expect($exp !== '', 'heartbeat refresh sets expiry');

$pdo->prepare("UPDATE licenses SET expires_at = datetime('now', '-1 day') WHERE token = ?")->execute([$token]);
expect(api_customer_from_token($pdo, $token) === null, 'expired token rejected');

amp_refresh_license($pdo, $token, 3650);
expect(is_array(api_customer_from_token($pdo, $token)), 'refresh restores valid token');

$pdo->prepare("UPDATE customers SET status = 'inactive' WHERE id = ?")->execute([(int) $approved['customer_id']]);
expect(api_customer_from_token($pdo, $token) === null, 'inactive subscription cannot use API');
$pdo->prepare("UPDATE customers SET status = 'active' WHERE id = ?")->execute([(int) $approved['customer_id']]);

$now = amp_sql_now($pdo);
$pdo->prepare(
    "INSERT INTO language_orders (customer_id, lang_code, amount, status, created_at)
     VALUES (?, 'ta', 499, 'pending_payment', {$now})"
)->execute([(int) $approved['customer_id']]);
$langOrderId = (int) $pdo->lastInsertId();
$langOk = amp_approve_language_order($pdo, $config, $langOrderId);
expect(!empty($langOk['ok']), 'addon language approve ok');
$unlocked2 = amp_customer_unlocked_langs($pdo, (int) $approved['customer_id']);
expect(in_array('ta', $unlocked2, true) && count($unlocked2) === 4, 'addon Tamil reaches the app catalog');

$jobNow = amp_sql_now($pdo);
$pdo->prepare(
    "INSERT INTO customer_jobs (customer_id, title, video_type, upload_status, created_at)
     VALUES (?, 'Demo Short', 'short', 'generated', {$jobNow})"
)->execute([(int) $approved['customer_id']]);
expect((int) $pdo->lastInsertId() > 0, 'jobs-sync table accepts desktop job rows');

log_api($pdo, (int) $approved['customer_id'], 'login_ok', 'token_issued');
$logCount = (int) $pdo->query('SELECT COUNT(*) FROM api_logs')->fetchColumn();
expect($logCount >= 1, 'api logs record gateway events');

$wa = (int) $pdo->query('SELECT COUNT(*) FROM whatsapp_outbox')->fetchColumn();
expect($wa >= 1, 'approval queues WhatsApp credentials for the customer');

@unlink($tmp);
echo "\n{$passed} passed, {$failed} failed\n";
exit($failed === 0 ? 0 : 1);
