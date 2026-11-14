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
if ($hardwareId === '') {
    json_response(['ok' => false, 'error' => 'hardware_id_required'], 400);
}

// 1. Validate customer identity, active license, and strict hardware lock
$customer = require_api_customer($pdo, $hardwareId);

$action = trim((string) ($data['action'] ?? 'generate_short'));
$videoType = ($data['video_type'] ?? 'short') === 'long' ? 'long' : 'short';
$tier = (string) ($customer['tier'] ?? $customer['plan'] ?? 'profile_page');

// 2. Strict 3-Tier Access Gating (Server Authority)
$isVideoAction = in_array($action, ['generate_short', 'generate_long', 'video_production', 'generate_video'], true);

if ($isVideoAction && $tier !== 'video_studio') {
    log_api($pdo, (int) $customer['id'], 'ticket_denied_tier', "tier:{$tier}, action:{$action}");
    json_response([
        'ok' => false,
        'error' => 'tier_upgrade_required',
        'current_tier' => $tier,
        'message' => 'আপনার বর্তমান প্ল্যানে ফুল ভিডিও স্টুডিও অন্তর্ভুক্ত নয়। ভিডিও তৈরি করতে ৳৩,৯৯৯ ভিডিও স্টুডিও প্যাকেজে আপগ্রেড করুন।',
        'upgrade_url' => 'https://automoviepro.com/#pricing'
    ], 403);
}

// 3. Dynamic Viral Framework / Secret Recipe Injected from Server
// Note: This proprietary recipe is NEVER stored on the client machine!
$viralFramework = [
    'hook_framework' => 'PATTERN_INTERRUPT_3S',
    'retention_rules' => [
        'first_3_seconds' => 'Visual contradiction or high-stakes curiosity gap',
        'pacing' => '130-150 words per minute with 0.3s breath pauses',
        'emotional_climax' => 'Minute 01:45 revelation before call to action',
        'anti_hallucination_filter' => 'STRICT_FACTUAL_ASSERTION'
    ],
    'server_issued_at' => time()
];

// 4. Generate Single-Use Cryptographic Ticket (HMAC-SHA256)
$ticketId = bin2hex(random_bytes(16));
$serverSecret = (string) ($config['app_key'] ?? 'amp_master_secret_key_prod_2026_super_secure');

$payload = [
    'jti' => $ticketId,
    'customer_id' => (int) $customer['id'],
    'login_id' => (string) $customer['login_id'],
    'tier' => $tier,
    'action' => $action,
    'video_type' => $videoType,
    'hardware_id' => strtoupper($hardwareId),
    'issued_at' => time(),
    'expires_at' => time() + 600, // Valid for 10 minutes
    'framework' => $viralFramework
];

$payloadJson = json_encode($payload, JSON_UNESCAPED_UNICODE);
$signature = hash_hmac('sha256', $payloadJson, $serverSecret);

log_api($pdo, (int) $customer['id'], 'ticket_issued', "ticket:{$ticketId}, action:{$action}");

json_response([
    'ok' => true,
    'ticket_id' => $ticketId,
    'ticket' => $payload,
    'signature' => $signature,
    'expires_in_seconds' => 600
]);
