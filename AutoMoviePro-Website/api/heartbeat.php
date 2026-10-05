<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['ok' => false, 'error' => 'method_not_allowed'], 405);
}

$raw = file_get_contents('php://input') ?: '';
$data = json_decode($raw, true);
if (!is_array($data)) {
    $data = $_POST;
}
$hardwareId = trim((string) ($data['hardware_id'] ?? ''));

$customer = require_api_customer($pdo, $hardwareId !== '' ? $hardwareId : null);
$now = amp_sql_now($pdo);
$pdo->prepare("UPDATE customers SET last_heartbeat_at = {$now} WHERE id = ?")
    ->execute([(int) $customer['id']]);

$days = (int) ($config['api_token_days'] ?? 3650);
amp_refresh_license($pdo, (string) ($customer['token'] ?? ''), $days);
log_api($pdo, (int) $customer['id'], 'heartbeat', '');

json_response([
    'ok' => true,
    'server_time' => date('c'),
    'customer' => amp_customer_api_payload($pdo, $customer),
]);
