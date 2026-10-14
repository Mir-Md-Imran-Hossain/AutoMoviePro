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

/**
 * Clean and standardize Bangladeshi or international phone numbers to standard forms.
 * Returns e.g. "8801712345678" or "01712345678"
 */
function whatsapp_clean_phone(string $phone, bool $withCountryCode = true): string
{
    $digits = preg_replace('/\D+/', '', $phone) ?? '';
    if (str_starts_with($digits, '8801')) {
        return $withCountryCode ? $digits : substr($digits, 2);
    }
    if (str_starts_with($digits, '01')) {
        return $withCountryCode ? ('88' . $digits) : $digits;
    }
    if (str_starts_with($digits, '1') && strlen($digits) === 10) {
        return $withCountryCode ? ('880' . $digits) : ('0' . $digits);
    }
    return $digits;
}

/**
 * Save or update a marketing lead from chat, orders, or manual input.
 */
function whatsapp_save_lead(
    PDO $pdo,
    string $phone,
    string $name = 'ওয়েবসাইট ভিজিটর',
    string $source = 'chat',
    ?string $interest = 'video_studio',
    ?string $notes = null,
    ?string $lastMessage = null
): int {
    $cleanFull = whatsapp_clean_phone($phone, true);
    if ($cleanFull === '') {
        return 0;
    }

    try {
        ensure_amp_migrations($pdo);
        $stmt = $pdo->prepare("SELECT id, name, notes FROM whatsapp_leads WHERE clean_phone = ? LIMIT 1");
        $stmt->execute([$cleanFull]);
        $existing = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($existing) {
            $leadId = (int) $existing['id'];
            $newName = ($existing['name'] === 'ওয়েবসাইট ভিজিটর' && $name !== 'ওয়েবসাইট ভিজিটর') ? $name : $existing['name'];
            $mergedNotes = $notes ? (trim((string)$existing['notes'] . " | " . $notes)) : (string)$existing['notes'];

            $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
            $nowSql = ($driver === 'sqlite') ? "datetime('now')" : "NOW()";

            $up = $pdo->prepare(
                "UPDATE whatsapp_leads 
                 SET name = ?, interest_package = COALESCE(?, interest_package), 
                     last_message = COALESCE(?, last_message), notes = ?, updated_at = {$nowSql} 
                 WHERE id = ?"
            );
            $up->execute([$newName, $interest, $lastMessage, $mergedNotes, $leadId]);
            return $leadId;
        }

        $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        $nowSql = ($driver === 'sqlite') ? "datetime('now')" : "NOW()";

        $ins = $pdo->prepare(
            "INSERT INTO whatsapp_leads (name, phone, clean_phone, source, interest_package, status, last_message, notes, created_at, updated_at)
             VALUES (?, ?, ?, ?, ?, 'new', ?, ?, {$nowSql}, {$nowSql})"
        );
        $ins->execute([
            $name ?: 'ওয়েবসাইট ভিজিটর',
            $phone,
            $cleanFull,
            $source,
            $interest ?: 'video_studio',
            $lastMessage,
            $notes
        ]);
        return (int) $pdo->lastInsertId();
    } catch (\Throwable $e) {
        return 0;
    }
}

/**
 * Render template text with dynamic variable substitutions.
 */
function whatsapp_render_template(string $body, array $vars): string
{
    foreach ($vars as $k => $v) {
        $body = str_replace('{' . $k . '}', (string) $v, $body);
    }
    return $body;
}

/**
 * Build 1-click wa.me URL with prefilled text for direct sending.
 */
function whatsapp_build_share_url(string $phone, string $text = ''): string
{
    $clean = whatsapp_clean_phone($phone, true);
    $url = 'https://wa.me/' . rawurlencode($clean);
    if ($text !== '') {
        $url .= '?text=' . rawurlencode($text);
    }
    return $url;
}

