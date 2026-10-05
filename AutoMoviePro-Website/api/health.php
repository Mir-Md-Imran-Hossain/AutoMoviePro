<?php
declare(strict_types=1);

/**
 * Public deploy check — no secrets. App and Hostinger can hit this after paste.
 */
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$configPath = dirname(__DIR__) . '/config.php';
if (!is_file($configPath)) {
    http_response_code(503);
    echo json_encode([
        'ok' => false,
        'installed' => false,
        'error' => 'not_installed',
        'hint' => 'Open /install/ after uploading files and creating MySQL.',
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    require dirname(__DIR__) . '/includes/bootstrap.php';
    $pdo->query('SELECT 1');
    $tables = ['customers', 'orders', 'licenses', 'customer_jobs', 'customer_languages', 'language_orders'];
    $missing = [];
    foreach ($tables as $t) {
        try {
            $pdo->query('SELECT 1 FROM ' . $t . ' LIMIT 1');
        } catch (Throwable $e) {
            $missing[] = $t;
        }
    }
    json_response([
        'ok' => $missing === [],
        'installed' => true,
        'php' => PHP_VERSION,
        'site' => rtrim((string) ($config['site_url'] ?? ''), '/'),
        'time' => date('c'),
        'missing_tables' => $missing,
    ]);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode([
        'ok' => false,
        'installed' => true,
        'error' => 'db_failed',
    ], JSON_UNESCAPED_UNICODE);
}
