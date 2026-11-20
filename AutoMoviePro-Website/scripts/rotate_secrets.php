<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit('Not Found');
}

require_once dirname(__DIR__) . '/includes/bootstrap.php';

echo "==================================================================\n";
echo "🔑 AUTOMOVIE PRO SECURE SECRETS ROTATION UTILITY (CLI-ONLY)\n";
echo "==================================================================\n\n";

$newAgentSecret = bin2hex(random_bytes(32));
$newSmsSecret = bin2hex(random_bytes(32));
$newOrderSecret = bin2hex(random_bytes(32));
$newWaVerifyToken = bin2hex(random_bytes(32));

// 1. Update site_settings table
try {
    set_setting($pdo, 'agent_master_secret', $newAgentSecret);
    set_setting($pdo, 'sms_gateway_secret', $newSmsSecret);
    set_setting($pdo, 'order_signing_secret', $newOrderSecret);
    set_setting($pdo, 'whatsapp_webhook_verify_token', $newWaVerifyToken);
    echo "[✓] Database site_settings table updated with fresh cryptographic keys.\n";
} catch (\Throwable $e) {
    echo "[!] Warning: Failed to update site_settings table: " . $e->getMessage() . "\n";
}

// 2. Update storage/.signing_secret
$signingSecretFile = dirname(__DIR__) . '/storage/.signing_secret';
@mkdir(dirname(__DIR__) . '/storage', 0755, true);
file_put_contents($signingSecretFile, $newOrderSecret);
echo "[✓] storage/.signing_secret safely updated.\n";

// 3. Update config.php if present
$configPath = dirname(__DIR__) . '/config.php';
if (is_file($configPath)) {
    $current = require $configPath;
    if (is_array($current)) {
        $current['agent_master_secret'] = $newAgentSecret;
        $current['sms_gateway_secret'] = $newSmsSecret;
        $current['order_signing_secret'] = $newOrderSecret;
        $current['whatsapp_webhook_verify_token'] = $newWaVerifyToken;

        $content = "<?php\n/**\n * AutoMovie Pro Production Configuration\n * Updated by rotate_secrets.php on " . date('Y-m-d H:i:s') . "\n */\nreturn " . var_export($current, true) . ";\n";
        file_put_contents($configPath, $content);
        echo "[✓] config.php updated with fresh secrets.\n";
    }
}

function mask_key(string $k): string {
    if (strlen($k) <= 8) return '****';
    return substr($k, 0, 4) . '...' . substr($k, -4) . ' (' . strlen($k) . ' chars)';
}

echo "\nRotation Summary (Masked for Security):\n";
echo " - agent_master_secret:           " . mask_key($newAgentSecret) . "\n";
echo " - sms_gateway_secret:            " . mask_key($newSmsSecret) . "\n";
echo " - order_signing_secret:          " . mask_key($newOrderSecret) . "\n";
echo " - whatsapp_webhook_verify_token: " . mask_key($newWaVerifyToken) . "\n";

echo "\n[✓] Secrets rotation completed successfully.\n";
echo "==================================================================\n";
