<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

// 1. Fetch KPI Metrics
$totalCust = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status != 'removed'")->fetchColumn();
$activeCust = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'active'")->fetchColumn();
$pendingOrders = (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status = 'pending_payment'")->fetchColumn();
$totalRevenue = (float) $pdo->query("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active')")->fetchColumn();
$todayRevenue = (float) $pdo->query("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active') AND DATE(created_at) = CURRENT_DATE")->fetchColumn();

// 2. Fetch Chat Logs Count Today
$todayChats = 0;
try {
    $todayChats = (int) $pdo->query("SELECT COUNT(DISTINCT session_id) FROM customer_chat_logs WHERE DATE(created_at) = CURRENT_DATE")->fetchColumn();
} catch (\Throwable $e) {}

// 3. Fetch Recent Pending Orders
$recentPending = [];
try {
    $stmt = $pdo->query("SELECT o.*, c.name as customer_name, c.whatsapp as customer_whatsapp 
                          FROM orders o 
                          LEFT JOIN customers c ON o.customer_id = c.id 
                          WHERE o.status = 'pending_payment' 
                          ORDER BY o.id DESC LIMIT 5");
    $recentPending = $stmt ? $stmt->fetchAll(PDO::FETCH_ASSOC) : [];
} catch (\Throwable $e) {}

// 4. Active Consultant Persona
$activePersona = setting($pdo, 'agent_primary_persona', 'nirob');
$personaDisplay = $activePersona === 'nirob' ? 'নীরব (Nirob)' : ($activePersona === 'tania' ? 'তানিয়া (Tania)' : 'আয়েশা (Ayesha)');

admin_header('মাস্টার ড্যাশবোর্ড', 'dashboard');
?>

<!-- 1. KPI Ribbon (Top 4 Metrics) -->
<div class="admin-kpi-grid">
  <!-- Revenue Card -->
  <div class="kpi-card kpi-revenue">
    <div>
      <div class="kpi-label">মোট অনুমোদিত আয়</div>
      <div class="kpi-val">৳<?= number_format($totalRevenue) ?></div>
      <div class="kpi-sub">আজকের আয়: <strong style="color:var(--admin-emerald)">৳<?= number_format($todayRevenue) ?></strong></div>
    </div>
    <div class="kpi-icon-bubble">💰</div>
  </div>

  <!-- Pending Orders Card -->
  <div class="kpi-card kpi-pending">
    <div>
      <div class="kpi-label">অপেক্ষমাণ পেমেন্ট কিউ</div>
      <div class="kpi-val" style="color:var(--admin-amber);"><?= $pendingOrders ?></div>
      <div class="kpi-sub"><?= $pendingOrders > 0 ? '⚠️ তাৎক্ষণিক যাচাই প্রয়োজন' : '✅ সব অর্ডার ভেরিফাইড' ?></div>
    </div>
    <div class="kpi-icon-bubble">⏳</div>
  </div>

  <!-- Active Customers Card -->
  <div class="kpi-card kpi-customers">
    <div>
      <div class="kpi-label">সক্রিয় কাস্টমার ও লাইসেন্স</div>
      <div class="kpi-val" style="color:var(--admin-cyan);"><?= $activeCust ?></div>
      <div class="kpi-sub">মোট রেজিস্টার্ড: <?= $totalCust ?> জন</div>
    </div>
    <div class="kpi-icon-bubble">👥</div>
  </div>

  <!-- Visitor Chats Card -->
  <div class="kpi-card kpi-chat">
    <div>
      <div class="kpi-label">আজকের কাস্টমার চ্যাট</div>
      <div class="kpi-val" style="color:var(--admin-purple);"><?= $todayChats ?></div>
      <div class="kpi-sub"><?= e($personaDisplay) ?> হ্যান্ডেল করছে</div>
    </div>
    <div class="kpi-icon-bubble">💬</div>
  </div>
</div>

<!-- 2. Quick Actions Strip -->
<div class="admin-card" style="padding: 1.25rem 1.5rem; margin-bottom: 2rem;">
  <div style="font-size:0.85rem; font-weight:700; color:var(--admin-cyan); text-transform:uppercase; letter-spacing:1px; margin-bottom:0.75rem;">
    ⚡ ১-ক্লিক কুইক অ্যাকশন হাব (নন-টেক শর্টকাট)
  </div>
  <div class="quick-action-strip" style="margin-bottom:0;">
    <a href="/admin/whatsapp_marketing.php" class="action-pill-btn" style="border-color:#10b981; color:#34d399;">
      <span>📱</span> <span>হোয়াটসঅ্যাপ মার্কেটিং ও লিড</span>
    </a>
    <a href="/admin/agent_settings.php" class="action-pill-btn" style="border-color:#38bdf8; color:#38bdf8;">
      <span>🤖</span> <span>এআই চ্যাট এজেন্ট ও ডিসকাউন্ট</span>
    </a>
    <a href="/admin/orders.php" class="action-pill-btn">
      <span>💳</span> <span>পেমেন্ট যাচাই করুন <?= $pendingOrders > 0 ? "({$pendingOrders})" : "" ?></span>
    </a>
    <a href="/admin/customers.php" class="action-pill-btn">
      <span>👥</span> <span>কাস্টমার লিস্ট দেখুন</span>
    </a>
    <a href="/admin/coupons.php" class="action-pill-btn">
      <span>🎟️</span> <span>নতুন কুপন কোড তৈরি</span>
    </a>
    <a href="/admin/broadcast.php" class="action-pill-btn">
      <span>📢</span> <span>সাইটে জরুরী নোটিশ দিন</span>
    </a>
    <a href="/admin/settings.php" class="action-pill-btn">
      <span>⚙️</span> <span>বিকাশ/নগদ নম্বর পরিবর্তন</span>
    </a>
    <a href="/admin/api_keys.php" class="action-pill-btn">
      <span>🔑</span> <span>এআই API Keys সেটআপ</span>
    </a>
  </div>
</div>

<!-- 3. Pending Orders Alert & Table -->
<div class="admin-card">
  <div class="admin-card-head">
    <h3>
      <span>⏳</span>
      <span>অপেক্ষমাণ পেমেন্ট কিউ (যাচাই ও লাইসেন্স ইস্যু)</span>
    </h3>
    <a href="/admin/orders.php" class="btn-admin btn-admin-primary">
      সব অর্ডার দেখুন &rarr;
    </a>
  </div>

  <?php if (!empty($recentPending)): ?>
    <div class="table-responsive">
      <table class="admin-table">
        <thead>
          <tr>
            <th>অর্ডার ID</th>
            <th>গ্রাহকের নাম</th>
            <th>WhatsApp নম্বর</th>
            <th>নির্বাচিত প্যাকেজ</th>
            <th>পরিশোধকৃত টাকা</th>
            <th>পেমেন্ট মেথড ও TrxID</th>
            <th>তারিখ</th>
            <th>দ্রুত অ্যাকশন</th>
          </tr>
        </thead>
        <tbody>
          <?php foreach ($recentPending as $ord): 
              $pkgMap = [
                  'video_studio' => '🎬 Video Studio (৳৩,৯৯৯)',
                  'fb_business' => '💼 FB Business (৳২,৯৯৯)',
                  'profile_page' => '📱 Profile Post (৳১,৯৯৯)',
                  'google_pro' => '🚀 Google AI Pro',
              ];
              $pkgLabel = $pkgMap[$ord['plan_name'] ?? ''] ?? $ord['plan_name'] ?? 'AutoMovie Pro Core';
              ?>
            <tr>
              <td><strong style="color:var(--admin-cyan);">#<?= (int) $ord['id'] ?></strong></td>
              <td><?= e($ord['customer_name'] ?? $ord['name'] ?? 'গ্রাহক') ?></td>
              <td>
                <a href="https://wa.me/<?= preg_replace('/\D+/', '', (string) ($ord['customer_whatsapp'] ?? $ord['whatsapp'] ?? '')) ?>" target="_blank" style="color:#34d399; text-decoration:none; font-weight:700;">
                  📱 <?= e($ord['customer_whatsapp'] ?? $ord['whatsapp'] ?? '—') ?>
                </a>
              </td>
              <td><span style="font-weight:700; color:#e2e8f0;"><?= e($pkgLabel) ?></span></td>
              <td><strong style="color:#34d399; font-size:1.05rem;">৳<?= number_format((float) ($ord['amount'] ?? 0)) ?></strong></td>
              <td>
                <span class="badge-status pending"><?= e($ord['payment_method'] ?? 'bKash/Nagad') ?></span>
                <span style="font-family:monospace; margin-left:6px; color:#cbd5e1;"><?= e($ord['transaction_id'] ?? '—') ?></span>
              </td>
              <td style="font-size:0.8rem; color:var(--admin-text-muted);"><?= date('d M, h:i A', strtotime($ord['created_at'])) ?></td>
              <td>
                <a href="/admin/orders.php?view_id=<?= (int) $ord['id'] ?>" class="btn-admin btn-admin-success" style="padding:4px 10px; font-size:0.8rem;">
                  ✓ রিভিউ ও অনুমোদন
                </a>
              </td>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  <?php else: ?>
    <div style="text-align:center; padding:2.5rem 1rem; color:var(--admin-text-muted);">
      <div style="font-size:2.5rem; margin-bottom:0.5rem;">🎉</div>
      <h4 style="color:#ffffff; margin:0 0 0.35rem; font-size:1.1rem;">বর্তমানে কোনো অপেক্ষমাণ পেমেন্ট নেই!</h4>
      <p style="margin:0; font-size:0.9rem;">সকল গ্রাহকের অর্ডার ও লাইসেন্স ইস্যু সফলভাবে সম্পন্ন হয়েছে।</p>
    </div>
  <?php endif; ?>
</div>

<!-- 4. System Health & Platform Infrastructure HUD -->
<div class="admin-card">
  <div class="admin-card-head">
    <h3>
      <span>🛡️</span>
      <span>সিস্টেম অবকাঠামো ও ক্লাউড স্ট্যাটাস</span>
    </h3>
    <span class="badge-status active">● সকল সার্ভিস ১০০% অপারেশনাল</span>
  </div>

  <div class="hud-grid">
    <div class="hud-item">
      <div class="hud-label">ওয়েব সার্ভার</div>
      <div class="hud-val">LiteSpeed PHP 8.3</div>
    </div>
    <div class="hud-item">
      <div class="hud-label">ডাটাবেজ ইঞ্জিন</div>
      <div class="hud-val" style="color:#34d399;">Hostinger MySQL Live</div>
    </div>
    <div class="hud-item">
      <div class="hud-label">গিটহাব অটো-ডিপ্লয়</div>
      <div class="hud-val" style="color:var(--admin-cyan);">Synced with main</div>
    </div>
    <div class="hud-item">
      <div class="hud-label">এআই সাপোর্ট কনসালট্যান্ট</div>
      <div class="hud-val" style="color:#c084fc;"><?= e($personaDisplay) ?> (Live)</div>
    </div>
    <div class="hud-item">
      <div class="hud-label">সার্ভার আইপি</div>
      <div class="hud-val" style="font-family:monospace; font-size:0.88rem;">193.203.184.176</div>
    </div>
    <div class="hud-item">
      <div class="hud-label">এসএসএল ও ডোমেইন</div>
      <div class="hud-val" style="color:#34d399;">automoviepro.com (HTTPS)</div>
    </div>
  </div>
</div>

<?php admin_footer(); ?>
