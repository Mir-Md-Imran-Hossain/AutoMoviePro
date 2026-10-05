<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

$customer = require_api_customer($pdo);
$rows = $pdo->query(
    'SELECT id, platform, title, url FROM promo_channels WHERE is_active = 1 ORDER BY sort_order ASC, id ASC'
)->fetchAll();

log_api($pdo, (int) $customer['id'], 'promo_links', 'count=' . count($rows));

json_response(['ok' => true, 'links' => $rows]);
