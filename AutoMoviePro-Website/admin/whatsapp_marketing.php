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
                $message = "নতুন নম্বর '{$accName}' (+{$cleanPhone}) সফলভাবে রোটেশন পুলে যুক্ত হয়েছে!";
                $activeTab = 'accounts';
            }
        }

        // 3. DELETE ACCOUNT FROM POOL
        elseif ($action === 'delete_account') {
            $accId = trim((string) ($_POST['account_id'] ?? ''));
            if ($accId !== '') {
                $pdo->prepare("DELETE FROM accounts WHERE id = ?")->execute([$accId]);
                $message = 'হোয়াটসঅ্যাপ অ্যাকাউন্টটি রোটেশন পুল থেকে সফলভাবে অপসারিত হয়েছে!';
                $activeTab = 'accounts';
            }
        }

        // 4. TOGGLE OR SAVE AGENT SETTINGS
        elseif ($action === 'save_agents') {
            set_setting($pdo, 'agent_ayesha_active', isset($_POST['agent_ayesha_active']) ? '1' : '0');
            set_setting($pdo, 'agent_nirob_active', isset($_POST['agent_nirob_active']) ? '1' : '0');
            set_setting($pdo, 'agent_tania_active', isset($_POST['agent_tania_active']) ? '1' : '0');
            if (isset($_POST['ayesha_prompt'])) set_setting($pdo, 'ayesha_custom_prompt', trim((string)$_POST['ayesha_prompt']));
            if (isset($_POST['nirob_prompt'])) set_setting($pdo, 'nirob_custom_prompt', trim((string)$_POST['nirob_prompt']));
            if (isset($_POST['tania_prompt'])) set_setting($pdo, 'tania_custom_prompt', trim((string)$_POST['tania_prompt']));
            $message = '৩ জন এআই এজেন্টের সক্রিয়তা ও প্রম্পট কনফিগারেশন সফলভাবে আপডেট হয়েছে!';
            $activeTab = 'agents';
        }

        // 5. QUICK DISPATCH TRIGGER (Order Approved, Demo, Check-in, Update)
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

                // Dispatch using Anti-Ban Sentinel with priority bypass for urgent triggers
                $priority = in_array($triggerType, ['order_approved', 'customer_inquiry'], true) ? 'high' : 'normal';
                $dispRes = whatsapp_antiban_dispatch($pdo, $config, $cleanPhone, $msgContent, $priority, $triggerType);

                $delayNote = $dispRes['delay_applied'] > 0 ? " ({$dispRes['delay_applied']}s অ্যান্টি-ব্যান জিটার প্রয়োগ)" : " (০ সেকেন্ড জরুরি বাইপাস)";
                $message = "গ্রাহক {$cName} ({$dispRes['phone']})-এর কাছে {$dispRes['account_used']} নম্বর দিয়ে বার্তা প্রেরণ করা হয়েছে{$delayNote}!";
                $activeTab = 'dispatch';
            }
        }

        // 6. BROADCAST CAMPAIGN DISPATCH
        elseif ($action === 'broadcast_campaign') {
            $targetAudience = trim((string) ($_POST['target_audience'] ?? 'all_leads'));
            $campTopic = trim((string) ($_POST['campaign_topic'] ?? 'marketing_notice'));
            $campMessage = trim((string) ($_POST['campaign_message'] ?? ''));

            if (empty($campMessage)) {
                $error = 'ক্যাম্পেইনের মেসেজ কনটেন্ট খালি রাখা যাবে না।';
            } else {
                $contacts = [];
                if ($targetAudience === 'all_leads') {
                    $contacts = $pdo->query("SELECT name, clean_phone as phone, interest_package as pkg FROM whatsapp_leads ORDER BY id DESC LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
                } elseif ($targetAudience === 'all_paid') {
                    $contacts = $pdo->query("SELECT name, whatsapp as phone, plan_name as pkg FROM orders WHERE status IN ('approved', 'active') GROUP BY whatsapp LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
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
                            ['{name}', '{package}', '{login_id}'],
                            [$c['name'] ?: 'সম্মানিত গ্রাহক', $c['pkg'] ?: 'AutoMovie Pro', 'amp_' . mt_rand(1000, 9999)],
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

        // 7. CRM INBOX LIVE REPLY
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
// DATA FETCHING FOR DESKTOP SUITE
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

// CRM Threads
$crmThreads = $pdo->query("SELECT * FROM whatsapp_leads ORDER BY updated_at DESC LIMIT 20")->fetchAll(PDO::FETCH_ASSOC);
$recentInbound = $pdo->query("SELECT * FROM inbound_messages ORDER BY timestamp DESC LIMIT 10")->fetchAll(PDO::FETCH_ASSOC);

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

  /* TOP MASTER HUD */
  .wam-master-hud {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(2, 6, 23, 0.98));
    border: 1px solid var(--wam-border-glow);
    border-radius: 16px;
    padding: 1.25rem 1.75rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6), 0 0 25px rgba(16, 185, 129, 0.12);
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
    color: #e2e8f0;
  }

  .wam-pill.secure {
    border-color: rgba(16, 185, 129, 0.4);
    background: rgba(16, 185, 129, 0.1);
    color: #6ee7b7;
  }

  .wam-pill.ai-live {
    border-color: rgba(6, 182, 212, 0.4);
    background: rgba(6, 182, 212, 0.1);
    color: #67e8f9;
  }

  .wam-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--wam-primary);
    box-shadow: 0 0 10px var(--wam-primary);
    animation: pulse 1.8s infinite;
  }

  @keyframes pulse {
    0% { transform: scale(0.95); opacity: 0.7; }
    50% { transform: scale(1.15); opacity: 1; }
    100% { transform: scale(0.95); opacity: 0.7; }
  }

  /* METRICS STRIP */
  .wam-metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
    gap: 8px;
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
    font-size: 0.88rem;
    font-weight: 700;
    padding: 10px 18px;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
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
    margin-bottom: 1.25rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .wam-section-header h2 {
    font-size: 1.15rem;
    font-weight: 800;
    color: #ffffff;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .wam-section-header p {
    font-size: 0.82rem;
    color: var(--wam-text-muted);
    margin: 4px 0 0;
  }

  /* BUTTONS & FORMS */
  .btn-wam-primary {
    background: linear-gradient(135deg, var(--wam-primary), var(--wam-primary-dark));
    color: #ffffff;
    font-weight: 700;
    font-size: 0.85rem;
    padding: 9px 18px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.3);
    transition: all 0.2s ease;
  }

  .btn-wam-primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
  }

  .btn-wam-secondary {
    background: #1e293b;
    color: #cbd5e1;
    font-weight: 600;
    font-size: 0.85rem;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s ease;
  }

  .btn-wam-secondary:hover {
    background: #334155;
    color: #ffffff;
  }

  .btn-wam-danger {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
    font-size: 0.8rem;
    font-weight: 600;
    padding: 6px 10px;
    border-radius: 6px;
    cursor: pointer;
  }

  .btn-wam-danger:hover {
    background: #ef4444;
    color: #ffffff;
  }

  .wam-form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
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
    gap: 14px;
  }

  .wam-agent-avatar-img {
    width: 68px;
    height: 68px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid var(--wam-primary);
    box-shadow: 0 0 15px rgba(16, 185, 129, 0.35);
  }

  .wam-agent-details h3 {
    margin: 0;
    font-size: 1.15rem;
    color: #ffffff;
    font-weight: 800;
  }

  .wam-agent-role {
    font-size: 0.78rem;
    color: var(--wam-cyan);
    font-weight: 700;
    margin-top: 2px;
  }

  /* LIVE WHATSAPP PHONE PREVIEW */
  .wam-phone-mockup {
    width: 100%;
    max-width: 380px;
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
    transition: background 0.2s ease;
  }

  .wam-thread-item:hover, .wam-thread-item.active {
    background: rgba(16, 185, 129, 0.12);
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
    background: #080d14;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .wam-crm-chat-foot {
    background: #111827;
    padding: 12px 16px;
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
        <h1>WAManager <span class="wam-brand-tag">PRO DESKTOP</span></h1>
        <p class="wam-brand-sub">হোয়াটসঅ্যাপ মার্কেটিং, মাল্টি-অ্যাকাউন্ট রোটেশন ও এআই সেলস সিআরএম স্যুট</p>
      </div>
    </div>

    <!-- LIVE STATUS PILLS -->
    <div class="wam-system-pills">
      <div class="wam-pill secure">
        <span class="wam-pulse"></span>
        <span>🛡️ অ্যান্টি-ব্যান শিল্ড: সক্রিয় (100% নিরাপদ)</span>
      </div>
      <div class="wam-pill ai-live">
        <span>🤖 ৩ জন এআই এজেন্ট: অনলাইন</span>
      </div>
      <div class="wam-pill">
        <span>🔄 স্মার্ট রোটেশন: <?= $totalActiveAccounts ?>টি নম্বর পুল</span>
      </div>
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
        <span>আজকের নিরাপদ কোটা</span>
        <span>🛡️</span>
      </div>
      <div class="wam-metric-num" style="color:var(--wam-cyan);"><?= $totalDailyRemaining ?> <span style="font-size:0.9rem; color:#64748b;">বাকি</span></div>
      <div class="wam-metric-sub">আজকে পাঠানো হয়েছে: <?= $totalDailySent ?> টি</div>
    </div>

    <div class="wam-metric-card">
      <div class="wam-metric-label">
        <span>মোট লিড ও কাস্টমার</span>
        <span>👥</span>
      </div>
      <div class="wam-metric-num" style="color:var(--wam-purple);"><?= number_format($totalLeads + $totalOrders) ?></div>
      <div class="wam-metric-sub">লিড: <?= $totalLeads ?> | কাস্টমার: <?= $totalOrders ?></div>
    </div>

    <div class="wam-metric-card">
      <div class="wam-metric-label">
        <span>অটো লাইসেন্স ডেলিভারি</span>
        <span>⚡</span>
      </div>
      <div class="wam-metric-num" style="color:var(--wam-amber);"><?= number_format($totalDispatches) ?></div>
      <div class="wam-metric-sub">১০০% তাৎক্ষণিক ডেলিভার্ড</div>
    </div>
  </div>

  <!-- NAVIGATION TABS -->
  <div class="wam-tabs-deck">
    <button type="button" class="wam-tab-btn <?= $activeTab === 'accounts' ? 'active' : '' ?>" onclick="switchWamTab('accounts')">
      <span>📱</span> <span>মাল্টি-অ্যাকাউন্ট ও রোটেশন পুল</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'agents' ? 'active' : '' ?>" onclick="switchWamTab('agents')">
      <span>🤖</span> <span>৩ জন এআই এজেন্ট ও ট্রেইনিং</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'antiban' ? 'active' : '' ?>" onclick="switchWamTab('antiban')">
      <span>🛡️</span> <span>অ্যান্টি-ব্যান সেন্টিনেল ও ডেলিভারি গার্ড</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'crm' ? 'active' : '' ?>" onclick="switchWamTab('crm')">
      <span>💬</span> <span>টু-ওয়ে লাইভ সিআরএম ও চ্যাট</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'broadcast' ? 'active' : '' ?>" onclick="switchWamTab('broadcast')">
      <span>📢</span> <span>স্মার্ট ক্যাম্পেইন ও ব্রডকাস্টার</span>
    </button>
    <button type="button" class="wam-tab-btn <?= $activeTab === 'dispatch' ? 'active' : '' ?>" onclick="switchWamTab('dispatch')">
      <span>⚡</span> <span>কাস্টমার অটো-ডিসপ্যাচ ও হিস্ট্রি</span>
    </button>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 1: MULTI-ACCOUNT & SMART ROTATION POOL -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'accounts' ? 'active' : '' ?>" id="tab-accounts">
    <div class="wam-section-header">
      <div>
        <h2><span>📱</span> মাল্টি-অ্যাকাউন্ট ও স্মার্ট রোটেশন পুল (৩-৪ নম্বর সংযোগ)</h2>
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
  <!-- TAB 2: 3 AI AGENTS & SIMULATOR -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'agents' ? 'active' : '' ?>" id="tab-agents">
    <div class="wam-section-header">
      <div>
        <h2><span>🤖</span> ৩ জন এআই এজেন্ট ও ট্রেইনিং সেন্ট্রাল (Ayesha, Nirob, Tania)</h2>
        <p>গ্রাহকের যে ধরণের প্রশ্নই আসুক, সংশ্লিষ্ট দক্ষ এজেন্ট স্বয়ংক্রিয়ভাবে প্রফেশনাল ও নির্ভুল উত্তর প্রদান করবে।</p>
      </div>
    </div>

    <form method="POST">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="save_agents">

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
            নতুন আগ্রহী লিডদের ফলো-আপ, প্যাকেজের মূল্যছাড় ও স্পেশাল 'VIP500' ডিসকাউন্ট অফার দিয়ে সেলস ক্লোজ করে।
          </p>
          <div class="wam-form-group">
            <label>কাস্টম ইনস্ট্রাকশন / প্রম্পট:</label>
            <textarea class="wam-form-textarea" rows="3" name="tania_prompt" placeholder="তানিয়ার সেলস ইনস্ট্রাকশন..."><?= e(setting($pdo, 'tania_custom_prompt', 'প্যাকেজের মূল্য ৩,৯৯৯ টাকা, ২,৯৯৯ টাকা ও ১,৯৯৯ টাকা। আগ্রহী ক্রেতাকে VIP500 কুপন কোড অফার করে দ্রুত অর্ডার সম্পন্ন করতে সহায়তা করো।')) ?></textarea>
          </div>
        </div>
      </div>

      <div style="margin-top:1.25rem; display:flex; justify-content:flex-end;">
        <button type="submit" class="btn-wam-primary">💾 এআই এজেন্টদের সেটিংস সংরক্ষণ করুন</button>
      </div>
    </form>

    <!-- INTERACTIVE AGENT SIMULATOR -->
    <div style="margin-top:2rem; background:#080d14; border:1px solid #1e293b; border-radius:14px; padding:1.5rem;">
      <h3 style="color:#ffffff; margin:0 0 10px; font-size:1.05rem; display:flex; align-items:center; gap:8px;">
        <span>⚡</span> এআই অটো-রিপ্লাই সিমুলেটর (Live Interactive Test)
      </h3>
      <p style="font-size:0.85rem; color:#94a3b8; margin:0 0 1rem;">
        নিচে যেকোনো একটি কাস্টমার প্রশ্ন লিখে টেস্ট করে দেখতে পারেন আমাদের এআই এজেন্টরা কীভাবে স্বয়ংক্রিয়ভাবে হোয়াটসঅ্যাপে উত্তর প্রদান করবে:
      </p>

      <div class="wam-form-grid">
        <div class="wam-form-group">
          <label>এজেন্ট নির্বাচন করুন:</label>
          <select class="wam-form-select" id="simAgentSelect">
            <option value="ayesha">আয়েশা (Ayesha) — কাস্টমার কেয়ার ও ওয়েলকাম</option>
            <option value="nirob">নীরব (Nirob) — টেকনিক্যাল ও সেটআপ সাপোর্ট</option>
            <option value="tania">তানিয়া (Tania) — সেলস, প্রাইস ও ডিসকাউন্ট অফার</option>
          </select>
        </div>

        <div class="wam-form-group">
          <label>গ্রাহকের প্রশ্ন / মেসেজ:</label>
          <input type="text" class="wam-form-input" id="simUserMessage" value="আমার পিসিতে 4GB RAM, এটা দিয়ে কি ফুল 4K ভিডিও বানানো যাবে?" placeholder="গ্রাহকের প্রশ্ন লিখুন...">
        </div>
      </div>

      <div style="margin-top:10px;">
        <button type="button" class="btn-wam-primary" onclick="runAgentSimulation()">
          ⚡ তাৎক্ষণিক এআই উত্তর জেনারেট করুন
        </button>
      </div>

      <div id="simResultBox" style="margin-top:1rem; display:none;">
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
              আমার পিসিতে 4GB RAM, এটা দিয়ে কি ফুল 4K ভিডিও বানানো যাবে?
            </div>
            <div class="wam-bubble-out" id="simAgentBubble">
              জেনারেট হচ্ছে...
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- TAB 3: ANTI-BAN SENTINEL & DELIVERY GUARD -->
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
  <!-- TAB 4: TWO-WAY LIVE CRM & CHAT -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'crm' ? 'active' : '' ?>" id="tab-crm">
    <div class="wam-section-header">
      <div>
        <h2><span>💬</span> টু-ওয়ে লাইভ সিআরএম ও চ্যাট ইনবক্স</h2>
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
  <!-- TAB 5: SMART CAMPAIGN & BROADCASTER -->
  <!-- ========================================================================= -->
  <div class="wam-panel <?= $activeTab === 'broadcast' ? 'active' : '' ?>" id="tab-broadcast">
    <div class="wam-section-header">
      <div>
        <h2><span>📢</span> স্মার্ট ক্যাম্পেইন ও নোটিফিকেশন ব্রডকাস্টার (Anti-Ban Safe Broadcast)</h2>
        <p>হাজার হাজার গ্রাহক বা লিডের কাছে নিরাপদ সময় বিরতি বজায় রেখে সফটওয়্যার আপডেট, অফার বা ওয়েলফেয়ার মেসেজ ব্রডকাস্ট করুন।</p>
      </div>
    </div>

    <form method="POST">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="broadcast_campaign">

      <div class="wam-form-grid">
        <div class="wam-form-group">
          <label>টার্গেট অডিয়েন্স নির্বাচন করুন:</label>
          <select class="wam-form-select" name="target_audience" id="campAudienceSelect" onchange="updateCampTemplate()">
            <option value="all_leads">🎯 সকল নতুন লিড ও ভিজিটর (<?= $totalLeads ?> জন)</option>
            <option value="all_paid">💼 সকল অনুমোদিত পেইড কাস্টমার (<?= $totalOrders ?> জন)</option>
            <option value="contacts">📂 সংরক্ষিত কন্টাক্ট ডাটাবেজ</option>
          </select>
        </div>

        <div class="wam-form-group">
          <label>ক্যাম্পেইন টেমপ্লেট প্রিসেট:</label>
          <select class="wam-form-select" name="campaign_topic" id="campTopicSelect" onchange="updateCampTemplate()">
            <option value="version_update">🚀 নতুন সফটওয়্যার ভার্সন আপডেট নোটিফিকেশন</option>
            <option value="price_discount">🏷️ স্পেশাল অফার ও ৫০০ টাকা ডিসকাউন্ট নোটিশ</option>
            <option value="care_checkin">🤝 কাস্টমার ওয়েলফেয়ার ও নিয়মিত চেক-ইন</option>
            <option value="faceless_tips">💡 ফেসলেস চ্যানেল আর্নিং টিপস ও গাইড</option>
          </select>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 380px; gap:1.5rem; margin-top:1.25rem;">
        <div>
          <div class="wam-form-group">
            <label style="display:flex; justify-content:space-between;">
              <span>বার্তা কম্পোজার (Dynamic Tags: {name}, {package}, {login_id}):</span>
              <span style="font-size:0.75rem; color:#38bdf8;">ট্যাগগুলো স্বয়ংক্রিয়ভাবে প্রতিস্থাপিত হবে</span>
            </label>
            <textarea class="wam-form-textarea" rows="10" name="campaign_message" id="campMsgInput" oninput="updatePhoneMockup()"></textarea>
          </div>

          <div style="margin-top:1rem; background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); border-radius:10px; padding:12px; font-size:0.82rem; color:#fde68a;">
            🛡️ <strong>অ্যান্টি-ব্যান সুরক্ষা সক্রিয়:</strong> প্রতিটি মেসেজের মাঝে ২৫ থেকে ৫৫ সেকেন্ডের জিটার গ্যাপ দেওয়া হবে এবং প্রতি ১৫টি মেসেজ পর ৮ মিনিটের কুলডাউন রেস্ট বজায় রাখা হবে। আপনার সংযুক্ত ৪টি নম্বরে সমানভাবে ট্র্যাফিক রোটেশন করা হবে।
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
  <!-- TAB 6: INSTANT TRIGGERS & DISPATCH HISTORY -->
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
<!-- MODAL: ADD NEW NUMBER TO ROTATION POOL -->
<!-- ========================================================================= -->
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

<script>
  // Tab Switching
  function switchWamTab(tabId) {
    document.querySelectorAll('.wam-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.wam-panel').forEach(p => p.classList.remove('active'));
    
    event.currentTarget.classList.add('active');
    const target = document.getElementById('tab-' + tabId);
    if (target) target.classList.add('active');
  }

  // Add Account Modal
  function openAddAccountModal() {
    const modal = document.getElementById('addAccountModal');
    if (modal) modal.style.display = 'flex';
  }
  function closeAddAccountModal() {
    const modal = document.getElementById('addAccountModal');
    if (modal) modal.style.display = 'none';
  }

  // Live Simulation
  function runAgentSimulation() {
    const agent = document.getElementById('simAgentSelect').value;
    const msg = document.getElementById('simUserMessage').value;
    const resultBox = document.getElementById('simResultBox');
    const userBubble = document.getElementById('simUserBubble');
    const agentBubble = document.getElementById('simAgentBubble');
    const headerName = document.getElementById('simHeaderName');
    const headerAvatar = document.getElementById('simHeaderAvatar');

    userBubble.innerText = msg;
    resultBox.style.display = 'block';

    if (agent === 'nirob') {
      headerName.innerText = 'নীরব (Tech Specialist)';
      headerAvatar.innerText = 'N';
      headerAvatar.style.background = '#06b6d4';
      agentBubble.innerText = "আসসালামু আলাইকুম ভাই! আমি নীরব, AutoMovie Pro-এর টেকনিক্যাল স্পেশালিস্ট। 💻\n\nকোনো চিন্তা করবেন না, 4GB র‍্যামেই চমৎকারভাবে সফটওয়্যারটি চলবে। কোনো ডেডিকেটেড গ্রাফিক্স কার্ডের প্রয়োজন নেই। সফটওয়্যারটি সম্পূর্ণ লোকাল পিসিতে অফলাইনে প্রসেস হয়, তাই ভিডিও তৈরির সময় ইন্টারনেটও লাগে না!";
    } else if (agent === 'tania') {
      headerName.innerText = 'তানিয়া (Onboarding & Sales)';
      headerAvatar.innerText = 'T';
      headerAvatar.style.background = '#8b5cf6';
      agentBubble.innerText = "আসসালামু আলাইকুম! আমি তানিয়া, AutoMovie Pro টিম থেকে। 🌟\n\nআজকের স্পেশাল অফারে আপনি 'VIP500' কুপন কোড ব্যবহার করে সাথে সাথে ৫০০ টাকা ডিসকাউন্ট পাবেন!\n🎬 ফুল ভিডিও স্টুডিও লাইসেন্স প্যাকেজ: মাত্র ৳৩,৯৯৯ (অফার মূল্য: ৳৩,৪৯৯)।\n👉 এখনই অর্ডার সম্পন্ন করতে ভিজিট করুন: https://automoviepro.com/order.php";
    } else {
      headerName.innerText = 'আয়েশা (Customer Care)';
      headerAvatar.innerText = 'A';
      headerAvatar.style.background = '#10b981';
      agentBubble.innerText = "আসসালামু আলাইকুম! আমি আয়েশা, AutoMovie Pro কাস্টমার সাপোর্ট থেকে বলছি। 🌸\n\nAutoMovie Pro-তে আপনাকে স্বাগতম। আপনি কোনো ফেস বা ভয়েস না দেখিয়েই স্বয়ংক্রিয়ভাবে ভাইরাল ভিডিও ও পোস্ট তৈরি করতে পারবেন। আপনি কি আমাদের ৩টি প্যাকেজের ফিচার সম্পর্কে জানতে চাচ্ছেন?";
    }
  }

  // CRM Thread selection
  function selectCrmThread(name, phone, pkg, msg) {
    document.getElementById('crmActiveName').innerText = name;
    document.getElementById('crmActivePhone').innerText = phone;
    document.getElementById('crmActivePkg').innerText = ' • ' + (pkg || 'General Visitor');
    document.getElementById('crmInputPhone').value = phone;
    document.getElementById('crmUserLastBubble').innerText = msg || 'কোনো সাম্প্রতিক বার্তা নেই';
    document.getElementById('crmDirectWaBtn').href = 'https://wa.me/' + phone.replace(/[^0-9]/g, '');
  }

  // Campaign templates
  function updateCampTemplate() {
    const topic = document.getElementById('campTopicSelect').value;
    const msgBox = document.getElementById('campMsgInput');

    if (topic === 'version_update') {
      msgBox.value = "📢 AutoMovie Pro নতুন আপডেট রিলিজ (v4.5.2)!\n\nসম্মানিত গ্রাহক {name},\nআমাদের ভিডিও স্টুডিওতে নতুন সুপার-ফাস্ট 4K রেন্ডারিং ইঞ্জিন ও ফেসবুক অটো-রিলস শিডিউলার যুক্ত হয়েছে।\n\nআপনার পিসিতে সফটওয়্যারটি চালু করলেই স্বয়ংক্রিয়ভাবে আপডেট সক্রিয় হয়ে যাবে।\nযেকোনো সহায়তায় আমাদের সাপোর্ট টিম সর্বদা আপনার পাশে রয়েছে।";
    } else if (topic === 'price_discount') {
      msgBox.value = "🎉 বিশেষ অফার: AutoMovie Pro লাইফটাইম লাইসেন্সে ৫০০ টাকা ছাড়!\n\nসম্মানিত {name},\nআপনি যদি ইউটিউব ও ফেসবুকে ফেসলেস ভিডিও বানিয়ে প্যাসিভ ইনকাম শুরু করতে চান, তবে এখনই সেরা সুযোগ!\n\nকুপন কোড: VIP500\nঅর্ডার লিংক: https://automoviepro.com/order.php\nঅফারটি সীমিত সময়ের জন্য প্রযোজ্য।";
    } else if (topic === 'care_checkin') {
      msgBox.value = "Assalamu Alaikum {name}!\n\nAutoMovie Pro কাস্টমার রিলেশনশিপ টিম থেকে যোগাযোগ করছি।\nআপনার সফটওয়্যারটি কেমন চলছে? ভিডিও তৈরি বা ফেসবুক অটোমেশনে কোনো প্রকার সমস্যা বা সহায়তা প্রয়োজন কি?\n\nকোনো কিছু জানার থাকলে সরাসরি এই নম্বরে রিপ্লাই করুন, আমরা সাথে সাথে সমাধান করে দেবো।";
    } else {
      msgBox.value = "💡 ফেসলেস চ্যানেল আর্নিং টিপস:\n\nসম্মানিত {name},\nAutoMovie Pro ব্যবহার করে প্রতিদিন ২-৩টি হাই-রিটেনশন শর্টস আপলোড করুন।\nআমাদের встроен ট্রেন্ডিং টপিক ফাইন্ডার দিয়ে ভাইরাল স্ক্রিপ্ট জেনারেট করুন।\n\nবিস্তারিত গাইড দেখতে ভিজিট করুন: https://automoviepro.com/guide.html";
    }
    updatePhoneMockup();
  }

  function updatePhoneMockup() {
    const text = document.getElementById('campMsgInput').value;
    document.getElementById('phoneMockupText').innerText = text.replace('{name}', 'তানভীর আহমেদ').replace('{package}', 'Video Studio');
  }

  // Initialize on load
  document.addEventListener('DOMContentLoaded', function() {
    updateCampTemplate();
  });
</script>

<?php
admin_footer();
