<?php
declare(strict_types=1);

function admin_header(string $title, string $active = ''): void
{
    global $pdo, $config;

    // Fetch pending order count and new leads count for notification badges
    $pendingCount = 0;
    $todayRevenue = 0.0;
    $newLeadCount = 0;
    try {
        $pendingCount = (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status = 'pending_payment'")->fetchColumn();
        $todayRevenue = (float) $pdo->query("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active') AND DATE(created_at) = CURRENT_DATE")->fetchColumn();
        $newLeadCount = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_leads WHERE status = 'new'")->fetchColumn();
    } catch (\Throwable $e) {}

    $navGroups = [
        'মূল নিয়ন্ত্রণ' => [
            'dashboard' => ['/admin/index.php', '📊', 'ড্যাশবোর্ড', null],
            'orders' => ['/admin/orders.php', '💳', 'পেমেন্ট ও অর্ডার কিউ', $pendingCount > 0 ? ['val' => $pendingCount, 'type' => 'badge-danger'] : null],
            'customers' => ['/admin/customers.php', '👥', 'কাস্টমার ও লাইসেন্স', null],
            'reviews' => ['/admin/reviews.php', '🌟', 'রিভিউ ও রেটিং (55+)', null],
        ],
        'মার্কেটিং ও সেলস' => [
            'whatsapp' => ['/admin/whatsapp_marketing.php', '📱', 'হোয়াটসঅ্যাপ মার্কেটিং ও লিড', $newLeadCount > 0 ? ['val' => $newLeadCount, 'type' => 'badge-warning'] : null],
            'agent_settings' => ['/admin/agent_settings.php', '🤖', 'এআই এজেন্ট ও ডিসকাউন্ট', null],
            'chat_logs' => ['/admin/chat_logs.php', '💬', 'আয়েশা চ্যাট লগস', null],
            'coupons' => ['/admin/coupons.php', '🎟️', 'ডিসকাউন্ট কুপন', null],
            'broadcast' => ['/admin/broadcast.php', '📢', 'লাইভ এলার্ট ও নোটিশ', null],
            'cms' => ['/admin/cms.php', '📝', 'ওয়েবসাইট CMS কন্টেন্ট', null],
        ],
        'সিস্টেম ও কনফিগারেশন' => [
            'settings' => ['/admin/settings.php', '⚙️', 'মূল্য ও পেমেন্ট নম্বর', null],
            'api_keys' => ['/admin/api_keys.php', '🔑', 'এআই এপিআই কি সেটিংস', null],
            'admins' => ['/admin/admins.php', '🛡️', 'পাসওয়ার্ড পরিবর্তন', null],
            'logs' => ['/admin/logs.php', '📋', 'সিস্টেম ট্র্যাকিং লগ', null],
        ]
    ];
    ?>
<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= e($title) ?> — AutoMovie Pro Master Admin</title>
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <link rel="stylesheet" href="/assets/css/admin.css">
  <style>
    /* Responsive Mobile Sidebar Drawer Toggle */
    @media (max-width: 900px) {
      .admin-sidebar {
        position: fixed;
        left: -280px;
        transition: left 0.3s ease;
      }
      .admin-sidebar.open {
        left: 0;
      }
      .sidebar-backdrop {
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.6);
        z-index: 998;
      }
      .sidebar-backdrop.show { display: block; }
    }
  </style>
</head>
<body class="admin-body">
  <div class="sidebar-backdrop" id="sidebarBackdrop" onclick="toggleAdminSidebar()"></div>
  <div class="admin-shell">
    
    <!-- LEFT SIDEBAR NAVIGATION -->
    <aside class="admin-sidebar" id="adminSidebar">
      <div class="admin-sidebar-brand">
        <img class="brand-logo-img" src="/assets/img/logo.png" alt="AutoMovie Pro Logo">
        <div class="brand-info">
          <div class="brand-title">AutoMovie <span>ADMIN</span></div>
          <div class="brand-status">
            <span class="status-dot"></span>
            <span>SYSTEM ACTIVE v4.5</span>
          </div>
        </div>
      </div>

      <div class="admin-nav-scroll">
        <?php foreach ($navGroups as $groupName => $items): ?>
          <div class="nav-group-section">
            <div class="nav-group-title"><?= e($groupName) ?></div>
            <ul class="admin-nav-list">
              <?php foreach ($items as $key => [$href, $icon, $label, $badge]): 
                  $isActive = ($active === $key);
                  ?>
                <li>
                  <a class="nav-item-link <?= $isActive ? 'active' : '' ?>" href="<?= e($href) ?>">
                    <span class="nav-icon"><?= $icon ?></span>
                    <span class="nav-label"><?= e($label) ?></span>
                    <?php if ($badge): ?>
                      <span class="nav-badge <?= e($badge['type']) ?>"><?= (int) $badge['val'] ?></span>
                    <?php endif; ?>
                  </a>
                </li>
              <?php endforeach; ?>
            </ul>
          </div>
        <?php endforeach; ?>
      </div>

      <div class="admin-sidebar-footer">
        <a class="sidebar-action-btn" href="/" target="_blank" rel="noopener">
          <span>🌐</span> <span>লাইভ ওয়েবসাইট দেখুন</span>
        </a>
        <a class="sidebar-action-btn btn-logout" href="/admin/logout.php">
          <span>🚪</span> <span>লগআউট (Logout)</span>
        </a>
      </div>
    </aside>

    <!-- MAIN DASHBOARD WORKSPACE -->
    <main class="admin-main">
      <header class="admin-topbar">
        <div class="topbar-left">
          <button type="button" class="btn-admin btn-admin-primary" style="display:none; padding:6px 10px;" id="sidebarToggleBtn" onclick="toggleAdminSidebar()" aria-label="Toggle Menu">
            ☰
          </button>
          <h1 class="topbar-title">
            <span><?= e($title) ?></span>
          </h1>
        </div>
        <div class="topbar-right">
          <div class="topbar-pill" id="liveClockPill">
            <span>⏰ ঢাকা:</span> <strong id="liveDhakaClock">--:--:--</strong>
          </div>
          <div class="topbar-pill">
            <span>💰 আজকের আয়:</span> <strong style="color:#34d399;">৳<?= (int) $todayRevenue ?></strong>
          </div>
          <div class="topbar-user">
            <div class="user-avatar-circle">A</div>
            <div>
              <div class="user-name-text">Super Admin</div>
              <div class="user-role-text">Master Terminal</div>
            </div>
          </div>
        </div>
      </header>

      <div class="admin-workspace">
<?php
}

function admin_footer(): void
{
    ?>
      </div><!-- /.admin-workspace -->
    </main><!-- /.admin-main -->
  </div><!-- /.admin-shell -->

  <script>
    // Live Dhaka Clock
    function updateDhakaClock() {
      const el = document.getElementById('liveDhakaClock');
      if (!el) return;
      const now = new Date();
      // UTC+6 for Dhaka
      const dhakaTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (6 * 3600000));
      el.textContent = dhakaTime.toLocaleTimeString('en-US', { hour12: true });
    }
    setInterval(updateDhakaClock, 1000);
    updateDhakaClock();

    // Mobile Sidebar Toggle
    function toggleAdminSidebar() {
      const sb = document.getElementById('adminSidebar');
      const bd = document.getElementById('sidebarBackdrop');
      if (sb) sb.classList.toggle('open');
      if (bd) bd.classList.toggle('show');
    }

    if (window.innerWidth <= 900) {
      const btn = document.getElementById('sidebarToggleBtn');
      if (btn) btn.style.display = 'inline-flex';
    }
  </script>
</body>
</html>
<?php
}
