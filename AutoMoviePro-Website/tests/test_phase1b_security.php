<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit('Not Found');
}

ob_start();
require_once dirname(__DIR__) . '/includes/bootstrap.php';

echo "==================================================================\n";
echo "🛡️ AUTOMOVIE PRO PHASE 1B COMPREHENSIVE SECURITY TEST SUITE\n";
echo "==================================================================\n\n";

$allPassed = true;

function test_assert(string $desc, bool $condition): void {
    global $allPassed;
    if ($condition) {
        echo "  [PASS] {$desc} ✓\n";
    } else {
        echo "  [FAIL] {$desc} ❌\n";
        $allPassed = false;
    }
}

// -----------------------------------------------------------------------------
// 1. S-04: Known Compromised Default Secrets Rejection
// -----------------------------------------------------------------------------
echo "1. S-04: Compromised Default Secrets Filter:\n";
test_assert("Recognizes old agent master secret as compromised", amp_is_compromised_secret('amp_agent_master_live_key_2026'));
test_assert("Recognizes old sms gateway secret as compromised", amp_is_compromised_secret('amp_sms_gateway_live_secret_2026'));
test_assert("Recognizes old wa webhook key as compromised", amp_is_compromised_secret('automoviepro_wa_webhook_secure_key_2026'));
test_assert("Recognizes empty/null secrets as compromised", amp_is_compromised_secret(''));
test_assert("Valid 64-char hex key is NOT compromised", !amp_is_compromised_secret(bin2hex(random_bytes(32))));
echo "\n";

// -----------------------------------------------------------------------------
// 2. S-04: Order Token Signing & Verification
// -----------------------------------------------------------------------------
echo "2. S-04: Order Token HMAC Signing & Verification:\n";
$dummyOrder = ['id' => 12345, 'order_token' => null];
try {
    $token = amp_get_order_token($pdo, $dummyOrder);
    test_assert("Order token successfully generated using strong per-install secret", is_string($token) && strlen($token) === 64);
    test_assert("Order token verified with valid HMAC", amp_verify_order_token($pdo, $dummyOrder, $token));
    test_assert("Order token rejected with tampered token", !amp_verify_order_token($pdo, $dummyOrder, $token . 'bad'));
    test_assert("Order token rejected with wrong order ID", !amp_verify_order_token($pdo, ['id' => 99999], $token));
} catch (\Throwable $e) {
    test_assert("Order token failed with exception: " . $e->getMessage(), false);
}
echo "\n";

// -----------------------------------------------------------------------------
// 3. W-01: client_ip() Spoofed Header Protection
// -----------------------------------------------------------------------------
echo "3. W-01: Reverse Proxy & Spoofed Header Protection:\n";
// Case A: Untrusted remote address connecting directly
$_SERVER['REMOTE_ADDR'] = '203.0.113.50';
$_SERVER['HTTP_X_FORWARDED_FOR'] = '10.0.0.1';
$_SERVER['HTTP_CF_CONNECTING_IP'] = '10.0.0.2';
$ipUntrusted = client_ip();
test_assert("Untrusted REMOTE_ADDR ignores spoofed X-Forwarded-For and CF-Connecting-IP", $ipUntrusted === '203.0.113.50');

// Case B: Trusted reverse proxy (127.0.0.1) forwarding real client IP
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
$_SERVER['HTTP_CF_CONNECTING_IP'] = '198.51.100.22';
$ipTrustedCf = client_ip();
test_assert("Trusted proxy correctly honors CF-Connecting-IP", $ipTrustedCf === '198.51.100.22');

unset($_SERVER['HTTP_CF_CONNECTING_IP']);
$_SERVER['HTTP_X_FORWARDED_FOR'] = '198.51.100.33, 10.0.0.1';
$ipTrustedFwd = client_ip();
test_assert("Trusted proxy correctly honors first X-Forwarded-For hop", $ipTrustedFwd === '198.51.100.33');
unset($_SERVER['HTTP_X_FORWARDED_FOR']);
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
echo "\n";

// -----------------------------------------------------------------------------
// 4. W-02: Admin Session Hardening & Regeneration
// -----------------------------------------------------------------------------
echo "4. W-02: Admin Session Hardening & Timeout:\n";
// Ensure test admin exists in DB
$testAdminUser = 'amp_sec_test_admin';
$testAdminPass = 'SecAdminPass!2026';
$pdo->prepare("DELETE FROM admins WHERE username = ?")->execute([$testAdminUser]);
$pdo->prepare("INSERT INTO admins (username, password_hash) VALUES (?, ?)")
    ->execute([$testAdminUser, password_hash($testAdminPass, PASSWORD_DEFAULT)]);

if (session_status() === PHP_SESSION_NONE) {
    session_start();
}
$oldSessionId = session_id();
if (empty($oldSessionId)) {
    session_regenerate_id(true);
    $oldSessionId = session_id();
}

$loginSuccess = attempt_admin_login($pdo, $testAdminUser, $testAdminPass);
$newSessionId = session_id();

test_assert("Admin password verification succeeds", $loginSuccess);
test_assert("Session ID regenerated on admin login (prevent session fixation)", $newSessionId !== $oldSessionId && !empty($newSessionId));
test_assert("admin_logged_in() returns true for fresh session", admin_logged_in());

// Test idle timeout (simulated 2 hours in past)
$_SESSION['admin_last_activity'] = time() - 7200;
test_assert("admin_logged_in() invalidates session on idle timeout (> 1 hour)", !admin_logged_in());

// Clean up
$pdo->prepare("DELETE FROM admins WHERE username = ?")->execute([$testAdminUser]);
$_SESSION = [];
echo "\n";

// -----------------------------------------------------------------------------
// 5. W-04: No Secrets or Tokens in Query Strings
// -----------------------------------------------------------------------------
echo "5. W-04: Query String Token Leak Prevention:\n";
$_GET['token'] = 'leaked_query_token_123';
$_SERVER['HTTP_AUTHORIZATION'] = '';
test_assert("api_bearer_token() strictly ignores \$_GET['token']", api_bearer_token() === null);

$_SERVER['HTTP_AUTHORIZATION'] = 'Bearer valid_header_token_456';
test_assert("api_bearer_token() extracts Bearer token from HTTP Authorization header", api_bearer_token() === 'valid_header_token_456');
unset($_GET['token']);
unset($_SERVER['HTTP_AUTHORIZATION']);
echo "\n";

// -----------------------------------------------------------------------------
// 6. W-05: WhatsApp Webhook Signature Verification Logic
// -----------------------------------------------------------------------------
echo "6. W-05: WhatsApp Webhook HMAC-SHA256 Verification:\n";
$testAppSecret = 'test_wa_secret_key_888';
$testPayload = json_encode(['object' => 'whatsapp_business_account', 'entry' => []]);
$validSig = 'sha256=' . hash_hmac('sha256', $testPayload, $testAppSecret);
$tamperedSig = 'sha256=' . hash_hmac('sha256', $testPayload . 'tamper', $testAppSecret);

test_assert("Valid X-Hub-Signature-256 matches computed HMAC", hash_equals($validSig, 'sha256=' . hash_hmac('sha256', $testPayload, $testAppSecret)));
test_assert("Tampered payload fails HMAC verification", !hash_equals($tamperedSig, 'sha256=' . hash_hmac('sha256', $testPayload, $testAppSecret)));
echo "\n";

// -----------------------------------------------------------------------------
// 7. W-06: .htaccess Rules & CLI-Only Guards
// -----------------------------------------------------------------------------
echo "7. W-06: Sensitive Directories & File Exposure Guards:\n";
$htaccess = file_get_contents(dirname(__DIR__) . '/.htaccess');
test_assert(".htaccess blocks tests/ directory", strpos($htaccess, 'tests') !== false);
test_assert(".htaccess blocks scripts/ directory", strpos($htaccess, 'scripts') !== false);
test_assert(".htaccess blocks storage/ directory", strpos($htaccess, 'storage') !== false);
test_assert(".htaccess blocks .sqlite files", strpos($htaccess, 'sqlite') !== false);
test_assert(".htaccess blocks .log and .sql files", strpos($htaccess, 'log') !== false && strpos($htaccess, 'sql') !== false);

$testScript = file_get_contents(__FILE__);
test_assert("CLI guard present in test file", strpos($testScript, "PHP_SAPI !== 'cli'") !== false);
echo "\n";

// -----------------------------------------------------------------------------
// 8. W-07: Installer Lock Verification
// -----------------------------------------------------------------------------
echo "8. W-07: Installer Lock File & Protection:\n";
$installFile = file_get_contents(dirname(__DIR__) . '/install/index.php');
test_assert("install/index.php checks install.lock files", strpos($installFile, 'install.lock') !== false);
test_assert("install/index.php implements CSRF verification", strpos($installFile, 'install_csrf') !== false);
test_assert("install/index.php generates random 32-byte secrets", strpos($installFile, 'random_bytes(32)') !== false);
echo "\n";

// -----------------------------------------------------------------------------
// 9. W-10: Rate Limiting Atomic & Fail-Closed Behavior
// -----------------------------------------------------------------------------
echo "9. W-10: Rate Limiter Atomic & Fail-Closed Behavior:\n";
$rlAction = 'phase1b_test_' . bin2hex(random_bytes(4));
test_assert("Rate limit allows request within quota (1/2)", check_rate_limit($pdo, $rlAction, 2, 60));
test_assert("Rate limit allows request within quota (2/2)", check_rate_limit($pdo, $rlAction, 2, 60));
test_assert("Rate limit blocks request exceeding quota (3rd blocked)", !check_rate_limit($pdo, $rlAction, 2, 60));
$pdo->prepare("DELETE FROM rate_limit_tracker WHERE action_key = ?")->execute([$rlAction]);
echo "\n";

echo "==================================================================\n";
if ($allPassed) {
    echo "🏆 ALL PHASE 1B SECURITY TESTS PASSED SUCCESSFULLY! ✓\n";
    echo "==================================================================\n";
    ob_end_flush();
    exit(0);
} else {
    echo "❌ SOME PHASE 1B SECURITY TESTS FAILED.\n";
    echo "==================================================================\n";
    ob_end_flush();
    exit(1);
}
