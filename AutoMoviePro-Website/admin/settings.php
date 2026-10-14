<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';
$error = '';

$settingDefinitions = [
    // Payment Numbers
    'bkash_personal_number' => ['label' => 'বিকাশ পার্সোনাল নম্বর (bKash Personal)', 'default' => '01684355055', 'category' => 'payment', 'hint' => 'কাস্টমার সেন্ড মানি বা ক্যাশ-ইন করার জন্য দেখতে পাবে।'],
    'bkash_agent_number' => ['label' => 'বিকাশ এজেন্ট নম্বর (bKash Agent)', 'default' => '01684355055', 'category' => 'payment', 'hint' => 'ক্যাশ-আউটের জন্য নম্বর।'],
    'nagad_agent_number' => ['label' => 'নগদ এজেন্ট নম্বর (Nagad Agent)', 'default' => '01684355055', 'category' => 'payment', 'hint' => 'নগদ পেমেন্ট ক্যাশ-আউটের নম্বর।'],
    'rocket_agent_number' => ['label' => 'রকেট এজেন্ট নম্বর (Rocket Agent)', 'default' => '01684355055', 'category' => 'payment', 'hint' => 'রকেট পেমেন্ট ক্যাশ-আউটের নম্বর।'],
    'binance_pay_id' => ['label' => 'Binance Payee Name / Pay ID', 'default' => 'ChatEarly Ai', 'category' => 'payment', 'hint' => 'আন্তর্জাতিক বা ক্রিপ্টো পেমেন্টের অ্যাকাউন্ট নেম।'],

    // Pricing
    'price_amount' => ['label' => 'ফুল স্টুডিও প্যাকেজ মূল্য (৳)', 'default' => '3999', 'category' => 'pricing', 'hint' => 'Social Media Content Automation Engine মূল প্যাকেজের মূল্য।'],
    'price_tier_2999' => ['label' => 'বিজনেস ম্যানেজার প্যাকেজ মূল্য (৳)', 'default' => '2999', 'category' => 'pricing', 'hint' => 'FB Business Manager & Ad Studio প্যাকেজের মূল্য।'],
    'price_tier_1999' => ['label' => 'প্রোফাইল অটো পাইলট প্যাকেজ মূল্য (৳)', 'default' => '1999', 'category' => 'pricing', 'hint' => 'FB Profile & Page Auto Pilot প্যাকেজের মূল্য।'],
    'language_addon_price' => ['label' => 'অতিরিক্ত ভাষা অ্যাড-অন মূল্য (৳)', 'default' => '499', 'category' => 'pricing', 'hint' => 'প্রতিটি অতিরিক্ত আন্তর্জাতিক ভাষার ফি।'],

    // Support Contacts
    'whatsapp_number' => ['label' => 'সেলস ও কাস্টমার সাপোর্ট WhatsApp নম্বর', 'default' => '8801684355055', 'category' => 'support', 'hint' => 'কান্ট্রি কোড সহ (যেমন: 8801684355055)। ওয়েবসাইটে wa.me লিংকে ব্যবহৃত হয়।'],
    'support_email' => ['label' => 'অফিশিয়াল সাপোর্ট ইমেইল', 'default' => 'support@automoviepro.com', 'category' => 'support', 'hint' => 'কাস্টমার ইনভয়েস ও যোগাযোগের জন্য ইমেইল।'],
];

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    foreach ($settingDefinitions as $key => $meta) {
        if (isset($_POST[$key])) {
            $val = trim((string) $_POST[$key]);
            if ($key === 'whatsapp_number') {
                $val = preg_replace('/\D+/', '', $val) ?: '8801684355055';
            }
            set_setting($pdo, $key, $val);
        }
    }
    $message = 'পেমেন্ট নম্বর ও মূল্য সংক্রান্ত সকল সেটিংস সফলভাবে আপডেট হয়েছে!';
}

// Load current values
$currentValues = [];
foreach ($settingDefinitions as $key => $meta) {
    $currentValues[$key] = setting($pdo, $key, $meta['default']);
}

admin_header('মূল্য ও পেমেন্ট নম্বর সেটিংস', 'settings');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<!-- Top Explainer -->
<div class="admin-card" style="margin-bottom: 2rem; border-left:4px solid #10b981;">
  <h3 style="margin-top:0; font-size:1.15rem; color:#f8fafc; display:flex; align-items:center; gap:8px;">
    <span>⚙️</span> <span>নন-টেক বিজনেস কন্ট্রোল হাব</span>
  </h3>
  <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6; margin-bottom:0;">
    এখানে আপনার বিকাশ, নগদ বা রকেট নম্বর অথবা যেকোনো প্যাকেজের দাম পরিবর্তন করলে স্বয়ংক্রিয়ভাবে পুরো ওয়েবসাইটের চেকআউট পেজ, পেমেন্ট ইনস্ট্রাকশন এবং এআই চ্যাটবট নতুন তথ্য অনুযায়ী আপডেট হয়ে যাবে। কোনো টেকনিক্যাল কোডিং ছাড়াই আপনি যেকোনো সময় আপনার ব্যবসায়িক তথ্য পরিবর্তন করতে পারেন।
  </p>
</div>

<form method="post" class="admin-form">
  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">

  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1.5rem; align-items:start;">
    
    <!-- SECTION 1: Payment Numbers -->
    <div class="admin-card">
      <div class="card-header">
        <div class="card-title">
          <span>💳</span>
          <span>পেমেন্ট অ্যাকাউন্ট ও নম্বরসমূহ</span>
        </div>
      </div>

      <?php foreach ($settingDefinitions as $key => $meta): 
          if ($meta['category'] !== 'payment') continue;
          ?>
        <div class="form-group">
          <label class="form-label"><?= e($meta['label']) ?></label>
          <input type="text" name="<?= e($key) ?>" class="form-input" value="<?= e($currentValues[$key]) ?>" required style="font-weight:600; font-size:0.95rem; color:#38bdf8;">
          <small style="color:#64748b; font-size:0.75rem;"><?= e($meta['hint']) ?></small>
        </div>
      <?php endforeach; ?>
    </div>

    <!-- SECTION 2: Pricing & Packages -->
    <div class="admin-card">
      <div class="card-header">
        <div class="card-title">
          <span>💰</span>
          <span>প্যাকেজ মূল্য ও লাইসেন্স ফি (টাকা ৳)</span>
        </div>
      </div>

      <?php foreach ($settingDefinitions as $key => $meta): 
          if ($meta['category'] !== 'pricing') continue;
          ?>
        <div class="form-group">
          <label class="form-label"><?= e($meta['label']) ?></label>
          <input type="number" name="<?= e($key) ?>" class="form-input" value="<?= e($currentValues[$key]) ?>" step="1" required style="font-weight:700; font-size:1.05rem; color:#10b981;">
          <small style="color:#64748b; font-size:0.75rem;"><?= e($meta['hint']) ?></small>
        </div>
      <?php endforeach; ?>
    </div>

    <!-- SECTION 3: Customer Support Hotlines -->
    <div class="admin-card" style="grid-column: 1 / -1;">
      <div class="card-header">
        <div class="card-title">
          <span>📞</span>
          <span>কাস্টমার সাপোর্ট ও সেলস হটলাইন</span>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:1rem;">
        <?php foreach ($settingDefinitions as $key => $meta): 
            if ($meta['category'] !== 'support') continue;
            ?>
          <div class="form-group">
            <label class="form-label"><?= e($meta['label']) ?></label>
            <input type="text" name="<?= e($key) ?>" class="form-input" value="<?= e($currentValues[$key]) ?>" required style="font-size:0.95rem;">
            <small style="color:#64748b; font-size:0.75rem;"><?= e($meta['hint']) ?></small>
          </div>
        <?php endforeach; ?>
      </div>
    </div>

  </div>

  <div style="margin-top:2rem; background:rgba(2,6,23,0.7); padding:1.25rem; border-radius:12px; border:1px solid rgba(56,189,248,0.2); display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">
    <div style="color:#94a3b8; font-size:0.88rem;">
      💡 সেভ বাটনে ক্লিক করার সাথে সাথে লাইভ ওয়েবসাইটে পরিবর্তনগুলো কার্যকর হবে।
    </div>
    <button type="submit" class="btn-admin btn-admin-primary" style="padding:12px 28px; font-size:1rem; font-weight:700;">
      <span>💾</span> <span>সকল সেটিংস সেভ করুন (Save Changes)</span>
    </button>
  </div>
</form>

<?php admin_footer(); ?>
