<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';

// Handle actions
if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = (string) ($_POST['action'] ?? '');
    if ($action === 'clear_old') {
        try {
            $pdo->exec("DELETE FROM customer_chat_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)");
            $message = '৩০ দিনের পূর্বের পুরনো চ্যাট লগসমূহ সফলভাবে মুছে ফেলা হয়েছে।';
        } catch (\Throwable $e) {
            $message = 'লগ ডিলিট করার সময় সমস্যা হয়েছে।';
        }
    }
}

// Filters
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

try {
    $totalLogs = (int) $pdo->query("SELECT COUNT(*) FROM customer_chat_logs")->fetchColumn();
    $todayLogs = (int) $pdo->query("SELECT COUNT(*) FROM customer_chat_logs WHERE DATE(created_at) = CURRENT_DATE")->fetchColumn();
    $waLeads = (int) $pdo->query("SELECT COUNT(*) FROM customer_chat_logs WHERE whatsapp_handoff = 1")->fetchColumn();
} catch (\Throwable $e) {}

// Query logs
$logs = [];
try {
    $stmt = $pdo->prepare("SELECT * FROM customer_chat_logs {$whereSql} ORDER BY id DESC LIMIT 150");
    $stmt->execute($params);
    $logs = $stmt->fetchAll();
} catch (\Throwable $e) {}

admin_header('আয়েশা এআই চ্যাট মনিটর ও লিড লগস', 'chat_logs');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<!-- Top Metrics -->
<div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-bottom: 2rem;">
  <div class="stat-card">
    <div class="stat-label">মোট চ্যাট কনভার্সেশন</div>
    <div class="stat-value" style="color:#38bdf8;"><?= number_format($totalLogs) ?> টি</div>
    <div class="stat-trend">ওয়েবসাইটে ভিজিটরদের প্রশ্নোত্তর</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">আজকের লাইভ চ্যাট</div>
    <div class="stat-value" style="color:#10b981;"><?= number_format($todayLogs) ?> টি</div>
    <div class="stat-trend" style="color:#a7f3d0;">গত ২৪ ঘণ্টার কাস্টমার এনগেজমেন্ট</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">WhatsApp সেলস লিড</div>
    <div class="stat-value" style="color:#f59e0b;"><?= number_format($waLeads) ?> টি</div>
    <div class="stat-trend" style="color:#fde68a;">সরাসরি WhatsApp-এ রেফার করা হয়েছে</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">সক্রিয় সাপোর্ট টিম</div>
    <div class="stat-value" style="color:#ec4899; font-size:1.4rem;">৩ জন এজেন্ট</div>
    <div class="stat-trend">আয়েশা, তানিয়া ও নীরব (২৪/৭ লাইভ)</div>
  </div>
</div>

<!-- Filters Bar -->
<div class="admin-card" style="margin-bottom: 1.5rem; padding: 1.25rem;">
  <form method="get" style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;">
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
        <a href="/admin/chat_logs.php" class="btn-admin btn-admin-ghost" style="padding:7px 12px; font-size:0.85rem;">
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
          <th style="text-align:right;">লিড স্ট্যাটাস</th>
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
                <?php if (!empty($l['whatsapp_handoff'])): ?>
                  <span class="admin-badge badge-warning" style="font-size:0.75rem; display:inline-block; margin-bottom:4px;">
                    🔥 WhatsApp লিড
                  </span>
                  <div style="font-size:0.7rem; color:#fbbf24;">অর্ডারে আগ্রহী</div>
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

<?php admin_footer(); ?>
