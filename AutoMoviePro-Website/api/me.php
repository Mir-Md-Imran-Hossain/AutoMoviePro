<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

$hw = trim((string) ($_GET['hardware_id'] ?? $_POST['hardware_id'] ?? ''));
$customer = require_api_customer($pdo, $hw !== '' ? $hw : null);
log_api($pdo, (int) $customer['id'], 'me', '');

json_response([
    'ok' => true,
    'customer' => amp_customer_api_payload($pdo, $customer),
]);
