<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';
$error = '';

// Handle Actions
if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = (string) ($_POST['action'] ?? '');
    
    if ($action === 'create') {
        $code = strtoupper(trim((string) ($_POST['code'] ?? '')));
        $discountAmount = (float) ($_POST['discount_amount'] ?? 0);
        $discountPercent = (int) ($_POST['discount_percent'] ?? 0);
        $minOrderAmount = (float) ($_POST['min_order_amount'] ?? 0);
        $isActive = !empty($_POST['is_active']) ? 1 : 0;

        if ($code === '') {
            $error = 'অনুগ্রহ করে কুপন কোড লিখুন (যেমন: SPECIAL500 বা EID20)';
        } else {
            try {
                $stmt = $pdo->prepare(
                    "INSERT INTO coupons (code, discount_amount, discount_percent, min_order_amount, is_active)
                     VALUES (?, ?, ?, ?, ?)"
                );
                $stmt->execute([$code, $discountAmount, $discountPercent, $minOrderAmount, $isActive]);
                $message = "নতুন কুপন '{$code}' সফলভাবে তৈরি করা হয়েছে!";
            } catch (\PDOException $e) {
                if (str_contains($e->getMessage(), 'Duplicate') || $e->getCode() === '23000') {
                    $error = "এই কোডের কুপন ('{$code}') ইতিমধ্যে বিদ্যমান রয়েছে। অন্য কোড দিন।";
                } else {
                    $error = 'কুপন তৈরি করতে সমস্যা হয়েছে: ' . $e->getMessage();
                }
            }
        }
    } elseif ($action === 'toggle') {
        $id = (int) ($_POST['id'] ?? 0);
        $curStatus = (int) ($_POST['current_status'] ?? 0);
        $newStatus = $curStatus ? 0 : 1;
        $pdo->prepare("UPDATE coupons SET is_active = ? WHERE id = ?")->execute([$newStatus, $id]);
        $message = "কুপনের স্ট্যাটাস সফলভাবে পরিবর্তন করা হয়েছে।";
    } elseif ($action === 'delete') {
        $id = (int) ($_POST['id'] ?? 0);
        $pdo->prepare("DELETE FROM coupons WHERE id = ?")->execute([$id]);
        $message = "কুপনটি সফলভাবে মুছে ফেলা হয়েছে।";
    }
}

// Fetch all coupons
$coupons = [];
try {
    $coupons = $pdo->query("SELECT * FROM coupons ORDER BY id DESC")->fetchAll();
} catch (\Throwable $e) {}

$totalCoupons = count($coupons);
$activeCoupons = count(array_filter($coupons, fn($c) => !empty($c['is_active'])));

admin_header('ডিসকাউন্ট কুপন ম্যানেজমেন্ট', 'coupons');
?>

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

<!-- Top Metrics -->
<div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 2rem;">
  <div class="stat-card">
    <div class="stat-label">মোট কুপন সংখ্যা</div>
    <div class="stat-value" style="color:#38bdf8;"><?= $totalCoupons ?> টি</div>
    <div class="stat-trend">সিস্টেমে রেজিস্টার্ড প্রোমোশন</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">সক্রিয় কুপন</div>
    <div class="stat-value" style="color:#10b981;"><?= $activeCoupons ?> টি</div>
    <div class="stat-trend" style="color:#a7f3d0;">কাস্টমাররা এখনই ব্যবহার করতে পারবেন</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">নিষ্ক্রিয় / অফ কুপন</div>
    <div class="stat-value" style="color:#f59e0b;"><?= ($totalCoupons - $activeCoupons) ?> টি</div>
    <div class="stat-trend" style="color:#fde68a;">বর্তমানে অফলাইনে রাখা আছে</div>
  </div>
</div>

<div style="display:grid; grid-template-columns: 1fr 340px; gap: 1.5rem; align-items: start;">
  
  <!-- Coupons List Table -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>🎟️</span>
        <span>বর্তমান কুপন তালিকা</span>
      </div>
      <span style="font-size:0.8rem; color:#94a3b8;">সর্বমোট <?= $totalCoupons ?> টি কুপন</span>
    </div>

    <div style="overflow-x:auto;">
      <table class="admin-table">
        <thead>
          <tr>
            <th>কুপন কোড</th>
            <th>ডিসকাউন্ট</th>
            <th>নূন্যতম অর্ডার</th>
            <th>স্ট্যাটাস</th>
            <th>তৈরির তারিখ</th>
            <th style="text-align:right;">অ্যাকশন</th>
          </tr>
        </thead>
        <tbody>
          <?php if (empty($coupons)): ?>
            <tr>
              <td colspan="6" style="text-align:center; padding:2.5rem; color:#64748b;">
                কোনো কুপন তৈরি করা হয়নি। ডানপাশের ফর্ম থেকে নতুন কুপন যোগ করুন।
              </td>
            </tr>
          <?php else: ?>
            <?php foreach ($coupons as $c): ?>
              <tr>
                <td>
                  <strong style="font-size:1.05rem; letter-spacing:1px; color:#38bdf8; background:rgba(56,189,248,0.1); padding:4px 8px; border-radius:6px; border:1px dashed rgba(56,189,248,0.3);">
                    <?= e($c['code']) ?>
                  </strong>
                </td>
                <td>
                  <?php if ((float)$c['discount_amount'] > 0): ?>
                    <span style="color:#10b981; font-weight:700;">৳<?= number_format((float)$c['discount_amount']) ?> ফ্ল্যাট ছাড়</span>
                  <?php elseif ((int)$c['discount_percent'] > 0): ?>
                    <span style="color:#a855f7; font-weight:700;"><?= (int)$c['discount_percent'] ?>% শতকরা ছাড়</span>
                  <?php else: ?>
                    <span style="color:#94a3b8;">—</span>
                  <?php endif; ?>
                </td>
                <td>
                  <?php if ((float)$c['min_order_amount'] > 0): ?>
                    ৳<?= number_format((float)$c['min_order_amount']) ?>
                  <?php else: ?>
                    <span style="color:#64748b;">যেকোনো অর্ডার</span>
                  <?php endif; ?>
                </td>
                <td>
                  <?php if (!empty($c['is_active'])): ?>
                    <span class="admin-badge badge-success">সক্রিয় (Active)</span>
                  <?php else: ?>
                    <span class="admin-badge badge-warning">বন্ধ (Inactive)</span>
                  <?php endif; ?>
                </td>
                <td style="color:#94a3b8; font-size:0.85rem;">
                  <?= date('d M, Y', strtotime($c['created_at'])) ?>
                </td>
                <td style="text-align:right;">
                  <form method="post" style="display:inline-block; margin-right:4px;">
                    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                    <input type="hidden" name="action" value="toggle">
                    <input type="hidden" name="id" value="<?= (int) $c['id'] ?>">
                    <input type="hidden" name="current_status" value="<?= (int) $c['is_active'] ?>">
                    <?php if (!empty($c['is_active'])): ?>
                      <button type="submit" class="btn-admin" style="background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.3); padding:4px 8px; font-size:0.8rem;" title="সাময়িক বন্ধ করুন">
                        অফ করুন
                      </button>
                    <?php else: ?>
                      <button type="submit" class="btn-admin" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); padding:4px 8px; font-size:0.8rem;" title="সক্রিয় করুন">
                        চালু করুন
                      </button>
                    <?php endif; ?>
                  </form>
                  <form method="post" style="display:inline-block;" onsubmit="return confirm('আপনি কি নিশ্চিত যে কুপন \'<?= e($c['code']) ?>\' স্থায়ীভাবে মুছে ফেলতে চান?');">
                    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="id" value="<?= (int) $c['id'] ?>">
                    <button type="submit" class="btn-admin" style="background:rgba(244,63,94,0.15); color:#f43f5e; border:1px solid rgba(244,63,94,0.3); padding:4px 8px; font-size:0.8rem;">
                      মুছুন
                    </button>
                  </form>
                </td>
              </tr>
            <?php endforeach; ?>
          <?php endif; ?>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Create New Coupon Form -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>➕</span>
        <span>নতুন কুপন তৈরি</span>
      </div>
    </div>
    
    <form method="post" class="admin-form">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="create">

      <div class="form-group">
        <label class="form-label">কুপন কোড (ইংরেজি বড় অক্ষরে)</label>
        <input type="text" name="code" class="form-input" placeholder="যেমন: SPECIAL500" required style="text-transform:uppercase; letter-spacing:1px; font-weight:700;">
        <small style="color:#64748b; font-size:0.75rem;">কাস্টমার এই কোডটি চেকআউটে লিখবে।</small>
      </div>

      <div class="form-group">
        <label class="form-label">নির্দিষ্ট ছাড়ের পরিমাণ (টাকা ৳)</label>
        <input type="number" name="discount_amount" class="form-input" placeholder="যেমন: 500" step="1" min="0" value="500">
        <small style="color:#64748b; font-size:0.75rem;">ফ্ল্যাট কত টাকা ডিসকাউন্ট পাবে।</small>
      </div>

      <div class="form-group">
        <label class="form-label">অথবা শতকরা ছাড় (%)</label>
        <input type="number" name="discount_percent" class="form-input" placeholder="যেমন: 15" min="0" max="100" value="0">
        <small style="color:#64748b; font-size:0.75rem;">টাকার পরিবর্তে % দিতে চাইলে এখানে লিখুন।</small>
      </div>

      <div class="form-group">
        <label class="form-label">নূন্যতম অর্ডার পরিমাণ (৳)</label>
        <input type="number" name="min_order_amount" class="form-input" placeholder="0 = যেকোনো অর্ডার" min="0" value="0">
        <small style="color:#64748b; font-size:0.75rem;">কমপক্ষে কত টাকার অর্ডারে কুপন কার্যকর হবে।</small>
      </div>

      <div class="form-group" style="display:flex; align-items:center; gap:8px; margin-top:0.5rem;">
        <input type="checkbox" name="is_active" id="is_active" value="1" checked style="width:18px; height:18px; accent-color:#38bdf8;">
        <label for="is_active" style="margin:0; font-size:0.9rem; color:#f8fafc; cursor:pointer;">এখনই কুপনটি সক্রিয় রাখুন</label>
      </div>

      <div style="margin-top:1.5rem;">
        <button type="submit" class="btn-admin btn-admin-primary" style="width:100%; justify-content:center; padding:10px 14px;">
          <span>✓</span> <span>কুপন পাবলিশ করুন</span>
        </button>
      </div>
    </form>
  </div>

</div>

<?php admin_footer(); ?>
