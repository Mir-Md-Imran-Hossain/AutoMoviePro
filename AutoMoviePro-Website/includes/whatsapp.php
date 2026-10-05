<?php
declare(strict_types=1);

/**
 * Queue + optional send via WhatsApp Cloud API.
 * If token/phone_id empty, message is stored in whatsapp_outbox only.
 */
function whatsapp_queue(
    PDO $pdo,
    array $config,
    string $toNumber,
    string $message,
    ?int $customerId = null
): bool {
    $toNumber = preg_replace('/\D+/', '', $toNumber) ?? '';
    $now = amp_sql_now($pdo);
    $stmt = $pdo->prepare(
        "INSERT INTO whatsapp_outbox (customer_id, to_number, message, status, created_at)
         VALUES (?, ?, ?, ?, {$now})"
    );
    $status = 'queued';
    $stmt->execute([$customerId, $toNumber, $message, $status]);
    $outboxId = (int) $pdo->lastInsertId();

    $token = trim((string) ($config['whatsapp_token'] ?? ''));
    $phoneId = trim((string) ($config['whatsapp_phone_id'] ?? ''));
    if ($token === '' || $phoneId === '') {
        $pdo->prepare('UPDATE whatsapp_outbox SET status = ? WHERE id = ?')
            ->execute(['logged_only', $outboxId]);
        return true;
    }

    $payload = [
        'messaging_product' => 'whatsapp',
        'to' => $toNumber,
        'type' => 'text',
        'text' => ['body' => $message],
    ];
    $ch = curl_init("https://graph.facebook.com/v19.0/{$phoneId}/messages");
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $token,
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS => json_encode($payload),
        CURLOPT_TIMEOUT => 30,
    ]);
    $raw = curl_exec($ch);
    $err = curl_error($ch);
    $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $ok = $err === '' && $code >= 200 && $code < 300;
    $pdo->prepare('UPDATE whatsapp_outbox SET status = ?, response = ? WHERE id = ?')
        ->execute([$ok ? 'sent' : 'failed', substr((string) ($raw ?: $err), 0, 2000), $outboxId]);
    return $ok;
}

function build_approval_message(array $config, string $loginId, string $password, string $customerName): string
{
    $download = $config['download_url'] ?? '';
    $guide = $config['install_guide_url'] ?? '';
    $site = $config['site_name'] ?? 'AutoMovie Pro';
    return "Assalamu Alaikum {$customerName},\n\n"
        . "আপনার {$site} পেমেন্ট অ্যাপ্রুভ হয়েছে।\n\n"
        . "লগইন ID: {$loginId}\n"
        . "পাসওয়ার্ড: {$password}\n\n"
        . "ডাউনলোড: {$download}\n"
        . "ইনস্টল গাইড: {$guide}\n\n"
        . "ইনস্টলের পর উপরের ID/পাসওয়ার্ড দিয়ে লগইন করুন।";
}
