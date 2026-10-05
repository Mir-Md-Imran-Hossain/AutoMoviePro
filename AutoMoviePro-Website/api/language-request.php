<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

$customer = require_api_customer($pdo);
$body = json_decode(file_get_contents('php://input') ?: '{}', true);
if (!is_array($body)) {
    $body = [];
}

$catalog = amp_lang_catalog();
$codes = [];
if (!empty($body['lang_codes']) && is_array($body['lang_codes'])) {
    foreach ($body['lang_codes'] as $c) {
        $code = strtolower(trim((string) $c));
        if ($code !== '' && !in_array($code, $codes, true)) {
            $codes[] = $code;
        }
    }
} elseif (!empty($body['lang_code'])) {
    $codes[] = strtolower(trim((string) $body['lang_code']));
}

if (!$codes) {
    json_response(['ok' => false, 'error' => 'lang_required'], 400);
}

$unlocked = amp_customer_unlocked_langs($pdo, (int) $customer['id']);
if (count($unlocked) + count($codes) > 6) {
    json_response([
        'ok' => false,
        'error' => 'max_languages_reached',
        'hint' => 'সর্বোচ্চ ৬টি ভাষা',
    ], 400);
}

foreach ($codes as $lang) {
    if (!isset($catalog[$lang]) || $lang === 'en') {
        json_response(['ok' => false, 'error' => 'invalid_language', 'lang_code' => $lang], 400);
    }
    if (in_array($lang, $unlocked, true)) {
        json_response(['ok' => false, 'error' => 'already_unlocked', 'lang_code' => $lang], 400);
    }
    $pending = $pdo->prepare(
        "SELECT id FROM language_orders WHERE customer_id = ? AND lang_code = ? AND status = 'pending_payment' LIMIT 1"
    );
    $pending->execute([(int) $customer['id'], $lang]);
    if ($pending->fetch()) {
        json_response(['ok' => false, 'error' => 'already_pending', 'lang_code' => $lang], 400);
    }
}

$unit = (float) ($body['unit_price'] ?? setting($pdo, 'language_addon_price', '499'));
if ($unit <= 0) {
    $unit = 499.0;
}
$ref = trim((string) ($body['payment_ref'] ?? ''));
$note = trim((string) ($body['payment_note'] ?? ''));
if ($ref === '' && $note === '') {
    json_response(['ok' => false, 'error' => 'payment_info_required'], 400);
}

$ins = $pdo->prepare(
    'INSERT INTO language_orders (customer_id, lang_code, amount, payment_ref, payment_note, status, created_at)
     VALUES (?, ?, ?, ?, ?, \'pending_payment\', NOW())'
);

$orderIds = [];
$items = [];
foreach ($codes as $lang) {
    $ins->execute([(int) $customer['id'], $lang, $unit, $ref ?: null, $note ?: null]);
    $orderId = (int) $pdo->lastInsertId();
    $orderIds[] = $orderId;
    $items[] = [
        'order_id' => $orderId,
        'lang_code' => $lang,
        'lang_name' => $catalog[$lang],
        'amount' => $unit,
    ];
}

$total = $unit * count($codes);
log_api(
    $pdo,
    (int) $customer['id'],
    'language_request',
    implode(',', $codes) . ' total=' . $total
);

json_response([
    'ok' => true,
    'order_ids' => $orderIds,
    'order_id' => $orderIds[0] ?? null,
    'items' => $items,
    'count' => count($codes),
    'unit_price' => $unit,
    'total_amount' => $total,
    'status' => 'pending_payment',
]);
