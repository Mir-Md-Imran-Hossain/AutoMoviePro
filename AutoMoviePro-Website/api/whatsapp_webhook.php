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

                // 1. Store in wa_inbox_messages and inbound_messages (WAManager Pro)
                try {
                    $insInbox = $pdo->prepare(
                        "INSERT INTO wa_inbox_messages (id, account_id, direction, sender_phone, recipient_phone, sender_name, message_body, status, is_read, timestamp)
                         VALUES (?, 'primary_cloud_api', 'inbound', ?, 'business', ?, ?, 'delivered', 0, CURRENT_TIMESTAMP)"
                    );
                    $insInbox->execute([$msgId, $senderPhone, $contactName, $body]);

                    $cleanDigits = preg_replace('/\D+/', '', $senderPhone);
                    if (str_starts_with($cleanDigits, '01')) $cleanDigits = '880' . substr($cleanDigits, 1);
                    $normPhone = '+' . $cleanDigits;

                    $pdo->prepare("REPLACE INTO inbound_messages (id, account_id, sender_phone, sender_name, message_body, is_read, timestamp) VALUES (?, 'primary_cloud_api', ?, ?, ?, 0, CURRENT_TIMESTAMP)")
                        ->execute([$msgId, $normPhone, $contactName, $body]);

                    $cId = 'cnt_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                    $pdo->prepare("REPLACE INTO contacts (id, name, phone, country_code, source, consent_status, created_at, updated_at) VALUES (?, ?, ?, '880', 'whatsapp_inbound', 'opted_in', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
                        ->execute([$cId, $contactName, $normPhone]);
                } catch (\Throwable $e) {}

                // 2. Also register or update in whatsapp_leads
                whatsapp_save_lead($pdo, $senderPhone, $contactName, 'whatsapp_inbound', 'video_studio', null, $body);

                // 3. Intelligent Unified Auto-Reply & Central AI Agent Brain
                try {
                    // Step A: Check keyword rules from both automation_rules and wa_auto_reply_rules
                    $rules = [];
                    try {
                        $rules = $pdo->query("SELECT id, keyword, match_type, response_text, priority FROM automation_rules WHERE is_active = 1
                                              UNION ALL
                                              SELECT id, keyword, match_type, response_text, priority FROM wa_auto_reply_rules WHERE is_active = 1
                                              ORDER BY priority ASC")->fetchAll(PDO::FETCH_ASSOC);
                    } catch (\Throwable $eRules) {
                        try {
                            $rules = $pdo->query("SELECT id, keyword, match_type, response_text, priority FROM automation_rules WHERE is_active = 1 ORDER BY priority ASC")->fetchAll(PDO::FETCH_ASSOC);
                        } catch (\Throwable $eR2) {
                            $rules = $pdo->query("SELECT id, keyword, match_type, response_text, priority FROM wa_auto_reply_rules WHERE is_active = 1 ORDER BY priority ASC")->fetchAll(PDO::FETCH_ASSOC);
                        }
                    }

                    $matchedReply = null;
                    $matchedKeyword = null;
                    $bodyLower = mb_strtolower(trim($body), 'UTF-8');

                    foreach ($rules as $r) {
                        $kw = mb_strtolower(trim((string)$r['keyword']), 'UTF-8');
                        $matchType = (string)($r['match_type'] ?? 'contains');
                        $kwList = array_filter(array_map('trim', preg_split('/[|,]/u', $kw) ?: []));
                        if (empty($kwList)) $kwList = [$kw];
                        $isMatch = false;

                        foreach ($kwList as $kItem) {
                            if ($kItem === '') continue;
                            if ($matchType === 'exact' && $bodyLower === $kItem) {
                                $isMatch = true; break;
                            } elseif ($matchType === 'contains' && str_contains($bodyLower, $kItem)) {
                                $isMatch = true; break;
                            } elseif ($matchType === 'startswith' && str_starts_with($bodyLower, $kItem)) {
                                $isMatch = true; break;
                            } elseif ($matchType === 'endswith' && str_ends_with($bodyLower, $kItem)) {
                                $isMatch = true; break;
                            }
                        }

                        if ($isMatch) {
                            $matchedReply = (string)$r['response_text'];
                            $matchedKeyword = $r['keyword'];
                            break;
                        }
                    }

                    if ($matchedReply !== null) {
                        // Dispatch automated rule response via unified anti-ban engine
                        whatsapp_antiban_dispatch($pdo, $config, $senderPhone, $matchedReply, 'high', 'auto_responder', null, null, $contactName);

                        $replyId = 'in_' . (round(microtime(true) * 1000) + 100) . '_' . mt_rand(100, 999);
                        $pdo->prepare("INSERT INTO inbound_messages (id, account_id, sender_phone, sender_name, message_body, is_read, timestamp) VALUES (?, 'primary_cloud_api', ?, 'অটো-রেসপন্ডার বট', ?, 1, CURRENT_TIMESTAMP)")
                            ->execute([$replyId, '+' . $cleanDigits, $matchedReply]);
                        
                        $autoReplyId = uniqid('auto_', true);
                        $pdo->prepare("INSERT INTO wa_inbox_messages (id, account_id, direction, sender_phone, recipient_phone, sender_name, message_body, status, is_read, timestamp) VALUES (?, 'primary_cloud_api', 'outbound', 'business', ?, 'Auto-Reply Bot', ?, 'sent', 1, CURRENT_TIMESTAMP)")
                            ->execute([$autoReplyId, '+' . $cleanDigits, $matchedReply]);
                    } else {
                        // Step B: Intelligent Central AI Sales Consultant Fallback (Ayesha / Nirob / Tania)
                        require_once dirname(__DIR__) . '/includes/marketing_master_agent.php';
                        $aiRes = MarketingMasterBrain::process($pdo, $config, [
                            'channel' => 'whatsapp_inbound',
                            'user_message' => $body,
                            'lead_name' => $contactName,
                            'lead_phone' => '+' . $cleanDigits,
                            'requested_agent' => 'auto'
                        ]);

                        if (!empty($aiRes['reply'])) {
                            $aiReply = $aiRes['reply'];
                            $agentId = $aiRes['meta']['selected_agent'] ?? 'ayesha';
                            $agentLabel = ($agentId === 'nirob') ? 'নীরব (Tech Specialist)' : (($agentId === 'tania') ? 'তানিয়া (Sales Closer)' : 'আয়েশা (Customer Care)');

                            whatsapp_antiban_dispatch($pdo, $config, $cleanDigits, $aiReply, 'high', 'ai_auto_responder', null, null, $contactName);

                            $aiRepId = 'in_' . (round(microtime(true) * 1000) + 200) . '_' . mt_rand(100, 999);
                            $pdo->prepare("INSERT INTO inbound_messages (id, account_id, sender_phone, sender_name, message_body, is_read, timestamp) VALUES (?, 'ai_director', ?, ?, ?, 1, CURRENT_TIMESTAMP)")
                                ->execute([$aiRepId, '+' . $cleanDigits, $agentLabel, $aiReply]);

                            $pdo->prepare("INSERT INTO wa_inbox_messages (id, account_id, direction, sender_phone, recipient_phone, sender_name, message_body, status, is_read, timestamp) VALUES (?, 'ai_director', 'outbound', 'business', ?, ?, ?, 'sent', 1, CURRENT_TIMESTAMP)")
                                ->execute([$aiRepId, '+' . $cleanDigits, $agentLabel, $aiReply]);
                        }
                    }
                } catch (\Throwable $eReply) {
                    error_log('WhatsApp webhook auto-reply error: ' . $eReply->getMessage());
                }
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
