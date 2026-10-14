<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_once dirname(__DIR__) . '/includes/agent_llm.php';
require_admin();

$message = '';
$error = '';

// Setting Definitions
$agentSettings = [
    'agent_primary_persona' => ['default' => 'ayesha'],
    'agent_chat_active' => ['default' => '1'],
    'agent_custom_instructions' => ['default' => ''],
    'agent_followup_reminder_hours' => ['default' => '24'],
    'agent_discount_allowed' => ['default' => '1'],
    'agent_discount_mode' => ['default' => 'consultative'],
    'agent_discount_type' => ['default' => 'flat'],
    'agent_initial_discount_amount' => ['default' => '500'],
    'agent_max_discount_amount' => ['default' => '1000'],
    'agent_pkg_video_studio_init' => ['default' => '500'],
    'agent_pkg_video_studio_max' => ['default' => '1000'],
    'agent_pkg_fb_business_init' => ['default' => '300'],
    'agent_pkg_fb_business_max' => ['default' => '600'],
    'agent_pkg_profile_page_init' => ['default' => '200'],
    'agent_pkg_profile_page_max' => ['default' => '400'],
    'agent_free_addon_lang' => ['default' => '1'],
    'agent_coupon_prefix' => ['default' => 'VIP500'],
    'agent_ask_whatsapp_for_demo' => ['default' => '1'],
    'agent_auto_queue_whatsapp_welcome' => ['default' => '1'],
];

// Handle Form Submission
if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    foreach ($agentSettings as $key => $meta) {
        if (isset($_POST[$key])) {
            $val = trim((string) $_POST[$key]);
            set_setting($pdo, $key, $val);
        } else {
            // For unchecked checkboxes
            if (in_array($key, ['agent_chat_active', 'agent_discount_allowed', 'agent_free_addon_lang', 'agent_ask_whatsapp_for_demo', 'agent_auto_queue_whatsapp_welcome'], true)) {
                set_setting($pdo, $key, '0');
            }
        }
    }

    // Ensure coupon exists in coupons table if prefix provided
    $cpCode = strtoupper(trim((string) ($_POST['agent_coupon_prefix'] ?? 'VIP500')));
    $initAmt = (float) ($_POST['agent_initial_discount_amount'] ?? 500);
    if ($cpCode !== '') {
        try {
            $cpCheck = $pdo->prepare("SELECT id FROM coupons WHERE code = ? LIMIT 1");
            $cpCheck->execute([$cpCode]);
            if ($cpRow = $cpCheck->fetch()) {
                $pdo->prepare("UPDATE coupons SET discount_amount = ? WHERE id = ?")->execute([$initAmt, (int)$cpRow['id']]);
            } else {
                $pdo->prepare("INSERT INTO coupons (code, discount_amount, discount_percent, min_order_amount, is_active) VALUES (?, ?, 0, 0, 1)")
                    ->execute([$cpCode, $initAmt]);
            }
        } catch (\Throwable $e) {}
    }

    $message = 'এআই চ্যাট এজেন্ট ও ডিসকাউন্ট পলিসি সেটিংস সফলভাবে সংরক্ষিত ও লাইভ আপডেট হয়েছে!';
}

// Load current values
$cur = [];
foreach ($agentSettings as $k => $m) {
    $cur[$k] = setting($pdo, $k, $m['default']);
}

$activePersona = $cur['agent_primary_persona'];
$discountActive = ($cur['agent_discount_allowed'] === '1');
$maxCeiling = (int) $cur['agent_max_discount_amount'];
$couponName = $cur['agent_coupon_prefix'];

admin_header('এআই চ্যাট এজেন্ট ও ডিসকাউন্ট কন্ট্রোল', 'agent_settings');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<!-- Top Metrics -->
<div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 2rem;">
  <div class="stat-card">
    <div class="stat-label">বর্তমান প্রধান চ্যাট এজেন্ট</div>
    <div class="stat-value" style="color:#38bdf8; font-size:1.35rem;">
      <?= $activePersona === 'nirob' ? '👨‍💼 নীরব (Nirob)' : ($activePersona === 'tania' ? '👩‍💼 তানিয়া (Tania)' : '🧕 আয়েশা (Ayesha)') ?>
    </div>
    <div class="stat-trend" style="color:#a7f3d0;">ওয়েবসাইটে সার্বক্ষণিক অ্যাক্টিভ</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">ডিসকাউন্ট পলিসি স্ট্যাটাস</div>
    <div class="stat-value" style="color:<?= $discountActive ? '#10b981' : '#f43f5e' ?>;">
      <?= $discountActive ? 'অনুমোদিত (Active)' : 'নিষ্ক্রিয় (Disabled)' ?>
    </div>
    <div class="stat-trend"><?= $discountActive ? 'এজেন্ট কুপন অফার করতে পারবে' : 'কোনো ছাড় অফার করা যাবে না' ?></div>
  </div>
  <div class="stat-card">
    <div class="stat-label">সর্বোচ্চ ছাড়ের সীমা (Ceiling)</div>
    <div class="stat-value" style="color:#f59e0b;">৳<?= number_format($maxCeiling) ?></div>
    <div class="stat-trend">এজেন্ট এর বেশি ছাড় দিতে পারবে না</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">অফারের কুপন ও মেয়াদ</div>
    <div class="stat-value" style="color:#a855f7; font-size:1.35rem;"><?= e($couponName) ?></div>
    <div class="stat-trend">মেয়াদ: <?= (int)$cur['agent_followup_reminder_hours'] ?> ঘণ্টা সময়সীমা</div>
  </div>
</div>

<form method="post" class="admin-form">
  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">

  <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1.5rem; align-items:start;">

    <!-- 1. PERSONA & GENERAL CONTROLS -->
    <div class="admin-card">
      <div class="card-header">
        <div class="card-title">
          <span>🤖</span>
          <span>প্রধান এজেন্ট সিলেকশন ও আচরণ</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">সক্রিয় প্রধান সেলস কনসালট্যান্ট নির্বাচন করুন</label>
        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-top:6px;">
          <label style="border:2px solid <?= $activePersona === 'ayesha' ? '#38bdf8' : 'rgba(255,255,255,0.1)' ?>; background:rgba(0,0,0,0.3); border-radius:10px; padding:12px; text-align:center; cursor:pointer; transition:all 0.2s;">
            <input type="radio" name="agent_primary_persona" value="ayesha" <?= $activePersona === 'ayesha' ? 'checked' : '' ?> style="display:none;" onchange="this.form.submit()">
            <img src="/assets/img/agents/ayesha.png" style="width:48px; height:48px; border-radius:50%; margin:0 auto 8px; display:block; object-fit:cover; border:2px solid #38bdf8;">
            <strong style="color:#f8fafc; font-size:0.9rem; display:block;">আয়েশা</strong>
            <small style="color:#94a3b8; font-size:0.75rem;">সিনিয়র কনসালট্যান্ট</small>
          </label>
          <label style="border:2px solid <?= $activePersona === 'tania' ? '#38bdf8' : 'rgba(255,255,255,0.1)' ?>; background:rgba(0,0,0,0.3); border-radius:10px; padding:12px; text-align:center; cursor:pointer; transition:all 0.2s;">
            <input type="radio" name="agent_primary_persona" value="tania" <?= $activePersona === 'tania' ? 'checked' : '' ?> style="display:none;" onchange="this.form.submit()">
            <img src="/assets/img/agents/tania.png" style="width:48px; height:48px; border-radius:50%; margin:0 auto 8px; display:block; object-fit:cover; border:2px solid #ec4899;">
            <strong style="color:#f8fafc; font-size:0.9rem; display:block;">তানিয়া</strong>
            <small style="color:#94a3b8; font-size:0.75rem;">অনবোর্ডিং স্পেশালিস্ট</small>
          </label>
          <label style="border:2px solid <?= $activePersona === 'nirob' ? '#38bdf8' : 'rgba(255,255,255,0.1)' ?>; background:rgba(0,0,0,0.3); border-radius:10px; padding:12px; text-align:center; cursor:pointer; transition:all 0.2s;">
            <input type="radio" name="agent_primary_persona" value="nirob" <?= $activePersona === 'nirob' ? 'checked' : '' ?> style="display:none;" onchange="this.form.submit()">
            <img src="/assets/img/agents/nirob.png" style="width:48px; height:48px; border-radius:50%; margin:0 auto 8px; display:block; object-fit:cover; border:2px solid #10b981;">
            <strong style="color:#f8fafc; font-size:0.9rem; display:block;">নীরব</strong>
            <small style="color:#94a3b8; font-size:0.75rem;">টেকনিক্যাল লিড</small>
          </label>
        </div>
      </div>

      <div class="form-group" style="margin-top:1.5rem;">
        <label class="form-label" style="display:flex; align-items:center; gap:8px;">
          <input type="checkbox" name="agent_chat_active" value="1" <?= $cur['agent_chat_active'] === '1' ? 'checked' : '' ?> style="width:18px; height:18px; accent-color:#38bdf8;">
          <span>ওয়েবসাইটে লাইভ চ্যাট উইজেট চালু রাখুন (Global Chat Active)</span>
        </label>
      </div>

      <div class="form-group">
        <label class="form-label">অ্যাডমিনের বিশেষ কাস্টম নির্দেশনা (Custom System Directive)</label>
        <textarea name="agent_custom_instructions" class="form-textarea" rows="3" placeholder="যেমন: 'আজকে বিশেষ ছাড়ের কথা জোর দিন', বা 'সবাইকে ৩,৯৯৯ টাকার ফুল ভিডিও প্যাকেজ সাজেস্ট করুন'..."><?= e($cur['agent_custom_instructions']) ?></textarea>
        <small style="color:#64748b; font-size:0.75rem;">এখানে কিছু লিখলে এআই এজেন্ট প্রতি উত্তরের সময় আপনার এই বিশেষ নির্দেশনা মেনে কথা বলবে।</small>
      </div>

      <div class="form-group">
        <label class="form-label">অফার ভ্যালিডিটি উইন্ডো (ঘণ্টা)</label>
        <input type="number" name="agent_followup_reminder_hours" class="form-input" value="<?= (int) $cur['agent_followup_reminder_hours'] ?>" min="1" max="168" style="color:#f59e0b; font-weight:700;">
        <small style="color:#64748b; font-size:0.75rem;">কাস্টমারকে বলবে এই অফারটি পরবর্তী এত ঘণ্টার মধ্যে অর্ডার করলে কার্যকর থাকবে।</small>
      </div>
    </div>

    <!-- 2. DISCOUNT RULES & NEGOTIATION LIMITS -->
    <div class="admin-card">
      <div class="card-header">
        <div class="card-title">
          <span>🏷️</span>
          <span>ডিসকাউন্ট ও নেগোসিয়েশন পলিসি</span>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" style="display:flex; align-items:center; gap:8px;">
          <input type="checkbox" name="agent_discount_allowed" value="1" <?= $discountActive ? 'checked' : '' ?> style="width:18px; height:18px; accent-color:#10b981;">
          <span style="font-weight:700; color:#34d399;">এআই এজেন্ট কাস্টমারকে ছাড়/কুপন অফার করতে পারবে (Allow Discounts)</span>
        </label>
        <small style="color:#64748b; font-size:0.75rem; display:block; margin-left:26px;">এটি বন্ধ করলে এআই কখনো কোনো ছাড় দেবে না এবং জানাবে যে এটি ওয়ান-টাইম ফিক্সড লাইফটাইম প্রাইস।</small>
      </div>

      <div class="form-group">
        <label class="form-label">নেগোসিয়েশন কৌশল (Sales Strategy Mode)</label>
        <select name="agent_discount_mode" class="form-select">
          <option value="consultative" <?= $cur['agent_discount_mode'] === 'consultative' ? 'selected' : '' ?>>
            🤝 কনসালটেটিভ (ডিফল্ট) — "পরে নেব" বা "বাজেট কম" বললে প্রারম্ভিক ছাড় দেবে
          </option>
          <option value="conservative" <?= $cur['agent_discount_mode'] === 'conservative' ? 'selected' : '' ?>>
            🛡️ কনজারভেটিভ (মার্জিন সুরক্ষিত রাখুন) — সহজে ছাড় দেবে না, ২য় বার অনুরোধ করলে তবেই ছাড় দেবে
          </option>
          <option value="aggressive" <?= $cur['agent_discount_mode'] === 'aggressive' ? 'selected' : '' ?>>
            ⚡ অ্যাগ্রেসিভ ক্লোজিং — শুরুতেই ছাড় অফার করে দ্রুত অর্ডার ক্লোজ করার চেষ্টা করবে
          </option>
        </select>
      </div>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
        <div class="form-group">
          <label class="form-label">প্রারম্ভিক ছাড় (Initial Offer)</label>
          <div style="position:relative;">
            <span style="position:absolute; left:12px; top:10px; color:#94a3b8;">৳</span>
            <input type="number" name="agent_initial_discount_amount" class="form-input" value="<?= (int) $cur['agent_initial_discount_amount'] ?>" style="padding-left:28px; font-weight:700; color:#10b981;">
          </div>
          <small style="color:#64748b; font-size:0.75rem;">প্রথমবার কত টাকা ছাড় দিয়ে শুরু করবে।</small>
        </div>

        <div class="form-group">
          <label class="form-label">সর্বোচ্চ ছাড়ের সীমা (Max Ceiling)</label>
          <div style="position:relative;">
            <span style="position:absolute; left:12px; top:10px; color:#94a3b8;">৳</span>
            <input type="number" name="agent_max_discount_amount" class="form-input" value="<?= (int) $cur['agent_max_discount_amount'] ?>" style="padding-left:28px; font-weight:700; color:#f43f5e;">
          </div>
          <small style="color:#64748b; font-size:0.75rem;">এজেন্ট কোনো অবস্থাতেই এর চেয়ে বেশি ছাড় দিতে পারবে না।</small>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">ডিফল্ট প্রোমো কুপন কোড (Secret Coupon Code)</label>
        <input type="text" name="agent_coupon_prefix" class="form-input" value="<?= e($cur['agent_coupon_prefix']) ?>" required style="text-transform:uppercase; font-weight:700; color:#38bdf8; letter-spacing:1px;">
        <small style="color:#64748b; font-size:0.75rem;">এই কোডটি স্বয়ংক্রিয়ভাবে ডাটাবেজের কুপন টেবিলে সিঙ্ক হবে এবং ১-ক্লিক অর্ডারে কাজ করবে।</small>
      </div>

      <div class="form-group">
        <label class="form-label" style="display:flex; align-items:center; gap:8px;">
          <input type="checkbox" name="agent_free_addon_lang" value="1" <?= $cur['agent_free_addon_lang'] === '1' ? 'checked' : '' ?> style="width:18px; height:18px; accent-color:#38bdf8;">
          <span>১টি অতিরিক্ত বিদেশি ভাষা (মূল্য ৳৪৯৯) উপহার হিসেবে ফ্রি অফার করবে</span>
        </label>
      </div>
    </div>

    <!-- 3. PACKAGE-SPECIFIC CEILINGS -->
    <div class="admin-card" style="grid-column: 1 / -1;">
      <div class="card-header">
        <div class="card-title">
          <span>📦</span>
          <span>প্যাকেজভিত্তিক আলাদা আলাদা সর্বোচ্চ ছাড় নিয়ন্ত্রণ (Package Concession Matrix)</span>
        </div>
      </div>
      <p style="color:#94a3b8; font-size:0.88rem; margin-top:0;">
        প্রতিটি সফটওয়্যারের প্যাকেজের লাভ ও ফিচারের উপর ভিত্তি করে আলাদা আলাদা ছাড় নির্ধারণ করতে পারবেন:
      </p>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap:1rem;">
        
        <!-- Package 1 -->
        <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(56,189,248,0.25); border-radius:12px; padding:1.25rem;">
          <div style="font-weight:700; color:#38bdf8; font-size:1rem; margin-bottom:4px;">
            Omni Video Content Studio
          </div>
          <div style="color:#94a3b8; font-size:0.8rem; margin-bottom:12px;">মূল প্যাকেজ রেগুলার মূল্য: <strong>৳৩,৯৯৯</strong></div>
          <div class="form-group" style="margin-bottom:8px;">
            <label class="form-label" style="font-size:0.8rem;">প্রারম্ভিক ছাড় (৳)</label>
            <input type="number" name="agent_pkg_video_studio_init" class="form-input" value="<?= (int) $cur['agent_pkg_video_studio_init'] ?>">
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label" style="font-size:0.8rem; color:#f87171;">সর্বোচ্চ অনুমোদিত ছাড় (৳)</label>
            <input type="number" name="agent_pkg_video_studio_max" class="form-input" value="<?= (int) $cur['agent_pkg_video_studio_max'] ?>" style="color:#f87171; font-weight:700;">
          </div>
        </div>

        <!-- Package 2 -->
        <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(236,72,153,0.25); border-radius:12px; padding:1.25rem;">
          <div style="font-weight:700; color:#ec4899; font-size:1rem; margin-bottom:4px;">
            FB Business Manager & Ads
          </div>
          <div style="color:#94a3b8; font-size:0.8rem; margin-bottom:12px;">বিজনেস প্যাকেজ রেগুলার মূল্য: <strong>৳২,৯৯৯</strong></div>
          <div class="form-group" style="margin-bottom:8px;">
            <label class="form-label" style="font-size:0.8rem;">প্রারম্ভিক ছাড় (৳)</label>
            <input type="number" name="agent_pkg_fb_business_init" class="form-input" value="<?= (int) $cur['agent_pkg_fb_business_init'] ?>">
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label" style="font-size:0.8rem; color:#f87171;">সর্বোচ্চ অনুমোদিত ছাড় (৳)</label>
            <input type="number" name="agent_pkg_fb_business_max" class="form-input" value="<?= (int) $cur['agent_pkg_fb_business_max'] ?>" style="color:#f87171; font-weight:700;">
          </div>
        </div>

        <!-- Package 3 -->
        <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(16,185,129,0.25); border-radius:12px; padding:1.25rem;">
          <div style="font-weight:700; color:#10b981; font-size:1rem; margin-bottom:4px;">
            FB Profile Auto Pilot
          </div>
          <div style="color:#94a3b8; font-size:0.8rem; margin-bottom:12px;">প্রোফাইল প্যাকেজ রেগুলার মূল্য: <strong>৳১,৯৯৯</strong></div>
          <div class="form-group" style="margin-bottom:8px;">
            <label class="form-label" style="font-size:0.8rem;">প্রারম্ভিক ছাড় (৳)</label>
            <input type="number" name="agent_pkg_profile_page_init" class="form-input" value="<?= (int) $cur['agent_pkg_profile_page_init'] ?>">
          </div>
          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label" style="font-size:0.8rem; color:#f87171;">সর্বোচ্চ অনুমোদিত ছাড় (৳)</label>
            <input type="number" name="agent_pkg_profile_page_max" class="form-input" value="<?= (int) $cur['agent_pkg_profile_page_max'] ?>" style="color:#f87171; font-weight:700;">
          </div>
        </div>

      </div>
    </div>

    <!-- 4. WHATSAPP LEAD COLLECTION BEHAVIOR -->
    <div class="admin-card" style="grid-column: 1 / -1;">
      <div class="card-header">
        <div class="card-title">
          <span>💬</span>
          <span>চ্যাট চলাকালীন WhatsApp লিড ক্যাপচার আচরণ</span>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap:1.25rem;">
        <div class="form-group" style="margin-bottom:0;">
          <label class="form-label" style="display:flex; align-items:center; gap:8px;">
            <input type="checkbox" name="agent_ask_whatsapp_for_demo" value="1" <?= $cur['agent_ask_whatsapp_for_demo'] === '1' ? 'checked' : '' ?> style="width:18px; height:18px; accent-color:#38bdf8;">
            <span>ভিডিও ডেমো বা ভাউচার পাঠানোর জন্য বিনীতভাবে WhatsApp নম্বর চেয়ে নেবে</span>
          </label>
          <small style="color:#64748b; font-size:0.75rem; display:block; margin-left:26px;">কাস্টমার আগ্রহী হলে এজেন্ট বিনয়ের সাথে তার হোয়াটসঅ্যাপ নম্বর চাইবে।</small>
        </div>

        <div class="form-group" style="margin-bottom:0;">
          <label class="form-label" style="display:flex; align-items:center; gap:8px;">
            <input type="checkbox" name="agent_auto_queue_whatsapp_welcome" value="1" <?= $cur['agent_auto_queue_whatsapp_welcome'] === '1' ? 'checked' : '' ?> style="width:18px; height:18px; accent-color:#10b981;">
            <span>চ্যাটে কাস্টমার নম্বর দিলে স্বয়ংক্রিয়ভাবে WhatsApp Outbox-এ ডেমো ও ওয়েলকাম মেসেজ কিউ করবে</span>
          </label>
          <small style="color:#64748b; font-size:0.75rem; display:block; margin-left:26px;">কাস্টমার চ্যাটে নম্বর টাইপ করলেই সিস্টেম ব্যাকএন্ডে স্বয়ংক্রিয়ভাবে ওয়েলকাম মেসেজ তৈরি করে রাখবে।</small>
        </div>
      </div>
    </div>

  </div>

  <div style="margin-top: 2rem; display:flex; gap:12px; justify-content:flex-end;">
    <button type="submit" class="btn-admin btn-admin-primary" style="padding:12px 28px; font-size:1rem; font-weight:700;">
      💾 সেটিংস সেভ ও সক্রিয় করুন (Save Settings)
    </button>
  </div>
</form>

<?php
admin_footer();
