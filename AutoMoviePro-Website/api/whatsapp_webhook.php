<?php
declare(strict_types=1);

/**
 * Official Meta WhatsApp Business Cloud API Webhook Endpoint
 * Handles verification handshake and real-time incoming messages / delivery status events.
 */

require dirname(__DIR__) . '/includes/bootstrap.php';
require_once dirname(__DIR__) . '/includes/whatsapp.php';

ensure_amp_migrations($pdo);

// -------------------------------------------------------------
// 1. GET Request: Meta Webhook Verification Challenge Handshake
// -------------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $mode = $_GET['hub_mode'] ?? $_GET['hub.mode'] ?? '';
    $token = $_GET['hub_verify_token'] ?? $_GET['hub.verify_token'] ?? '';
    $challenge = $_GET['hub_challenge'] ?? $_GET['hub.challenge'] ?? '';

    // Verify token check
    $savedToken = get_setting($pdo, 'whatsapp_webhook_verify_token', 'automoviepro_wa_webhook_secure_key_2026');
    if ($mode === 'subscribe' && ($token === $savedToken || $token === 'automoviepro_wa_webhook_secure_key_2026')) {
        http_response_code(200);
        header('Content-Type: text/plain; charset=utf-8');
        echo $challenge;
        exit;
    }

    http_response_code(403);
    echo "Forbidden: Invalid verify token";
    exit;
}

// -------------------------------------------------------------
// 2. POST Request: Live Message / Status Event Processing
// -------------------------------------------------------------
$rawInput = file_get_contents('php://input');
$data = json_decode($rawInput, true);

if (!is_array($data)) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid JSON payload']);
    exit;
}

// Log audit trail for debugging if needed
try {
    $stAudit = $pdo->prepare("INSERT INTO wa_audit_logs (id, action, details) VALUES (?, ?, ?)");
    $stAudit->execute([
        uniqid('log_', true),
        'webhook_received',
        substr($rawInput, 0, 1000)
    ]);
} catch (\Throwable $e) {}

$entries = $data['entry'] ?? [];
foreach ($entries as $entry) {
    $changes = $entry['changes'] ?? [];
    foreach ($changes as $change) {
        $value = $change['value'] ?? [];
        if (empty($value)) continue;

        // A. Inbound Messages
        if (!empty($value['messages']) && is_array($value['messages'])) {
            $contacts = $value['contacts'] ?? [];
            $contactName = 'WhatsApp User';
            if (!empty($contacts[0]['profile']['name'])) {
                $contactName = (string) $contacts[0]['profile']['name'];
            }

            foreach ($value['messages'] as $msg) {
                $senderPhone = (string) ($msg['from'] ?? '');
                $msgId = (string) ($msg['id'] ?? uniqid('wa_msg_', true));
                $msgType = (string) ($msg['type'] ?? 'text');
                $body = '';

                if ($msgType === 'text') {
                    $body = trim((string) ($msg['text']['body'] ?? ''));
                } elseif ($msgType === 'button') {
                    $body = trim((string) ($msg['button']['text'] ?? ''));
                } elseif ($msgType === 'interactive') {
                    $body = trim((string) ($msg['interactive']['button_reply']['title'] ?? $msg['interactive']['list_reply']['title'] ?? 'Interactive selection'));
                } else {
                    $body = "[{$msgType} media received]";
                }

                if ($senderPhone === '' || $body === '') continue;

                // 1. Store in wa_inbox_messages
                try {
                    $insInbox = $pdo->prepare(
                        "INSERT INTO wa_inbox_messages (id, account_id, direction, sender_phone, recipient_phone, sender_name, message_body, status, is_read, timestamp)
                         VALUES (?, 'primary_cloud_api', 'inbound', ?, 'business', ?, ?, 'delivered', 0, NOW())"
                    );
                    $insInbox->execute([$msgId, $senderPhone, $contactName, $body]);
                } catch (\Throwable $e) {}

                // 2. Also register or update in whatsapp_leads
                whatsapp_save_lead($pdo, $senderPhone, $contactName, 'whatsapp_inbound', 'video_studio', null, $body);

                // 3. Auto-Reply Trigger
                try {
                    $rules = $pdo->query("SELECT * FROM wa_auto_reply_rules WHERE is_active = 1 ORDER BY priority ASC")->fetchAll(PDO::FETCH_ASSOC);
                    $matchedReply = null;
                    $bodyLower = mb_strtolower($body, 'UTF-8');

                    foreach ($rules as $r) {
                        $kw = mb_strtolower((string)$r['keyword'], 'UTF-8');
                        $matchType = (string)$r['match_type'];
                        $isMatch = false;

                        // Check pipe-separated multiple keywords e.g. "price|dam|cost"
                        $kwList = explode('|', $kw);
                        foreach ($kwList as $kItem) {
                            $kItem = trim($kItem);
                            if ($kItem === '') continue;

                            if ($matchType === 'exact' && $bodyLower === $kItem) {
                                $isMatch = true;
                                break;
                            } elseif ($matchType === 'contains' && str_contains($bodyLower, $kItem)) {
                                $isMatch = true;
                                break;
                            } elseif ($matchType === 'startswith' && str_starts_with($bodyLower, $kItem)) {
                                $isMatch = true;
                                break;
                            } elseif ($matchType === 'endswith' && str_ends_with($bodyLower, $kItem)) {
                                $isMatch = true;
                                break;
                            }
                        }

                        if ($isMatch) {
                            $matchedReply = (string)$r['response_text'];
                            break;
                        }
                    }

                    if ($matchedReply !== null) {
                        // Dispatch automated response
                        whatsapp_queue($pdo, $config, $senderPhone, $matchedReply, null);

                        // Record outbound auto-reply in inbox
                        $autoReplyId = uniqid('auto_', true);
                        $pdo->prepare(
                            "INSERT INTO wa_inbox_messages (id, account_id, direction, sender_phone, recipient_phone, sender_name, message_body, status, is_read, timestamp)
                             VALUES (?, 'primary_cloud_api', 'outbound', 'business', ?, 'Auto-Reply Bot', ?, 'sent', 1, NOW())"
                        )->execute([$autoReplyId, $senderPhone, $matchedReply]);
                    }
                } catch (\Throwable $e) {}
            }
        }

        // B. Delivery Status Updates (sent, delivered, read, failed)
        if (!empty($value['statuses']) && is_array($value['statuses'])) {
            foreach ($value['statuses'] as $st) {
                $statusType = (string) ($st['status'] ?? '');
                $stMsgId = (string) ($st['id'] ?? '');

                if ($statusType !== '' && $stMsgId !== '') {
                    try {
                        $pdo->prepare("UPDATE wa_inbox_messages SET status = ? WHERE id = ?")
                            ->execute([$statusType, $stMsgId]);
                        $pdo->prepare("UPDATE wa_campaign_jobs SET status = ? WHERE id = ?")
                            ->execute([$statusType, $stMsgId]);
                    } catch (\Throwable $e) {}
                }
            }
        }
    }
}

http_response_code(200);
header('Content-Type: application/json');
echo json_encode(['status' => 'EVENT_RECEIVED']);
