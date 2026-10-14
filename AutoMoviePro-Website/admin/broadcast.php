<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $active = !empty($_POST['broadcast_active']) ? '1' : '0';
    $text = trim((string) ($_POST['broadcast_text'] ?? ''));
    $type = trim((string) ($_POST['broadcast_type'] ?? 'offer'));
    $link = trim((string) ($_POST['broadcast_link'] ?? ''));
    $linkText = trim((string) ($_POST['broadcast_link_text'] ?? ''));

    set_setting($pdo, 'broadcast_active', $active);
    set_setting($pdo, 'broadcast_text', $text);
    set_setting($pdo, 'broadcast_type', $type);
    set_setting($pdo, 'broadcast_link', $link);
    set_setting($pdo, 'broadcast_link_text', $linkText);

    $message = 'ব্রডকাস্ট নোটিশ সেটিংস সফলভাবে আপডেট করা হয়েছে!';
}

$curActive = setting($pdo, 'broadcast_active', '1') === '1';
$curText = setting($pdo, 'broadcast_text', '🔥 মেগা লঞ্চ অফার: AutoMovie Pro লাইফটাইম প্যাকেজে পাচ্ছেন বিশেষ ছাড়! সীমিত সময়ের জন্য কার্যকর।');
$curType = setting($pdo, 'broadcast_type', 'offer');
$curLink = setting($pdo, 'broadcast_link', '/order.php');
$curLinkText = setting($pdo, 'broadcast_link_text', 'এখনই অর্ডার করুন');

admin_header('লাইভ এলার্ট ও ব্রডকাস্ট নোটিশ', 'broadcast');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<!-- Top Explainer -->
<div class="admin-card" style="margin-bottom: 2rem; border-left:4px solid #38bdf8;">
  <h3 style="margin-top:0; font-size:1.15rem; color:#f8fafc; display:flex; align-items:center; gap:8px;">
    <span>📢</span> <span>লাইভ ব্রডকাস্ট ব্যানার কী?</span>
  </h3>
  <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6; margin-bottom:0;">
    এটি আপনার ওয়েবসাইটের একেবারে শীর্ষে একটি আকর্ষণীয় অ্যানিমেটেড স্ট্রিপ হিসেবে প্রদর্শিত হয়। যেকোনো বিশেষ অফার, ডিসকাউন্ট নোটিশ, ঈদ বা পূজার শুভেচ্ছা অথবা জরুরি বার্তা খুব সহজে এখান থেকে ১ ক্লিকে পরিবর্তন বা চালু/বন্ধ করতে পারবেন। কোনো কোডিং জানার প্রয়োজন নেই!
  </p>
</div>

<!-- Live Preview Section -->
<div class="admin-card" style="margin-bottom: 2rem;">
  <div class="card-header">
    <div class="card-title">
      <span>👁️</span>
      <span>ওয়েবসাইটে যেমন দেখাবে (লাইভ প্রিভিউ)</span>
    </div>
    <span class="admin-badge <?= $curActive ? 'badge-success' : 'badge-warning' ?>">
      <?= $curActive ? '● বর্তমানে ওয়েবসাইটে লাইভ চালু আছে' : '○ বর্তমানে ওয়েবসাইটে বন্ধ আছে' ?>
    </span>
  </div>

  <div style="background:#020617; padding:1.5rem; border-radius:10px; border:1px dashed rgba(255,255,255,0.15);">
    <?php
      $bgGrad = match ($curType) {
          'offer' => 'linear-gradient(90deg, #064e3b, #047857)',
          'warning' => 'linear-gradient(90deg, #78350f, #d97706)',
          'alert' => 'linear-gradient(90deg, #881337, #e11d48)',
          default => 'linear-gradient(90deg, #0c4a6e, #0284c7)',
      };
      $icon = match ($curType) {
          'offer' => '⚡',
          'warning' => '⚠️',
          'alert' => '🚨',
          default => '📢',
      };
    ?>
    <div style="background:<?= $bgGrad ?>; color:#ffffff; padding:10px 20px; border-radius:8px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; box-shadow:0 4px 15px rgba(0,0,0,0.3);">
      <div style="display:flex; align-items:center; gap:10px; font-size:0.95rem; font-weight:600;">
        <span style="font-size:1.2rem;"><?= $icon ?></span>
        <span><?= e($curText) ?></span>
      </div>
      <?php if ($curLink && $curLinkText): ?>
        <a href="<?= e($curLink) ?>" target="_blank" style="background:#ffffff; color:#0f172a; padding:5px 14px; border-radius:6px; font-weight:700; font-size:0.85rem; text-decoration:none; white-space:nowrap;">
          <?= e($curLinkText) ?> →
        </a>
      <?php endif; ?>
    </div>
  </div>
</div>

<!-- Edit Form -->
<div class="admin-card" style="max-width:700px;">
  <div class="card-header">
    <div class="card-title">
      <span>✏️</span>
      <span>ব্রডকাস্ট নোটিশ পরিবর্তন করুন</span>
    </div>
  </div>

  <form method="post" class="admin-form">
    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">

    <div class="form-group" style="display:flex; align-items:center; gap:10px; background:rgba(255,255,255,0.03); padding:12px 16px; border-radius:8px; border:1px solid rgba(255,255,255,0.08);">
      <input type="checkbox" name="broadcast_active" id="broadcast_active" value="1" <?= $curActive ? 'checked' : '' ?> style="width:20px; height:20px; accent-color:#10b981; cursor:pointer;">
      <label for="broadcast_active" style="margin:0; font-size:1rem; font-weight:700; color:#f8fafc; cursor:pointer;">
        ওয়েবসাইটে নোটিশটি প্রদর্শন করুন (Enable Live Broadcast)
      </label>
    </div>

    <div class="form-group">
      <label class="form-label">নোটিশের বিষয় / ক্যাটাগরি কালার</label>
      <select name="broadcast_type" class="form-input" style="font-size:0.95rem;">
        <option value="offer" <?= $curType === 'offer' ? 'selected' : '' ?>>⚡ অফার বা ডিসকাউন্ট (সবুজ এমারেল্ড থিম)</option>
        <option value="info" <?= $curType === 'info' ? 'selected' : '' ?>>📢 সাধারণ ঘোষণা ও আপডেট (নীল সায়ান থিম)</option>
        <option value="warning" <?= $curType === 'warning' ? 'selected' : '' ?>>⚠️ গুরুত্বপূর্ণ নোটিশ বা সতর্কতা (হলুদ অ্যাম্বার থিম)</option>
        <option value="alert" <?= $curType === 'alert' ? 'selected' : '' ?>>🚨 জরুরি সতর্কতা বা অফার শেষ নোটিশ (লাল রোজ থিম)</option>
      </select>
    </div>

    <div class="form-group">
      <label class="form-label">নোটিশের মূল বার্তা (Text)</label>
      <textarea name="broadcast_text" rows="3" class="form-input" placeholder="যেমন: ঈদ স্পেশাল অফার: আজই কিনলে ফ্রি ১৫ দিনের সাপোর্ট ও ইনস্টলেশন গাইড!" required style="font-size:0.95rem; line-height:1.5;"><?= e($curText) ?></textarea>
      <small style="color:#64748b; font-size:0.75rem;">বাংলা বা ইংরেজি যেকোনো ভাষায় লিখতে পারেন।</small>
    </div>

    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
      <div class="form-group">
        <label class="form-label">বাটনের লিংক (URL)</label>
        <input type="text" name="broadcast_link" class="form-input" value="<?= e($curLink) ?>" placeholder="যেমন: /order.php অথবা wa.me লিংক">
      </div>
      <div class="form-group">
        <label class="form-label">বাটনের টেক্সট (Button Text)</label>
        <input type="text" name="broadcast_link_text" class="form-input" value="<?= e($curLinkText) ?>" placeholder="যেমন: এখনই অর্ডার করুন">
      </div>
    </div>

    <div style="margin-top:1.5rem;">
      <button type="submit" class="btn-admin btn-admin-primary" style="padding:10px 20px; font-size:0.95rem;">
        <span>✓</span> <span>সেটিংস সেভ করুন ও ওয়েবসাইটে পাবলিশ করুন</span>
      </button>
    </div>
  </form>
</div>

<?php admin_footer(); ?>
