<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

$customer = require_api_customer($pdo);
$cid = (int) $customer['id'];
$unlocked = amp_customer_unlocked_langs($pdo, $cid);
$catalog = amp_lang_catalog();

$pend = $pdo->prepare(
    "SELECT id, lang_code, amount, payment_ref, status, created_at
     FROM language_orders WHERE customer_id = ? AND status = 'pending_payment' ORDER BY id DESC"
);
$pend->execute([$cid]);
$pending = $pend->fetchAll();

log_api($pdo, $cid, 'language_status', 'unlocked=' . count($unlocked));

json_response([
    'ok' => true,
    'max' => 6,
    'unlocked' => $unlocked,
    'unlocked_names' => array_map(static fn($c) => $catalog[$c] ?? $c, $unlocked),
    'pending' => $pending,
    'price' => setting($pdo, 'language_addon_price', '499'),
]);
