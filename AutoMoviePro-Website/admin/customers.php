<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $id = (int) ($_POST['id'] ?? 0);
    $action = (string) ($_POST['action'] ?? '');
    if ($id > 0) {
        if ($action === 'activate') {
            $pdo->prepare("UPDATE customers SET status = 'active', activated_at = COALESCE(activated_at, NOW()) WHERE id = ?")
                ->execute([$id]);
            $message = "কাস্টমার #{$id} সফলভাবে সক্রিয় (Active) করা হয়েছে।";
        } elseif ($action === 'deactivate') {
            $pdo->prepare("UPDATE customers SET status = 'inactive' WHERE id = ?")->execute([$id]);
            $pdo->prepare('UPDATE licenses SET revoked = 1 WHERE customer_id = ?')->execute([$id]);
            $message = "কাস্টমার #{$id} সাময়িক নিষ্ক্রিয় (Inactive) করা হয়েছে।";
        } elseif ($action === 'remove') {
            $pdo->prepare("UPDATE customers SET status = 'removed' WHERE id = ?")->execute([$id]);
            $pdo->prepare('UPDATE licenses SET revoked = 1 WHERE customer_id = ?')->execute([$id]);
            $message = "কাস্টমার #{$id} সফলভাবে মুছে ফেলা হয়েছে।";
        }
    }
}

$search = trim((string) ($_GET['q'] ?? ''));
$filterStatus = trim((string) ($_GET['status'] ?? 'all'));

$where = ["status != 'removed'"];
$params = [];

if ($filterStatus !== 'all' && $filterStatus !== '') {
    $where[] = "status = ?";
    $params[] = $filterStatus;
}

if ($search !== '') {
    $where[] = "(name LIKE ? OR whatsapp LIKE ? OR login_id LIKE ?)";
    $params[] = "%{$search}%";
    $params[] = "%{$search}%";
    $params[] = "%{$search}%";
}

$whereSql = 'WHERE ' . implode(' AND ', $where);

$stmt = $pdo->prepare("SELECT * FROM customers {$whereSql} ORDER BY id DESC");
$stmt->execute($params);
$rows = $stmt->fetchAll();

// Stats
$totalCustomers = 0;
$activeCount = 0;
$pendingCount = 0;
try {
    $totalCustomers = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status != 'removed'")->fetchColumn();
    $activeCount = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'active'")->fetchColumn();
    $pendingCount = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'pending'")->fetchColumn();
} catch (\Throwable $e) {}

admin_header('কাস্টমার ও লাইসেন্স ম্যানেজমেন্ট', 'customers');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<!-- Top Metrics -->
<div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-bottom: 2rem;">
  <div class="stat-card">
    <div class="stat-label">মোট কাস্টমার</div>
    <div class="stat-value" style="color:#38bdf8;"><?= $totalCustomers ?> জন</div>
    <div class="stat-trend">রেজিস্টার্ড গ্রাহক সংখ্যা</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">সক্রিয় লাইসেন্স (Active)</div>
    <div class="stat-value" style="color:#10b981;"><?= $activeCount ?> জন</div>
    <div class="stat-trend" style="color:#a7f3d0;">সফটওয়্যার সক্রিয় ব্যবহারকারী</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">অপেক্ষমাণ / নতুন (Pending)</div>
    <div class="stat-value" style="color:#f59e0b;"><?= $pendingCount ?> জন</div>
    <div class="stat-trend" style="color:#fde68a;">অনুমোদনের অপেক্ষায়</div>
  </div>
</div>

<!-- Search & Filter Bar -->
<div class="admin-card" style="margin-bottom: 1.5rem; padding: 1.25rem;">
  <form method="get" style="display:flex; flex-wrap:wrap; gap:12px; align-items:center;">
    <input type="text" name="q" value="<?= e($search) ?>" placeholder="নাম, WhatsApp বা Login ID দিয়ে খুঁজুন…" class="form-input" style="width:280px; padding:8px 14px; font-size:0.9rem;">
    
    <select name="status" class="form-input" style="width:160px; padding:8px 14px; font-size:0.9rem;">
      <option value="all" <?= $filterStatus === 'all' ? 'selected' : '' ?>>সকল স্ট্যাটাস</option>
      <option value="active" <?= $filterStatus === 'active' ? 'selected' : '' ?>>সক্রিয় (Active)</option>
      <option value="pending" <?= $filterStatus === 'pending' ? 'selected' : '' ?>>পেন্ডিং (Pending)</option>
      <option value="inactive" <?= $filterStatus === 'inactive' ? 'selected' : '' ?>>নিষ্ক্রিয় (Inactive)</option>
    </select>

    <button type="submit" class="btn-admin btn-admin-primary" style="padding:8px 16px;">
      🔍 খুঁজুন
    </button>
    <?php if ($search || $filterStatus !== 'all'): ?>
      <a href="/admin/customers.php" class="btn-admin btn-admin-ghost" style="padding:8px 14px;">
        রিসেট
      </a>
    <?php endif; ?>
  </form>
</div>

<!-- Customers Table -->
<div class="admin-card">
  <div class="card-header">
    <div class="card-title">
      <span>👥</span>
      <span>গ্রাহক তালিকা (Customer Directory)</span>
    </div>
    <span style="font-size:0.85rem; color:#94a3b8;"><?= count($rows) ?> জন প্রদর্শিত</span>
  </div>

  <div style="overflow-x:auto;">
    <table class="admin-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>কাস্টমারের নাম ও WhatsApp</th>
          <th>Login ID</th>
          <th>প্যাকেজ / প্ল্যান</th>
          <th>স্ট্যাটাস</th>
          <th>ব্যবহারকাল</th>
          <th>Heartbeat</th>
          <th style="text-align:right;">অ্যাকশন</th>
        </tr>
      </thead>
      <tbody>
        <?php if (empty($rows)): ?>
          <tr>
            <td colspan="8" style="text-align:center; padding:3rem; color:#64748b;">
              কোনো কাস্টমার পাওয়া যায়নি।
            </td>
          </tr>
        <?php else: ?>
          <?php foreach ($rows as $r): 
              $waClean = preg_replace('/\D+/', '', (string) $r['whatsapp']);
              $waLink = 'https://wa.me/' . (str_starts_with($waClean, '88') ? $waClean : ('88' . $waClean));
              ?>
            <tr>
              <td>
                <a href="/admin/customer_view.php?id=<?= (int) $r['id'] ?>" style="color:#38bdf8; font-weight:700; text-decoration:none;">
                  #<?= (int) $r['id'] ?>
                </a>
              </td>
              <td>
                <div style="font-weight:700; color:#f8fafc; font-size:0.95rem;">
                  <a href="/admin/customer_view.php?id=<?= (int) $r['id'] ?>" style="color:#f8fafc; text-decoration:none;">
                    <?= e($r['name']) ?>
                  </a>
                </div>
                <div style="font-size:0.82rem; margin-top:2px;">
                  <a href="<?= e($waLink) ?>" target="_blank" rel="noopener" style="color:#34d399; text-decoration:none; display:inline-flex; align-items:center; gap:4px;">
                    <span>📱</span> <span><?= e($r['whatsapp']) ?></span>
                  </a>
                </div>
              </td>
              <td>
                <code style="background:rgba(56,189,248,0.1); color:#38bdf8; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.85rem;">
                  <?= e($r['login_id'] ?? '—') ?>
                </code>
              </td>
              <td>
                <span class="admin-badge badge-info" style="font-size:0.75rem;">
                  <?= e($r['plan'] ?? $r['tier'] ?? 'video_studio') ?>
                </span>
              </td>
              <td>
                <?php if ($r['status'] === 'active'): ?>
                  <span class="admin-badge badge-success">সক্রিয় (Active)</span>
                <?php elseif ($r['status'] === 'pending'): ?>
                  <span class="admin-badge badge-warning">পেন্ডিং (Pending)</span>
                <?php else: ?>
                  <span class="admin-badge badge-danger"><?= e($r['status']) ?></span>
                <?php endif; ?>
              </td>
              <td style="color:#94a3b8; font-size:0.85rem;">
                <?= days_since($r['activated_at'] ?: $r['created_at']) ?> দিন
              </td>
              <td style="color:#94a3b8; font-size:0.8rem;">
                <?= e($r['last_heartbeat_at'] ?? '—') ?>
              </td>
              <td style="text-align:right;">
                <form method="post" style="display:inline-block; margin-right:4px;">
                  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                  <input type="hidden" name="id" value="<?= (int) $r['id'] ?>">
                  <?php if ($r['status'] !== 'active'): ?>
                    <button class="btn-admin" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); padding:4px 10px; font-size:0.8rem;" name="action" value="activate">
                      ✓ Active
                    </button>
                  <?php else: ?>
                    <button class="btn-admin" style="background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.3); padding:4px 10px; font-size:0.8rem;" name="action" value="deactivate">
                      Deactive
                    </button>
                  <?php endif; ?>
                  <button class="btn-admin" style="background:rgba(244,63,94,0.15); color:#f43f5e; border:1px solid rgba(244,63,94,0.3); padding:4px 8px; font-size:0.8rem;" name="action" value="remove" onclick="return confirm('এই কাস্টমারকে রিমুভ করবেন?')">
                    ✕
                  </button>
                </form>
                <a href="/admin/customer_view.php?id=<?= (int) $r['id'] ?>" class="btn-admin btn-admin-ghost" style="padding:4px 8px; font-size:0.8rem;" title="বিস্তারিত দেখুন">
                  👁️
                </a>
              </td>
            </tr>
          <?php endforeach; ?>
        <?php endif; ?>
      </tbody>
    </table>
  </div>
</div>

<?php admin_footer(); ?>
