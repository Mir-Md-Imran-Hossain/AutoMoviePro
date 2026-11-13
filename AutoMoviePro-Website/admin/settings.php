<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';
$error = '';

$settingDefinitions = [
    // Payment Numbers
    'bkash_personal_number' => ['label' => 'বিকাশ পার্সোনাল নম্বর (bKash Personal)', 'default' => '01968111593', 'category' => 'payment', 'hint' => 'কাস্টমার সেন্ড মানি বা ক্যাশ-ইন করার জন্য দেখতে পাবে।'],
    'bkash_agent_number' => ['label' => 'বিকাশ এজেন্ট নম্বর (bKash Agent)', 'default' => '01756160993', 'category' => 'payment', 'hint' => 'ক্যাশ-আউটের জন্য নম্বর (Zahid Pharmacy)।'],
    'nagad_agent_number' => ['label' => 'নগদ এজেন্ট নম্বর (Nagad Agent)', 'default' => '01611-824811', 'category' => 'payment', 'hint' => 'নগদ পেমেন্ট ক্যাশ-আউটের নম্বর (Simi Drug House)।'],
    'rocket_agent_number' => ['label' => 'রকেট এজেন্ট নম্বর (Rocket Agent)', 'default' => '01756160993-5', 'category' => 'payment', 'hint' => 'রকেট পেমেন্ট ক্যাশ-আউটের নম্বর।'],
    'binance_pay_id' => ['label' => 'Binance Payee Name / Pay ID', 'default' => 'ChatEarly Ai', 'category' => 'payment', 'hint' => 'আন্তর্জাতিক বা ক্রিপ্টো পেমেন্টের অ্যাকাউন্ট নেম।'],

    // Pricing
    'price_amount' => ['label' => 'ফুল স্টুডিও প্যাকেজ মূল্য (৳)', 'default' => '3999', 'category' => 'pricing', 'hint' => 'Social Media Content Automation Engine মূল প্যাকেজের মূল্য।'],
    'price_tier_2999' => ['label' => 'বিজনেস ম্যানেজার প্যাকেজ মূল্য (৳)', 'default' => '2999', 'category' => 'pricing', 'hint' => 'FB Business Manager & Ad Studio প্যাকেজের মূল্য।'],
    'price_tier_1999' => ['label' => 'প্রোফাইল অটো পাইলট প্যাকেজ মূল্য (৳)', 'default' => '1999', 'category' => 'pricing', 'hint' => 'FB Profile & Page Auto Pilot প্যাকেজের মূল্য।'],
    'language_addon_price' => ['label' => 'অতিরিক্ত ভাষা অ্যাড-অন মূল্য (৳)', 'default' => '499', 'category' => 'pricing', 'hint' => 'প্রতিটি অতিরিক্ত আন্তর্জাতিক ভাষার ফি।'],

    // Support Contacts
    'whatsapp_number' => ['label' => 'সেলস ও কাস্টমার সাপোর্ট WhatsApp নম্বর', 'default' => '8801968111593', 'category' => 'support', 'hint' => 'কান্ট্রি কোড সহ (যেমন: 8801968111593)। ওয়েবসাইটে wa.me লিংকে ব্যবহৃত হয়।'],
    'support_email' => ['label' => 'অফিশিয়াল সাপোর্ট ইমেইল', 'default' => 'support@automoviepro.com', 'category' => 'support', 'hint' => 'কাস্টমার ইনভয়েস ও যোগাযোগের জন্য ইমেইল।'],

    // WhatsApp Automated Gateway (Meta Cloud API / HTTP Gateway)
    'whatsapp_token' => ['label' => 'Meta WhatsApp Cloud API Access Token (Bearer)', 'default' => '', 'category' => 'whatsapp_api', 'hint' => 'মেটা ডেভেলপার ড্যাশবোর্ড থেকে সিস্টেম ইউজার পার্মানেন্ট এক্সেস টোকেন (EAAG...)। খালি থাকলে কিউআর/ম্যানুয়াল মোড চলবে।'],
    'whatsapp_phone_id' => ['label' => 'Meta WhatsApp Phone Number ID', 'default' => '', 'category' => 'whatsapp_api', 'hint' => 'মেটা ক্লাউড এপিআই এর Phone Number ID (যেমন: 104829102938471)'],
    'whatsapp_business_account_id' => ['label' => 'WhatsApp Business Account ID (WABA ID)', 'default' => '', 'category' => 'whatsapp_api', 'hint' => 'আপনার মেটা বিজনেস একাউন্ট আইডি (ঐচ্ছিক)'],
    'whatsapp_gateway_url' => ['label' => 'কাস্টম WhatsApp HTTP Gateway URL (ঐচ্ছিক)', 'default' => '', 'category' => 'whatsapp_api', 'hint' => 'UltraMsg / GreenAPI / Wasender / Baileys এপিআই এন্ডপয়েন্ট (যেমন: https://api.ultramsg.com/instance/messages/chat)'],
];

$testWaResult = null;
$csrfError = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!csrf_verify($_POST['csrf'] ?? null)) {
        $csrfError = 'সেশনের মেয়াদ শেষ হয়েছে বা ফর্মের সিকিউরিটি টোকেন মেয়াদোত্তীর্ণ। অনুগ্রহ করে পৃষ্ঠাটি রিলোড করে পুনরায় ফর্ম পূরণ করুন।';
    } else {
        $action = $_POST['action'] ?? 'save_settings';

        if ($action === 'test_whatsapp') {
        $testPhone = trim((string) ($_POST['test_wa_phone'] ?? ''));
        if ($testPhone === '') {
            $testWaResult = ['success' => false, 'msg' => 'টেস্ট করার জন্য একটি সঠিক মোবাইল নম্বর লিখুন।'];
        } else {
            $testMsg = "AutoMovie Pro: এটি সার্ভার থেকে একটি টেস্ট WhatsApp মেসেজ। আপনার WhatsApp গেটওয়ে সঠিকভাবে সংযুক্ত রয়েছে! সময়: " . date('Y-m-d H:i:s');
            $testOk = whatsapp_queue($pdo, $config, $testPhone, $testMsg, null);
            if ($testOk) {
                $testWaResult = ['success' => true, 'msg' => "সাফল্য! মেটা ক্লাউড এপিআই / গেটওয়ে থেকে সরাসরি +{$testPhone} নম্বরে টেস্ট মেসেজ সফলভাবে পৌঁছে গেছে!"];
            } else {
                $lastErr = 'সার্ভারে Meta Access Token বা Phone Number ID প্রদান করা হয়নি।';
                try {
                    $errStmt = $pdo->query("SELECT response FROM whatsapp_outbox ORDER BY id DESC LIMIT 1");
                    if ($errStmt && ($errRow = $errStmt->fetchColumn())) {
                        if (!empty($errRow)) $lastErr = (string)$errRow;
                    }
                } catch (\Throwable) {}
                $testWaResult = ['success' => false, 'msg' => "মেসেজ পাঠানো যায়নি। কারণ: {$lastErr}"];
            }
        }
    } else {
        foreach ($settingDefinitions as $key => $meta) {
            if (isset($_POST[$key])) {
                $val = trim((string) $_POST[$key]);
                if ($key === 'whatsapp_number') {
                    $val = preg_replace('/\D+/', '', $val) ?: '8801968111593';
                }
                set_setting($pdo, $key, $val);
            }
        }
        $message = 'পেমেন্ট নম্বর, মূল্য ও WhatsApp গেটওয়ে সংক্রান্ত সকল সেটিংস সফলভাবে আপডেট হয়েছে!';
    }
}
}

// Load current values
$currentValues = [];
foreach ($settingDefinitions as $key => $meta) {
    $currentValues[$key] = setting($pdo, $key, $meta['default']);
}

admin_header('মূল্য ও পেমেন্ট নম্বর সেটিংস', 'settings');
?>

<?php if (!empty($csrfError)): ?>
  <div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#fca5a5; font-size:0.95rem; font-weight:600;">
    ⚠️ <?= e($csrfError) ?>
  </div>
<?php endif; ?>

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

    <!-- SECTION 4: WhatsApp Automated Gateway (Meta Cloud API / Gateway) -->
    <div class="admin-card" style="grid-column: 1 / -1; border: 1px solid #10b981;">
      <div class="card-header" style="border-bottom: 1px solid rgba(16,185,129,0.3); padding-bottom: 0.75rem; margin-bottom: 1rem;">
        <div class="card-title">
          <span style="font-size:1.3rem;">🤖</span>
          <span style="color:#34d399; font-weight:800;">অটোমেটিক WhatsApp ক্লাউড গেটওয়ে (Meta Cloud API / Gateway)</span>
        </div>
        <span class="wam-pill secure" style="font-size:0.78rem;">
          <?= (!empty($currentValues['whatsapp_token']) && !empty($currentValues['whatsapp_phone_id'])) || !empty($currentValues['whatsapp_gateway_url']) ? '● এপিআই কানেক্টেড' : '● কিউআর / ম্যানুয়াল মোড' ?>
        </span>
      </div>

      <p style="color:#94a3b8; font-size:0.85rem; line-height:1.6; margin-top:0;">
        সার্ভার ব্যাকগ্রাউন্ড থেকে ক্রেতাদের মোবাইলে সম্পূর্ণ স্বয়ংক্রিয়ভাবে WhatsApp মেসেজ পাঠাতে মেটা ক্লাউড এপিআই টোকেন প্রদান করুন। যদি টোকেন না থাকে, তবে সিস্টেম স্বয়ংক্রিয়ভাবে <strong>১-ক্লিক কিউআর / ম্যানুয়াল মোডে</strong> কাজ করবে এবং অ্যাডমিন প্যানেল থেকে ১-ক্লিকেই মেসেজ পাঠানো যাবে।
      </p>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap:1rem;">
        <?php foreach ($settingDefinitions as $key => $meta): 
            if ($meta['category'] !== 'whatsapp_api') continue;
            ?>
          <div class="form-group">
            <label class="form-label" style="color:#cbd5e1;"><?= e($meta['label']) ?></label>
            <input type="text" name="<?= e($key) ?>" class="form-input" value="<?= e($currentValues[$key]) ?>" placeholder="<?= str_contains($key, 'token') ? 'EAAG...' : (str_contains($key, 'url') ? 'https://...' : '') ?>" style="font-size:0.88rem; font-family:monospace;">
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

<!-- TEST WHATSAPP DISPATCH CARD -->
<div class="admin-card" style="margin-top:2rem; border:1px solid #38bdf8;">
  <div class="card-header">
    <div class="card-title">
      <span>⚡</span>
      <span style="color:#38bdf8; font-weight:700;">টেস্ট WhatsApp মেসেজ ভেরিফিকেশন (Live Test Dispatch)</span>
    </div>
  </div>
  <p style="color:#94a3b8; font-size:0.85rem; margin-top:0;">
    আপনার কনফিগার করা WhatsApp গেটওয়ে থেকে সরাসরি আপনার মোবাইলে একটি টেস্ট মেসেজ পাঠিয়ে যাচাই করুন।
  </p>

  <?php if ($testWaResult): ?>
    <div style="padding:12px 16px; border-radius:8px; margin-bottom:1rem; font-size:0.9rem; <?= $testWaResult['success'] ? 'background:rgba(16,185,129,0.2); color:#6ee7b7; border:1px solid #10b981;' : 'background:rgba(239,68,68,0.2); color:#fca5a5; border:1px solid #ef4444;' ?>">
      <?= $testWaResult['success'] ? '✓' : '✗' ?> <?= e($testWaResult['msg']) ?>
    </div>
  <?php endif; ?>

  <form method="post" style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
    <input type="hidden" name="action" value="test_whatsapp">
    <div style="flex:1; min-width:240px;">
      <input type="text" name="test_wa_phone" class="form-input" placeholder="মোবাইল নম্বর (যেমন: 01717820998)" value="<?= e($currentValues['whatsapp_number'] ?: '01717820998') ?>" required style="font-size:0.95rem;">
    </div>
    <button type="submit" class="btn-admin" style="background:#0284c7; color:#fff; font-weight:700; padding:10px 22px;">
      ⚡ টেস্ট মেসেজ পাঠান
    </button>
  </form>
</div>

<?php admin_footer(); ?>
