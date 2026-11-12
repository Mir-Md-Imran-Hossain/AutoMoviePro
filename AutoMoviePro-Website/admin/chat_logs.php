<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';
$error = '';

// Handle actions
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!csrf_verify($_POST['csrf'] ?? null)) {
        $error = 'সেশনের মেয়াদ শেষ হয়েছে বা ফর্মের টোকেন মেয়াদোত্তীর্ণ। অনুগ্রহ করে পৃষ্ঠাটি রিলোড করে পুনরায় ফর্ম পূরণ করুন।';
    } else {
        $action = (string) ($_POST['action'] ?? '');
        if ($action === 'clear_old') {
            try {
                $cutoff = date('Y-m-d H:i:s', strtotime('-30 days'));
                $delStmt = $pdo->prepare("DELETE FROM customer_chat_logs WHERE created_at < ?");
                $delStmt->execute([$cutoff]);
                $message = '৩০ দিনের পূর্বের পুরনো চ্যাট লগসমূহ সফলভাবে মুছে ফেলা হয়েছে।';
            } catch (\Throwable $e) {
                $error = 'লগ ডিলিট করার সময় সমস্যা হয়েছে।';
            }
        }
    }
}

// Tabs & Filters
$activeTab = trim((string) ($_GET['tab'] ?? 'chat')); // 'chat' or 'psychology'
$filterAgent = trim((string) ($_GET['agent'] ?? 'all'));
$filterWa = trim((string) ($_GET['wa'] ?? 'all'));
$search = trim((string) ($_GET['q'] ?? ''));

$where = [];
$params = [];

if ($filterAgent !== 'all' && $filterAgent !== '') {
    $where[] = "agent_id = ?";
    $params[] = $filterAgent;
}

if ($filterWa === '1') {
    $where[] = "whatsapp_handoff = 1";
}

if ($search !== '') {
    $where[] = "(user_message LIKE ? OR bot_reply LIKE ? OR session_id LIKE ?)";
    $params[] = "%{$search}%";
    $params[] = "%{$search}%";
    $params[] = "%{$search}%";
}

$whereSql = $where ? ('WHERE ' . implode(' AND ', $where)) : '';

// Stats
$totalLogs = 0;
$todayLogs = 0;
$waLeads = 0;
$totalProfiles = 0;
$hotProfiles = 0;
$inChatOrdersCount = 0;

try {
    $totalLogs = (int) $pdo->query("SELECT COUNT(*) FROM customer_chat_logs")->fetchColumn();
    $todayLogs = (int) $pdo->query("SELECT COUNT(*) FROM customer_chat_logs WHERE DATE(created_at) = CURRENT_DATE")->fetchColumn();
    $waLeads = (int) $pdo->query("SELECT COUNT(*) FROM customer_chat_logs WHERE whatsapp_handoff = 1")->fetchColumn();
    
    // Psychology table stats
    $totalProfiles = (int) $pdo->query("SELECT COUNT(*) FROM customer_psychology_profiles")->fetchColumn();
    $hotProfiles = (int) $pdo->query("SELECT COUNT(*) FROM customer_psychology_profiles WHERE buying_temperature >= 70")->fetchColumn();
    $inChatOrdersCount = (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE order_source = 'chat_agent'")->fetchColumn();
    $waitlistLeadsCount = (int) $pdo->query("SELECT COUNT(*) FROM customer_psychology_profiles WHERE in_chat_order_state = 'waitlist_registered' OR (customer_phone IS NOT NULL AND customer_phone != '')")->fetchColumn();
} catch (\Throwable $e) {}

// Query logs
$logs = [];
try {
    $stmt = $pdo->prepare("SELECT * FROM customer_chat_logs {$whereSql} ORDER BY id DESC LIMIT 150");
    $stmt->execute($params);
    $logs = $stmt->fetchAll();
} catch (\Throwable $e) {}

// Query psychology profiles
$psychologyProfiles = [];
try {
    $stmtP = $pdo->query("SELECT * FROM customer_psychology_profiles ORDER BY last_seen_at DESC LIMIT 100");
    $psychologyProfiles = $stmtP->fetchAll();
} catch (\Throwable $e) {}

admin_header('এআই সেলস মাস্টারমাইন্ড ও কাস্টমার সাইকোলজি মনিটর', 'chat_logs');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<?php if ($error): ?>
  <div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#fca5a5; font-size:0.95rem; font-weight:700;">
    ⚠️ <?= e($error) ?>
  </div>
<?php endif; ?>

<!-- Top Metrics -->
<div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-bottom: 2rem;">
  <div class="stat-card">
    <div class="stat-label">মোট চ্যাট কনভার্সেশন</div>
    <div class="stat-value" style="color:#38bdf8;"><?= number_format($totalLogs) ?> টি</div>
    <div class="stat-trend">ওয়েবসাইটে ভিজিটরদের লাইভ বার্তা</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">সাইকোলজি প্রোফাইল্ড ভিজিটর</div>
    <div class="stat-value" style="color:#a855f7;"><?= number_format($totalProfiles) ?> জন</div>
    <div class="stat-trend" style="color:#d8b4fe;">মাস্টার ব্রেন দ্বারা নিখুঁত প্রোফাইল্ড</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">হট বায়ার্স (Temp ≥ ৭০%)</div>
    <div class="stat-value" style="color:#f59e0b;"><?= number_format($hotProfiles) ?> জন</div>
    <div class="stat-trend" style="color:#fde68a;">অর্ডার করার সর্বোচ্চ সম্ভাবনাময়</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">ইন-চ্যাট সরাসরি অর্ডার</div>
    <div class="stat-value" style="color:#10b981; font-size:1.4rem;"><?= number_format($inChatOrdersCount) ?> টি</div>
    <div class="stat-trend" style="color:#a7f3d0;">এজেন্ট সরাসরি চ্যাটেই অর্ডার নিয়েছে</div>
  </div>
  <div class="stat-card" style="border: 1.5px solid rgba(245,158,11,0.5); background: rgba(245,158,11,0.08);">
    <div class="stat-label" style="color:#fbbf24;">📋 প্রি-লঞ্চ প্রায়োরিটি ওয়েটিং লিস্ট</div>
    <div class="stat-value" style="color:#fbbf24; font-size:1.4rem;"><?= number_format($waitlistLeadsCount) ?> জন</div>
    <div class="stat-trend" style="color:#fde68a;">সার্ভার আপগ্রেড চলাকালীন সংরক্ষিত লিড</div>
  </div>
</div>

<!-- Tab Navigation Header -->
<div style="display:flex; gap:10px; margin-bottom:1.5rem; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:10px;">
  <a href="?tab=chat" class="btn-admin <?= $activeTab === 'chat' ? 'btn-admin-primary' : 'btn-admin-ghost' ?>" style="font-weight:700; font-size:0.9rem; padding:9px 18px; border-radius:8px;">
    💬 লাইভ চ্যাট হিস্ট্রি স্ট্রিম (Chat Logs)
  </a>
  <a href="?tab=psychology" class="btn-admin <?= $activeTab === 'psychology' ? 'btn-admin-primary' : 'btn-admin-ghost' ?>" style="font-weight:700; font-size:0.9rem; padding:9px 18px; border-radius:8px;">
    🧠 কাস্টমার সাইকোলজি ডসিয়ার ও প্রোফাইল গ্রাফ (<?= count($psychologyProfiles) ?>)
  </a>
</div>

<?php if ($activeTab === 'psychology'): ?>
  <!-- PSYCHOLOGY PROFILES VIEW -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>🧠</span>
        <span>কাস্টমার সাইকোলজিক্যাল ডসিয়ার ও আচরণগত প্রোফাইল</span>
      </div>
      <span style="font-size:0.8rem; color:#94a3b8;">মাস্টার এআই মার্কেটিং ব্রেন দ্বারা স্বয়ংক্রিয়ভাবে সংগৃহীত ও বিশ্লেষিত</span>
    </div>

    <div style="overflow-x:auto;">
      <table class="admin-table">
        <thead>
          <tr>
            <th style="width:160px;">ভিজিটর / কাস্টমার</th>
            <th style="width:140px;">এজেন্ট ও টার্নস</th>
            <th style="width:150px;">সাইকোলজিক্যাল আর্কিটাইপ</th>
            <th style="width:180px;">বায়িং টেম্পারেচার</th>
            <th style="width:150px;">কনভার্সেশন স্টেজ</th>
            <th style="width:170px;">পূর্বের ক্রয় ও অ্যান্টি-ন্যাগিং</th>
            <th style="width:140px;">পরবর্তী অফার</th>
            <th style="width:130px;">ডিসকাউন্ট অবস্থা</th>
            <th style="text-align:right; width:130px;">ইন-চ্যাট অর্ডার</th>
          </tr>
        </thead>
        <tbody>
          <?php if (empty($psychologyProfiles)): ?>
            <tr>
              <td colspan="9" style="text-align:center; padding:3rem; color:#64748b;">
                এখনো কোনো সাইকোলজি প্রোফাইল তৈরি হয়নি। ভিজিটররা ওয়েবসাইটে চ্যাট শুরু করলেই মাস্টার ব্রেন স্বয়ংক্রিয়ভাবে তাদের সাইকোলজি বিশ্লেষণ করে এখানে ডসিয়ার তৈরি করবে।
              </td>
            </tr>
          <?php else: ?>
            <?php foreach ($psychologyProfiles as $p): ?>
              <?php
                $archetype = (string) ($p['psychological_archetype'] ?? 'hesitant_shopper');
                $archetypeLabels = [
                  'skeptic_analyst' => ['label' => '🔬 সংশয়ী বিশ্লেষক', 'color' => '#38bdf8', 'bg' => 'rgba(56,189,248,0.15)'],
                  'budget_conscious' => ['label' => '💰 বাজেট সচেতন', 'color' => '#f59e0b', 'bg' => 'rgba(245,158,11,0.15)'],
                  'passionate_creator' => ['label' => '🎨 সৃষ্টিশীল ক্রিয়েটর', 'color' => '#ec4899', 'bg' => 'rgba(236,72,153,0.15)'],
                  'busy_merchant' => ['label' => '🏢 ব্যস্ত মার্চেন্ট', 'color' => '#10b981', 'bg' => 'rgba(16,185,129,0.15)'],
                  'hesitant_shopper' => ['label' => '⏳ দ্বিধান্বিত ক্রেতা', 'color' => '#a855f7', 'bg' => 'rgba(168,85,247,0.15)'],
                ];
                $archMeta = $archetypeLabels[$archetype] ?? ['label' => $archetype, 'color' => '#cbd5e1', 'bg' => 'rgba(255,255,255,0.1)'];

                $temp = (int) ($p['buying_temperature'] ?? 15);
                $tempColor = ($temp >= 70) ? '#10b981' : (($temp >= 40) ? '#f59e0b' : '#38bdf8');
                $tempLabel = ($temp >= 70) ? '🔥 হট বায়ার' : (($temp >= 40) ? '🌤️ ওয়ার্ম' : '❄️ কোল্ড');

                $purchased = json_decode((string) ($p['purchased_products'] ?? '[]'), true) ?: [];
                $doNotNag = json_decode((string) ($p['do_not_nag_products'] ?? '[]'), true) ?: [];
              ?>
              <tr>
                <td>
                  <div style="font-weight:700; color:#f8fafc; font-size:0.9rem;">
                    <?= e($p['customer_name'] ?: 'ভিজিটর #' . substr((string)$p['visitor_id'], 0, 8)) ?>
                  </div>
                  <?php if (!empty($p['customer_phone'])): ?>
                    <div style="font-size:0.78rem; color:#10b981; font-weight:600;">
                      📱 <?= e($p['customer_phone']) ?>
                    </div>
                  <?php endif; ?>
                  <div style="font-size:0.7rem; color:#64748b; font-family:monospace;">
                    ID: <?= substr((string)$p['visitor_id'], 0, 10) ?>…
                  </div>
                  <div style="font-size:0.7rem; color:#94a3b8; margin-top:2px;">
                    দেখা: <?= date('d M, h:i A', strtotime($p['last_seen_at'])) ?>
                  </div>
                </td>
                <td>
                  <div style="font-weight:600; font-size:0.85rem; color:#f8fafc;">
                    <?= e($p['assigned_agent_name'] ?? 'নীরব') ?>
                  </div>
                  <div style="font-size:0.75rem; color:#94a3b8;">
                    টার্নস: <strong style="color:#38bdf8;"><?= (int)$p['turns_count'] ?></strong> টি মেসেজ
                  </div>
                </td>
                <td>
                  <span style="display:inline-block; padding:4px 8px; border-radius:6px; font-size:0.78rem; font-weight:700; background:<?= $archMeta['bg'] ?>; color:<?= $archMeta['color'] ?>; border:1px solid <?= $archMeta['color'] ?>40;">
                    <?= $archMeta['label'] ?>
                  </span>
                </td>
                <td>
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <span style="font-size:0.75rem; font-weight:700; color:<?= $tempColor ?>;"><?= $temp ?>%</span>
                    <span style="font-size:0.7rem; color:<?= $tempColor ?>; font-weight:600;"><?= $tempLabel ?></span>
                  </div>
                  <div style="width:100%; height:6px; background:rgba(255,255,255,0.1); border-radius:4px; overflow:hidden;">
                    <div style="width:<?= min(100, max(5, $temp)) ?>%; height:100%; background:<?= $tempColor ?>; border-radius:4px; transition:width 0.3s;"></div>
                  </div>
                </td>
                <td>
                  <span class="admin-badge badge-info" style="font-size:0.72rem; text-transform:uppercase;">
                    <?= e(str_replace('_', ' ', (string)($p['conversation_stage'] ?? 'unaware'))) ?>
                  </span>
                </td>
                <td>
                  <?php if (!empty($purchased)): ?>
                    <div style="margin-bottom:4px;">
                      <?php foreach ($purchased as $pkg): ?>
                        <span class="admin-badge badge-success" style="font-size:0.68rem; margin:1px;">
                          ✓ <?= e($pkg) ?>
                        </span>
                      <?php endforeach; ?>
                    </div>
                    <div style="font-size:0.7rem; color:#ec4899; font-weight:600;">
                      🚫 অ্যান্টি-ন্যাগিং সক্রিয়
                    </div>
                  <?php else: ?>
                    <span style="font-size:0.75rem; color:#64748b;">নতুন গ্রাহক (কোনো ক্রয় নেই)</span>
                  <?php endif; ?>
                </td>
                <td>
                  <span style="font-size:0.78rem; font-weight:600; color:#38bdf8;">
                    <?= e(str_replace('_', ' ', (string)($p['recommended_next_product'] ?? 'video_studio'))) ?>
                  </span>
                </td>
                <td>
                  <?php if (!empty($p['authorized_coupon_code'])): ?>
                    <span class="admin-badge badge-warning" style="font-size:0.72rem; font-weight:700;">
                      <?= e($p['authorized_coupon_code']) ?> (৳<?= (int)$p['discount_authorized_amount'] ?>)
                    </span>
                  <?php else: ?>
                    <span style="font-size:0.75rem; color:#10b981;">🛡️ মার্জিন সুরক্ষিত</span>
                  <?php endif; ?>
                </td>
                <td style="text-align:right;">
                  <?php if (($p['in_chat_order_state'] ?? '') === 'completed' || ($p['in_chat_order_state'] ?? '') === 'order_completed'): ?>
                    <span class="admin-badge badge-success" style="font-size:0.75rem;">
                      ✓ সম্পন্ন
                    </span>
                  <?php elseif (($p['in_chat_order_state'] ?? '') === 'waitlist_registered'): ?>
                    <span class="admin-badge" style="background:rgba(245,158,11,0.2); color:#fbbf24; border:1px solid #f59e0b; font-size:0.75rem;">
                      📋 ওয়েটিং লিস্ট
                    </span>
                  <?php elseif (($p['in_chat_order_state'] ?? '') === 'awaiting_payment'): ?>
                    <span class="admin-badge badge-warning" style="font-size:0.75rem;">
                      ⏳ পেমেন্ট বাকি
                    </span>
                  <?php else: ?>
                    <span style="font-size:0.75rem; color:#64748b;">—</span>
                  <?php endif; ?>
                </td>
              </tr>
            <?php endforeach; ?>
          <?php endif; ?>
        </tbody>
      </table>
    </div>
  </div>

<?php else: ?>
  <!-- CHAT LOGS STREAM VIEW -->
  <!-- Filters Bar -->
  <div class="admin-card" style="margin-bottom: 1.5rem; padding: 1.25rem;">
    <form method="get" style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;">
      <input type="hidden" name="tab" value="chat">
      <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center;">
        <input type="text" name="q" value="<?= e($search) ?>" placeholder="প্রশ্ন বা উত্তর দিয়ে খুঁজুন…" class="form-input" style="width:240px; padding:7px 12px; font-size:0.85rem;">
        
        <select name="agent" class="form-input" style="width:160px; padding:7px 12px; font-size:0.85rem;">
          <option value="all" <?= $filterAgent === 'all' ? 'selected' : '' ?>>সকল এজেন্ট</option>
          <option value="ayesha" <?= $filterAgent === 'ayesha' ? 'selected' : '' ?>>আয়েশা (Ayesha)</option>
          <option value="tania" <?= $filterAgent === 'tania' ? 'selected' : '' ?>>তানিয়া (Tania)</option>
          <option value="nirob" <?= $filterAgent === 'nirob' ? 'selected' : '' ?>>নীরব (Nirob)</option>
        </select>

        <select name="wa" class="form-input" style="width:170px; padding:7px 12px; font-size:0.85rem;">
          <option value="all" <?= $filterWa === 'all' ? 'selected' : '' ?>>সকল চ্যাট</option>
          <option value="1" <?= $filterWa === '1' ? 'selected' : '' ?>>🔥 শুধু WhatsApp লিড</option>
        </select>

        <button type="submit" class="btn-admin btn-admin-primary" style="padding:7px 14px; font-size:0.85rem;">
          🔍 ফিল্টার করুন
        </button>
        <?php if ($search || $filterAgent !== 'all' || $filterWa !== 'all'): ?>
          <a href="/admin/chat_logs.php?tab=chat" class="btn-admin btn-admin-ghost" style="padding:7px 12px; font-size:0.85rem;">
            রিসেট
          </a>
        <?php endif; ?>
      </div>

      <div>
        <form method="post" onsubmit="return confirm('৩০ দিনের পুরনো সকল চ্যাট লগ মুছে ফেলতে চান?');" style="display:inline;">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="action" value="clear_old">
          <button type="submit" class="btn-admin" style="background:rgba(244,63,94,0.1); color:#f43f5e; border:1px solid rgba(244,63,94,0.25); padding:6px 12px; font-size:0.8rem;">
            🗑️ পুরনো লগ ডিলিট
          </button>
        </form>
      </div>
    </form>
  </div>

  <!-- Chat Logs Table -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>💬</span>
        <span>ভিজিটর ও এআই চ্যাট হিস্ট্রি (সর্বশেষ ১৫০টি)</span>
      </div>
      <span style="font-size:0.8rem; color:#94a3b8;">রিয়েল-টাইমে সেভ হচ্ছে</span>
    </div>

    <div style="overflow-x:auto;">
      <table class="admin-table">
        <thead>
          <tr>
            <th style="width:130px;">সময় ও ভাষা</th>
            <th style="width:140px;">এজেন্ট</th>
            <th style="width:30%;">ভিজিটর কী জানতে চেয়েছেন</th>
            <th style="width:38%;">এজেন্টের এআই রিপ্লাই</th>
            <th style="text-align:right;">লিড ও অর্ডার স্ট্যাটাস</th>
          </tr>
        </thead>
        <tbody>
          <?php if (empty($logs)): ?>
            <tr>
              <td colspan="5" style="text-align:center; padding:3rem; color:#64748b;">
                এখনো কোনো চ্যাট বার্তা রেকর্ড হয়নি। ওয়েবসাইটে ভিজিটররা আয়েশার সাথে চ্যাট করলে স্বয়ংক্রিয়ভাবে এখানে তালিকা চলে আসবে।
              </td>
            </tr>
          <?php else: ?>
            <?php foreach ($logs as $l): ?>
              <tr>
                <td>
                  <div style="font-size:0.85rem; color:#f8fafc; font-weight:600;">
                    <?= date('h:i A', strtotime($l['created_at'])) ?>
                  </div>
                  <div style="font-size:0.75rem; color:#94a3b8;">
                    <?= date('d M, Y', strtotime($l['created_at'])) ?>
                  </div>
                  <div style="margin-top:4px;">
                    <span class="admin-badge badge-info" style="font-size:0.7rem; padding:2px 6px;">
                      <?= strtoupper(e($l['lang'] ?? 'bn')) ?>
                    </span>
                  </div>
                </td>
                <td>
                  <div style="display:flex; align-items:center; gap:8px;">
                    <?php
                      $avatar = '/assets/img/agents/ayesha.png';
                      if (($l['agent_id'] ?? '') === 'tania') $avatar = '/assets/img/agents/tania.png';
                      if (($l['agent_id'] ?? '') === 'nirob') $avatar = '/assets/img/agents/nirob.png';
                    ?>
                    <img src="<?= $avatar ?>" alt="Agent" style="width:32px; height:32px; border-radius:50%; object-fit:cover; border:1px solid #38bdf8;">
                    <div>
                      <div style="font-weight:700; font-size:0.85rem; color:#f8fafc;">
                        <?= e($l['agent_name'] ?? 'আয়েশা') ?>
                      </div>
                      <div style="font-size:0.7rem; color:#64748b;">AI Consultant</div>
                    </div>
                  </div>
                </td>
                <td>
                  <div style="background:rgba(15,23,42,0.6); border:1px solid rgba(56,189,248,0.2); border-radius:8px; padding:10px 12px; color:#e2e8f0; font-size:0.88rem; line-height:1.45;">
                    <?= nl2br(e($l['user_message'] ?? '')) ?>
                  </div>
                </td>
                <td>
                  <div style="background:rgba(6,78,59,0.2); border:1px solid rgba(16,185,129,0.25); border-radius:8px; padding:10px 12px; color:#a7f3d0; font-size:0.88rem; line-height:1.45;">
                    <?= nl2br(e($l['bot_reply'] ?? '')) ?>
                  </div>
                </td>
                <td style="text-align:right;">
                  <?php 
                    $hasReceipt = (strpos($l['bot_reply'] ?? '', '[ORDER_RECEIPT:') !== false) || (strpos($l['bot_reply'] ?? '', '#AMP') !== false);
                    $hasCoupon = (strpos($l['bot_reply'] ?? '', 'VIP') !== false) || (strpos($l['bot_reply'] ?? '', 'কুপন') !== false);
                  ?>
                  <?php if ($hasReceipt): ?>
                    <span class="admin-badge badge-success" style="font-size:0.75rem; display:inline-block; margin-bottom:4px;">
                      💳 ইন-চ্যাট অর্ডার সম্পন্ন
                    </span>
                    <div style="font-size:0.7rem; color:#6ee7b7;">রসিদ প্রদান করা হয়েছে</div>
                  <?php elseif (!empty($l['whatsapp_handoff'])): ?>
                    <span class="admin-badge badge-warning" style="font-size:0.75rem; display:inline-block; margin-bottom:4px;">
                      🔥 WhatsApp লিড
                    </span>
                    <div style="font-size:0.7rem; color:#fbbf24;">অর্ডারে আগ্রহী</div>
                  <?php elseif ($hasCoupon): ?>
                    <span class="admin-badge badge-warning" style="font-size:0.75rem; display:inline-block; margin-bottom:4px; background:rgba(245,158,11,0.2); color:#f59e0b; border:1px solid rgba(245,158,11,0.3);">
                      🏷️ কুপন অফার
                    </span>
                  <?php else: ?>
                    <span class="admin-badge badge-info" style="font-size:0.75rem;">
                      ওয়েব আলোচনা
                    </span>
                  <?php endif; ?>
                </td>
              </tr>
            <?php endforeach; ?>
          <?php endif; ?>
        </tbody>
      </table>
    </div>
  </div>
<?php endif; ?>

<?php admin_footer(); ?>
