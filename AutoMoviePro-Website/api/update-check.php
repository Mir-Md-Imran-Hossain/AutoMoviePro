<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require dirname(__DIR__) . '/includes/release_service.php';

/**
 * Desktop / website clients poll this to learn about forced updates.
 * GET ?version=1.0.0  (optional token for logging)
 */
$clientVersion = trim((string) ($_GET['version'] ?? $_POST['version'] ?? '0.0.0'));
if ($clientVersion === '') {
    $clientVersion = '0.0.0';
}

$token = trim((string) ($_GET['token'] ?? $_POST['token'] ?? ''));
if ($token === '' && isset($_SERVER['HTTP_AUTHORIZATION'])) {
    if (preg_match('/Bearer\s+(\S+)/i', (string) $_SERVER['HTTP_AUTHORIZATION'], $m)) {
        $token = $m[1];
    }
}
$cid = null;
if ($token !== '') {
    try {
        $stmt = $pdo->prepare(
            'SELECT customer_id FROM licenses WHERE token = ? AND revoked = 0
             AND (expires_at IS NULL OR expires_at > NOW()) LIMIT 1'
        );
        $stmt->execute([$token]);
        $row = $stmt->fetch();
        if ($row) {
            $cid = (int) $row['customer_id'];
        }
    } catch (Throwable $e) {
        // ignore
    }
}

$payload = amp_update_check_payload($pdo, $config, $clientVersion);
if ($cid) {
    try {
        log_api(
            $pdo,
            $cid,
            'update_check',
            ($payload['message'] ?? '') . ' cv=' . $clientVersion . ' lv=' . ($payload['latest_version'] ?? '')
        );
    } catch (Throwable $e) {
        // ignore
    }
}

json_response($payload);
