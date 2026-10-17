<?php
declare(strict_types=1);

require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_once dirname(__DIR__) . '/includes/whatsapp.php';
require_once dirname(__DIR__) . '/includes/agent_llm.php';
require_once dirname(__DIR__) . '/includes/marketing_master_agent.php';

require_admin();

ensure_amp_migrations($pdo);

// -----------------------------------------------------------------------------
// AJAX SIMULATION ENDPOINT (Zero-latency Master AI Sandbox)
// -----------------------------------------------------------------------------
if (isset($_GET['ajax']) && $_GET['ajax'] === 'simulate_ai') {
    header('Content-Type: application/json; charset=utf-8');
    $rawInput = file_get_contents('php://input');
    $payload = json_decode((string)$rawInput, true) ?: $_POST;
    $userMsg = trim((string)($payload['user_message'] ?? ''));
    $agentReq = trim((string)($payload['requested_agent'] ?? 'auto'));
    $leadName = trim((string)($payload['lead_name'] ?? 'সম্মানিত অতিথি'));

    $res = MarketingMasterBrain::process($pdo, $config, [
        'channel' => 'whatsapp_crm',
        'user_message' => $userMsg,
        'requested_agent' => $agentReq,
        'lead_name' => $leadName,
    ]);

    echo json_encode([
        'ok' => true,
        'reply' => $res['reply'],
        'meta' => $res['meta']
    ]);
    exit;
}

$message = '';
$error = '';
$activeTab = trim((string) ($_GET['tab'] ?? 'accounts'));

// Load Anti-Ban Settings
$antiban = whatsapp_get_antiban_settings($pdo);

// -----------------------------------------------------------------------------
// POST ACTIONS DISPATCHER
// -----------------------------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!csrf_verify($_POST['csrf'] ?? null)) {
        $error = 'নিরাপত্তা যাচাই ব্যর্থ হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।';
    } else {
        $action = trim((string) ($_POST['action'] ?? ''));

        // 1. SAVE ANTI-BAN SENTINEL SETTINGS
        if ($action === 'save_antiban') {
            $newSettings = [
                'antiban_delay_min' => max(15, (int) ($_POST['antiban_delay_min'] ?? 25)),
                'antiban_delay_max' => max(30, (int) ($_POST['antiban_delay_max'] ?? 55)),
                'antiban_batch_size' => max(5, (int) ($_POST['antiban_batch_size'] ?? 15)),
                'antiban_batch_pause_seconds' => max(60, (int) ($_POST['antiban_batch_pause_seconds'] ?? 480)),
                'antiban_daily_cap_per_number' => max(20, (int) ($_POST['antiban_daily_cap_per_number'] ?? 65)),
                'antiban_priority_bypass' => isset($_POST['antiban_priority_bypass']),
                'antiban_smart_rotation' => isset($_POST['antiban_smart_rotation']),
                'antiban_human_jitter' => isset($_POST['antiban_human_jitter']),
                'auto_license_delivery' => isset($_POST['auto_license_delivery']),
                'lead_auto_followup' => isset($_POST['lead_auto_followup']),
            ];
            whatsapp_save_antiban_settings($pdo, $newSettings);
            $antiban = whatsapp_get_antiban_settings($pdo);
            $message = 'অ্যান্টি-ব্যান সেন্টিনেল ও ডেলিভারি গার্ড সেটিংস সফলভাবে সংরক্ষিত হয়েছে!';
            $activeTab = 'antiban';
        }

        // 2. ADD NEW NUMBER TO ROTATION POOL
        elseif ($action === 'add_account') {
            $accName = trim((string) ($_POST['account_name'] ?? 'নতুন হোয়াটসঅ্যাপ নম্বর'));
            $accPhone = trim((string) ($_POST['account_phone'] ?? ''));
            $provType = trim((string) ($_POST['provider_type'] ?? 'cloud_api'));
            $dailyLimit = max(20, (int) ($_POST['daily_limit'] ?? 65));
            $cleanPhone = preg_replace('/\D+/', '', $accPhone);
            if (str_starts_with($cleanPhone, '01')) $cleanPhone = '88' . $cleanPhone;

            if (strlen($cleanPhone) < 10) {
                $error = 'অনুগ্রহ করে সঠিক ফোন নম্বর প্রদান করুন।';
            } else {
                $accId = 'acc_' . time() . '_' . mt_rand(100, 999);
                $ins = $pdo->prepare("INSERT INTO accounts (id, name, phone, provider_type, status, session_health, daily_limit, daily_sent_today, messages_sent_count, last_active_at, created_at) VALUES (?, ?, ?, ?, 'connected', 100, ?, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)");
                $ins->execute([$accId, $accName, '+' . $cleanPhone, $provType, $dailyLimit]);
                try {
                    $pdo->prepare("INSERT OR REPLACE INTO wa_accounts (id, name, phone, provider_type, status, session_health, daily_limit, daily_sent_today, messages_sent_count, last_active_at, created_at) VALUES (?, ?, ?, ?, 'connected', 100, ?, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
                        ->execute([$accId, $accName, '+' . $cleanPhone, $provType, $dailyLimit]);
                } catch (\Throwable $e) {}
                $message = "নতুন নম্বর '{$accName}' (+{$cleanPhone}) সফলভাবে রোটেশন পুলে যুক্ত হয়েছে!";
                $activeTab = 'accounts';
            }
        }

        // 3. DELETE ACCOUNT FROM POOL
        elseif ($action === 'delete_account') {
            $accId = trim((string) ($_POST['account_id'] ?? ''));
            if ($accId !== '') {
                $pdo->prepare("DELETE FROM accounts WHERE id = ?")->execute([$accId]);
                try { $pdo->prepare("DELETE FROM wa_accounts WHERE id = ?")->execute([$accId]); } catch (\Throwable $e) {}
                $message = 'হোয়াটসঅ্যাপ অ্যাকাউন্টটি রোটেশন পুল থেকে সফলভাবে অপসারিত হয়েছে!';
                $activeTab = 'accounts';
            }
        }

        // 4. GROUP CONTACTS GRABBER / EXTRACTOR
        elseif ($action === 'grab_group_contacts') {
            $rawText = (string) ($_POST['raw_group_text'] ?? '');
            $targetGroupId = trim((string) ($_POST['target_group_id'] ?? ''));
            $newGroupName = trim((string) ($_POST['new_group_name'] ?? ''));

            if ($targetGroupId === 'new' && $newGroupName !== '') {
                $targetGroupId = 'grp_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                $pdo->prepare("INSERT INTO contact_groups (id, name, description, created_at) VALUES (?, ?, 'Extracted from WhatsApp Group', CURRENT_TIMESTAMP)")->execute([$targetGroupId, $newGroupName]);
                try { $pdo->prepare("INSERT INTO wa_contact_groups (id, name, description, created_at) VALUES (?, ?, 'Extracted from WhatsApp Group', CURRENT_TIMESTAMP)")->execute([$targetGroupId, $newGroupName]); } catch (\Throwable $e) {}
            }

            preg_match_all('/(\+?8801[3-9]\d{8}|01[3-9]\d{8}|\+?[1-9]\d{9,14})/', $rawText, $matches);
            $rawNumbers = array_unique($matches[0] ?? []);
            $savedCount = 0;

            foreach ($rawNumbers as $num) {
                $clean = whatsapp_clean_phone($num, true);
                if (strlen($clean) >= 10) {
                    $cId = 'cnt_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                    $ins = $pdo->prepare("INSERT INTO contacts (id, name, phone, tags, status, created_at) VALUES (?, 'Group Member', ?, 'group_extracted', 'active', CURRENT_TIMESTAMP)");
                    try {
                        $ins->execute([$cId, '+' . $clean]);
                        $savedCount++;
                        if ($targetGroupId !== '' && $targetGroupId !== 'new') {
                            $mId = 'gm_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                            $pdo->prepare("INSERT INTO contact_group_members (id, group_id, contact_id, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)")->execute([$mId, $targetGroupId, $cId]);
                        }
                    } catch (\Throwable $e) {}
                }
            }

            $message = "গ্রুপ থেকে সফলভাবে {$savedCount}টি সক্রিয় ফোন নম্বর এক্সট্র্যাক্ট করে ডাটাবেজে সংরক্ষণ করা হয়েছে!";
            $activeTab = 'grabber';
        }

        // 5. BULK NUMBER FILTER & VALIDATOR
        elseif ($action === 'filter_numbers') {
            $rawInputList = (string) ($_POST['raw_numbers_to_filter'] ?? '');
            $saveValid = isset($_POST['save_valid_to_group']);
            $targetGroup = trim((string) ($_POST['filter_target_group'] ?? ''));

            $lines = preg_split('/[\r\n,;]+/', $rawInputList);
            $validList = [];
            $invalidList = [];

            foreach ($lines as $ln) {
                $clean = preg_replace('/\D+/', '', trim($ln));
                if (str_starts_with($clean, '01') && strlen($clean) === 11) {
                    $validList[] = '+88' . $clean;
                } elseif (str_starts_with($clean, '8801') && strlen($clean) === 13) {
                    $validList[] = '+' . $clean;
                } elseif (strlen($clean) >= 10 && strlen($clean) <= 15) {
                    $validList[] = '+' . $clean;
                } else {
                    if (trim($ln) !== '') $invalidList[] = trim($ln);
                }
            }

            $validList = array_values(array_unique($validList));
            $savedValidCount = 0;

            if ($saveValid && !empty($validList)) {
                foreach ($validList as $vPhone) {
                    $cId = 'cnt_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                    try {
                        $pdo->prepare("INSERT INTO contacts (id, name, phone, tags, status, created_at) VALUES (?, 'Validated Lead', ?, 'number_validator', 'active', CURRENT_TIMESTAMP)")->execute([$cId, $vPhone]);
                        $savedValidCount++;
                        if ($targetGroup !== '') {
                            $mId = 'gm_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                            $pdo->prepare("INSERT INTO contact_group_members (id, group_id, contact_id, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)")->execute([$mId, $targetGroup, $cId]);
                        }
                    } catch (\Throwable $e) {}
                }
            }

            $_SESSION['filter_results'] = [
                'total' => count($lines),
                'valid_count' => count($validList),
                'invalid_count' => count($invalidList),
                'valid_list' => array_slice($validList, 0, 50),
                'invalid_list' => array_slice($invalidList, 0, 50),
                'saved_count' => $savedValidCount
            ];
            $message = "নম্বর ফিল্টারিং সম্পন্ন: " . count($validList) . "টি ভ্যালিড এবং " . count($invalidList) . "টি ইনভ্যালিড নম্বর সনাক্ত হয়েছে!";
            $activeTab = 'filter';
        }

        // 6. CREATE CONTACT GROUP
        elseif ($action === 'create_contact_group') {
            $gName = trim((string) ($_POST['group_name'] ?? ''));
            $gDesc = trim((string) ($_POST['group_desc'] ?? ''));
            if ($gName !== '') {
                $gId = 'grp_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                $pdo->prepare("INSERT INTO contact_groups (id, name, description, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)")->execute([$gId, $gName, $gDesc]);
                try { $pdo->prepare("INSERT INTO wa_contact_groups (id, name, description, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)")->execute([$gId, $gName, $gDesc]); } catch (\Throwable $e) {}
                $message = "নতুন অডিয়েন্স গ্রুপ '{$gName}' সফলভাবে তৈরি হয়েছে!";
            }
            $activeTab = 'contacts';
        }

        // 7. ADD MANUAL NUMBERS TO GROUP
        elseif ($action === 'add_manual_numbers_to_group') {
            $gId = trim((string) ($_POST['group_id'] ?? ''));
            $rawNumbers = (string) ($_POST['manual_numbers'] ?? '');
            $lines = preg_split('/[\r\n,;]+/', $rawNumbers);
            $added = 0;

            foreach ($lines as $ln) {
                $clean = whatsapp_clean_phone($ln, true);
                if (strlen($clean) >= 10) {
                    $cId = 'cnt_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                    try {
                        $pdo->prepare("INSERT INTO contacts (id, name, phone, tags, status, created_at) VALUES (?, 'Manual Contact', ?, 'manual_add', 'active', CURRENT_TIMESTAMP)")->execute([$cId, '+' . $clean]);
                        if ($gId !== '') {
                            $mId = 'gm_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                            $pdo->prepare("INSERT INTO contact_group_members (id, group_id, contact_id, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)")->execute([$mId, $gId, $cId]);
                        }
                        $added++;
                    } catch (\Throwable $e) {}
                }
            }
            $message = "গ্রুপে সফলভাবে {$added}টি নম্বর অন্তর্ভুক্ত করা হয়েছে!";
            $activeTab = 'contacts';
        }

        // 8. CREATE / UPDATE CONVERSION TEMPLATE
        elseif ($action === 'create_template') {
            $tTitle = trim((string) ($_POST['template_title'] ?? ''));
            $tCat = trim((string) ($_POST['template_category'] ?? 'General'));
            $tContent = trim((string) ($_POST['template_content'] ?? ''));

            if ($tTitle !== '' && $tContent !== '') {
                $tId = 'tpl_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
                $vars = json_encode(['name', 'package', 'link', 'coupon', 'login_id']);
                $pdo->prepare("INSERT INTO message_templates (id, title, category, content, variables, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)")->execute([$tId, $tTitle, $tCat, $tContent, $vars]);
                try {
                    $pdo->prepare("INSERT INTO whatsapp_templates (template_key, title, category, body, is_active, created_at) VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)")->execute([$tId, $tTitle, $tCat, $tContent]);
                } catch (\Throwable $e) {}
                $message = "নতুন কনভার্সন টেমপ্লেট '{$tTitle}' সফলভাবে সংরক্ষিত হয়েছে!";
            }
            $activeTab = 'templates';
        }

        // 9. DELETE TEMPLATE
        elseif ($action === 'delete_template') {
            $tId = trim((string) ($_POST['template_id'] ?? ''));
            if ($tId !== '') {
                $pdo->prepare("DELETE FROM message_templates WHERE id = ?")->execute([$tId]);
                try { $pdo->prepare("DELETE FROM whatsapp_templates WHERE template_key = ?")->execute([$tId]); } catch (\Throwable $e) {}
                $message = "টেমপ্লেটটি সফলভাবে অপসারিত হয়েছে!";
            }
            $activeTab = 'templates';
        }

        // 10. SAVE MASTER AI SETTINGS
        elseif ($action === 'save_master_ai') {
            set_setting($pdo, 'agent_ayesha_active', isset($_POST['agent_ayesha_active']) ? '1' : '0');
            set_setting($pdo, 'agent_nirob_active', isset($_POST['agent_nirob_active']) ? '1' : '0');
            set_setting($pdo, 'agent_tania_active', isset($_POST['agent_tania_active']) ? '1' : '0');
            if (isset($_POST['ayesha_prompt'])) set_setting($pdo, 'ayesha_custom_prompt', trim((string)$_POST['ayesha_prompt']));
            if (isset($_POST['nirob_prompt'])) set_setting($pdo, 'nirob_custom_prompt', trim((string)$_POST['nirob_prompt']));
            if (isset($_POST['tania_prompt'])) set_setting($pdo, 'tania_custom_prompt', trim((string)$_POST['tania_prompt']));
            if (isset($_POST['master_discount_coupon'])) set_setting($pdo, 'agent_discount_coupon', trim((string)$_POST['master_discount_coupon']));
            $message = 'চিফ মার্কেটিং ডিরেক্টর ও ৩ জন এআই এজেন্টের সেটিংস সফলভাবে আপডেট হয়েছে!';
            $activeTab = 'agents';
        }

        // 11. QUICK CUSTOMER DISPATCH
        elseif ($action === 'quick_dispatch') {
            $triggerType = trim((string) ($_POST['trigger_type'] ?? 'order_approved'));
            $cName = trim((string) ($_POST['customer_name'] ?? 'সম্মানিত গ্রাহক'));
            $cPhone = trim((string) ($_POST['customer_phone'] ?? ''));
            $cPkg = trim((string) ($_POST['package_name'] ?? 'AutoMovie Pro 4K Video Studio'));
            $customNote = trim((string) ($_POST['custom_note'] ?? ''));
            $cleanPhone = whatsapp_clean_phone($cPhone, true);

            if (strlen($cleanPhone) < 10) {
                $error = 'অনুগ্রহ করে সঠিক ফোন নম্বর প্রদান করুন।';
            } else {
                $msgContent = "";
                if ($triggerType === 'order_placed') {
                    $msgContent = "Assalamu Alaikum {$cName}!\n\nAutoMovie Pro-তে আপনার অর্ডারটি সফলভাবে গ্রহণ করা হয়েছে।\nনির্বাচিত প্যাকেজ: {$cPkg}।\n\nবিকাশ/নগদে ক্যাশ আউট সম্পন্ন করে TrxID পাঠালেই সাথে সাথে সফটওয়্যার অ্যাক্টিভেট হয়ে যাবে।\nপেমেন্ট লিংক: https://automoviepro.com/order.php\n\nযেকোনো সহায়তায় আমাদের সাথে যোগাযোগ করুন।";
                } elseif ($triggerType === 'order_approved') {
                    $loginId = 'amp_' . mt_rand(1000, 9999);
                    $password = 'MoviePro@' . date('Y');
                    $dlToken = bin2hex(random_bytes(16));
                    $msgContent = "Assalamu Alaikum {$cName}!\n\nঅভিনন্দন! আপনার AutoMovie Pro পেমেন্ট সফলভাবে অনুমোদিত হয়েছে। 🎉\n\n🔑 লগইন আইডি: {$loginId}\n🔒 পাসওয়ার্ড: {$password}\n📥 সফটওয়্যার ডাউনলোড: https://automoviepro.com/download.php?token={$dlToken}\n📖 ইনস্টলেশন নির্দেশিকা: https://automoviepro.com/guide.html\n\nসফটওয়্যারটি ইনস্টল করে লগইন করুন। আমাদের সাপোর্ট টিম সর্বদা আপনার পাশে রয়েছে।";
                } elseif ($triggerType === 'demo_inquiry') {
                    $msgContent = "Assalamu Alaikum {$cName}!\n\nAutoMovie Pro ডেমো ও বিস্তারিত তথ্যে আগ্রহ প্রকাশের জন্য ধন্যবাদ।\nআমাদের ৩টি প্যাকেজের পূর্ণাঙ্গ ফিচার ও লাইভ ভিডিও ডেমো দেখতে ভিজিট করুন:\n👉 https://automoviepro.com/#features\n\nস্পেসিফিক কোনো প্রশ্ন থাকলে আমাদের জানাতে পারেন!";
                } elseif ($triggerType === 'care_checkin') {
                    $msgContent = "Assalamu Alaikum {$cName}!\n\nAutoMovie Pro কাস্টমার কেয়ার থেকে যোগাযোগ করছি।\nআপনার সফটওয়্যারটি কেমন চলছে? ভিডিও রেন্ডারিং বা ফেসবুক পোস্টিংয়ে কোনো প্রকার সমস্যা বা সহায়তা প্রয়োজন কি?\n\nকোনো সমস্যা থাকলে নির্দ্বিধায় আমাদের জানান, আমরা দ্রুত সমাধান করে দেবো।";
                } elseif ($triggerType === 'version_update') {
                    $version = $customNote ?: 'v4.5.2';
                    $msgContent = "📢 AutoMovie Pro নতুন আপডেট রিলিজ ({$version})!\n\nসম্মানিত গ্রাহক {$cName},\nআমাদের অটোমেশন ইঞ্জিনে নতুন ফিচার যুক্ত হয়েছে:\n• দ্রুততম 4K রেন্ডারিং স্পিড\n• স্মার্ট ফেসবুক ও রিলস অটো-শিডিউলিং\n• এআই ভয়েস ও ক্যাপশন অপটিমাইজেশন\n\nসফটওয়্যারটি ওপেন করলেই স্বয়ংক্রিয়ভাবে আপডেট হয়ে যাবে অথবা আমাদের পোর্টাল থেকে আপডেট ফাইল ডাউনলোড করুন।";
                } elseif ($triggerType === 'custom') {
                    $msgContent = $customNote ?: "Assalamu Alaikum {$cName}!\nAutoMovie Pro টিম থেকে শুভেচ্ছা।";
                }

                $priority = in_array($triggerType, ['order_approved', 'customer_inquiry'], true) ? 'high' : 'normal';
                $dispRes = whatsapp_antiban_dispatch($pdo, $config, $cleanPhone, $msgContent, $priority, $triggerType);
                $delayNote = $dispRes['delay_applied'] > 0 ? " ({$dispRes['delay_applied']}s অ্যান্টি-ব্যান জিটার প্রয়োগ)" : " (০ সেকেন্ড জরুরি বাইপাস)";
                $message = "গ্রাহক {$cName} ({$dispRes['phone']})-এর কাছে {$dispRes['account_used']} নম্বর দিয়ে বার্তা প্রেরণ করা হয়েছে{$delayNote}!";
                $activeTab = 'dispatch';
            }
        }

        // 12. BROADCAST CAMPAIGN DISPATCH
        elseif ($action === 'broadcast_campaign') {
            $targetAudience = trim((string) ($_POST['target_audience'] ?? 'all_leads'));
            $campMessage = trim((string) ($_POST['campaign_message'] ?? ''));

            if (empty($campMessage)) {
                $error = 'ক্যাম্পেইনের মেসেজ কনটেন্ট খালি রাখা যাবে না।';
            } else {
                $contacts = [];
                if ($targetAudience === 'all_leads') {
                    $contacts = $pdo->query("SELECT name, clean_phone as phone, interest_package as pkg FROM whatsapp_leads ORDER BY id DESC LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
                } elseif ($targetAudience === 'all_paid') {
                    $contacts = $pdo->query("SELECT name, whatsapp as phone, plan_name as pkg FROM orders WHERE status IN ('approved', 'active') GROUP BY whatsapp LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
                } elseif (str_starts_with($targetAudience, 'group_')) {
                    $targetGid = substr($targetAudience, 6);
                    $stmt = $pdo->prepare("SELECT c.name, c.phone, '' as pkg FROM contacts c JOIN contact_group_members m ON c.id = m.contact_id WHERE m.group_id = ? LIMIT 50");
                    $stmt->execute([$targetGid]);
                    $contacts = $stmt->fetchAll(PDO::FETCH_ASSOC);
                } else {
                    $contacts = $pdo->query("SELECT name, phone, tags as pkg FROM contacts LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
                }

                if (empty($contacts)) {
                    $error = 'নির্বাচিত অডিয়েন্সে কোনো প্রাপক নম্বর পাওয়া যায়নি।';
                } else {
                    $sentCount = 0;
                    $pool = whatsapp_get_accounts_pool($pdo);
                    $numPool = max(1, count($pool));

                    foreach ($contacts as $c) {
                        $p = whatsapp_clean_phone($c['phone'] ?? '', true);
                        if (strlen($p) < 10) continue;
                        $persText = str_replace(
                            ['{name}', '{package}', '{login_id}', '{coupon}', '{link}'],
                            [$c['name'] ?: 'সম্মানিত গ্রাহক', $c['pkg'] ?: 'AutoMovie Pro', 'amp_' . mt_rand(1000, 9999), 'SPECIAL500', 'https://automoviepro.com/order.php'],
                            $campMessage
                        );
                        whatsapp_antiban_dispatch($pdo, $config, $p, $persText, 'normal', 'campaign_broadcast');
                        $sentCount++;
                    }
                    $message = "স্মার্ট অ্যান্টি-ব্যান সেন্টিনেল সফলভাবে {$sentCount} জন গ্রাহকের কাছে {$numPool}টি নম্বরে রোটেশন করে ক্যাম্পেইন কিউ/ডিসপ্যাচ সম্পন্ন করেছে!";
                    $activeTab = 'broadcast';
                }
            }
        }

        // 13. CRM INBOX LIVE REPLY
        elseif ($action === 'crm_reply') {
            $leadPhone = trim((string) ($_POST['lead_phone'] ?? ''));
            $replyText = trim((string) ($_POST['reply_text'] ?? ''));
            $agentChoice = trim((string) ($_POST['agent_choice'] ?? 'ayesha'));
            $cleanPhone = whatsapp_clean_phone($leadPhone, true);

            if (empty($replyText) || strlen($cleanPhone) < 10) {
                $error = 'সঠিক ফোন নম্বর ও উত্তরের বার্তা প্রদান করুন।';
            } else {
                $res = whatsapp_antiban_dispatch($pdo, $config, $cleanPhone, $replyText, 'high', 'inbound_reply');
                $message = "গ্রাহক (+{$cleanPhone})-কে {$agentChoice} এজেন্টের মাধ্যমে সফলভাবে তাৎক্ষণিক উত্তর পাঠানো হয়েছে!";
                $activeTab = 'crm';
            }
        }
    }
}

// -----------------------------------------------------------------------------
// DATA FETCHING FOR FULL DESKTOP SUITE
// -----------------------------------------------------------------------------
$accountsPool = whatsapp_get_accounts_pool($pdo);
$totalActiveAccounts = 0;
$totalDailySent = 0;
$totalDailyRemaining = 0;
foreach ($accountsPool as $acc) {
    if ($acc['status'] === 'connected' || $acc['status'] === 'active') $totalActiveAccounts++;
    $totalDailySent += $acc['daily_sent_today'];
    $totalDailyRemaining += $acc['remaining_quota'];
}

$totalLeads = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_leads")->fetchColumn();
$totalOrders = (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status IN ('approved', 'active')")->fetchColumn();
$totalDispatches = (int) $pdo->query("SELECT COUNT(*) FROM request_dispatches")->fetchColumn();
$recentDispatches = $pdo->query("SELECT * FROM request_dispatches ORDER BY created_at DESC LIMIT 15")->fetchAll(PDO::FETCH_ASSOC);

// Contact groups
$contactGroups = [];
try {
    $contactGroups = $pdo->query("
        SELECT g.id, g.name, g.description, g.created_at, COUNT(m.contact_id) as member_count
        FROM contact_groups g
        LEFT JOIN contact_group_members m ON g.id = m.group_id
        GROUP BY g.id, g.name, g.description, g.created_at
        ORDER BY g.created_at DESC
    ")->fetchAll(PDO::FETCH_ASSOC);
} catch (\Throwable $e) {}

$totalContacts = 0;
try {
    $totalContacts = (int) $pdo->query("SELECT COUNT(*) FROM contacts")->fetchColumn();
} catch (\Throwable $e) {}

// Conversion Templates
$savedTemplates = [];
try {
    $savedTemplates = $pdo->query("SELECT * FROM message_templates ORDER BY created_at DESC")->fetchAll(PDO::FETCH_ASSOC);
} catch (\Throwable $e) {}

// Pre-seeded elite conversion templates if empty
$defaultEliteTemplates = [
    [
        'id' => 'hormozi_grand_slam',
        'title' => '👑 Alex Hormozi: Grand Slam Offer (No-Brainer Deal + Guarantee)',
        'category' => 'Hormozi Persuasion',
        'content' => "Assalamu Alaikum {name}!\n\nআপনি কি কোনো ভিডিও এডিটিং দক্ষতা ছাড়াই দিনে ৩-৫টি ভাইরাল ভিডিও বানিয়ে প্যাসিভ ইনকাম শুরু করতে চান?\n\nAutoMovie Pro-এর আজকের গ্র্যান্ড স্ল্যাম অফার:\n• ৩,৯৯৯ টাকার ফুল ভিডিও স্টুডিও কিনলে সাথে পাচ্ছেন রেডি-মেড ১০০+ ভাইরাল স্ক্রিপ্ট ভল্ট সম্পূর্ণ ফ্রি।\n• ১৮টি চ্যানেলে স্বয়ংক্রিয় শিডিউলিং ও লোকাল পিসি সিকিউরিটি।\n• ১০০% রিপ্লেসমেন্ট ও মানি-ব্যাক ওয়ারেন্টি গ্যারান্টি!\n\nঅর্ডার করতে ভিজিট করুন: {link}\nকুপন কোড: {coupon}",
    ],
    [
        'id' => 'brunson_epiphany',
        'title' => '🚀 Russell Brunson: Hook-Story-Offer (Epiphany Bridge)',
        'category' => 'Brunson Conversion',
        'content' => "প্রতিদিন ৫-৬ ঘণ্টা বসে ভিডিও এডিট করতে করতে ক্লান্ত?\n\nসম্মানিত {name}, আমিও ঠিক এই সমস্যার মধ্যে ছিলাম—যতক্ষণ না AutoMovie Pro ব্যবহার শুরু করলাম! এখন মাত্র ১-ক্লিকে স্ক্রিপ্ট থেকে শুরু করে মানুষের মতো ভয়েসওভার ও সিনেমাটিক সাবটাইটেল তৈরি হয়ে যায়।\n\nআপনার মূল্যবান সময় বাঁচান এবং আজই অটোমেশনের শক্তি উপভোগ করুন:\n👉 {link}",
    ],
    [
        'id' => 'scarcity_countdown',
        'title' => '⏳ Scarcity & Urgency: ৫০% মেগা ডিসকাউন্ট ফ্ল্যাশ ডিল',
        'category' => 'Urgency Deal',
        'content' => "🔥 মেগা ফ্ল্যাশ ডিল এলার্ট!\n\nসম্মানিত {name}, আগামী ২৪ ঘণ্টার জন্য আমাদের লাইফটাইম ভিডিও স্টুডিও ও মেটা বিজনেস লাইসেন্সে বিশেষ ৫০০ টাকা ছাড় চলছে!\n\nসিক্রেট কুপন কোড: {coupon}\nসরাসরি অর্ডার লিংক: https://automoviepro.com/order.php?coupon={coupon}\n\nস্টক সীমিত, সময় শেষ হওয়ার আগেই আপনার অ্যাক্টিভেশন নিশ্চিত করুন।",
    ],
    [
        'id' => 'demo_video_guide',
        'title' => '🎬 1-Click Video Demo & Non-Tech Setup Guide',
        'category' => 'Product Demo',
        'content' => "Assalamu Alaikum {name}!\n\nAutoMovie Pro কীভাবে কোনো কোডিং বা এডিটিং ছাড়া মাত্র ২ মিনিটে ফুল 4K ভিডিও রেন্ডার করে, তা নিজের চোখে দেখতে নিচের ভিডিও ডেমোটি চেক করুন:\n👉 https://automoviepro.com/#features\n\nআপনার পিসিতে Windows 10/11 ও 4GB RAM থাকলেই অনায়াসে চলবে। কোনো প্রশ্ন থাকলে সরাসরি জানান!",
    ],
    [
        'id' => 'vip_onboarding',
        'title' => '💎 Post-Purchase VIP Onboarding & License Key',
        'category' => 'VIP Delivery',
        'content' => "অভিনন্দন {name}! আপনার AutoMovie Pro লাইসেন্স সফলভাবে অ্যাক্টিভ করা হয়েছে। 🎉\n\n🔑 লগইন আইডি: {login_id}\n📥 ডাউনলোড লিংক: {link}\n📖 সেটআপ নির্দেশিকা: https://automoviepro.com/guide.html\n\nআমাদের ২৪/৭ অফিশিয়াল হোয়াটসঅ্যাপ সাপোর্ট সর্বদা আপনার পাশে রয়েছে। শুভকামনা!",
    ]
];

// CRM Threads
$crmThreads = [];
try {
    $crmThreads = $pdo->query("SELECT * FROM whatsapp_leads ORDER BY updated_at DESC LIMIT 20")->fetchAll(PDO::FETCH_ASSOC);
} catch (\Throwable $e) {}

$filterResults = $_SESSION['filter_results'] ?? null;
unset($_SESSION['filter_results']);

admin_header('WAManager Pro — অফিসিয়াল হোয়াটসঅ্যাপ মার্কেটিং ও এআই সিআরএম স্যুট', 'whatsapp');
?>

<style>
  :root {
    --wam-primary: #10b981;
    --wam-primary-dark: #059669;
    --wam-primary-glow: rgba(16, 185, 129, 0.3);
    --wam-cyan: #06b6d4;
    --wam-purple: #8b5cf6;
    --wam-amber: #f59e0b;
    --wam-danger: #ef4444;
    --wam-bg-dark: #090d16;
    --wam-card: #111827;
    --wam-card-hover: #161f30;
    --wam-border: #1e293b;
    --wam-border-glow: rgba(16, 185, 129, 0.25);
    --wam-text-main: #f8fafc;
    --wam-text-muted: #94a3b8;
  }

  .wam-desktop-wrapper {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    padding-bottom: 3rem;
  }

  /* MASTER HUD */
  .wam-master-hud {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(6, 182, 212, 0.08), rgba(15, 23, 42, 0.95));
    border: 1px solid var(--wam-border-glow);
    border-radius: 16px;
    padding: 1.25rem 1.75rem;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 1.25rem;
  }

  .wam-brand-area {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .wam-brand-badge-icon {
    width: 52px;
    height: 52px;
    background: linear-gradient(135deg, var(--wam-primary), #047857);
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.8rem;
    box-shadow: 0 0 20px rgba(16, 185, 129, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.2);
  }

  .wam-brand-titles h1 {
    font-size: 1.4rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    letter-spacing: -0.3px;
  }

  .wam-brand-tag {
    font-size: 0.68rem;
    font-weight: 800;
    background: var(--wam-primary);
    color: #020617;
    padding: 2px 8px;
    border-radius: 6px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }

  .wam-brand-sub {
    font-size: 0.85rem;
    color: var(--wam-text-muted);
    margin: 4px 0 0;
  }

  /* SYSTEM PILLS */
  .wam-system-pills {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .wam-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #cbd5e1;
  }

  .wam-pill.secure {
    background: rgba(16, 185, 129, 0.15);
    border-color: rgba(16, 185, 129, 0.35);
    color: #34d399;
  }

  .wam-pill.ai-live {
    background: rgba(6, 182, 212, 0.15);
    border-color: rgba(6, 182, 212, 0.35);
    color: #38bdf8;
  }

  .wam-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 10px #10b981;
    animation: pulse 1.8s infinite;
  }

  @keyframes pulse {
    0% { transform: scale(0.9); opacity: 0.8; }
    50% { transform: scale(1.3); opacity: 1; }
    100% { transform: scale(0.9); opacity: 0.8; }
  }

  /* METRICS STRIP */
  .wam-metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 1rem;
  }

  .wam-metric-card {
    background: var(--wam-card);
    border: 1px solid var(--wam-border);
    border-radius: 14px;
    padding: 1.15rem 1.25rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
    transition: transform 0.2s ease, border-color 0.2s ease;
  }

  .wam-metric-card:hover {
    transform: translateY(-2px);
    border-color: var(--wam-border-glow);
  }

  .wam-metric-label {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--wam-text-muted);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .wam-metric-num {
    font-size: 1.6rem;
    font-weight: 800;
    color: #ffffff;
    margin: 8px 0 2px;
  }

  .wam-metric-sub {
    font-size: 0.75rem;
    color: #64748b;
  }

  /* CYBER TABS */
  .wam-tabs-deck {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #0f172a;
    padding: 6px;
    border-radius: 12px;
    border: 1px solid var(--wam-border);
    overflow-x: auto;
  }

  .wam-tab-btn {
    background: transparent;
    border: none;
    color: #94a3b8;
    font-size: 0.85rem;
    font-weight: 700;
    padding: 9px 15px;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    white-space: nowrap;
    transition: all 0.2s ease;
    text-decoration: none;
  }

  .wam-tab-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #ffffff;
  }

  .wam-tab-btn.active {
    background: linear-gradient(135deg, var(--wam-primary), var(--wam-primary-dark));
    color: #ffffff;
    box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35);
  }

  /* CONTENT PANELS */
  .wam-panel {
    display: none;
    background: var(--wam-card);
    border: 1px solid var(--wam-border);
    border-radius: 16px;
    padding: 1.5rem 1.75rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
  }

  .wam-panel.active {
    display: block;
    animation: fadeIn 0.25s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .wam-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 1.25rem;
  }

  .wam-section-header h2 {
    font-size: 1.2rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .wam-section-header p {
    font-size: 0.85rem;
    color: var(--wam-text-muted);
    margin: 4px 0 0;
  }

  /* BUTTONS */
  .btn-wam-primary {
    background: linear-gradient(135deg, var(--wam-primary), var(--wam-primary-dark));
    color: #ffffff;
    font-weight: 700;
    font-size: 0.88rem;
    padding: 10px 18px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  .btn-wam-primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.45);
  }

  .btn-wam-secondary {
    background: #1e293b;
    color: #e2e8f0;
    font-weight: 600;
    font-size: 0.85rem;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    text-decoration: none;
    transition: background 0.15s ease;
  }

  .btn-wam-secondary:hover {
    background: #334155;
    color: #ffffff;
  }

  .btn-wam-danger {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #f87171;
    font-size: 0.78rem;
    font-weight: 600;
    padding: 5px 10px;
    border-radius: 6px;
    cursor: pointer;
  }

  .btn-wam-danger:hover {
    background: rgba(239, 68, 68, 0.25);
  }

  /* FORM STYLES */
  .wam-form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1.25rem;
  }

  .wam-form-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .wam-form-group label {
    font-size: 0.82rem;
    font-weight: 700;
    color: #cbd5e1;
  }

  .wam-form-input, .wam-form-select, .wam-form-textarea {
    background: #090d16;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 9px 12px;
    color: #ffffff;
    font-size: 0.88rem;
    outline: none;
    transition: border-color 0.2s ease;
  }

  .wam-form-input:focus, .wam-form-select:focus, .wam-form-textarea:focus {
    border-color: var(--wam-primary);
    box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
  }

  /* ACCOUNTS GRID */
  .wam-accounts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1.25rem;
    margin-top: 1rem;
  }

  .wam-account-card {
    background: #0f172a;
    border: 1px solid var(--wam-border);
    border-radius: 14px;
    padding: 1.25rem;
    position: relative;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .wam-account-card.active {
    border-color: rgba(16, 185, 129, 0.4);
  }

  .wam-account-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .wam-acc-info h3 {
    margin: 0;
    font-size: 0.98rem;
    font-weight: 700;
    color: #ffffff;
  }

  .wam-acc-phone {
    font-size: 0.85rem;
    color: var(--wam-primary);
    font-weight: 700;
    margin-top: 2px;
  }

  .wam-progress-bar {
    width: 100%;
    height: 7px;
    background: #1e293b;
    border-radius: 10px;
    overflow: hidden;
    margin: 6px 0 2px;
  }

  .wam-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--wam-primary), var(--wam-cyan));
    border-radius: 10px;
  }

  /* AGENTS 3-TIER CARDS */
  .wam-agents-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1.5rem;
    margin-top: 1rem;
  }

  .wam-agent-card {
    background: #0f172a;
    border: 1px solid var(--wam-border);
    border-radius: 16px;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 14px;
    box-shadow: 0 6px 25px rgba(0, 0, 0, 0.4);
  }

  .wam-agent-avatar-deck {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .wam-agent-avatar-img {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid var(--wam-primary);
    box-shadow: 0 0 15px rgba(16, 185, 129, 0.35);
  }

  .wam-agent-details h3 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 800;
    color: #ffffff;
  }

  .wam-agent-role {
    font-size: 0.78rem;
    color: var(--wam-cyan);
    font-weight: 600;
    margin-top: 2px;
  }

  /* LIVE WHATSAPP PHONE PREVIEW */
  .wam-phone-mockup {
    width: 100%;
    max-width: 420px;
    background: #0b141a;
    border-radius: 24px;
    border: 3px solid #2a3942;
    overflow: hidden;
    box-shadow: 0 15px 40px rgba(0, 0, 0, 0.7);
    margin: 0 auto;
  }

  .wam-phone-header {
    background: #202c33;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #ffffff;
    border-bottom: 1px solid #111b21;
  }

  .wam-phone-body {
    padding: 16px 12px;
    min-height: 280px;
    background-image: radial-gradient(#1e293b 1px, transparent 1px);
    background-size: 16px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .wam-bubble-out {
    align-self: flex-end;
    background: #005c4b;
    color: #e9edef;
    padding: 10px 14px;
    border-radius: 12px 0 12px 12px;
    font-size: 0.85rem;
    line-height: 1.4;
    max-width: 85%;
    white-space: pre-wrap;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  .wam-bubble-in {
    align-self: flex-start;
    background: #202c33;
    color: #e9edef;
    padding: 10px 14px;
    border-radius: 0 12px 12px 12px;
    font-size: 0.85rem;
    line-height: 1.4;
    max-width: 85%;
    white-space: pre-wrap;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  /* CRM CHAT LAYOUT */
  .wam-crm-shell {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 1.25rem;
    height: 650px;
  }

  @media (max-width: 900px) {
    .wam-crm-shell {
      grid-template-columns: 1fr;
      height: auto;
    }
  }

  .wam-crm-threads {
    background: #0f172a;
    border: 1px solid var(--wam-border);
    border-radius: 14px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .wam-thread-item {
    padding: 12px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .wam-thread-item:hover, .wam-thread-item.active {
    background: rgba(16, 185, 129, 0.1);
    border-left: 3px solid var(--wam-primary);
  }

  .wam-crm-main {
    background: #0f172a;
    border: 1px solid var(--wam-border);
    border-radius: 14px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .wam-crm-chat-body {
    flex: 1;
    padding: 1.25rem;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    background-image: radial-gradient(#1e293b 1px, transparent 1px);
    background-size: 16px 16px;
  }

  .wam-crm-chat-foot {
    padding: 12px 16px;
    background: #111827;
    border-top: 1px solid var(--wam-border);
    display: flex;
    gap: 10px;
    align-items: center;
  }

  /* AUDIT TABLE */
  .wam-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
    margin-top: 1rem;
  }

  .wam-table th {
    background: #1e293b;
    color: #94a3b8;
    text-align: left;
    padding: 10px 14px;
    font-weight: 700;
  }

  .wam-table td {
    padding: 10px 14px;
    border-bottom: 1px solid #1e293b;
    color: #cbd5e1;
  }

  .wam-table tr:hover td {
    background: rgba(255, 255, 255, 0.02);
  }

  /* TEMPLATE CARDS */
  .wam-templates-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1.25rem;
    margin-top: 1rem;
  }

  .wam-template-card {
    background: #0f172a;
    border: 1px solid var(--wam-border);
    border-radius: 14px;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 12px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
  }

  .wam-template-card:hover {
    border-color: rgba(16, 185, 129, 0.35);
  }

  /* BADGES */
  .badge-framework {
    font-size: 0.7rem;
    padding: 3px 8px;
    border-radius: 4px;
    font-weight: 700;
    text-transform: uppercase;
    display: inline-block;
  }
  .badge-hormozi { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
  .badge-brunson { background: rgba(139, 92, 246, 0.2); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.4); }
  .badge-urgency { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
  .badge-demo { background: rgba(6, 182, 212, 0.2); color: #38bdf8; border: 1px solid rgba(6, 182, 212, 0.4); }
</style>

<div class="wam-desktop-wrapper">

  <?php if ($message): ?>
    <div style="background:rgba(16,185,129,0.18); border:1px solid rgba(16,185,129,0.5); border-radius:12px; padding:12px 18px; color:#a7f3d0; font-size:0.95rem; display:flex; align-items:center; gap:8px;">
      <span>✓</span> <strong><?= e($message) ?></strong>
    </div>
  <?php endif; ?>

  <?php if ($error): ?>
    <div style="background:rgba(239,68,68,0.18); border:1px solid rgba(239,68,68,0.5); border-radius:12px; padding:12px 18px; color:#fca5a5; font-size:0.95rem; display:flex; align-items:center; gap:8px;">
      <span>⚠️</span> <strong><?= e($error) ?></strong>
    </div>
  <?php endif; ?>

  <!-- MASTER HUD -->
  <div class="wam-master-hud">
    <div class="wam-brand-area">
      <div class="wam-brand-badge-icon">📱</div>
      <div class="wam-brand-titles">
        <h1>WAManager <span class="wam-brand-tag">PRO DESKTOP SUITE</span></h1>
        <p class="wam-brand-sub">হোয়াটসঅ্যাপ মার্কেটিং, গ্রুপ গ্র্যাবার, ফিল্টার, মাল্টি-রোটেশন ও এআই সেলস ব্রেইন</p>
      </div>
    </div>

    <!-- LIVE STATUS PILLS & FULLSCREEN DESKTOP LAUNCHER -->
    <div class="wam-system-pills">
      <div class="wam-pill secure">
        <span class="wam-pulse"></span>
        <span>🛡️ অ্যান্টি-ব্যান শিল্ড: সক্রিয় (100% নিরাপদ)</span>
      </div>
      <div class="wam-pill ai-live">
        <span>🧠 চিফ মার্কেটিং এআই: অনলাইন</span>
      </div>
      <div class="wam-pill">
        <span>🔄 রোটেশন পুল: <?= $totalActiveAccounts ?>টি নম্বর</span>
      </div>
      <a href="/assets/wamanager/index.html" target="_blank" class="btn-wam-secondary" style="border-color:#10b981; color:#34d399; font-weight:700;">
        🖥️ ফুলস্ক্রিন ডেস্কটপ মোড (SPA)
      </a>
    </div>
  </div>

  <!-- METRICS CARDS -->
  <div class="wam-metrics-grid">
    <div class="wam-metric-card">
      <div class="wam-metric-label">
        <span>সংযুক্ত নম্বর পুল</span>
        <span>📱</span>
      </div>
      <div class="wam-metric-num" style="color:var(--wam-primary);"><?= $totalActiveAccounts ?> / <?= count($accountsPool) ?></div>
      <div class="wam-metric-sub">সক্রিয় রোটেশন অ্যাকাউন্টস</div>
    </div>

    <div class="wam-metric-card">
      <div class="wam-metric-label">
        <span>কন্টাক্ট ডাটাবেজ</span>
        <span>👥</span>
      </div>
      <div class="wam-metric-num" style="color:var(--wam-cyan);"><?= $totalContacts ?></div>
      <div class="wam-metric-sub">ভ্যালিড কন্টাক্ট ও লিড</div>
    </div>

    <div class="wam-metric-card">
      <div class="wam-metric-label">
        <span>অডিয়েন্স গ্রুপস</span>
        <span>📁</span>
      </div>
      <div class="wam-metric-num" style="color:var(--wam-purple);"><?= count($contactGroups) ?></div>
      <div class="wam-metric-sub">কাস্টম টার্গেটেড সেগমেন্ট</div>
    </div>

    <div class="wam-metric-card">
      <div class="wam-metric-label">
        <span>টু-ওয়ে লাইভ লিড</span>
        <span>💬</span>
      </div>
      <div class="wam-metric-num" style="color:var(--wam-amber);"><?= $totalLeads ?></div>
      <div class="wam-metric-sub">চ্যাট ও ফলো-আপ কিউ</div>
    </div>

    <div class="wam-metric-card">
      <div class="wam-metric-label">
        <span>আজকের ডেলিভারি কোটা</span>
        <span>🛡️</span>
      </div>
      <div class="wam-metric-num" style="color:#ffffff;"><?= $totalDailySent ?> / <?= ($totalDailySent + $totalDailyRemaining) ?></div>
      <div class="wam-metric-sub">অবশিষ্ট কোটা: <?= $totalDailyRemaining ?>টি</div>
    </div>
  </div>

  <!-- 10 COMPREHENSIVE CYBER TABS MATCHING DESKTOP SUITE -->
  <div class="wam-tabs-deck">
    <button type="button" class="wam-tab-btn <?= $activeTab === 'accounts' ? 'active' : '' ?>" onclick="switchWamTab('accounts')">
      <span>📱</span> <span>অ্যাকাউন্ট ও কিউআর</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'grabber' ? 'active' : '' ?>" onclick="switchWamTab('grabber')">
      <span>👥</span> <span>গ্রুপ গ্র্যাবার</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'filter' ? 'active' : '' ?>" onclick="switchWamTab('filter')">
      <span>🔍</span> <span>নম্বর ফিল্টার</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'contacts' ? 'active' : '' ?>" onclick="switchWamTab('contacts')">
      <span>📁</span> <span>কন্টাক্ট ও গ্রুপস</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'templates' ? 'active' : '' ?>" onclick="switchWamTab('templates')">
      <span>📜</span> <span>টেমপ্লেট লাইব্রেরি</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'broadcast' ? 'active' : '' ?>" onclick="switchWamTab('broadcast')">
      <span>📢</span> <span>স্মার্ট ব্রডকাস্ট</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'crm' ? 'active' : '' ?>" onclick="switchWamTab('crm')">
      <span>💬</span> <span>লাইভ সিআরএম</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'agents' ? 'active' : '' ?>" onclick="switchWamTab('agents')">
      <span>🧠</span> <span>চিফ এআই ডিরেক্টর</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'antiban' ? 'active' : '' ?>" onclick="switchWamTab('antiban')">
      <span>🛡️</span> <span>অ্যান্টি-ব্যান সেন্টিনেল</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'dispatch' ? 'active' : '' ?>" onclick="switchWamTab('dispatch')">
      <span>⚡</span> <span>অটো-ডিসপ্যাচ</span>
    </button>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 1: ACCOUNTS & QR MULTI-DEVICE ROTATION -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'accounts' ? 'active' : '' ?>" id="tab-accounts">
    <div class="wam-section-header">
      <div>
        <h2><span>📱</span> মাল্টি-অ্যাকাউন্ট ও কিউআর রোটেশন পুল (Anti-Ban Multi-Device)</h2>
        <p>একাধিক হোয়াটসঅ্যাপ নম্বর যুক্ত থাকলে স্বয়ংক্রিয়ভাবে একটির পর একটি নম্বর থেকে মেসেজ পাঠানো হয়, যার ফলে কোনো নম্বরে ব্যান হওয়ার ঝুঁকি থাকে না।</p>
      </div>
      <button type="button" class="btn-wam-primary" onclick="openAddAccountModal()">
        + নতুন WhatsApp নম্বর যুক্ত করুন
      </button>
    </div>

    <div class="wam-accounts-grid">
      <?php foreach ($accountsPool as $acc): 
          $pct = $acc['daily_limit'] > 0 ? min(100, round(($acc['daily_sent_today'] / $acc['daily_limit']) * 100)) : 0;
      ?>
        <div class="wam-account-card active">
          <div class="wam-account-header">
            <div class="wam-acc-info">
              <h3><?= e($acc['name']) ?></h3>
              <div class="wam-acc-phone"><?= e($acc['phone']) ?></div>
            </div>
            <span class="wam-pill secure" style="font-size:0.72rem;">
              ● <?= $acc['status'] === 'connected' ? 'সক্রিয় ও প্রস্তুত' : e($acc['status']) ?>
            </span>
          </div>

          <div style="font-size:0.8rem; color:#94a3b8; display:flex; justify-content:space-between; margin-top:4px;">
            <span>আজকের দৈনিক লিমিট কোটা:</span>
            <strong style="color:#ffffff;"><?= $acc['daily_sent_today'] ?> / <?= $acc['daily_limit'] ?> টি</strong>
          </div>
          <div class="wam-progress-bar">
            <div class="wam-progress-fill" style="width: <?= $pct ?>%;"></div>
          </div>
          <div style="font-size:0.75rem; color:#64748b; display:flex; justify-content:space-between;">
            <span>অবশিষ্ট কোটা: <strong style="color:#34d399;"><?= $acc['remaining_quota'] ?></strong> টি</span>
            <span>সংযোগ হেলথ: <strong style="color:#38bdf8;"><?= $acc['session_health'] ?>%</strong></span>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.05);">
            <span style="font-size:0.75rem; color:#94a3b8;">টাইপ: <strong><?= strtoupper(str_replace('_', ' ', $acc['provider_type'])) ?></strong></span>
            <form method="POST" onsubmit="return confirm('আপনি কি এই নম্বরটি রোটেশন পুল থেকে সরাতে চান?');" style="margin:0;">
              <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
              <input type="hidden" name="action" value="delete_account">
              <input type="hidden" name="account_id" value="<?= e($acc['id']) ?>">
              <button type="submit" class="btn-wam-danger">অপসারণ</button>
            </form>
          </div>
        </div>
      <?php endforeach; ?>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 2: WHATSAPP GROUP CONTACTS GRABBER -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'grabber' ? 'active' : '' ?>" id="tab-grabber">
    <div class="wam-section-header">
      <div>
        <h2><span>👥</span> হোয়াটসঅ্যাপ গ্রুপ কন্টাক্ট গ্র্যাবার (Group Contacts Extractor)</h2>
        <p>যেকোনো জয়েন করা হোয়াটসঅ্যাপ গ্রুপ থেকে মেম্বারদের ফোন নম্বর ১-ক্লিকে এক্সট্র্যাক্ট করে অডিয়েন্স গ্রুপে সেভ করুন।</p>
      </div>
    </div>

    <div style="display:grid; grid-template-columns:1fr 340px; gap:1.5rem;">
      <div>
        <form method="POST">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="action" value="grab_group_contacts">

          <div class="wam-form-group" style="margin-bottom:1rem;">
            <label>টার্গেট গ্রুপ নির্বাচন করুন (অথবা নতুন নাম দিন):</label>
            <select class="wam-form-select" name="target_group_id" id="grabberGroupSelect" onchange="toggleNewGroupInput(this.value)">
              <option value="new">+ নতুন অডিয়েন্স গ্রুপ তৈরি করুন</option>
              <?php foreach ($contactGroups as $cg): ?>
                <option value="<?= e($cg['id']) ?>"><?= e($cg['name']) ?> (<?= $cg['member_count'] ?> জন)</option>
              <?php endforeach; ?>
            </select>
          </div>

          <div class="wam-form-group" id="grabberNewGroupField" style="margin-bottom:1rem;">
            <label>নতুন গ্রুপের নাম:</label>
            <input type="text" class="wam-form-input" name="new_group_name" placeholder="যেমন: ফেসবুক মার্কেটার্স গ্রুপ ১">
          </div>

          <div class="wam-form-group" style="margin-bottom:1rem;">
            <label style="display:flex; justify-content:space-between;">
              <span>গ্রুপ মেম্বারদের টেক্সট বা চ্যাট এক্সপোর্ট পেস্ট করুন:</span>
              <span style="font-size:0.75rem; color:#34d399;">স্মার্ট রেজেক্স অটোমেটিক নম্বর আলাদা করবে</span>
            </label>
            <textarea class="wam-form-textarea" rows="10" name="raw_group_text" id="grabberTextInput" placeholder="WhatsApp Web বা মোবাইল থেকে গ্রুপ মেম্বারদের লিস্ট কপি করে এখানে পেস্ট করুন...&#10;যেমন: +8801715894521, 01968111593, +8801811223344" required></textarea>
          </div>

          <div style="display:flex; gap:10px;">
            <button type="submit" class="btn-wam-primary">
              👥 গ্রুপ নম্বরগুলো এক্সট্র্যাক্ট ও সেভ করুন
            </button>
            <button type="button" class="btn-wam-secondary" onclick="exportGrabberCsv()">
              📥 CSV এক্সপোর্ট করুন
            </button>
          </div>
        </form>
      </div>

      <!-- INSTRUCTIONS CARD -->
      <div style="background:#080d14; border:1px solid #1e293b; border-radius:14px; padding:1.25rem;">
        <h4 style="color:#ffffff; margin:0 0 10px; font-size:0.95rem; display:flex; align-items:center; gap:6px;">
          <span>💡</span> ব্যবহারের সহজ ৩টি ধাপ:
        </h4>
        <ol style="font-size:0.82rem; color:#94a3b8; padding-left:18px; line-height:1.6; margin:0 0 1rem;">
          <li>আপনার কম্পিউটার বা মোবাইলে <strong>WhatsApp Web</strong> খুলুন।</li>
          <li>টার্গেট গ্রুপের ভেতরে ঢুকে গ্রুপ হেডার/মেম্বার লিস্ট বা চ্যাট কপি করুন।</li>
          <li>বাম পাশের বক্সে পেস্ট করে <strong>'এক্সট্র্যাক্ট ও সেভ করুন'</strong> চাপুন।</li>
        </ol>
        <div style="font-size:0.78rem; color:#38bdf8; background:rgba(6,182,212,0.1); border:1px solid rgba(6,182,212,0.3); padding:10px; border-radius:8px;">
          🛡️ আমাদের এআই স্বয়ংক্রিয়ভাবে ডুপ্লিকেট নম্বর দূর করে এবং স্ট্যান্ডার্ড <code>+880...</code> ফরম্যাটে সাজিয়ে নেয়।
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 3: NUMBER FILTER & VALIDATOR -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'filter' ? 'active' : '' ?>" id="tab-filter">
    <div class="wam-section-header">
      <div>
        <h2><span>🔍</span> নম্বর ফিল্টার ও ভ্যালিডেটর (Bulk WhatsApp Number Validator)</h2>
        <p>ক্যাম্পেইনের আগে সক্রিয় হোয়াটসঅ্যাপ নম্বরগুলো যাচাই করুন যাতে কোনো ইনভ্যালিড নম্বরে মেসেজ পাঠাতে গিয়ে নম্বর ব্যান না হয়।</p>
      </div>
    </div>

    <form method="POST">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="filter_numbers">

      <div style="display:grid; grid-template-columns:1fr 340px; gap:1.5rem;">
        <div>
          <div class="wam-form-group" style="margin-bottom:1rem;">
            <label>যাচাই করার জন্য ফোন নম্বরগুলোর লিস্ট পেস্ট করুন (Newline / Comma):</label>
            <textarea class="wam-form-textarea" rows="8" name="raw_numbers_to_filter" placeholder="01711223344&#10;+8801968111593&#10;01822334455&#10;ভুল নম্বর যেমন 12345" required></textarea>
          </div>

          <div style="background:#080d14; border:1px solid #1e293b; border-radius:10px; padding:12px; margin-bottom:1rem; display:flex; flex-direction:column; gap:8px;">
            <label style="font-size:0.85rem; color:#ffffff; display:flex; align-items:center; gap:8px; cursor:pointer;">
              <input type="checkbox" name="save_valid_to_group" value="1" checked>
              <span><strong>ভ্যালিড নম্বরগুলো স্বয়ংক্রিয়ভাবে অডিয়েন্স গ্রুপে সেভ করুন</strong></span>
            </label>
            <div class="wam-form-group">
              <label style="font-size:0.78rem;">কোন গ্রুপে সেভ করবেন:</label>
              <select class="wam-form-select" name="filter_target_group" style="font-size:0.82rem; padding:6px 10px;">
                <option value="">-- সাধারণ কন্টাক্ট লিস্ট --</option>
                <?php foreach ($contactGroups as $cg): ?>
                  <option value="<?= e($cg['id']) ?>"><?= e($cg['name']) ?></option>
                <?php endforeach; ?>
              </select>
            </div>
          </div>

          <button type="submit" class="btn-wam-primary">
            🔍 নম্বরগুলো ফিল্টার ও ভ্যালিডেট করুন
          </button>
        </div>

        <!-- FILTER STATS -->
        <div>
          <?php if ($filterResults): ?>
            <div style="background:#080d14; border:1px solid var(--wam-border-glow); border-radius:14px; padding:1.25rem;">
              <h4 style="color:#ffffff; margin:0 0 10px; font-size:0.95rem;">📊 ফিল্টারিং ফলাফল:</h4>
              <div style="display:flex; flex-direction:column; gap:8px; font-size:0.85rem;">
                <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1e293b;">
                  <span>মোট স্ক্যান করা হয়েছে:</span>
                  <strong style="color:#ffffff;"><?= $filterResults['total'] ?> টি</strong>
                </div>
                <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1e293b;">
                  <span>সক্রিয় ও ভ্যালিড WhatsApp:</span>
                  <strong style="color:#34d399;"><?= $filterResults['valid_count'] ?> টি</strong>
                </div>
                <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1e293b;">
                  <span>ইনভ্যালিড / বাতিল:</span>
                  <strong style="color:#f87171;"><?= $filterResults['invalid_count'] ?> টি</strong>
                </div>
                <div style="display:flex; justify-content:space-between; padding:6px 0;">
                  <span>ডাটাবেজে সংরক্ষিত:</span>
                  <strong style="color:#38bdf8;"><?= $filterResults['saved_count'] ?> টি</strong>
                </div>
              </div>
            </div>
          <?php else: ?>
            <div style="background:#080d14; border:1px solid #1e293b; border-radius:14px; padding:1.25rem; color:#94a3b8; font-size:0.85rem;">
              <h4 style="color:#ffffff; margin:0 0 8px;">🛡️ ভ্যালিডেশনের নিয়মাবলী:</h4>
              <p style="margin:0 0 6px;">আমাদের ভ্যালিডেটর বাংলাদেশ ও আন্তর্জাতিক সব অপারেটর (+88013, 014, 015, 016, 017, 018, 019) স্বয়ংক্রিয়ভাবে চেক করে।</p>
              <p style="margin:0;">ভ্যালিড নম্বরগুলো ফিল্টার করে নিলে ক্যাম্পেইনের ডেলিভারি রেট ৯৯.৮% নিশ্চিত হয়।</p>
            </div>
          <?php endif; ?>
        </div>
      </div>
    </form>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 4: CONTACT GROUPS & AUDIENCE MANAGER -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'contacts' ? 'active' : '' ?>" id="tab-contacts">
    <div class="wam-section-header">
      <div>
        <h2><span>📁</span> কন্টাক্ট ও অডিয়েন্স গ্রুপ ম্যানেজার (Audience Segmentation)</h2>
        <p>গ্রাহকদের বিভিন্ন সেগমেন্টে ভাগ করুন (যেমন: ভিআইপি ক্রেতা, নতুন লিড, ইউটিউবারস) এবং আলাদা ক্যাম্পেইন পরিচালনা করুন।</p>
      </div>
      <button type="button" class="btn-wam-primary" onclick="openCreateGroupModal()">
        + নতুন অডিয়েন্স গ্রুপ তৈরি করুন
      </button>
    </div>

    <div class="wam-templates-grid">
      <?php if (empty($contactGroups)): ?>
        <div style="grid-column:1/-1; padding:20px; text-align:center; color:#64748b;">
          কোনো অডিয়েন্স গ্রুপ তৈরি করা হয়নি। নতুন গ্রুপ তৈরি করুন।
        </div>
      <?php else: ?>
        <?php foreach ($contactGroups as $cg): ?>
          <div class="wam-template-card">
            <div>
              <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <h3 style="margin:0; font-size:1rem; color:#ffffff;"><?= e($cg['name']) ?></h3>
                <span class="wam-pill secure" style="font-size:0.72rem;">
                  <?= $cg['member_count'] ?> জন মেম্বার
                </span>
              </div>
              <p style="font-size:0.82rem; color:#94a3b8; margin:6px 0 0;">
                <?= e($cg['description'] ?: 'কোনো বিবরণ দেওয়া নেই') ?>
              </p>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px;">
              <button type="button" class="btn-wam-secondary" onclick="openAddNumbersModal('<?= e($cg['id']) ?>', '<?= e($cg['name']) ?>')" style="font-size:0.78rem;">
                + নম্বর যোগ করুন
              </button>
              <a href="?tab=broadcast&target=group_<?= e($cg['id']) ?>" class="btn-wam-primary" style="font-size:0.78rem; padding:6px 12px;">
                📢 ক্যাম্পেইন পাঠান
              </a>
            </div>
          </div>
        <?php endforeach; ?>
      <?php endif; ?>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 5: PERSUASION TEMPLATES LIBRARY -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'templates' ? 'active' : '' ?>" id="tab-templates">
    <div class="wam-section-header">
      <div>
        <h2><span>📜</span> হাই-কনভার্সন পারসুয়েশন টেমপ্লেট লাইব্রেরি (Direct Response Vault)</h2>
        <p>অ্যালেক্স হরমুজি, রাসেল ব্রানসন ও রবার্ট সিয়ালদিনির শীর্ষস্থানীয় সেলস ফ্রেমওয়ার্কে সাজানো রেডি-মেড কপিরাইটিং টেমপ্লেট।</p>
      </div>
      <button type="button" class="btn-wam-primary" onclick="openCreateTemplateModal()">
        + নতুন কাস্টম টেমপ্লেট যোগ করুন
      </button>
    </div>

    <div class="wam-templates-grid">
      <!-- DEFAULT PRE-SEEDED ELITE TEMPLATES -->
      <?php foreach ($defaultEliteTemplates as $dt): ?>
        <div class="wam-template-card">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
              <h3 style="margin:0; font-size:0.95rem; color:#ffffff;"><?= e($dt['title']) ?></h3>
              <span class="badge-framework badge-hormozi"><?= e($dt['category']) ?></span>
            </div>
            <div style="margin-top:10px; background:#080d14; border:1px solid #1e293b; border-radius:8px; padding:10px; font-size:0.8rem; color:#cbd5e1; max-height:160px; overflow-y:auto; white-space:pre-wrap;">
              <?= e($dt['content']) ?>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px;">
            <button type="button" class="btn-wam-secondary" onclick="copyTemplateText(<?= json_encode($dt['content']) ?>)" style="font-size:0.75rem;">
              📋 কপি করুন
            </button>
            <button type="button" class="btn-wam-primary" onclick="useTemplateInBroadcast(<?= json_encode($dt['content']) ?>)" style="font-size:0.75rem; padding:6px 12px;">
              📢 ব্রডকাস্টে ব্যবহার করুন
            </button>
          </div>
        </div>
      <?php endforeach; ?>

      <!-- USER SAVED TEMPLATES -->
      <?php foreach ($savedTemplates as $st): ?>
        <div class="wam-template-card">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
              <h3 style="margin:0; font-size:0.95rem; color:#ffffff;"><?= e($st['title']) ?></h3>
              <span class="badge-framework badge-brunson"><?= e($st['category'] ?? 'Custom') ?></span>
            </div>
            <div style="margin-top:10px; background:#080d14; border:1px solid #1e293b; border-radius:8px; padding:10px; font-size:0.8rem; color:#cbd5e1; max-height:160px; overflow-y:auto; white-space:pre-wrap;">
              <?= e($st['content']) ?>
            </div>
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px;">
            <form method="POST" onsubmit="return confirm('টেমপ্লেটটি মুছে ফেলতে চান?');" style="margin:0;">
              <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
              <input type="hidden" name="action" value="delete_template">
              <input type="hidden" name="template_id" value="<?= e($st['id']) ?>">
              <button type="submit" class="btn-wam-danger">মুছুন</button>
            </form>
            <button type="button" class="btn-wam-primary" onclick="useTemplateInBroadcast(<?= json_encode($st['content']) ?>)" style="font-size:0.75rem; padding:6px 12px;">
              📢 ব্রডকাস্টে ব্যবহার করুন
            </button>
          </div>
        </div>
      <?php endforeach; ?>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 6: SMART CAMPAIGN & BROADCASTER -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'broadcast' ? 'active' : '' ?>" id="tab-broadcast">
    <div class="wam-section-header">
      <div>
        <h2><span>📢</span> স্মার্ট ক্যাম্পেইন ও ব্রডকাস্টার (Anti-Ban Safe Broadcast)</h2>
        <p>নিরাপদ সময় বিরতি ও স্মার্ট রোটেশন বজায় রেখে হাজার হাজার গ্রাহকের কাছে মেসেজ ব্রডকাস্ট করুন।</p>
      </div>
    </div>

    <form method="POST">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="broadcast_campaign">

      <div class="wam-form-grid">
        <div class="wam-form-group">
          <label>টার্গেট অডিয়েন্স নির্বাচন করুন:</label>
          <select class="wam-form-select" name="target_audience" id="campAudienceSelect">
            <option value="all_leads">🎯 সকল নতুন লিড ও ভিজিটর (<?= $totalLeads ?> জন)</option>
            <option value="all_paid">💼 সকল অনুমোদিত পেইড কাস্টমার (<?= $totalOrders ?> জন)</option>
            <?php foreach ($contactGroups as $cg): ?>
              <option value="group_<?= e($cg['id']) ?>">📁 <?= e($cg['name']) ?> (<?= $cg['member_count'] ?> জন)</option>
            <?php endforeach; ?>
            <option value="contacts">📂 সংরক্ষিত সাধারণ কন্টাক্ট ডাটাবেজ (<?= $totalContacts ?> জন)</option>
          </select>
        </div>

        <div class="wam-form-group">
          <label>প্রেরক অ্যাকাউন্ট:</label>
          <select class="wam-form-select" name="sending_account">
            <option value="smart_rotation">🔄 স্মার্ট রোটেশন পুল (৪টি নম্বর ব্যালেন্সিং - অ্যান্টি-ব্যান)</option>
            <?php foreach ($accountsPool as $acc): ?>
              <option value="<?= e($acc['id']) ?>"><?= e($acc['name']) ?> (<?= e($acc['phone']) ?>)</option>
            <?php endforeach; ?>
          </select>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 380px; gap:1.5rem; margin-top:1.25rem;">
        <div>
          <div class="wam-form-group">
            <label style="display:flex; justify-content:space-between;">
              <span>বার্তা কম্পোজার (Dynamic Tags: {name}, {package}, {link}, {coupon}):</span>
              <span style="font-size:0.75rem; color:#38bdf8;">ট্যাগগুলো স্বয়ংক্রিয়ভাবে প্রতিস্থাপিত হবে</span>
            </label>
            <textarea class="wam-form-textarea" rows="10" name="campaign_message" id="campMsgInput" oninput="updatePhoneMockup()"></textarea>
          </div>

          <div style="margin-top:1rem; background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); border-radius:10px; padding:12px; font-size:0.82rem; color:#fde68a;">
            🛡️ <strong>অ্যান্টি-ব্যান সুরক্ষা সক্রিয়:</strong> প্রতিটি মেসেজের মাঝে ২৫ থেকে ৫৫ সেকেন্ডের জিটার বিরতি থাকবে এবং প্রতি ১৫টি মেসেজ পর ৮ মিনিটের কুলডাউন রেস্ট বজায় রাখা হবে।
          </div>

          <div style="margin-top:1.25rem;">
            <button type="submit" class="btn-wam-primary" onclick="return confirm('আপনি কি নিশ্চিত যে অ্যান্টি-ব্যান মোডে এই ক্যাম্পেইনটি শুরু করতে চান?');">
              🚀 অ্যান্টি-ব্যান মোডে শিডিউল ডিসপ্যাচ করুন
            </button>
          </div>
        </div>

        <!-- LIVE SMARTPHONE PREVIEW -->
        <div>
          <div style="text-align:center; font-size:0.8rem; font-weight:700; color:#94a3b8; margin-bottom:8px;">
            📱 লাইভ হোয়াটসঅ্যাপ প্রিভিউ (গ্রাহক যেভাবে দেখবে)
          </div>
          <div class="wam-phone-mockup">
            <div class="wam-phone-header">
              <div style="width:36px; height:36px; border-radius:50%; background:#10B981; display:flex; align-items:center; justify-content:center; font-weight:800;">A</div>
              <div>
                <div style="font-weight:700; font-size:0.85rem;">AutoMovie Pro Official</div>
                <div style="font-size:0.7rem; color:#34d399;">Business Account • Verified</div>
              </div>
            </div>
            <div class="wam-phone-body">
              <div class="wam-bubble-out" id="phoneMockupText">
                মেসেজ লোড হচ্ছে...
              </div>
            </div>
          </div>
        </div>
      </div>
    </form>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 7: TWO-WAY LIVE CRM & CHAT -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'crm' ? 'active' : '' ?>" id="tab-crm">
    <div class="wam-section-header">
      <div>
        <h2><span>💬</span> টু-ওয়ে লাইভ সিআরএম ও চ্যাট ইনবক্স (Live 2-Way CRM)</h2>
        <p>গ্রাহকের সাথে সরাসরি হোয়াটসঅ্যাপ চ্যাট পরিচালনা করুন এবং এআই এজেন্টের মাধ্যমে স্মার্ট উত্তর পাঠান।</p>
      </div>
    </div>

    <div class="wam-crm-shell">
      <!-- LEFT THREADS -->
      <div class="wam-crm-threads">
        <div style="padding:10px 14px; background:#1e293b; color:#94a3b8; font-weight:700; font-size:0.8rem; display:flex; justify-content:space-between;">
          <span>সাম্প্রতিক কথোপকথন</span>
          <span><?= count($crmThreads) ?> জন</span>
        </div>

        <?php if (empty($crmThreads)): ?>
          <div style="padding:20px; text-align:center; color:#64748b; font-size:0.85rem;">
            কোনো মেসেজ হিস্ট্রি নেই
          </div>
        <?php else: ?>
          <?php foreach ($crmThreads as $idx => $th): ?>
            <div class="wam-thread-item <?= $idx === 0 ? 'active' : '' ?>" onclick="selectCrmThread('<?= e($th['name']) ?>', '<?= e($th['phone']) ?>', '<?= e($th['interest_package']) ?>', '<?= e($th['last_message']) ?>')">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <strong style="color:#ffffff; font-size:0.88rem;"><?= e($th['name'] ?: 'কাস্টমার') ?></strong>
                <span style="font-size:0.68rem; background:rgba(16,185,129,0.15); color:#34d399; padding:2px 6px; border-radius:4px;">
                  <?= e($th['status']) ?>
                </span>
              </div>
              <div style="font-size:0.75rem; color:#38bdf8; margin:2px 0;"><?= e($th['phone']) ?></div>
              <div style="font-size:0.78rem; color:#94a3b8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                <?= e($th['last_message'] ?: 'কোনো বার্তা নেই') ?>
              </div>
            </div>
          <?php endforeach; ?>
        <?php endif; ?>
      </div>

      <!-- RIGHT CHAT WORKSPACE -->
      <div class="wam-crm-main">
        <div style="padding:12px 16px; background:#111827; border-bottom:1px solid var(--wam-border); display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h3 style="margin:0; font-size:0.95rem; color:#ffffff;" id="crmActiveName">তানভীর আহমেদ</h3>
            <span style="font-size:0.75rem; color:#10B981;" id="crmActivePhone">+8801715894521</span>
            <span style="font-size:0.75rem; color:#94a3b8;" id="crmActivePkg"> • AutoMovie Pro Video Studio</span>
          </div>
          <a href="#" target="_blank" id="crmDirectWaBtn" class="btn-wam-secondary" style="font-size:0.75rem; padding:5px 10px;">
            📱 WhatsApp Web-এ খুলুন
          </a>
        </div>

        <div class="wam-crm-chat-body" id="crmChatBody">
          <div class="wam-bubble-in" id="crmUserLastBubble">
            আমার পিসিতে 4GB র‍্যাম, এটা দিয়ে কি ফুল 4K ভিডিও বানানো যাবে?
          </div>
          <div class="wam-bubble-out">
            Assalamu Alaikum তানভীর ভাই! আমি নীরব, AutoMovie Pro-এর টেকনিক্যাল স্পেশালিস্ট। জি অবশ্যই! আমাদের সফটওয়্যার 4GB র‍্যামেই চমৎকারভাবে কাজ করে।
          </div>
        </div>

        <form method="POST" class="wam-crm-chat-foot">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="action" value="crm_reply">
          <input type="hidden" name="lead_phone" id="crmInputPhone" value="8801715894521">

          <select class="wam-form-select" name="agent_choice" style="width:140px; font-size:0.8rem; padding:8px;">
            <option value="ayesha">আয়েশা (Care)</option>
            <option value="nirob" selected>নীরব (Tech)</option>
            <option value="tania">তানিয়া (Sales)</option>
          </select>

          <input type="text" class="wam-form-input" name="reply_text" id="crmReplyInput" placeholder="উত্তর লিখুন..." style="flex:1;" required>
          <button type="submit" class="btn-wam-primary" style="white-space:nowrap;">
            পাঠান (Send)
          </button>
        </form>
      </div>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 8: CENTRAL MARKETING AI DIRECTOR STUDIO & LIVE SANDBOX -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'agents' ? 'active' : '' ?>" id="tab-agents">
    <div class="wam-section-header">
      <div>
        <h2><span>🧠</span> চিফ মার্কেটিং ও সেলস ডিরেক্টর এআই স্টুডিও (Central Persuasion Brain)</h2>
        <p>ওয়েবসাইট চ্যাট, হোয়াটসঅ্যাপ ও ফেসবুকের সকল যোগাযোগ পরিচালনার কেন্দ্রীয় মার্কেটিং ডিরেক্টর ও ৩ জন সাব-এজেন্ট।</p>
      </div>
    </div>

    <!-- PERSUASION FRAMEWORKS ARCHITECTURE BANNER -->
    <div style="background:linear-gradient(135deg, rgba(16,185,129,0.1), rgba(139,92,246,0.1)); border:1px solid rgba(139,92,246,0.3); border-radius:14px; padding:1.25rem; margin-bottom:1.5rem;">
      <h3 style="color:#ffffff; font-size:1rem; margin:0 0 8px; display:flex; align-items:center; gap:8px;">
        <span>🌐</span> গ্লোবাল ৫টি শীর্ষস্থানীয় পারসুয়েশন ও সেলস ফ্রেমওয়ার্ক অন্তর্নির্মিত:
      </h3>
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">
        <span class="badge-framework badge-hormozi">Alex Hormozi ($100M Value Eq & Risk Reversal)</span>
        <span class="badge-framework badge-brunson">Russell Brunson (Hook-Story-Offer Bridge)</span>
        <span class="badge-framework badge-demo">Eugene Schwartz (5 Stages of Customer Awareness)</span>
        <span class="badge-framework badge-urgency">Robert Cialdini (Influence & Social Proof)</span>
        <span class="badge-framework" style="background:rgba(16,185,129,0.2); color:#34d399; border:1px solid rgba(16,185,129,0.4);">Chris Voss (Tactical Empathy & Black Swan)</span>
      </div>
    </div>

    <form method="POST">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="save_master_ai">

      <div class="wam-agents-grid">
        <!-- AGENT 1: AYESHA -->
        <div class="wam-agent-card">
          <div class="wam-agent-avatar-deck">
            <img class="wam-agent-avatar-img" src="/assets/img/agents/ayesha.png" alt="Ayesha Avatar" onerror="this.src='/assets/img/logo.png'">
            <div class="wam-agent-details">
              <h3>আয়েশা (Ayesha)</h3>
              <div class="wam-agent-role">কাস্টমার রিলেশনশিপ ও সাধারণ সহায়তা প্রধান</div>
              <label style="font-size:0.75rem; color:#34d399; display:inline-flex; align-items:center; gap:5px; margin-top:4px; cursor:pointer;">
                <input type="checkbox" name="agent_ayesha_active" value="1" <?= setting($pdo, 'agent_ayesha_active', '1') === '1' ? 'checked' : '' ?>>
                <span>সক্রিয় রাখুন (Active)</span>
              </label>
            </div>
          </div>
          <p style="font-size:0.82rem; color:#94a3b8; margin:0;">
            অত্যন্ত মিষ্টি, ভদ্র ও বিনয়ী ভাষায় গ্রাহকের শুভেচ্ছা বিনিময়, সফটওয়্যারের সারসংক্ষেপ ও সাধারণ প্রশ্নের সমাধান করে।
          </p>
          <div class="wam-form-group">
            <label>কাস্টম ইনস্ট্রাকশন / প্রম্পট:</label>
            <textarea class="wam-form-textarea" rows="3" name="ayesha_prompt" placeholder="আয়েশার আচরণ ও নির্দেশনা..."><?= e(setting($pdo, 'ayesha_custom_prompt', 'সর্বদা সালাম দিয়ে আন্তরিক ও সম্মানজনক ভাষায় কথা বলো। সফটওয়্যার কেনার প্রক্রিয়া সহজভাবে বুঝিয়ে দাও।')) ?></textarea>
          </div>
        </div>

        <!-- AGENT 2: NIROB -->
        <div class="wam-agent-card">
          <div class="wam-agent-avatar-deck">
            <img class="wam-agent-avatar-img" src="/assets/img/agents/nirob.png" alt="Nirob Avatar" onerror="this.src='/assets/img/logo.png'">
            <div class="wam-agent-details">
              <h3>নীরব (Nirob)</h3>
              <div class="wam-agent-role">সিনিয়র টেকনিক্যাল স্পেশালিস্ট ও সেটআপ গাইড</div>
              <label style="font-size:0.75rem; color:#34d399; display:inline-flex; align-items:center; gap:5px; margin-top:4px; cursor:pointer;">
                <input type="checkbox" name="agent_nirob_active" value="1" <?= setting($pdo, 'agent_nirob_active', '1') === '1' ? 'checked' : '' ?>>
                <span>সক্রিয় রাখুন (Active)</span>
              </label>
            </div>
          </div>
          <p style="font-size:0.82rem; color:#94a3b8; margin:0;">
            পিসির কনফিগারেশন (RAM, Windows, FFmpeg), ইনস্টলেশন গাইড, এরর সমাধান ও লোকাল রেন্ডারিং নিয়ে স্পষ্ট গাইড প্রদান করে।
          </p>
          <div class="wam-form-group">
            <label>কাস্টম ইনস্ট্রাকশন / প্রম্পট:</label>
            <textarea class="wam-form-textarea" rows="3" name="nirob_prompt" placeholder="নীরবের টেকনিক্যাল ইনস্ট্রাকশন..."><?= e(setting($pdo, 'nirob_custom_prompt', 'Windows 10/11 64-bit ও 4GB RAM হলে অনায়াসে চলবে। কোনো GPU দরকার নেই। ইনস্টলেশন ফাইল আনজিপ করে ব্যাচ ফাইল চালালেই সেটআপ শেষ।')) ?></textarea>
          </div>
        </div>

        <!-- AGENT 3: TANIA -->
        <div class="wam-agent-card">
          <div class="wam-agent-avatar-deck">
            <img class="wam-agent-avatar-img" src="/assets/img/agents/tania.png" alt="Tania Avatar" onerror="this.src='/assets/img/logo.png'">
            <div class="wam-agent-details">
              <h3>তানিয়া (Tania)</h3>
              <div class="wam-agent-role">অনবোর্ডিং ও সেলস কনভার্সন স্পেশালিস্ট</div>
              <label style="font-size:0.75rem; color:#34d399; display:inline-flex; align-items:center; gap:5px; margin-top:4px; cursor:pointer;">
                <input type="checkbox" name="agent_tania_active" value="1" <?= setting($pdo, 'agent_tania_active', '1') === '1' ? 'checked' : '' ?>>
                <span>সক্রিয় রাখুন (Active)</span>
              </label>
            </div>
          </div>
          <p style="font-size:0.82rem; color:#94a3b8; margin:0;">
            নতুন আগ্রহী লিডদের ফলো-আপ, প্যাকেজের মূল্যছাড় ও স্পেশাল 'SPECIAL500' ডিসকাউন্ট অফার দিয়ে সেলস ক্লোজ করে।
          </p>
          <div class="wam-form-group">
            <label>কাস্টম ইনস্ট্রাকশন / প্রম্পট:</label>
            <textarea class="wam-form-textarea" rows="3" name="tania_prompt" placeholder="তানিয়ার সেলস ইনস্ট্রাকশন..."><?= e(setting($pdo, 'tania_custom_prompt', 'প্যাকেজের মূল্য ৩,৯৯৯ টাকা, ২,৯৯৯ টাকা ও ১,৯৯৯ টাকা। আগ্রহী ক্রেতাকে SPECIAL500 কুপন কোড অফার করে দ্রুত বিকাশ/নগদে অর্ডার সম্পন্ন করতে সহায়তা করো।')) ?></textarea>
          </div>
        </div>
      </div>

      <div style="margin-top:1.25rem; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <label style="font-size:0.85rem; color:#cbd5e1; font-weight:700;">মাস্টার ডিসকাউন্ট কুপন কোড:</label>
          <input type="text" class="wam-form-input" style="width:160px; font-weight:800; color:#34d399; text-transform:uppercase;" name="master_discount_coupon" value="<?= e(setting($pdo, 'agent_discount_coupon', 'SPECIAL500')) ?>">
        </div>
        <button type="submit" class="btn-wam-primary">💾 এআই সেটিংস সংরক্ষণ করুন</button>
      </div>
    </form>

    <!-- INTERACTIVE MASTER AI LIVE SIMULATION SANDBOX -->
    <div style="margin-top:2rem; background:#080d14; border:1px solid var(--wam-border-glow); border-radius:14px; padding:1.5rem;">
      <h3 style="color:#ffffff; margin:0 0 10px; font-size:1.05rem; display:flex; align-items:center; gap:8px;">
        <span>⚡</span> সেন্ট্রাল এআই সাইকোলজিক্যাল সিমুলেটর (Live Interactive Sandbox)
      </h3>
      <p style="font-size:0.85rem; color:#94a3b8; margin:0 0 1rem;">
        যেকোনো গ্রাহকের আপত্তি বা প্রশ্ন লিখে টেস্ট করুন। সেন্ট্রাল এআই গ্রাহকের অ্যাওয়ারনেস স্টেজ চিহ্নিত করে স্বয়ংক্রিয়ভাবে সঠিক ফ্রেমওয়ার্কে কনভার্সন রেসপন্স তৈরি করবে:
      </p>

      <div class="wam-form-grid">
        <div class="wam-form-group">
          <label>এজেন্ট রাউটিং:</label>
          <select class="wam-form-select" id="simAgentSelect">
            <option value="auto">🤖 অটো রাউটিং (Master Brain স্বয়ংক্রিয় সিদ্ধান্ত নেবে)</option>
            <option value="ayesha">🌸 আয়েশা (Ayesha) — কাস্টমার কেয়ার ও ওয়েলকাম</option>
            <option value="nirob">💻 নীরব (Nirob) — টেকনিক্যাল ও সেটআপ সাপোর্ট</option>
            <option value="tania">🔥 তানিয়া (Tania) — সেলস ক্লোজার ও অফার</option>
          </select>
        </div>

        <div class="wam-form-group">
          <label>গ্রাহকের প্রশ্ন বা আপত্তি (Customer Input):</label>
          <input type="text" class="wam-form-input" id="simUserMessage" value="আমার পিসিতে 4GB RAM, এটা দিয়ে কি ফুল 4K ভিডিও বানিয়ে প্যাসিভ ইনকাম করা যাবে?" placeholder="গ্রাহকের প্রশ্ন লিখুন...">
        </div>
      </div>

      <div style="margin-top:12px; display:flex; gap:10px;">
        <button type="button" class="btn-wam-primary" id="simSubmitBtn" onclick="runLiveMasterAISimulation()">
          ⚡ এআই রেসপন্স জেনারেট করুন
        </button>
      </div>

      <!-- SIMULATION RESULT BOX -->
      <div id="simResultBox" style="margin-top:1.5rem; display:none;">
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:12px; padding:1rem; margin-bottom:1rem; display:flex; flex-wrap:wrap; gap:15px; font-size:0.82rem;">
          <div>🎯 সনাক্তকৃত স্টেজ: <strong style="color:#38bdf8;" id="simDetectedStage">Problem Aware</strong></div>
          <div>💡 ফ্রেমওয়ার্ক: <strong style="color:#fbbf24;" id="simAppliedFramework">Hormozi Value Eq</strong></div>
          <div>👤 নির্বাচিত স্পেশালিস্ট: <strong style="color:#34d399;" id="simSelectedAgent">Ayesha Support</strong></div>
        </div>

        <div class="wam-phone-mockup" style="max-width:550px;">
          <div class="wam-phone-header">
            <div style="width:36px; height:36px; border-radius:50%; background:#10B981; display:flex; align-items:center; justify-content:center; font-weight:800;" id="simHeaderAvatar">A</div>
            <div>
              <div style="font-weight:700; font-size:0.9rem;" id="simHeaderName">Ayesha Support</div>
              <div style="font-size:0.7rem; color:#34d399;">Active Now • AutoMovie Pro Official</div>
            </div>
          </div>
          <div class="wam-phone-body">
            <div class="wam-bubble-in" id="simUserBubble">
              আমার পিসিতে 4GB RAM...
            </div>
            <div class="wam-bubble-out" id="simAgentBubble">
              জেনারেট হচ্ছে...
            </div>
          </div>
        </div>

        <div id="simSuggestionsDeck" style="margin-top:12px; display:flex; flex-wrap:wrap; gap:8px; justify-content:center;"></div>
      </div>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 9: ANTI-BAN SENTINEL & DELIVERY GUARD -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'antiban' ? 'active' : '' ?>" id="tab-antiban">
    <div class="wam-section-header">
      <div>
        <h2><span>🛡️</span> অ্যান্টি-ব্যান অটোনোমাস সেন্টিনেল ও ডেলিভারি গার্ড সেটিংস</h2>
        <p>মেটা ও হোয়াটসঅ্যাপের পলিসি শতভাগ মেনে চলতে অ্যালগরিদম ভিত্তিক রোটেশন, জৈবিক জিটার ডিলে ও ব্যাচ কুলডাউন নিয়ন্ত্রণ করুন।</p>
      </div>
    </div>

    <form method="POST">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="save_antiban">

      <div class="wam-form-grid">
        <div class="wam-form-group">
          <label>ইন্টার-মেসেজ মিনিমাম ডিলে (সেকেন্ড):</label>
          <input type="number" class="wam-form-input" name="antiban_delay_min" value="<?= $antiban['antiban_delay_min'] ?>" min="15" max="60" required>
          <span style="font-size:0.75rem; color:#64748b;">মেসেজের মাঝে সর্বনিম্ন বিরতি (ডিফল্ট: ২৫ সেকেন্ড)</span>
        </div>

        <div class="wam-form-group">
          <label>ইন্টার-মেসেজ ম্যাক্সিমাম ডিলে (সেকেন্ড):</label>
          <input type="number" class="wam-form-input" name="antiban_delay_max" value="<?= $antiban['antiban_delay_max'] ?>" min="30" max="120" required>
          <span style="font-size:0.75rem; color:#64748b;">মেসেজের মাঝে সর্বোচ্চ বিরতি (ডিফল্ট: ৫৫ সেকেন্ড)</span>
        </div>

        <div class="wam-form-group">
          <label>ব্যাচ সাইজ (কয়টি মেসেজ পর কুলডাউন বিরতি):</label>
          <input type="number" class="wam-form-input" name="antiban_batch_size" value="<?= $antiban['antiban_batch_size'] ?>" min="5" max="30" required>
          <span style="font-size:0.75rem; color:#64748b;">নির্দিষ্ট সংখ্যক মেসেজ পাঠানোর পর লম্বা বিরতি (ডিফল্ট: ১৫টি)</span>
        </div>

        <div class="wam-form-group">
          <label>ব্যাচ কুলডাউন বিরতির সময় (সেকেন্ড):</label>
          <input type="number" class="wam-form-input" name="antiban_batch_pause_seconds" value="<?= $antiban['antiban_batch_pause_seconds'] ?>" min="120" max="1800" required>
          <span style="font-size:0.75rem; color:#64748b;">৪৮০ সেকেন্ড = ৮ মিনিট কুলডাউন বিরতি</span>
        </div>

        <div class="wam-form-group">
          <label>দৈনিক সর্বোচ্চ আউটবাউন্ড কোটা (প্রতি নম্বর):</label>
          <input type="number" class="wam-form-input" name="antiban_daily_cap_per_number" value="<?= $antiban['antiban_daily_cap_per_number'] ?>" min="20" max="100" required>
          <span style="font-size:0.75rem; color:#64748b;">প্রতিটি নম্বরে দিনে নিরাপদ মেসেজ সীমা (ডিফল্ট: ৬৫টি)</span>
        </div>
      </div>

      <div style="margin-top:1.5rem; background:#080d14; border:1px solid #1e293b; border-radius:12px; padding:1.25rem; display:flex; flex-direction:column; gap:12px;">
        <h4 style="color:#ffffff; margin:0 0 6px; font-size:0.95rem;">🚨 স্মার্ট সুরক্ষামূলক সুইচ ও বাইপাস পলিসি:</h4>

        <label style="font-size:0.85rem; color:#e2e8f0; display:flex; align-items:center; gap:8px; cursor:pointer;">
          <input type="checkbox" name="antiban_priority_bypass" value="1" <?= $antiban['antiban_priority_bypass'] ? 'checked' : '' ?>>
          <span><strong>ইনবাউন্ড গ্রাহক প্রায়োরিটি বাইপাস (Inbound & Emergency Priority Bypass):</strong> দৈনিক কোটা শেষ হলেও বা কুলডাউন চলাকালেও কোনো কাস্টমার প্রশ্ন করলে বা অর্ডার অনুমোদিত হলে সাথে সাথে ০ সেকেন্ড ডিলেতে উত্তর পাঠানো হবে।</span>
        </label>

        <label style="font-size:0.85rem; color:#e2e8f0; display:flex; align-items:center; gap:8px; cursor:pointer;">
          <input type="checkbox" name="antiban_smart_rotation" value="1" <?= $antiban['antiban_smart_rotation'] ? 'checked' : '' ?>>
          <span><strong>স্মার্ট মাল্টি-নম্বর রোটেশন পুল (Smart Multi-Number Rotation):</strong> একটি নম্বরে লিমিট শেষ হলে স্বয়ংক্রিয়ভাবে পরবর্তী উপলব্ধ নম্বর থেকে মেসেজ পাঠানো হবে।</span>
        </label>

        <label style="font-size:0.85rem; color:#e2e8f0; display:flex; align-items:center; gap:8px; cursor:pointer;">
          <input type="checkbox" name="antiban_human_jitter" value="1" <?= $antiban['antiban_human_jitter'] ? 'checked' : '' ?>>
          <span><strong>হিউম্যান টাইপিং ও দৈবচয়ন জিটার (Organic Human Jitter):</strong> রোবোটিক আচরণ এড়াতে প্রতিটি মেসেজের সময়ে ২ থেকে ৮ সেকেন্ডের মানুষের মত অনিয়মিত গ্যাপ যুক্ত করা।</span>
        </label>
      </div>

      <div style="margin-top:1.25rem; display:flex; justify-content:flex-end;">
        <button type="submit" class="btn-wam-primary">🛡️ অ্যান্টি-ব্যান সেটিংস কার্যকর করুন</button>
      </div>
    </form>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 10: INSTANT TRIGGERS & DISPATCH HISTORY -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'dispatch' ? 'active' : '' ?>" id="tab-dispatch">
    <div class="wam-section-header">
      <div>
        <h2><span>⚡</span> কাস্টমার রিকোয়েস্ট অটো-ডিসপ্যাচ ও লাইসেন্স ডেলিভারি</h2>
        <p>ওয়েবসাইট অর্ডার, পেমেন্ট অনুমোদন বা ডেমো চাইলে স্বয়ংক্রিয়ভাবে অ্যাক্টিভেশন ক্রেডেনশিয়াল হোয়াটসঅ্যাপে প্রেরণ করা হয়।</p>
      </div>
    </div>

    <!-- QUICK MANUAL TRIGGER FORM -->
    <div style="background:#080d14; border:1px solid #1e293b; border-radius:14px; padding:1.5rem; margin-bottom:1.5rem;">
      <h3 style="color:#ffffff; margin:0 0 12px; font-size:1.05rem;">⚡ ম্যানুয়াল কাস্টমার ডিসপ্যাচ টেস্ট</h3>
      <form method="POST">
        <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
        <input type="hidden" name="action" value="quick_dispatch">

        <div class="wam-form-grid">
          <div class="wam-form-group">
            <label>ট্রিগার ধরণ:</label>
            <select class="wam-form-select" name="trigger_type" required>
              <option value="order_approved">🎉 পেমেন্ট অনুমোদন + লাইসেন্স ডেলিভারি (Order Approved)</option>
              <option value="order_placed">⏳ নতুন অর্ডার সাবমিশন নোটিফিকেশন (Order Placed)</option>
              <option value="demo_inquiry">🎬 ডেমো ও ব্রোশিউর রিকোয়েস্ট (Demo Inquiry)</option>
              <option value="care_checkin">🤝 কাস্টমার ওয়েলফেয়ার চেক-ইন (Customer Care Check-in)</option>
              <option value="version_update">📢 নতুন সফটওয়্যার ভার্সন আপডেট (Version Update)</option>
            </select>
          </div>

          <div class="wam-form-group">
            <label>গ্রাহকের নাম:</label>
            <input type="text" class="wam-form-input" name="customer_name" placeholder="যেমন: তানভীর আহমেদ" required>
          </div>

          <div class="wam-form-group">
            <label>হোয়াটসঅ্যাপ নম্বর:</label>
            <input type="text" class="wam-form-input" name="customer_phone" placeholder="যেমন: +8801711223344" required>
          </div>

          <div class="wam-form-group">
            <label>প্যাকেজ / ভার্সন:</label>
            <input type="text" class="wam-form-input" name="package_name" value="AutoMovie Pro 4K Video Studio (৳৩,৯৯৯)">
          </div>
        </div>

        <div style="margin-top:1.25rem;">
          <button type="submit" class="btn-wam-primary">
            🚀 তাৎক্ষণিক হোয়াটসঅ্যাপ বার্তা প্রেরণ করুন
          </button>
        </div>
      </form>
    </div>

    <!-- RECENT DISPATCHES TABLE -->
    <h3 style="color:#ffffff; margin:0 0 10px; font-size:1.05rem;">📋 সাম্প্রতিক প্রেরিত বার্তার ট্র্যাকিং লগ (Recent Dispatches)</h3>
    <table class="wam-table">
      <thead>
        <tr>
          <th>আইডি</th>
          <th>ট্রিগার ধরণ</th>
          <th>গ্রাহকের নাম</th>
          <th>ফোন নম্বর</th>
          <th>প্রেরিত অ্যাকাউন্ট</th>
          <th>স্ট্যাটাস</th>
          <th>সময়</th>
        </tr>
      </thead>
      <tbody>
        <?php if (empty($recentDispatches)): ?>
          <tr><td colspan="7" style="text-align:center; color:#64748b;">কোনো ডিসপ্যাচ রেকর্ড পাওয়া যায়নি</td></tr>
        <?php else: ?>
          <?php foreach ($recentDispatches as $disp): ?>
            <tr>
              <td style="font-family:monospace; color:#94a3b8;"><?= e(substr((string)$disp['id'], 0, 14)) ?></td>
              <td>
                <span class="wam-pill" style="font-size:0.7rem; padding:2px 8px;">
                  <?= e(ucfirst(str_replace('_', ' ', (string)$disp['trigger_type']))) ?>
                </span>
              </td>
              <td style="font-weight:700; color:#ffffff;"><?= e((string)$disp['customer_name']) ?></td>
              <td style="color:var(--wam-primary); font-family:monospace;"><?= e((string)$disp['phone']) ?></td>
              <td style="font-size:0.78rem; color:#cbd5e1;"><?= e((string)($disp['package_name'] ?? 'Primary Account')) ?></td>
              <td>
                <span style="color:#34d399; font-weight:700;">✓ ডেলিভার্ড</span>
              </td>
              <td style="font-size:0.75rem; color:#64748b;"><?= e((string)$disp['created_at']) ?></td>
            </tr>
          <?php endforeach; ?>
        <?php endif; ?>
      </tbody>
    </table>
  </div>

</div>

<!-- ========================================================================= -->
<!-- MODALS: ADD ACCOUNT, CREATE GROUP, ADD NUMBERS, CREATE TEMPLATE -->
<!-- ========================================================================= -->

<!-- 1. ADD NEW NUMBER MODAL -->
<div id="addAccountModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:99999; align-items:center; justify-content:center; padding:1.5rem;">
  <div style="background:#0f172a; border:1px solid var(--wam-border-glow); border-radius:18px; width:100%; max-width:550px; overflow:hidden; box-shadow:0 25px 60px rgba(0,0,0,0.8);">
    <div style="background:#1e293b; padding:1.25rem 1.5rem; display:flex; justify-content:space-between; align-items:center;">
      <h3 style="margin:0; font-size:1.1rem; color:#ffffff; display:flex; align-items:center; gap:8px;">
        <span>📱</span> রোটেশন পুলে নতুন WhatsApp নম্বর যুক্ত করুন
      </h3>
      <button type="button" onclick="closeAddAccountModal()" style="background:none; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer;">&times;</button>
    </div>
    <form method="POST" style="padding:1.5rem;">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="add_account">

      <div class="wam-form-group" style="margin-bottom:1rem;">
        <label>অ্যাকাউন্ট লেবেল / পরিচয়:</label>
        <input type="text" class="wam-form-input" name="account_name" placeholder="যেমন: হেল্পলাইন নম্বর ২ বা সেলস সাপোর্ট" required>
      </div>

      <div class="wam-form-group" style="margin-bottom:1rem;">
        <label>হোয়াটসঅ্যাপ ফোন নম্বর:</label>
        <input type="text" class="wam-form-input" name="account_phone" placeholder="যেমন: +8801700112233" required>
      </div>

      <div class="wam-form-group" style="margin-bottom:1rem;">
        <label>কানেকশন মেথড:</label>
        <select class="wam-form-select" name="provider_type">
          <option value="cloud_api">অফিসিয়াল মেটা ক্লাউড এপিআই (Meta Cloud API)</option>
          <option value="qr_session">ডেস্কটপ কিউআর সেশন (WhatsApp Web Multi-Device)</option>
        </select>
      </div>

      <div class="wam-form-group" style="margin-bottom:1.5rem;">
        <label>দৈনিক সর্বোচ্চ নিরাপদ আউটবাউন্ড লিমিট:</label>
        <input type="number" class="wam-form-input" name="daily_limit" value="65" min="20" max="100">
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button type="button" class="btn-wam-secondary" onclick="closeAddAccountModal()">বাতিল</button>
        <button type="submit" class="btn-wam-primary">+ রোটেশন পুলে যুক্ত করুন</button>
      </div>
    </form>
  </div>
</div>

<!-- 2. CREATE GROUP MODAL -->
<div id="createGroupModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:99999; align-items:center; justify-content:center; padding:1.5rem;">
  <div style="background:#0f172a; border:1px solid var(--wam-border-glow); border-radius:18px; width:100%; max-width:500px; overflow:hidden;">
    <div style="background:#1e293b; padding:1.25rem 1.5rem; display:flex; justify-content:space-between; align-items:center;">
      <h3 style="margin:0; font-size:1.05rem; color:#ffffff;">📁 নতুন অডিয়েন্স গ্রুপ তৈরি করুন</h3>
      <button type="button" onclick="closeCreateGroupModal()" style="background:none; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer;">&times;</button>
    </div>
    <form method="POST" style="padding:1.5rem;">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="create_contact_group">

      <div class="wam-form-group" style="margin-bottom:1rem;">
        <label>গ্রুপের নাম:</label>
        <input type="text" class="wam-form-input" name="group_name" placeholder="যেমন: ভিআইপি ইউটিউবারস" required>
      </div>

      <div class="wam-form-group" style="margin-bottom:1.5rem;">
        <label>বিবরণ (ঐচ্ছিক):</label>
        <textarea class="wam-form-textarea" rows="3" name="group_desc" placeholder="গ্রুপের উদ্দেশ্য বা অডিয়েন্স বিবরণ..."></textarea>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button type="button" class="btn-wam-secondary" onclick="closeCreateGroupModal()">বাতিল</button>
        <button type="submit" class="btn-wam-primary">তৈরি করুন</button>
      </div>
    </form>
  </div>
</div>

<!-- 3. ADD NUMBERS TO GROUP MODAL -->
<div id="addNumbersModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:99999; align-items:center; justify-content:center; padding:1.5rem;">
  <div style="background:#0f172a; border:1px solid var(--wam-border-glow); border-radius:18px; width:100%; max-width:520px; overflow:hidden;">
    <div style="background:#1e293b; padding:1.25rem 1.5rem; display:flex; justify-content:space-between; align-items:center;">
      <h3 style="margin:0; font-size:1.05rem; color:#ffffff;" id="addNumbersModalTitle">গ্রুপে নম্বর যোগ করুন</h3>
      <button type="button" onclick="closeAddNumbersModal()" style="background:none; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer;">&times;</button>
    </div>
    <form method="POST" style="padding:1.5rem;">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="add_manual_numbers_to_group">
      <input type="hidden" name="group_id" id="addNumbersModalGid" value="">

      <div class="wam-form-group" style="margin-bottom:1.5rem;">
        <label>ফোন নম্বরগুলো পেস্ট করুন (প্রতি লাইনে একটি বা কমা দিয়ে):</label>
        <textarea class="wam-form-textarea" rows="8" name="manual_numbers" placeholder="01711223344&#10;+8801968111593&#10;01822334455" required></textarea>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button type="button" class="btn-wam-secondary" onclick="closeAddNumbersModal()">বাতিল</button>
        <button type="submit" class="btn-wam-primary">নম্বর যোগ করুন</button>
      </div>
    </form>
  </div>
</div>

<!-- 4. CREATE TEMPLATE MODAL -->
<div id="createTemplateModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.8); z-index:99999; align-items:center; justify-content:center; padding:1.5rem;">
  <div style="background:#0f172a; border:1px solid var(--wam-border-glow); border-radius:18px; width:100%; max-width:580px; overflow:hidden;">
    <div style="background:#1e293b; padding:1.25rem 1.5rem; display:flex; justify-content:space-between; align-items:center;">
      <h3 style="margin:0; font-size:1.05rem; color:#ffffff;">📜 নতুন কনভার্সন টেমপ্লেট তৈরি করুন</h3>
      <button type="button" onclick="closeCreateTemplateModal()" style="background:none; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer;">&times;</button>
    </div>
    <form method="POST" style="padding:1.5rem;">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="create_template">

      <div class="wam-form-grid" style="margin-bottom:1rem;">
        <div class="wam-form-group">
          <label>টেমপ্লেটের নাম:</label>
          <input type="text" class="wam-form-input" name="template_title" placeholder="যেমন: উইকেন্ড স্পেশাল অফার" required>
        </div>
        <div class="wam-form-group">
          <label>ক্যাটাগরি:</label>
          <select class="wam-form-select" name="template_category">
            <option value="Hormozi Offer">Hormozi Offer</option>
            <option value="Brunson Bridge">Brunson Bridge</option>
            <option value="Urgency Flash">Urgency Flash</option>
            <option value="Customer Care">Customer Care</option>
            <option value="General">General</option>
          </select>
        </div>
      </div>

      <div class="wam-form-group" style="margin-bottom:1.5rem;">
        <label>মেসেজ কনটেন্ট (ট্যাগ: {name}, {package}, {link}, {coupon}):</label>
        <textarea class="wam-form-textarea" rows="7" name="template_content" placeholder="Assalamu Alaikum {name}! আপনার জন্য বিশেষ অফার..." required></textarea>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button type="button" class="btn-wam-secondary" onclick="closeCreateTemplateModal()">বাতিল</button>
        <button type="submit" class="btn-wam-primary">টেমপ্লেট সেভ করুন</button>
      </div>
    </form>
  </div>
</div>

<script>
  // Tab Switching
  function switchWamTab(tabId) {
    document.querySelectorAll('.wam-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.wam-panel').forEach(p => p.classList.remove('active'));
    
    const clickedBtn = Array.from(document.querySelectorAll('.wam-tab-btn')).find(b => b.getAttribute('onclick')?.includes(tabId));
    if (clickedBtn) clickedBtn.classList.add('active');

    const target = document.getElementById('tab-' + tabId);
    if (target) target.classList.add('active');

    // Update URL without reload
    const url = new URL(window.location);
    url.searchParams.set('tab', tabId);
    window.history.replaceState({}, '', url);
  }

  // Modals
  function openAddAccountModal() { document.getElementById('addAccountModal').style.display = 'flex'; }
  function closeAddAccountModal() { document.getElementById('addAccountModal').style.display = 'none'; }
  function openCreateGroupModal() { document.getElementById('createGroupModal').style.display = 'flex'; }
  function closeCreateGroupModal() { document.getElementById('createGroupModal').style.display = 'none'; }

  function openAddNumbersModal(gid, gname) {
    document.getElementById('addNumbersModalGid').value = gid;
    document.getElementById('addNumbersModalTitle').innerText = gname + ' - এ নম্বর যোগ করুন';
    document.getElementById('addNumbersModal').style.display = 'flex';
  }
  function closeAddNumbersModal() { document.getElementById('addNumbersModal').style.display = 'none'; }

  function openCreateTemplateModal() { document.getElementById('createTemplateModal').style.display = 'flex'; }
  function closeCreateTemplateModal() { document.getElementById('createTemplateModal').style.display = 'none'; }

  function toggleNewGroupInput(val) {
    const field = document.getElementById('grabberNewGroupField');
    if (field) field.style.display = (val === 'new') ? 'flex' : 'none';
  }

  // Group Grabber CSV Export
  function exportGrabberCsv() {
    const text = document.getElementById('grabberTextInput').value;
    const matches = text.match(/(\+?8801[3-9]\d{8}|01[3-9]\d{8}|\+?[1-9]\d{9,14})/g) || [];
    if (matches.length === 0) {
      alert('এক্সপোর্ট করার মতো কোনো বৈধ ফোন নম্বর পাওয়া যায়নি।');
      return;
    }
    const unique = Array.from(new Set(matches));
    let csv = "Phone Number\n" + unique.join("\n");
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "whatsapp_group_contacts_" + Date.now() + ".csv";
    link.click();
  }

  // Template utilities
  function copyTemplateText(content) {
    navigator.clipboard.writeText(content).then(() => {
      alert('টেমপ্লেট সফলভাবে ক্লিপবোর্ডে কপি হয়েছে!');
    });
  }

  function useTemplateInBroadcast(content) {
    switchWamTab('broadcast');
    document.getElementById('campMsgInput').value = content;
    updatePhoneMockup();
    window.scrollTo({ top: document.getElementById('tab-broadcast').offsetTop - 50, behavior: 'smooth' });
  }

  // LIVE MASTER AI SANDBOX SIMULATION (AJAX Call to MarketingMasterBrain)
  async function runLiveMasterAISimulation() {
    const userMsg = document.getElementById('simUserMessage').value.trim();
    const reqAgent = document.getElementById('simAgentSelect').value;
    const submitBtn = document.getElementById('simSubmitBtn');
    const resultBox = document.getElementById('simResultBox');
    const userBubble = document.getElementById('simUserBubble');
    const agentBubble = document.getElementById('simAgentBubble');
    const stageBadge = document.getElementById('simDetectedStage');
    const fwBadge = document.getElementById('simAppliedFramework');
    const agentBadge = document.getElementById('simSelectedAgent');
    const headerName = document.getElementById('simHeaderName');
    const headerAvatar = document.getElementById('simHeaderAvatar');
    const sugDeck = document.getElementById('simSuggestionsDeck');

    if (!userMsg) {
      alert('অনুগ্রহ করে গ্রাহকের প্রশ্ন লিখুন।');
      return;
    }

    userBubble.innerText = userMsg;
    agentBubble.innerText = 'চিফ মার্কেটিং ডিরেক্টর সাইকোলজিক্যাল রেসপন্স প্রস্তুত করছেন... ⏳';
    resultBox.style.display = 'block';
    submitBtn.disabled = true;

    try {
      const resp = await fetch('?ajax=simulate_ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_message: userMsg,
          requested_agent: reqAgent,
          lead_name: 'কাস্টমার'
        })
      });

      const data = await resp.json();
      if (data && data.ok) {
        agentBubble.innerText = data.reply;
        const meta = data.meta || {};
        stageBadge.innerText = meta.awareness_stage || 'Problem Aware';
        fwBadge.innerText = meta.persuasion_framework || 'Hormozi Value Eq + Cialdini';
        
        const agentName = meta.selected_agent === 'nirob' ? 'নীরব (Tech Specialist)' : (meta.selected_agent === 'tania' ? 'তানিয়া (Sales Closer)' : 'আয়েশা (Customer Care)');
        agentBadge.innerText = agentName;
        headerName.innerText = agentName;
        headerAvatar.innerText = meta.selected_agent === 'nirob' ? 'N' : (meta.selected_agent === 'tania' ? 'T' : 'A');
        headerAvatar.style.background = meta.selected_agent === 'nirob' ? '#06b6d4' : (meta.selected_agent === 'tania' ? '#8b5cf6' : '#10b981');

        sugDeck.innerHTML = '';
        if (meta.suggestions && Array.isArray(meta.suggestions)) {
          meta.suggestions.forEach(s => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn-wam-secondary';
            btn.style.fontSize = '0.75rem';
            btn.innerText = s;
            btn.onclick = () => {
              document.getElementById('simUserMessage').value = s;
              runLiveMasterAISimulation();
            };
            sugDeck.appendChild(btn);
          });
        }
      } else {
        agentBubble.innerText = 'দুঃখিত, সিমুলেশন রেসপন্স জেনারেট করা যায়নি।';
      }
    } catch (e) {
      console.error(e);
      agentBubble.innerText = 'সার্ভার যোগাযোগে সাময়িক ত্রুটি। অনুগ্রহ করে আবার চেষ্টা করুন।';
    } finally {
      submitBtn.disabled = false;
    }
  }

  // CRM Thread Selection
  function selectCrmThread(name, phone, pkg, msg) {
    document.getElementById('crmActiveName').innerText = name;
    document.getElementById('crmActivePhone').innerText = phone;
    document.getElementById('crmActivePkg').innerText = ' • ' + (pkg || 'General Visitor');
    document.getElementById('crmInputPhone').value = phone;
    document.getElementById('crmUserLastBubble').innerText = msg || 'কোনো সাম্প্রতিক বার্তা নেই';
    document.getElementById('crmDirectWaBtn').href = 'https://wa.me/' + phone.replace(/[^0-9]/g, '');
  }

  // Phone Mockup update in Broadcast
  function updatePhoneMockup() {
    const text = document.getElementById('campMsgInput').value;
    document.getElementById('phoneMockupText').innerText = text.replace('{name}', 'তানভীর আহমেদ').replace('{package}', 'Video Studio').replace('{coupon}', 'SPECIAL500').replace('{link}', 'https://automoviepro.com');
  }

  document.addEventListener('DOMContentLoaded', function() {
    const defaultBroadcastMsg = "Assalamu Alaikum {name}!\n\nআপনি কি কোনো ভিডিও এডিটিং দক্ষতা ছাড়াই দিনে ৩-৫টি ভাইরাল ভিডিও বানিয়ে প্যাসিভ ইনকাম শুরু করতে চান?\n\nAutoMovie Pro-এর আজকের গ্র্যান্ড স্ল্যাম অফার:\n• ৩,৯৯৯ টাকার ফুল ভিডিও স্টুডিও কিনলে সাথে পাচ্ছেন রেডি-মেড ১০০+ ভাইরাল স্ক্রিপ্ট ভল্ট সম্পূর্ণ ফ্রি।\n• ১৮টি চ্যানেলে স্বয়ংক্রিয় শিডিউলিং ও লোকাল পিসি সিকিউরিটি।\n• ১০০% রিপ্লেসমেন্ট ও মানি-ব্যাক ওয়ারেন্টি গ্যারান্টি!\n\nঅর্ডার করতে ভিজিট করুন: https://automoviepro.com/order.php\nকুপন কোড: SPECIAL500";
    if (document.getElementById('campMsgInput') && !document.getElementById('campMsgInput').value) {
      document.getElementById('campMsgInput').value = defaultBroadcastMsg;
      updatePhoneMockup();
    }
  });
</script>

<?php
admin_footer();
