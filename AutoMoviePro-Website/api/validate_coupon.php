<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';

$raw = file_get_contents('php://input');
$data = json_decode($raw, true) ?? $_POST;

$code = strtoupper(trim((string) ($data['code'] ?? '')));
$orderAmount = (float) ($data['amount'] ?? 2998.0);

if ($code === '') {
    echo json_encode(['ok' => false, 'error' => 'কুপন কোড প্রবেশ করান।'], JSON_UNESCAPED_UNICODE);
    exit;
}

// 1. Strictly query database coupons table (no hardcoded simulations)
$stmt = $pdo->prepare('SELECT code, discount_amount, discount_percent, min_order_amount, is_active FROM coupons WHERE UPPER(code) = ? AND is_active = 1 LIMIT 1');
$stmt->execute([$code]);
$coupon = $stmt->fetch();

if (!$coupon) {
    echo json_encode(['ok' => false, 'error' => 'অকার্যকর বা মেয়াদোত্তীর্ণ কুপন কোড।'], JSON_UNESCAPED_UNICODE);
    exit;
}

$minOrder = (float) ($coupon['min_order_amount'] ?? 0);
if ($minOrder > 0 && $orderAmount < $minOrder) {
    echo json_encode([
        'ok' => false,
        'error' => "এই কুপনটি ব্যবহার করতে ন্যূনতম ৳" . number_format($minOrder, 0) . " টাকার অর্ডার প্রয়োজন।"
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$discount = 0.0;
if ((int) ($coupon['discount_percent'] ?? 0) > 0) {
    $discount = ($orderAmount * (float) $coupon['discount_percent']) / 100.0;
} else {
    $discount = (float) ($coupon['discount_amount'] ?? 0);
}

$finalAmount = max(0.0, $orderAmount - $discount);

echo json_encode([
    'ok' => true,
    'code' => (string) $coupon['code'],
    'discount' => $discount,
    'discount_amount' => $discount,
    'original_amount' => $orderAmount,
    'final_amount' => $finalAmount,
    'message' => "অভিনন্দন! কুপন '{$coupon['code']}' প্রয়োগ করে আপনি ৳ {$discount} টাকা ছাড় পেয়েছেন।"
], JSON_UNESCAPED_UNICODE);
