<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_once dirname(__DIR__) . '/includes/whatsapp.php';
require_admin();

ensure_amp_migrations($pdo);

$message = '';
$error = '';
$tab = trim((string) ($_GET['tab'] ?? 'leads'));

// ---------------------------------------------------------
// POST ACTIONS HANDLER
// ---------------------------------------------------------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = (string) ($_POST['action'] ?? '');

    // 1. Add Manual Lead
    if ($action === 'add_lead') {
        $name = trim((string) ($_POST['name'] ?? ''));
        $phone = trim((string) ($_POST['phone'] ?? ''));
        $pkg = trim((string) ($_POST['interest_package'] ?? 'video_studio'));
        $notes = trim((string) ($_POST['notes'] ?? ''));

        if ($phone === '') {
            $error = 'অনুগ্রহ করে গ্রাহকের ফোন বা WhatsApp নম্বর লিখুন।';
        } else {
            $leadId = whatsapp_save_lead($pdo, $phone, $name ?: 'গ্রাহক', 'manual', $pkg, $notes);
            if ($leadId > 0) {
                $message = "নতুন লিড সফলভাবে যুক্ত করা হয়েছে!";
            } else {
                $error = 'লিড সংরক্ষণ করতে সমস্যা হয়েছে। নম্বর সঠিক কিনা যাচাই করুন।';
            }
        }
    }

    // 2. Update Lead Status
    elseif ($action === 'update_lead_status') {
        $leadId = (int) ($_POST['lead_id'] ?? 0);
        $newStatus = trim((string) ($_POST['status'] ?? 'new'));
        $allowed = ['new', 'contacted', 'interested', 'converted', 'closed'];
        if (in_array($newStatus, $allowed, true)) {
            $pdo->prepare("UPDATE whatsapp_leads SET status = ?, updated_at = NOW() WHERE id = ?")
                ->execute([$newStatus, $leadId]);
            $message = "লিডের স্ট্যাটাস সফলভাবে আপডেট করা হয়েছে।";
        }
    }

    // 3. Delete Lead
    elseif ($action === 'delete_lead') {
        $leadId = (int) ($_POST['lead_id'] ?? 0);
        $pdo->prepare("DELETE FROM whatsapp_leads WHERE id = ?")->execute([$leadId]);
        $message = "লিডটি মুছে ফেলা হয়েছে।";
    }

    // 4. Queue Outbox Message to Lead
    elseif ($action === 'send_lead_message') {
        $phone = trim((string) ($_POST['phone'] ?? ''));
        $msgBody = trim((string) ($_POST['message_body'] ?? ''));
        if ($phone !== '' && $msgBody !== '') {
            whatsapp_queue($pdo, $config, $phone, $msgBody, null);
            $message = "মেসেজটি সফলভাবে WhatsApp Outbox কিউতে যোগ করা হয়েছে!";
        } else {
            $error = 'ফোন নম্বর ও মেসেজ উভয়ই প্রদান করতে হবে।';
        }
    }

    // 5. Retry Outbox Message
    elseif ($action === 'retry_outbox') {
        $outboxId = (int) ($_POST['outbox_id'] ?? 0);
        $st = $pdo->prepare("SELECT * FROM whatsapp_outbox WHERE id = ?");
        $st->execute([$outboxId]);
        $row = $st->fetch();
        if ($row) {
            whatsapp_queue($pdo, $config, (string)$row['to_number'], (string)$row['message'], $row['customer_id'] ? (int)$row['customer_id'] : null);
            $message = "মেসেজটি পুনরায় কিউ করা হয়েছে!";
        }
    }

    // 6. Delete Outbox Message
    elseif ($action === 'delete_outbox') {
        $outboxId = (int) ($_POST['outbox_id'] ?? 0);
        $pdo->prepare("DELETE FROM whatsapp_outbox WHERE id = ?")->execute([$outboxId]);
        $message = "আউটবক্স মেসেজটি মুছে ফেলা হয়েছে।";
    }

    // 7. Clear Old Outbox
    elseif ($action === 'clear_outbox') {
        $pdo->exec("DELETE FROM whatsapp_outbox WHERE created_at < DATE_SUB(NOW(), INTERVAL 15 DAY)");
        $message = "১৫ দিনের পূর্বের সকল পুরনো আউটবক্স লগ সফলভাবে পরিষ্কার করা হয়েছে।";
    }

    // 8. Update Template
    elseif ($action === 'save_template') {
        $tplKey = trim((string) ($_POST['template_key'] ?? ''));
        $tplTitle = trim((string) ($_POST['title'] ?? ''));
        $tplBody = trim((string) ($_POST['body'] ?? ''));
        if ($tplKey !== '' && $tplBody !== '') {
            $pdo->prepare("UPDATE whatsapp_templates SET title = ?, body = ?, updated_at = NOW() WHERE template_key = ?")
                ->execute([$tplTitle, $tplBody, $tplKey]);
            $message = "টেমপ্লেট সফলভাবে আপডেট করা হয়েছে!";
        }
    }

    // 9. Save Automation & Gateway Settings
    elseif ($action === 'save_settings') {
        $waToken = trim((string) ($_POST['whatsapp_token'] ?? ''));
        $waPhoneId = trim((string) ($_POST['whatsapp_phone_id'] ?? ''));
        $adminWa = trim((string) ($_POST['admin_notify_whatsapp'] ?? ''));
        $autoWelcome = !empty($_POST['wa_auto_welcome_chat']) ? '1' : '0';
        $autoOrderPlaced = !empty($_POST['wa_auto_order_placed']) ? '1' : '0';

        set_setting($pdo, 'whatsapp_token', $waToken);
        set_setting($pdo, 'whatsapp_phone_id', $waPhoneId);
        set_setting($pdo, 'admin_notify_whatsapp', $adminWa);
        set_setting($pdo, 'wa_auto_welcome_chat', $autoWelcome);
        set_setting($pdo, 'wa_auto_order_placed', $autoOrderPlaced);

        $message = "হোয়াটসঅ্যাপ গেটওয়ে ও অটোমেশন সেটিংস সফলভাবে সংরক্ষিত হয়েছে!";
    }

    // 10. Broadcast Campaign Launch
    elseif ($action === 'launch_broadcast') {
        $targetAudience = trim((string) ($_POST['target_audience'] ?? 'leads'));
        $campaignMsg = trim((string) ($_POST['campaign_message'] ?? ''));

        if ($campaignMsg === '') {
            $error = 'অনুগ্রহ করে ক্যাম্পেইন মেসেজ লিখুন।';
        } else {
            $count = 0;
            if ($targetAudience === 'leads') {
                $recipients = $pdo->query("SELECT name, clean_phone as phone FROM whatsapp_leads WHERE status != 'closed'")->fetchAll();
            } elseif ($targetAudience === 'orders_pending') {
                $recipients = $pdo->query("SELECT name, whatsapp as phone FROM orders WHERE status = 'pending_payment'")->fetchAll();
            } else {
                $recipients = $pdo->query("SELECT name, whatsapp as phone FROM customers WHERE status != 'removed'")->fetchAll();
            }

            foreach ($recipients as $rc) {
                $p = trim((string) $rc['phone']);
                if ($p !== '') {
                    $personalized = str_replace('{name}', (string)$rc['name'], $campaignMsg);
                    whatsapp_queue($pdo, $config, $p, $personalized, null);
                    $count++;
                }
            }
            $message = "ক্যাম্পেইন সফলভাবে চালু করা হয়েছে! মোট {$count} জন গ্রাহকের জন্য মেসেজ কিউতে জমা হয়েছে।";
        }
    }
}

// ---------------------------------------------------------
// FETCH STATS
// ---------------------------------------------------------
$totalLeads = 0;
$newLeads = 0;
$convertedLeads = 0;
$outboxCount = 0;

try {
    $totalLeads = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_leads")->fetchColumn();
    $newLeads = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_leads WHERE status = 'new'")->fetchColumn();
    $convertedLeads = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_leads WHERE status = 'converted'")->fetchColumn();
    $outboxCount = (int) $pdo->query("SELECT COUNT(*) FROM whatsapp_outbox")->fetchColumn();
} catch (\Throwable $e) {}

// Fetch Templates
$templates = [];
try {
    $templates = $pdo->query("SELECT * FROM whatsapp_templates ORDER BY id ASC")->fetchAll(PDO::FETCH_ASSOC);
} catch (\Throwable $e) {}

admin_header('হোয়াটসঅ্যাপ মার্কেটিং ও লিড হাব', 'whatsapp');
?>

<style>
.tab-nav-bar {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--admin-border);
  margin-bottom: 2rem;
  overflow-x: auto;
  padding-bottom: 2px;
}
.tab-nav-btn {
  padding: 10px 18px;
  border-radius: 8px 8px 0 0;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.92rem;
  color: var(--admin-text-muted);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
  border-bottom: none;
  transition: all 0.2s ease;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tab-nav-btn:hover {
  color: var(--admin-text-main);
  background: rgba(255, 255, 255, 0.08);
}
.tab-nav-btn.active {
  color: var(--admin-cyan);
  background: var(--admin-card-bg);
  border-color: var(--admin-border);
  border-bottom: 2px solid var(--admin-cyan);
}
.badge-count {
  background: rgba(56, 189, 248, 0.2);
  color: #38bdf8;
  padding: 2px 7px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 700;
}
</style>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<?php if ($error): ?>
  <div style="background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#fda4af; font-size:0.95rem;">
    ⚠️ <?= e($error) ?>
  </div>
<?php endif; ?>

<!-- Top Metrics Ribbon -->
<div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-bottom: 2rem;">
  <div class="stat-card">
    <div class="stat-label">মোট সংগৃহীত লিড</div>
    <div class="stat-value" style="color:#38bdf8;"><?= number_format($totalLeads) ?> জন</div>
    <div class="stat-trend">চ্যাট, ওয়েবসাইট অর্ডার ও ম্যানুয়াল</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">নতুন লিড (নতুন সুযোগ)</div>
    <div class="stat-value" style="color:#f59e0b;"><?= number_format($newLeads) ?> টি</div>
    <div class="stat-trend" style="color:#fde68a;">অবিলম্বে যোগাযোগ প্রয়োজন</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">সফল সেলস কনভার্সন</div>
    <div class="stat-value" style="color:#10b981;"><?= number_format($convertedLeads) ?> জন</div>
    <div class="stat-trend" style="color:#a7f3d0;">অর্ডার নিশ্চিত করেছেন</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">আউটবক্স কিউ হিস্ট্রি</div>
    <div class="stat-value" style="color:#a855f7;"><?= number_format($outboxCount) ?> টি</div>
    <div class="stat-trend">স্বয়ংক্রিয় ও ম্যানুয়াল মেসেজ</div>
  </div>
</div>

<!-- Tab Navigation Bar -->
<div class="tab-nav-bar">
  <a href="?tab=leads" class="tab-nav-btn <?= $tab === 'leads' ? 'active' : '' ?>">
    <span>👥 লিড ডিরেক্টরি</span>
    <span class="badge-count"><?= $totalLeads ?></span>
  </a>
  <a href="?tab=outbox" class="tab-nav-btn <?= $tab === 'outbox' ? 'active' : '' ?>">
    <span>📤 মেসেজ আউটবক্স</span>
    <span class="badge-count" style="background:rgba(168,85,247,0.2); color:#c084fc;"><?= $outboxCount ?></span>
  </a>
  <a href="?tab=templates" class="tab-nav-btn <?= $tab === 'templates' ? 'active' : '' ?>">
    <span>📝 মেসেজ টেমপ্লেট</span>
    <span class="badge-count" style="background:rgba(16,185,129,0.2); color:#34d399;"><?= count($templates) ?></span>
  </a>
  <a href="?tab=broadcast" class="tab-nav-btn <?= $tab === 'broadcast' ? 'active' : '' ?>">
    <span>📢 বাল্ক ক্যাম্পেইন সেন্ডার</span>
  </a>
  <a href="?tab=settings" class="tab-nav-btn <?= $tab === 'settings' ? 'active' : '' ?>">
    <span>⚙️ অটোমেশন ও গেটওয়ে</span>
  </a>
</div>

<!-- =========================================================
     TAB 1: LEADS DIRECTORY
     ========================================================= -->
<?php if ($tab === 'leads'): 
    $filterStatus = trim((string) ($_GET['status'] ?? 'all'));
    $filterSource = trim((string) ($_GET['source'] ?? 'all'));
    $q = trim((string) ($_GET['q'] ?? ''));

    $where = [];
    $p = [];
    if ($filterStatus !== 'all' && $filterStatus !== '') {
        $where[] = "status = ?";
        $p[] = $filterStatus;
    }
    if ($filterSource !== 'all' && $filterSource !== '') {
        $where[] = "source = ?";
        $p[] = $filterSource;
    }
    if ($q !== '') {
        $where[] = "(name LIKE ? OR phone LIKE ? OR clean_phone LIKE ? OR notes LIKE ?)";
        $p[] = "%{$q}%";
        $p[] = "%{$q}%";
        $p[] = "%{$q}%";
        $p[] = "%{$q}%";
    }
    $whereSql = $where ? ('WHERE ' . implode(' AND ', $where)) : '';

    $leads = [];
    try {
        $stmt = $pdo->prepare("SELECT * FROM whatsapp_leads {$whereSql} ORDER BY id DESC LIMIT 100");
        $stmt->execute($p);
        $leads = $stmt->fetchAll(PDO::FETCH_ASSOC);
    } catch (\Throwable $e) {}
    ?>

  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:1.5rem;">
    <!-- Filters Form -->
    <form method="get" style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
      <input type="hidden" name="tab" value="leads">
      <input type="text" name="q" value="<?= e($q) ?>" placeholder="নাম বা মোবাইল নম্বর..." class="form-input" style="width:200px; padding:6px 12px; font-size:0.88rem;">
      <select name="status" class="form-select" style="width:140px; padding:6px 12px; font-size:0.88rem;" onchange="this.form.submit()">
        <option value="all" <?= $filterStatus === 'all' ? 'selected' : '' ?>>সকল স্ট্যাটাস</option>
        <option value="new" <?= $filterStatus === 'new' ? 'selected' : '' ?>>নতুন (New)</option>
        <option value="contacted" <?= $filterStatus === 'contacted' ? 'selected' : '' ?>>যোগাযোগ হয়েছে</option>
        <option value="interested" <?= $filterStatus === 'interested' ? 'selected' : '' ?>>আগ্রহী (Interested)</option>
        <option value="converted" <?= $filterStatus === 'converted' ? 'selected' : '' ?>>কনভার্টেড (Sales)</option>
        <option value="closed" <?= $filterStatus === 'closed' ? 'selected' : '' ?>>ক্লোজড</option>
      </select>
      <select name="source" class="form-select" style="width:140px; padding:6px 12px; font-size:0.88rem;" onchange="this.form.submit()">
        <option value="all" <?= $filterSource === 'all' ? 'selected' : '' ?>>সকল সোর্স</option>
        <option value="chat" <?= $filterSource === 'chat' ? 'selected' : '' ?>>💬 চ্যাট এজেন্ট</option>
        <option value="order" <?= $filterSource === 'order' ? 'selected' : '' ?>>💳 ওয়েবসাইট অর্ডার</option>
        <option value="manual" <?= $filterSource === 'manual' ? 'selected' : '' ?>>✍️ ম্যানুয়াল</option>
      </select>
      <button type="submit" class="btn-admin btn-admin-primary" style="padding:6px 14px; font-size:0.88rem;">সার্চ</button>
      <?php if ($q || $filterStatus !== 'all' || $filterSource !== 'all'): ?>
        <a href="?tab=leads" style="color:#94a3b8; font-size:0.85rem; text-decoration:none;">রিসেট</a>
      <?php endif; ?>
    </form>

    <!-- Add Manual Lead Button -->
    <button type="button" class="btn-admin btn-admin-primary" onclick="document.getElementById('addLeadModal').style.display='flex'" style="background:linear-gradient(135deg, #10b981, #059669); font-weight:700;">
      ➕ নতুন লিড যোগ করুন
    </button>
  </div>

  <div class="admin-card" style="padding:0; overflow:hidden;">
    <div class="table-responsive">
      <table class="data-table">
        <thead>
          <tr>
            <th>গ্রাহকের নাম & নম্বর</th>
            <th>সোর্স ও প্যাকেজ</th>
            <th>শেষ মেসেজ / নোট</th>
            <th>স্ট্যাটাস</th>
            <th>তারিখ</th>
            <th style="text-align:right;">অ্যাকশন</th>
          </tr>
        </thead>
        <tbody>
          <?php if (empty($leads)): ?>
            <tr>
              <td colspan="6" style="text-align:center; padding:3rem 1rem; color:#64748b;">
                কোনো লিড পাওয়া যায়নি। চ্যাট এজেন্ট বা অর্ডার আসলে এখানে স্বয়ংক্রিয়ভাবে জমা হবে।
              </td>
            </tr>
          <?php else: ?>
            <?php foreach ($leads as $ld): 
                $clean = whatsapp_clean_phone((string)$ld['clean_phone'] ?: (string)$ld['phone'], true);
                $defGreeting = "আসসালামু আলাইকুম " . ($ld['name'] !== 'ওয়েবসাইট ভিজিটর' ? $ld['name'] : 'স্যার') . "! AutoMovie Pro টিম থেকে বলছি। ওয়েবসাইটে আপনার সাথে কথা হয়েছিল। আমি কি আপনাকে কোনো বিষয়ে সাহায্য করতে পারি?";
                $directWaUrl = whatsapp_build_share_url($clean, $defGreeting);
                ?>
              <tr>
                <td>
                  <strong style="color:#f8fafc; font-size:0.95rem;"><?= e($ld['name']) ?></strong>
                  <div style="display:flex; align-items:center; gap:6px; margin-top:2px;">
                    <span style="font-family:monospace; color:#38bdf8; font-size:0.88rem;"><?= e($ld['phone']) ?></span>
                    <button type="button" onclick="navigator.clipboard.writeText('<?= e($clean) ?>'); alert('নম্বর কপি করা হয়েছে!');" style="background:none; border:none; color:#64748b; cursor:pointer; font-size:0.75rem;" title="কপি করুন">📋</button>
                  </div>
                </td>
                <td>
                  <?php if ($ld['source'] === 'chat'): ?>
                    <span class="admin-badge badge-info">💬 লাইভ চ্যাট</span>
                  <?php elseif ($ld['source'] === 'order'): ?>
                    <span class="admin-badge badge-success">💳 অর্ডার</span>
                  <?php else: ?>
                    <span class="admin-badge badge-warning">✍️ ম্যানুয়াল</span>
                  <?php endif; ?>
                  <div style="font-size:0.8rem; color:#94a3b8; margin-top:4px;">
                    <?= e($ld['interest_package'] ?: 'Social Media Content Automation Engine') ?>
                  </div>
                </td>
                <td style="max-width:280px;">
                  <div style="font-size:0.85rem; color:#cbd5e1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                    <?= e($ld['last_message'] ?: ($ld['notes'] ?: 'কোনো নোট নেই')) ?>
                  </div>
                  <?php if (!empty($ld['notes']) && !empty($ld['last_message'])): ?>
                    <small style="color:#64748b; font-size:0.75rem;"><?= e($ld['notes']) ?></small>
                  <?php endif; ?>
                </td>
                <td>
                  <form method="post" style="margin:0;">
                    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                    <input type="hidden" name="action" value="update_lead_status">
                    <input type="hidden" name="lead_id" value="<?= (int) $ld['id'] ?>">
                    <select name="status" class="form-select" style="padding:3px 8px; font-size:0.8rem; border-radius:6px;" onchange="this.form.submit()">
                      <option value="new" <?= $ld['status'] === 'new' ? 'selected' : '' ?>>🟡 নতুন (New)</option>
                      <option value="contacted" <?= $ld['status'] === 'contacted' ? 'selected' : '' ?>>🔵 যোগাযোগ হয়েছে</option>
                      <option value="interested" <?= $ld['status'] === 'interested' ? 'selected' : '' ?>>🟣 আগ্রহী</option>
                      <option value="converted" <?= $ld['status'] === 'converted' ? 'selected' : '' ?>>🟢 সেলস কনভার্টেড</option>
                      <option value="closed" <?= $ld['status'] === 'closed' ? 'selected' : '' ?>>⚪ ক্লোজড</option>
                    </select>
                  </form>
                </td>
                <td style="font-size:0.8rem; color:#64748b;">
                  <?= date('d M Y, h:i A', strtotime($ld['created_at'])) ?>
                </td>
                <td style="text-align:right;">
                  <div style="display:inline-flex; gap:6px; align-items:center;">
                    <a href="<?= e($directWaUrl) ?>" target="_blank" rel="noopener" class="btn-admin" style="background:#10b981; color:#022c22; font-weight:700; font-size:0.8rem; padding:5px 10px; border-radius:6px; text-decoration:none; display:inline-flex; align-items:center; gap:4px;">
                      <span>💬</span> <span>চ্যাট</span>
                    </a>
                    <button type="button" class="btn-admin btn-admin-ghost" style="padding:5px 8px; font-size:0.8rem;" onclick="openMsgModal('<?= e($clean) ?>', '<?= e($ld['name']) ?>')">
                      ✉️
                    </button>
                    <form method="post" style="display:inline; margin:0;" onsubmit="return confirm('এই লিডটি মুছে ফেলতে চান?');">
                      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                      <input type="hidden" name="action" value="delete_lead">
                      <input type="hidden" name="lead_id" value="<?= (int) $ld['id'] ?>">
                      <button type="submit" class="btn-admin btn-admin-ghost" style="padding:5px 8px; font-size:0.8rem; color:#f43f5e;" title="মুছুন">
                        🗑️
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            <?php endforeach; ?>
          <?php endif; ?>
        </tbody>
      </table>
    </div>
  </div>

  <!-- MODAL: ADD LEAD -->
  <div id="addLeadModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:9999; align-items:center; justify-content:center; padding:1rem;">
    <div style="background:var(--admin-sidebar-bg); border:1px solid var(--admin-border); border-radius:14px; max-width:480px; width:100%; padding:1.5rem; box-shadow:0 20px 40px rgba(0,0,0,0.5);">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem;">
        <h3 style="margin:0; font-size:1.15rem; color:#f8fafc;">➕ নতুন লিড যোগ করুন</h3>
        <button type="button" onclick="document.getElementById('addLeadModal').style.display='none'" style="background:none; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer;">&times;</button>
      </div>
      <form method="post">
        <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
        <input type="hidden" name="action" value="add_lead">
        <div class="form-group">
          <label class="form-label">গ্রাহকের নাম</label>
          <input type="text" name="name" class="form-input" placeholder="যেমন: মো: রফিকুল ইসলাম">
        </div>
        <div class="form-group">
          <label class="form-label">WhatsApp বা মোবাইল নম্বর *</label>
          <input type="text" name="phone" class="form-input" placeholder="যেমন: 01712345678" required style="font-weight:700; color:#38bdf8;">
        </div>
        <div class="form-group">
          <label class="form-label">প্যাকেজ আগ্রহ</label>
          <select name="interest_package" class="form-select">
            <option value="Social Media Content Automation Engine (৳৩,৯৯৯)">Social Media Content Automation Engine (৳৩,৯৯৯)</option>
            <option value="FB Business Manager & Ads (৳২,৯৯৯)">FB Business Manager & Ads (৳২,৯৯৯)</option>
            <option value="FB Profile Auto Pilot (৳১,৯৯৯)">FB Profile Auto Pilot (৳১,৯৯৯)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">নোট বা মন্তব্য</label>
          <textarea name="notes" class="form-textarea" rows="2" placeholder="কাস্টমারের সাথে কথা বলার সারাংশ বা অনুরোধ..."></textarea>
        </div>
        <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:1.5rem;">
          <button type="button" class="btn-admin btn-admin-ghost" onclick="document.getElementById('addLeadModal').style.display='none'">বাতিল</button>
          <button type="submit" class="btn-admin btn-admin-primary">সংরক্ষণ করুন</button>
        </div>
      </form>
    </div>
  </div>

  <!-- MODAL: QUICK SEND MESSAGE -->
  <div id="quickMsgModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:9999; align-items:center; justify-content:center; padding:1rem;">
    <div style="background:var(--admin-sidebar-bg); border:1px solid var(--admin-border); border-radius:14px; max-width:540px; width:100%; padding:1.5rem; box-shadow:0 20px 40px rgba(0,0,0,0.5);">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem;">
        <h3 style="margin:0; font-size:1.15rem; color:#f8fafc;">✉️ কাস্টমারকে মেসেজ পাঠান</h3>
        <button type="button" onclick="document.getElementById('quickMsgModal').style.display='none'" style="background:none; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer;">&times;</button>
      </div>
      <form method="post">
        <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
        <input type="hidden" name="action" value="send_lead_message">
        <input type="hidden" name="phone" id="modalTargetPhone" value="">
        
        <div style="margin-bottom:1rem; background:rgba(0,0,0,0.3); padding:10px; border-radius:8px;">
          <span style="color:#94a3b8; font-size:0.85rem;">প্রাপক: </span>
          <strong id="modalTargetName" style="color:#f8fafc;"></strong>
          <span style="color:#38bdf8; font-family:monospace; margin-left:6px;" id="modalTargetPhoneDisplay"></span>
        </div>

        <div class="form-group">
          <label class="form-label">রেডিমেড টেমপ্লেট নির্বাচন করুন (ঐচ্ছিক)</label>
          <select id="modalTemplateSelector" class="form-select" onchange="applyTemplateToModal(this.value)">
            <option value="">-- কাস্টম মেসেজ লিখুন --</option>
            <?php foreach ($templates as $t): ?>
              <option value="<?= e(json_encode($t)) ?>"><?= e($t['title']) ?></option>
            <?php endforeach; ?>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">মেসেজ কন্টেন্ট *</label>
          <textarea name="message_body" id="modalMessageBody" class="form-textarea" rows="6" required></textarea>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:1.5rem;">
          <a href="#" id="modalDirectWaLink" target="_blank" rel="noopener" class="btn-admin" style="background:#10b981; color:#022c22; font-weight:700; text-decoration:none;">
            💬 WhatsApp-এ সরাসরি ওপেন করুন
          </a>
          <div style="display:flex; gap:10px;">
            <button type="button" class="btn-admin btn-admin-ghost" onclick="document.getElementById('quickMsgModal').style.display='none'">বাতিল</button>
            <button type="submit" class="btn-admin btn-admin-primary">আউটবক্স কিউতে পাঠান</button>
          </div>
        </div>
      </form>
    </div>
  </div>

  <script>
    let curModalName = '';
    function openMsgModal(phone, name) {
      curModalName = name;
      document.getElementById('modalTargetPhone').value = phone;
      document.getElementById('modalTargetPhoneDisplay').innerText = phone;
      document.getElementById('modalTargetName').innerText = name;
      document.getElementById('modalMessageBody').value = 'আসসালামু আলাইকুম ' + (name !== 'ওয়েবসাইট ভিজিটর' ? name : 'স্যার') + '! AutoMovie Pro টিম থেকে বলছি।';
      updateModalDirectWa();
      document.getElementById('quickMsgModal').style.display = 'flex';
    }

    function applyTemplateToModal(jsonStr) {
      if (!jsonStr) return;
      try {
        const tpl = JSON.parse(jsonStr);
        let text = tpl.body;
        text = text.replace(/\{name\}/g, curModalName !== 'ওয়েবসাইট ভিজিটর' ? curModalName : 'স্যার');
        text = text.replace(/\{discount\}/g, '৫০০');
        text = text.replace(/\{coupon\}/g, 'VIP500');
        document.getElementById('modalMessageBody').value = text;
        updateModalDirectWa();
      } catch (e) {}
    }

    function updateModalDirectWa() {
      const phone = document.getElementById('modalTargetPhone').value;
      const text = document.getElementById('modalMessageBody').value;
      document.getElementById('modalDirectWaLink').href = 'https://wa.me/' + encodeURIComponent(phone) + '?text=' + encodeURIComponent(text);
    }
    document.getElementById('modalMessageBody').addEventListener('input', updateModalDirectWa);
  </script>

<!-- =========================================================
     TAB 2: OUTBOX QUEUE
     ========================================================= -->
<?php elseif ($tab === 'outbox'): 
    $outbox = [];
    try {
        $outbox = $pdo->query("SELECT * FROM whatsapp_outbox ORDER BY id DESC LIMIT 100")->fetchAll(PDO::FETCH_ASSOC);
    } catch (\Throwable $e) {}
    ?>

  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
    <p style="color:#94a3b8; font-size:0.9rem; margin:0;">
      সিস্টেম ও অ্যাডমিন দ্বারা কিউ করা সকল WhatsApp মেসেজের লাইভ স্টেটাস:
    </p>
    <form method="post" style="margin:0;" onsubmit="return confirm('১৫ দিনের পূর্বের পুরনো আউটবক্স মুছে ফেলতে চান?');">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="clear_outbox">
      <button type="submit" class="btn-admin btn-admin-ghost" style="color:#f43f5e; font-size:0.85rem;">
        🧹 পুরনো আউটবক্স ক্লিয়ার করুন
      </button>
    </form>
  </div>

  <div class="admin-card" style="padding:0; overflow:hidden;">
    <div class="table-responsive">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>প্রাপক নম্বর</th>
            <th>মেসেজ কন্টেন্ট</th>
            <th>স্ট্যাটাস</th>
            <th>তারিখ</th>
            <th style="text-align:right;">অ্যাকশন</th>
          </tr>
        </thead>
        <tbody>
          <?php if (empty($outbox)): ?>
            <tr>
              <td colspan="6" style="text-align:center; padding:3rem 1rem; color:#64748b;">
                আউটবক্স সম্পূর্ণ পরিষ্কার। কোনো মেসেজ কিউ নেই।
              </td>
            </tr>
          <?php else: ?>
            <?php foreach ($outbox as $msg): 
                $clean = whatsapp_clean_phone((string)$msg['to_number'], true);
                $directWa = whatsapp_build_share_url($clean, (string)$msg['message']);
                ?>
              <tr>
                <td style="color:#64748b; font-family:monospace;">#<?= (int) $msg['id'] ?></td>
                <td>
                  <strong style="color:#38bdf8; font-family:monospace;"><?= e($msg['to_number']) ?></strong>
                </td>
                <td style="max-width:380px;">
                  <div style="font-size:0.85rem; color:#e2e8f0; line-height:1.4; white-space:pre-line; max-height:80px; overflow-y:auto;">
                    <?= e($msg['message']) ?>
                  </div>
                </td>
                <td>
                  <?php if ($msg['status'] === 'sent'): ?>
                    <span class="admin-badge badge-success">✓ সফলভাবে প্রেরিত</span>
                  <?php elseif ($msg['status'] === 'failed'): ?>
                    <span class="admin-badge badge-danger">✗ ব্যর্থ (Failed)</span>
                  <?php elseif ($msg['status'] === 'logged_only'): ?>
                    <span class="admin-badge badge-info">📝 সেভড (Logged)</span>
                  <?php else: ?>
                    <span class="admin-badge badge-warning">⏳ অপেক্ষমান কিউ</span>
                  <?php endif; ?>
                </td>
                <td style="font-size:0.8rem; color:#64748b;">
                  <?= date('d M Y, h:i A', strtotime($msg['created_at'])) ?>
                </td>
                <td style="text-align:right;">
                  <div style="display:inline-flex; gap:6px;">
                    <a href="<?= e($directWa) ?>" target="_blank" rel="noopener" class="btn-admin" style="background:#10b981; color:#022c22; font-weight:700; font-size:0.8rem; padding:4px 8px; border-radius:6px; text-decoration:none;" title="WhatsApp-এ সরাসরি পাঠান">
                      💬 1-Click
                    </a>
                    <form method="post" style="display:inline; margin:0;">
                      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                      <input type="hidden" name="action" value="retry_outbox">
                      <input type="hidden" name="outbox_id" value="<?= (int) $msg['id'] ?>">
                      <button type="submit" class="btn-admin btn-admin-ghost" style="padding:4px 8px; font-size:0.8rem;" title="পুনরায় কিউ করুন">
                        🔄
                      </button>
                    </form>
                    <form method="post" style="display:inline; margin:0;" onsubmit="return confirm('মুছে ফেলতে চান?');">
                      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                      <input type="hidden" name="action" value="delete_outbox">
                      <input type="hidden" name="outbox_id" value="<?= (int) $msg['id'] ?>">
                      <button type="submit" class="btn-admin btn-admin-ghost" style="padding:4px 8px; font-size:0.8rem; color:#f43f5e;" title="মুছুন">
                        🗑️
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            <?php endforeach; ?>
          <?php endif; ?>
        </tbody>
      </table>
    </div>
  </div>

<!-- =========================================================
     TAB 3: TEMPLATES
     ========================================================= -->
<?php elseif ($tab === 'templates'): ?>

  <div style="margin-bottom:1.5rem;">
    <p style="color:#94a3b8; font-size:0.9rem; margin-top:0;">
      গ্রাহকদের সাথে দ্রুত ও আকর্ষণীয় যোগাযোগের জন্য প্রি-বিল্ট বিশ্বমানের বাংলা টেমপ্লেটসমূহ। আপনি যেকোনো টেমপ্লেট আপনার প্রয়োজন অনুযায়ী এডিট ও কাস্টমাইজ করতে পারবেন:
    </p>
  </div>

  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap:1.5rem;">
    <?php foreach ($templates as $tpl): ?>
      <div class="admin-card">
        <form method="post">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="action" value="save_template">
          <input type="hidden" name="template_key" value="<?= e($tpl['template_key']) ?>">

          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <div style="font-weight:700; color:#38bdf8; font-size:1.05rem;">
              <?= e($tpl['title']) ?>
            </div>
            <span class="admin-badge badge-info" style="font-family:monospace;"><?= e($tpl['template_key']) ?></span>
          </div>

          <div class="form-group">
            <label class="form-label" style="font-size:0.8rem;">শিরোনাম</label>
            <input type="text" name="title" class="form-input" value="<?= e($tpl['title']) ?>" required>
          </div>

          <div class="form-group">
            <label class="form-label" style="font-size:0.8rem;">মেসেজ বডি (Dynamic Tags: {name}, {discount}, {coupon}, {package}, {price}, {order_id})</label>
            <textarea name="body" class="form-textarea" rows="6" required style="line-height:1.5; font-size:0.9rem;"><?= e($tpl['body']) ?></textarea>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:1rem;">
            <button type="button" class="btn-admin btn-admin-ghost" onclick="navigator.clipboard.writeText(this.closest('form').querySelector('textarea').value); alert('টেমপ্লেট কপি করা হয়েছে!');" style="font-size:0.82rem;">
              📋 কপি করুন
            </button>
            <button type="submit" class="btn-admin btn-admin-primary" style="font-size:0.85rem; padding:6px 14px;">
              💾 টেমপ্লেট সেভ করুন
            </button>
          </div>
        </form>
      </div>
    <?php endforeach; ?>
  </div>

<!-- =========================================================
     TAB 4: BROADCAST CAMPAIGN
     ========================================================= -->
<?php elseif ($tab === 'broadcast'): ?>

  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap:1.5rem; align-items:start;">
    
    <!-- Campaign Launcher Form -->
    <div class="admin-card">
      <div class="card-header">
        <div class="card-title">
          <span>📢</span>
          <span>বাল্ক ক্যাম্পেইন তৈরি ও প্রেরণ</span>
        </div>
      </div>

      <form method="post" onsubmit="return confirm('আপনি কি নিশ্চিত যে সকল নির্বাচিত গ্রাহকের জন্য মেসেজ কিউ চালু করতে চান?');">
        <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
        <input type="hidden" name="action" value="launch_broadcast">

        <div class="form-group">
          <label class="form-label">টার্গেট গ্রাহক গ্রুপ নির্বাচন করুন *</label>
          <select name="target_audience" class="form-select">
            <option value="leads">👥 সকল চ্যাট ও ইনবক্স লিড (যাদের এখনও অর্ডার চূড়ান্ত হয়নি)</option>
            <option value="orders_pending">⏳ সকল অপেক্ষমান (Pending Payment) অর্ডার গ্রাহক</option>
            <option value="all_customers">🌟 সকল রেজিস্টার্ড কাস্টমার ও লাইসেন্স হোল্ডার</option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">ক্যাম্পেইন মেসেজ কন্টেন্ট *</label>
          <textarea name="campaign_message" class="form-textarea" rows="7" placeholder="প্রিয় {name}, AutoMovie Pro-তে বিশেষ মেগা অফার চলছে!..." required></textarea>
          <small style="color:#64748b; font-size:0.75rem;">গ্রাহকের নাম ডায়নামিক বসাতে <strong>{name}</strong> ট্যাগটি ব্যবহার করুন।</small>
        </div>

        <div style="margin-top:1.5rem;">
          <button type="submit" class="btn-admin btn-admin-primary" style="width:100%; padding:12px; font-size:1rem; font-weight:700;">
            🚀 ক্যাম্পেইন কিউতে পাঠান (Launch Queue)
          </button>
        </div>
      </form>
    </div>

    <!-- Safety Instructions Card -->
    <div class="admin-card" style="border-left:4px solid #38bdf8;">
      <h3 style="margin-top:0; font-size:1.15rem; color:#f8fafc; display:flex; align-items:center; gap:8px;">
        <span>🛡️</span> <span>মেটা হোয়াটসঅ্যাপ সেফটি গাইডলাইন</span>
      </h3>
      <p style="color:#94a3b8; font-size:0.9rem; line-height:1.6;">
        WhatsApp-এ বাল্ক মেসেজ পাঠানোর সময় মেটা অ্যান্টি-স্প্যাম অ্যালগরিদম সক্রিয় থাকে। আপনার ব্যক্তিগত নম্বর যেন কখনো ব্যান না হয়, সেজন্য আমাদের সিস্টেম ২টি সম্পূর্ণ নিরাপদ পদ্ধতি প্রদান করে:
      </p>
      <ul style="color:#cbd5e1; font-size:0.88rem; line-height:1.8; padding-left:1.25rem;">
        <li><strong>১-ক্লিক পার্সোনাল ব্রডকাস্ট:</strong> আউটবক্স পেজ থেকে ১-ক্লিকে WhatsApp Web ওপেন করে মেসেজ পাঠানো সবচেয়ে নিরাপদ ও প্রাকৃতিক।</li>
        <li><strong>মেটা ক্লাউড এপিআই:</strong> আপনি যদি অফিশিয়াল মেটা বিজনেস ক্লাউড এপিআই দিয়ে মেসেজ পাঠাতে চান, সেটিংস ট্যাবে আপনার Token ও Phone ID দিয়ে স্বয়ংক্রিয় বাল্ক ডেলিভারি চালু করতে পারেন।</li>
      </ul>
    </div>

  </div>

<!-- =========================================================
     TAB 5: SETTINGS & GATEWAY
     ========================================================= -->
<?php elseif ($tab === 'settings'): 
    $curToken = setting($pdo, 'whatsapp_token', '');
    $curPhoneId = setting($pdo, 'whatsapp_phone_id', '');
    $curAdminWa = setting($pdo, 'admin_notify_whatsapp', '8801684355055');
    $curAutoWelcome = setting($pdo, 'wa_auto_welcome_chat', '1') === '1';
    $curAutoOrder = setting($pdo, 'wa_auto_order_placed', '1') === '1';
    ?>

  <form method="post" class="admin-form">
    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
    <input type="hidden" name="action" value="save_settings">

    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap:1.5rem; align-items:start;">

      <!-- Automation Triggers -->
      <div class="admin-card">
        <div class="card-header">
          <div class="card-title">
            <span>⚡</span>
            <span>স্বয়ংক্রিয় WhatsApp মার্কেটিং ট্রিগারসমূহ</span>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label" style="display:flex; align-items:center; gap:8px;">
            <input type="checkbox" name="wa_auto_welcome_chat" value="1" <?= $curAutoWelcome ? 'checked' : '' ?> style="width:18px; height:18px; accent-color:#10b981;">
            <span style="font-weight:700; color:#34d399;">চ্যাটে কাস্টমার নম্বর দিলে স্বয়ংক্রিয়ভাবে আউটবক্সে ডেমো ও স্বাগতম বার্তা যোগ হবে</span>
          </label>
          <small style="color:#64748b; font-size:0.75rem; display:block; margin-left:26px;">ভিজিটর লাইভ চ্যাটে নিজের ফোন বা WhatsApp নম্বর দেওয়া মাত্রই আউটবক্সে স্বাগতম বার্তা কিউ হবে।</small>
        </div>

        <div class="form-group">
          <label class="form-label" style="display:flex; align-items:center; gap:8px;">
            <input type="checkbox" name="wa_auto_order_placed" value="1" <?= $curAutoOrder ? 'checked' : '' ?> style="width:18px; height:18px; accent-color:#38bdf8;">
            <span style="font-weight:700; color:#38bdf8;">ওয়েবসাইটে নতুন অর্ডার প্লেস হলে কাস্টমারের WhatsApp-এ পেমেন্ট গাইড যাবে</span>
          </label>
          <small style="color:#64748b; font-size:0.75rem; display:block; margin-left:26px;">অর্ডার ফর্ম সাবমিট করার সাথে সাথে বিকাশ/নগদ পেমেন্ট সম্পন্ন করার বিস্তারিত নির্দেশনা যাবে।</small>
        </div>

        <div class="form-group" style="margin-top:1.5rem;">
          <label class="form-label">অ্যাডমিনের নিজস্ব WhatsApp নম্বর (অর্ডার এলার্টের জন্য)</label>
          <input type="text" name="admin_notify_whatsapp" class="form-input" value="<?= e($curAdminWa) ?>" placeholder="যেমন: 8801684355055" style="font-weight:700; color:#f59e0b;">
          <small style="color:#64748b; font-size:0.75rem;">ওয়েবসাইটে নতুন অর্ডার বা গুগল প্রো সাবস্ক্রিপশন আসলে এই নম্বরে তাৎক্ষণিক নোটিফিকেশন যাবে।</small>
        </div>
      </div>

      <!-- Meta Cloud API Gateway -->
      <div class="admin-card">
        <div class="card-header">
          <div class="card-title">
            <span>🌐</span>
            <span>Meta WhatsApp Cloud API (ঐচ্ছিক)</span>
          </div>
        </div>
        <p style="color:#94a3b8; font-size:0.85rem; margin-top:0;">
          মেটা অফিশিয়াল ক্লাউড এপিআই যুক্ত থাকলে সার্ভার থেকে সরাসরি স্বয়ংক্রিয়ভাবে মেসেজ চলে যাবে। ফাঁকা রাখলে আউটবক্সে সংরক্ষিত থাকবে এবং আপনি ১-ক্লিকে WhatsApp Web দিয়ে পাঠাতে পারবেন।
        </p>

        <div class="form-group">
          <label class="form-label">WhatsApp Cloud API Permanent Access Token</label>
          <input type="password" name="whatsapp_token" class="form-input" value="<?= e($curToken) ?>" placeholder="EAAG...">
        </div>

        <div class="form-group">
          <label class="form-label">Phone Number ID</label>
          <input type="text" name="whatsapp_phone_id" class="form-input" value="<?= e($curPhoneId) ?>" placeholder="যেমন: 104523985723...">
        </div>
      </div>

    </div>

    <div style="margin-top:2rem; display:flex; justify-content:flex-end;">
      <button type="submit" class="btn-admin btn-admin-primary" style="padding:12px 28px; font-size:1rem; font-weight:700;">
        💾 সেটিংস সংরক্ষণ করুন (Save Settings)
      </button>
    </div>
  </form>

<?php endif; ?>

<?php
admin_footer();
