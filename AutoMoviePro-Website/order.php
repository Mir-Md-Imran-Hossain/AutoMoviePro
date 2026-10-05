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
  <title><?= e($brand) ?> — Order</title>
  <meta name="robots" content="noindex">
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
      <div class="logo"><?= e($brand) ?></div>
    </a>
    <div class="header-actions">
      <select id="siteLangSelect" aria-label="Language"></select>
      <a class="btn btn-sm btn-ghost" href="/?lang=<?= e($uiLang) ?>" data-i18n="home">হোমে ফিরুন</a>
    </div>
  </header>

  <?php
  $reqProduct = strtolower(trim((string) ($_GET['product'] ?? '')));
  $reqPlan = (int) ($_GET['plan'] ?? 1);
  $isGooglePro = ($reqProduct === 'google_pro');
  ?>

  <section id="buy" class="reveal in">
    <h2 data-i18n="order_title">অর্ডার করুন</h2>
    <p class="lead" data-i18n="order_lead">প্যাকেজ বেছে নিন, তথ্য দিন — পেমেন্ট সম্পন্ন করে দ্রুত এক্সেস বুঝে নিন।</p>
    <?php if ($error): ?>
      <p class="err" data-i18n="order_error">নাম ও সঠিক WhatsApp নম্বর দিন।</p>
    <?php endif; ?>

    <!-- Product Selection Tabs -->
    <div style="display: flex; gap: 0.75rem; justify-content: center; margin: 1.5rem 0 2rem; flex-wrap: wrap;">
      <button type="button" id="tabSoftwareBtn" class="btn <?= !$isGooglePro ? '' : 'ghost' ?>" style="padding: 0.65rem 1.25rem; font-size: 0.95rem; border-radius: 9999px;">
        💻 AutoMovie Pro লাইফটাইম সফটওয়্যার
      </button>
      <button type="button" id="tabGoogleProBtn" class="btn <?= $isGooglePro ? '' : 'ghost' ?>" style="padding: 0.65rem 1.25rem; font-size: 0.95rem; border-radius: 9999px; background: <?= $isGooglePro ? '#2563eb' : 'transparent' ?>; border-color: #2563eb;">
        🚀 স্পেশাল গুগল AI Pro প্যাকেজ
      </button>
    </div>

    <!-- Software Price Block -->
    <div class="price-block" id="softwarePriceBlock" style="<?= $isGooglePro ? 'display:none;' : '' ?>">
      <div class="amount" id="softwareAmountDisplay">৳<?= (int) $price ?></div>
      <?php if ($useCmsPriceLabel): ?>
        <div class="lead"><?= e($priceLabel) ?></div>
      <?php else: ?>
        <div class="lead" data-i18n="price_base_note">একবার কিনলেই — ইংরেজি + আপনার পছন্দের ১টা ভাষা</div>
      <?php endif; ?>
      <p class="addon-note" data-i18n="price_addon_note" data-i18n-vars='<?= e(json_encode(["n" => (int) $addonPrice], JSON_UNESCAPED_UNICODE)) ?>'>আরও ভাষা চাইলে প্রতিটায় ৳<?= (int) $addonPrice ?></p>
    </div>

    <!-- Google Pro Price Block & Highlights -->
    <div id="googleProBlock" style="<?= $isGooglePro ? '' : 'display:none;' ?> background: #0b1528; border: 2px solid #2563eb; border-radius: 18px; padding: 1.5rem; margin-bottom: 2rem;">
      <div style="text-align: center; margin-bottom: 1.25rem;">
        <span style="background: #2563eb; color: #fff; font-size: 0.75rem; font-weight: 700; padding: 4px 12px; border-radius: 9999px; text-transform: uppercase;">গুগল স্পেশাল সার্ভিস</span>
        <h3 style="color: #60a5fa; font-size: 1.35rem; margin-top: 0.5rem; margin-bottom: 0.25rem;">কোন ঝামেলা ছাড়াই ভিডিও তৈরির জন্য স্পেশাল গুগল AI Pro প্যাকেজ</h3>
        <p style="color: #cbd5e1; font-size: 0.9rem;">সরাসরি আপনার জিমেইল অ্যাকাউন্টে ১৫০ জিবি ক্লাউড ড্রাইভ ও আনলিমিটেড কোটা এপিআই কনফিগার করে দেওয়া হবে।</p>
      </div>

      <div style="background: #111d33; border: 1px solid #1e3a8a; border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem; font-size: 0.88rem; color: #93c5fd; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem;">
        <div>⚡ গুগল Nano Banana ও VEO-3 স্পেশাল API</div>
        <div>🎙️ আল্ট্রা-ন্যাচারাল রোবোটিকলেস TTS</div>
        <div>📈 হাই CTR এসইও টপিক ও স্ক্রিপ্ট</div>
        <div>💬 ২৪/৭ আনলিমিটেড চ্যাটিং ও মনিটরিং</div>
        <div style="grid-column: 1 / -1;">☁️ ফুটেজ স্টোরের জন্য ১৫০ জিবি গুগল ক্লাউড স্টোরেজ</div>
      </div>

      <fieldset style="border: 1px solid #334155; border-radius: 12px; padding: 1rem; margin: 0 0 1rem; background: #0f172a;">
        <legend style="color: #38bdf8; font-weight: 600; font-size: 0.95rem; padding: 0 8px;">প্ল্যান নির্বাচন করুন</legend>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
          <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 8px; padding: 0.75rem; background: #1e293b; border-radius: 8px; border: 1px solid #475569;">
            <input type="radio" name="google_plan_choice" value="1" <?= (!$isGooglePro || $reqPlan === 1) ? 'checked' : '' ?>>
            <div>
              <strong style="color: #fff; display: block;">প্ল্যান ১: মাসিক (৩০ দিন)</strong>
              <span style="color: #38bdf8; font-weight: 700; font-size: 1.1rem;">১২০ ৳</span>
            </div>
          </label>

          <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 8px; padding: 0.75rem; background: #1e293b; border-radius: 8px; border: 1px solid #38bdf8;">
            <input type="radio" name="google_plan_choice" value="12" <?= ($isGooglePro && $reqPlan === 12) ? 'checked' : '' ?>>
            <div>
              <strong style="color: #fff; display: block;">প্ল্যান ২: বাৎসরিক (১২ মাস)</strong>
              <span style="color: #38bdf8; font-weight: 700; font-size: 1.1rem;">৯৯৯ ৳</span>
            </div>
          </label>

          <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 8px; padding: 0.75rem; background: #1e293b; border-radius: 8px; border: 1px solid #475569;">
            <input type="radio" name="google_plan_choice" value="18" <?= ($isGooglePro && $reqPlan === 18) ? 'checked' : '' ?>>
            <div>
              <strong style="color: #fff; display: block;">প্ল্যান ৩: স্পেশাল (১৮ মাস)</strong>
              <span style="color: #38bdf8; font-weight: 700; font-size: 1.1rem;">১২৯৯ ৳</span>
            </div>
          </label>
        </div>
      </fieldset>
    </div>

    <form class="purchase" method="post" action="/purchase.php" id="purchaseForm">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="product_type" id="productTypeField" value="<?= $isGooglePro ? 'google_pro' : 'software' ?>">
      <input type="hidden" name="plan_duration_months" id="planDurationField" value="<?= $reqPlan ?>">
      <input type="hidden" name="plan_name" id="planNameField" value="<?= $isGooglePro ? "Google AI Pro ({$reqPlan} Months)" : 'Lifetime Core' ?>">
      <input type="hidden" name="amount" id="orderAmount" value="<?= $isGooglePro ? ($reqPlan === 18 ? 1299 : ($reqPlan === 12 ? 999 : 120)) : (int) $price ?>">
      <input type="hidden" name="base_langs" id="baseLangs" value="en,bn">
      <input type="hidden" name="addon_langs" id="addonLangs" value="">
      <input type="hidden" name="ui_lang" value="<?= e($uiLang) ?>">

      <label><span data-i18n="name">আপনার নাম</span> <input name="name" required maxlength="120" autocomplete="name"></label>
      <label><span data-i18n="whatsapp">WhatsApp নম্বর</span> <input name="whatsapp" required placeholder="8801…" maxlength="32" inputmode="tel"></label>
      <label><span id="emailLabel">আপনার ইমেইল / জিমেইল (Gmail)</span> <input name="email" id="emailInput" type="email" maxlength="120" autocomplete="email" placeholder="example@gmail.com"></label>

      <div id="softwareLangPickers" style="<?= $isGooglePro ? 'display:none;' : '' ?>">
        <fieldset class="lang-pick">
          <legend data-i18n="pick_personal_lang">ইংরেজির সাথে কোন ভাষা রাখবেন?</legend>
          <p class="hint" data-i18n="en_included">ইংরেজি সব প্যাকেজেই থাকে।</p>
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

        <fieldset class="lang-pick">
          <legend data-i18n="pick_addon_langs">আরও ভাষা খুলবেন? (প্রতিটা ৳<?= (int) $addonPrice ?>)</legend>
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

      <div class="coupon-box" id="couponBoxSection">
        <label style="font-size:0.85rem; color:#94a3b8;">🎟️ ডিসকাউন্ট কুপন কোড (যেমন: LAUNCH500):</label>
        <div class="coupon-input-group">
          <input type="text" id="couponCodeInput" name="coupon_code" placeholder="কুপন কোড লিখুন" style="max-width:200px;">
          <button type="button" class="coupon-btn" id="applyCouponBtn">অ্যাপ্লাই</button>
        </div>
        <div id="couponStatusMsg" class="coupon-msg"></div>
      </div>

      <div class="total-line">
        <span data-i18n="total_due">মোট টাকা</span>
        <strong id="totalDisplay">৳<?= $isGooglePro ? ($reqPlan === 18 ? 1299 : ($reqPlan === 12 ? 999 : 120)) : (int) $price ?></strong>
      </div>

      <button class="btn" type="submit" data-i18n="pay_now">অর্ডার কনফার্ম করুন</button>
      <p class="hint"><a class="btn-wa-inline" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="or_whatsapp">সরাসরি WhatsApp-এ কথা বলুন</a></p>
    </form>
  </section>

  <script>
    // Dynamic Product and Plan Switcher Logic
    document.addEventListener('DOMContentLoaded', () => {
      const tabSoftwareBtn = document.getElementById('tabSoftwareBtn');
      const tabGoogleProBtn = document.getElementById('tabGoogleProBtn');
      const softwarePriceBlock = document.getElementById('softwarePriceBlock');
      const googleProBlock = document.getElementById('googleProBlock');
      const softwareLangPickers = document.getElementById('softwareLangPickers');
      const productTypeField = document.getElementById('productTypeField');
      const planDurationField = document.getElementById('planDurationField');
      const planNameField = document.getElementById('planNameField');
      const orderAmount = document.getElementById('orderAmount');
      const totalDisplay = document.getElementById('totalDisplay');

      function setProduct(isPro) {
        if (isPro) {
          productTypeField.value = 'google_pro';
          tabGoogleProBtn.classList.remove('ghost');
          tabGoogleProBtn.style.background = '#2563eb';
          tabSoftwareBtn.classList.add('ghost');
          softwarePriceBlock.style.display = 'none';
          googleProBlock.style.display = 'block';
          softwareLangPickers.style.display = 'none';
          updateGooglePrice();
        } else {
          productTypeField.value = 'software';
          tabSoftwareBtn.classList.remove('ghost');
          tabGoogleProBtn.classList.add('ghost');
          tabGoogleProBtn.style.background = 'transparent';
          softwarePriceBlock.style.display = 'block';
          googleProBlock.style.display = 'none';
          softwareLangPickers.style.display = 'block';
          planNameField.value = 'Lifetime Core';
          if (window.AMP_RECALC) window.AMP_RECALC();
        }
      }

      function updateGooglePrice() {
        const choice = document.querySelector('input[name="google_plan_choice"]:checked');
        const months = choice ? parseInt(choice.value, 10) : 1;
        let p = 120;
        if (months === 18) p = 1299;
        else if (months === 12) p = 999;
        else p = 120;

        planDurationField.value = months;
        planNameField.value = `Google AI Pro (${months} Months)`;
        orderAmount.value = p;
        totalDisplay.textContent = '৳' + p;
      }

      tabSoftwareBtn?.addEventListener('click', () => setProduct(false));
      tabGoogleProBtn?.addEventListener('click', () => setProduct(true));

      document.querySelectorAll('input[name="google_plan_choice"]').forEach(r => {
        r.addEventListener('change', () => {
          if (productTypeField.value === 'google_pro') {
            updateGooglePrice();
          }
        });
      });
    });
  </script>

  <div id="ampChat" class="amp-chat" aria-live="polite">
    <button type="button" class="amp-chat-toggle" id="ampChatToggle">
      <span class="online-dot"></span>
      <span>👩‍💼 আয়েশা (লাইভ সেলস কনসালট্যান্ট)</span>
    </button>
    <div class="amp-chat-panel" id="ampChatPanel" hidden>
      <header class="amp-chat-head">
        <div class="amp-chat-agent-info">
          <div class="amp-chat-avatar">👩‍💼</div>
          <div class="amp-chat-name">
            <strong>আয়েশা (Ayesha)</strong>
            <span><span class="online-dot" style="width:6px; height:6px;"></span> অনলাইন কনসালট্যান্ট</span>
          </div>
        </div>
        <button type="button" class="amp-chat-close" id="ampChatClose" aria-label="Close">×</button>
      </header>
      <div class="amp-chat-log" id="ampChatLog"></div>
      <form class="amp-chat-form" id="ampChatForm">
        <input type="text" id="ampChatInput" placeholder="প্যাকেজ বা অফার নিয়ে প্রশ্ন করুন…" maxlength="800" autocomplete="off">
        <button type="submit" class="btn btn-sm">পাঠান</button>
      </form>
      <a class="amp-chat-wa" id="ampChatWa" href="<?= e($waLink) ?>" target="_blank" rel="noopener">📱 সরাসরি WhatsApp-এ কথা বলুন</a>
    </div>
  </div>

  <script src="/assets/js/i18n-site.js"></script>
  <script src="/assets/js/site.js"></script>
  <script src="/assets/js/marketing-chat.js"></script>
</body>
</html>
