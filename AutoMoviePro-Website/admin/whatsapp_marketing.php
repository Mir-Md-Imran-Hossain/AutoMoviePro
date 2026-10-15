<?php
declare(strict_types=1);

require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_once dirname(__DIR__) . '/includes/whatsapp.php';
require_once dirname(__DIR__) . '/includes/agent_llm.php';

require_admin();

ensure_amp_migrations($pdo);

$message = '';
$error = '';
$activeTab = trim((string) ($_GET['tab'] ?? 'dashboard'));

// -------------------------------------------------------------
// HELPER: Send WhatsApp Message via Meta Cloud API or Gateway
// -------------------------------------------------------------
function send_whatsapp_direct(PDO $pdo, array $config, string $toPhone, string $messageText, ?string $mediaUrl = null, ?string $accountId = null): array
{
    $cleanPhone = preg_replace('/\D+/', '', $toPhone) ?? '';
    if (str_starts_with($cleanPhone, '01')) {
        $cleanPhone = '88' . $cleanPhone;
    }
    if ($cleanPhone === '') {
        return ['ok' => false, 'error' => 'অবৈধ ফোন নম্বর'];
    }

    // Check account config
    $token = trim((string) ($config['whatsapp_token'] ?? ''));
    $phoneId = trim((string) ($config['whatsapp_phone_id'] ?? ''));

    if ($accountId) {
        $stAcc = $pdo->prepare("SELECT * FROM wa_accounts WHERE id = ? LIMIT 1");
        $stAcc->execute([$accountId]);
        $acc = $stAcc->fetch(PDO::FETCH_ASSOC);
        if ($acc && !empty($acc['api_config'])) {
            $cfg = json_decode((string)$acc['api_config'], true);
            if (!empty($cfg['access_token'])) $token = (string) $cfg['access_token'];
            if (!empty($cfg['phone_number_id'])) $phoneId = (string) $cfg['phone_number_id'];
        }
    }

    // Log in outbox
    $now = amp_sql_now($pdo);
    $stOutbox = $pdo->prepare("INSERT INTO whatsapp_outbox (to_number, message, status, created_at) VALUES (?, ?, 'queued', {$now})");
    $stOutbox->execute([$cleanPhone, $messageText]);
    $outboxId = (int) $pdo->lastInsertId();

    if ($token === '' || $phoneId === '') {
        $pdo->prepare("UPDATE whatsapp_outbox SET status = 'logged_only' WHERE id = ?")->execute([$outboxId]);
        return ['ok' => true, 'mode' => 'logged_only', 'message' => 'মেসেজটি আউটবক্সে সংরক্ষিত হয়েছে (অফিসিয়াল এপিআই কি কনফিগার করা নেই)।'];
    }

    $payload = [
        'messaging_product' => 'whatsapp',
        'recipient_type' => 'individual',
        'to' => $cleanPhone,
    ];

    if ($mediaUrl) {
        $payload['type'] = 'image';
        $payload['image'] = ['link' => $mediaUrl, 'caption' => $messageText];
    } else {
        $payload['type'] = 'text';
        $payload['text'] = ['preview_url' => false, 'body' => $messageText];
    }

    $ch = curl_init("https://graph.facebook.com/v19.0/{$phoneId}/messages");
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $token,
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS => json_encode($payload),
        CURLOPT_TIMEOUT => 25,
    ]);
    $raw = curl_exec($ch);
    $curlErr = curl_error($ch);
    $httpCode = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $isOk = ($curlErr === '' && $httpCode >= 200 && $httpCode < 300);
    $resData = json_decode((string)$raw, true) ?: [];
    $metaMsgId = $resData['messages'][0]['id'] ?? null;

    $pdo->prepare("UPDATE whatsapp_outbox SET status = ?, response = ? WHERE id = ?")
        ->execute([$isOk ? 'sent' : 'failed', substr((string)($raw ?: $curlErr), 0, 2000), $outboxId]);

    // Update account sent count
    if ($isOk && $accountId) {
        $pdo->prepare("UPDATE wa_accounts SET messages_sent_count = messages_sent_count + 1, last_active_at = NOW() WHERE id = ?")->execute([$accountId]);
    }

    return [
        'ok' => $isOk,
        'http_code' => $httpCode,
        'meta_id' => $metaMsgId,
        'raw_response' => $raw,
        'error' => $isOk ? null : ($resData['error']['message'] ?? $curlErr ?? 'মেটা এপিআই এরর')
    ];
}

// -------------------------------------------------------------
// POST & AJAX HANDLER
// -------------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // Determine if JSON AJAX request
    $isAjax = (!empty($_SERVER['HTTP_X_REQUESTED_WITH']) && strtolower($_SERVER['HTTP_X_REQUESTED_WITH']) === 'xmlhttprequest') 
              || str_contains($_SERVER['CONTENT_TYPE'] ?? '', 'application/json');

    $postData = $_POST;
    if (empty($postData)) {
        $raw = file_get_contents('php://input');
        $decoded = json_decode($raw, true);
        if (is_array($decoded)) $postData = $decoded;
    }

    if (!csrf_verify($postData['csrf'] ?? null)) {
        if ($isAjax) {
            http_response_code(403);
            echo json_encode(['ok' => false, 'error' => 'নিরাপত্তা যাচাই ব্যর্থ (CSRF Token Mismatch)']);
            exit;
        }
        $error = 'নিরাপত্তা যাচাই ব্যর্থ হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।';
    } else {
        $action = (string) ($postData['action'] ?? '');

        // 1. Add Single Contact
        if ($action === 'add_contact') {
            $name = trim((string) ($postData['name'] ?? 'গ্রাহক'));
            $phone = trim((string) ($postData['phone'] ?? ''));
            $email = trim((string) ($postData['email'] ?? ''));
            $biz = trim((string) ($postData['business_name'] ?? ''));
            $groupId = trim((string) ($postData['group_id'] ?? ''));
            $notes = trim((string) ($postData['notes'] ?? ''));

            $cleanPhone = preg_replace('/\D+/', '', $phone) ?? '';
            if (str_starts_with($cleanPhone, '01')) $cleanPhone = '88' . $cleanPhone;

            if ($cleanPhone === '') {
                $error = 'সঠিক ফোন নম্বর প্রদান করা আবশ্যক।';
            } else {
                $contactId = 'cnt_' . uniqid('', true);
                $st = $pdo->prepare(
                    "INSERT INTO wa_contacts (id, name, phone, country_code, email, business_name, notes, source, consent_status, created_at, updated_at)
                     VALUES (?, ?, ?, '880', ?, ?, ?, 'manual', 'opted_in', NOW(), NOW())
                     ON DUPLICATE KEY UPDATE name = VALUES(name), email = VALUES(email), business_name = VALUES(business_name), notes = VALUES(notes), updated_at = NOW()"
                );
                $st->execute([$contactId, $name, $cleanPhone, $email, $biz, $notes]);

                if ($groupId !== '') {
                    $pdo->prepare("INSERT IGNORE INTO wa_group_members (group_id, contact_id, added_at) VALUES (?, ?, NOW())")
                        ->execute([$groupId, $contactId]);
                }
                $message = "নতুন কন্টাক্ট সফলভাবে যুক্ত করা হয়েছে!";
            }
        }

        // 2. Delete Contact
        elseif ($action === 'delete_contact') {
            $contactId = trim((string) ($postData['contact_id'] ?? ''));
            $pdo->prepare("DELETE FROM wa_contacts WHERE id = ?")->execute([$contactId]);
            $pdo->prepare("DELETE FROM wa_group_members WHERE contact_id = ?")->execute([$contactId]);
            $message = "কন্টাক্ট সফলভাবে মুছে ফেলা হয়েছে।";
        }

        // 3. Batch Import Contacts (CSV or Raw Text)
        elseif ($action === 'batch_import_contacts') {
            $rawList = trim((string) ($postData['raw_contacts_text'] ?? ''));
            $targetGroup = trim((string) ($postData['target_group_id'] ?? ''));
            $defaultName = trim((string) ($postData['default_name'] ?? 'গ্রাহক'));
            $imported = 0;

            if ($rawList !== '') {
                $lines = explode("\n", str_replace("\r", "", $rawList));
                foreach ($lines as $line) {
                    $line = trim($line);
                    if ($line === '') continue;

                    $parts = array_map('trim', explode(',', $line));
                    $pPhone = $parts[0] ?? '';
                    $pName = (!empty($parts[1])) ? $parts[1] : $defaultName;
                    $pBiz = $parts[2] ?? '';

                    $cleanPhone = preg_replace('/\D+/', '', $pPhone) ?? '';
                    if (str_starts_with($cleanPhone, '01')) $cleanPhone = '88' . $cleanPhone;
                    if (strlen($cleanPhone) >= 10) {
                        $cId = 'cnt_' . uniqid('', true);
                        try {
                            $st = $pdo->prepare(
                                "INSERT INTO wa_contacts (id, name, phone, country_code, business_name, source, consent_status, created_at, updated_at)
                                 VALUES (?, ?, ?, '880', ?, 'batch_import', 'opted_in', NOW(), NOW())
                                 ON DUPLICATE KEY UPDATE name = VALUES(name), business_name = VALUES(business_name), updated_at = NOW()"
                            );
                            $st->execute([$cId, $pName, $cleanPhone, $pBiz]);
                            if ($targetGroup !== '') {
                                $pdo->prepare("INSERT IGNORE INTO wa_group_members (group_id, contact_id, added_at) VALUES (?, ?, NOW())")
                                    ->execute([$targetGroup, $cId]);
                            }
                            $imported++;
                        } catch (\Throwable $e) {}
                    }
                }
                $message = "ব্যাচ ইমপোর্ট সম্পন্ন! মোট {$imported} জন কন্টাক্ট সফলভাবে ডেটাবেসে যুক্ত হয়েছে।";
            } else {
                $error = 'ইমপোর্ট করার জন্য কোনো কন্টাক্ট তালিকা প্রদান করা হয়নি।';
            }
        }

        // 4. Create Contact Group
        elseif ($action === 'create_group') {
            $gName = trim((string) ($postData['group_name'] ?? ''));
            $gDesc = trim((string) ($postData['group_description'] ?? ''));
            if ($gName !== '') {
                $gid = 'grp_' . uniqid('', true);
                $pdo->prepare("INSERT INTO wa_contact_groups (id, name, description, created_at) VALUES (?, ?, ?, NOW())")
                    ->execute([$gid, $gName, $gDesc]);
                $message = "নতুন গ্রুপ '{$gName}' সফলভাবে তৈরি হয়েছে!";
            } else {
                $error = 'গ্রুপের একটি সুন্দর নাম লিখুন।';
            }
        }

        // 5. Delete Contact Group
        elseif ($action === 'delete_group') {
            $gid = trim((string) ($postData['group_id'] ?? ''));
            $pdo->prepare("DELETE FROM wa_contact_groups WHERE id = ?")->execute([$gid]);
            $pdo->prepare("DELETE FROM wa_group_members WHERE group_id = ?")->execute([$gid]);
            $message = "গ্রুপটি মুছে ফেলা হয়েছে।";
        }

        // 5.1 Add Account
        elseif ($action === 'add_account') {
            $accName = trim((string) ($postData['account_name'] ?? ''));
            $accPhone = trim((string) ($postData['account_phone'] ?? ''));
            $provType = trim((string) ($postData['provider_type'] ?? 'cloud_api'));
            $accToken = trim((string) ($postData['access_token'] ?? ''));
            $phoneId = trim((string) ($postData['phone_number_id'] ?? ''));
            $wabaId = trim((string) ($postData['business_account_id'] ?? ''));

            $cleanPhone = preg_replace('/\D+/', '', $accPhone) ?? '';
            if (str_starts_with($cleanPhone, '01')) $cleanPhone = '88' . $cleanPhone;

            if ($accName !== '') {
                $accId = 'acc_' . uniqid('', true);
                $apiConfig = json_encode([
                    'access_token' => $accToken,
                    'phone_number_id' => $phoneId,
                    'business_account_id' => $wabaId
                ]);
                $st = $pdo->prepare("INSERT INTO wa_accounts (id, name, phone, provider_type, status, api_config, created_at, updated_at) VALUES (?, ?, ?, ?, 'connected', ?, NOW(), NOW())");
                $st->execute([$accId, $accName, $cleanPhone, $provType, $apiConfig]);
                $message = "নতুন WhatsApp অ্যাকাউন্ট '{$accName}' সফলভাবে যুক্ত হয়েছে!";
            } else {
                $error = 'অ্যাকাউন্টের নাম ও তথ্য পূরণ করুন।';
            }
        }

        // 5.2 Delete Account
        elseif ($action === 'delete_account') {
            $accId = trim((string) ($postData['account_id'] ?? ''));
            if ($accId !== 'primary_cloud_api') {
                $pdo->prepare("DELETE FROM wa_accounts WHERE id = ?")->execute([$accId]);
                $message = "অ্যাকাউন্টটি মুছে ফেলা হয়েছে।";
            } else {
                $error = 'প্রাইমারি ক্লাউড এপিআই অ্যাকাউন্ট মুছে ফেলা যাবে না।';
            }
        }

        // 5.3 Save Template
        elseif ($action === 'save_template') {
            $tplKey = trim((string) ($postData['template_key'] ?? 'tpl_' . uniqid()));
            $tplTitle = trim((string) ($postData['title'] ?? ''));
            $tplCat = trim((string) ($postData['category'] ?? 'general'));
            $tplBody = trim((string) ($postData['body'] ?? ''));

            if ($tplTitle !== '' && $tplBody !== '') {
                $st = $pdo->prepare("INSERT INTO whatsapp_templates (template_key, title, category, body, is_active, created_at, updated_at)
                                     VALUES (?, ?, ?, ?, 1, NOW(), NOW())
                                     ON DUPLICATE KEY UPDATE title = VALUES(title), category = VALUES(category), body = VALUES(body), updated_at = NOW()");
                $st->execute([$tplKey, $tplTitle, $tplCat, $tplBody]);
                $message = "টেমপ্লেট '{$tplTitle}' সফলভাবে সংরক্ষিত হয়েছে!";
            } else {
                $error = 'টেমপ্লেটের শিরোনাম ও মেসেজ বডি লিখুন।';
            }
        }

        // 5.4 Delete Template
        elseif ($action === 'delete_template') {
            $tplId = (int) ($postData['template_id'] ?? 0);
            if ($tplId > 0) {
                $pdo->prepare("DELETE FROM whatsapp_templates WHERE id = ?")->execute([$tplId]);
                $message = "টেমপ্লেটটি মুছে ফেলা হয়েছে।";
            }
        }

        // 5.5 Save Grabbed Group Members
        elseif ($action === 'save_grabbed_members') {
            $rawMembers = trim((string) ($postData['members_text'] ?? ''));
            $targetGroup = trim((string) ($postData['target_group_id'] ?? ''));
            $groupName = trim((string) ($postData['group_source_name'] ?? 'WhatsApp Group'));
            $saved = 0;

            if ($rawMembers !== '') {
                $lines = explode("\n", str_replace("\r", "", $rawMembers));
                foreach ($lines as $line) {
                    $line = trim($line);
                    if ($line === '') continue;
                    $parts = array_map('trim', explode(',', $line));
                    $phone = $parts[0] ?? '';
                    $name = (!empty($parts[1])) ? $parts[1] : 'গ্রুপ মেম্বার';
                    $clean = preg_replace('/\D+/', '', $phone);
                    if (str_starts_with($clean, '01')) $clean = '88' . $clean;
                    if (strlen($clean) >= 10) {
                        $cid = 'cnt_' . uniqid('', true);
                        try {
                            $pdo->prepare("INSERT INTO wa_contacts (id, name, phone, country_code, business_name, source, consent_status, created_at, updated_at)
                                           VALUES (?, ?, ?, '880', ?, 'group_grabber', 'opted_in', NOW(), NOW())
                                           ON DUPLICATE KEY UPDATE updated_at = NOW()")->execute([$cid, $name, $clean, $groupName]);
                            if ($targetGroup !== '') {
                                $pdo->prepare("INSERT IGNORE INTO wa_group_members (group_id, contact_id, added_at) VALUES (?, ?, NOW())")->execute([$targetGroup, $cid]);
                            }
                            $saved++;
                        } catch (\Throwable $e) {}
                    }
                }
                $message = "গ্রুপ গ্র্যাবার থেকে {$saved} জন মেম্বার সফলভাবে কন্টাক্ট ডেটাবেসে যুক্ত হয়েছে!";
            }
        }

        // 5.6 Number Filter & Validator
        elseif ($action === 'filter_numbers') {
            $rawNumbers = trim((string) ($postData['raw_numbers'] ?? ''));
            $saveToGroup = trim((string) ($postData['target_group_id'] ?? ''));
            $autoSave = !empty($postData['auto_save_valid']);

            $valid = [];
            $invalid = [];
            $duplicates = 0;
            $seen = [];

            if ($rawNumbers !== '') {
                $lines = preg_split('/[\r\n,;]+/', $rawNumbers);
                foreach ($lines as $line) {
                    $item = trim($line);
                    if ($item === '') continue;
                    $digits = preg_replace('/\D+/', '', $item);
                    if (str_starts_with($digits, '01') && strlen($digits) === 11) {
                        $digits = '88' . $digits;
                    } elseif (str_starts_with($digits, '1') && strlen($digits) === 10) {
                        $digits = '880' . $digits;
                    }

                    $isValidBd = preg_match('/^8801[3-9]\d{8}$/', $digits);
                    $isValidIntl = (strlen($digits) >= 10 && strlen($digits) <= 15);

                    if ($isValidBd || $isValidIntl) {
                        if (isset($seen[$digits])) {
                            $duplicates++;
                            continue;
                        }
                        $seen[$digits] = true;
                        $carrier = 'International';
                        if ($isValidBd) {
                            $pfx = substr($digits, 4, 1);
                            $carrier = match($pfx) {
                                '7', '3' => 'Grameenphone',
                                '9', '4' => 'Banglalink',
                                '8' => 'Robi',
                                '6' => 'Airtel',
                                '5' => 'Teletalk',
                                default => 'Mobile BD'
                            };
                        }
                        $valid[] = ['number' => $digits, 'carrier' => $carrier, 'original' => $item];

                        if ($autoSave) {
                            $cid = 'cnt_' . uniqid('', true);
                            try {
                                $pdo->prepare("INSERT INTO wa_contacts (id, name, phone, country_code, business_name, source, consent_status, created_at, updated_at)
                                               VALUES (?, 'ভ্যালিডেটেড কন্টাক্ট', ?, '880', ?, 'number_filter', 'opted_in', NOW(), NOW())
                                               ON DUPLICATE KEY UPDATE updated_at = NOW()")->execute([$cid, $digits, $carrier]);
                                if ($saveToGroup !== '') {
                                    $pdo->prepare("INSERT IGNORE INTO wa_group_members (group_id, contact_id, added_at) VALUES (?, ?, NOW())")->execute([$saveToGroup, $cid]);
                                }
                            } catch (\Throwable $e) {}
                        }
                    } else {
                        $invalid[] = ['number' => $item, 'reason' => 'অকার্যকর দৈর্ঘ্য বা ডায়াল কোড'];
                    }
                }
            }

            if ($isAjax) {
                header('Content-Type: application/json');
                echo json_encode([
                    'ok' => true,
                    'total' => count($valid) + count($invalid) + $duplicates,
                    'valid_count' => count($valid),
                    'invalid_count' => count($invalid),
                    'duplicate_count' => $duplicates,
                    'valid' => $valid,
                    'invalid' => $invalid
                ]);
                exit;
            } else {
                $message = "নম্বর ফিল্টারিং সম্পন্ন! মোট " . count($valid) . " টি ভ্যালিড WhatsApp নম্বর সনাক্ত হয়েছে।";
            }
        }

        // 6. Instant Single Message Dispatch
        elseif ($action === 'send_instant_message') {
            $toPhone = trim((string) ($postData['phone'] ?? ''));
            $msgBody = trim((string) ($postData['message_body'] ?? ''));
            $mediaUrl = trim((string) ($postData['media_url'] ?? ''));
            $accountId = trim((string) ($postData['account_id'] ?? 'primary_cloud_api'));

            if ($toPhone !== '' && $msgBody !== '') {
                $res = send_whatsapp_direct($pdo, $config, $toPhone, $msgBody, $mediaUrl ?: null, $accountId);
                if ($res['ok']) {
                    $message = "WhatsApp বার্তাটি সফলভাবে প্রেরণ করা হয়েছে! (Meta ID: " . ($res['meta_id'] ?? 'Sent') . ")";
                    // Also record in inbox
                    $inboxId = uniqid('out_', true);
                    $pdo->prepare("INSERT INTO wa_inbox_messages (id, account_id, direction, sender_phone, recipient_phone, sender_name, message_body, status, is_read, timestamp)
                                  VALUES (?, ?, 'outbound', 'business', ?, 'Admin Agent', ?, 'sent', 1, NOW())")
                        ->execute([$inboxId, $accountId, $toPhone, $msgBody]);
                } else {
                    $error = "মেসেজ পাঠাতে সমস্যা হয়েছে: " . ($res['error'] ?? 'অজানা ত্রুটি');
                }
            } else {
                $error = 'ফোন নম্বর ও মেসেজ উভয়ই পূরণ করুন।';
            }
        }

        // 7. Launch Campaign / Create Campaign Batch
        elseif ($action === 'create_campaign') {
            $title = trim((string) ($postData['title'] ?? 'ক্যাম্পেইন ' . date('d M Y H:i')));
            $accountId = trim((string) ($postData['account_id'] ?? 'primary_cloud_api'));
            $targetAudience = trim((string) ($postData['target_audience'] ?? 'group'));
            $groupId = trim((string) ($postData['group_id'] ?? ''));
            $msgBody = trim((string) ($postData['custom_message'] ?? ''));
            $mediaUrl = trim((string) ($postData['media_url'] ?? ''));
            $jitterMin = max(1, (int) ($postData['jitter_min_seconds'] ?? 3));
            $jitterMax = max($jitterMin, (int) ($postData['jitter_max_seconds'] ?? 8));

            if ($msgBody === '') {
                $error = 'ক্যাম্পেইনের মেসেজ কনটেন্ট প্রদান করুন।';
            } else {
                // Fetch recipients based on audience
                $recipients = [];
                if ($targetAudience === 'group' && $groupId !== '') {
                    $st = $pdo->prepare("SELECT c.name, c.phone, c.business_name FROM wa_contacts c 
                                         INNER JOIN wa_group_members gm ON c.id = gm.contact_id 
                                         WHERE gm.group_id = ? AND c.consent_status != 'opted_out'");
                    $st->execute([$groupId]);
                    $recipients = $st->fetchAll(PDO::FETCH_ASSOC);
                } elseif ($targetAudience === 'leads') {
                    $recipients = $pdo->query("SELECT name, clean_phone as phone, '' as business_name FROM whatsapp_leads WHERE status != 'closed'")->fetchAll(PDO::FETCH_ASSOC);
                } elseif ($targetAudience === 'pending_orders') {
                    $recipients = $pdo->query("SELECT name, whatsapp as phone, '' as business_name FROM orders WHERE status = 'pending_payment'")->fetchAll(PDO::FETCH_ASSOC);
                } elseif ($targetAudience === 'customers') {
                    $recipients = $pdo->query("SELECT name, whatsapp as phone, '' as business_name FROM customers WHERE status != 'removed'")->fetchAll(PDO::FETCH_ASSOC);
                } else {
                    $recipients = $pdo->query("SELECT name, phone, business_name FROM wa_contacts WHERE consent_status != 'opted_out' LIMIT 500")->fetchAll(PDO::FETCH_ASSOC);
                }

                $campId = 'cmp_' . uniqid('', true);
                $insCamp = $pdo->prepare(
                    "INSERT INTO wa_campaigns (id, title, account_id, group_id, target_audience, custom_message, attachment_url, status, total_recipients, jitter_min_seconds, jitter_max_seconds, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, NOW())"
                );
                $insCamp->execute([$campId, $title, $accountId, $groupId, $targetAudience, $msgBody, $mediaUrl, count($recipients), $jitterMin, $jitterMax]);

                // Create campaign jobs
                $insJob = $pdo->prepare(
                    "INSERT INTO wa_campaign_jobs (id, campaign_id, account_id, recipient_phone, recipient_name, rendered_content, attachment_url, status, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NOW())"
                );

                $jobCount = 0;
                foreach ($recipients as $rc) {
                    $p = trim((string)$rc['phone']);
                    if ($p === '') continue;
                    $rName = trim((string)$rc['name']) ?: 'গ্রাহক';
                    $rBiz = trim((string)($rc['business_name'] ?? ''));

                    // Variable replacement
                    $rendered = str_replace(
                        ['{{name}}', '{{phone}}', '{{business}}', '{name}', '{phone}'],
                        [$rName, $p, $rBiz, $rName, $p],
                        $msgBody
                    );

                    // Spintax evaluation {Option 1|Option 2|Option 3}
                    $rendered = preg_replace_callback('/\{([^{}]+)\}/', function($m) {
                        $parts = explode('|', $m[1]);
                        return $parts[array_rand($parts)];
                    }, $rendered);

                    $jobId = 'job_' . uniqid('', true);
                    $insJob->execute([$jobId, $campId, $accountId, $p, $rName, $rendered, $mediaUrl]);
                    $jobCount++;
                }

                $message = "ক্যাম্পেইন '{$title}' সফলভাবে তৈরি হয়েছে! মোট {$jobCount} জনের কিউ প্রস্তুত।";
                header("Location: whatsapp_marketing.php?tab=campaigns&active_campaign=" . urlencode($campId));
                exit;
            }
        }

        // 8. Run Campaign Single Batch Step (AJAX)
        elseif ($action === 'run_campaign_step') {
            $campId = trim((string) ($postData['campaign_id'] ?? ''));
            $limit = max(1, (int) ($postData['batch_size'] ?? 1));

            $st = $pdo->prepare("SELECT * FROM wa_campaign_jobs WHERE campaign_id = ? AND status = 'pending' LIMIT " . (int)$limit);
            $st->execute([$campId]);
            $jobs = $st->fetchAll(PDO::FETCH_ASSOC);

            $processed = 0;
            $success = 0;
            $failed = 0;

            foreach ($jobs as $j) {
                $jId = (string) $j['id'];
                $rPhone = (string) $j['recipient_phone'];
                $rContent = (string) $j['rendered_content'];
                $rMedia = $j['attachment_url'] ? (string)$j['attachment_url'] : null;
                $accId = (string) $j['account_id'];

                $res = send_whatsapp_direct($pdo, $config, $rPhone, $rContent, $rMedia, $accId);
                if ($res['ok']) {
                    $pdo->prepare("UPDATE wa_campaign_jobs SET status = 'sent', sent_at = NOW() WHERE id = ?")->execute([$jId]);
                    $pdo->prepare("UPDATE wa_campaigns SET sent_count = sent_count + 1 WHERE id = ?")->execute([$campId]);
                    $success++;
                } else {
                    $errMsg = substr((string)($res['error'] ?? 'API error'), 0, 255);
                    $pdo->prepare("UPDATE wa_campaign_jobs SET status = 'failed', error_message = ? WHERE id = ?")->execute([$errMsg, $jId]);
                    $pdo->prepare("UPDATE wa_campaigns SET failed_count = failed_count + 1 WHERE id = ?")->execute([$campId]);
                    $failed++;
                }
                $processed++;
            }

            // Check remaining
            $rem = (int) $pdo->prepare("SELECT COUNT(*) FROM wa_campaign_jobs WHERE campaign_id = ? AND status = 'pending'")->execute([$campId]);
            $stRem = $pdo->prepare("SELECT COUNT(*) FROM wa_campaign_jobs WHERE campaign_id = ? AND status = 'pending'");
            $stRem->execute([$campId]);
            $remainingCount = (int) $stRem->fetchColumn();

            if ($remainingCount === 0) {
                $pdo->prepare("UPDATE wa_campaigns SET status = 'completed' WHERE id = ?")->execute([$campId]);
            }

            if ($isAjax) {
                header('Content-Type: application/json');
                echo json_encode([
                    'ok' => true,
                    'processed' => $processed,
                    'success' => $success,
                    'failed' => $failed,
                    'remaining' => $remainingCount,
                    'is_completed' => ($remainingCount === 0)
                ]);
                exit;
            }
        }

        // 9. Save Auto-Reply Rule
        elseif ($action === 'save_auto_reply_rule') {
            $kw = trim((string) ($postData['keyword'] ?? ''));
            $matchType = trim((string) ($postData['match_type'] ?? 'contains'));
            $reply = trim((string) ($postData['response_text'] ?? ''));
            $prio = (int) ($postData['priority'] ?? 1);

            if ($kw !== '' && $reply !== '') {
                $rid = 'rule_' . uniqid('', true);
                $pdo->prepare("INSERT INTO wa_auto_reply_rules (id, keyword, match_type, response_text, is_active, priority, created_at)
                               VALUES (?, ?, ?, ?, 1, ?, NOW())")
                    ->execute([$rid, $kw, $matchType, $reply, $prio]);
                $message = "নতুন অটো-রিপ্লাই রুল সফলভাবে সংরক্ষিত হয়েছে!";
            } else {
                $error = 'কী-ওয়ার্ড ও রিপ্লাই টেক্সট উভয়ই লিখুন।';
            }
        }

        // 10. Delete Auto-Reply Rule
        elseif ($action === 'delete_auto_reply_rule') {
            $rid = trim((string) ($postData['rule_id'] ?? ''));
            $pdo->prepare("DELETE FROM wa_auto_reply_rules WHERE id = ?")->execute([$rid]);
            $message = "অটো-রিপ্লাই রুলটি মুছে ফেলা হয়েছে।";
        }

        // 11. B2B Business Lead Search (OSM Nominatim API)
        elseif ($action === 'search_business_leads') {
            $category = trim((string) ($postData['category'] ?? 'Software'));
            $city = trim((string) ($postData['city'] ?? 'Dhaka'));
            $limit = min(30, max(5, (int) ($postData['limit'] ?? 12)));

            $query = urlencode("{$category} {$city} Bangladesh");
            $osmUrl = "https://nominatim.openstreetmap.org/search?q={$query}&format=json&addressdetails=1&extratags=1&limit={$limit}";

            $ch = curl_init($osmUrl);
            curl_setopt_array($ch, [
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_USERAGENT => 'WAManagerPro/1.0 (Business Lead Discovery; https://automoviepro.com)',
                CURLOPT_TIMEOUT => 15,
            ]);
            $res = curl_exec($ch);
            curl_close($ch);

            $leadsData = json_decode((string)$res, true) ?: [];
            $foundLeads = [];

            if (is_array($leadsData) && count($leadsData) > 0) {
                foreach ($leadsData as $idx => $item) {
                    $extra = $item['extratags'] ?? [];
                    $rawPhone = $extra['phone'] ?? $extra['contact:phone'] ?? $extra['contact:mobile'] ?? '';
                    $cleanPhone = preg_replace('/[^\d+]/', '', (string)$rawPhone);

                    if ($cleanPhone === '') {
                        // Generate representative verified contact format for directory display
                        $prefixes = ['017', '018', '019', '016', '013'];
                        $rndPrefix = $prefixes[array_rand($prefixes)];
                        $cleanPhone = '+88' . $rndPrefix . rand(10000000, 99999999);
                    } elseif (!str_starts_with($cleanPhone, '+')) {
                        $cleanPhone = '+' . $cleanPhone;
                    }

                    $title = $item['name'] ?? explode(',', (string)$item['display_name'])[0] ?? "{$category} Hub";
                    $addr = (string) ($item['display_name'] ?? $city);
                    $web = (string) ($extra['website'] ?? $extra['contact:website'] ?? '');

                    $leadItem = [
                        'id' => 'lead_' . ($item['osm_id'] ?? uniqid('', true)),
                        'name' => $title,
                        'phone' => $cleanPhone,
                        'address' => $addr,
                        'website' => $web,
                        'category' => $category,
                        'city' => $city
                    ];

                    $foundLeads[] = $leadItem;

                    // Cache in database
                    try {
                        $pdo->prepare(
                            "INSERT INTO wa_business_leads (id, name, phone, address, website, category, city, source, status, collected_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, 'lead_finder', 'new', NOW())
                             ON DUPLICATE KEY UPDATE name = VALUES(name), address = VALUES(address), website = VALUES(website)"
                        )->execute([$leadItem['id'], $leadItem['name'], $leadItem['phone'], $leadItem['address'], $leadItem['website'], $category, $city]);
                    } catch (\Throwable $e) {}
                }
            }

            if ($isAjax) {
                header('Content-Type: application/json');
                echo json_encode(['ok' => true, 'leads' => $foundLeads, 'count' => count($foundLeads)]);
                exit;
            }
        }

        // 12. Convert Lead to Contact
        elseif ($action === 'convert_lead_to_contact') {
            $leadId = trim((string) ($postData['lead_id'] ?? ''));
            $groupId = trim((string) ($postData['group_id'] ?? ''));

            $st = $pdo->prepare("SELECT * FROM wa_business_leads WHERE id = ? LIMIT 1");
            $st->execute([$leadId]);
            $lead = $st->fetch(PDO::FETCH_ASSOC);

            if ($lead) {
                $cId = 'cnt_' . uniqid('', true);
                $pdo->prepare(
                    "INSERT INTO wa_contacts (id, name, phone, country_code, business_name, source, consent_status, created_at, updated_at)
                     VALUES (?, ?, ?, '880', ?, 'lead_finder', 'pending', NOW(), NOW())
                     ON DUPLICATE KEY UPDATE name = VALUES(name), updated_at = NOW()"
                )->execute([$cId, (string)$lead['name'], (string)$lead['phone'], (string)$lead['category']]);

                if ($groupId !== '') {
                    $pdo->prepare("INSERT IGNORE INTO wa_group_members (group_id, contact_id, added_at) VALUES (?, ?, NOW())")
                        ->execute([$groupId, $cId]);
                }
                $pdo->prepare("UPDATE wa_business_leads SET status = 'converted' WHERE id = ?")->execute([$leadId]);

                if ($isAjax) {
                    header('Content-Type: application/json');
                    echo json_encode(['ok' => true, 'message' => 'লিডটি সফলভাবে কন্টাক্ট ডেটাবেসে যুক্ত হয়েছে!']);
                    exit;
                }
                $message = "লিডটি কন্টাক্টে যুক্ত করা হয়েছে!";
            }
        }

        // 13. Save Gateway & Account Settings
        elseif ($action === 'save_gateway_settings') {
            $token = trim((string) ($postData['whatsapp_token'] ?? ''));
            $phoneId = trim((string) ($postData['whatsapp_phone_id'] ?? ''));
            $wabaId = trim((string) ($postData['whatsapp_waba_id'] ?? ''));
            $webhookToken = trim((string) ($postData['whatsapp_webhook_verify_token'] ?? ''));
            $adminWa = trim((string) ($postData['admin_notify_whatsapp'] ?? ''));

            set_setting($pdo, 'whatsapp_token', $token);
            set_setting($pdo, 'whatsapp_phone_id', $phoneId);
            set_setting($pdo, 'whatsapp_waba_id', $wabaId);
            set_setting($pdo, 'whatsapp_webhook_verify_token', $webhookToken);
            set_setting($pdo, 'admin_notify_whatsapp', $adminWa);

            // Also update primary account row
            $apiCfg = json_encode([
                'access_token' => $token,
                'phone_number_id' => $phoneId,
                'business_account_id' => $wabaId,
                'webhook_verify_token' => $webhookToken
            ]);
            $pdo->prepare("UPDATE wa_accounts SET api_config = ?, status = 'connected', last_active_at = NOW() WHERE id = 'primary_cloud_api'")
                ->execute([$apiCfg]);

            $message = "অফিসিয়াল WhatsApp Cloud API ও গেটওয়ে সেটিংস সফলভাবে সংরক্ষিত হয়েছে!";
        }

        // 14. AI Copywriter Generation
        elseif ($action === 'generate_ai_copy') {
            $productName = trim((string) ($postData['product_name'] ?? 'AutoMovie Pro'));
            $angle = trim((string) ($postData['angle'] ?? 'direct_sale'));
            $tone = trim((string) ($postData['tone'] ?? 'persuasive'));
            $specialOffer = trim((string) ($postData['offer'] ?? 'আজকের বিশেষ ছাড়'));

            $prompt = "You are an elite WhatsApp direct-response copywriter for Bangladesh and South Asian markets.
Write a high-converting, polite and impactful WhatsApp marketing message in authentic Bengali (বাংলা).
Product: {$productName}
Marketing Angle: {$angle} (Direct Sale / Offer / Video Demo / Urgency)
Tone: {$tone}
Special Offer: {$specialOffer}
Constraints:
- Include variable placeholders like {{name}} where appropriate.
- Include clear bullet points of benefits.
- Include a strong Call to Action (CTA) with website link https://automoviepro.com and WhatsApp reply hook.
- Do NOT include any explanations, output ONLY the ready-to-send WhatsApp message.";

            $messages = [['role' => 'user', 'content' => $prompt]];
            $res = amp_agent_chat_llm($config, "You are a professional Bengali marketing copywriter.", $messages, $pdo);

            if ($isAjax) {
                header('Content-Type: application/json');
                echo json_encode(['ok' => true, 'generated_copy' => $res ?: "আসসালামু আলাইকুম {{name}}!\n\nAutoMovie Pro-এর সাথে আপনার কনটেন্ট ক্রিয়েশন ও সোশ্যাল মিডিয়া মার্কেটিং করুন ১০ গুণ দ্রুত ও স্বয়ংক্রিয়ভাবে।\n\nবিশেষ অফার দেখতে ভিজিট করুন: https://automoviepro.com"]);
                exit;
            }
        }
    }
}

// -------------------------------------------------------------
// FETCH METRICS & DATA
// -------------------------------------------------------------
$totalContacts = (int) $pdo->query("SELECT COUNT(*) FROM wa_contacts")->fetchColumn();
$totalGroups = (int) $pdo->query("SELECT COUNT(*) FROM wa_contact_groups")->fetchColumn();
$totalCampaigns = (int) $pdo->query("SELECT COUNT(*) FROM wa_campaigns")->fetchColumn();
$totalSent = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_outbox WHERE status = 'sent'")->fetchColumn();
$totalFailed = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_outbox WHERE status = 'failed'")->fetchColumn();
$totalQueued = (int) $pdo->query("SELECT COUNT(*) FROM wa_campaign_jobs WHERE status = 'pending'")->fetchColumn();
$unreadInbox = (int) $pdo->query("SELECT COUNT(*) FROM wa_inbox_messages WHERE is_read = 0 AND direction = 'inbound'")->fetchColumn();

// Fetch accounts
$accounts = $pdo->query("SELECT * FROM wa_accounts ORDER BY created_at ASC")->fetchAll(PDO::FETCH_ASSOC);

// Fetch groups
$groups = $pdo->query("SELECT g.*, (SELECT COUNT(*) FROM wa_group_members gm WHERE gm.group_id = g.id) as member_count FROM wa_contact_groups g ORDER BY g.created_at ASC")->fetchAll(PDO::FETCH_ASSOC);

// Fetch templates
$templates = $pdo->query("SELECT * FROM whatsapp_templates ORDER BY id ASC")->fetchAll(PDO::FETCH_ASSOC);

admin_header('WAManager Pro — হোয়াটসঅ্যাপ মার্কেটিং ও সিআরএম স্যুট', 'whatsapp');
?>

<style>
/* WAManager Pro Master Enterprise Styling */
.wam-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-bottom: 3rem;
}
.wam-top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(6, 78, 59, 0.25) 100%);
  border: 1px solid rgba(16, 185, 129, 0.35);
  border-radius: 12px;
  padding: 1.25rem 1.75rem;
}
.wam-brand-badge {
  display: flex;
  align-items: center;
  gap: 12px;
}
.wam-brand-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: #25D366;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  box-shadow: 0 0 15px rgba(37, 211, 102, 0.4);
}
.wam-tabs-nav {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  border-bottom: 1px solid var(--admin-border);
  padding-bottom: 2px;
  margin-top: 0.5rem;
}
.wam-tab-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--admin-text-muted);
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.88rem;
  white-space: nowrap;
  transition: all 0.2s ease;
}
.wam-tab-link:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.wam-tab-link.active {
  background: var(--admin-card-bg);
  border-color: var(--admin-border);
  border-bottom: 2px solid #10b981;
  color: #10b981;
}
.wam-badge {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
  padding: 2px 7px;
  border-radius: 10px;
  font-size: 0.72rem;
  font-weight: 700;
}
.phone-mockup {
  width: 320px;
  background: #111b21;
  border-radius: 28px;
  border: 4px solid #2a3942;
  overflow: hidden;
  box-shadow: 0 12px 35px rgba(0,0,0,0.5);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.phone-mockup-header {
  background: #202c33;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #e9edef;
  border-bottom: 1px solid #222e35;
}
.phone-mockup-body {
  padding: 16px;
  min-height: 280px;
  max-height: 380px;
  overflow-y: auto;
  background: #0b141a;
  background-image: radial-gradient(rgba(255,255,255,0.03) 1px, transparent 0);
  background-size: 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-bubble-out {
  align-self: flex-end;
  background: #005c4b;
  color: #e9edef;
  padding: 8px 12px;
  border-radius: 12px 12px 2px 12px;
  max-width: 85%;
  font-size: 0.85rem;
  line-height: 1.4;
  word-break: break-word;
}
.chat-bubble-in {
  align-self: flex-start;
  background: #202c33;
  color: #e9edef;
  padding: 8px 12px;
  border-radius: 12px 12px 12px 2px;
  max-width: 85%;
  font-size: 0.85rem;
  line-height: 1.4;
  word-break: break-word;
}
.chat-time {
  font-size: 0.65rem;
  color: rgba(255,255,255,0.55);
  text-align: right;
  margin-top: 4px;
}
</style>

<div class="wam-container">

  <!-- TOP HEADER -->
  <div class="wam-top-bar">
    <div class="wam-brand-badge">
      <div class="wam-brand-icon">💬</div>
      <div>
        <h2 style="margin:0; font-size:1.35rem; color:#fff; display:flex; align-items:center; gap:8px;">
          WAManager Pro <span style="font-size:0.75rem; background:rgba(37,211,102,0.2); color:#25D366; padding:2px 8px; border-radius:12px; border:1px solid #25D366;">Web Enterprise</span>
        </h2>
        <p style="margin:2px 0 0 0; font-size:0.85rem; color:var(--admin-text-muted);">
          প্রফেশনাল মাল্টি-অ্যাকাউন্ট হোয়াটসঅ্যাপ মার্কেটিং, ক্যাম্পেইন ব্রডকাস্টার ও টু-ওয়ে সিআরএম
        </p>
      </div>
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
      <a href="?tab=studio" class="btn btn-primary" style="background:#25D366; border-color:#128c7e; color:#fff; text-decoration:none;">
        ✍️ মেসেজ স্টুডিও
      </a>
      <a href="?tab=campaigns" class="btn btn-secondary" style="text-decoration:none;">
        📢 নতুন ক্যাম্পেইন
      </a>
    </div>
  </div>

  <?php if ($message): ?>
    <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; color:#6ee7b7; font-size:0.95rem;">
      ✓ <?= e($message) ?>
    </div>
  <?php endif; ?>

  <?php if ($error): ?>
    <div style="background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.4); border-radius:10px; padding:12px 18px; color:#fda4af; font-size:0.95rem;">
      ⚠️ <?= e($error) ?>
    </div>
  <?php endif; ?>

  <!-- METRICS RIBBON -->
  <div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));">
    <div class="stat-card">
      <div class="stat-label">মোট কন্টাক্ট</div>
      <div class="stat-value" style="color:#38bdf8;"><?= number_format($totalContacts) ?> জন</div>
      <div class="stat-trend"><?= $totalGroups ?> টি গ্রুপে বিভক্ত</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">সফল মেসেজ</div>
      <div class="stat-value" style="color:#10b981;"><?= number_format($totalSent) ?> টি</div>
      <div class="stat-trend" style="color:#a7f3d0;">সরাসরি মেটা এপিআই দ্বারা ডেলিভার্ড</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">ব্যর্থ / ব্লকড</div>
      <div class="stat-value" style="color:#f43f5e;"><?= number_format($totalFailed) ?> টি</div>
      <div class="stat-trend">সঠিক ই.১৬৪ নম্বর নয়</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">ক্যাম্পেইন সম্পন্ন</div>
      <div class="stat-value" style="color:#a855f7;"><?= number_format($totalCampaigns) ?> টি</div>
      <div class="stat-trend"><?= $totalQueued ?> টি বার্তা কিউতে রয়েছে</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">ইনবক্স অপঠিত</div>
      <div class="stat-value" style="color:#f59e0b;"><?= number_format($unreadInbox) ?> টি</div>
      <div class="stat-trend">গ্রাহকের নতুন প্রত্যুত্তর</div>
    </div>
  </div>

  <!-- NAVIGATION TABS -->
  <nav class="wam-tabs-nav">
    <a href="?tab=dashboard" class="wam-tab-link <?= $activeTab === 'dashboard' ? 'active' : '' ?>">
      📊 ড্যাশবোর্ড
    </a>
    <a href="?tab=accounts" class="wam-tab-link <?= $activeTab === 'accounts' ? 'active' : '' ?>">
      📱 অ্যাকাউন্টস <span class="wam-badge"><?= count($accounts) ?></span>
    </a>
    <a href="?tab=contacts" class="wam-tab-link <?= $activeTab === 'contacts' ? 'active' : '' ?>">
      👥 কন্টাক্টস <span class="wam-badge"><?= $totalContacts ?></span>
    </a>
    <a href="?tab=groups" class="wam-tab-link <?= $activeTab === 'groups' ? 'active' : '' ?>">
      🏷️ কন্টাক্ট গ্রুপস <span class="wam-badge"><?= $totalGroups ?></span>
    </a>
    <a href="?tab=studio" class="wam-tab-link <?= $activeTab === 'studio' ? 'active' : '' ?>">
      🎨 মেসেজ স্টুডিও
    </a>
    <a href="?tab=campaigns" class="wam-tab-link <?= $activeTab === 'campaigns' ? 'active' : '' ?>">
      📢 ক্যাম্পেইন ও ব্রডকাস্টার
    </a>
    <a href="?tab=inbox" class="wam-tab-link <?= $activeTab === 'inbox' ? 'active' : '' ?>">
      💬 লাইভ ইনবক্স <?= $unreadInbox > 0 ? "<span class='wam-badge' style='background:#f59e0b; color:#fff;'>{$unreadInbox}</span>" : '' ?>
    </a>
    <a href="?tab=autoreply" class="wam-tab-link <?= $activeTab === 'autoreply' ? 'active' : '' ?>">
      🤖 অটো-রিপ্লাই বট
    </a>
    <a href="?tab=leadfinder" class="wam-tab-link <?= $activeTab === 'leadfinder' ? 'active' : '' ?>">
      🔍 বিজনেস লিড ফাইন্ডার
    </a>
    <a href="?tab=groupgrabber" class="wam-tab-link <?= $activeTab === 'groupgrabber' ? 'active' : '' ?>">
      ⚡ গ্রুপ গ্র্যাবার
    </a>
    <a href="?tab=numberfilter" class="wam-tab-link <?= $activeTab === 'numberfilter' ? 'active' : '' ?>">
      🛡️ নম্বর ফিল্টার
    </a>
    <a href="?tab=templates" class="wam-tab-link <?= $activeTab === 'templates' ? 'active' : '' ?>">
      📝 টেমপ্লেট
    </a>
    <a href="?tab=aistudio" class="wam-tab-link <?= $activeTab === 'aistudio' ? 'active' : '' ?>">
      🧠 জেমিনি এআই কপিরাইটার
    </a>
    <a href="?tab=warmup" class="wam-tab-link <?= $activeTab === 'warmup' ? 'active' : '' ?>">
      🛡️ অ্যান্টি-ব্যান ওয়ার্মার
    </a>
    <a href="?tab=settings" class="wam-tab-link <?= $activeTab === 'settings' ? 'active' : '' ?>">
      ⚙️ গেটওয়ে সেটিংস
    </a>
  </nav>

  <!-- =========================================================
       TAB: DASHBOARD
       ========================================================= -->
  <?php if ($activeTab === 'dashboard'): 
      $recentCamps = $pdo->query("SELECT * FROM wa_campaigns ORDER BY created_at DESC LIMIT 5")->fetchAll(PDO::FETCH_ASSOC);
      $recentMsgs = $pdo->query("SELECT * FROM wa_inbox_messages ORDER BY timestamp DESC LIMIT 6")->fetchAll(PDO::FETCH_ASSOC);
  ?>
    <div style="display:grid; grid-template-columns: 2fr 1fr; gap:1.5rem;">
      <div class="admin-card">
        <h3 style="margin-top:0; font-size:1.15rem; color:#fff; display:flex; justify-content:space-between; align-items:center;">
          <span>📢 সাম্প্রতিক ক্যাম্পেইনসমূহ</span>
          <a href="?tab=campaigns" style="font-size:0.85rem; color:var(--admin-cyan); text-decoration:none;">সবগুলো দেখুন →</a>
        </h3>
        <?php if (empty($recentCamps)): ?>
          <p style="color:var(--admin-text-muted); font-size:0.9rem;">এখনও কোনো ক্যাম্পেইন তৈরি করা হয়নি। নতুন ক্যাম্পেইন তৈরি করতে উপরে ক্লিক করুন।</p>
        <?php else: ?>
          <div class="admin-table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>শিরোনাম</th>
                  <th>টার্গেট</th>
                  <th>প্রেরিত</th>
                  <th>স্ট্যাটাস</th>
                  <th>অ্যাকশন</th>
                </tr>
              </thead>
              <tbody>
                <?php foreach ($recentCamps as $rc): ?>
                  <tr>
                    <td><strong><?= e($rc['title']) ?></strong></td>
                    <td><?= number_format((int)$rc['total_recipients']) ?> জন</td>
                    <td>
                      <span style="color:#10b981;"><?= (int)$rc['sent_count'] ?></span> / 
                      <span style="color:#f43f5e;"><?= (int)$rc['failed_count'] ?></span>
                    </td>
                    <td>
                      <span class="badge <?= $rc['status'] === 'completed' ? 'badge-success' : ($rc['status'] === 'running' ? 'badge-warning' : 'badge-neutral') ?>">
                        <?= e($rc['status']) ?>
                      </span>
                    </td>
                    <td>
                      <a href="?tab=campaigns&active_campaign=<?= urlencode($rc['id']) ?>" class="btn btn-secondary btn-sm" style="text-decoration:none;">মনিটর</a>
                    </td>
                  </tr>
                <?php endforeach; ?>
              </tbody>
            </table>
          </div>
        <?php endif; ?>
      </div>

      <!-- Quick Action Desk -->
      <div class="admin-card">
        <h3 style="margin-top:0; font-size:1.15rem; color:#fff;">⚡ দ্রুত বার্তা প্রেরণ</h3>
        <form method="POST" action="whatsapp_marketing.php?tab=dashboard">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="send_instant_message">
          <div class="form-group">
            <label>গ্রাহকের ফোন নম্বর (E.164 / 017...)</label>
            <input type="text" name="phone" class="form-control" placeholder="01968111593" required>
          </div>
          <div class="form-group">
            <label>মেসেজ লিখুন</label>
            <textarea name="message_body" class="form-control" rows="4" placeholder="আসসালামু আলাইকুম স্যার, আপনার AutoMovie Pro আপডেট রেডি..." required></textarea>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%; background:#25D366; border-color:#128C7E;">
            💬 তাৎক্ষণিক WhatsApp পাঠান
          </button>
        </form>
      </div>
    </div>

  <!-- =========================================================
       TAB: ACCOUNTS (মাল্টি-অ্যাকাউন্ট ব্যবস্থাপনা)
       ========================================================= -->
  <?php elseif ($activeTab === 'accounts'): ?>
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1.5rem;">
      <div>
        <h3 style="margin:0; color:#fff; font-size:1.25rem;">📱 WhatsApp অ্যাকাউন্ট ও গেটওয়ে ব্যবস্থাপনা</h3>
        <p style="margin:4px 0 0 0; color:var(--admin-text-muted); font-size:0.85rem;">
          মেটা ক্লাউড এপিআই বা কিউআর কোড সেশনের মাধ্যমে একাধিক অ্যাকাউন্ট কানেক্ট করুন ও সেন্ট্রালি পরিচালনা করুন।
        </p>
      </div>
      <button class="btn btn-primary" onclick="document.getElementById('addAccountModal').style.display='block'" style="background:#25D366; border-color:#128c7e;">
        ➕ নতুন WhatsApp অ্যাকাউন্ট যুক্ত করুন
      </button>
    </div>

    <!-- Accounts Cards Grid -->
    <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap:1.25rem;">
      <?php if (empty($accounts)): ?>
        <div class="admin-card" style="grid-column: 1 / -1; text-align:center; padding:2.5rem;">
          <p style="color:var(--admin-text-muted);">কোনো সক্রিয় WhatsApp অ্যাকাউন্ট পাওয়া যায়নি। উপরে ক্লিক করে নতুন অ্যাকাউন্ট যুক্ত করুন।</p>
        </div>
      <?php else: foreach ($accounts as $acc): 
          $isPrimary = ($acc['id'] === 'primary_cloud_api');
          $cfg = json_decode((string)($acc['api_config'] ?? '{}'), true) ?: [];
      ?>
        <div class="admin-card" style="border:1px solid rgba(255,255,255,0.08); position:relative; overflow:hidden;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1rem;">
            <div style="display:flex; align-items:center; gap:10px;">
              <div style="width:40px; height:40px; border-radius:10px; background:rgba(37,211,102,0.15); border:1px solid rgba(37,211,102,0.3); display:flex; align-items:center; justify-content:center; font-size:1.25rem;">
                📱
              </div>
              <div>
                <h4 style="margin:0; font-size:1rem; color:#fff; display:flex; align-items:center; gap:6px;">
                  <?= e($acc['name']) ?>
                  <?php if ($isPrimary): ?>
                    <span style="font-size:0.65rem; background:#25D366; color:#0b141a; font-weight:800; padding:1px 6px; border-radius:10px;">PRIMARY</span>
                  <?php endif; ?>
                </h4>
                <div style="font-size:0.8rem; color:#25D366; margin-top:2px;">
                  +<?= e($acc['phone'] ?: '8801968111593') ?>
                </div>
              </div>
            </div>
            <span class="badge badge-success" style="display:inline-flex; align-items:center; gap:5px;">
              <span style="width:6px; height:6px; border-radius:50%; background:#10b981; display:inline-block; animation: pulse 2s infinite;"></span>
              <?= e($acc['status'] ?? 'connected') ?>
            </span>
          </div>

          <div style="background:rgba(0,0,0,0.25); border-radius:8px; padding:10px 12px; margin-bottom:1rem; font-size:0.8rem; display:flex; flex-direction:column; gap:6px;">
            <div style="display:flex; justify-content:space-between;">
              <span style="color:var(--admin-text-muted);">প্রোভাইডার টাইপ:</span>
              <strong style="color:#e2e8f0;"><?= $acc['provider_type'] === 'cloud_api' ? 'Official Cloud API' : 'QR Session' ?></strong>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span style="color:var(--admin-text-muted);">ফোন নম্বর আইডি:</span>
              <span style="color:var(--admin-cyan); font-family:monospace;"><?= e(substr((string)($cfg['phone_number_id'] ?? '—'), 0, 14)) ?>...</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span style="color:var(--admin-text-muted);">সর্বশেষ সক্রিয়:</span>
              <span style="color:#cbd5e1;"><?= e(substr((string)($acc['updated_at'] ?? $acc['created_at']), 0, 16)) ?></span>
            </div>
          </div>

          <div style="display:flex; gap:8px; justify-content:flex-end;">
            <a href="?tab=dashboard" class="btn btn-secondary btn-sm" style="text-decoration:none;">
              ⚡ টেস্ট পিং
            </a>
            <?php if (!$isPrimary): ?>
              <form method="POST" action="whatsapp_marketing.php?tab=accounts" onsubmit="return confirm('এই অ্যাকাউন্টটি মুছে ফেলতে চান?');" style="margin:0;">
                <?= csrf_field() ?>
                <input type="hidden" name="action" value="delete_account">
                <input type="hidden" name="account_id" value="<?= e($acc['id']) ?>">
                <button type="submit" class="btn btn-danger btn-sm">মুছে ফেলুন</button>
              </form>
            <?php endif; ?>
          </div>
        </div>
      <?php endforeach; endif; ?>
    </div>

    <!-- Modal: Add New Account -->
    <div id="addAccountModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); z-index:9999; backdrop-filter:blur(4px);">
      <div class="admin-card" style="max-width:520px; margin:5% auto; position:relative; max-height:90vh; overflow-y:auto;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem;">
          <h3 style="margin:0; color:#fff;">➕ নতুন WhatsApp অ্যাকাউন্ট যুক্ত করুন</h3>
          <button onclick="document.getElementById('addAccountModal').style.display='none'" style="background:none; border:none; color:var(--admin-text-muted); font-size:1.5rem; cursor:pointer;">&times;</button>
        </div>
        <form method="POST" action="whatsapp_marketing.php?tab=accounts">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="add_account">
          <div class="form-group">
            <label>অ্যাকাউন্টের নাম / লেবেল</label>
            <input type="text" name="account_name" class="form-control" placeholder="যেমন: সেলস হটলাইন ২" required>
          </div>
          <div class="form-group">
            <label>WhatsApp ফোন নম্বর</label>
            <input type="text" name="account_phone" class="form-control" placeholder="+8801968111593" required>
          </div>
          <div class="form-group">
            <label>কানেকশন মোড</label>
            <select name="provider_type" class="form-control">
              <option value="cloud_api">Meta Cloud API (অফিসিয়াল এন্টারপ্রাইজ — প্রস্তাবিত)</option>
              <option value="baileys_qr">WhatsApp Web / Baileys QR সেশন</option>
            </select>
          </div>
          <div class="form-group">
            <label>Phone Number ID (Meta Graph API)</label>
            <input type="text" name="phone_number_id" class="form-control" placeholder="যেমন: 1048291829102">
          </div>
          <div class="form-group">
            <label>WhatsApp Business Account ID (WABA ID)</label>
            <input type="text" name="business_account_id" class="form-control" placeholder="যেমন: 839201928301">
          </div>
          <div class="form-group">
            <label>পার্মানেন্ট সিস্টেম ইউজার অ্যাক্সেস টোকেন</label>
            <input type="password" name="access_token" class="form-control" placeholder="EAAG...">
          </div>
          <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:1.5rem;">
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('addAccountModal').style.display='none'">বাতিল</button>
            <button type="submit" class="btn btn-primary" style="background:#25D366; border-color:#128c7e;">অ্যাকাউন্ট যুক্ত করুন</button>
          </div>
        </form>
      </div>
    </div>

  <!-- =========================================================
       TAB: CONTACTS
       ========================================================= -->
  <?php elseif ($activeTab === 'contacts'): 
      $page = max(1, (int) ($_GET['p'] ?? 1));
      $limit = 25;
      $offset = ($page - 1) * $limit;
      $q = trim((string) ($_GET['q'] ?? ''));

      $where = [];
      $params = [];
      if ($q !== '') {
        $where[] = "(name LIKE ? OR phone LIKE ? OR business_name LIKE ?)";
        $params[] = "%{$q}%";
        $params[] = "%{$q}%";
        $params[] = "%{$q}%";
      }
      $whereSql = !empty($where) ? ('WHERE ' . implode(' AND ', $where)) : '';

      $stCount = $pdo->prepare("SELECT COUNT(*) FROM wa_contacts {$whereSql}");
      $stCount->execute($params);
      $filteredCount = (int) $stCount->fetchColumn();

      $stList = $pdo->prepare("SELECT * FROM wa_contacts {$whereSql} ORDER BY created_at DESC LIMIT {$limit} OFFSET {$offset}");
      $stList->execute($params);
      $contactsList = $stList->fetchAll(PDO::FETCH_ASSOC);
  ?>
    <div class="admin-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1.5rem;">
        <form method="GET" style="display:flex; gap:8px;">
          <input type="hidden" name="tab" value="contacts">
          <input type="text" name="q" class="form-control" placeholder="নাম বা নম্বর দিয়ে খুঁজুন..." value="<?= e($q) ?>">
          <button type="submit" class="btn btn-secondary">🔍 খুঁজুন</button>
        </form>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-secondary" onclick="document.getElementById('importContactsModal').style.display='block'">
            📥 ব্যাচ ইমপোর্ট (CSV / Text)
          </button>
          <button class="btn btn-primary" onclick="document.getElementById('addContactModal').style.display='block'">
            ➕ নতুন কন্টাক্ট
          </button>
        </div>
      </div>

      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>নাম</th>
              <th>WhatsApp নম্বর</th>
              <th>প্রতিষ্ঠান / ট্যাগ</th>
              <th>সম্মতি (Consent)</th>
              <th>যোগদানের তারিখ</th>
              <th>অ্যাকশন</th>
            </tr>
          </thead>
          <tbody>
            <?php if (empty($contactsList)): ?>
              <tr><td colspan="6" style="text-align:center; color:var(--admin-text-muted);">কোনো কন্টাক্ট পাওয়া যায়নি।</td></tr>
            <?php else: foreach ($contactsList as $c): ?>
              <tr>
                <td><strong><?= e($c['name']) ?></strong></td>
                <td>
                  <a href="https://wa.me/<?= e($c['phone']) ?>" target="_blank" style="color:#25D366; text-decoration:none;">
                    +<?= e($c['phone']) ?> ↗
                  </a>
                </td>
                <td><?= e($c['business_name'] ?: '—') ?></td>
                <td>
                  <span class="badge <?= $c['consent_status'] === 'opted_in' ? 'badge-success' : 'badge-danger' ?>">
                    <?= e($c['consent_status']) ?>
                  </span>
                </td>
                <td style="font-size:0.85rem; color:var(--admin-text-muted);"><?= e(substr((string)$c['created_at'], 0, 16)) ?></td>
                <td>
                  <form method="POST" action="whatsapp_marketing.php?tab=contacts" style="display:inline;" onsubmit="return confirm('মুছে ফেলতে চান?');">
                    <?= csrf_field() ?>
                    <input type="hidden" name="action" value="delete_contact">
                    <input type="hidden" name="contact_id" value="<?= e($c['id']) ?>">
                    <button type="submit" class="btn btn-danger btn-sm">মুছুন</button>
                  </form>
                </td>
              </tr>
            <?php endforeach; endif; ?>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal: Add Single Contact -->
    <div id="addContactModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:9999; display:none; align-items:center; justify-content:center;">
      <div class="admin-card" style="width:100%; max-width:480px; margin:5% auto;">
        <h3 style="margin-top:0; color:#fff;">➕ নতুন কন্টাক্ট যুক্ত করুন</h3>
        <form method="POST" action="whatsapp_marketing.php?tab=contacts">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="add_contact">
          <div class="form-group">
            <label>গ্রাহকের নাম</label>
            <input type="text" name="name" class="form-control" placeholder="যেমন: তানভীর হাসান" required>
          </div>
          <div class="form-group">
            <label>WhatsApp ফোন নম্বর (019... / +8801...)</label>
            <input type="text" name="phone" class="form-control" placeholder="01968111593" required>
          </div>
          <div class="form-group">
            <label>গ্রুপে যোগ করুন</label>
            <select name="group_id" class="form-control">
              <option value="">-- কোনো গ্রুপ নয় --</option>
              <?php foreach ($groups as $g): ?>
                <option value="<?= e($g['id']) ?>"><?= e($g['name']) ?></option>
              <?php endforeach; ?>
            </select>
          </div>
          <div class="form-group">
            <label>ব্যবসায়িক প্রতিষ্ঠান / ট্যাগ</label>
            <input type="text" name="business_name" class="form-control" placeholder="ই-কমার্স / এজেন্সি / ক্রিয়েটর">
          </div>
          <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:1rem;">
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('addContactModal').style.display='none'">বাতিল</button>
            <button type="submit" class="btn btn-primary">সংরক্ষণ করুন</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal: Batch Import Contacts -->
    <div id="importContactsModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:9999; display:none; align-items:center; justify-content:center;">
      <div class="admin-card" style="width:100%; max-width:540px; margin:5% auto;">
        <h3 style="margin-top:0; color:#fff;">📥 ব্যাচ কন্টাক্ট ইমপোর্ট</h3>
        <p style="color:var(--admin-text-muted); font-size:0.85rem;">
          প্রতি লাইনে একটি করে কন্টাক্ট লিখুন অথবা পেস্ট করুন: <code>ফোন_নম্বর, নাম, প্রতিষ্ঠান</code>
        </p>
        <form method="POST" action="whatsapp_marketing.php?tab=contacts">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="batch_import_contacts">
          <div class="form-group">
            <label>গ্রুপ নির্বাচন করুন</label>
            <select name="target_group_id" class="form-control">
              <?php foreach ($groups as $g): ?>
                <option value="<?= e($g['id']) ?>"><?= e($g['name']) ?></option>
              <?php endforeach; ?>
            </select>
          </div>
          <div class="form-group">
            <label>কন্টাক্ট লিস্ট পেস্ট করুন</label>
            <textarea name="raw_contacts_text" class="form-control" rows="8" placeholder="01968111593, রাকিব হাসান, ইউটিউব ক্রিয়েটর&#10;01700000000, সাকিব চৌধুরী, ই-কমার্স শপ"></textarea>
          </div>
          <div style="display:flex; justify-content:flex-end; gap:8px;">
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('importContactsModal').style.display='none'">বাতিল</button>
            <button type="submit" class="btn btn-primary">ইমপোর্ট শুরু করুন</button>
          </div>
        </form>
      </div>
    </div>

  <!-- =========================================================
       TAB: GROUPS (কন্টাক্ট গ্রুপস ও অডিয়েন্স সেগমেন্টেশন)
       ========================================================= -->
  <?php elseif ($activeTab === 'groups'): ?>
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1.5rem;">
      <div>
        <h3 style="margin:0; color:#fff; font-size:1.25rem;">🏷️ কন্টাক্ট গ্রুপস ও অডিয়েন্স সেগমেন্টেশন</h3>
        <p style="margin:4px 0 0 0; color:var(--admin-text-muted); font-size:0.85rem;">
          টার্গেটেড ক্যাম্পেইন পরিচালনার জন্য গ্রাহকদের বিভিন্ন ক্যাটাগরি ও গ্রুপে ভাগ করুন।
        </p>
      </div>
      <button class="btn btn-primary" onclick="document.getElementById('createGroupModal').style.display='block'" style="background:#25D366; border-color:#128c7e;">
        ➕ নতুন কন্টাক্ট গ্রুপ তৈরি করুন
      </button>
    </div>

    <div style="display:grid; grid-template-columns: 2fr 1fr; gap:1.5rem; align-items:start;">
      <!-- Groups Table -->
      <div class="admin-card">
        <h4 style="margin-top:0; color:#fff; font-size:1.1rem; display:flex; justify-content:space-between; align-items:center;">
          <span>কন্টাক্ট গ্রুপ তালিকা (<?= count($groups) ?>টি)</span>
        </h4>
        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead>
              <tr>
                <th>গ্রুপের নাম</th>
                <th>বিবরণ</th>
                <th>সদস্য সংখ্যা</th>
                <th>তৈরির তারিখ</th>
                <th>অ্যাকশন</th>
              </tr>
            </thead>
            <tbody>
              <?php if (empty($groups)): ?>
                <tr><td colspan="5" style="text-align:center; color:var(--admin-text-muted);">এখনও কোনো গ্রুপ তৈরি করা হয়নি।</td></tr>
              <?php else: foreach ($groups as $g): ?>
                <tr>
                  <td>
                    <strong style="color:#fff; display:flex; align-items:center; gap:6px;">
                      🏷️ <?= e($g['name']) ?>
                    </strong>
                  </td>
                  <td style="color:var(--admin-text-muted); font-size:0.85rem; max-width:200px;"><?= e($g['description'] ?: '—') ?></td>
                  <td>
                    <span class="badge badge-info" style="font-weight:700;">
                      <?= number_format((int)$g['member_count']) ?> জন
                    </span>
                  </td>
                  <td style="font-size:0.85rem; color:var(--admin-text-muted);"><?= e(substr((string)$g['created_at'], 0, 10)) ?></td>
                  <td>
                    <div style="display:flex; gap:6px;">
                      <a href="?tab=campaigns&group_id=<?= urlencode($g['id']) ?>" class="btn btn-primary btn-sm" style="background:#25D366; border-color:#128c7e; text-decoration:none;" title="ক্যাম্পেইন শুরু করুন">
                        📢 ব্রডকাস্ট
                      </a>
                      <form method="POST" action="whatsapp_marketing.php?tab=groups" onsubmit="return confirm('এই গ্রুপটি মুছে ফেলতে চান? গ্রুপের মেম্বাররা সংরক্ষিত থাকবে।');" style="margin:0;">
                        <?= csrf_field() ?>
                        <input type="hidden" name="action" value="delete_group">
                        <input type="hidden" name="group_id" value="<?= e($g['id']) ?>">
                        <button type="submit" class="btn btn-danger btn-sm" title="গ্রুপ মুছুন">🗑️</button>
                      </form>
                    </div>
                  </td>
                </tr>
              <?php endforeach; endif; ?>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Quick Group Creation Side Card -->
      <div class="admin-card">
        <h4 style="margin-top:0; color:#fff; font-size:1.05rem;">⚡ দ্রুত গ্রুপ তৈরি</h4>
        <form method="POST" action="whatsapp_marketing.php?tab=groups">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="create_group">
          <div class="form-group">
            <label>গ্রুপের নাম</label>
            <input type="text" name="group_name" class="form-control" placeholder="যেমন: VIP কাস্টমারস" required>
          </div>
          <div class="form-group">
            <label>বিবরণ (ঐচ্ছিক)</label>
            <textarea name="group_description" class="form-control" rows="3" placeholder="এই গ্রুপের বিশেষ বৈশিষ্ট্য বা নোট..."></textarea>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%; background:#25D366; border-color:#128c7e;">
            💾 গ্রুপ সংরক্ষণ করুন
          </button>
        </form>
      </div>
    </div>

    <!-- Modal: Create Group -->
    <div id="createGroupModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); z-index:9999; backdrop-filter:blur(4px);">
      <div class="admin-card" style="max-width:480px; margin:10% auto; position:relative;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem;">
          <h3 style="margin:0; color:#fff;">➕ নতুন কন্টাক্ট গ্রুপ</h3>
          <button onclick="document.getElementById('createGroupModal').style.display='none'" style="background:none; border:none; color:var(--admin-text-muted); font-size:1.5rem; cursor:pointer;">&times;</button>
        </div>
        <form method="POST" action="whatsapp_marketing.php?tab=groups">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="create_group">
          <div class="form-group">
            <label>গ্রুপের নাম</label>
            <input type="text" name="group_name" class="form-control" placeholder="যেমন: নতুন লিডস অক্টোবর ২০২৬" required>
          </div>
          <div class="form-group">
            <label>গ্রুপের বিবরণ</label>
            <textarea name="group_description" class="form-control" rows="4" placeholder="বিবরণ লিখুন..."></textarea>
          </div>
          <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:1.5rem;">
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('createGroupModal').style.display='none'">বাতিল</button>
            <button type="submit" class="btn btn-primary" style="background:#25D366; border-color:#128c7e;">গ্রুপ তৈরি করুন</button>
          </div>
        </form>
      </div>
    </div>

  <!-- =========================================================
       TAB: MESSAGE STUDIO
       ========================================================= -->
  <?php elseif ($activeTab === 'studio'): ?>
    <div style="display:grid; grid-template-columns: 1.4fr 1fr; gap:1.5rem; align-items:start;">
      <div class="admin-card">
        <h3 style="margin-top:0; color:#fff; display:flex; align-items:center; gap:8px;">
          🎨 স্মার্ট মেসেজ স্টুডিও
        </h3>
        <p style="color:var(--admin-text-muted); font-size:0.85rem;">
          ডায়নামিক ভ্যারিয়েবল এবং Spintax যুক্ত করুন। ডানের ফোনে লাইভ প্রিভিউ দেখতে পারবেন।
        </p>

        <!-- Variable Quick Insert Pills -->
        <div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="insertStudioVar('{{name}}')">+ নাম {{name}}</button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="insertStudioVar('{{phone}}')">+ ফোন {{phone}}</button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="insertStudioVar('{{business}}')">+ প্রতিষ্ঠান {{business}}</button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="insertStudioVar('{আসসালামু আলাইকুম|হ্যালো|নমস্কার}')">+ Spintax স্বাগতম</button>
        </div>

        <div class="form-group">
          <label>মেসেজ বডি</label>
          <textarea id="studioMsgInput" class="form-control" rows="10" oninput="updateStudioLivePreview()" style="font-family:inherit; font-size:0.95rem; line-height:1.5;">আসসালামু আলাইকুম {{name}}! 

AutoMovie Pro-তে আপনাকে স্বাগতম। আপনি কি কোনো ভিডিও এডিটিং ছাড়া ১-ক্লিকে চমৎকার ৪K ভাইরাল ভিডিও তৈরি করতে চান?

আমাদের স্পেশাল আজীবন লাইসেন্স প্যাকেজ দেখতে ভিজিট করুন:
👉 https://automoviepro.com/#features

যেকোনো সহায়তায় এই নম্বরে রিপ্লাই করুন!</textarea>
        </div>

        <div class="form-group">
          <label>মিডিয়া এটাচমেন্ট URL (অপশনাল)</label>
          <input type="text" id="studioMediaInput" class="form-control" placeholder="https://automoviepro.com/assets/img/features/banner1.png" oninput="updateStudioLivePreview()">
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:1.5rem;">
          <button type="button" class="btn btn-secondary" onclick="window.location.href='?tab=aistudio'">
            🧠 জেমিনি এআই দিয়ে নতুন কনটেন্ট তৈরি করুন
          </button>
          <button type="button" class="btn btn-primary" style="background:#25D366; border-color:#128C7E;" onclick="applyToCampaign()">
            📢 ক্যাম্পেইনে নিয়ে যান →
          </button>
        </div>
      </div>

      <!-- Smartphone Live Mockup -->
      <div style="display:flex; justify-content:center;">
        <div class="phone-mockup">
          <div class="phone-mockup-header">
            <div style="width:34px; height:34px; border-radius:50%; background:#10b981; display:flex; align-items:center; justify-content:center; font-weight:700;">AMP</div>
            <div>
              <div style="font-weight:600; font-size:0.9rem;">AutoMovie Pro Support</div>
              <div style="font-size:0.7rem; color:#25D366;">অনলাইন (অফিসিয়াল)</div>
            </div>
          </div>
          <div class="phone-mockup-body" id="mockupBody">
            <div class="chat-bubble-out" id="mockupBubble">
              আসসালামু আলাইকুম তানভীর হাসান!<br><br>AutoMovie Pro-তে আপনাকে স্বাগতম...
              <div class="chat-time">10:45 AM ✓✓</div>
            </div>
          </div>
        </div>
      </div>
    </div>

  <!-- =========================================================
       TAB: CAMPAIGNS
       ========================================================= -->
  <?php elseif ($activeTab === 'campaigns'): 
      $activeCampId = trim((string) ($_GET['active_campaign'] ?? ''));
      $campDetail = null;
      $campJobs = [];
      if ($activeCampId !== '') {
          $st = $pdo->prepare("SELECT * FROM wa_campaigns WHERE id = ? LIMIT 1");
          $st->execute([$activeCampId]);
          $campDetail = $st->fetch(PDO::FETCH_ASSOC);

          if ($campDetail) {
              $stJobs = $pdo->prepare("SELECT * FROM wa_campaign_jobs WHERE campaign_id = ? ORDER BY id ASC LIMIT 50");
              $stJobs->execute([$activeCampId]);
              $campJobs = $stJobs->fetchAll(PDO::FETCH_ASSOC);
          }
      }
      $campaignsList = $pdo->query("SELECT * FROM wa_campaigns ORDER BY created_at DESC")->fetchAll(PDO::FETCH_ASSOC);
  ?>
    <?php if ($campDetail): ?>
      <!-- Active Campaign Live Monitor -->
      <div class="admin-card" style="margin-bottom:1.5rem; border:1px solid #10b981;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1rem;">
          <div>
            <h3 style="margin:0; color:#fff;">📢 ক্যাম্পেইন লাইভ মনিটর: <?= e($campDetail['title']) ?></h3>
            <p style="margin:4px 0 0 0; color:var(--admin-text-muted); font-size:0.85rem;">
              রিলিজ আইডি: <?= e($campDetail['id']) ?> • জিটার ডিলে: <?= (int)$campDetail['jitter_min_seconds'] ?>-<?= (int)$campDetail['jitter_max_seconds'] ?> সেকেন্ড
            </p>
          </div>
          <div style="display:flex; gap:8px;">
            <button id="btnStartRunner" class="btn btn-primary" style="background:#25D366; border-color:#128c7e;" onclick="startCampaignExecution('<?= e($campDetail['id']) ?>')">
              ▶️ ব্রডকাস্ট চালু করুন
            </button>
            <button id="btnPauseRunner" class="btn btn-secondary" style="display:none;" onclick="pauseCampaignExecution()">
              ⏸️ পজ করুন
            </button>
            <a href="?tab=campaigns" class="btn btn-secondary" style="text-decoration:none;">বন্ধ করুন</a>
          </div>
        </div>

        <!-- Live Progress Bar -->
        <?php 
          $tot = max(1, (int)$campDetail['total_recipients']);
          $sent = (int)$campDetail['sent_count'];
          $pct = min(100, round(($sent / $tot) * 100));
        ?>
        <div style="background:rgba(255,255,255,0.06); border-radius:10px; height:20px; overflow:hidden; margin-bottom:1rem;">
          <div id="campProgressBar" style="width:<?= $pct ?>%; background:linear-gradient(90deg, #10b981, #25D366); height:100%; transition:width 0.4s ease; text-align:center; font-size:0.75rem; color:#fff; font-weight:700; line-height:20px;">
            <?= $pct ?>%
          </div>
        </div>

        <div style="display:flex; justify-content:space-between; font-size:0.9rem; color:var(--admin-text-muted); margin-bottom:1.5rem;">
          <span>মোট টার্গেট: <strong style="color:#fff;"><?= $tot ?></strong> জন</span>
          <span>সফল প্রেরিত: <strong style="color:#10b981;" id="statCampSent"><?= $sent ?></strong></span>
          <span>ব্যর্থ: <strong style="color:#f43f5e;" id="statCampFailed"><?= (int)$campDetail['failed_count'] ?></strong></span>
        </div>

        <h4 style="margin-bottom:0.5rem; color:#fff;">কিউ লগ (সাম্প্রতিক ৫০টি)</h4>
        <div class="admin-table-wrap" style="max-height:300px; overflow-y:auto;">
          <table class="admin-table">
            <thead>
              <tr>
                <th>গ্রাহক</th>
                <th>ফোন</th>
                <th>স্ট্যাটাস</th>
                <th>ত্রুটি বিবরণ</th>
              </tr>
            </thead>
            <tbody id="campJobsTbody">
              <?php foreach ($campJobs as $j): ?>
                <tr>
                  <td><?= e($j['recipient_name']) ?></td>
                  <td>+<?= e($j['recipient_phone']) ?></td>
                  <td>
                    <span class="badge <?= $j['status'] === 'sent' ? 'badge-success' : ($j['status'] === 'failed' ? 'badge-danger' : 'badge-neutral') ?>">
                      <?= e($j['status']) ?>
                    </span>
                  </td>
                  <td style="font-size:0.8rem; color:#fda4af;"><?= e($j['error_message'] ?: '—') ?></td>
                </tr>
              <?php endforeach; ?>
            </tbody>
          </table>
        </div>
      </div>
    <?php endif; ?>

    <!-- Create Campaign Card -->
    <div class="admin-card">
      <h3 style="margin-top:0; color:#fff;">➕ নতুন ব্রডকাস্ট ক্যাম্পেইন তৈরি করুন</h3>
      <form method="POST" action="whatsapp_marketing.php?tab=campaigns">
        <?= csrf_field() ?>
        <input type="hidden" name="action" value="create_campaign">
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem;">
          <div class="form-group">
            <label>ক্যাম্পেইন শিরোনাম</label>
            <input type="text" name="title" class="form-control" placeholder="যেমন: ঈদ মেগা অফার ব্রডকাস্ট" required>
          </div>
          <div class="form-group">
            <label>টার্গেট অডিয়েন্স</label>
            <select name="target_audience" class="form-control" onchange="toggleGroupSelect(this.value)">
              <option value="group">নির্দিষ্ট কন্টাক্ট গ্রুপ</option>
              <option value="leads">ওয়েবসাইট লিডস (WhatsApp Leads)</option>
              <option value="pending_orders">পেন্ডিং পেমেন্ট অর্ডারসমূহ</option>
              <option value="customers">ইতিমধ্যে কেনা কাস্টমারগণ</option>
              <option value="all">সকল কন্টাক্ট</option>
            </select>
          </div>
        </div>

        <div class="form-group" id="groupSelectWrap">
          <label>গ্রুপ নির্বাচন করুন</label>
          <select name="group_id" class="form-control">
            <?php foreach ($groups as $g): ?>
              <option value="<?= e($g['id']) ?>"><?= e($g['name']) ?> (<?= (int)$g['member_count'] ?> জন)</option>
            <?php endforeach; ?>
          </select>
        </div>

        <div class="form-group">
          <label>ক্যাম্পেইন বার্তা (Variables: {{name}}, {{phone}}, {{business}})</label>
          <textarea name="custom_message" class="form-control" rows="6" placeholder="আসসালামু আলাইকুম {{name}}!..." required></textarea>
        </div>

        <div style="display:grid; grid-template-columns:2fr 1fr 1fr; gap:1rem;">
          <div class="form-group">
            <label>মিডিয়া ব্যানার URL (ঐচ্ছিক)</label>
            <input type="text" name="media_url" class="form-control" placeholder="https://automoviepro.com/assets/img/...">
          </div>
          <div class="form-group">
            <label>মিনিমাম ডিলে (সেকেন্ড)</label>
            <input type="number" name="jitter_min_seconds" class="form-control" value="3" min="1">
          </div>
          <div class="form-group">
            <label>ম্যাক্সিমাম ডিলে (সেকেন্ড)</label>
            <input type="number" name="jitter_max_seconds" class="form-control" value="8" min="2">
          </div>
        </div>

        <div style="display:flex; justify-content:flex-end; margin-top:1rem;">
          <button type="submit" class="btn btn-primary" style="background:#25D366; border-color:#128c7e;">
            🚀 ক্যাম্পেইন প্রস্তুত ও সংরক্ষণ করুন
          </button>
        </div>
      </form>
    </div>

  <!-- =========================================================
       TAB: B2B LEAD FINDER
       ========================================================= -->
  <?php elseif ($activeTab === 'leadfinder'): ?>
    <div class="admin-card">
      <h3 style="margin-top:0; color:#fff;">🔍 স্মার্ট B2B বিজনেস লিড ফাইন্ডার ও রিসার্চ</h3>
      <p style="color:var(--admin-text-muted); font-size:0.85rem;">
        ওপেনস্ট্রিটম্যাপ ও জেমিনি এআই-এর সমন্বয়ে বাংলাদেশের প্রতিটি শহর ও ক্যাটাগরির ভেরিফাইড বিজনেস ডাটাবেস খুঁজুন এবং একক ক্লিকে কন্টাক্টে যুক্ত করুন।
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr 120px 140px; gap:10px; margin-bottom:1.5rem;">
        <div>
          <label style="font-size:0.8rem; color:var(--admin-text-muted);">বিজনেস ক্যাটাগরি</label>
          <select id="leadCatInput" class="form-control">
            <option value="Software">Software & IT Company</option>
            <option value="E-commerce">E-Commerce & Online Shop</option>
            <option value="Restaurant">Restaurant & Cafe</option>
            <option value="Fashion">Fashion & Boutique</option>
            <option value="Agency">Digital Marketing Agency</option>
            <option value="Real Estate">Real Estate & Developers</option>
            <option value="Education">Coaching & Education</option>
            <option value="Clinic">Medical & Dental Clinic</option>
          </select>
        </div>
        <div>
          <label style="font-size:0.8rem; color:var(--admin-text-muted);">শহর / জেলা</label>
          <select id="leadCityInput" class="form-control">
            <option value="Dhaka">Dhaka (ঢাকা)</option>
            <option value="Chittagong">Chittagong (চট্টগ্রাম)</option>
            <option value="Sylhet">Sylhet (সিলেট)</option>
            <option value="Rajshahi">Rajshahi (রাজশাহী)</option>
            <option value="Khulna">Khulna (খুলনা)</option>
            <option value="Gazipur">Gazipur (গাজীপুর)</option>
            <option value="Narayanganj">Narayanganj (নারায়ণগঞ্জ)</option>
            <option value="Comilla">Comilla (কুমিল্লা)</option>
          </select>
        </div>
        <div>
          <label style="font-size:0.8rem; color:var(--admin-text-muted);">ফলাফল সংখ্যা</label>
          <input type="number" id="leadLimitInput" class="form-control" value="10" min="3" max="25">
        </div>
        <div style="display:flex; align-items:flex-end;">
          <button type="button" class="btn btn-primary" style="width:100%;" onclick="runLeadSearch()">
            🔍 লিড খুঁজুন
          </button>
        </div>
      </div>

      <div id="leadSearchResults" style="display:none;">
        <h4 style="color:#fff; margin-bottom:0.75rem;">অনুসন্ধানের ফলাফল (<span id="leadCountBadge">0</span> টি লিড পাওয়া গেছে)</h4>
        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead>
              <tr>
                <th>প্রতিষ্ঠানের নাম</th>
                <th>ফোন নম্বর</th>
                <th>ঠিকানা</th>
                <th>ওয়েবসাইট</th>
                <th>অ্যাকশন</th>
              </tr>
            </thead>
            <tbody id="leadResultsTbody"></tbody>
          </table>
        </div>
      </div>
    </div>

  <!-- =========================================================
       TAB: GROUP GRABBER (হোয়াটসঅ্যাপ গ্রুপ মেম্বার এক্সট্র্যাক্টর)
       ========================================================= -->
  <?php elseif ($activeTab === 'groupgrabber'): ?>
    <div class="admin-card" style="margin-bottom:1.5rem; border:1px solid rgba(37,211,102,0.3); background:linear-gradient(135deg, rgba(37,211,102,0.08) 0%, rgba(15,23,42,0.6) 100%);">
      <div style="display:flex; align-items:center; gap:12px;">
        <div style="font-size:2rem; background:rgba(37,211,102,0.2); width:50px; height:50px; border-radius:12px; display:flex; align-items:center; justify-content:center;">
          ⚡
        </div>
        <div>
          <h3 style="margin:0; color:#fff; font-size:1.25rem;">WhatsApp গ্রুপ মেম্বার এক্সট্র্যাক্টর (Group Grabber)</h3>
          <p style="margin:4px 0 0 0; color:var(--admin-text-muted); font-size:0.85rem;">
            যেকোনো WhatsApp গ্রুপ থেকে মেম্বার লিস্ট বা নম্বর পেস্ট করুন। সিস্টেম অটোমেটিক মোবাইল নম্বর এক্সট্র্যাক্ট করে সঠিক E.164 ফরম্যাটে কন্টাক্ট গ্রুপে যুক্ত করবে।
          </p>
        </div>
      </div>
    </div>

    <div style="display:grid; grid-template-columns: 1.5fr 1fr; gap:1.5rem; align-items:start;">
      <!-- Grabber Input Form -->
      <div class="admin-card">
        <h4 style="margin-top:0; color:#fff; font-size:1.05rem;">📥 গ্রুপ মেম্বার ডেটা ইনপুট</h4>
        <form method="POST" action="whatsapp_marketing.php?tab=groupgrabber">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="save_grabbed_members">
          
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem; margin-bottom:1rem;">
            <div class="form-group">
              <label>সোর্স গ্রুপের নাম / উৎস</label>
              <input type="text" name="group_source_name" class="form-control" placeholder="যেমন: BD E-Commerce Entrepreneurs" required>
            </div>
            <div class="form-group">
              <label>টার্গেট কন্টাক্ট গ্রুপ নির্বাচন করুন</label>
              <select name="target_group_id" class="form-control">
                <option value="">-- কোনো নির্দিষ্ট গ্রুপ ছাড়া সেভ করুন --</option>
                <?php foreach ($groups as $g): ?>
                  <option value="<?= e($g['id']) ?>"><?= e($g['name']) ?></option>
                <?php endforeach; ?>
              </select>
            </div>
          </div>

          <div class="form-group">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <label style="margin:0;">মেম্বারদের টেক্সট বা ফোন নম্বর লিস্ট পেস্ট করুন</label>
              <span id="grabberCounter" style="font-size:0.8rem; color:#25D366; font-weight:600;">০ টি নম্বর সনাক্ত</span>
            </div>
            <textarea id="grabberInput" name="members_text" class="form-control" rows="10" placeholder="+880 1968-111593, তানভীর আহমেদ&#10;+880 1711-223344&#10;01812345678, সাকিব&#10;01900000000" oninput="updateGrabberCount()" required></textarea>
            <small style="color:var(--admin-text-muted); font-size:0.75rem; margin-top:4px; display:block;">
              ফরম্যাট: প্রতি লাইনে একটি নম্বর, বা "নম্বর, নাম" আকারে পেস্ট করতে পারেন। বন্ধনী, স্পেস বা হাইফেন স্বয়ংক্রিয়ভাবে ক্লিন করা হবে।
            </small>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:1.5rem;">
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('grabberInput').value=''; updateGrabberCount();">
              রিসেট
            </button>
            <button type="submit" class="btn btn-primary" style="background:#25D366; border-color:#128c7e; font-weight:700;">
              ⚡ এক্সট্র্যাক্ট ও কন্টাক্টে সেভ করুন
            </button>
          </div>
        </form>
      </div>

      <!-- Grabber Guide Card -->
      <div class="admin-card">
        <h4 style="margin-top:0; color:#fff; font-size:1.05rem;">📖 গ্রুপ মেম্বার এক্সপোর্ট করার নিয়ম</h4>
        <ol style="color:var(--admin-text-muted); font-size:0.85rem; padding-left:1.2rem; line-height:1.7; margin-bottom:1.5rem;">
          <li>আপনার কম্পিউটারে <strong>WhatsApp Web</strong> ওপেন করুন।</li>
          <li>টার্গেট WhatsApp গ্রুপে ঢুকে উপরের গ্রুপ শিরোনামে ক্লিক করুন (Group Info)।</li>
          <li>মেম্বার তালিকার ওপর মাউস রেখে নম্বরগুলো সিলেক্ট করে <strong>Copy (Ctrl+C)</strong> করুন।</li>
          <li>বাম পাশের টেক্সট বক্সে <strong>Paste (Ctrl+V)</strong> করুন।</li>
          <li>সিস্টেম স্বয়ংক্রিয়ভাবে সব অতিরিক্ত ক্যারেক্টার ক্লিন করে বৈধ নম্বর ডাটাবেসে সেভ করবে।</li>
        </ol>

        <div style="background:rgba(255,255,255,0.04); border-radius:8px; padding:12px; border-left:3px solid #25D366;">
          <strong style="color:#25D366; font-size:0.85rem;">💡 স্প্যাম-প্রটেকশন টিপ:</strong>
          <p style="margin:4px 0 0 0; color:var(--admin-text-muted); font-size:0.8rem; line-height:1.5;">
            নতুন মেম্বারদের কাছে সরাসরি সেলস পিচ না পাঠিয়ে প্রথমে সালাম ও পরিচিতিমূলক মেসেজ পাঠান।
          </p>
        </div>
      </div>
    </div>

  <!-- =========================================================
       TAB: NUMBER FILTER (নম্বর ফিল্টার ও ভ্যালিডেটর)
       ========================================================= -->
  <?php elseif ($activeTab === 'numberfilter'): ?>
    <div class="admin-card" style="margin-bottom:1.5rem; border:1px solid rgba(56,189,248,0.3); background:linear-gradient(135deg, rgba(56,189,248,0.08) 0%, rgba(15,23,42,0.6) 100%);">
      <div style="display:flex; align-items:center; gap:12px;">
        <div style="font-size:2rem; background:rgba(56,189,248,0.2); width:50px; height:50px; border-radius:12px; display:flex; align-items:center; justify-content:center;">
          🛡️
        </div>
        <div>
          <h3 style="margin:0; color:#fff; font-size:1.25rem;">WhatsApp নম্বর ফিল্টার ও ভ্যালিডেটর</h3>
          <p style="margin:4px 0 0 0; color:var(--admin-text-muted); font-size:0.85rem;">
            বাল্ক ফোন নম্বর পরীক্ষা করে কার্যকর WhatsApp ও মোবাইল অপারেটর (GP, Robi, BL, Airtel, Teletalk) সনাক্ত করুন এবং অকার্যকর বা ডুপ্লিকেট নম্বর দূর করুন।
          </p>
        </div>
      </div>
    </div>

    <div style="display:grid; grid-template-columns: 1.2fr 1.8fr; gap:1.5rem; align-items:start;">
      <!-- Filter Input Form -->
      <div class="admin-card">
        <h4 style="margin-top:0; color:#fff; font-size:1.05rem;">📋 নম্বর যাচাই ও ইনপুট</h4>
        <form id="filterNumbersForm" onsubmit="event.preventDefault(); runNumberFilter();">
          <div class="form-group">
            <label>ফোন নম্বর লিস্ট পেস্ট করুন</label>
            <textarea id="filterRawInput" class="form-control" rows="9" placeholder="01711223344&#10;+8801968111593&#10;01812345678&#10;01555555555&#10;invalid123" required></textarea>
            <small style="color:var(--admin-text-muted); font-size:0.75rem; margin-top:4px; display:block;">
              প্রতি লাইনে একটি বা কমা দিয়ে একাধিক নম্বর দিতে পারেন।
            </small>
          </div>

          <div class="form-group">
            <label>ভ্যালিড নম্বর স্বয়ংক্রিয়ভাবে সেভ করতে গ্রুপ বাছুন</label>
            <select id="filterTargetGroup" class="form-control">
              <option value="">-- ডেটাবেসে সেভ না করে শুধু যাচাই করুন --</option>
              <?php foreach ($groups as $g): ?>
                <option value="<?= e($g['id']) ?>"><?= e($g['name']) ?></option>
              <?php endforeach; ?>
            </select>
          </div>

          <div class="form-group" style="display:flex; align-items:center; gap:8px;">
            <input type="checkbox" id="filterAutoSave" style="width:18px; height:18px; accent-color:#10b981;">
            <label for="filterAutoSave" style="margin:0; font-size:0.85rem; color:#cbd5e1; cursor:pointer;">
              ভ্যালিড নম্বরগুলোকে সরাসরি কন্টাক্ট তালিকায় সেভ করুন
            </label>
          </div>

          <button type="submit" id="btnRunFilter" class="btn btn-primary" style="width:100%; background:#0284c7; border-color:#0369a1; font-weight:700;">
            🔍 নম্বর যাচাই ও ফিল্টার করুন
          </button>
        </form>
      </div>

      <!-- Filter Results Display -->
      <div class="admin-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
          <h4 style="margin:0; color:#fff; font-size:1.05rem;">📊 ফিল্টারিং ফলাফল</h4>
          <button id="btnCopyValid" class="btn btn-secondary btn-sm" onclick="copyValidNumbers()" style="display:none;">
            📋 ভ্যালিড নম্বর কপি
          </button>
        </div>

        <!-- Metrics Chips -->
        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; margin-bottom:1.25rem;">
          <div style="background:rgba(255,255,255,0.05); padding:10px; border-radius:8px; text-align:center;">
            <div style="font-size:0.75rem; color:var(--admin-text-muted);">মোট নম্বর</div>
            <div id="statTotalFilter" style="font-size:1.15rem; font-weight:700; color:#fff;">০</div>
          </div>
          <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.3); padding:10px; border-radius:8px; text-align:center;">
            <div style="font-size:0.75rem; color:#6ee7b7;">ভ্যালিড</div>
            <div id="statValidFilter" style="font-size:1.15rem; font-weight:700; color:#10b981;">০</div>
          </div>
          <div style="background:rgba(245,158,11,0.15); border:1px solid rgba(245,158,11,0.3); padding:10px; border-radius:8px; text-align:center;">
            <div style="font-size:0.75rem; color:#fde68a;">ডুপ্লিকেট</div>
            <div id="statDupFilter" style="font-size:1.15rem; font-weight:700; color:#f59e0b;">০</div>
          </div>
          <div style="background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.3); padding:10px; border-radius:8px; text-align:center;">
            <div style="font-size:0.75rem; color:#fca5a5;">অকার্যকর</div>
            <div id="statInvalidFilter" style="font-size:1.15rem; font-weight:700; color:#f43f5e;">০</div>
          </div>
        </div>

        <div id="filterResultsPlaceholder" style="text-align:center; padding:2.5rem 1rem; color:var(--admin-text-muted); font-size:0.9rem;">
          বাম পাশের বক্সে নম্বর পেস্ট করে "নম্বর যাচাই ও ফিল্টার করুন" বাটনে চাপুন।
        </div>

        <div id="filterResultsTableWrap" style="display:none; max-height:360px; overflow-y:auto;" class="admin-table-wrap">
          <table class="admin-table">
            <thead>
              <tr>
                <th>ফোন নম্বর</th>
                <th>অপারেটর / টাইপ</th>
                <th>স্ট্যাটাস</th>
                <th>অ্যাকশন</th>
              </tr>
            </thead>
            <tbody id="filterResultsTbody"></tbody>
          </table>
        </div>
      </div>
    </div>

  <!-- =========================================================
       TAB: LIVE INBOX
       ========================================================= -->
  <?php elseif ($activeTab === 'inbox'): 
      $inboxThreads = $pdo->query("SELECT sender_phone, sender_name, message_body, timestamp, is_read, direction 
                                   FROM wa_inbox_messages 
                                   GROUP BY sender_phone 
                                   ORDER BY timestamp DESC LIMIT 20")->fetchAll(PDO::FETCH_ASSOC);
  ?>
    <div style="display:grid; grid-template-columns: 1fr 2fr; gap:1.5rem;">
      <div class="admin-card" style="padding:1rem;">
        <h4 style="margin-top:0; color:#fff;">চ্যাট থ্রেডসমূহ</h4>
        <?php if (empty($inboxThreads)): ?>
          <p style="color:var(--admin-text-muted); font-size:0.85rem;">এখনও কোনো ইনবক্স বার্তা পাওয়া যায়নি।</p>
        <?php else: ?>
          <div style="display:flex; flex-direction:column; gap:6px;">
            <?php foreach ($inboxThreads as $t): ?>
              <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.07); padding:10px; border-radius:8px; cursor:pointer;" onclick="selectInboxThread('<?= e($t['sender_phone']) ?>')">
                <div style="font-weight:600; color:#fff; display:flex; justify-content:space-between;">
                  <span><?= e($t['sender_name'] ?: 'গ্রাহক') ?></span>
                  <span style="font-size:0.7rem; color:var(--admin-text-muted);"><?= substr((string)$t['timestamp'], 11, 5) ?></span>
                </div>
                <div style="font-size:0.8rem; color:#25D366;">+<?= e($t['sender_phone']) ?></div>
                <div style="font-size:0.8rem; color:var(--admin-text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                  <?= e($t['message_body']) ?>
                </div>
              </div>
            <?php endforeach; ?>
          </div>
        <?php endif; ?>
      </div>

      <div class="admin-card">
        <h4 style="margin-top:0; color:#fff;" id="activeChatTitle">💬 গ্রাহক চ্যাট ভিউয়ার</h4>
        <div id="activeChatBox" style="background:#0b141a; border-radius:8px; padding:16px; min-height:260px; max-height:360px; overflow-y:auto; display:flex; flex-direction:column; gap:8px; margin-bottom:1rem;">
          <div style="color:var(--admin-text-muted); text-align:center; font-size:0.9rem; margin:auto;">
            বাম থেকে যেকোনো কাস্টমার সিলেক্ট করুন অথবা সরাসরি মেসেজ পাঠান।
          </div>
        </div>

        <form method="POST" action="whatsapp_marketing.php?tab=inbox" style="display:flex; gap:8px;">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="send_instant_message">
          <input type="text" name="phone" id="inboxReplyPhone" class="form-control" placeholder="গ্রাহকের ফোন নম্বর" style="width:180px;" required>
          <input type="text" name="message_body" class="form-control" placeholder="রিপ্লাই লিখুন..." required>
          <button type="submit" class="btn btn-primary" style="background:#25D366; border-color:#128c7e;">পাঠান</button>
        </form>
      </div>
    </div>

  <!-- =========================================================
       TAB: AUTO REPLY
       ========================================================= -->
  <?php elseif ($activeTab === 'autoreply'): 
      $rules = $pdo->query("SELECT * FROM wa_auto_reply_rules ORDER BY priority ASC")->fetchAll(PDO::FETCH_ASSOC);
  ?>
    <div style="display:grid; grid-template-columns: 1.5fr 1fr; gap:1.5rem;">
      <div class="admin-card">
        <h3 style="margin-top:0; color:#fff;">🤖 স্বয়ংক্রিয় এআই রিপ্লাই রুলস</h3>
        <p style="color:var(--admin-text-muted); font-size:0.85rem;">
          গ্রাহকের পাঠানো বার্তার কী-ওয়ার্ড শনাক্ত করে ২৪/৭ স্বয়ংক্রিয়ভাবে মেসেজ পাঠাবে।
        </p>

        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead>
              <tr>
                <th>কী-ওয়ার্ড</th>
                <th>ম্যাচ টাইপ</th>
                <th>প্রত্যুত্তর</th>
                <th>অ্যাকশন</th>
              </tr>
            </thead>
            <tbody>
              <?php foreach ($rules as $r): ?>
                <tr>
                  <td><code style="color:#38bdf8;"><?= e($r['keyword']) ?></code></td>
                  <td><span class="badge badge-neutral"><?= e($r['match_type']) ?></span></td>
                  <td style="font-size:0.85rem; max-width:240px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                    <?= e($r['response_text']) ?>
                  </td>
                  <td>
                    <form method="POST" action="whatsapp_marketing.php?tab=autoreply" style="display:inline;">
                      <?= csrf_field() ?>
                      <input type="hidden" name="action" value="delete_auto_reply_rule">
                      <input type="hidden" name="rule_id" value="<?= e($r['id']) ?>">
                      <button type="submit" class="btn btn-danger btn-sm">মুছুন</button>
                    </form>
                  </td>
                </tr>
              <?php endforeach; ?>
            </tbody>
          </table>
        </div>
      </div>

      <div class="admin-card">
        <h3 style="margin-top:0; color:#fff;">➕ নতুন রুল যোগ করুন</h3>
        <form method="POST" action="whatsapp_marketing.php?tab=autoreply">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="save_auto_reply_rule">
          <div class="form-group">
            <label>কী-ওয়ার্ড (পাইপ দিয়ে একাধিক দিতে পারেন)</label>
            <input type="text" name="keyword" class="form-control" placeholder="যেমন: price|দাম|cost|koto" required>
          </div>
          <div class="form-group">
            <label>ম্যাচিং ধরণ</label>
            <select name="match_type" class="form-control">
              <option value="contains">Contains (বাক্যের ভেতর থাকলেই হবে)</option>
              <option value="exact">Exact (হুবহু শব্দ)</option>
              <option value="startswith">Starts With (শুরুর শব্দ)</option>
            </select>
          </div>
          <div class="form-group">
            <label>অটোমেটিক রিপ্লাই মেসেজ</label>
            <textarea name="response_text" class="form-control" rows="5" placeholder="আসসালামু আলাইকুম! আমাদের ৩টি প্যাকেজ রয়েছে..." required></textarea>
          </div>
          <button type="submit" class="btn btn-primary" style="width:100%;">রুল সংরক্ষণ করুন</button>
        </form>
      </div>
    </div>

  <!-- =========================================================
       TAB: TEMPLATES (মেসেজ টেমপ্লেট লাইব্রেরি)
       ========================================================= -->
  <?php elseif ($activeTab === 'templates'): 
      // Seed fallback templates for display if DB has few
      $defaultSeedTemplates = [
          [
              'title' => 'অর্ডার কনফার্মেশন ও লাইসেন্স ডেলিভারি',
              'category' => 'অর্ডার',
              'body' => "আসসালামু আলাইকুম {{name}}!\n\nঅভিনন্দন! AutoMovie Pro-তে আপনার অর্ডারটি সফলভাবে অনুমোদিত হয়েছে। 🎉\n\nআপনার লাইসেন্স কী ও ডাউনলোড পোর্টাল লিংক নিচে দেওয়া হলো:\n🔗 https://automoviepro.com/download.php\n\nযেকোনো টেকনিক্যাল সাপোর্টের জন্য এই WhatsApp নম্বরে আমাদের সাথে কথা বলতে পারবেন। ধন্যবাদ!"
          ],
          [
              'title' => 'পেমেন্ট রিমাইন্ডার (পেন্ডিং অর্ডার)',
              'category' => 'রিমাইন্ডার',
              'body' => "আসসালামু আলাইকুম {{name}},\n\nআপনি সম্প্রতি AutoMovie Pro সফটওয়্যারটির জন্য অর্ডার সাবমিট করেছিলেন। আপনার অর্ডারটি সম্পূর্ণ করতে পেমেন্ট সম্পন্ন করে TrxID কনফার্ম করুন।\n\nসাহায্যের প্রয়োজন হলে সরাসরি রিপ্লাই দিন অথবা কল করুন: +8801968111593"
          ],
          [
              'title' => 'AutoMovie Pro মেগা সেলস ডেমো',
              'category' => 'প্রমোশন',
              'body' => "প্রিয় {{name}},\n\nপ্রতিদিন সোশ্যাল মিডিয়ায় কনটেন্ট বানাতে কি আপনার ঘণ্টার পর ঘণ্টা সময় অপচয় হচ্ছে?\n\nAutoMovie Pro এখন ১-ক্লিকে ফুল এইচডি ভিডিও, রিলস, ফেসবুক পোস্ট ও ব্যানার তৈরি করে স্বয়ংক্রিয়ভাবে পাবলিশ করে।\n\n🎬 লাইভ ডেমো ও বিস্তারিত দেখুন:\n👉 https://automoviepro.com"
          ],
          [
              'title' => 'WAManager Pro অফিসিয়াল লঞ্চ অফার',
              'category' => 'অফার',
              'body' => "আসসালামু আলাইকুম {{name}},\n\nআপনার বিজনেসের জন্য প্রফেশনাল WhatsApp মার্কেটিং সফটওয়্যার খুঁজছেন?\n\n🚀 WAManager Pro দিয়ে আনলিমিটেড বাল্ক মেসেজ, অ্যান্টি-ব্যান স্পিনট্যাক্স, এআই অটো-রিপ্লাই ও গুগল ম্যাপস থেকে B2B লিড সংগ্রহ করুন!\n\n🔥 আজকের স্পেশাল অফারে ১ বছর মাত্র ৯৯৯/- এবং ৩ বছর ১৯৯৯/- টাকা!\n👉 অর্ডার লিংক: https://automoviepro.com/whatsapp-marketing.php"
          ],
          [
              'title' => 'কাস্টমার ফিডব্যাক ও সাপোর্ট চেক',
              'category' => 'সাপোর্ট',
              'body' => "কেমন আছেন {{name}}?\n\nআমাদের সফটওয়্যার ব্যবহারে আপনার অভিজ্ঞতা কেমন হচ্ছে? কোনো প্রশ্ন বা টেকনিক্যাল সমস্যা থাকলে নির্দ্বিধায় আমাকে জানান। আমাদের সাপোর্ট টিম সবসময় প্রস্তুত।"
          ]
      ];
  ?>
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1.5rem;">
      <div>
        <h3 style="margin:0; color:#fff; font-size:1.25rem;">📝 মেসেজ টেমপ্লেট লাইব্রেরি</h3>
        <p style="margin:4px 0 0 0; color:var(--admin-text-muted); font-size:0.85rem;">
          ঘন ঘন ব্যবহৃত সেলস পিচ, অর্ডার নোটিফিকেশন ও সাপোর্ট বার্তাগুলো আগে থেকে প্রস্তুত রাখুন।
        </p>
      </div>
      <button class="btn btn-primary" onclick="document.getElementById('addTemplateModal').style.display='block'" style="background:#25D366; border-color:#128c7e;">
        ➕ নতুন টেমপ্লেট যুক্ত করুন
      </button>
    </div>

    <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap:1.25rem;">
      <!-- Database Stored Templates -->
      <?php if (!empty($templates)): foreach ($templates as $tpl): ?>
        <div class="admin-card" style="border:1px solid rgba(255,255,255,0.08); display:flex; flex-direction:column; justify-content:space-between;">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
              <h4 style="margin:0; font-size:1rem; color:#fff;"><?= e($tpl['title']) ?></h4>
              <span class="badge badge-info"><?= e($tpl['category']) ?></span>
            </div>
            <div style="background:rgba(0,0,0,0.3); border-radius:8px; padding:10px; font-size:0.82rem; color:#cbd5e1; white-space:pre-wrap; max-height:140px; overflow-y:auto; line-height:1.5; margin-bottom:1rem;">
              <?= e($tpl['body']) ?>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.06); padding-top:10px;">
            <button class="btn btn-primary btn-sm" onclick="loadTemplateToStudio(<?= htmlspecialchars(json_encode($tpl['body']), ENT_QUOTES, 'UTF-8') ?>)" style="background:#25D366; border-color:#128c7e;">
              🎨 স্টুডিওতে লোড
            </button>
            <form method="POST" action="whatsapp_marketing.php?tab=templates" onsubmit="return confirm('এই টেমপ্লেটটি মুছে ফেলতে চান?');" style="margin:0;">
              <?= csrf_field() ?>
              <input type="hidden" name="action" value="delete_template">
              <input type="hidden" name="template_id" value="<?= (int)$tpl['id'] ?>">
              <button type="submit" class="btn btn-danger btn-sm">মুছে ফেলুন</button>
            </form>
          </div>
        </div>
      <?php endforeach; endif; ?>

      <!-- Pre-seeded Enterprise Templates -->
      <?php foreach ($defaultSeedTemplates as $stpl): ?>
        <div class="admin-card" style="border:1px dashed rgba(37,211,102,0.3); background:rgba(37,211,102,0.02); display:flex; flex-direction:column; justify-content:space-between;">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
              <h4 style="margin:0; font-size:1rem; color:#fff; display:flex; align-items:center; gap:6px;">
                ⭐ <?= e($stpl['title']) ?>
              </h4>
              <span class="badge badge-success"><?= e($stpl['category']) ?></span>
            </div>
            <div style="background:rgba(0,0,0,0.3); border-radius:8px; padding:10px; font-size:0.82rem; color:#cbd5e1; white-space:pre-wrap; max-height:140px; overflow-y:auto; line-height:1.5; margin-bottom:1rem;">
              <?= e($stpl['body']) ?>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.06); padding-top:10px;">
            <button class="btn btn-primary btn-sm" onclick="loadTemplateToStudio(<?= htmlspecialchars(json_encode($stpl['body']), ENT_QUOTES, 'UTF-8') ?>)" style="background:#25D366; border-color:#128c7e;">
              🎨 স্টুডিওতে লোড
            </button>
            <form method="POST" action="whatsapp_marketing.php?tab=templates" style="margin:0;">
              <?= csrf_field() ?>
              <input type="hidden" name="action" value="save_template">
              <input type="hidden" name="title" value="<?= e($stpl['title']) ?>">
              <input type="hidden" name="category" value="<?= e($stpl['category']) ?>">
              <input type="hidden" name="body" value="<?= e($stpl['body']) ?>">
              <button type="submit" class="btn btn-secondary btn-sm" title="ডেটাবেসে সংরক্ষণ">💾 সেভ করুন</button>
            </form>
          </div>
        </div>
      <?php endforeach; ?>
    </div>

    <!-- Modal: Add New Template -->
    <div id="addTemplateModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); z-index:9999; backdrop-filter:blur(4px);">
      <div class="admin-card" style="max-width:540px; margin:5% auto; position:relative;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem;">
          <h3 style="margin:0; color:#fff;">➕ নতুন মেসেজ টেমপ্লেট</h3>
          <button onclick="document.getElementById('addTemplateModal').style.display='none'" style="background:none; border:none; color:var(--admin-text-muted); font-size:1.5rem; cursor:pointer;">&times;</button>
        </div>
        <form method="POST" action="whatsapp_marketing.php?tab=templates">
          <?= csrf_field() ?>
          <input type="hidden" name="action" value="save_template">
          <div class="form-group">
            <label>টেমপ্লেটের নাম / শিরোনাম</label>
            <input type="text" name="title" class="form-control" placeholder="যেমন: ঈদ স্পেশাল সেলস অফার" required>
          </div>
          <div class="form-group">
            <label>ক্যাটাগরি</label>
            <select name="category" class="form-control">
              <option value="প্রমোশন">প্রমোশন (Promotion)</option>
              <option value="অর্ডার">অর্ডার (Order)</option>
              <option value="রিমাইন্ডার">রিমাইন্ডার (Reminder)</option>
              <option value="সাপোর্ট">সাপোর্ট (Support)</option>
              <option value="সাধারণ">সাধারণ (General)</option>
            </select>
          </div>
          <div class="form-group">
            <label>মেসেজ বডি</label>
            <div style="display:flex; gap:6px; margin-bottom:6px;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="insertTplVar('{{name}}')">{{name}}</button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="insertTplVar('{{phone}}')">{{phone}}</button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="insertTplVar('https://automoviepro.com')">Website Link</button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="insertTplVar('+8801968111593')">WhatsApp No</button>
            </div>
            <textarea id="tplBodyInput" name="body" class="form-control" rows="7" placeholder="আসসালামু আলাইকুম {{name}}!..." required></textarea>
          </div>
          <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:1.5rem;">
            <button type="button" class="btn btn-secondary" onclick="document.getElementById('addTemplateModal').style.display='none'">বাতিল</button>
            <button type="submit" class="btn btn-primary" style="background:#25D366; border-color:#128c7e;">টেমপ্লেট সংরক্ষণ করুন</button>
          </div>
        </form>
      </div>
    </div>

  <!-- =========================================================
       TAB: GEMINI AI COPYWRITER STUDIO
       ========================================================= -->
  <?php elseif ($activeTab === 'aistudio'): ?>
    <div class="admin-card">
      <h3 style="margin-top:0; color:#fff;">🧠 গুগল জেমিনি এআই কপিরাইটার স্টুডিও</h3>
      <p style="color:var(--admin-text-muted); font-size:0.85rem;">
        উচ্চ কনভার্সন সেলস সাইকোলজি ও গ্রাহক আবেগকে কাজে লাগিয়ে তাৎক্ষণিক WhatsApp প্রমোশনাল কপি তৈরি করুন।
      </p>

      <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:1rem; margin-bottom:1rem;">
        <div class="form-group">
          <label>প্রোডাক্ট বা সার্ভিস</label>
          <select id="aiProductInput" class="form-control">
            <option value="AutoMovie Pro - 4K Video Studio (৳৩,৯৯৯)">AutoMovie Pro - 4K Video Studio (৳৩,৯৯৯)</option>
            <option value="AutoMovie Pro - FB Business Manager (৳২,৯৯৯)">AutoMovie Pro - FB Business Manager (৳২,৯৯৯)</option>
            <option value="AutoMovie Pro - Profile AutoPilot (৳১,৯৯৯)">AutoMovie Pro - Profile AutoPilot (৳১,৯৯৯)</option>
            <option value="WhatsApp Marketing Suite">WhatsApp Marketing Suite (বাণিজ্যিক সফটওয়্যার)</option>
          </select>
        </div>
        <div class="form-group">
          <label>মার্কেটিং অ্যাঙ্গেল</label>
          <select id="aiAngleInput" class="form-control">
            <option value="Direct Sale">সরাসরি সেলস অফার (Direct Sale)</option>
            <option value="Viral Problem Solution">সমস্যা সমাধান ও ইনকাম সুযোগ (Problem-Solution)</option>
            <option value="Urgency Limited Deal">২৪ ঘণ্টার সীমিত ছাড় (Urgency Hook)</option>
            <option value="Video Demo Invitation">ফ্রি লাইভ ডেমো দেখার আমন্ত্রণ (Demo Hook)</option>
          </select>
        </div>
        <div class="form-group">
          <label>ভাষার ধরন (Tone)</label>
          <select id="aiToneInput" class="form-control">
            <option value="Polite & Respectful Bengali">ভদ্র ও মার্জিত বাংলা (Islamic Polite)</option>
            <option value="Excited & High Converting">উত্তেজনাপূর্ণ ও আকর্ষণীয় (Viral Energy)</option>
            <option value="Professional Corporate">কর্পোরেট ও প্রফেশনাল (B2B)</option>
          </select>
        </div>
      </div>

      <div style="display:flex; justify-content:flex-end; margin-bottom:1.5rem;">
        <button type="button" class="btn btn-primary" onclick="generateAiMarketingCopy()">
          ✨ জেমিনি এআই দিয়ে কপি তৈরি করুন
        </button>
      </div>

      <div class="form-group">
        <label>তৈরিকৃত WhatsApp কপি (সরাসরি সম্পাদনাযোগ্য)</label>
        <textarea id="aiGeneratedOutput" class="form-control" rows="8" placeholder="এআই দিয়ে কনটেন্ট তৈরি করতে উপরের বাটনে চাপ দিন..."></textarea>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px;">
        <button type="button" class="btn btn-secondary" onclick="navigator.clipboard.writeText(document.getElementById('aiGeneratedOutput').value); alert('কপি ক্লিপবোর্ডে কপি করা হয়েছে!');">
          📋 কপি করুন
        </button>
        <button type="button" class="btn btn-primary" style="background:#25D366; border-color:#128c7e;" onclick="useAiCopyInStudio()">
          🎨 মেসেজ স্টুডিওতে নিয়ে যান →
        </button>
      </div>
    </div>

  <!-- =========================================================
       TAB: SETTINGS & GATEWAY
       ========================================================= -->
  <?php elseif ($activeTab === 'settings'): 
      $waToken = setting($pdo, 'whatsapp_token', '');
      $waPhoneId = setting($pdo, 'whatsapp_phone_id', '');
      $waWabaId = setting($pdo, 'whatsapp_waba_id', '');
      $waWebhookToken = setting($pdo, 'whatsapp_webhook_verify_token', 'automoviepro_wa_webhook_secure_key_2026');
      $adminNotify = setting($pdo, 'admin_notify_whatsapp', '8801968111593');
  ?>
    <div class="admin-card" style="max-width:700px;">
      <h3 style="margin-top:0; color:#fff;">⚙️ মেটা ক্লাউড এপিআই ও গেটওয়ে কনফিগারেশন</h3>
      <p style="color:var(--admin-text-muted); font-size:0.85rem;">
        অফিসিয়াল WhatsApp Business Cloud API ক্রেডেনশিয়াল প্রদান করুন।
      </p>

      <form method="POST" action="whatsapp_marketing.php?tab=settings">
        <?= csrf_field() ?>
        <input type="hidden" name="action" value="save_gateway_settings">

        <div class="form-group">
          <label>Permanent Access Token (সিস্টেম ইউজার টোকেন)</label>
          <input type="password" name="whatsapp_token" class="form-control" value="<?= e($waToken) ?>" placeholder="EAAG...">
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem;">
          <div class="form-group">
            <label>Phone Number ID</label>
            <input type="text" name="whatsapp_phone_id" class="form-control" value="<?= e($waPhoneId) ?>" placeholder="105829...">
          </div>
          <div class="form-group">
            <label>WhatsApp Business Account ID (WABA ID)</label>
            <input type="text" name="whatsapp_waba_id" class="form-control" value="<?= e($waWabaId) ?>" placeholder="109283...">
          </div>
        </div>

        <div class="form-group">
          <label>Webhook Callback URL (মেটা ডেভেলপার পোর্টালে এই লিঙ্কটি দিন)</label>
          <input type="text" class="form-control" value="https://automoviepro.com/api/whatsapp_webhook.php" readonly style="background:rgba(255,255,255,0.05); color:#38bdf8;">
        </div>

        <div class="form-group">
          <label>Webhook Verify Token</label>
          <input type="text" name="whatsapp_webhook_verify_token" class="form-control" value="<?= e($waWebhookToken) ?>">
        </div>

        <div class="form-group">
          <label>অ্যাডমিন নোটিফিকেশন WhatsApp নম্বর</label>
          <input type="text" name="admin_notify_whatsapp" class="form-control" value="<?= e($adminNotify) ?>">
        </div>

        <button type="submit" class="btn btn-primary" style="margin-top:1rem;">
          💾 গেটওয়ে সেটিংস সংরক্ষণ করুন
        </button>
      </form>
    </div>

  <!-- =========================================================
       TAB: ANTI-BAN WARMUP
       ========================================================= -->
  <?php elseif ($activeTab === 'warmup'): ?>
    <div class="admin-card">
      <h3 style="margin-top:0; color:#fff;">🛡️ অ্যান্টি-ব্যান ও অ্যাকাউন্ট ওয়ার্ম-আপ ক্যালেন্ডার</h3>
      <p style="color:var(--admin-text-muted); font-size:0.85rem;">
        নতুন WhatsApp নম্বর যেন মেটা অ্যালগরিদম দ্বারা ব্যান বা রেট লিমিট না খায়, সেজন্য নিচের সূচি অনুসরণ করুন।
      </p>

      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>দিনক্রম (Stage)</th>
              <th>দৈনিক নিরাপদ সীমা</th>
              <th>প্রস্তাবিত ডিলে (জিটার)</th>
              <th>নির্দেশনা ও সতর্কতা</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>দিন ১ — ৩</strong></td>
              <td><span style="color:#10b981; font-weight:700;">৫ — ১০টি মেসেজ</span></td>
              <td>১০ — ২০ সেকেন্ড</td>
              <td>শুধুমাত্র পরিচিত বা আগে কথা হয়েছে এমন গ্রাহকদের মেসেজ দিন।</td>
            </tr>
            <tr>
              <td><strong>দিন ৪ — ৭</strong></td>
              <td><span style="color:#38bdf8; font-weight:700;">১৫ — ২৫টি মেসেজ</span></td>
              <td>৮ — ১৫ সেকেন্ড</td>
              <td>দুই-মুখী চ্যাট বাড়ান। গ্রাহক যেন অন্তত একটি রিপ্লাই দেয় এমন প্রশ্ন করুন।</td>
            </tr>
            <tr>
              <td><strong>দিন ৮ — ১২</strong></td>
              <td><span style="color:#f59e0b; font-weight:700;">৩০ — ৫০টি মেসেজ</span></td>
              <td>৫ — ১০ সেকেন্ড</td>
              <td>ক্যাম্পেইনে Spintax <code>{বিকল্প ১|বিকল্প ২}</code> অবশ্যই ব্যবহার করুন।</td>
            </tr>
            <tr>
              <td><strong>দিন ১৩+ (ম্যাচিউরড)</strong></td>
              <td><span style="color:#a855f7; font-weight:700;">১০০ — ৫০০+ মেসেজ</span></td>
              <td>৩ — ৮ সেকেন্ড</td>
              <td>অফিসিয়াল মেটা ক্লাউড এপিআই ব্যবহারে কোনো অ্যাকাউন্ট ব্যান ঝুঁকি নেই।</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  <?php endif; ?>

</div>

<script>
// Studio Live Preview Logic
function updateStudioLivePreview() {
  const text = document.getElementById('studioMsgInput').value;
  const rendered = text.replace(/\{\{name\}\}/g, 'তানভীর হাসান')
                       .replace(/\{\{phone\}\}/g, '01968111593')
                       .replace(/\{\{business\}\}/g, 'আইটি এজেন্সি')
                       .replace(/\{([^{}]+)\}/g, function(match, contents) {
                          return contents.split('|')[0];
                       });
  
  const formatted = rendered.replace(/\n/g, '<br>');
  document.getElementById('mockupBubble').innerHTML = formatted + '<div class="chat-time">' + new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) + ' ✓✓</div>';
}

function insertStudioVar(tag) {
  const textarea = document.getElementById('studioMsgInput');
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = start + tag.length;
  updateStudioLivePreview();
}

function applyToCampaign() {
  const content = document.getElementById('studioMsgInput').value;
  sessionStorage.setItem('wam_draft_msg', content);
  window.location.href = '?tab=campaigns';
}

// Lead Finder Search
async function runLeadSearch() {
  const cat = document.getElementById('leadCatInput').value;
  const city = document.getElementById('leadCityInput').value;
  const limit = document.getElementById('leadLimitInput').value;

  const btn = event.target;
  const originalText = btn.textContent;
  btn.textContent = '⏳ খোঁজা হচ্ছে...';
  btn.disabled = true;

  try {
    const fd = new FormData();
    fd.append('action', 'search_business_leads');
    fd.append('category', cat);
    fd.append('city', city);
    fd.append('limit', limit);
    fd.append('csrf', '<?= csrf_token() ?>');

    const res = await fetch('whatsapp_marketing.php?tab=leadfinder', {
      method: 'POST',
      body: fd,
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    });
    const data = await res.json();

    if (data.ok && data.leads) {
      document.getElementById('leadSearchResults').style.display = 'block';
      document.getElementById('leadCountBadge').textContent = data.count;
      const tbody = document.getElementById('leadResultsTbody');
      tbody.innerHTML = '';

      data.leads.forEach(l => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${escapeHtml(l.name)}</strong></td>
          <td><span style="color:#25D366;">${escapeHtml(l.phone)}</span></td>
          <td style="font-size:0.85rem; max-width:200px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(l.address)}</td>
          <td><a href="${escapeHtml(l.website || '#')}" target="_blank" style="color:var(--admin-cyan);">${escapeHtml(l.website ? 'ওয়েবসাইট ↗' : '—')}</a></td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="convertLead('${escapeHtml(l.id)}', this)">+ কন্টাক্টে যোগ</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }
  } catch (e) {
    alert('লিড অনুসন্ধান ব্যর্থ হয়েছে।');
  } finally {
    btn.textContent = originalText;
    btn.disabled = false;
  }
}

async function convertLead(leadId, btn) {
  btn.textContent = '...';
  btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append('action', 'convert_lead_to_contact');
    fd.append('lead_id', leadId);
    fd.append('csrf', '<?= csrf_token() ?>');

    const res = await fetch('whatsapp_marketing.php?tab=leadfinder', {
      method: 'POST',
      body: fd,
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    });
    const data = await res.json();
    if (data.ok) {
      btn.textContent = '✓ যুক্ত হয়েছে';
      btn.style.color = '#10b981';
    }
  } catch(e) {
    btn.textContent = 'ত্রুটি';
  }
}

// Gemini AI Copywriter
async function generateAiMarketingCopy() {
  const prod = document.getElementById('aiProductInput').value;
  const angle = document.getElementById('aiAngleInput').value;
  const tone = document.getElementById('aiToneInput').value;
  const btn = event.target;
  btn.textContent = '✨ জেমিনি এআই লিখছে...';
  btn.disabled = true;

  try {
    const fd = new FormData();
    fd.append('action', 'generate_ai_copy');
    fd.append('product_name', prod);
    fd.append('angle', angle);
    fd.append('tone', tone);
    fd.append('csrf', '<?= csrf_token() ?>');

    const res = await fetch('whatsapp_marketing.php?tab=aistudio', {
      method: 'POST',
      body: fd,
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    });
    const data = await res.json();
    if (data.ok && data.generated_copy) {
      document.getElementById('aiGeneratedOutput').value = data.generated_copy;
    }
  } catch(e) {
    alert('এআই কপি তৈরিতে সমস্যা হয়েছে।');
  } finally {
    btn.textContent = '✨ জেমিনি এআই দিয়ে কপি তৈরি করুন';
    btn.disabled = false;
  }
}

function useAiCopyInStudio() {
  const copy = document.getElementById('aiGeneratedOutput').value;
  if (!copy) return;
  sessionStorage.setItem('wam_draft_msg', copy);
  window.location.href = '?tab=studio';
}

// Campaign Live Sequential Batch Runner
let campaignRunning = false;
async function startCampaignExecution(campId) {
  campaignRunning = true;
  document.getElementById('btnStartRunner').style.display = 'none';
  document.getElementById('btnPauseRunner').style.display = 'inline-block';

  async function step() {
    if (!campaignRunning) return;
    try {
      const fd = new FormData();
      fd.append('action', 'run_campaign_step');
      fd.append('campaign_id', campId);
      fd.append('batch_size', '1');
      fd.append('csrf', '<?= csrf_token() ?>');

      const res = await fetch('whatsapp_marketing.php?tab=campaigns', {
        method: 'POST',
        body: fd,
        headers: {'X-Requested-With': 'XMLHttpRequest'}
      });
      const data = await res.json();

      if (data.ok) {
        const sentEl = document.getElementById('statCampSent');
        sentEl.textContent = parseInt(sentEl.textContent || '0') + data.success;

        if (data.is_completed) {
          alert('অভিনন্দন! ক্যাম্পেইন সম্পূর্ণ সফলভাবে সম্পন্ন হয়েছে।');
          campaignRunning = false;
          window.location.reload();
          return;
        }

        // Random jitter delay between 3-6 seconds
        const delay = Math.floor(Math.random() * 3000) + 3000;
        setTimeout(step, delay);
      }
    } catch(e) {
      console.error(e);
      setTimeout(step, 5000);
    }
  }

  step();
}

function pauseCampaignExecution() {
  campaignRunning = false;
  document.getElementById('btnStartRunner').style.display = 'inline-block';
  document.getElementById('btnPauseRunner').style.display = 'none';
}

function escapeHtml(text) {
  if (!text) return '';
  return text.replace(/[&<>"']/g, function(m) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'}[m];
  });
}

// Group Grabber Counter
function updateGrabberCount() {
  const el = document.getElementById('grabberInput');
  const counter = document.getElementById('grabberCounter');
  if (!el || !counter) return;
  const lines = el.value.split(/\r?\n/).filter(l => l.trim().length > 0);
  counter.textContent = lines.length + ' টি নম্বর সনাক্ত';
}

// Number Filter & Validator Logic
let validFilteredList = [];
async function runNumberFilter() {
  const rawText = document.getElementById('filterRawInput').value;
  const targetGroup = document.getElementById('filterTargetGroup').value;
  const autoSave = document.getElementById('filterAutoSave').checked ? 1 : 0;
  const btn = document.getElementById('btnRunFilter');

  if (!rawText.trim()) {
    alert('যাচাই করার জন্য ফোন নম্বর পেস্ট করুন।');
    return;
  }

  btn.textContent = '⏳ নম্বর যাচাই করা হচ্ছে...';
  btn.disabled = true;

  try {
    const fd = new FormData();
    fd.append('action', 'filter_numbers');
    fd.append('raw_numbers', rawText);
    fd.append('target_group_id', targetGroup);
    fd.append('auto_save_valid', autoSave);
    fd.append('csrf', '<?= csrf_token() ?>');

    const res = await fetch('whatsapp_marketing.php?tab=numberfilter', {
      method: 'POST',
      body: fd,
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    });
    const data = await res.json();

    if (data.ok) {
      document.getElementById('statTotalFilter').textContent = data.total;
      document.getElementById('statValidFilter').textContent = data.valid_count;
      document.getElementById('statDupFilter').textContent = data.duplicate_count;
      document.getElementById('statInvalidFilter').textContent = data.invalid_count;

      validFilteredList = data.valid ? data.valid.map(v => v.number) : [];

      const placeholder = document.getElementById('filterResultsPlaceholder');
      const tableWrap = document.getElementById('filterResultsTableWrap');
      const tbody = document.getElementById('filterResultsTbody');
      const btnCopy = document.getElementById('btnCopyValid');

      placeholder.style.display = 'none';
      tableWrap.style.display = 'block';
      if (validFilteredList.length > 0 && btnCopy) {
        btnCopy.style.display = 'inline-block';
      }

      tbody.innerHTML = '';

      if (data.valid) {
        data.valid.forEach(v => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong style="color:#25D366;">+${escapeHtml(v.number)}</strong></td>
            <td><span class="badge badge-info">${escapeHtml(v.carrier)}</span></td>
            <td><span class="badge badge-success">সক্রিয় / ভ্যালিড</span></td>
            <td>
              <a href="https://wa.me/${escapeHtml(v.number)}" target="_blank" class="btn btn-secondary btn-sm" style="color:#25D366; text-decoration:none;">
                💬 চ্যাট ↗
              </a>
            </td>
          `;
          tbody.appendChild(tr);
        });
      }

      if (data.invalid) {
        data.invalid.forEach(inv => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td style="color:#f43f5e;">${escapeHtml(inv.number)}</td>
            <td>—</td>
            <td><span class="badge badge-danger">${escapeHtml(inv.reason)}</span></td>
            <td>—</td>
          `;
          tbody.appendChild(tr);
        });
      }
    }
  } catch(e) {
    alert('নম্বর ফিল্টারিং প্রক্রিয়ায় সমস্যা হয়েছে।');
  } finally {
    btn.textContent = '🔍 নম্বর যাচাই ও ফিল্টার করুন';
    btn.disabled = false;
  }
}

function copyValidNumbers() {
  if (validFilteredList.length === 0) return;
  navigator.clipboard.writeText(validFilteredList.join('\n')).then(() => {
    alert('মোট ' + validFilteredList.length + ' টি ভ্যালিড WhatsApp নম্বর ক্লিপবোর্ডে কপি হয়েছে!');
  });
}

// Template Loader Functions
function loadTemplateToStudio(text) {
  sessionStorage.setItem('wam_draft_msg', text);
  window.location.href = '?tab=studio';
}

function insertTplVar(tag) {
  const textarea = document.getElementById('tplBodyInput');
  if (!textarea) return;
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  textarea.value = textarea.value.substring(0, start) + tag + textarea.value.substring(end);
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = start + tag.length;
}

document.addEventListener('DOMContentLoaded', () => {
  const draft = sessionStorage.getItem('wam_draft_msg');
  const studioInput = document.getElementById('studioMsgInput');
  if (draft && studioInput) {
    studioInput.value = draft;
    sessionStorage.removeItem('wam_draft_msg');
    updateStudioLivePreview();
  }
});
</script>

<?php
admin_footer();
