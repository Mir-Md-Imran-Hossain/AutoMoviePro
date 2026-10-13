<?php
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';

$uiLang = strtolower(substr((string) ($_GET['lang'] ?? $_COOKIE['amp_ui_lang'] ?? 'bn'), 0, 2));
if (!in_array($uiLang, amp_cms_langs(), true)) {
    $uiLang = 'bn';
}

$brand = setting($pdo, 'hero_brand', 'AutoMovie Pro');
$price = (float) setting($pdo, 'price_amount', '2998');
$addonPrice = (float) setting($pdo, 'language_addon_price', '499');
$priceLabel = setting_i18n($pdo, 'price_label', $uiLang, '') ?? '';
$useCmsPriceLabel = trim($priceLabel) !== '';
$langCatalog = amp_lang_catalog();
$siteUrl = rtrim((string) ($config['site_url'] ?? 'https://automoviepro.com'), '/');
$waLink = amp_whatsapp_sales_link('Hi! I want to order AutoMovie Pro.');
$error = !empty($_GET['error']);
?>
<!DOCTYPE html>
<html lang="<?= e($uiLang) ?>"<?= $uiLang === 'ur' ? ' dir="rtl"' : '' ?>>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= e($brand) ?> — Checkout</title>
  <meta name="robots" content="noindex">
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <link rel="stylesheet" href="/assets/css/site.css">
  <script>
    window.AMP_SITE = {
      price: <?= json_encode($price) ?>,
      addon: <?= json_encode($addonPrice) ?>,
      waLink: <?= json_encode($waLink) ?>,
      langs: <?= json_encode($langCatalog, JSON_UNESCAPED_UNICODE) ?>,
      features: [],
      uiLang: <?= json_encode($uiLang) ?>
    };
  </script>
</head>
<body>
  <header class="site-header">
    <a class="logo-link" href="/?lang=<?= e($uiLang) ?>">
      <img class="logo-img" src="/assets/img/logo.png" alt="<?= e($brand) ?>" width="40" height="40">
      <div class="logo"><?= e($brand) ?> <span>SAAS</span></div>
    </a>
    <div class="header-actions">
       <div class="mech-switch-container">
          <span class="lang-label" id="lang-en">EN</span>
          <div class="mech-switch" id="siteLangSwitch" onclick="this.classList.toggle('active'); document.dispatchEvent(new CustomEvent('langToggle'));">
              <div class="mech-toggle"></div>
          </div>
          <span class="lang-label" id="lang-bn">BN</span>
      </div>
      <a class="btn btn-sm btn-ghost" href="/?lang=<?= e($uiLang) ?>" data-i18n="home">হোমে ফিরুন</a>
    </div>
  </header>

  <?php
  $reqProduct = strtolower(trim((string) ($_GET['product'] ?? 'video_studio')));
  if (!in_array($reqProduct, ['video_studio', 'fb_business', 'profile_page', 'google_pro'], true)) {
      $reqProduct = 'video_studio';
  }
  $reqPlan = (int) ($_GET['plan'] ?? 1);
  $isGooglePro = ($reqProduct === 'google_pro');

  if ($isGooglePro) {
      if ($reqPlan === 24) $initialPrice = 1999;
      elseif ($reqPlan === 18) $initialPrice = 1299;
      elseif ($reqPlan === 12) $initialPrice = 999;
      else { $reqPlan = 1; $initialPrice = 199; }
      $initialPlanName = "Special Gemini Pro API ({$reqPlan} Months)";
  } elseif ($reqProduct === 'fb_business') {
      $initialPrice = 2999;
      $initialPlanName = 'AutoMovie Pro FB Business Manager & Ad';
  } elseif ($reqProduct === 'profile_page') {
      $initialPrice = 1999;
      $initialPlanName = 'AutoMovie Pro FB Profile & Page Post';
  } else {
      $initialPrice = 3999;
      $initialPlanName = 'AutoMovie Pro Omni Social Media Content Automation';
  }
  ?>

  <section id="buy" class="reveal">
    <div class="purchase-wrapper" style="max-width: 800px;">
      <div class="section-head" style="margin-bottom: 2rem;">
        <h2 data-i18n="order_title">অর্ডার ফর্ম</h2>
        <p class="lead" data-i18n="order_lead">প্যাকেজ বেছে নিন, তথ্য দিন — পেমেন্ট সম্পন্ন করে দ্রুত এক্সেস বুঝে নিন।</p>
      </div>

      <?php if ($error): ?>
        <p class="err" data-i18n="order_error" style="color:var(--danger); text-align:center; font-weight:600; margin-bottom:1.5rem;">
          অনুগ্রহ করে আপনার নাম ও সঠিক WhatsApp নম্বর প্রদান করুন।
        </p>
      <?php endif; ?>

      <!-- Product Selection Tabs (5 Distinct Products) -->
      <div style="display: flex; gap: 0.65rem; justify-content: center; margin-bottom: 2rem; flex-wrap: wrap;">
        <button type="button" id="tabVideoStudioBtn" class="btn <?= ($reqProduct === 'video_studio' || (!$isGooglePro && !$isOmniSocial && $reqProduct !== 'fb_business' && $reqProduct !== 'profile_page')) ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          🎬 ১. Omni Social Video Automation (৳৩,৯৯৯)
        </button>
        <button type="button" id="tabFbBusinessBtn" class="btn <?= ($reqProduct === 'fb_business') ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          💼 ২. Omni FB Business Manager & Ad (৳২,৯৯৯)
        </button>
        <button type="button" id="tabProfilePageBtn" class="btn <?= ($reqProduct === 'profile_page') ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          📝 ৩. Omni Profile & Page Post (৳১,৯৯৯)
        </button>
        <button type="button" id="tabGoogleProBtn" class="btn <?= $isGooglePro ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          🚀 ৪. Special Gemini Pro API
        </button>
      </div>

      <!-- 1. Video Studio Product Block -->
      <div id="videoStudioBlock" style="<?= ($reqProduct === 'video_studio' || (!$isGooglePro && !$isOmniSocial && $reqProduct !== 'fb_business' && $reqProduct !== 'profile_page')) ? '' : 'display:none;' ?> background: rgba(11, 21, 40, 0.85); border: 2px solid #38bdf8; border-radius: var(--radius-lg); padding: 1.75rem; margin-bottom: 2rem; box-shadow: 0 0 30px rgba(56, 189, 248, 0.15);">
        <div style="text-align: center; margin-bottom: 1.25rem;">
          <span class="gpro-pill" style="background: rgba(56, 189, 248, 0.2); border: 1px solid #38bdf8; color: #38bdf8;">🎬 ভিডিও কন্টেন্ট পাইপলাইন</span>
          <h3 style="color: #38bdf8; font-size: 1.4rem; margin-top: 0.75rem; margin-bottom: 0.35rem;">
            AutoMovie Pro “Omni Social Media Content Automation”
          </h3>
          <p style="color: #cbd5e1; font-size: 0.92rem;">
            ইউটিউব, ফেসবুক ও টিকটকের জন্য স্বয়ংক্রিয় শর্ট ও লং ভিডিও তৈরি, শিডিউল পোস্টিং এবং কমেন্ট ও ইনবক্স রিপ্লাই।
          </p>
        </div>
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: var(--radius-md); padding: 1.25rem; font-size: 0.9rem; color: #93c5fd; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.85rem;">
          <div>✓ স্বয়ংক্রিয় ভাইরাল টপিক রিসার্চ ও চিত্রনাট্য</div>
          <div>✓ মানুষের মতো ১০০% স্বাভাবিক বাংলা এআই ভয়েসওভার</div>
          <div>✓ আল্ট্রা-এইচডি সিনেমাটিক ভিডিও ও কাইনেটিক মোশন কার্ড</div>
          <div>✓ ইউটিউব ও ফেসবুকে স্বয়ংক্রিয় অটোপাইলট আপলোড</div>
        </div>
        <div style="text-align: center; margin-top: 1.25rem; font-size: 2.2rem; font-weight: 800; color: #38bdf8;">
          ৳৩,৯৯৯ <span style="font-size: 1.1rem; color: #ef4444; text-decoration: line-through; margin-right: 8px;">৳১০,০০০</span> <span style="font-size: 0.92rem; color: #94A3B8; font-weight: 500;">(এককালীন ওয়ান টাইম লাইফটাইম লাইসেন্স)</span>
        </div>
      </div>

      <!-- 2. FB Business Manager Block -->
      <div id="fbBusinessBlock" style="<?= ($reqProduct === 'fb_business') ? '' : 'display:none;' ?> background: rgba(11, 21, 40, 0.85); border: 2px solid #f59e0b; border-radius: var(--radius-lg); padding: 1.75rem; margin-bottom: 2rem; box-shadow: 0 0 30px rgba(245, 158, 11, 0.15);">
        <div style="text-align: center; margin-bottom: 1.25rem;">
          <span class="gpro-pill" style="background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #f59e0b;">💼 বিজনেস ও সেলস ম্যানেজার</span>
          <h3 style="color: #fbbf24; font-size: 1.4rem; margin-top: 0.75rem; margin-bottom: 0.35rem;">
            AutoMovie Pro “Omni FB Business Manager & Ad Content Automation”
          </h3>
          <p style="color: #cbd5e1; font-size: 0.92rem;">
            বিজনেস পেজের জন্য সেলস ব্যানার, রিলস/অ্যাড তৈরি, ফেসবুক গ্রুপে অর্গানিক শেয়ার এবং কাস্টমার ইনবক্স ও কমেন্ট সেলস রিপ্লাই।
          </p>
        </div>
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-md); padding: 1.25rem; font-size: 0.9rem; color: #fde68a; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.85rem;">
          <div>✓ হাই-কনভার্টিং সেলস ব্যানার ও অফার গ্রাফিক্স</div>
          <div>✓ কাইনেটিক মোশন কার্ড সহ ৩০-৭০ সেকেন্ডের বিজ্ঞাপন ভিডিও</div>
          <div>✓ টার্গেটেড ফেসবুক গ্রুপে স্বয়ংক্রিয় অর্গানিক শেয়ারিং</div>
          <div>✓ কাস্টমারের প্রোডাক্ট ইনকোয়ারিতে স্বয়ংক্রিয় সেলস কনভার্সন</div>
        </div>
        <div style="text-align: center; margin-top: 1.25rem; font-size: 2.2rem; font-weight: 800; color: #fbbf24;">
          ৳২,৯৯৯ <span style="font-size: 1.1rem; color: #ef4444; text-decoration: line-through; margin-right: 8px;">৳৮,৫০০</span> <span style="font-size: 0.92rem; color: #94A3B8; font-weight: 500;">(এককালীন ওয়ান টাইম লাইফটাইম লাইসেন্স)</span>
        </div>
      </div>

      <!-- 3. Profile & Page Post Block -->
      <div id="profilePageBlock" style="<?= ($reqProduct === 'profile_page') ? '' : 'display:none;' ?> background: rgba(11, 21, 40, 0.85); border: 2px solid #10b981; border-radius: var(--radius-lg); padding: 1.75rem; margin-bottom: 2rem; box-shadow: 0 0 30px rgba(16, 185, 129, 0.15);">
        <div style="text-align: center; margin-bottom: 1.25rem;">
          <span class="gpro-pill" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #10b981;">📝 প্রোফাইল ও পেজ ব্র্যান্ডিং</span>
          <h3 style="color: #34d399; font-size: 1.4rem; margin-top: 0.75rem; margin-bottom: 0.35rem;">
            AutoMovie Pro “Omni Facebook Profile & Page Post Automation”
          </h3>
          <p style="color: #cbd5e1; font-size: 0.92rem;">
            ব্যক্তিগত প্রোফাইল ও পেজের জন্য নির্দিষ্ট নিসভিত্তিক রিটেন পোস্ট, কোট ব্যানার ও অটোপোস্টিং (যেমন আস-সুন্নাহ পাথ)।
          </p>
        </div>
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: var(--radius-md); padding: 1.25rem; font-size: 0.9rem; color: #a7f3d0; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.85rem;">
          <div>✓ খাঁটি ইসলামিক হাদিস/কোরআন বা অনুপ্রেরণামূলক পোস্ট রাইটিং</div>
          <div>✓ স্বয়ংক্রিয় গোল্ডেন এমবলেম ব্যানার ও ফটো ফ্রেম</div>
          <div>✓ ফেসবুক প্রোফাইল ও পেজে হিউম্যান-লাইক শিডিউল পোস্ট</div>
          <div>✓ ইসলামিক ও শিক্ষণীয় গ্রুপে নিরাপদ অর্গানিক শেয়ারিং</div>
        </div>
        <div style="text-align: center; margin-top: 1.25rem; font-size: 2.2rem; font-weight: 800; color: #34d399;">
          ৳১,৯৯৯ <span style="font-size: 1.1rem; color: #ef4444; text-decoration: line-through; margin-right: 8px;">৳৬,৫০০</span> <span style="font-size: 0.92rem; color: #94A3B8; font-weight: 500;">(এককালীন ওয়ান টাইম লাইফটাইম লাইসেন্স)</span>
        </div>
      </div>

      <!-- 4. Google Pro Price Block & Highlights -->
      <div id="googleProBlock" style="<?= $isGooglePro ? '' : 'display:none;' ?> background: rgba(11, 21, 40, 0.8); border: 2px solid rgba(168, 85, 247, 0.5); border-radius: var(--radius-lg); padding: 1.75rem; margin-bottom: 2rem;">
        <div style="text-align: center; margin-bottom: 1.5rem;">
          <span class="gpro-pill" style="background: rgba(168, 85, 247, 0.2); border: 1px solid #c084fc; color: #c084fc;">⚡ স্পেশাল এআই সার্ভিস</span>
          <h3 style="color: #c084fc; font-size: 1.4rem; margin-top: 0.75rem; margin-bottom: 0.35rem;">
            AutoMovie Pro “Special Gemini Pro Account with API”
          </h3>
          <p style="color: #cbd5e1; font-size: 0.92rem;">
            ফ্রি API কোটা ড্রপ বা স্পিড স্লো হওয়া এড়াতে আমাদের প্রিমিয়াম জেমিনি প্রো ক্লাউড অ্যাকাউন্ট ও এপিআই স্লট।
          </p>
        </div>

        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(168, 85, 247, 0.25); border-radius: var(--radius-md); padding: 1.25rem; margin-bottom: 1.75rem; font-size: 0.9rem; color: #e9d5ff; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.85rem;">
          <div>⚡ জেমিনি ৩.১ ফ্ল্যাশ ও প্রো আল্ট্রা-ফাস্ট রেসপন্স</div>
          <div>🎙️ আল্ট্রা-ন্যাচারাল রোবোটিকলেস হিউম্যান ভয়েসওভার</div>
          <div>📈 আনলিমিটেড কোটা পুল ও ব্যাকআপ কি রোটেশন</div>
          <div>☁️ হাই-রেজোলিউশন ভিডিও ফুটেজ স্টোরেজ ক্লাউড ভল্ট</div>
        </div>

        <fieldset style="border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.25rem; margin: 0 0 1rem; background: rgba(15, 23, 42, 0.6);">
          <legend style="color: #c084fc; font-weight: 700; font-size: 0.95rem; padding: 0 8px;">প্ল্যান নির্বাচন করুন</legend>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
            <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 0.85rem; background: rgba(30, 41, 59, 0.8); border-radius: var(--radius-md); border: 1px solid #475569;">
              <input type="radio" name="google_plan_choice" value="1" <?= (!$isGooglePro || $reqPlan === 1) ? 'checked' : '' ?>>
              <div>
                <strong style="color: #fff; display: block;">টেস্ট একাউন্ট (১ মাস)</strong>
                <span style="color: #c084fc; font-weight: 800; font-size: 1.15rem;">১৯৯ ৳</span>
              </div>
            </label>

            <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 0.85rem; background: rgba(30, 41, 59, 0.8); border-radius: var(--radius-md); border: 2px solid #a855f7;">
              <input type="radio" name="google_plan_choice" value="12" <?= ($isGooglePro && $reqPlan === 12) ? 'checked' : '' ?>>
              <div>
                <strong style="color: #fff; display: block;">স্টার্টআপ একাউন্ট (১২ মাস)</strong>
                <span style="color: #c084fc; font-weight: 800; font-size: 1.15rem;">৯৯৯ ৳</span>
              </div>
            </label>

            <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 0.85rem; background: rgba(30, 41, 59, 0.8); border-radius: var(--radius-md); border: 1px solid #475569;">
              <input type="radio" name="google_plan_choice" value="18" <?= ($isGooglePro && $reqPlan === 18) ? 'checked' : '' ?>>
              <div>
                <strong style="color: #fff; display: block;">বিজনেস একাউন্ট (১৮ মাস)</strong>
                <span style="color: #c084fc; font-weight: 800; font-size: 1.15rem;">১২৯৯ ৳</span>
              </div>
            </label>

            <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 0.85rem; background: rgba(30, 41, 59, 0.8); border-radius: var(--radius-md); border: 1px solid #475569;">
              <input type="radio" name="google_plan_choice" value="24" <?= ($isGooglePro && $reqPlan === 24) ? 'checked' : '' ?>>
              <div>
                <strong style="color: #fff; display: block;">রিল্যাক্স বিজনেস (২টি একাউন্ট)</strong>
                <span style="color: #c084fc; font-weight: 800; font-size: 1.15rem;">১৯৯৯ ৳</span>
              </div>
            </label>
          </div>
        </fieldset>
      </div>

      <form class="purchase" method="post" action="/purchase.php" id="purchaseForm">
        <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
        <input type="hidden" name="product_type" id="productTypeField" value="<?= e($reqProduct) ?>">
        <input type="hidden" name="plan_duration_months" id="planDurationField" value="<?= $reqPlan ?>">
        <input type="hidden" name="plan_name" id="planNameField" value="<?= e($initialPlanName) ?>">
        <input type="hidden" name="amount" id="orderAmount" value="<?= (int) $initialPrice ?>">
        <input type="hidden" name="base_langs" id="baseLangs" value="en,bn">
        <input type="hidden" name="addon_langs" id="addonLangs" value="">
        <input type="hidden" name="ui_lang" value="<?= e($uiLang) ?>">

        <div class="form-group">
          <label><span data-i18n="name">আপনার পূর্ণ নাম</span></label>
          <input name="name" required maxlength="120" autocomplete="name" placeholder="John Doe">
        </div>

        <div class="form-group">
          <label><span data-i18n="whatsapp">WhatsApp নম্বর (অ্যাক্টিভেশনের জন্য)</span></label>
          <input name="whatsapp" required placeholder="+8801..." maxlength="32" inputmode="tel">
        </div>

        <div class="form-group">
          <label><span data-i18n="email_opt">ইমেইল / জিমেইল অ্যাড্রেস</span></label>
          <input name="email" id="emailInput" type="email" maxlength="120" autocomplete="email" placeholder="example@gmail.com">
        </div>

        <div id="softwareLangPickers" style="<?= $isGooglePro ? 'display:none;' : '' ?>">
          <fieldset class="lang-pick">
            <legend data-i18n="pick_personal_lang">কোর প্যাকেজে ইংরেজির সাথে আপনার প্রাথমিক ভাষা বেছে নিন</legend>
            <p class="hint" data-i18n="en_included">ইংরেজি ডিফল্টভাবে সব প্যাকেজে সক্রিয় থাকে।</p>
            <div class="lang-chips" id="personalLangChips">
              <?php foreach ($langCatalog as $code => $label):
                  if ($code === 'en') {
                      continue;
                  }
                  $checked = ($code === $uiLang) || ($uiLang === 'en' && $code === 'bn');
                  ?>
                <label class="chip">
                  <input type="radio" name="personal_lang" value="<?= e($code) ?>" <?= $checked ? 'checked' : '' ?> required>
                  <span><?= e($label) ?></span>
                </label>
              <?php endforeach; ?>
            </div>
          </fieldset>

          <fieldset class="lang-pick" style="margin-top: 1rem;">
            <legend data-i18n="pick_addon_langs" data-i18n-vars='<?= e(json_encode(["n" => (int) $addonPrice], JSON_UNESCAPED_UNICODE)) ?>'>অতিরিক্ত কোনো গ্লোবাল ভাষা আনলক করতে চান? (+৳<?= (int) $addonPrice ?> / ভাষা)</legend>
            <div class="lang-chips" id="addonLangChips">
              <?php foreach ($langCatalog as $code => $label):
                  if ($code === 'en') {
                      continue;
                  }
                  ?>
                <label class="chip chip-addon" data-lang="<?= e($code) ?>">
                  <input type="checkbox" name="extra_langs[]" value="<?= e($code) ?>">
                  <span><?= e($label) ?> +৳<?= (int) $addonPrice ?></span>
                </label>
              <?php endforeach; ?>
            </div>
          </fieldset>
        </div>

        <!-- Coupon Box -->
        <div class="coupon-box" id="couponBoxSection">
          <label style="font-size:0.88rem; color:#93c5fd; font-weight:600;" data-i18n="coupon_label">🎟️ ডিসকাউন্ট কুপন কোড (যেমন: LAUNCH500):</label>
          <div class="coupon-input-group">
            <input type="text" id="couponCodeInput" name="coupon_code" placeholder="কুপন কোড লিখুন" data-i18n-placeholder="coupon_placeholder">
            <button type="button" class="coupon-btn" id="applyCouponBtn" data-i18n="coupon_btn">অ্যাপ্লাই</button>
          </div>
          <div id="couponStatusMsg" class="coupon-msg"></div>
        </div>

        <div class="total-line">
          <span data-i18n="total_due">সর্বমোট পরিশোধযোগ্য</span>
          <strong id="totalDisplay">৳<?= (int) $initialPrice ?></strong>
        </div>

        <button class="btn" type="submit" style="width:100%; font-size:1.1rem; padding:1rem;" data-i18n="pay_now">অর্ডার কনফার্ম করুন</button>
        <p style="text-align:center; margin-top:1rem;">
          <a class="btn-wa-inline" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="or_whatsapp">অথবা WhatsApp-এ সরাসরি অর্ডার সম্পন্ন করুন</a>
        </p>
      </form>
    </div>
  </section>

  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const tabVideoStudioBtn = document.getElementById('tabVideoStudioBtn');
      const tabFbBusinessBtn = document.getElementById('tabFbBusinessBtn');
      const tabProfilePageBtn = document.getElementById('tabProfilePageBtn');
      const tabGoogleProBtn = document.getElementById('tabGoogleProBtn');

      const videoStudioBlock = document.getElementById('videoStudioBlock');
      const fbBusinessBlock = document.getElementById('fbBusinessBlock');
      const profilePageBlock = document.getElementById('profilePageBlock');
      const googleProBlock = document.getElementById('googleProBlock');

      const softwareLangPickers = document.getElementById('softwareLangPickers');
      const productTypeField = document.getElementById('productTypeField');
      const planDurationField = document.getElementById('planDurationField');
      const planNameField = document.getElementById('planNameField');
      const orderAmount = document.getElementById('orderAmount');
      const totalDisplay = document.getElementById('totalDisplay');

      let currentDiscount = 0;

      function calculateTotal() {
        const prod = productTypeField.value;
        let base = 3999;
        let pName = 'AutoMovie Pro Omni Social Media Content Automation';

        if (prod === 'fb_business') {
          base = 2999;
          pName = 'AutoMovie Pro FB Business Manager & Ad';
        } else if (prod === 'profile_page') {
          base = 1999;
          pName = 'AutoMovie Pro FB Profile & Page Post';
        } else if (prod === 'google_pro') {
          const choice = document.querySelector('input[name="google_plan_choice"]:checked');
          const months = choice ? parseInt(choice.value, 10) : 1;
          if (months === 24) base = 1999;
          else if (months === 18) base = 1299;
          else if (months === 12) base = 999;
          else base = 199;
          planDurationField.value = months;
          pName = `Special Gemini Pro API (${months} Months)`;
        } else {
          // video_studio: calculate multi-language add-on
          base = 3999;
          pName = 'AutoMovie Pro Omni Social Media Content Automation';
          const checkedAddons = document.querySelectorAll('input[name="extra_langs[]"]:checked');
          base += (checkedAddons.length * 499);
        }

        planNameField.value = pName;
        const finalAmt = Math.max(0, base - currentDiscount);
        orderAmount.value = finalAmt;
        totalDisplay.textContent = '৳' + finalAmt;
      }

      function setProduct(mode) {
        productTypeField.value = mode;

        // Reset all tabs
        [tabVideoStudioBtn, tabFbBusinessBtn, tabProfilePageBtn, tabGoogleProBtn].forEach(b => b?.classList.add('btn-ghost'));
        // Hide all blocks
        [videoStudioBlock, fbBusinessBlock, profilePageBlock, googleProBlock].forEach(b => { if (b) b.style.display = 'none'; });

        if (mode === 'google_pro') {
          tabGoogleProBtn?.classList.remove('btn-ghost');
          if (googleProBlock) googleProBlock.style.display = 'block';
          if (softwareLangPickers) softwareLangPickers.style.display = 'none';
        } else if (mode === 'fb_business') {
          tabFbBusinessBtn?.classList.remove('btn-ghost');
          if (fbBusinessBlock) fbBusinessBlock.style.display = 'block';
          if (softwareLangPickers) softwareLangPickers.style.display = 'none';
          planDurationField.value = '0';
        } else if (mode === 'profile_page') {
          tabProfilePageBtn?.classList.remove('btn-ghost');
          if (profilePageBlock) profilePageBlock.style.display = 'block';
          if (softwareLangPickers) softwareLangPickers.style.display = 'none';
          planDurationField.value = '0';
        } else {
          // video_studio
          tabVideoStudioBtn?.classList.remove('btn-ghost');
          if (videoStudioBlock) videoStudioBlock.style.display = 'block';
          if (softwareLangPickers) softwareLangPickers.style.display = 'block';
          planDurationField.value = '0';
        }

        calculateTotal();
      }

      tabVideoStudioBtn?.addEventListener('click', () => setProduct('video_studio'));
      tabFbBusinessBtn?.addEventListener('click', () => setProduct('fb_business'));
      tabProfilePageBtn?.addEventListener('click', () => setProduct('profile_page'));
      tabGoogleProBtn?.addEventListener('click', () => setProduct('google_pro'));

      document.querySelectorAll('input[name="google_plan_choice"]').forEach(r => {
        r.addEventListener('change', () => {
          if (productTypeField.value === 'google_pro') {
            calculateTotal();
          }
        });
      });

      document.querySelectorAll('input[name="extra_langs[]"]').forEach(cb => {
        cb.addEventListener('change', () => {
          if (productTypeField.value === 'video_studio') {
            calculateTotal();
          }
        });
      });

      // Coupon application
      const couponBtn = document.getElementById('applyCouponBtn');
      const couponInput = document.getElementById('couponCodeInput');
      const couponMsg = document.getElementById('couponStatusMsg');

      couponBtn?.addEventListener('click', async () => {
        const code = couponInput?.value.trim().toUpperCase();
        if (!code) {
          if (couponMsg) couponMsg.textContent = 'কুপন কোড প্রদান করুন';
          return;
        }
        if (code === 'LAUNCH500' || code === 'SPECIAL500') {
          currentDiscount = 500;
          if (couponMsg) {
            couponMsg.style.color = '#34d399';
            couponMsg.textContent = `কুপন সফল! ৳৫০০ ছাড় যুক্ত হয়েছে।`;
          }
        } else if (code === 'PRO200') {
          currentDiscount = 200;
          if (couponMsg) {
            couponMsg.style.color = '#34d399';
            couponMsg.textContent = `কুপন সফল! ৳২০০ ছাড় যুক্ত হয়েছে।`;
          }
        } else {
          currentDiscount = 0;
          if (couponMsg) {
            couponMsg.style.color = '#ef4444';
            couponMsg.textContent = 'দুঃখিত, কুপনটি অবৈধ বা মেয়াদোত্তীর্ণ।';
          }
        }
        calculateTotal();
      });

      window.AMP_RECALC = calculateTotal;
    });
  </script>

  <!-- Floating AI Sales Consultant Widget ("আয়েশা") -->
  <div id="ampChat" class="amp-chat" aria-live="polite">
    <button type="button" class="amp-chat-toggle" id="ampChatToggle">
      <span class="online-dot"></span>
      <span data-i18n="agent_toggle_btn">👩‍💼 আয়েশা (লাইভ সেলস কনসালট্যান্ট)</span>
    </button>
    <div class="amp-chat-panel" id="ampChatPanel" hidden>
      <header class="amp-chat-head">
        <div class="amp-chat-agent-info">
          <div class="amp-chat-avatar">👩‍💼</div>
          <div class="amp-chat-name">
            <strong data-i18n="agent_name">আয়েশা (Ayesha)</strong>
            <span><span class="online-dot" style="width:6px; height:6px;"></span> <span data-i18n="agent_status">অনলাইন কনসালট্যান্ট</span></span>
          </div>
        </div>
        <button type="button" class="amp-chat-close" id="ampChatClose" aria-label="Close">×</button>
      </header>
      <div class="amp-chat-log" id="ampChatLog"></div>
      <form class="amp-chat-form" id="ampChatForm">
        <input type="text" id="ampChatInput" placeholder="প্যাকেজ, ফিচার বা অফার নিয়ে প্রশ্ন করুন…" data-i18n-placeholder="agent_placeholder" maxlength="800" autocomplete="off">
        <button type="submit" data-i18n="agent_send">পাঠান</button>
      </form>
      <a class="amp-chat-wa" id="ampChatWa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="agent_wa_link">📱 সরাসরি WhatsApp-এ বিস্তারিত কথা বলুন</a>
    </div>
  </div>

  <script src="/assets/js/i18n-site.js"></script>
  <script src="/assets/js/site.js"></script>
  <script src="/assets/js/marketing-chat.js"></script>
</body>
</html>
