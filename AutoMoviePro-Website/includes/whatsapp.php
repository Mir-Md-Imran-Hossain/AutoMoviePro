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
    if ($token === '') {
        $token = trim((string) setting($pdo, 'whatsapp_token', ''));
    }
    $phoneId = trim((string) ($config['whatsapp_phone_id'] ?? ''));
    if ($phoneId === '') {
        $phoneId = trim((string) setting($pdo, 'whatsapp_phone_id', ''));
    }

    if ($token === '' || $phoneId === '') {
        try {
            $accStmt = $pdo->query("SELECT api_config FROM wa_accounts WHERE (status = 'connected' OR status = 'active') AND api_config IS NOT NULL ORDER BY id ASC LIMIT 1");
            if ($accStmt && ($accRow = $accStmt->fetch(PDO::FETCH_ASSOC))) {
                $accCfg = json_decode((string) ($accRow['api_config'] ?? ''), true);
                if (is_array($accCfg)) {
                    if (empty($token) && !empty($accCfg['access_token'])) $token = trim((string) $accCfg['access_token']);
                    if (empty($phoneId) && !empty($accCfg['phone_number_id'])) $phoneId = trim((string) $accCfg['phone_number_id']);
                }
            }
        } catch (\Throwable $eAcc) {}
    }

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

function whatsapp_get_accounts_pool(PDO $pdo): array
{
    ensure_amp_migrations($pdo);
    $table = 'accounts';
    try {
        $check = $pdo->query("SELECT COUNT(*) FROM accounts");
        if ($check === false) $table = 'wa_accounts';
    } catch (\Throwable $e) {
        $table = 'wa_accounts';
    }

    try {
        $stmt = $pdo->query("SELECT * FROM {$table} ORDER BY id ASC");
        $accounts = $stmt->fetchAll(PDO::FETCH_ASSOC);
        $settings = whatsapp_get_antiban_settings($pdo);
        $defaultCap = $settings['antiban_daily_cap_per_number'];

        $pool = [];
        foreach ($accounts as $acc) {
            $dailyLimit = !empty($acc['daily_limit']) ? (int) $acc['daily_limit'] : $defaultCap;
            $dailySent = !empty($acc['daily_sent_today']) ? (int) $acc['daily_sent_today'] : ((int) ($acc['messages_sent_count'] ?? 0) % $dailyLimit);
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
            $status = $acc['status'] ?? 'connected';
            if ($remQuota <= 0) {
                $status = 'quota_reached';
            } elseif ($inCooldown) {
                $status = 'cooldown';
            }

            $pool[] = [
                'id' => $acc['id'],
                'name' => $acc['name'],
                'phone' => $acc['phone'],
                'provider_type' => $acc['provider_type'] ?? 'cloud_api',
                'status' => $status,
                'session_health' => (int) ($acc['session_health'] ?? 100),
                'daily_limit' => $dailyLimit,
                'daily_sent_today' => $dailySent,
                'remaining_quota' => $remQuota,
                'batch_count' => $batchCount,
                'in_cooldown' => $inCooldown,
                'cooldown_remaining_sec' => $cooldownRemaining,
                'messages_sent_count' => (int) ($acc['messages_sent_count'] ?? 0),
                'last_active_at' => $acc['last_active_at'] ?? null,
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

    // If priority bypass is requested or enabled, ignore daily cap or cooldown
    if ($isPriority && $settings['antiban_priority_bypass']) {
        foreach ($pool as $acc) {
            if ($acc['session_health'] > 50) {
                return $acc;
            }
        }
        return $pool[0];
    }

    // Filter available candidates:
    // 1. Has remaining daily quota
    // 2. Not in batch cooling pause
    $candidates = [];
    foreach ($pool as $acc) {
        if ($acc['remaining_quota'] > 0 && !$acc['in_cooldown'] && $acc['session_health'] > 50) {
            $candidates[] = $acc;
        }
    }

    if (empty($candidates)) {
        // Fallback: pick any account with highest remaining quota
        usort($pool, fn($a, $b) => $b['remaining_quota'] <=> $a['remaining_quota']);
        return $pool[0] ?? null;
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
    ?int $customerId = null
): array {
    $settings = whatsapp_get_antiban_settings($pdo);
    $cleanPhone = whatsapp_clean_phone($toNumber, true);

    $isPriority = ($priority === 'high' || $priority === 'emergency' || in_array($triggerType, ['order_approved', 'customer_inquiry', 'support_reply'], true));

    // Account selection
    $account = whatsapp_select_rotation_account($pdo, $isPriority);
    $accountName = $account['name'] ?? 'Primary Account';
    $accountPhone = $account['phone'] ?? '+8801968111593';
    $accountId = $account['id'] ?? 'acc_cloud_official';

    // Anti-ban calculation
    $delayApplied = 0;
    if ($isPriority && $settings['antiban_priority_bypass']) {
        // High priority inbound or order approval: ZERO delay!
        $delayApplied = 0;
    } else {
        // Cold marketing message: enforce jitter delay
        $minDelay = $settings['antiban_delay_min'];
        $maxDelay = $settings['antiban_delay_max'];
        $jitter = $settings['antiban_human_jitter'] ? mt_rand(2, 8) : 0;
        $delayApplied = mt_rand($minDelay, max($minDelay, $maxDelay)) + $jitter;
    }

    // Update account metrics in database
    $table = 'accounts';
    try {
        $newBatch = ($account['batch_count'] ?? 0) + 1;
        $cooldownSql = "NULL";
        if ($newBatch >= $settings['antiban_batch_size'] && !$isPriority) {
            // Trigger batch pause
            $cdSeconds = $settings['antiban_batch_pause_seconds'];
            $cdTime = date('Y-m-d H:i:s', time() + $cdSeconds);
            $cooldownSql = "'{$cdTime}'";
            $newBatch = 0; // reset batch counter
        }

        $now = amp_sql_now($pdo);
        $pdo->exec("UPDATE accounts SET 
            messages_sent_count = messages_sent_count + 1,
            daily_sent_today = daily_sent_today + 1,
            batch_count = {$newBatch},
            cooldown_until = {$cooldownSql},
            last_active_at = {$now}
            WHERE id = '{$accountId}'");
    } catch (\Throwable $e) {}

    // Dispatch via WhatsApp outbox & Cloud API
    $ok = whatsapp_queue($pdo, $config, $cleanPhone, $message, $customerId);

    // Record in request_dispatches
    try {
        $dispId = 'disp_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
        $st = $pdo->prepare("INSERT INTO request_dispatches 
            (id, trigger_type, customer_name, phone, package_name, message_content, status, sent_at, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, 'sent', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)");
        $cName = $triggerType ? ucfirst(str_replace('_', ' ', $triggerType)) : 'Marketing Contact';
        $st->execute([$dispId, $triggerType ?: 'marketing_broadcast', $cName, '+' . $cleanPhone, $accountName, $message]);
    } catch (\Throwable $e) {}

    return [
        'success' => $ok,
        'account_used' => $accountName . ' (' . $accountPhone . ')',
        'account_id' => $accountId,
        'delay_applied' => $delayApplied,
        'is_priority_bypass' => $isPriority,
        'phone' => '+' . $cleanPhone,
        'status' => 'sent_safe'
    ];
}

function whatsapp_simulate_agent_reply(PDO $pdo, array $config, string $agentPersona, string $userMessage): string
{
    $msg = trim($userMessage);
    $agentPersona = strtolower($agentPersona);

    // Try real LLM if configured
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

    // High quality contextual Bengali responses for each agent:
    if ($agentPersona === 'nirob') {
        // Nirob: Senior Technical & Setup Specialist
        if (preg_match('/(ram|রম|কনফিগারেশন|requirement|সিস্টেম|উইন্ডোজ|windows|pc|ল্যাপটপ|laptop|গ্রাফিক্স|graphics|gpu)/iu', $msg)) {
            return "আসসালামু আলাইকুম ভাই! আমি নীরব, AutoMovie Pro-এর টেকনিক্যাল স্পেশালিস্ট। 💻\n\nসফটওয়্যারটির সিস্টেম রিকোয়ারমেন্টস একদম মিনিমাল:\n• ওএস: Windows 10 বা Windows 11 (64-bit)\n• র‍্যাম: মিনিমাম 4GB (8GB হলে সেরা পারফরম্যান্স পাবেন)\n• স্টোরেজ: মাত্র 1GB ফ্রি স্পেস\n• গ্রাফিক্স কার্ড: কোনো ডেডিকেটেড GPU দরকার নেই! সাধারণ কোর i3/i5 প্রসেসরেই ফুল 4K ভিডিও রেন্ডার হবে।\n\nতাছাড়া আমাদের সফটওয়্যারটি সম্পূর্ণ পিসিতে লোকালভাবে চলে, ভিডিও তৈরির সময় কোনো ইন্টারনেটও খরচ হয় না।";
        } elseif (preg_match('/(ইনস্টল|setup|error|সমস্যা|problem|খোলে না|open|রান|run)/iu', $msg)) {
            return "আসসালামু আলাইকুম! কোনো চিন্তা করবেন না ভাই, আমি সমাধান করে দিচ্ছি। 🛠️\n\nAutoMovie Pro সেটআপ করা ১০০% অটোমেটিক—\n১. ডাউনলোড করা .zip ফাইলটি আনজিপ করুন।\n২. 'Install_AutoMovie_Pro.bat'-এ ডাবল ক্লিক করলেই রানটাইম সহ সবকিছু স্বয়ংক্রিয়ভাবে ইনস্টল হয়ে ডেস্কটপে আইকন তৈরি হয়ে যাবে।\n৩. আমাদের দেয়া আইডি ও পাসওয়ার্ড দিয়ে একবার লগইন করলেই লাইফটাইম অ্যাক্সেস চালু হয়ে যাবে।\n\nপ্রয়োজনে আমি এনিডেস্ক (AnyDesk) দিয়ে সরাসরি আপনার পিসিতে সেটআপ করে দিতে পারব।";
        }
        return "আসসালামু আলাইকুম! আমি নীরব, AutoMovie Pro-এর টেকনিক্যাল এক্সপার্ট। 👨‍💻\nAutoMovie Pro একটি ফুল-অটোমেটেড ডেস্কটপ সফটওয়্যার। আপনি কি সফটওয়্যারটির ইনস্টলেশন বা আপনার পিসির স্পেসিফিকেশন নিয়ে জানতে চাচ্ছেন? আমাকে নির্দ্বিধায় বলুন, আমি সব বুঝিয়ে দিচ্ছি।";
    }

    if ($agentPersona === 'tania') {
        // Tania: Onboarding & Conversion Specialist
        if (preg_match('/(দাম|price|cost|টাকা|অফার|ডিসকাউন্ট|discount|coupon|কুপন|প্যাকেজ|package)/iu', $msg)) {
            return "আসসালামু আলাইকুম! আমি তানিয়া, AutoMovie Pro অনবোর্ডিং ম্যানেজার। 🌟\n\nআজকের স্পেশাল অফারে আমাদের ৩টি লাইফটাইম লাইসেন্স প্যাকেজ রয়েছে:\n১. 🎬 ফুল ভিডিও স্টুডিও (৳৩,৯৯৯) — ফুল AI ভিডিও তৈরি, ৫০+ ভাষা ও সোশ্যাল অটো-পোস্টিং।\n২. 💼 ফেসবুক বিজনেস ম্যানেজার (৳২,৯৯৯) — প্রোডাক্ট এড, ভিডিও ও ফেসবুক পেজ মনিটাইজেশন।\n৩. 🚀 ফেসবুক প্রোফাইল অটো পাইলট (৳১,৯৯৯) — প্রোফাইল ও পেজে স্বয়ংক্রিয় শিডিউলিং।\n\n🎉 সুখবর! আপনি যদি এখনই অর্ডার সম্পন্ন করেন, তবে 'VIP500' কুপন কোড ব্যবহার করে সাথে সাথে আরও ৫০০ টাকা ডিসকাউন্ট পাবেন!\n👉 অর্ডার লিংক: https://automoviepro.com/order.php";
        } elseif (preg_match('/(বিকাশ|নগদ|রকেট|পেমেন্ট|payment|bkash|nagad|order|অর্ডার)/iu', $msg)) {
            return "আসসালামু আলাইকুম! আমি তানিয়া। 💳\n\nপেমেন্ট প্রক্রিয়াটি অত্যন্ত সহজ:\n১. আমাদের বিকাশ/নগদ মার্চেন্ট নম্বরে ক্যাশ আউট বা সেন্ড মানি করুন।\n২. পেমেন্ট পেজ: https://automoviepro.com/order.php-এ গিয়ে TrxID ও আপনার নাম-নম্বর সাবমিট করুন।\n৩. সাবমিট করার সাথে সাথেই আমাদের স্বয়ংক্রিয় সিস্টেম আপনার পেমেন্ট ভেরিফাই করে হোয়াটসঅ্যাপেই ডাউনলোড লিংক ও লগইন আইডি পাঠিয়ে দেবে।\n\nআমি কি আপনার জন্য একটি ডিসকাউন্ট কুপন রিজার্ভ করে রাখব?";
        }
        return "আসসালামু আলাইকুম! আমি তানিয়া। 🌸\nAutoMovie Pro-তে আগ্রহ প্রকাশের জন্য আপনাকে ধন্যবাদ। ফেসলেস ভিডিও বানিয়ে ইউটিউব ও ফেসবুক থেকে প্যাসিভ ইনকাম শুরু করার এখনই সেরা সময়। আপনার কোনো প্যাকেজটি পছন্দ হয়েছে আমাকে জানালে আমি এখনই আপনার জন্য স্পেশাল ডিসকাউন্ট একটিভ করে দিচ্ছি!";
    }

    // Default: Ayesha (Customer Care Lead)
    return "আসসালামু আলাইকুম! আমি আয়েশা, AutoMovie Pro কাস্টমার রিলেশনশিপ টিম থেকে বলছি। 🌸\n\nকীভাবে আপনাকে সহযোগিতা করতে পারি জানাবেন কি?\nআমাদের সফটওয়্যারটি দিয়ে আপনি কোনো ফেস বা ভয়েস না দেখিয়েই সম্পূর্ণ স্বয়ংক্রিয়ভাবে ভাইরাল ভিডিও ও ফেসবুক পোস্ট তৈরি করতে পারবেন। কোনো কিছু জানার থাকলে বলুন, আমি সম্পূর্ণ গাইড করছি।";
}


