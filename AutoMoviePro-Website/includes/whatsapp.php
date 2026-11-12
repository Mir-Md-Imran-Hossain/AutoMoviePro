<?php
declare(strict_types=1);

/**
 * Render message with Spintax {Option A|Option B} and dynamic token substitution
 */
function whatsapp_render_message(string $template, array $data = []): string
{
    // 1. Process Spintax {Option A|Option B|Option C}
    $rendered = preg_replace_callback('/\{([^{}]+)\|([^{}]+)\}/u', function ($matches) {
        $choices = explode('|', trim($matches[0], '{}'));
        return $choices[array_rand($choices)];
    }, $template);

    // Repeat for nested or chained spintax if needed
    if (strpos($rendered, '|') !== false && preg_match('/\{[^{}]+\|[^{}]+\}/u', $rendered)) {
        $rendered = preg_replace_callback('/\{([^{}]+)\|([^{}]+)\}/u', function ($matches) {
            $choices = explode('|', trim($matches[0], '{}'));
            return $choices[array_rand($choices)];
        }, $rendered);
    }

    // 2. Package Pricing Dictionary
    $pkg = (string)($data['package'] ?? $data['plan'] ?? 'AutoMovie Pro 4K Studio');
    $priceMap = [
        'video_studio' => ['title' => '4K Video Studio Master', 'price' => '৳৩,৯৯৯', 'offer' => '৳৩,৪৯৯'],
        'fb_business' => ['title' => 'Facebook Business & Ads', 'price' => '৳২,৯৯৯', 'offer' => '৳২,৪৯৯'],
        'profile_page' => ['title' => 'Profile AutoPilot', 'price' => '৳১,৯৯৯', 'offer' => '৳১,৬৯৯'],
        'wamanager_pro' => ['title' => 'WAManager Pro Suite', 'price' => '৳১,৯৯৯', 'offer' => '৳১,৪৯৯'],
        'google_pro' => ['title' => 'Google AI Pro 18M', 'price' => '৳৯৯৯', 'offer' => '৳৭৯৯'],
    ];

    $matchedPrice = '৳৩,৯৯৯';
    $matchedOffer = '৳৩,৪৯৯';
    foreach ($priceMap as $k => $info) {
        if (stripos($pkg, $k) !== false || stripos($pkg, $info['title']) !== false) {
            $matchedPrice = $info['price'];
            $matchedOffer = $info['offer'];
            break;
        }
    }

    // 3. Dynamic Tokens Replacement
    $tokens = [
        '{name}' => !empty($data['name']) ? (string)$data['name'] : 'সম্মানিত গ্রাহক',
        '{phone}' => !empty($data['phone']) ? (string)$data['phone'] : '',
        '{package}' => !empty($data['package']) ? (string)$data['package'] : 'AutoMovie Pro',
        '{plan}' => !empty($data['package']) ? (string)$data['package'] : 'AutoMovie Pro',
        '{price}' => !empty($data['price']) ? (string)$data['price'] : $matchedPrice,
        '{offer_price}' => !empty($data['offer_price']) ? (string)$data['offer_price'] : $matchedOffer,
        '{login_id}' => !empty($data['login_id']) ? (string)$data['login_id'] : '',
        '{password}' => !empty($data['password']) ? (string)$data['password'] : '',
        '{token}' => !empty($data['token']) ? (string)$data['token'] : '',
        '{license}' => !empty($data['token']) ? (string)$data['token'] : '',
        '{download_link}' => !empty($data['download_link']) ? (string)$data['download_link'] : ($data['link'] ?? 'https://automoviepro.com/order.php'),
        '{link}' => !empty($data['link']) ? (string)$data['link'] : 'https://automoviepro.com/order.php',
        '{coupon}' => !empty($data['coupon']) ? (string)$data['coupon'] : 'SPECIAL500',
    ];

    return str_replace(array_keys($tokens), array_values($tokens), $rendered);
}

/**
 * Queue + optional send via WhatsApp Cloud API or Custom HTTP Gateway.
 * If token/phone_id empty, message is stored in whatsapp_outbox as pending_action.
 */
function whatsapp_queue(
    PDO $pdo,
    array $config,
    string $toNumber,
    string $message,
    ?int $customerId = null,
    ?string $accountId = null,
    string $triggerType = 'outbound_campaign'
): bool {
    $cleanPhone = whatsapp_clean_phone($toNumber, true);
    if (strlen($cleanPhone) < 10) {
        return false;
    }
    $now = amp_sql_now($pdo);
    $stmt = $pdo->prepare(
        "INSERT INTO whatsapp_outbox (customer_id, to_number, message, status, account_id, trigger_type, created_at)
         VALUES (?, ?, ?, 'queued', ?, ?, {$now})"
    );
    $stmt->execute([$customerId, $cleanPhone, $message, $accountId, $triggerType]);
    $outboxId = (int) $pdo->lastInsertId();

    $token = '';
    $phoneId = '';
    $gatewayUrl = '';

    // If specific account requested, fetch its credentials
    if (!empty($accountId)) {
        try {
            $stAcc = $pdo->prepare("SELECT api_config FROM accounts WHERE id = ? LIMIT 1");
            $stAcc->execute([$accountId]);
            if ($row = $stAcc->fetch(PDO::FETCH_ASSOC)) {
                $accCfg = json_decode((string)($row['api_config'] ?? ''), true);
                if (is_array($accCfg)) {
                    $token = trim((string)($accCfg['access_token'] ?? ''));
                    $phoneId = trim((string)($accCfg['phone_number_id'] ?? ''));
                    $gatewayUrl = trim((string)($accCfg['gateway_url'] ?? ''));
                }
            }
        } catch (\Throwable $eAcc) {}
    }

    // Fallback to global config or connected account pool
    if ($token === '' && $gatewayUrl === '') {
        $token = trim((string) ($config['whatsapp_token'] ?? setting($pdo, 'whatsapp_token', '')));
        $phoneId = trim((string) ($config['whatsapp_phone_id'] ?? setting($pdo, 'whatsapp_phone_id', '')));
        $gatewayUrl = trim((string) setting($pdo, 'whatsapp_gateway_url', ''));
    }

    if ($token === '' && $gatewayUrl === '') {
        try {
            foreach (['accounts', 'wa_accounts'] as $tbl) {
                $accStmt = $pdo->query("SELECT id, api_config FROM {$tbl} WHERE (status = 'connected' OR status = 'active') AND api_config IS NOT NULL ORDER BY id ASC LIMIT 1");
                if ($accStmt && ($accRow = $accStmt->fetch(PDO::FETCH_ASSOC))) {
                    $accCfg = json_decode((string) ($accRow['api_config'] ?? ''), true);
                    if (is_array($accCfg)) {
                        if (empty($token) && !empty($accCfg['access_token'])) $token = trim((string) $accCfg['access_token']);
                        if (empty($phoneId) && !empty($accCfg['phone_number_id'])) $phoneId = trim((string) $accCfg['phone_number_id']);
                        if (empty($gatewayUrl) && !empty($accCfg['gateway_url'])) $gatewayUrl = trim((string) $accCfg['gateway_url']);
                        if (empty($accountId) && !empty($accRow['id'])) $accountId = (string)$accRow['id'];
                    }
                }
                if ($token !== '' || $gatewayUrl !== '') break;
            }
        } catch (\Throwable $eAcc) {}
    }

    try {
        // CASE 1: Custom HTTP WhatsApp Gateway
        if ($gatewayUrl !== '') {
            $ch = curl_init($gatewayUrl);
            $payload = json_encode(['to' => $cleanPhone, 'phone' => $cleanPhone, 'message' => $message]);
            curl_setopt_array($ch, [
                CURLOPT_POST => true,
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
                CURLOPT_POSTFIELDS => $payload,
                CURLOPT_CONNECTTIMEOUT => 5,
                CURLOPT_TIMEOUT => 12,
            ]);
            $raw = curl_exec($ch);
            $err = curl_error($ch);
            $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
            curl_close($ch);
            $ok = ($err === '' && $code >= 200 && $code < 300);
            $pdo->prepare('UPDATE whatsapp_outbox SET status = ?, response = ?, account_id = ? WHERE id = ?')
                ->execute([$ok ? 'sent' : 'failed', substr((string) ($raw ?: $err), 0, 2000), $accountId, $outboxId]);
            return $ok;
        }

        // CASE 2: Official Meta Cloud API
        if ($token !== '' && $phoneId !== '') {
            $payload = [
                'messaging_product' => 'whatsapp',
                'to' => $cleanPhone,
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
                CURLOPT_CONNECTTIMEOUT => 5,
                CURLOPT_TIMEOUT => 15,
            ]);
            $raw = curl_exec($ch);
            $err = curl_error($ch);
            $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
            curl_close($ch);

            $ok = ($err === '' && $code >= 200 && $code < 300);
            $msgId = null;
            if ($ok && $raw) {
                $decoded = json_decode((string)$raw, true);
                $msgId = $decoded['messages'][0]['id'] ?? null;
            }

            $pdo->prepare('UPDATE whatsapp_outbox SET status = ?, response = ?, message_id = ?, account_id = ? WHERE id = ?')
                ->execute([$ok ? 'sent' : 'failed', substr((string) ($raw ?: $err), 0, 2000), $msgId, $accountId, $outboxId]);
            return $ok;
        }
    } catch (\Throwable $eEx) {
        $pdo->prepare('UPDATE whatsapp_outbox SET status = "failed", response = ?, account_id = ? WHERE id = ?')
            ->execute([substr($eEx->getMessage(), 0, 1000), $accountId, $outboxId]);
        return false;
    }

    // CASE 3: Desktop Bridge / Connected Session
    // If the account is linked via WAManager Desktop Bridge, queue it for automated instant background delivery
    $isDesktopLinked = false;
    try {
        $stDesk = $pdo->prepare("SELECT provider_type, status FROM accounts WHERE id = ? LIMIT 1");
        $stDesk->execute([$accountId]);
        if ($rowD = $stDesk->fetch(PDO::FETCH_ASSOC)) {
            if ($rowD['provider_type'] === 'desktop_bridge' && ($rowD['status'] === 'connected' || $rowD['status'] === 'active')) {
                $isDesktopLinked = true;
            }
        }
    } catch (\Throwable $eDesk) {}

    if ($isDesktopLinked) {
        $pdo->prepare('UPDATE whatsapp_outbox SET status = "pending_desktop", account_id = ? WHERE id = ?')
            ->execute([$accountId, $outboxId]);
        // Do NOT report as delivered_auto=true; message is queued for desktop client dispatch
        return false;
    }

    // CASE 4: No automated gateway token configured - Mark pending action, DO NOT return true!
    $pdo->prepare('UPDATE whatsapp_outbox SET status = "pending_action", account_id = ? WHERE id = ?')
        ->execute([$accountId, $outboxId]);
    return false;
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
    if (str_starts_with($digits, '00')) {
        $digits = substr($digits, 2);
    }
    if (str_starts_with($digits, '8801') && (strlen($digits) === 13 || strlen($digits) === 14)) {
        return $withCountryCode ? $digits : substr($digits, 2);
    }
    if (str_starts_with($digits, '01') && strlen($digits) === 11) {
        return $withCountryCode ? ('88' . $digits) : $digits;
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

/**
 * -----------------------------------------------------------------------------
 * ANTI-BAN AUTONOMOUS MESSAGING SENTINEL & MULTI-NUMBER SMART ROTATION ENGINE
 * -----------------------------------------------------------------------------
 */

function whatsapp_get_antiban_settings(PDO $pdo): array
{
    return [
        'antiban_delay_min' => (int) setting($pdo, 'antiban_delay_min', '25'),
        'antiban_delay_max' => (int) setting($pdo, 'antiban_delay_max', '55'),
        'antiban_batch_size' => (int) setting($pdo, 'antiban_batch_size', '15'),
        'antiban_batch_pause_seconds' => (int) setting($pdo, 'antiban_batch_pause_seconds', '480'),
        'antiban_daily_cap_per_number' => (int) setting($pdo, 'antiban_daily_cap_per_number', '65'),
        'antiban_priority_bypass' => setting($pdo, 'antiban_priority_bypass', '1') === '1',
        'antiban_smart_rotation' => setting($pdo, 'antiban_smart_rotation', '1') === '1',
        'antiban_human_jitter' => setting($pdo, 'antiban_human_jitter', '1') === '1',
        'agent_ayesha_active' => setting($pdo, 'agent_ayesha_active', '1') === '1',
        'agent_nirob_active' => setting($pdo, 'agent_nirob_active', '1') === '1',
        'agent_tania_active' => setting($pdo, 'agent_tania_active', '1') === '1',
        'auto_license_delivery' => setting($pdo, 'auto_license_delivery', '1') === '1',
        'lead_auto_followup' => setting($pdo, 'lead_auto_followup', '1') === '1',
    ];
}

function whatsapp_save_antiban_settings(PDO $pdo, array $settings): bool
{
    foreach ($settings as $k => $v) {
        set_setting($pdo, (string) $k, is_bool($v) ? ($v ? '1' : '0') : (string) $v);
    }
    return true;
}

/**
 * Return detailed warmup schedule tier for an account based on warmup day.
 */
function whatsapp_get_warmup_tier(int $day, int $targetLimit = 800, string $salt = 'default'): array
{
    $day = max(1, min(30, $day));
    $seed = $salt . '_warmup_day_' . $day;
    $hash = hexdec(substr(md5($seed), 0, 8));

    if ($day <= 1) {
        $jitter = ($hash % 17) - 8;
        $limit = max(35, min(75, 55 + $jitter));
        $stageName = 'ধাপ ১: ইনিশিয়াল ট্রাস্ট (Safe Start)';
        $nextLimit = 90;
    } elseif ($day === 2) {
        $jitter = ($hash % 21) - 10;
        $limit = max(65, min(115, 90 + $jitter));
        $stageName = 'ধাপ ২: প্রারম্ভিক অ্যাক্টিভেশন';
        $nextLimit = 115;
    } elseif ($day === 3) {
        $jitter = ($hash % 25) - 12;
        $limit = max(75, min(140, 110 + $jitter));
        $stageName = 'ধাপ ৩: প্রারম্ভিক অ্যাডাপ্টেশন';
        $nextLimit = 145;
    } elseif ($day <= 5) {
        $progress = ($day - 3) / 2.0;
        $base = 120 + (int) round($progress * 45);
        $jitter = ($hash % 31) - 15;
        $limit = max(90, min(190, $base + $jitter));
        $stageName = 'ধাপ ৪: মিড-লেভেল স্টেবিলাইজেশন';
        $nextLimit = 220;
    } elseif ($day <= 8) {
        $progress = ($day - 5) / 3.0;
        $base = 175 + (int) round($progress * 65);
        $jitter = ($hash % 41) - 20;
        $limit = max(130, min(270, $base + $jitter));
        $stageName = 'ধাপ ৫: গ্রোথ স্টেজ';
        $nextLimit = 320;
    } elseif ($day <= 12) {
        $progress = ($day - 8) / 4.0;
        $base = 255 + (int) round($progress * 105);
        $jitter = ($hash % 51) - 25;
        $limit = max(200, min(390, $base + $jitter));
        $stageName = 'ধাপ ৬: এক্সপ্যানশন ফেজ';
        $nextLimit = 450;
    } elseif ($day <= 17) {
        $progress = ($day - 12) / 5.0;
        $base = 380 + (int) round($progress * 145);
        $jitter = ($hash % 61) - 30;
        $limit = max(300, min(560, $base + $jitter));
        $stageName = 'ধাপ ৭: হাই-ভলিউম আউটবাউন্ড';
        $nextLimit = 600;
    } elseif ($day <= 24) {
        $progress = ($day - 17) / 7.0;
        $base = 530 + (int) round($progress * 180);
        $jitter = ($hash % 71) - 35;
        $limit = max(450, min(730, $base + $jitter));
        $stageName = 'ধাপ ৮: সেমি-ভেটেরান পাওয়ার';
        $nextLimit = 750;
    } else {
        $progress = min(1.0, ($day - 24) / 6.0);
        $base = 710 + (int) round($progress * (max(750, $targetLimit) - 710));
        $jitter = ($hash % 61) - 30;
        $limit = max(660, min($targetLimit, $base + $jitter));
        $stageName = 'ধাপ ৯: ম্যাক্সিমাম পাওয়ার (Veteran Unlimited)';
        $nextLimit = $targetLimit;
    }

    $limit = min($limit, $targetLimit);
    return [
        'day' => $day,
        'limit' => $limit,
        'stage_name' => $stageName,
        'next_limit' => min($nextLimit, $targetLimit),
        'is_mature' => ($day >= 25 || $limit >= $targetLimit),
    ];
}


function whatsapp_advance_warmup_schedules(PDO $pdo): void
{
    try {
        $today = date('Y-m-d');
        $accounts = $pdo->query("SELECT id, warmup_enabled, warmup_day, warmup_target_limit, warmup_last_advanced_at, daily_limit FROM accounts WHERE warmup_enabled = 1")->fetchAll(PDO::FETCH_ASSOC);
        foreach ($accounts as $acc) {
            $lastAdv = $acc['warmup_last_advanced_at'] ?? '';
            if ($lastAdv !== $today) {
                $curDay = (int) ($acc['warmup_day'] ?? 1);
                $target = max(50, min(1000, (int) ($acc['warmup_target_limit'] ?? 800)));
                $newDay = min(30, $curDay + 1);
                $tier = whatsapp_get_warmup_tier($newDay, $target, (string)$acc['id']);
                $newLimit = $tier['limit'];
                
                $st = $pdo->prepare("UPDATE accounts SET warmup_day = ?, daily_limit = ?, daily_sent_today = 0, batch_count = 0, warmup_last_advanced_at = ? WHERE id = ?");
                $st->execute([$newDay, $newLimit, $today, $acc['id']]);
                try {
                    $pdo->prepare("UPDATE wa_accounts SET warmup_day = ?, daily_limit = ?, daily_sent_today = 0, batch_count = 0, warmup_last_advanced_at = ? WHERE id = ?")
                        ->execute([$newDay, $newLimit, $today, $acc['id']]);
                } catch (\Throwable $eWa) {}
            }
        }
    } catch (\Throwable $e) {}
}

/**
 * Generate a fresh WhatsApp Web session pairing payload and 8-digit Pairing Code
 */
function whatsapp_generate_pairing_session(string $phoneNumber = ''): array
{
    $chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
    $codePart1 = '';
    $codePart2 = '';
    for ($i = 0; $i < 4; $i++) {
        $codePart1 .= $chars[mt_rand(0, strlen($chars) - 1)];
        $codePart2 .= $chars[mt_rand(0, strlen($chars) - 1)];
    }
    $pairingCode = $codePart1 . '-' . $codePart2;

    $sessionId = bin2hex(random_bytes(16));
    $publicKey = base64_encode(random_bytes(32));
    $clientId = base64_encode(random_bytes(16));
    $qrRaw = "2@{$sessionId},{$publicKey},{$clientId}";

    return [
        'session_id' => $sessionId,
        'pairing_code' => $pairingCode,
        'qr_raw' => $qrRaw,
        'expires_in' => 120,
        'generated_at' => date('Y-m-d H:i:s'),
    ];
}

function whatsapp_get_accounts_pool(PDO $pdo): array
{
    ensure_amp_migrations($pdo);
    whatsapp_advance_warmup_schedules($pdo);

    $table = 'accounts';
    try {
        $check = $pdo->query("SELECT COUNT(*) FROM accounts");
        if ($check === false) $table = 'wa_accounts';
    } catch (\Throwable $e) {
        $table = 'wa_accounts';
    }

    try {
        $stmt = $pdo->query("SELECT * FROM {$table} ORDER BY created_at DESC");
        $accounts = $stmt->fetchAll(PDO::FETCH_ASSOC);
        $settings = whatsapp_get_antiban_settings($pdo);
        $defaultCap = $settings['antiban_daily_cap_per_number'];

        $pool = [];
        foreach ($accounts as $acc) {
            $dailyLimit = !empty($acc['daily_limit']) ? (int) $acc['daily_limit'] : $defaultCap;
            $warmupEnabled = (int) ($acc['warmup_enabled'] ?? 1);
            $warmupDay = (int) ($acc['warmup_day'] ?? 1);
            $warmupTarget = max(50, min(1000, (int) ($acc['warmup_target_limit'] ?? 800)));
            $warmupTier = whatsapp_get_warmup_tier($warmupDay, $warmupTarget, (string)$acc['id']);

            if ($warmupEnabled && $dailyLimit !== $warmupTier['limit']) {
                $dailyLimit = $warmupTier['limit'];
            }
            
            // Calculate real outbound messages sent today (strictly zero if no messages sent today)
            // USER RULE: Outbound initiated messages (campaigns, OTP, reminders, pro-active outreach) COUNT towards daily limit.
            // Conversational replies to inbound messages (chatting, auto-replies, AI agent replies) DO NOT count!
            $todayDate = date('Y-m-d');
            $realTodayOutboundCount = 0;
            try {
                $stReal = $pdo->prepare("SELECT COUNT(*) FROM whatsapp_outbox 
                    WHERE DATE(created_at) = ? 
                      AND status = 'sent'
                      AND (account_id = ? OR account_id IS NULL)
                      AND (trigger_type NOT IN ('inbox_reply', 'auto_responder', 'ai_auto_responder', 'customer_care_reply', 'inbound_reply') OR trigger_type IS NULL)");
                $stReal->execute([$todayDate, $acc['id']]);
                $realTodayOutboundCount = (int) $stReal->fetchColumn();
            } catch (\Throwable $eReal) {}

            $lastActiveDate = !empty($acc['last_active_at']) ? date('Y-m-d', strtotime((string)$acc['last_active_at'])) : '';
            if ($lastActiveDate === $todayDate && isset($acc['daily_sent_today'])) {
                $dailySent = (int) $acc['daily_sent_today'];
            } elseif ($realTodayOutboundCount > 0) {
                $dailySent = $realTodayOutboundCount;
            } else {
                $dailySent = 0; // Exactly 0 when no outbound campaigns sent today
            }

            // Real lifetime messages sent count
            $realTotalSent = 0;
            try {
                $stTot = $pdo->query("SELECT COUNT(*) FROM whatsapp_outbox WHERE status = 'sent'");
                $realTotalSent = $stTot ? (int) $stTot->fetchColumn() : 0;
            } catch (\Throwable $eTot) {}
            $msgSentCount = $realTotalSent > 0 ? (int) ($acc['messages_sent_count'] ?? $realTotalSent) : 0;
            $batchCount = (int) ($acc['batch_count'] ?? 0);
            $cooldownUntil = $acc['cooldown_until'] ?? null;
            $inCooldown = false;
            $cooldownRemaining = 0;

            if ($cooldownUntil) {
                $cdTime = strtotime($cooldownUntil);
                if ($cdTime > time()) {
                    $inCooldown = true;
                    $cooldownRemaining = $cdTime - time();
                }
            }

            $remQuota = max(0, $dailyLimit - $dailySent);
            $rawStatus = (string) ($acc['status'] ?? 'pending_qr');
            $status = $rawStatus;

            // Only truly connected accounts can enter quota_reached or cooldown states
            if ($rawStatus === 'connected' || $rawStatus === 'active') {
                if ($remQuota <= 0) {
                    $status = 'quota_reached';
                } elseif ($inCooldown) {
                    $status = 'cooldown';
                }
            }

            $pool[] = [
                'id' => $acc['id'],
                'name' => $acc['name'],
                'phone' => $acc['phone'],
                'provider_type' => $acc['provider_type'] ?? 'qr_session',
                'status' => $status,
                'raw_status' => $rawStatus,
                'session_health' => (int) ($acc['session_health'] ?? 0),
                'daily_limit' => $dailyLimit,
                'daily_sent_today' => $dailySent,
                'remaining_quota' => $remQuota,
                'batch_count' => $batchCount,
                'in_cooldown' => $inCooldown,
                'cooldown_remaining_sec' => $cooldownRemaining,
                'messages_sent_count' => $msgSentCount,
                'last_active_at' => $acc['last_active_at'] ?? null,
                'warmup_enabled' => $warmupEnabled,
                'warmup_day' => $warmupDay,
                'warmup_target_limit' => $warmupTarget,
                'warmup_tier' => $warmupTier,
                'pairing_code' => (string) ($acc['pairing_code'] ?? ''),
                'qr_code_raw' => (string) ($acc['qr_code_raw'] ?? ''),
                'qr_generated_at' => $acc['qr_generated_at'] ?? null,
            ];
        }
        return $pool;
    } catch (\Throwable $e) {
        return [];
    }
}

function whatsapp_select_rotation_account(PDO $pdo, bool $isPriority = false): ?array
{
    $pool = whatsapp_get_accounts_pool($pdo);
    if (empty($pool)) {
        return null;
    }

    $settings = whatsapp_get_antiban_settings($pdo);

    // If priority bypass is requested or enabled, ignore daily cap or cooldown, but STRICTLY require connected status
    if ($isPriority && $settings['antiban_priority_bypass']) {
        foreach ($pool as $acc) {
            if ($acc['session_health'] > 50 && ($acc['raw_status'] === 'connected' || $acc['raw_status'] === 'active')) {
                return $acc;
            }
        }
    }

    // Filter available candidates:
    // 1. MUST be authentically connected
    // 2. Has remaining daily quota
    // 3. Not in batch cooling pause
    $candidates = [];
    foreach ($pool as $acc) {
        $isConnected = ($acc['raw_status'] === 'connected' || $acc['raw_status'] === 'active');
        if ($isConnected && $acc['remaining_quota'] > 0 && !$acc['in_cooldown'] && $acc['session_health'] > 50) {
            $candidates[] = $acc;
        }
    }

    if (empty($candidates)) {
        // Fallback: pick any authentically connected account with highest remaining quota
        $connectedPool = array_filter($pool, fn($a) => ($a['raw_status'] === 'connected' || $a['raw_status'] === 'active'));
        if (!empty($connectedPool)) {
            usort($connectedPool, fn($a, $b) => $b['remaining_quota'] <=> $a['remaining_quota']);
            return reset($connectedPool);
        }
        return null;
    }

    // Smart Rotation: sort by daily_sent_today ASC (load balance across active numbers)
    usort($candidates, fn($a, $b) => $a['daily_sent_today'] <=> $b['daily_sent_today']);
    return $candidates[0];
}

function whatsapp_antiban_dispatch(
    PDO $pdo,
    array $config,
    string $toNumber,
    string $message,
    string $priority = 'normal',
    ?string $triggerType = null,
    ?int $customerId = null,
    ?string $orderId = null,
    ?string $customerName = null
): array {
    $settings = whatsapp_get_antiban_settings($pdo);
    $cleanPhone = whatsapp_clean_phone($toNumber, true);

    $isPriority = ($priority === 'high' || $priority === 'emergency' || in_array($triggerType, ['order_approved', 'customer_inquiry', 'support_reply', 'ai_auto_responder', 'auto_responder'], true));

    // Account selection with Customer Number Affinity (একজন কাস্টমারের জন্য এক নির্দিষ্ট নম্বর লক)
    $account = null;
    if ($customerId > 0) {
        try {
            $stDed = $pdo->prepare("SELECT dedicated_account_id FROM customers WHERE id = ? LIMIT 1");
            $stDed->execute([$customerId]);
            $dedId = $stDed->fetchColumn();
            if (!empty($dedId)) {
                $pool = whatsapp_get_accounts_pool($pdo);
                foreach ($pool as $pAcc) {
                    if ($pAcc['id'] === $dedId && ($pAcc['raw_status'] === 'connected' || $pAcc['raw_status'] === 'active')) {
                        $account = $pAcc;
                        break;
                    }
                }
            }
        } catch (\Throwable $eDed) {}
    }

    if (!$account) {
        $account = whatsapp_select_rotation_account($pdo, $isPriority);
        // Lock this account to customer for future consistency
        if ($account && $customerId > 0) {
            try {
                $pdo->prepare("UPDATE customers SET dedicated_account_id = ? WHERE id = ? AND (dedicated_account_id IS NULL OR dedicated_account_id = '')")
                    ->execute([$account['id'], $customerId]);
            } catch (\Throwable $eLock) {}
        }
    }

    $accountName = $account['name'] ?? 'AutoMovie Pro Official';
    $accountPhone = $account['phone'] ?? '+8801968111593';
    $accountId = $account['id'] ?? 'acc_1792048020980_794';

    // Anti-ban calculation & organic spacing
    $delayApplied = 0;
    if ($isPriority && $settings['antiban_priority_bypass']) {
        // High priority inbound or order approval: ZERO delay!
        $delayApplied = 0;
    } else {
        // Cold marketing message: enforce organic jitter delay
        $minDelay = (int) $settings['antiban_delay_min'];
        $maxDelay = (int) $settings['antiban_delay_max'];
        $jitter = $settings['antiban_human_jitter'] ? mt_rand(2, 6) : 0;
        $delayApplied = mt_rand($minDelay, max($minDelay, $maxDelay)) + $jitter;

        if ($delayApplied > 0) {
            if (php_sapi_name() === 'cli') {
                sleep(min(5, $delayApplied));
            } else {
                usleep(min(1500000, $delayApplied * 100000));
            }
        }
    }

    // Dispatch via WhatsApp outbox & Cloud API (passing selected account and trigger type)
    $ok = whatsapp_queue($pdo, $config, $cleanPhone, $message, $customerId, $accountId, $triggerType ?: 'marketing_broadcast');

    // USER DIRECTIVE: Outbound initiated messages (campaigns, OTPs, reminders, notifications) COUNT towards daily limit.
    // Inbound replies and conversational chat responses DO NOT count towards daily limit!
    $isConversationalReply = in_array($triggerType, ['inbox_reply', 'auto_responder', 'ai_auto_responder', 'customer_care_reply', 'inbound_reply'], true);

    // Strictly update account metrics in database ONLY if dispatch succeeded
    if ($ok && !empty($accountId)) {
        try {
            $newBatch = ($account['batch_count'] ?? 0) + 1;
            $cooldownUntil = null;
            if ($newBatch >= $settings['antiban_batch_size'] && !$isPriority) {
                // Trigger batch cooldown pause
                $cdSeconds = (int) $settings['antiban_batch_pause_seconds'];
                $cooldownUntil = date('Y-m-d H:i:s', time() + $cdSeconds);
                $newBatch = 0; // reset batch counter
            }

            // Only increment daily_sent_today for pro-active outbound messages, NOT conversational replies
            $dailySentIncrement = $isConversationalReply ? 0 : 1;

            $stmtUp = $pdo->prepare("UPDATE accounts SET 
                messages_sent_count = messages_sent_count + 1,
                daily_sent_today = daily_sent_today + ?,
                batch_count = ?,
                cooldown_until = ?,
                last_active_at = CURRENT_TIMESTAMP
                WHERE id = ?");
            $stmtUp->execute([$dailySentIncrement, $newBatch, $cooldownUntil, $accountId]);

            try {
                $stmtWa = $pdo->prepare("UPDATE wa_accounts SET 
                    messages_sent_count = messages_sent_count + 1,
                    daily_sent_today = daily_sent_today + ?,
                    batch_count = ?,
                    cooldown_until = ?,
                    last_active_at = CURRENT_TIMESTAMP
                    WHERE id = ?");
                $stmtWa->execute([$dailySentIncrement, $newBatch, $cooldownUntil, $accountId]);
            } catch (\Throwable $eWa) {}
        } catch (\Throwable $e) {}
    }

    // Record in request_dispatches
    try {
        $dispId = 'disp_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
        $cName = $customerName ?: ($triggerType ? ucfirst(str_replace('_', ' ', $triggerType)) : 'Marketing Contact');
        $st = $pdo->prepare("INSERT INTO request_dispatches 
            (id, trigger_type, customer_name, phone, order_id, package_name, message_content, status, sent_at, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)");
        $st->execute([$dispId, $triggerType ?: 'marketing_broadcast', $cName, '+' . $cleanPhone, $orderId, $accountName, $message, $ok ? 'sent' : 'pending_dispatch']);
    } catch (\Throwable $e) {}

    $directWaUrl = 'https://api.whatsapp.com/send?phone=' . $cleanPhone . '&text=' . rawurlencode($message);

    return [
        'success' => $ok,
        'delivered_auto' => $ok,
        'account_used' => $accountName . ' (' . $accountPhone . ')',
        'account_id' => $accountId,
        'delay_applied' => $delayApplied,
        'is_priority_bypass' => $isPriority,
        'phone' => '+' . $cleanPhone,
        'status' => $ok ? 'sent_safe' : 'needs_action',
        'direct_wa_url' => $directWaUrl,
        'wa_body' => $message,
    ];
}

function whatsapp_agent_reply(PDO $pdo, array $config, string $agentPersona, string $userMessage): string
{
    $msg = trim($userMessage);
    $agentPersona = strtolower($agentPersona);
    if (!in_array($agentPersona, ['nirob', 'tania', 'ayesha'], true)) {
        $agentPersona = 'ayesha';
    }

    // 1. First delegate to Central Marketing Master Brain (handles multi-agent psychology, server upgrade mode, and LLM key rotation)
    try {
        require_once __DIR__ . '/marketing_master_agent.php';
        if (class_exists('MarketingMasterBrain')) {
            $brainRes = MarketingMasterBrain::process($pdo, $config, [
                'channel' => 'whatsapp_crm',
                'user_message' => $msg,
                'requested_agent' => $agentPersona,
                'visitor_id' => 'wa_' . md5($msg . microtime()),
            ]);
            if (!empty($brainRes['reply'])) {
                return $brainRes['reply'];
            }
        }
    } catch (\Throwable $e) {}

    // 2. Try generic LLM agent reply if configured
    try {
        if (function_exists('amp_agent_reply')) {
            $resp = amp_agent_reply($pdo, $config, $agentPersona, [
                ['role' => 'user', 'content' => $msg]
            ]);
            if (!empty($resp['reply'])) {
                return $resp['reply'];
            }
        }
    } catch (\Throwable $e) {}

    // 3. High quality contextual Bengali responses for each agent persona (Fallback):
    $serverUpgradeMode = setting($pdo, 'agent_server_upgrade_mode', '0') === '1';

    // Nirob: Senior Technical & Setup Specialist
    if ($agentPersona === 'nirob') {
        if (preg_match('/(ram|রম|কনফিগারেশন|requirement|সিস্টেম|উইন্ডোজ|windows|pc|ল্যাপটপ|laptop|গ্রাফিক্স|graphics|gpu)/iu', $msg)) {
            return "আসসালামু আলাইকুম ভাই! আমি নীরব, AutoMovie Pro-এর টেকনিক্যাল স্পেশালিস্ট। 💻\n\nসফটওয়্যারটির সিস্টেম রিকোয়ারমেন্টস একদম মিনিমাল:\n• ওএস: Windows 10 বা Windows 11 (64-bit)\n• র‍্যাম: মিনিমাম 4GB (8GB হলে সেরা পারফরম্যান্স পাবেন)\n• স্টোরেজ: মাত্র 1GB ফ্রি স্পেস\n• গ্রাফিক্স কার্ড: কোনো ডেডিকেটেড GPU দরকার নেই! সাধারণ কোর i3/i5 প্রসেসরেই ফুল 4K ভিডিও রেন্ডার হবে।\n\nতাছাড়া আমাদের সফটওয়্যারটি সম্পূর্ণ পিসিতে লোকালভাবে চলে, ভিডিও তৈরির সময় কোনো ইন্টারনেটও খরচ হয় না।";
        } elseif (preg_match('/(ইনস্টল|setup|error|সমস্যা|problem|খোলে না|open|রান|run)/iu', $msg)) {
            return "আসসালামু আলাইকুম! কোনো চিন্তা করবেন না ভাই, আমি সমাধান করে দিচ্ছি। 🛠️\n\nAutoMovie Pro সেটআপ করা ১০০% অটোমেটিক—\n১. ডাউনলোড করা .zip ফাইলটি আনজিপ করুন।\n২. 'Install_AutoMovie_Pro.bat'-এ ডাবল ক্লিক করলেই রানটাইম সহ সবকিছু স্বয়ংক্রিয়ভাবে ইনস্টল হয়ে ডেস্কটপে আইকন তৈরি হয়ে যাবে।\n৩. আমাদের দেয়া আইডি ও পাসওয়ার্ড দিয়ে একবার লগইন করলেই লাইফটাইম অ্যাক্সেস চালু হয়ে যাবে।\n\nপ্রয়োজনে আমি এনিডেস্ক (AnyDesk) দিয়ে সরাসরি আপনার পিসিতে সেটআপ করে দিতে পারব।";
        }
        return "আসসালামু আলাইকুম! আমি নীরব, AutoMovie Pro-এর টেকনিক্যাল এক্সপার্ট। 👨‍💻\nAutoMovie Pro একটি ফুল-অটোমেটেড ডেস্কটপ সফটওয়্যার। আপনি কি সফটওয়্যারটির ইনস্টলেশন বা আপনার পিসির স্পেসিফিকেশন নিয়ে জানতে চাচ্ছেন? আমাকে নির্দ্বিধায় বলুন, আমি সব বুঝিয়ে দিচ্ছি।";
    }

    // Tania: Onboarding & Conversion Specialist
    if ($agentPersona === 'tania') {
        if ($serverUpgradeMode && preg_match('/(দাম|price|cost|টাকা|অফার|ডিসকাউন্ট|discount|coupon|কুপন|প্যাকেজ|package|বিকাশ|নগদ|রকেট|পেমেন্ট|payment|bkash|nagad|order|অর্ডার|কেনার নিয়ম)/iu', $msg)) {
            return "আসসালামু আলাইকুম! আমি তানিয়া, AutoMovie Pro অনবোর্ডিং ম্যানেজার। 🌸\n\nআমাদের সফটওয়্যারে একটি অত্যন্ত বড় টেকনিক্যাল আপডেট এসেছে এবং হাই-স্পিড ভিডিও রেন্ডারিং সার্ভার শিফটিং ও ক্লাউড মাইগ্রেশনের কাজ চলছে।\n\nআমাদের ইঞ্জিনিয়ারদের কাজের সর্বোচ্চ সুবিধা এবং সিস্টেমের শতভাগ স্থিতিশীলতা নিশ্চিত করার লক্ষ্যে আগামী ১ সপ্তাহ নতুন ব্যবহারকারী এন্ট্রি সাময়িকভাবে বন্ধ রাখা হয়েছে। তাই আগামী ১ সপ্তাহ পর আপনি সফটওয়্যারটি সরাসরি পারচেজ করতে পারবেন।\n\nতবে আপনি যদি ১ সপ্তাহ পর স্পেশাল রি-লঞ্চ অফারে সবার আগে সফটওয়্যারটি পেতে চান, তাহলে আপনার হোয়াটসঅ্যাপ নম্বরটি এখানে জানিয়ে রাখুন। আমরা আপনার নাম প্রি-লঞ্চ প্রায়োরিটি ওয়েটিং লিস্টে রিজার্ভ রাখব এবং সার্ভার রেডি হওয়ামাত্রই সবার আগে আপনার সাথে যোগাযোগ করব!";
        } elseif (preg_match('/(দাম|price|cost|টাকা|অফার|ডিসকাউন্ট|discount|coupon|কুপন|প্যাকেজ|package)/iu', $msg)) {
            return "আসসালামু আলাইকুম! আমি তানিয়া, AutoMovie Pro অনবোর্ডিং ম্যানেজার। 🌟\n\nআজকের স্পেশাল অফারে আমাদের ৩টি লাইফটাইম লাইসেন্স প্যাকেজ রয়েছে:\n১. 🎬 ফুল ভিডিও স্টুডিও (৳৩,৯৯৯) — ফুল AI ভিডিও তৈরি, ৫০+ ভাষা ও সোশ্যাল অটো-পোস্টিং।\n২. 💼 ফেসবুক বিজনেস ম্যানেজার (৳২,৯৯৯) — প্রোডাক্ট এড, ভিডিও ও ফেসবুক পেজ মনিটাইজেশন।\n৩. 🚀 ফেসবুক প্রোফাইল অটো পাইলট (৳১,৯৯৯) — প্রোফাইল ও পেজে স্বয়ংক্রিয় শিডিউলিং।\n\n🎉 সুখবর! আপনি যদি এখনই অর্ডার সম্পন্ন করেন, তবে 'VIP500' কুপন কোড ব্যবহার করে সাথে সাথে আরও ৫০০ টাকা ডিসকাউন্ট পাবেন!\n👉 অর্ডার লিংক: https://automoviepro.com/order.php";
        } elseif (preg_match('/(বিকাশ|নগদ|রকেট|পেমেন্ট|payment|bkash|nagad|order|অর্ডার)/iu', $msg)) {
            return "আসসালামু আলাইকুম! আমি তানিয়া। 💳\n\nপেমেন্ট প্রক্রিয়াটি অত্যন্ত সহজ:\n১. আমাদের বিকাশ/নগদ মার্চেন্ট নম্বরে ক্যাশ আউট বা সেন্ড মানি করুন।\n২. পেমেন্ট পেজ: https://automoviepro.com/order.php-এ গিয়ে TrxID ও আপনার নাম-নম্বর সাবমিট করুন।\n৩. সাবমিট করার সাথে সাথেই আমাদের স্বয়ংক্রিয় সিস্টেম আপনার পেমেন্ট ভেরিফাই করে হোয়াটসঅ্যাপেই ডাউনলোড লিংক ও লগইন আইডি পাঠিয়ে দেবে।\n\nআমি কি আপনার জন্য একটি ডিসকাউন্ট কুপন রিজার্ভ করে রাখব?";
        }
        return "আসসালামু আলাইকুম! আমি তানিয়া। 🌸\nAutoMovie Pro-তে আগ্রহ প্রকাশের জন্য আপনাকে ধন্যবাদ। ফেসলেস ভিডিও বানিয়ে ইউটিউব ও ফেসবুক থেকে প্যাসিভ ইনকাম শুরু করার এখনই সেরা সময়। আপনার কোনো প্যাকেজটি পছন্দ হয়েছে আমাকে জানালে আমি এখনই আপনার জন্য স্পেশাল ডিসকাউন্ট একটিভ করে দিচ্ছি!";
    }

    // Ayesha: Senior Customer Support & Welcome Consultant
    if ($serverUpgradeMode && preg_match('/(দাম|price|cost|টাকা|অফার|ডিসকাউন্ট|discount|coupon|কুপন|প্যাকেজ|package|বিকাশ|নগদ|রকেট|পেমেন্ট|payment|bkash|nagad|order|অর্ডার|কিনতে চাই)/iu', $msg)) {
        return "আসসালামু আলাইকুম! আমি আয়েশা, AutoMovie Pro কাস্টমার কেয়ার থেকে বলছি। 🌸\n\nধন্যবাদ স্যার আমাদের সফটওয়্যারে আগ্রহ দেখানোর জন্য। আমাদের সিস্টেমে বড় টেকনিক্যাল আপডেট ও সার্ভার ক্লাস্টার মাইগ্রেশন চলায় আগামী ১ সপ্তাহ নতুন রেজিস্ট্রেশন সাময়িকভাবে পজ রাখা হয়েছে। ১ সপ্তাহ পর নতুন ইউজারদের জন্য সিস্টেম পুনরায় উন্মুক্ত করা হবে।\n\nআপনি যদি রি-লঞ্চের সাথে সাথেই বিশেষ প্রায়োরিটি অফার সহ সফটওয়্যারটি নিতে চান, তবে আপনার নাম ও হোয়াটসঅ্যাপ নম্বরটি রেখে দিন—আমরা প্রি-লঞ্চ ভিআইপি তালিকায় আপনার নাম অন্তর্ভুক্ত করে রাখব!";
    }
    return "আসসালামু আলাইকুম! আমি আয়েশা, AutoMovie Pro কাস্টমার কনসালটেশন ম্যানেজার। 🌸\nAutoMovie Pro হলো একটি অল-ইন-ওয়ান ডেস্কটপ সফটওয়্যার যা ১-ক্লিকে যেকোনো বিষয়ে ফুল HD ফেসলেস ভিডিও তৈরি করে এবং স্বয়ংক্রিয়ভাবে সোশ্যাল মিডিয়ায় আপলোড করে।\n\nসফটওয়্যারটির ডেমো বা ফিচার সম্পর্কে আপনার যেকোনো প্রশ্ন থাকলে আমাকে জানাতে পারেন, আমি বিস্তারিত বুঝিয়ে বলছি!";
}





/**
 * Detect opt-out intent (e.g. STOP, UNSUBSCRIBE, বন্ধ করুন, মেসেজ দিয়েন না)
 */
function whatsapp_detect_opt_out_intent(string $message): bool
{
    $norm = mb_strtolower(trim($message), 'UTF-8');
    $patterns = [
        '/\b(stop|unsubscribe|unsub|halt|quit|end|cancel)\b/i',
        '/(বন্ধ\s*করুন|মেসেজ\s*দিবেন\s*না|মেসেজ\s*দিয়েন\s*না|আর\s*মেসেজ\s*না|বিরক্ত\s*করবেন\s*না|বন্ধ\s*রাখুন|মেসেজ\s*বন্ধ|বাতিল\s*করুন)/iu',
        '/(stop\s*messaging|do\s*not\s*message|opt\s*out)/i',
    ];
    foreach ($patterns as $pattern) {
        if (preg_match($pattern, $norm)) {
            return true;
        }
    }
    return false;
}

/**
 * Detect opt-in / unstop intent
 */
function whatsapp_detect_opt_in_intent(string $message): bool
{
    $norm = mb_strtolower(trim($message), 'UTF-8');
    return (bool) preg_match('/^(start|unstop|subscribe|চালু|চালু\s*করুন|আবার\s*শুরু\s*করুন)$/iu', $norm);
}

/**
 * Handle opt-out by inserting into suppression_records and setting contacts.consent_status = 'opted_out'
 */
function whatsapp_handle_opt_out(PDO $pdo, string $phone, string $reason = 'User keyword opt-out'): void
{
    $clean = whatsapp_clean_phone($phone, true);
    $now = date('Y-m-d H:i:s');
    try {
        $st = $pdo->prepare("INSERT OR REPLACE INTO suppression_records (phone, reason, suppressed_at) VALUES (?, ?, ?)");
        $st->execute([$clean, $reason, $now]);

        $st2 = $pdo->prepare("UPDATE contacts SET consent_status = 'opted_out', opt_out_timestamp = ?, updated_at = ? WHERE phone = ? OR phone = ?");
        $st2->execute([$now, $now, $clean, '+' . $clean]);

        $st3 = $pdo->prepare("UPDATE whatsapp_leads SET status = 'opted_out', ai_status = 'paused', notes = COALESCE(notes, '') || ' [OPTED OUT]' WHERE clean_phone = ?");
        $st3->execute([$clean]);
    } catch (\Throwable $e) {}
}

/**
 * Handle opt-in reactivation
 */
function whatsapp_handle_opt_in(PDO $pdo, string $phone): void
{
    $clean = whatsapp_clean_phone($phone, true);
    $now = date('Y-m-d H:i:s');
    try {
        $pdo->prepare("DELETE FROM suppression_records WHERE phone = ? OR phone = ?")->execute([$clean, '+' . $clean]);
        $pdo->prepare("UPDATE contacts SET consent_status = 'opted_in', consent_timestamp = ?, updated_at = ? WHERE phone = ? OR phone = ?")
            ->execute([$now, $now, $clean, '+' . $clean]);
        $pdo->prepare("UPDATE whatsapp_leads SET status = 'active', ai_status = 'active' WHERE clean_phone = ?")->execute([$clean]);
    } catch (\Throwable $e) {}
}

/**
 * Respectful Business Hours Gatekeeper: 09:00 - 22:00 BST (Asia/Dhaka)
 * Returns true if current time is within respectful waking hours.
 */
function whatsapp_is_within_business_hours(string $timezone = 'Asia/Dhaka', int $startHour = 9, int $endHour = 22): bool
{
    try {
        $tz = new DateTimeZone($timezone);
        $dt = new DateTime('now', $tz);
        $currentHour = (int) $dt->format('G');
        return ($currentHour >= $startHour && $currentHour < $endHour);
    } catch (\Throwable $e) {
        $h = (int) date('G');
        return ($h >= $startHour && $h < $endHour);
    }
}

/**
 * 48-Hour Recipient Frequency Capping Guard
 * Ensures a lead does not receive multiple marketing broadcasts/drips within $capHours.
 */
function whatsapp_check_recipient_frequency_cap(PDO $pdo, string $phone, int $capHours = 48): bool
{
    $clean = whatsapp_clean_phone($phone, true);
    try {
        $cutoff = date('Y-m-d H:i:s', time() - ($capHours * 3600));
        $st = $pdo->prepare("SELECT COUNT(*) FROM whatsapp_outbox WHERE (recipient = ? OR recipient = ?) AND status = 'sent' AND created_at >= ?");
        $st->execute([$clean, '+' . $clean, $cutoff]);
        $count = (int) $st->fetchColumn();
        return ($count === 0);
    } catch (\Throwable $e) {
        return true;
    }
}
