<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$msg = '';
$err = '';

// Handle actions
if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = $_POST['action'] ?? '';
    $id = (int) ($_POST['id'] ?? 0);

    if ($action === 'add') {
        $name = trim((string) ($_POST['name'] ?? ''));
        $rating = max(1, min(5, (int) ($_POST['rating'] ?? 5)));
        $text = trim((string) ($_POST['review_text'] ?? ''));
        $platform = trim((string) ($_POST['platform'] ?? 'General'));

        if (!empty($name) && !empty($text)) {
            $stmt = $pdo->prepare("INSERT INTO reviews (name, rating, review_text, platform, is_approved, created_at) VALUES (?, ?, ?, ?, 1, NOW())");
            $stmt->execute([$name, $rating, $text, $platform]);
            $msg = 'নতুন রিভিউ সফলভাবে যুক্ত করা হয়েছে!';
        } else {
            $err = 'নাম এবং রিভিউ টেক্সট প্রদান করুন।';
        }
    } elseif ($action === 'toggle' && $id > 0) {
        $pdo->prepare("UPDATE reviews SET is_approved = IF(is_approved=1, 0, 1) WHERE id = ?")->execute([$id]);
        $msg = "রিভিউ #{$id} এর স্ট্যাটাস পরিবর্তন করা হয়েছে।";
    } elseif ($action === 'delete' && $id > 0) {
        $pdo->prepare("DELETE FROM reviews WHERE id = ?")->execute([$id]);
        $msg = "রিভিউ #{$id} মুছে ফেলা হয়েছে।";
    } elseif ($action === 'reseed') {
        require_once dirname(__DIR__) . '/includes/reviews_data.php';
        $reviews = function_exists('amp_get_default_50_reviews') ? amp_get_default_50_reviews() : [];
        $pdo->exec("DELETE FROM reviews");
        $ins = $pdo->prepare("INSERT INTO reviews (name, rating, review_text, platform, is_approved, created_at) VALUES (?, ?, ?, ?, 1, NOW())");
        foreach ($reviews as $r) {
            $ins->execute([$r['name'], (int)$r['rating'], $r['review_text'], $r['platform']]);
        }
        $msg = 'সকল ৫৫টি প্রিমিয়াম ভেরিফাইড রিভিউ সফলভাবে রিসেট ও ডাটাবেজে রিস্টোর করা হয়েছে!';
    }
}

$rows = $pdo->query("SELECT * FROM reviews ORDER BY id DESC")->fetchAll(PDO::FETCH_ASSOC);

admin_header('কাস্টমার রিভিউ ও রেটিং (55+)', 'reviews');
?>

<?php if ($msg): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.3); color:#34d399; padding:0.85rem 1.25rem; border-radius:10px; margin-bottom:1.5rem; font-weight:700;">
    ✅ <?= e($msg) ?>
  </div>
<?php endif; ?>

<?php if ($err): ?>
  <div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); color:#fca5a5; padding:0.85rem 1.25rem; border-radius:10px; margin-bottom:1.5rem; font-weight:700;">
    ⚠️ <?= e($err) ?>
  </div>
<?php endif; ?>

<!-- Quick Actions & Add Review Accordion -->
<div class="admin-card">
  <div class="admin-card-head">
    <h3>
      <span>➕</span>
      <span>নতুন কাস্টমার রিভিউ যুক্ত করুন</span>
    </h3>
    <form method="post" style="display:inline;" onsubmit="return confirm('আপনি কি নিশ্চিত যে বর্তমান রিভিউগুলো রিসেট করে ৫৫টি ভেরিফাইড রিভিউ পুনরায় সেট করবেন?')">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <button type="submit" name="action" value="reseed" class="btn-admin" style="background:rgba(245,158,11,0.2); color:#fbbf24; border:1px solid rgba(245,158,11,0.4);">
        🔄 ৫৫টি ডিফল্ট রিভিউ রিস্টোর করুন
      </button>
    </form>
  </div>

  <form method="post">
    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
    <input type="hidden" name="action" value="add">
    <div class="form-grid">
      <div class="admin-form-group">
        <label>কাস্টমারের নাম</label>
        <input type="text" name="name" placeholder="যেমন: তানভীর আহমেদ" required>
      </div>
      <div class="admin-form-group">
        <label>প্ল্যাটফর্ম বা এলাকা</label>
        <input type="text" name="platform" placeholder="যেমন: YouTube Creator (ঢাকা)" required>
      </div>
      <div class="admin-form-group">
        <label>রেটিং (১ থেকে ৫ স্টার)</label>
        <select name="rating">
          <option value="5" selected>★★★★★ (৫ স্টার)</option>
          <option value="4">★★★★☆ (৪ স্টার)</option>
          <option value="3">★★★☆☆ (৩ স্টার)</option>
        </select>
      </div>
    </div>
    <div class="admin-form-group">
      <label>কাস্টমারের মন্তব্য / রিভিউ টেক্সট</label>
      <textarea name="review_text" rows="3" placeholder="সফটওয়্যার নিয়ে কাস্টমারের মতামত লিখুন..." required></textarea>
    </div>
    <button type="submit" class="btn-admin btn-admin-success">
      ✓ রিভিউটি সাইটে পাবলিশ করুন
    </button>
  </form>
</div>

<!-- All Reviews Table -->
<div class="admin-card">
  <div class="admin-card-head">
    <h3>
      <span>🌟</span>
      <span>ডাটাবেজের সকল কাস্টমার রিভিউ (মোট: <?= count($rows) ?>টি)</span>
    </h3>
    <span class="badge-status active">লাইভ সাইটে স্লাইডারে দৃশ্যমান</span>
  </div>

  <div class="table-responsive">
    <table class="admin-table">
      <thead>
        <tr>
          <th style="width:60px;">ID</th>
          <th style="width:180px;">নাম</th>
          <th style="width:100px;">রেটিং</th>
          <th>রিভিউ টেক্সট</th>
          <th style="width:200px;">প্ল্যাটফর্ম/লোকেশন</th>
          <th style="width:100px;">স্ট্যাটাস</th>
          <th style="width:140px;">অ্যাকশন</th>
        </tr>
      </thead>
      <tbody>
        <?php foreach ($rows as $r): ?>
          <tr>
            <td><strong>#<?= (int) $r['id'] ?></strong></td>
            <td><strong style="color:#ffffff;"><?= e($r['name']) ?></strong></td>
            <td><span style="color:#fbbf24;"><?= str_repeat('★', (int) $r['rating']) ?></span></td>
            <td style="font-size:0.88rem; line-height:1.5; color:#cbd5e1;"><?= e($r['review_text']) ?></td>
            <td><span class="platform-badge"><?= e($r['platform']) ?></span></td>
            <td>
              <?php if ((int) $r['is_approved'] === 1): ?>
                <span class="badge-status active">অনুমোদিত</span>
              <?php else: ?>
                <span class="badge-status pending">লুকায়িত</span>
              <?php endif; ?>
            </td>
            <td>
              <form method="post" style="display:inline;">
                <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                <input type="hidden" name="id" value="<?= (int) $r['id'] ?>">
                <button type="submit" name="action" value="toggle" class="btn-admin" style="background:rgba(255,255,255,0.08); color:#cbd5e1; padding:4px 8px; font-size:0.75rem;">
                  <?= (int) $r['is_approved'] === 1 ? 'হাইড' : 'শো' ?>
                </button>
                <button type="submit" name="action" value="delete" class="btn-admin btn-admin-danger" style="padding:4px 8px; font-size:0.75rem;" onclick="return confirm('ডিলিট করবেন?')">
                  মুছুন
                </button>
              </form>
            </td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
  </div>
</div>

<?php admin_footer(); ?>
