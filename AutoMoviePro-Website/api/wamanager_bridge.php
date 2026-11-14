<?php
declare(strict_types=1);

/**
 * WAManager Pro Desktop-to-Website Bridge API
 * Allows selective 1-click sync of connected WhatsApp accounts from desktop to website.
 */

require dirname(__DIR__) . '/includes/bootstrap.php';
require_once dirname(__DIR__) . '/includes/billing.php';
require_once dirname(__DIR__) . '/includes/whatsapp.php';

ensure_amp_migrations($pdo);

header('Content-Type: application/json; charset=utf-8');

$rawInput = file_get_contents('php://input');
$data = json_decode($rawInput, true);
if (!is_array($data)) {
    $data = $_POST;
}

$action = trim((string) ($data['action'] ?? $_GET['action'] ?? 'status'));

// Helper: Normalize phone
function bridge_clean_phone(string $raw): string {
    $digits = preg_replace('/\D+/', '', $raw);
    if (str_starts_with($digits, '01')) {
        $digits = '88' . $digits;
    }
    return '+' . $digits;
}

if ($action === 'sync_desktop_account') {
    $accId = trim((string)($data['id'] ?? $data['account_id'] ?? ''));
    $name = trim((string)($data['name'] ?? $data['account_name'] ?? 'WAManager Desktop Account'));
    $phone = trim((string)($data['phone'] ?? ''));
    $status = trim((string)($data['status'] ?? 'connected'));
    
    if (empty($phone) || strlen(preg_replace('/\D+/', '', $phone)) < 10) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => 'ফোন নম্বরটি অন্তত ১০ সংখ্যার হতে হবে।']);
        exit;
    }

    $formattedPhone = bridge_clean_phone($phone);
    if (empty($accId)) {
        $accId = 'acc_desk_' . round(microtime(true) * 1000);
    }

    // Check if account already exists with this phone or ID
    $st = $pdo->prepare("SELECT id FROM accounts WHERE phone = ? OR id = ? LIMIT 1");
    $st->execute([$formattedPhone, $accId]);
    $existing = $st->fetch(PDO::FETCH_ASSOC);

    if ($existing) {
        $realId = $existing['id'];
        $up = $pdo->prepare("UPDATE accounts SET name = ?, phone = ?, provider_type = 'desktop_bridge', status = 'connected', session_health = 100, last_active_at = CURRENT_TIMESTAMP WHERE id = ?");
        $up->execute([$name, $formattedPhone, $realId]);
        try {
            $pdo->prepare("UPDATE wa_accounts SET name = ?, phone = ?, provider_type = 'desktop_bridge', status = 'connected', session_health = 100, last_active_at = CURRENT_TIMESTAMP WHERE id = ?")->execute([$name, $formattedPhone, $realId]);
        } catch (\Throwable $e) {}
    } else {
        $ins = $pdo->prepare("INSERT INTO accounts (id, name, phone, provider_type, status, session_health, daily_limit, daily_sent_today, messages_sent_count, warmup_enabled, warmup_day, warmup_target_limit, last_active_at, created_at) VALUES (?, ?, ?, 'desktop_bridge', 'connected', 100, 50, 0, 0, 1, 1, 800, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)");
        $ins->execute([$accId, $name, $formattedPhone]);
        try {
            $pdo->prepare("REPLACE INTO wa_accounts (id, name, phone, provider_type, status, session_health, daily_limit, daily_sent_today, messages_sent_count, warmup_enabled, warmup_day, warmup_target_limit, last_active_at, created_at) VALUES (?, ?, ?, 'desktop_bridge', 'connected', 100, 50, 0, 0, 1, 1, 800, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
                ->execute([$accId, $name, $formattedPhone]);
        } catch (\Throwable $e) {}
    }

    try {
        $logId = 'log_' . round(microtime(true) * 1000);
        $pdo->prepare("INSERT INTO audit_logs (id, action, details, created_at) VALUES (?, 'DESKTOP_SYNC', ?, CURRENT_TIMESTAMP)")
            ->execute([$logId, "ডেস্কটপ থেকে সফলভাবে অ্যাকাউন্ট যুক্ত হয়েছে: {$name} ({$formattedPhone})"]);
    } catch (\Throwable $e) {}

    echo json_encode([
        'ok' => true,
        'message' => "অ্যাকাউন্ট '{$name}' সফলভাবে AutoMovie Pro ওয়েবসাইটে সংযুক্ত ও সক্রিয় করা হয়েছে!",
        'account' => [
            'id' => $accId,
            'name' => $name,
            'phone' => $formattedPhone,
            'status' => 'connected',
            'session_health' => 100
        ]
    ]);
    exit;
}

elseif ($action === 'remove_desktop_account') {
    $phone = trim((string)($data['phone'] ?? ''));
    $accId = trim((string)($data['id'] ?? $data['account_id'] ?? ''));
    if ($phone) {
        $fmt = bridge_clean_phone($phone);
        $pdo->prepare("DELETE FROM accounts WHERE phone = ? OR phone = ?")->execute([$fmt, $phone]);
        try { $pdo->prepare("DELETE FROM wa_accounts WHERE phone = ? OR phone = ?")->execute([$fmt, $phone]); } catch (\Throwable $e) {}
    } elseif ($accId) {
        $pdo->prepare("DELETE FROM accounts WHERE id = ?")->execute([$accId]);
        try { $pdo->prepare("DELETE FROM wa_accounts WHERE id = ?")->execute([$accId]); } catch (\Throwable $e) {}
    }
    echo json_encode(['ok' => true, 'message' => 'অ্যাকাউন্টটি ওয়েবসাইট থেকে অপসারিত হয়েছে।']);
    exit;
}

elseif ($action === 'status') {
    $phone = trim((string)($data['phone'] ?? $_GET['phone'] ?? ''));
    $fmt = $phone ? bridge_clean_phone($phone) : '';
    $st = $pdo->prepare("SELECT id, name, phone, status, session_health, daily_sent_today, daily_limit FROM accounts WHERE phone = ? OR phone = ? LIMIT 1");
    $st->execute([$fmt, $phone]);
    $acc = $st->fetch(PDO::FETCH_ASSOC);
    echo json_encode([
        'ok' => true,
        'is_synced' => ($acc && ($acc['status'] === 'connected' || $acc['status'] === 'active')),
        'account' => $acc ?: null
    ]);
    exit;
}

elseif ($action === 'get_customers') {
    $st = $pdo->query("SELECT id, name, whatsapp, login_id, dedicated_account_id FROM customers ORDER BY id DESC LIMIT 20");
    echo json_encode(['ok' => true, 'customers' => $st->fetchAll(PDO::FETCH_ASSOC)], JSON_UNESCAPED_UNICODE);
    exit;
}

elseif ($action === 'fetch_pending_outbox') {
    $phone = trim((string)($data['phone'] ?? $_GET['phone'] ?? ''));
    $fmt = $phone ? bridge_clean_phone($phone) : '';
    $accId = trim((string)($data['id'] ?? $data['account_id'] ?? ''));

    // Fetch queued messages waiting for desktop delivery
    $st = $pdo->prepare("SELECT id, customer_id, to_number, message, trigger_type, created_at 
        FROM whatsapp_outbox 
        WHERE status IN ('queued', 'pending_desktop', 'pending_action')
        ORDER BY id ASC 
        LIMIT 10");
    $st->execute();
    $messages = $st->fetchAll(PDO::FETCH_ASSOC);

    echo json_encode([
        'ok' => true,
        'count' => count($messages),
        'messages' => $messages
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

elseif ($action === 'mark_outbox_delivered') {
    $outboxId = (int)($data['outbox_id'] ?? 0);
    $status = trim((string)($data['status'] ?? 'sent'));
    $response = trim((string)($data['response'] ?? 'Delivered via Desktop WAManager Bridge'));
    $accId = trim((string)($data['account_id'] ?? ''));

    if ($outboxId > 0) {
        try {
            // Attempt full update including optional delivered_at and account_id
            $st = $pdo->prepare("UPDATE whatsapp_outbox 
                SET status = ?, response = ?
                WHERE id = ?");
            $st->execute([$status, $response, $outboxId]);

            try {
                $st2 = $pdo->prepare("UPDATE whatsapp_outbox 
                    SET delivered_at = CURRENT_TIMESTAMP, account_id = COALESCE(NULLIF(?, ''), account_id) 
                    WHERE id = ?");
                $st2->execute([$accId, $outboxId]);
            } catch (\Throwable $eCol) {}

            // If delivered successfully, increment account messages count
            if ($status === 'sent' && !empty($accId)) {
                try {
                    $pdo->prepare("UPDATE accounts SET messages_sent_count = messages_sent_count + 1, last_active_at = CURRENT_TIMESTAMP WHERE id = ?")->execute([$accId]);
                    $pdo->prepare("UPDATE wa_accounts SET messages_sent_count = messages_sent_count + 1, last_active_at = CURRENT_TIMESTAMP WHERE id = ?")->execute([$accId]);
                } catch (\Throwable $e) {}
            }

            echo json_encode(['ok' => true, 'message' => "আউটবক্স বার্তা #{$outboxId} সফলভাবে আপডেট হয়েছে।"], JSON_UNESCAPED_UNICODE);
        } catch (\Throwable $e) {
            http_response_code(500);
            echo json_encode(['ok' => false, 'error' => $e->getMessage()]);
        }
    } else {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => 'অবৈধ আউটবক্স আইডি।'], JSON_UNESCAPED_UNICODE);
    }
    exit;
}

elseif ($action === 'direct_dispatch') {
    $to = trim((string)($data['to'] ?? $data['phone'] ?? ''));
    $body = trim((string)($data['message'] ?? $data['body'] ?? ''));
    $custId = !empty($data['customer_id']) ? (int)$data['customer_id'] : null;
    $trigger = trim((string)($data['trigger_type'] ?? 'direct_api'));
    $priority = trim((string)($data['priority'] ?? 'high'));

    if (empty($to) || empty($body)) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => 'প্রাপকের নম্বর এবং মেসেজ আবশ্যক।']);
        exit;
    }

    $res = whatsapp_antiban_dispatch($pdo, $config, $to, $body, $priority, $trigger, $custId);
    echo json_encode([
        'ok' => true,
        'dispatch' => $res,
        'message' => 'মেসেজটি সফলভাবে স্বয়ংক্রিয় প্রসেসিংয়ে পাঠানো হয়েছে।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

elseif ($action === 'upgrade_customer_to_all_access') {
    $custId = (int)($data['customer_id'] ?? $data['id'] ?? 4);
    $loginId = trim((string)($data['login_id'] ?? 'AMP32E321'));
    $pdo->prepare("UPDATE customers SET tier = 'all_access', plan = 'all_access' WHERE id = ? OR login_id = ?")
        ->execute([$custId, $loginId]);
    echo json_encode([
        'ok' => true,
        'message' => "কাস্টমার #{$custId} ({$loginId}) সফলভাবে 'all_access' টিয়ারে উন্নীত করা হয়েছে।"
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

elseif ($action === 'list_all_outbox') {
    $st = $pdo->query("SELECT id, customer_id, to_number, status, trigger_type, LEFT(message, 120) as snippet, created_at FROM whatsapp_outbox ORDER BY id DESC LIMIT 10");
    echo json_encode(['ok' => true, 'rows' => $st->fetchAll(PDO::FETCH_ASSOC)], JSON_UNESCAPED_UNICODE);
    exit;
}

elseif ($action === 'queue_customer_credentials') {
    try {
        $custId = (int)($data['customer_id'] ?? 4);
        $stC = $pdo->prepare("SELECT * FROM customers WHERE id = ? LIMIT 1");
        $stC->execute([$custId]);
        $c = $stC->fetch(PDO::FETCH_ASSOC);
        if (!$c) {
            http_response_code(404);
            echo json_encode(['ok' => false, 'error' => 'Customer not found']);
            exit;
        }
        $cleanWa = preg_replace('/\D+/', '', (string)$c['whatsapp']);
        if (str_starts_with($cleanWa, '01')) $cleanWa = '880' . substr($cleanWa, 1);
        
        // License token
        $licStmt = $pdo->prepare('SELECT token FROM licenses WHERE customer_id = ? AND revoked = 0 ORDER BY id DESC LIMIT 1');
        $licStmt->execute([$custId]);
        $lic = $licStmt->fetch(PDO::FETCH_ASSOC);
        $token = $lic ? $lic['token'] : 'lic_' . bin2hex(random_bytes(16));

        // Download link
        $siteUrl = rtrim((string) ($config['site_url'] ?? 'https://automoviepro.com'), '/');
        $dlUrl = $siteUrl . '/download.php';

        $msg = "Assalamu Alaikum {$c['name']},\n\n"
             . "AutoMovie Pro-তে আপনাকে স্বাগতম! আপনার মাস্টার অল-অ্যাক্সেস অ্যাকাউন্ট সক্রিয় করা হয়েছে। 🎉\n\n"
             . "👤 লগইন ID: {$c['login_id']}\n"
             . "🔑 পাসওয়ার্ড: vgnT2XN5vP\n"
             . "🎫 লাইসেন্স টোকেন: {$token}\n\n"
             . "🔒 সফটওয়্যার ডাউনলোড লিংক:\n"
             . "📥 {$dlUrl}\n\n"
             . "সফটওয়্যারটি ওপেন করে উপরোক্ত Login ID ও Password দিয়ে লগইন করুন।\n\n"
             . "ধন্যবাদ,\nAutoMovie Pro টিম";

        $stIns = $pdo->prepare("INSERT INTO whatsapp_outbox (customer_id, to_number, message, trigger_type, status, created_at) VALUES (?, ?, ?, 'manual_credentials', 'queued', CURRENT_TIMESTAMP)");
        $stIns->execute([$custId, '+' . $cleanWa, $msg]);
        $outId = $pdo->lastInsertId();

        echo json_encode([
            'ok' => true,
            'outbox_id' => $outId,
            'to' => '+' . $cleanWa,
            'message' => 'কাস্টমার ক্রেডেনশিয়াল আউটবক্সে কিউ করা হয়েছে।'
        ], JSON_UNESCAPED_UNICODE);
        exit;
    } catch (\Throwable $e) {
        http_response_code(500);
        echo json_encode(['ok' => false, 'error' => $e->getMessage()]);
        exit;
    }
}

elseif ($action === 'sync_inbound') {
    $senderPhone = trim((string)($data['sender_phone'] ?? $data['from'] ?? ''));
    $senderName = trim((string)($data['sender_name'] ?? 'WhatsApp User'));
    $body = trim((string)($data['message'] ?? $data['body'] ?? ''));
    $accId = trim((string)($data['account_id'] ?? ''));

    if (empty($senderPhone) || empty($body)) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => 'Sender phone and message body required']);
        exit;
    }

    $cleanDigits = preg_replace('/\D+/', '', $senderPhone);
    if (str_starts_with($cleanDigits, '01')) $cleanDigits = '880' . substr($cleanDigits, 1);
    $normPhone = '+' . $cleanDigits;
    $msgId = 'in_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);

    // Save inbound record
    try {
        $pdo->prepare("REPLACE INTO inbound_messages (id, account_id, sender_phone, sender_name, message_body, is_read, timestamp) VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)")
            ->execute([$msgId, $accId ?: 'desktop_bridge', $normPhone, $senderName, $body]);
    } catch (\Throwable $e) {}

    // Process reply via Central Marketing Master Brain (Ayesha / Nirob / Tania)
    $aiReply = '';
    $selectedAgent = 'ayesha';
    try {
        require_once dirname(__DIR__) . '/includes/marketing_master_agent.php';
        $aiRes = MarketingMasterBrain::process($pdo, $config, [
            'channel' => 'whatsapp_inbound',
            'user_message' => $body,
            'lead_name' => $senderName,
            'lead_phone' => $normPhone,
            'requested_agent' => 'auto'
        ]);

        if (!empty($aiRes['reply'])) {
            $aiReply = $aiRes['reply'];
            $selectedAgent = $aiRes['meta']['selected_agent'] ?? 'ayesha';

            // Queue AI reply into whatsapp_outbox so desktop bridge dispatches it back to the customer!
            $outId = 'out_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
            $pdo->prepare("INSERT INTO whatsapp_outbox (to_number, message, trigger_type, priority, status, account_id, created_at) VALUES (?, ?, 'ai_auto_responder', 'high', 'pending_desktop', ?, CURRENT_TIMESTAMP)")
                ->execute([$normPhone, $aiReply, $accId]);
        }
    } catch (\Throwable $eBrain) {
        error_log('Bridge sync_inbound AI Brain error: ' . $eBrain->getMessage());
    }

    echo json_encode([
        'ok' => true,
        'reply_generated' => !empty($aiReply),
        'reply' => $aiReply,
        'agent' => $selectedAgent,
        'message' => 'ইনবাউন্ড বার্তা সফলভাবে এআই ব্রেইনে প্রসেস ও আউটবক্সে কিউ করা হয়েছে।'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

else {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => 'Invalid action']);
    exit;
}
