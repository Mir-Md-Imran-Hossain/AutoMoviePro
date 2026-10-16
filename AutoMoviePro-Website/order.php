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
<html lang="<?= e($uiLang) ?>" class="notranslate" translate="no"<?= $uiLang === 'ur' ? ' dir="rtl"' : '' ?>>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="google" content="notranslate">
  <meta name="googlebot" content="notranslate">
  <title><?= e($brand) ?> — Checkout</title>
  <meta name="robots" content="noindex">
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <link rel="stylesheet" href="/assets/css/site.css?v=<?= filemtime(__DIR__ . '/assets/css/site.css') ?>">
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
<body class="notranslate" translate="no">
  <header class="site-header">
    <a class="logo-link" href="/?lang=<?= e($uiLang) ?>">
      <img class="logo-img" src="/assets/img/logo.png?v=<?= filemtime(__DIR__ . '/assets/img/logo.png') ?>" alt="<?= e($brand) ?>" width="40" height="40">
      <div class="logo"><?= e($brand) ?></div>
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
  if (!in_array($reqProduct, ['video_studio', 'fb_business', 'profile_page', 'wa_marketing', 'google_pro'], true)) {
      $reqProduct = 'video_studio';
  }
  $reqPlan = (int) ($_GET['plan'] ?? 1);
  $isGooglePro = ($reqProduct === 'google_pro');

  if ($reqProduct === 'wa_marketing') {
      if ($reqPlan === 3 || $reqPlan === 36) {
          $initialPrice = 1999;
          $initialPlanName = 'WAManager Pro — WhatsApp Marketing & CRM Suite (৩ বছর সাবস্ক্রিপশন)';
      } else {
          $reqPlan = 1;
          $initialPrice = 999;
          $initialPlanName = 'WAManager Pro — WhatsApp Marketing & CRM Suite (১ বছর সাবস্ক্রিপশন)';
      }
  } elseif ($isGooglePro) {
      if ($reqPlan === 24) $initialPrice = 1999;
      elseif ($reqPlan === 18) $initialPrice = 1299;
      elseif ($reqPlan === 12) $initialPrice = 999;
      else { $reqPlan = 1; $initialPrice = 120; }
      $initialPlanName = "Special Gemini Pro API ({$reqPlan} Months)";
  } elseif ($reqProduct === 'fb_business') {
      $initialPrice = 2999;
      $initialPlanName = 'AutoMovie Pro - FB Business Manager & Ad Automation Engine';
  } elseif ($reqProduct === 'profile_page') {
      $initialPrice = 1999;
      $initialPlanName = 'AutoMovie Pro - FB Profile & Page Post Automation Engine';
  } else {
      $initialPrice = 3999;
      $initialPlanName = 'AutoMovie Pro - Social Media Content Automation Engine';
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
        <button type="button" id="tabVideoStudioBtn" class="btn <?= ($reqProduct === 'video_studio') ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          🎬 ১. Social Media Engine (৳৩,৯৯৯)
        </button>
        <button type="button" id="tabFbBusinessBtn" class="btn <?= ($reqProduct === 'fb_business') ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          💼 ২. FB Business Engine (৳২,৯৯৯)
        </button>
        <button type="button" id="tabProfilePageBtn" class="btn <?= ($reqProduct === 'profile_page') ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          📝 ৩. FB Profile Engine (৳১,৯৯৯)
        </button>
        <button type="button" id="tabWaMarketingBtn" class="btn <?= ($reqProduct === 'wa_marketing') ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem; border-color:#25D366; color:<?= ($reqProduct === 'wa_marketing') ? '#000' : '#25D366' ?>; <?= ($reqProduct === 'wa_marketing') ? 'background:#25D366;' : '' ?>">
          📱 ৪. WhatsApp মার্কেটিং (৳৯৯৯/৳১,৯৯৯)
        </button>
        <button type="button" id="tabGoogleProBtn" class="btn <?= $isGooglePro ? '' : 'btn-ghost' ?>" style="border-radius: var(--radius-full); font-size: 0.92rem;">
          🚀 ৫. Special Gemini Pro API
        </button>
      </div>

      <!-- 1. Video Studio Product Block -->
      <div id="videoStudioBlock" style="<?= ($reqProduct === 'video_studio' || (!$isGooglePro && $reqProduct !== 'fb_business' && $reqProduct !== 'profile_page')) ? '' : 'display:none;' ?> background: rgba(11, 21, 40, 0.85); border: 2px solid #38bdf8; border-radius: var(--radius-lg); padding: 1.75rem; margin-bottom: 2rem; box-shadow: 0 0 30px rgba(56, 189, 248, 0.15);">
        <div style="text-align: center; margin-bottom: 1.25rem;">
          <span class="gpro-pill" style="background: rgba(56, 189, 248, 0.2); border: 1px solid #38bdf8; color: #38bdf8;">🎬 ভিডিও কন্টেন্ট পাইপলাইন</span>
          <h3 style="color: #38bdf8; font-size: 1.4rem; margin-top: 0.75rem; margin-bottom: 0.35rem;">
            AutoMovie Pro - Social Media Content Automation Engine
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
            AutoMovie Pro - FB Business Manager & Ad Automation Engine
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
            AutoMovie Pro - FB Profile & Page Post Automation Engine
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

      <!-- 4. WAManager Pro WhatsApp Marketing Block -->
      <div id="waMarketingBlock" style="<?= ($reqProduct === 'wa_marketing') ? '' : 'display:none;' ?> background: rgba(11, 21, 40, 0.85); border: 2px solid #25D366; border-radius: var(--radius-lg); padding: 1.75rem; margin-bottom: 2rem; box-shadow: 0 0 30px rgba(37, 211, 102, 0.15);">
        <div style="text-align: center; margin-bottom: 1.25rem;">
          <span class="gpro-pill" style="background: rgba(37, 211, 102, 0.2); border: 1px solid #25D366; color: #25D366;">📱 WhatsApp মার্কেটিং ও সিআরএম স্যুট</span>
          <h3 style="color: #25D366; font-size: 1.4rem; margin-top: 0.75rem; margin-bottom: 0.35rem;">
            WAManager Pro — Official WhatsApp Marketing Suite
          </h3>
          <p style="color: #cbd5e1; font-size: 0.92rem;">
            আনলিমিটেড বাল্ক মেসেজিং, অ্যান্টি-ব্যান স্পিনট্যাক্স, ইন্টেলিজেন্ট অটো-রিপ্লাই বট, বি২বি বিজনেস লিড স্ক্র্যাপার এবং রিয়েল-টাইম লাইভ চ্যাট ইনবক্স।
          </p>
        </div>

        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(37, 211, 102, 0.3); border-radius: var(--radius-md); padding: 1.25rem; font-size: 0.9rem; color: #86efac; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.85rem; margin-bottom: 1.5rem;">
          <div>✓ আনলিমিটেড বাল্ক ক্যাম্পেইন ও হিউম্যান-লাইক অ্যান্টি-ব্যান ডিলে</div>
          <div>✓ কিওয়ার্ড ও এআই-ভিত্তিক অটো-রিপ্লাই বট রুলস</div>
          <div>✓ Google Maps ও ওয়েবসাইট থেকে আনলিমিটেড B2B লিড স্ক্র্যাপার</div>
          <div>✓ হোয়াটসঅ্যাপ গ্রুপ মেম্বার এক্সট্রাক্টর ও কন্টাক্ট ফিল্টারিং</div>
          <div>✓ লাইভ চ্যাট ইনবক্স, মেসেজ স্টুডিও ও লাইভ ফোন প্রিভিউ</div>
          <div>✓ নিয়মিত নতুন নতুন ফিচার রিলিজ ও সফটওয়্যার আপডেট</div>
        </div>

        <fieldset style="border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.25rem; margin: 0 0 1rem; background: rgba(15, 23, 42, 0.6);">
          <legend style="color: #25D366; font-weight: 700; font-size: 0.95rem; padding: 0 8px;">সাবস্ক্রিপশন মেয়াদ নির্বাচন করুন</legend>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem;">
            <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 0.85rem; background: rgba(30, 41, 59, 0.8); border-radius: var(--radius-md); border: 1px solid #475569;">
              <input type="radio" name="wa_plan_choice" value="1" <?= ($reqProduct !== 'wa_marketing' || $reqPlan !== 3) ? 'checked' : '' ?>>
              <div>
                <strong style="color: #fff; display: block;">১ বছর সাবস্ক্রিপশন (1 Year License)</strong>
                <span style="color: #25D366; font-weight: 800; font-size: 1.2rem;">৯৯৯ ৳</span>
                <span style="font-size: 0.8rem; color: #94a3b8; display: block;">১২ মাস নিয়মিত আপডেট + স্ট্যান্ডার্ড সাপোর্ট</span>
              </div>
            </label>

            <label class="chip" style="cursor: pointer; display: flex; align-items: center; gap: 10px; padding: 0.85rem; background: rgba(30, 41, 59, 0.8); border-radius: var(--radius-md); border: 2px solid #25D366;">
              <input type="radio" name="wa_plan_choice" value="3" <?= ($reqProduct === 'wa_marketing' && ($reqPlan === 3 || $reqPlan === 36)) ? 'checked' : '' ?>>
              <div>
                <strong style="color: #fff; display: block;">৩ বছর সাবস্ক্রিপশন (3 Years License)</strong>
                <span style="color: #25D366; font-weight: 800; font-size: 1.2rem;">১,৯৯৯ ৳</span>
                <span style="font-size: 0.8rem; color: #86efac; display: block;">৩৬ মাস নিয়মিত নতুন ফিচার আপডেট + ভিআইপি প্রায়োরিটি</span>
              </div>
            </label>
          </div>
        </fieldset>
      </div>

      <!-- 5. Google Pro Price Block & Highlights -->
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

      <form class="purchase" method="post" action="/purchase.php" id="purchaseForm" enctype="multipart/form-data">
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

        <!-- Payment Information & Proof Section -->
        <div class="payment-method-section" style="margin-top: 1.75rem; background: rgba(15, 23, 42, 0.85); border: 1.5px solid #0284c7; border-radius: var(--radius-lg); padding: 1.5rem; box-shadow: 0 4px 25px rgba(2, 132, 199, 0.2);">
          <div style="display:flex; align-items:center; gap:8px; margin-bottom: 0.75rem;">
            <span style="font-size:1.4rem;">💳</span>
            <h3 style="color:#38bdf8; font-size:1.2rem; margin:0; font-weight:700;">পেমেন্ট মেথড ও লেনদেন নির্দেশিকা</h3>
          </div>
          
          <p style="color:#cbd5e1; font-size:0.92rem; line-height:1.6; margin-bottom: 1.25rem;">
            নিচের যেকোনো একটি অনুমোদিত নম্বরে <strong>ক্যাশ আউট (Cash Out)</strong> করে পেমেন্ট সম্পন্ন করুন। নম্বর কপি করতে বাটনে ক্লিক করুন:
          </p>

          <!-- Interactive Payment Cards Grid -->
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.85rem; margin-bottom: 1.5rem;">
            <!-- bKash Agent -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #e11d48; border-radius: var(--radius-md); padding: 1rem; position: relative;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #fda4af; font-size: 0.95rem;">বিকাশ এজেন্ট</strong>
                <span style="background: #e11d48; color: #fff; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">ক্যাশ আউট</span>
              </div>
              <div style="font-family: monospace; font-size: 1.2rem; color: #fff; font-weight: 800; letter-spacing: 0.5px; margin: 4px 0 2px;">
                01756160993
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(Zahid Pharmacy)</small>
              <button type="button" class="btn btn-sm copy-btn" onclick="navigator.clipboard.writeText('01756160993'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='নম্বর কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #e11d48; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight:600;">
                নম্বর কপি করুন
              </button>
            </div>

            <!-- Nagad Agent -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #ea580c; border-radius: var(--radius-md); padding: 1rem; position: relative;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #fdba74; font-size: 0.95rem;">নগদ এজেন্ট</strong>
                <span style="background: #ea580c; color: #fff; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">ক্যাশ আউট</span>
              </div>
              <div style="font-family: monospace; font-size: 1.2rem; color: #fff; font-weight: 800; letter-spacing: 0.5px; margin: 4px 0 2px;">
                01611-824811
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(Simi Drug House)</small>
              <button type="button" class="btn btn-sm copy-btn" onclick="navigator.clipboard.writeText('01611824811'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='নম্বর কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #ea580c; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight:600;">
                নম্বর কপি করুন
              </button>
            </div>

            <!-- Rocket Agent -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #8b5cf6; border-radius: var(--radius-md); padding: 1rem; position: relative;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #c4b5fd; font-size: 0.95rem;">রকেট এজেন্ট</strong>
                <span style="background: #8b5cf6; color: #fff; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">ক্যাশ আউট</span>
              </div>
              <div style="font-family: monospace; font-size: 1.2rem; color: #fff; font-weight: 800; letter-spacing: 0.5px; margin: 4px 0 2px;">
                01756160993-5
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(এজেন্ট ক্যাশ আউট)</small>
              <button type="button" class="btn btn-sm copy-btn" onclick="navigator.clipboard.writeText('017561609935'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='নম্বর কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #8b5cf6; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight:600;">
                নম্বর কপি করুন
              </button>
            </div>

            <!-- Binance Pay / USDT -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #f59e0b; border-radius: var(--radius-md); padding: 1rem; position: relative;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #fde68a; font-size: 0.95rem;">Binance Pay</strong>
                <span style="background: #f59e0b; color: #000; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">USDT</span>
              </div>
              <div style="font-family: monospace; font-size: 1.1rem; color: #fff; font-weight: 800; letter-spacing: 0.5px; margin: 4px 0 2px;">
                ChatEarly Ai
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(Binance Pay ID / QR)</small>
              <button type="button" class="btn btn-sm copy-btn" onclick="navigator.clipboard.writeText('ChatEarly Ai'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='আইডি কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #f59e0b; color: #000; font-weight:700; border: none; border-radius: 6px; cursor: pointer;">
                আইডি কপি করুন
              </button>
            </div>
          </div>

          <!-- Payment Input Fields: Method, Sender Digits, TrxID, and Screenshot Upload -->
          <div style="background: rgba(15, 23, 42, 0.95); border: 1px solid #334155; border-radius: var(--radius-md); padding: 1.25rem;">
            <div style="margin-bottom: 1rem;">
              <label style="display: block; color: #cbd5e1; font-size: 0.88rem; font-weight: 600; margin-bottom: 0.4rem;">
                পেমেন্ট মেথড নির্বাচন করুন:
              </label>
              <div style="display: flex; flex-wrap: wrap; gap: 0.85rem;">
                <label style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px; color: #fff; font-size: 0.9rem;">
                  <input type="radio" name="payment_method" value="bkash" checked> বিকাশ (bKash)
                </label>
                <label style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px; color: #fff; font-size: 0.9rem;">
                  <input type="radio" name="payment_method" value="nagad"> নগদ (Nagad)
                </label>
                <label style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px; color: #fff; font-size: 0.9rem;">
                  <input type="radio" name="payment_method" value="rocket"> রকেট (Rocket)
                </label>
                <label style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px; color: #fff; font-size: 0.9rem;">
                  <input type="radio" name="payment_method" value="binance"> Binance Pay
                </label>
                <label style="cursor: pointer; display: inline-flex; align-items: center; gap: 6px; color: #fff; font-size: 0.9rem;">
                  <input type="radio" name="payment_method" value="bank"> ব্যাংক (Bank)
                </label>
              </div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1rem;">
              <div>
                <label style="display: block; color: #cbd5e1; font-size: 0.85rem; margin-bottom: 0.35rem;">
                  প্রেরক নম্বরের শেষ ৩-৪ ডিজিট <span style="color:#94a3b8; font-weight:normal;">(যদি পেমেন্ট করে থাকেন)</span>:
                </label>
                <input type="text" name="sender_last_digits" placeholder="যেমন: 0998" maxlength="10" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #475569;">
              </div>
              <div>
                <label style="display: block; color: #cbd5e1; font-size: 0.85rem; margin-bottom: 0.35rem;">
                  ট্রানজেকশন আইডি (TrxID) <span style="color:#94a3b8; font-weight:normal;">(যদি পেমেন্ট করে থাকেন)</span>:
                </label>
                <input type="text" name="txn_id" id="checkoutTxnId" placeholder="যেমন: BL92KA871X" maxlength="24" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #475569; text-transform:uppercase; font-family:monospace; font-weight:600;" oninput="this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, '');">
              </div>
            </div>

            <!-- Payment Screenshot Upload -->
            <div style="margin-top: 1rem;">
              <label style="display: block; color: #cbd5e1; font-size: 0.88rem; font-weight: 600; margin-bottom: 0.35rem;">
                📸 পেমেন্টের স্ক্রিনশট আপলোড করুন <span style="color:#94a3b8; font-weight:normal;">(ছবি / মানি রসিদ, ঐচ্ছিক কিন্তু দ্রুত অ্যাক্টিভেশনে সহায়ক)</span>:
              </label>
              <div style="border: 2px dashed #0284c7; border-radius: 8px; padding: 1.25rem; text-align: center; background: rgba(30, 41, 59, 0.5); cursor: pointer; transition: all 0.2s;" onclick="document.getElementById('paymentScreenshotInput').click();">
                <input type="file" id="paymentScreenshotInput" name="payment_screenshot" accept="image/*" style="display: none;" onchange="previewScreenshot(this)">
                <div id="uploadPrompt">
                  <span style="font-size: 2rem;">📎</span>
                  <p style="margin: 6px 0 2px; color: #38bdf8; font-size: 0.95rem; font-weight: 600;">পেমেন্টের স্ক্রিনশট সিলেক্ট করতে এখানে ক্লিক করুন</p>
                  <small style="color: #94a3b8; font-size: 0.78rem;">JPG, PNG, WEBP ফরম্যাট (সর্বোচ্চ 10MB)</small>
                </div>
                <div id="screenshotPreviewWrap" style="display: none; margin-top: 8px;">
                  <img id="screenshotPreviewImg" src="" alt="Screenshot Preview" style="max-height: 160px; max-width:100%; border-radius: 6px; border: 1.5px solid #38bdf8; box-shadow: 0 4px 12px rgba(0,0,0,0.4);">
                  <p id="screenshotFileName" style="color: #34d399; font-size: 0.85rem; margin-top: 6px; font-weight: 600;"></p>
                </div>
              </div>
            </div>

            <div style="margin-top: 1rem; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 0.75rem 1rem; font-size: 0.85rem; color: #93c5fd; display: flex; align-items: center; gap: 8px;">
              <span style="font-size:1.1rem;">💡</span>
              <span>আপনি চাইলে এখনই পেমেন্ট করে TrxID বা স্ক্রিনশট দিয়ে একবারে অর্ডার সাবমিট করতে পারেন, অথবা এখনই ফর্ম সাবমিট করে পরবর্তী পেজেও পেমেন্ট সম্পন্ন করতে পারবেন।</span>
            </div>
          </div>
        </div>

        <div class="total-line" style="margin-top:1.5rem;">
          <span data-i18n="total_due">সর্বমোট পরিশোধযোগ্য</span>
          <strong id="totalDisplay">৳<?= (int) $initialPrice ?></strong>
        </div>

        <button class="btn" type="submit" style="width:100%; font-size:1.15rem; padding:1.1rem; background:linear-gradient(135deg, #0284c7, #2563eb); font-weight:700; border-radius:10px;" data-i18n="pay_now">অর্ডার কনফার্ম করুন</button>
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
      const tabWaMarketingBtn = document.getElementById('tabWaMarketingBtn');
      const tabGoogleProBtn = document.getElementById('tabGoogleProBtn');

      const videoStudioBlock = document.getElementById('videoStudioBlock');
      const fbBusinessBlock = document.getElementById('fbBusinessBlock');
      const profilePageBlock = document.getElementById('profilePageBlock');
      const waMarketingBlock = document.getElementById('waMarketingBlock');
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
        let pName = 'AutoMovie Pro - Social Media Content Automation Engine';

        if (prod === 'wa_marketing') {
          const choice = document.querySelector('input[name="wa_plan_choice"]:checked');
          const years = choice ? parseInt(choice.value, 10) : 1;
          if (years === 3) {
            base = 1999;
            planDurationField.value = '36';
            pName = 'WAManager Pro — WhatsApp Marketing & CRM Suite (৩ বছর সাবস্ক্রিপশন)';
          } else {
            base = 999;
            planDurationField.value = '12';
            pName = 'WAManager Pro — WhatsApp Marketing & CRM Suite (১ বছর সাবস্ক্রিপশন)';
          }
        } else if (prod === 'fb_business') {
          base = 2999;
          pName = 'AutoMovie Pro - FB Business Manager & Ad Automation Engine';
        } else if (prod === 'profile_page') {
          base = 1999;
          pName = 'AutoMovie Pro - FB Profile & Page Post Automation Engine';
        } else if (prod === 'google_pro') {
          const choice = document.querySelector('input[name="google_plan_choice"]:checked');
          const months = choice ? parseInt(choice.value, 10) : 1;
          if (months === 24) base = 1999;
          else if (months === 18) base = 1299;
          else if (months === 12) base = 999;
          else base = 120;
          planDurationField.value = months;
          pName = `Special Gemini Pro API (${months} Months)`;
        } else {
          // video_studio: calculate multi-language add-on
          base = 3999;
          pName = 'AutoMovie Pro - Social Media Content Automation Engine';
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
        [tabVideoStudioBtn, tabFbBusinessBtn, tabProfilePageBtn, tabWaMarketingBtn, tabGoogleProBtn].forEach(b => b?.classList.add('btn-ghost'));
        // Hide all blocks
        [videoStudioBlock, fbBusinessBlock, profilePageBlock, waMarketingBlock, googleProBlock].forEach(b => { if (b) b.style.display = 'none'; });

        if (mode === 'wa_marketing') {
          tabWaMarketingBtn?.classList.remove('btn-ghost');
          if (waMarketingBlock) waMarketingBlock.style.display = 'block';
          if (softwareLangPickers) softwareLangPickers.style.display = 'none';
        } else if (mode === 'google_pro') {
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
      tabWaMarketingBtn?.addEventListener('click', () => setProduct('wa_marketing'));
      tabGoogleProBtn?.addEventListener('click', () => setProduct('google_pro'));

      document.querySelectorAll('input[name="wa_plan_choice"]').forEach(r => {
        r.addEventListener('change', () => {
          if (productTypeField.value === 'wa_marketing') {
            calculateTotal();
          }
        });
      });

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

    function previewScreenshot(input) {
      if (input.files && input.files[0]) {
        const file = input.files[0];
        const reader = new FileReader();
        reader.onload = function(e) {
          const promptEl = document.getElementById('uploadPrompt');
          const wrap = document.getElementById('screenshotPreviewWrap');
          const img = document.getElementById('screenshotPreviewImg');
          const nameEl = document.getElementById('screenshotFileName');
          if (promptEl) promptEl.style.display = 'none';
          if (img) img.src = e.target.result;
          if (nameEl) nameEl.textContent = '✓ ' + file.name + ' (' + (file.size / 1024).toFixed(0) + ' KB)';
          if (wrap) wrap.style.display = 'block';
        };
        reader.readAsDataURL(file);
      }
    }
  </script>

  <!-- Floating AI Sales Consultant Widget (Defaulting to Nirob) -->
  <div id="ampChat" class="amp-chat" aria-live="polite">
    <!-- 1. Sleek Floating Launcher Button -->
    <button type="button" class="amp-chat-launcher" id="ampChatLauncher" aria-label="Open Live Support">
      <div class="launcher-avatar-wrap">
        <img src="/assets/img/agents/nirob.png" id="ampLauncherAvatar" alt="Support Agent">
        <span class="online-dot"></span>
      </div>
      <div class="launcher-label">
        <span class="launcher-title">লাইভ সাপোর্ট</span>
        <span class="launcher-sub">অনলাইন • কথা বলুন</span>
      </div>
      <span class="launcher-close-icon" id="ampLauncherCloseIcon" style="display:none;">✕</span>
    </button>

    <!-- 2. Choice Card (WhatsApp vs Live Agent) -->
    <div class="amp-choice-card is-hidden" id="ampChoiceCard" style="display: none;">
      <div class="choice-header">
        <div class="choice-agent-preview">
          <div class="choice-avatar-wrap">
            <img src="/assets/img/agents/nirob.png" id="ampChoiceAvatar" alt="Support Agent">
            <span class="online-dot" style="width:7px; height:7px;"></span>
          </div>
          <div>
            <strong>AutoMovie Pro সাপোর্ট টিম</strong>
            <span class="choice-status-text">🟢 সক্রিয় • ১ মিনিটে রিপ্লাই</span>
          </div>
        </div>
        <button type="button" class="choice-close-btn" id="ampChoiceClose" aria-label="Close">✕</button>
      </div>
      <div class="choice-body">
        <p class="choice-lead">আসসালামু আলাইকুম! আপনার পছন্দের সাপোর্ট মাধ্যম বেছে নিন:</p>
        
        <!-- Option 1: Live Agent -->
        <button type="button" class="choice-option-btn primary-live" id="ampStartLiveAgentBtn">
          <div class="choice-icon-wrap live-icon">💬</div>
          <div class="choice-text">
            <strong>একজন লাইভ এজেন্টের সাথে কথা বলুন</strong>
            <span>ওয়েবসাইটে সরাসরি তাৎক্ষণিক চ্যাট শুরু করুন</span>
          </div>
          <span class="choice-badge">অনলাইন</span>
        </button>

        <!-- Option 2: Direct WhatsApp -->
        <a href="<?= e($waLink) ?>" target="_blank" rel="noopener" class="choice-option-btn whatsapp-link" id="ampDirectWaBtn">
          <div class="choice-icon-wrap wa-icon">📱</div>
          <div class="choice-text">
            <strong>WhatsApp-এ সরাসরি যোগাযোগ করুন</strong>
            <span>আমাদের অফিশিয়াল WhatsApp ইনবক্সে মেসেজ পাঠান</span>
          </div>
          <span class="choice-arrow">➔</span>
        </a>
      </div>
    </div>

    <!-- 3. Active Chat Panel -->
    <div class="amp-chat-panel is-hidden" id="ampChatPanel" style="display: none;">
      <header class="amp-chat-head">
        <div class="amp-chat-agent-info">
          <div class="amp-chat-avatar" id="ampChatAvatar">
            <img src="/assets/img/agents/nirob.png" id="ampChatAvatarImg" alt="Support Agent">
          </div>
          <div class="amp-chat-name">
            <strong id="ampChatAgentName">নীরব (Nirob)</strong>
            <span><span class="online-dot" style="width:6px; height:6px;"></span> <span id="ampChatAgentStatus">টেকনিক্যাল ও প্রোডাক্ট স্পেশালিস্ট</span></span>
          </div>
        </div>
        <div class="amp-chat-head-actions">
          <button type="button" class="amp-chat-sound" id="ampChatSoundToggle" title="সাউন্ড মিউট / আনমিউট">🔊</button>
          <button type="button" class="amp-chat-reset" id="ampChatReset" title="নতুন চ্যাট শুরু করুন">🔄</button>
          <button type="button" class="amp-chat-back" id="ampChatBack" title="মেনুতে ফিরুন">↩</button>
          <button type="button" class="amp-chat-close" id="ampChatClose" aria-label="Close">✕</button>
        </div>
      </header>

      <!-- Connecting Overlay -->
      <div class="amp-connecting-overlay" id="ampConnectingOverlay" style="display: none;">
        <div class="connecting-spinner-wrap">
          <div class="connecting-pulse-ring"></div>
          <div class="connecting-avatar-wrap">
            <img src="/assets/img/agents/nirob.png" id="ampConnectingAvatar" class="connecting-avatar" alt="Agent">
          </div>
        </div>
        <div class="connecting-status-title" id="ampConnectingTitle">লাইভ কনসালট্যান্ট নির্ধারণ হচ্ছে…</div>
        <div class="connecting-status-desc" id="ampConnectingDesc">আপনার চ্যাটের জন্য একজন সাপোর্ট এজেন্ট যুক্ত করা হচ্ছে</div>
        <div class="connecting-progress-bar">
          <div class="connecting-progress-fill" id="ampConnectingProgress"></div>
        </div>
      </div>

      <!-- Chat Log -->
      <div class="amp-chat-log" id="ampChatLog"></div>

      <!-- Chat Form -->
      <form class="amp-chat-form" id="ampChatForm">
        <input type="text" id="ampChatInput" placeholder="প্যাকেজ, ফিচার বা অফার নিয়ে প্রশ্ন করুন…" maxlength="800" autocomplete="off">
        <button type="submit">পাঠান</button>
      </form>

      <!-- Bottom WhatsApp quicklink -->
      <a class="amp-chat-wa" id="ampChatWa" href="<?= e($waLink) ?>" target="_blank" rel="noopener">📱 সরাসরি WhatsApp-এ কথা বলতে এখানে ক্লিক করুন</a>
    </div>
  </div>

  <script src="/assets/js/i18n-site.js?v=<?= filemtime(__DIR__ . '/assets/js/i18n-site.js') ?>"></script>
  <script src="/assets/js/site.js?v=<?= filemtime(__DIR__ . '/assets/js/site.js') ?>"></script>
  <script src="/assets/js/marketing-chat.js?v=<?= filemtime(__DIR__ . '/assets/js/marketing-chat.js') ?>"></script>
</body>
</html>
