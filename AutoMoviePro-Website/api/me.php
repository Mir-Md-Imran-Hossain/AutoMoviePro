<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

$customer = require_api_customer($pdo);
log_api($pdo, (int) $customer['id'], 'me', '');

json_response([
    'ok' => true,
    'customer' => amp_customer_api_payload($pdo, $customer),
]);
