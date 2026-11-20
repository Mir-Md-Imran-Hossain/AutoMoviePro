<?php
declare(strict_types=1);

function admin_logged_in(): bool
{
    if (empty($_SESSION['admin_id'])) {
        return false;
    }
    $now = time();
    $idleTimeout = 3600; // 1 hour idle timeout
    $maxLifetime = 43200; // 12 hours absolute session lifetime

    if (!empty($_SESSION['admin_last_activity']) && ($now - (int) $_SESSION['admin_last_activity']) > $idleTimeout) {
        $_SESSION = [];
        if (session_status() === PHP_SESSION_ACTIVE) {
            session_destroy();
        }
        return false;
    }

    if (!empty($_SESSION['admin_login_time']) && ($now - (int) $_SESSION['admin_login_time']) > $maxLifetime) {
        $_SESSION = [];
        if (session_status() === PHP_SESSION_ACTIVE) {
            session_destroy();
        }
        return false;
    }

    $_SESSION['admin_last_activity'] = $now;
    return true;
}

function require_admin(): void
{
    if (!admin_logged_in()) {
        redirect('/admin/login.php');
    }
}

function attempt_admin_login(PDO $pdo, string $username, string $password): bool
{
    $stmt = $pdo->prepare('SELECT id, password_hash FROM admins WHERE username = ? LIMIT 1');
    $stmt->execute([$username]);
    $row = $stmt->fetch();
    if (!$row || !password_verify($password, $row['password_hash'])) {
        return false;
    }
    if (session_status() === PHP_SESSION_ACTIVE) {
        session_regenerate_id(true);
    }
    $now = time();
    $_SESSION['admin_id'] = (int) $row['id'];
    $_SESSION['admin_user'] = $username;
    $_SESSION['admin_logged_in'] = true;
    $_SESSION['admin_login_time'] = $now;
    $_SESSION['admin_last_activity'] = $now;
    return true;
}

function api_bearer_token(): ?string
{
    $header = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    if (preg_match('/Bearer\s+(\S+)/i', $header, $m)) {
        return $m[1];
    }
    // W-04: Reject tokens in query strings ($_GET['token']). Only POST body allowed if header is absent.
    return $_POST['token'] ?? null;
}

function api_customer_from_token(PDO $pdo, ?string $token): ?array
{
    if (!$token) {
        return null;
    }
    $now = amp_sql_now($pdo);
    $stmt = $pdo->prepare(
        "SELECT c.*, l.token, l.expires_at AS token_expires, l.revoked
         FROM licenses l
         JOIN customers c ON c.id = l.customer_id
         WHERE l.token = ?
           AND l.revoked = 0
           AND (l.expires_at IS NULL OR l.expires_at > {$now})
           AND c.status = 'active'
         LIMIT 1"
    );
    $stmt->execute([$token]);
    $row = $stmt->fetch();
    return $row ?: null;
}

function require_api_customer(PDO $pdo, ?string $hardwareId = null): array
{
    $token = api_bearer_token();
    $customer = api_customer_from_token($pdo, $token);
    if (!$customer) {
        json_response(['ok' => false, 'error' => 'unauthorized', 'message' => 'অবৈধ সেশন টোকেন। অনুগ্রহ করে পুনরায় লগইন করুন।'], 401);
    }
    if ((int) ($customer['revoked'] ?? 0) === 1) {
        json_response([
            'ok' => false,
            'blocked' => true,
            'error' => 'license_revoked',
            'message' => 'আপনার লাইসেন্সটি অ্যাডমিন প্যানেল থেকে বাতিল (Revoked) করা হয়েছে।'
        ], 403);
    }
    if ($customer['status'] !== 'active') {
        json_response([
            'ok' => false,
            'blocked' => true,
            'error' => 'account_' . $customer['status'],
            'message' => 'অ্যাডমিন কর্তৃক আপনার অ্যাকাউন্টটি ব্লক বা স্থগিত করা হয়েছে।'
        ], 403);
    }
    if (!empty($customer['token_expires']) && strtotime($customer['token_expires']) < time()) {
        json_response(['ok' => false, 'error' => 'token_expired', 'message' => 'সেশনের মেয়াদ উত্তীর্ণ হয়েছে।'], 401);
    }
    if (!empty($customer['hardware_id'])) {
        if (empty($hardwareId) || strtoupper(trim((string)$customer['hardware_id'])) !== strtoupper(trim((string)$hardwareId))) {
            json_response([
                'ok' => false,
                'blocked' => true,
                'error' => 'hwid_mismatch',
                'message' => 'ডিভাইস অমিল! এই অ্যাকাউন্টটি অন্য নির্দিষ্ট পিসির সাথে আবদ্ধ।'
            ], 403);
        }
    }
    return $customer;
}

function log_api(PDO $pdo, ?int $customerId, string $action, string $detail = ''): void
{
    $now = amp_sql_now($pdo);
    $stmt = $pdo->prepare(
        "INSERT INTO api_logs (customer_id, action, detail, ip_address, created_at)
         VALUES (?, ?, ?, ?, {$now})"
    );
    $stmt->execute([$customerId, $action, $detail, client_ip()]);
}
