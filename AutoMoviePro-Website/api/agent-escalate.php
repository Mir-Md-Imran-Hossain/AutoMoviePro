<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

$token = api_bearer_token();
$customer = $token ? api_customer_from_token($pdo, $token) : null;

$body = json_decode(file_get_contents('php://input') ?: '{}', true);
if (!is_array($body)) {
    $body = [];
}

$message = trim((string) ($body['message'] ?? ''));
$reason = trim((string) ($body['reason'] ?? $body['type'] ?? 'General Support'));
$contact = trim((string) ($body['contact'] ?? $body['email'] ?? $body['whatsapp'] ?? ''));
$shot = trim((string) ($body['screenshot_note'] ?? ''));
$hint = trim((string) ($body['activity_hint'] ?? ''));
$needsUpdate = !empty($body['needs_app_update']) ? 1 : 0;

if ($message === '' && $reason === '') {
    json_response(['ok' => false, 'error' => 'empty', 'message' => 'অনুগ্রহ করে সমস্যার বিবরণ লিখুন।'], 400);
}

$customerId = $customer ? (int) $customer['id'] : null;
$customerName = $customer ? ($customer['name'] ?? $customer['login_id'] ?? '') : ($contact ?: 'Client Guest');

$ins = $pdo->prepare(
    'INSERT INTO agent_tickets
      (customer_id, message, reason, screenshot_note, activity_hint, needs_app_update, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, \'open\', NOW())'
);
$ins->execute([
    $customerId,
    $message !== '' ? ($contact ? "[যোগাযোগ: {$contact}]\n" . $message : $message) : null,
    $reason !== '' ? $reason : null,
    $shot !== '' ? $shot : null,
    $hint !== '' ? $hint : null,
    $needsUpdate,
]);
$rawTicketId = (int) $pdo->lastInsertId();
$formattedTicketId = 'AMP-TK' . str_pad((string)$rawTicketId, 4, '0', STR_PAD_LEFT);

$adminWa = setting($pdo, 'whatsapp_number', $config['whatsapp_admin_number'] ?? '');
$notify = "AutoMovie Pro — New Customer Ticket ({$formattedTicketId})\n"
    . "User: {$customerName}\n"
    . "Type: {$reason}\n"
    . "Contact: " . ($contact ?: ($customer['phone'] ?? $customer['email'] ?? 'N/A')) . "\n"
    . "Message: " . mb_substr($message, 0, 400);

if ($adminWa !== '') {
    whatsapp_queue($pdo, $config, $adminWa, $notify, $customerId ?: 0);
}

if ($customerId) {
    log_api($pdo, $customerId, 'agent_escalate', "ticket={$rawTicketId}");
}

json_response([
    'ok' => true,
    'ticket_id' => $formattedTicketId,
    'raw_ticket_id' => $rawTicketId,
    'message' => 'আপনার রিপোর্ট/পরামর্শ সফলভাবে জমা হয়েছে। টিকিট আইডি: ' . $formattedTicketId . '। ইনশাআল্লাহ, সর্বোচ্চ ৭২ ঘণ্টার মধ্যে আমাদের ইঞ্জিনিয়ার টিম এটি খতিয়ে দেখে সরাসরি আপনার হোয়াটসঅ্যাপ/ইমেইলে সমাধান বা আপডেট প্রদান করবে।',
]);

