<?php
declare(strict_types=1);

function e(?string $value): string
{
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function redirect(string $url): void
{
    header('Location: ' . $url);
    exit;
}

function json_response(array $data, int $code = 200): void
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function csrf_token(): string
{
    if (empty($_SESSION['csrf'])) {
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf'];
}

function csrf_verify(?string $token): bool
{
    return is_string($token)
        && isset($_SESSION['csrf'])
        && hash_equals($_SESSION['csrf'], $token);
}

function csrf_field(): string
{
    return '<input type="hidden" name="csrf" value="' . e(csrf_token()) . '">';
}

function setting(PDO $pdo, string $key, ?string $default = null): ?string
{
    $stmt = $pdo->prepare('SELECT setting_value FROM site_settings WHERE setting_key = ? LIMIT 1');
    $stmt->execute([$key]);
    $row = $stmt->fetch();
    return $row ? (string) $row['setting_value'] : $default;
}

function set_setting(PDO $pdo, string $key, string $value): void
{
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    if ($driver === 'sqlite') {
        $stmt = $pdo->prepare('INSERT OR REPLACE INTO site_settings (setting_key, setting_value) VALUES (?, ?)');
    } else {
        $stmt = $pdo->prepare(
            'INSERT INTO site_settings (setting_key, setting_value) VALUES (?, ?)
             ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)'
        );
    }
    $stmt->execute([$key, $value]);
}

function days_since(?string $datetime): int
{
    if (!$datetime) {
        return 0;
    }
    $start = new DateTimeImmutable($datetime);
    $now = new DateTimeImmutable('now');
    return max(0, (int) $start->diff($now)->days);
}

function random_password(int $length = 10): string
{
    $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
    $out = '';
    for ($i = 0; $i < $length; $i++) {
        $out .= $alphabet[random_int(0, strlen($alphabet) - 1)];
    }
    return $out;
}

function generate_login_id(): string
{
    return 'AMP' . strtoupper(bin2hex(random_bytes(3)));
}

function amp_get_order_token(PDO $pdo, array $order): string
{
    if (!empty($order['order_token'])) {
        return (string) $order['order_token'];
    }
    $secret = setting($pdo, 'agent_master_secret', 'amp_agent_master_live_key_2026');
    return hash_hmac('sha256', (string) ($order['id'] ?? 0), $secret);
}

function amp_verify_order_token(PDO $pdo, array $order, ?string $token): bool
{
    if (empty($token) || !is_string($token)) {
        return false;
    }
    // 1. Direct match with order_token column in database
    if (!empty($order['order_token']) && hash_equals((string) $order['order_token'], $token)) {
        return true;
    }
    // 2. Cryptographic HMAC matching hash_hmac('sha256', (string)$order['id'], $secret)
    $secret = setting($pdo, 'agent_master_secret', 'amp_agent_master_live_key_2026');
    $expectedHmac = hash_hmac('sha256', (string) ($order['id'] ?? 0), $secret);
    return hash_equals($expectedHmac, $token);
}

function client_ip(): string
{
    $headers = [
        'HTTP_CF_CONNECTING_IP',
        'HTTP_X_REAL_IP',
        'HTTP_X_FORWARDED_FOR',
        'REMOTE_ADDR'
    ];
    foreach ($headers as $h) {
        if (!empty($_SERVER[$h])) {
            $raw = (string) $_SERVER[$h];
            if (str_contains($raw, ',')) {
                $parts = explode(',', $raw);
                $raw = trim($parts[0]);
            }
            $clean = trim($raw);
            if (filter_var($clean, FILTER_VALIDATE_IP)) {
                return $clean;
            }
        }
    }
    return $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
}

function check_rate_limit(PDO $pdo, string $actionKey, int $maxHits = 15, int $windowSeconds = 60): bool
{
    $ip = client_ip();
    $now = time();
    $cutoff = $now - $windowSeconds;

    try {
        if (mt_rand(1, 25) === 1) {
            $pdo->prepare("DELETE FROM rate_limit_tracker WHERE timestamp < ?")->execute([$cutoff]);
        }

        $st = $pdo->prepare("SELECT COUNT(*) FROM rate_limit_tracker WHERE ip = ? AND action_key = ? AND timestamp >= ?");
        $st->execute([$ip, $actionKey, $cutoff]);
        $count = (int) $st->fetchColumn();

        if ($count >= $maxHits) {
            return false;
        }

        $pdo->prepare("INSERT INTO rate_limit_tracker (ip, action_key, timestamp) VALUES (?, ?, ?)")
            ->execute([$ip, $actionKey, $now]);
        return true;
    } catch (\Throwable $e) {
        try {
            $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
            if ($driver === 'sqlite') {
                $pdo->exec(
                    "CREATE TABLE IF NOT EXISTS rate_limit_tracker (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      ip VARCHAR(64) NOT NULL,
                      action_key VARCHAR(64) NOT NULL,
                      timestamp INTEGER NOT NULL
                    )"
                );
                $pdo->exec("CREATE INDEX IF NOT EXISTS idx_rlt_ip_act ON rate_limit_tracker (ip, action_key, timestamp)");
            } else {
                $pdo->exec(
                    "CREATE TABLE IF NOT EXISTS rate_limit_tracker (
                      id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                      ip VARCHAR(64) NOT NULL,
                      action_key VARCHAR(64) NOT NULL,
                      timestamp INT UNSIGNED NOT NULL,
                      INDEX idx_ip_act_time (ip, action_key, timestamp)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                );
            }
            $pdo->prepare("INSERT INTO rate_limit_tracker (ip, action_key, timestamp) VALUES (?, ?, ?)")
                ->execute([$ip, $actionKey, $now]);
        } catch (\Throwable $e2) {}
        return true;
    }
}
