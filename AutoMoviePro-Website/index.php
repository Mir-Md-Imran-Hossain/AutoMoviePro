<?php
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';
require_once __DIR__ . '/includes/reviews_data.php';

$uiLang = strtolower(substr((string) ($_GET['lang'] ?? $_COOKIE['amp_ui_lang'] ?? 'bn'), 0, 2));
if (!in_array($uiLang, amp_cms_langs(), true)) {
    $uiLang = 'bn';
}

$brand = setting_i18n($pdo, 'hero_brand', $uiLang, setting($pdo, 'hero_brand', 'AutoMovie Pro')) ?? 'AutoMovie Pro';
$price = (float) setting($pdo, 'price_amount', '2998');
$addonPrice = (float) setting($pdo, 'language_addon_price', '499');
$how = setting_i18n($pdo, 'how_it_works', $uiLang, '') ?? '';
$faq = setting_i18n($pdo, 'faq_text', $uiLang, '') ?? '';
$metaTitle = setting_i18n($pdo, 'meta_title', $uiLang, 'AutoMovie Pro — Industrial Multi-Language AI Video Automation') ?? 'AutoMovie Pro';
$metaDesc = setting_i18n(
    $pdo,
    'meta_description',
    $uiLang,
    'AutoMovie Pro: Industrial AI Video Studio. Automatically create and schedule videos to 6 YouTube + 6 Facebook + 6 TikTok destinations in 6 languages. Lifetime License from ৳2998.'
) ?? '';
$siteUrl = rtrim((string) ($config['site_url'] ?? ''), '/');
$waLink = amp_whatsapp_sales_link(
    "Hi! I want to order AutoMovie Pro (৳{$price} for Lifetime 2 languages). Please guide me."
);
$catalog = amp_features_catalog();
$langCatalog = amp_lang_catalog();

$featuresPayload = [];
foreach ($catalog as $feat) {
    $row = ['id' => $feat['id'], 'image' => $feat['image'] ?? '', 'langs' => []];
    foreach (amp_cms_langs() as $lc) {
        $f = amp_feature_for_lang($feat, $lc);
        $row['langs'][$lc] = ['title' => $f['title'], 'detail' => $f['detail']];
    }
    $featuresPayload[] = $row;
}

$broadcastActive = setting($pdo, 'broadcast_active', '0') === '1';
$broadcastText = setting($pdo, 'broadcast_text', '');
$broadcastType = setting($pdo, 'broadcast_type', 'offer');
$broadcastLink = setting($pdo, 'broadcast_link', '');
$broadcastLinkText = setting($pdo, 'broadcast_link_text', '');
?>
<!DOCTYPE html>
<html lang="<?= e($uiLang) ?>"<?= $uiLang === 'ur' ? ' dir="rtl"' : '' ?>>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= e($metaTitle) ?></title>
  <meta name="description" content="<?= e($metaDesc) ?>">
  <meta property="og:title" content="<?= e($metaTitle) ?>">
  <meta property="og:description" content="<?= e($metaDesc) ?>">
  <meta property="og:type" content="website">
  <meta property="og:url" content="<?= e($siteUrl) ?>/">
  <meta property="og:image" content="<?= e($siteUrl) ?>/assets/img/cover.png">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="<?= e($siteUrl) ?>/?lang=<?= e($uiLang) ?>">
  <?php foreach (amp_cms_langs() as $hl): ?>
  <link rel="alternate" hreflang="<?= e($hl) ?>" href="<?= e($siteUrl) ?>/?lang=<?= e($hl) ?>">
  <?php endforeach; ?>
  <link rel="alternate" hreflang="x-default" href="<?= e($siteUrl) ?>/?lang=en">
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <link rel="stylesheet" href="/assets/css/site.css?v=<?= filemtime(__DIR__ . '/assets/css/site.css') ?>">
  <script type="application/ld+json">
  <?= json_encode([
      '@context' => 'https://schema.org',
      '@type' => 'SoftwareApplication',
      'name' => $brand,
      'applicationCategory' => 'MultimediaApplication',
      'operatingSystem' => 'Windows',
      'offers' => [
          '@type' => 'Offer',
          'price' => (string) $price,
          'priceCurrency' => 'BDT',
          'description' => 'Lifetime core license includes English + 1 personal language',
      ],
      'description' => $metaDesc,
      'featureList' => array_map(
          static fn ($f) => amp_feature_for_lang($f, 'en')['title'],
          $catalog
      ),
  ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) ?>
  </script>
  <script>
    window.AMP_SITE = {
      price: <?= json_encode($price) ?>,
      addon: <?= json_encode($addonPrice) ?>,
      waLink: <?= json_encode($waLink) ?>,
      langs: <?= json_encode($langCatalog, JSON_UNESCAPED_UNICODE) ?>,
      features: <?= json_encode($featuresPayload, JSON_UNESCAPED_UNICODE) ?>,
      uiLang: <?= json_encode($uiLang) ?>
    };
  </script>
</head>
<body>
  <?php if ($broadcastActive && !empty($broadcastText)): 
    $bBg = match ($broadcastType) {
        'offer' => 'linear-gradient(90deg, #064e3b, #047857)',
        'warning' => 'linear-gradient(90deg, #78350f, #d97706)',
        'alert' => 'linear-gradient(90deg, #881337, #e11d48)',
        default => 'linear-gradient(90deg, #0c4a6e, #0284c7)',
    };
    $bIcon = match ($broadcastType) {
        'offer' => '⚡',
        'warning' => '⚠️',
        'alert' => '🚨',
        default => '📢',
    };
  ?>
  <aside class="amp-broadcast-banner" style="background:<?= $bBg ?>; color:#ffffff; padding:9px 16px; font-size:0.88rem; font-weight:600; text-align:center; display:flex; align-items:center; justify-content:center; gap:12px; z-index:99; position:relative; box-shadow:0 2px 8px rgba(0,0,0,0.3);">
    <span><?= $bIcon ?> <?= e($broadcastText) ?></span>
    <?php if ($broadcastLink && $broadcastLinkText): ?>
      <a href="<?= e($broadcastLink) ?>" style="background:#ffffff; color:#0f172a; padding:3px 12px; border-radius:4px; font-size:0.78rem; font-weight:700; text-decoration:none; white-space:nowrap; margin-left:6px; transition:transform 0.2s ease;">
        <?= e($broadcastLinkText) ?> →
      </a>
    <?php endif; ?>
  </aside>
  <?php endif; ?>

  <!-- Header Navigation -->
  <header class="site-header">
    <a class="logo-link" href="/?lang=<?= e($uiLang) ?>">
      <img class="logo-img" src="/assets/img/logo.png?v=<?= filemtime(__DIR__ . '/assets/img/logo.png') ?>" alt="<?= e($brand) ?>" width="42" height="42">
      <div class="logo"><?= e($brand) ?> <span>SAAS</span></div>
    </a>
    <div class="header-actions">
       <div class="lang-selector-pill">
          <span class="lang-globe-icon">🌐</span>
          <select id="siteLangSelect" class="lang-dropdown-select" aria-label="Choose Language" onchange="ampSwitchLang(this.value)">
            <option value="bn" <?= $uiLang === 'bn' ? 'selected' : '' ?>>বাংলা (BN)</option>
            <option value="en" <?= $uiLang === 'en' ? 'selected' : '' ?>>English (EN)</option>
            <option value="hi" <?= $uiLang === 'hi' ? 'selected' : '' ?>>हिन्दी (HI)</option>
            <option value="ur" <?= $uiLang === 'ur' ? 'selected' : '' ?>>اردو (UR)</option>
            <option value="ta" <?= $uiLang === 'ta' ? 'selected' : '' ?>>தமிழ் (TA)</option>
            <option value="ml" <?= $uiLang === 'ml' ? 'selected' : '' ?>>മലയാളം (ML)</option>
          </select>
       </div>
       <a class="btn btn-sm btn-wa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp</a>
      <a class="btn btn-sm" href="#buy" data-i18n="header_buy_btn">এখনই কিনুন</a>
    </div>
  </header>

  <!-- Grand Hero Section -->
  <section class="hero">
    <div class="hero-grid">
      <div class="hero-content">
        <div class="hero-badge-pill">
          <span data-i18n="hero_badge">🚀 নেক্সট-জেন এআই ভিডিও অটোমেশন v4.2</span>
        </div>
        <h1 class="hero-brand">
          <?= e($brand) ?> <em>STUDIO</em>
        </h1>
        <p class="hero-lead-text" data-i18n="hero_desc">
          কন্টেন্ট ক্রিয়েট করে ফেসবুক, ইউটিউব এবং টিকটক থেকে প্যাসিভ ইনকাম করার সুবর্ণ সুযোগ। AutoMovie Pro-তে একবার নিশ সিলেক্ট করুন — আমাদের প্রো অ্যালগরিদম স্বয়ংক্রিয়ভাবে ভাইরাল স্ক্রিপ্ট, সিনেমাটিক ভিজ্যুয়াল, প্রফেশনাল ভয়েসওভার ও হার্ফবাজ সাবটাইটেল তৈরি করে অটোমেটিক নিজেই ভিডিও তৈরি করবে। তারপরে আলাদা আলাদা ভাষায় সেই ভিডিওকে ট্রান্সলেট করবে। এবং সবশেষে তারপর সেই ভিডিও আলাদা আলাদা ভাষাভিত্তিক ইউটিউব, ফেসবুক ও টিকটকে নিজেই আপলোড করবে, কমেন্ট ও মেসেজের অ্যানসার করবে, ভিডিও শেয়ার করবে এবং একজন প্রফেশনাল সোশ্যাল মিডিয়া ইঞ্জিনিয়ার হিসেবে আপনার অ্যাকাউন্টগুলোর দেখাশোনা করবে।
        </p>
        <div class="cta-row cta-row-single-line">
          <a class="btn btn-hero" href="#buy" data-i18n="buy_now">এখনই লাইসেন্স নিন</a>
          <a class="btn btn-hero btn-ghost" href="#demo-video" data-i18n="see_demo_video">🎬 লাইভ ডেমো ভিডিও দেখুন</a>
          <a class="btn btn-hero btn-ghost" href="#features" data-i18n="see_features">সব ফিচার এক্সপ্লোর করুন</a>
          <a class="btn btn-hero btn-wa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp পরামর্শ</a>
        </div>
        <div class="hero-social-proof">
          <div class="avatar-stack">
            <span>⭐</span>
            <span>🎬</span>
            <span>🚀</span>
          </div>
          <div class="proof-text">
            <span data-i18n="active_creators_badge">১,২৫০+ অ্যাক্টিভ কনটেন্ট ক্রিয়েটর</span> • <strong>৪.৯/৫ রেটিং</strong>
          </div>
        </div>
      </div>

      <!-- Hero Mockup Display Frame -->
      <div class="hero-mockup-wrapper">
        <div class="hero-mockup-frame">
          <img class="hero-mockup-img" src="/assets/img/hero-studio.png" alt="AutoMovie Pro AI Video Studio Mockup" width="1280" height="720">
          <div class="hero-telemetry-chip chip-top">
            <span class="online-dot" style="width:8px; height:8px;"></span>
            <span data-i18n="studio_badge_live">🔴 লাইভ স্টুডিও ইঞ্জিন সক্রিয়</span>
          </div>
          <div class="hero-telemetry-chip chip-bottom">
            <span>⚡</span>
            <span data-i18n="studio_badge_channels">⚡ ১৮টি মাল্টি-চ্যানেল অটো স্ট্রিম</span>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Live Walkthrough & Demo Video Section -->
  <section id="demo-video" class="reveal demo-video-section">
    <div class="demo-video-container">
      <div class="section-head">
        <span class="video-pill">🎬 অফিসিয়াল ভিডিও ওয়াকথ্রু ও লাইভ ডেমো</span>
        <h2 data-i18n="video_section_title">AutoMovie Pro সফটওয়্যার কীভাবে কাজ করে — সরাসরি দেখুন</h2>
        <p class="lead" data-i18n="video_section_lead">স্ক্রিপ্ট তৈরি থেকে শুরু করে ভয়েসওভার, সিনেমাটিক সিন, সাবটাইটেল কম্পোজিশন এবং স্বয়ংক্রিয় ১৮টি চ্যানেলে আপলোড — সফটওয়্যারটির সকল কার্যক্রমের পুঙ্খানুপুঙ্খ বিবরণ সরাসরি এই ভিডিওতে দেখুন।</p>
      </div>

      <!-- Modern Cinematic Video Player Box -->
      <div class="video-player-wrapper">
        <div class="video-player-frame">
          <video id="ampWalkthroughVideo" controls playsinline preload="metadata" poster="/assets/img/hero-studio.png">
            <source src="/assets/video/automovie_pro_walkthrough.mp4" type="video/mp4">
            আপনার ব্রাউজার ভিডিওটি প্লে করতে পারছে না।
          </video>
        </div>

        <!-- Video Highlights Bar -->
        <div class="video-highlights-grid">
          <div class="video-highlight-card">
            <div class="vh-icon">⚡</div>
            <div class="vh-text">
              <strong>১-ক্লিকে ফুল ভিডিও তৈরি</strong>
              <span>স্ক্রিপ্ট, ভয়েস, ব্যাকগ্রাউন্ড মিউজিক ও সিনেমাটিক সিন স্বয়ংক্রিয়ভাবে তৈরি হয়</span>
            </div>
          </div>
          <div class="video-highlight-card">
            <div class="vh-icon">🌐</div>
            <div class="vh-text">
              <strong>বহুভাষিক অটো-ট্রান্সলেশন</strong>
              <span>একটি ভিডিও ৬টিরও বেশি আন্তর্জাতিক ভাষায় নিখুঁত লোকাল টিউন সহ রূপান্তর</span>
            </div>
          </div>
          <div class="video-highlight-card">
            <div class="vh-icon">📱</div>
            <div class="vh-text">
              <strong>১৮টি চ্যানেলে অটো-পোস্টিং</strong>
              <span>ইউটিউব, ফেসবুক ও টিকটকে শিডিউল অনুযায়ী স্বয়ংক্রিয় আপলোড ও অ্যানসার</span>
            </div>
          </div>
          <div class="video-highlight-card">
            <div class="vh-icon">💻</div>
            <div class="vh-text">
              <strong>১০০% লোকাল পিসি সিকিউরিটি</strong>
              <span>কোনো ক্লাউড সাবস্ক্রিপশন নেই, লাইফটাইম লাইসেন্স আপনার নিজের কম্পিউটারে</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Income Matrix / Pitch Section -->
  <section id="income" class="reveal pitch-strip">
    <div class="section-head">
      <h2 data-i18n="income_title">প্রতিটা ভিডিও আলাদা আলাদা ভাষায় অটোমেটিক ট্রান্সলেশন ও একটি ভিডিও দিয়েই আলাদা আলাদা ভাষার প্ল্যাটফর্ম থেকে অধিক প্যাসিভ ইনকামের সুবিধা।</h2>
      <p class="lead" data-i18n="income_lead">আমাদের বর্তমানে ৬টিরও বেশি ভাষা সেটআপ করা আছে এবং প্রতিনিয়ত নতুন নতুন ভাষা যুক্ত হচ্ছে। প্রতিটি ভাষায় লোকালাইজেশনের মাধ্যমে সেই ভাষার লোকাল টিউন, ভাবগাম্ভীর্য ও সংস্কৃতি অ্যানালাইসিসের মাধ্যমে ভিডিওটি অত্যন্ত নিখুঁতভাবে ট্রান্সলেশন হয়। তাই একটি ভিডিও দিয়েই আপনি আলাদা আলাদা ভাষার জন্য আলাদা আলাদা ইউটিউব চ্যানেল, ফেসবুক পেজ এবং টিকটক একাউন্ট ক্রিয়েট করে প্রত্যেক একাউন্ট থেকে আলাদা আলাদা প্যাসিভ ইনকাম করতে পারবেন।</p>
    </div>
    <div class="pitch-grid pitch-grid-3">
      <div class="pitch-card">
        <div class="pitch-card-icon">📺</div>
        <h3 data-i18n="pitch_yt">YouTube মাল্টি-চ্যানেল নেটওয়ার্ক</h3>
        <p data-i18n="pitch_yt_desc">আলাদা আলাদা ভাষায় ইউটিউব চ্যানেল ক্রিয়েট করে একই ভিডিও একাধিক ভাষায় আপলোড করুন এবং গ্লোবাল প্রিমিয়াম হাই-সিপিএম অ্যাড রেভিনিউ আয় করুন।</p>
      </div>
      <div class="pitch-card">
        <div class="pitch-card-icon">📱</div>
        <h3 data-i18n="pitch_fb">Facebook মাল্টি-পেজ ও রিলস স্ট্রিম</h3>
        <p data-i18n="pitch_fb_desc">ফেসবুক রিলস ও পেজ পোস্ট একযোগে অটো-পাইলটে পরিচালনা করে দেশীয় ও আন্তর্জাতিক ফলোয়ার বাড়িয়ে ইন-স্ট্রিম অ্যাড মনিটাইজেশন আর্ন করুন।</p>
      </div>
      <div class="pitch-card">
        <div class="pitch-card-icon">🎵</div>
        <h3 data-i18n="pitch_tt">TikTok গ্লোবাল ভাইরাল ডেস্টিনেশন</h3>
        <p data-i18n="pitch_tt_desc">টিকটক ক্রিয়েটর রিওয়ার্ডস প্রোগ্রামের জন্য হাইপার-এনগেজিং শর্ট ভিডিও দিয়ে বিশ্বজুড়ে ভাইরাল হয়ে সরাসরি প্যাসিভ ডলার ইনকাম করুন।</p>
      </div>
    </div>
  </section>

  <!-- Dedicated Automation Engines Showcase Section -->
  <section id="engines" class="reveal engines-showcase-section">
    <div class="section-head">
      <span class="gpro-pill" style="background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; margin-bottom: 0.85rem;">
        ⚡ পাওয়ারফুল তিনটি অটোনমাস ইঞ্জিন
      </span>
      <h2 data-i18n="engines_title">Automovie Pro এর অটোমেশন ইঞ্জিন সমূহ</h2>
      <p class="lead" data-i18n="engines_lead">আপনার প্রয়োজন অনুযায়ী ৩টি ডেডিকেটেড স্বয়ংক্রিয় এআই ইঞ্জিন — যা আপনার সোশ্যাল মিডিয়া, ব্যবসা ও প্রোফাইল পরিচালনা করবে মানুষের কোনো হস্তক্ষেপ ছাড়াই।</p>
    </div>

    <div class="engines-grid">
      <!-- Engine 1 -->
      <div class="engine-display-card engine-card-video">
        <div class="engine-card-top">
          <span class="engine-top-badge badge-cyan">🎬 ফুল কন্টেন্ট পাওয়ারহাউজ</span>
          <div class="engine-pricing-badge">
            <span class="current-price">৳৩,৯৯৯</span>
            <span class="old-price">৳১০,০০০</span>
          </div>
        </div>
        <h3 class="engine-title" data-i18n="engine1_name">Automovie Pro - Social Media Content Automation Engine</h3>
        <p class="engine-desc" data-i18n="engine1_desc">
          ইউটিউব, ফেসবুক ও টিকটকের জন্য সম্পূর্ণ স্বয়ংক্রিয় ভাইরাল ভিডিও তৈরি, ট্রান্সলেশন, শিডিউল আপলোড এবং কমেন্ট রেসপন্স।
        </p>
        <ul class="engine-feature-bullets">
          <li>✓ স্বয়ংক্রিয় ভাইরাল টপিক রিসার্চ ও এআই স্ক্রিপ্ট</li>
          <li>✓ ১০০% স্বাভাবিক মানবিক বাংলা ও বহুভাষিক ভয়েসওভার</li>
          <li>✓ কাইনেটিক মোশন কার্ড ও সিনেমাটিক ভিজ্যুয়াল জেনারেশন</li>
          <li>✓ ৬টি গ্লোবাল ভাষায় স্বয়ংক্রিয় নিখুঁত ট্রান্সলেশন</li>
          <li>✓ YouTube, Facebook ও TikTok-এ অটোমেটিক শিডিউল পাবলিশিং</li>
        </ul>
        <div class="engine-card-actions">
          <button type="button" class="btn btn-ghost btn-engine-details" onclick="window.switchWorkflowTab('engine_social')" data-i18n="engine_see_steps">ফিচার ও ধাপসমূহ দেখুন</button>
          <a href="#buy" class="btn btn-engine-order" onclick="window.selectEngineRadio('video_studio')" data-i18n="engine1_order_btn">অর্ডার করুন (৳৩,৯৯৯)</a>
        </div>
      </div>

      <!-- Engine 2 -->
      <div class="engine-display-card engine-card-business">
        <div class="engine-card-top">
          <span class="engine-top-badge badge-amber">💼 বিজনেস ও সেলস ম্যানেজার</span>
          <div class="engine-pricing-badge">
            <span class="current-price">৳২,৯৯৯</span>
            <span class="old-price">৳৮,৫০০</span>
          </div>
        </div>
        <h3 class="engine-title" data-i18n="engine2_name">Automovie Pro - FB Business Manager & Ad Automation Engine</h3>
        <p class="engine-desc" data-i18n="engine2_desc">
          বিজনেস ও প্রডাক্টের হাই-কনভার্টিং সেলস ব্যানার, কাইনেটিক বিজ্ঞাপন ভিডিও তৈরি, গ্রুপে অর্গানিক শেয়ার এবং মেসেঞ্জারে ২৪/৭ স্মার্ট সেলস রিপ্লাই।
        </p>
        <ul class="engine-feature-bullets">
          <li>✓ হাই-কনভার্টিং সেলস ব্যানার ও অফার গ্রাফিক্স</li>
          <li>✓ কাইনেটিক মোশন কার্ড সহ ৩০-৭০ সেকেন্ডের বিজ্ঞাপন ভিডিও</li>
          <li>✓ টার্গেটেড ফেসবুক গ্রুপে স্বয়ংক্রিয় অর্গানিক শেয়ারিং</li>
          <li>✓ ২৪/৭ স্মার্ট কাস্টমার ইনকোয়ারি সেলস রেসপন্স</li>
          <li>✓ প্রোডাক্ট ও সার্ভিসের স্পেশাল ক্যাম্পেইন ম্যানেজমেন্ট</li>
        </ul>
        <div class="engine-card-actions">
          <button type="button" class="btn btn-ghost btn-engine-details" onclick="window.switchWorkflowTab('engine_business')" data-i18n="engine_see_steps">ফিচার ও ধাপসমূহ দেখুন</button>
          <a href="#buy" class="btn btn-engine-order btn-amber" onclick="window.selectEngineRadio('fb_business')" data-i18n="engine2_order_btn">অর্ডার করুন (৳২,৯৯৯)</a>
        </div>
      </div>

      <!-- Engine 3 -->
      <div class="engine-display-card engine-card-profile">
        <div class="engine-card-top">
          <span class="engine-top-badge badge-emerald">📱 প্রোফাইল ও পেজ অটো-পাইলট</span>
          <div class="engine-pricing-badge">
            <span class="current-price">৳১,৯৯৯</span>
            <span class="old-price">৳৬,৫০০</span>
          </div>
        </div>
        <h3 class="engine-title" data-i18n="engine3_name">Automovie Pro - FB Profile & Page Post Automation Engine</h3>
        <p class="engine-desc" data-i18n="engine3_desc">
          ব্যক্তিগত ফেসবুক প্রোফাইল ও পেজের জন্য নির্দিষ্ট নিসভিত্তিক কোট ব্যানার ও স্ট্যাটাস পোস্ট রাইটিং, হিউম্যান-লাইক শিডিউলিং এবং প্রাসঙ্গিক গ্রুপে অটো শেয়ারিং।
        </p>
        <ul class="engine-feature-bullets">
          <li>✓ খাঁটি ইসলামিক হাদিস/কোরআন বা অনুপ্রেরণামূলক পোস্ট</li>
          <li>✓ স্বয়ংক্রিয় গোল্ডেন এমবলেম ব্যানার ও ফটো ফ্রেম তৈরি</li>
          <li>✓ ফেসবুক প্রোফাইল ও পেজে হিউম্যান-লাইক শিডিউল পোস্ট</li>
          <li>✓ ইসলামিক ও শিক্ষণীয় গ্রুপে নিরাপদ অর্গানিক শেয়ারিং</li>
          <li>✓ ফ্রেন্ড ও ফলোয়ার এনগেজমেন্ট অটোমেশন</li>
        </ul>
        <div class="engine-card-actions">
          <button type="button" class="btn btn-ghost btn-engine-details" onclick="window.switchWorkflowTab('engine_profile')" data-i18n="engine_see_steps">ফিচার ও ধাপসমূহ দেখুন</button>
          <a href="#buy" class="btn btn-engine-order btn-emerald" onclick="window.selectEngineRadio('profile_page')" data-i18n="engine3_order_btn">অর্ডার করুন (৳১,৯৯৯)</a>
        </div>
      </div>
    </div>
  </section>

  <!-- How It Works Section (Dedicated Workflows for All 3 Engines - Zero Tabs) -->
  <section id="how" class="reveal">
    <div class="section-head">
      <h2 data-i18n="how_section_title">৩টি স্বতন্ত্র অটোমেশন ইঞ্জিনের স্বয়ংক্রিয় কার্যপ্রণালী</h2>
      <p class="lead" data-i18n="how_section_lead">একবার নিশ ও চ্যানেল কানেক্ট করলেই প্রতিটি ইঞ্জিন মানুষের কোনো হস্তক্ষেপ ছাড়াই স্বয়ংক্রিয়ভাবে কাজ করে। নিচে প্রতিটি সফটওয়্যারের ধাপসমূহ বিস্তারিত দেখুন:</p>
    </div>

    <!-- 3 Dedicated Workflow Boxes (Zero Tab Clicks Required) -->
    <div class="engine-workflows-container">
      <!-- Workflow Box 1: Social Media Content Automation Engine (9 Steps) -->
      <div class="workflow-engine-box wf-box-social" id="wfBoxSocial">
        <div class="wf-box-header">
          <div class="wf-box-title-group">
            <span class="engine-pill pill-cyan">🎬 ফুল কন্টেন্ট পাওয়ারহাউজ • ৳৩,৯৯৯</span>
            <h3 data-i18n="how_it_works">১. Automovie Pro - Social Media Content Automation Engine (৯টি ধাপ)</h3>
            <p data-i18n="how_lead">সম্পূর্ণ স্বয়ংক্রিয় ৯টি ধাপে ভাইরাল কনটেন্ট রিসার্চ থেকে শুরু করে ভিডিও তৈরি, গ্লোবাল ট্রান্সলেশন ও মাল্টি-প্ল্যাটফর্ম পাবলিশিং।</p>
          </div>
          <a href="#buy" class="btn btn-sm btn-engine-order" onclick="window.selectEngineRadio('video_studio')" data-i18n="engine1_order_btn">অর্ডার করুন (৳৩,৯৯৯)</a>
        </div>
        <ol class="flow-steps-grid steps-grid-9">
          <li class="step-card">
            <div class="step-num">01</div>
            <h4 data-i18n="e1_step1_title">নিশ রিসার্চ ও ট্রেন্ডিং টপিক অ্যানালাইসিস</h4>
            <p data-i18n="e1_step1_desc">আপনার নির্দিষ্ট নিশ এর উপরে ভিত্তি করে Google এবং YouTube API এর মাধ্যমে নিজেই বর্তমানের সবচাইতে ট্রেন্ডিং টপিক খুঁজে বের করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">02</div>
            <h4 data-i18n="e1_step2_title">ভাইরাল হুক সহ ফুল এআই ভিডিও স্ক্রিপ্ট জেনারেশন</h4>
            <p data-i18n="e1_step2_desc">নির্দিষ্ট ট্রেন্ডিং টপিকের ভিত্তিতে সঠিক ইমোশন ও সিনেমাটিক ভিউসহ অত্যন্ত নিখুঁতভাবে ভিডিও এবং অডিওর জন্য আলাদা স্ক্রিপ্ট লিখে দেয়।</p>
          </li>
          <li class="step-card">
            <div class="step-num">03</div>
            <h4 data-i18n="e1_step3_title">কাইনেটিক মোশন কার্ড ও সিনেমাটিক ভিজ্যুয়াল ক্রিয়েশন</h4>
            <p data-i18n="e1_step3_desc">স্ক্রিপ্টের প্রতিটি সিন এবং অডিও গভীরভাবে অ্যানালাইসিস করে প্রতিটি সিনের ভিত্তিতে আলাদা আলাদা ভিডিও ক্লিপ জেনারেশন করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">04</div>
            <h4 data-i18n="e1_step4_title">১০০% স্বাভাবিক মানবিক বাংলা এআই ভয়েসওভার</h4>
            <p data-i18n="e1_step4_desc">অডিও স্ক্রিপ্ট দিয়ে আলাদা আলাদা ভাষায় লোকালাইজেশন করে সঠিক ইমোশনসহ রোবোটিক টিউন লেস অডিও জেনারেশন করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">05</div>
            <h4 data-i18n="e1_step5_title">হাই-সিপিএম গ্লোবাল মাল্টি-ল্যাঙ্গুয়েজ ট্রান্সলেশন</h4>
            <p data-i18n="e1_step5_desc">প্রতিটি ভিডিও ক্লিপ এবং অডিও একসাথে জোড়া লাগিয়ে নির্দিষ্ট ভাষার ভিত্তিতে সাবটাইটেল ও সাউন্ড ইফেক্ট বসিয়ে ভিডিও রেন্ডার করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">06</div>
            <h4 data-i18n="e1_step6_title">স্টুডিও মাস্টার ভিডিও ও ফুল এইচডি রিলস রেন্ডারিং</h4>
            <p data-i18n="e1_step6_desc">এরপর নির্দিষ্ট নিস, চ্যানেলের লোগো ও ভিডিওর বিষয়বস্তুর উপর ভিত্তি করে SEO ফ্রেন্ডলি থাম্বনেইল, টাইটেল, ডেসক্রিপশন এবং ট্যাগ জেনারেট করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">07</div>
            <h4 data-i18n="e1_step7_title">ইউটিউব, ফেসবুক ও টিকটকে অটোমেটিক শিডিউল পাবলিশিং</h4>
            <p data-i18n="e1_step7_desc">ভিডিও প্রস্তুত হলে নির্ধারিত সময়ে প্রতিটি ভাষার জন্য আলাদা আলাদা প্ল্যাটফর্মে এবং আলাদা আলাদা অ্যাকাউন্টে ভিডিওগুলো আপলোড করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">08</div>
            <h4 data-i18n="e1_step8_title">প্রাসঙ্গিক গ্রুপ সমূহে অটোমেটিক পোস্ট শেয়ারিং</h4>
            <p data-i18n="e1_step8_desc">আপলোড হওয়ার পর প্রতিটি ভিডিও সার্বক্ষণিক নজরদারি করে এবং ভিডিওর টপিকের ভিত্তিতে কমেন্ট ও পেইজের মেসেজের উত্তর দেয়।</p>
          </li>
          <li class="step-card">
            <div class="step-num">09</div>
            <h4 data-i18n="e1_step9_title">২৪/৭ স্মার্ট অটোমেটিক কমেন্ট ও ইনবক্স রেসপন্স</h4>
            <p data-i18n="e1_step9_desc">সবশেষে একটি সোশ্যাল মিডিয়া ইঞ্জিনিয়ার এজেন্ট ভিডিওগুলো অ্যানালাইসিস করে নির্দিষ্ট গ্রুপে শেয়ার করে ভিউ বাড়ানোর চেষ্টা করে।</p>
          </li>
        </ol>
      </div>

      <!-- Workflow Box 2: FB Business Manager & Ad Automation Engine (5 Steps) -->
      <div class="workflow-engine-box wf-box-business" id="wfBoxBusiness">
        <div class="wf-box-header">
          <div class="wf-box-title-group">
            <span class="engine-pill pill-amber">💼 বিজনেস ও সেলস ম্যানেজার • ৳২,৯৯৯</span>
            <h3 data-i18n="how_engine2_title">২. Automovie Pro - FB Business Manager & Ad Automation Engine (৫টি ধাপ)</h3>
            <p data-i18n="how_engine2_lead">৫টি নিখুঁত পদক্ষেপে প্রোডাক্ট ও সার্ভিসের সেলস ব্যানার, অ্যাড ভিডিও ও কাস্টমার রেসপন্স।</p>
          </div>
          <a href="#buy" class="btn btn-sm btn-engine-order btn-amber" onclick="window.selectEngineRadio('fb_business')" data-i18n="engine2_order_btn">অর্ডার করুন (৳২,৯৯৯)</a>
        </div>
        <ol class="flow-steps-grid steps-grid-5">
          <li class="step-card">
            <div class="step-num">01</div>
            <h4 data-i18n="e2_step1_title">প্রোডাক্ট ও অফার অ্যানালাইসিস</h4>
            <p data-i18n="e2_step1_desc">আপনার প্রোডাক্ট, সেবা ও স্পেশাল অফারের মূল বৈশিষ্ট্য এবং টার্গেট কাস্টমার প্রোফাইল অ্যানালাইসিস করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">02</div>
            <h4 data-i18n="e2_step2_title">হাই-কনভার্টিং সেলস ব্যানার ও গ্রাফিক্স ডিজাইন</h4>
            <p data-i18n="e2_step2_desc">আকর্ষণীয় অফার টেক্সট, প্রোডাক্টের ছবি, মূল্যছাড় ও জরুরি যোগাযোগের তথ্য সহ প্রিমিয়াম ব্যানার তৈরি করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">03</div>
            <h4 data-i18n="e2_step3_title">কাইনেটিক মোশন অ্যাড ভিডিও জেনারেশন</h4>
            <p data-i18n="e2_step3_desc">সোশ্যাল মিডিয়ায় দ্রুত সেলস কনভার্শনের জন্য ৩০-৭০ সেকেন্ডের ডায়নামিক কাইনেটিক অ্যাড ভিডিও তৈরি করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">04</div>
            <h4 data-i18n="e2_step4_title">টার্গেটেড ফেসবুক গ্রুপ ও মার্কেটপ্লেসে অটো-শেয়ার</h4>
            <p data-i18n="e2_step4_desc">অর্গানিক সেলস লিড পাওয়ার জন্য নিশভিত্তিক বিজনেস গ্রুপ সমূহে স্বয়ংক্রিয়ভাবে পোস্ট শেয়ার করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">05</div>
            <h4 data-i18n="e2_step5_title">২৪/৭ স্মার্ট সেলস রিপ্লাই ও কাস্টমার সাপোর্ট</h4>
            <p data-i18n="e2_step5_desc">মেসেঞ্জার ও কমেন্টে কাস্টমারের প্রোডাক্টের দাম, অর্ডার ও ডেলিভারি সংক্রান্ত যেকোনো প্রশ্নের সাথে সাথে উত্তর দেয়।</p>
          </li>
        </ol>
      </div>

      <!-- Workflow Box 3: FB Profile & Page Post Automation Engine (5 Steps) -->
      <div class="workflow-engine-box wf-box-profile" id="wfBoxProfile">
        <div class="wf-box-header">
          <div class="wf-box-title-group">
            <span class="engine-pill pill-emerald">📱 প্রোফাইল ও পেজ অটো-পাইলট • ৳১,৯৯৯</span>
            <h3 data-i18n="how_engine3_title">৩. Automovie Pro - FB Profile & Page Post Automation Engine (৫টি ধাপ)</h3>
            <p data-i18n="how_engine3_lead">৫টি পবিত্র ও পরিচ্ছন্ন ধাপে ইসলামিক বা অনুপ্রেরণামূলক পোস্ট ও ব্যানার অটো-পাইলট পাবলিশিং।</p>
          </div>
          <a href="#buy" class="btn btn-sm btn-engine-order btn-emerald" onclick="window.selectEngineRadio('profile_page')" data-i18n="engine3_order_btn">অর্ডার করুন (৳১,৯৯৯)</a>
        </div>
        <ol class="flow-steps-grid steps-grid-5">
          <li class="step-card">
            <div class="step-num">01</div>
            <h4 data-i18n="e3_step1_title">নিসভিত্তিক কন্টেন্ট ও হাদিস/উক্তি নির্বাচন</h4>
            <p data-i18n="e3_step1_desc">ইসলামিক নির্ভরযোগ্য হাদিস, কোরআনের বাণী বা অনুপ্রেরণামূলক পজিটিভ উক্তি অটোমেটিক নির্বাচন করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">02</div>
            <h4 data-i18n="e3_step2_title">গোল্ডেন এমবলেম ব্যানার ও ফটো ফ্রেম তৈরি</h4>
            <p data-i18n="e3_step2_desc">আপনার পেজ বা প্রোফাইলের লোগো ও ব্র্যান্ডিং সহ দৃষ্টিনন্দন সোশ্যাল কোট ব্যানার ইমেজ প্রস্তুত করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">03</div>
            <h4 data-i18n="e3_step3_title">প্রাসঙ্গিক স্ট্যাটাস ও ক্যাপশন রাইটিং</h4>
            <p data-i18n="e3_step3_desc">অডিয়েন্স এনগেজমেন্ট বাড়ানোর জন্য আকর্ষণীয় বাংলা ক্যাপশন, রেফারেন্স ও হ্যাশট্যাগ দিয়ে পোস্ট ড্রাফট করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">04</div>
            <h4 data-i18n="e3_step4_title">ফেসবুক প্রোফাইল ও পেজে হিউম্যান-লাইক পোস্টিং</h4>
            <p data-i18n="e3_step4_desc">সম্পূর্ণ নিরাপদ হিউম্যান সিমুলেশনের মাধ্যমে নির্দিষ্ট শিডিউলে আপনার প্রোফাইল ও পেজে পোস্ট পাবলিশ করে।</p>
          </li>
          <li class="step-card">
            <div class="step-num">05</div>
            <h4 data-i18n="e3_step5_title">নিশভিত্তিক কমিউনিটি গ্রুপে অর্গানিক শেয়ারিং</h4>
            <p data-i18n="e3_step5_desc">প্রোফাইল বা পেজের ফলোয়ার ও রিচ বাড়ানোর জন্য ইসলামিক ও জ্ঞানমূলক ফেসবুক গ্রুপগুলোতে পোস্ট পৌঁছে দেয়।</p>
          </li>
        </ol>
      </div>
    </div>

    <?php if (trim($how) !== ''): ?>
      <div class="steps cms-block" style="max-width:800px; margin:2rem auto 0;"><?= nl2br(e($how)) ?></div>
    <?php endif; ?>
  </section>

  <!-- SPECIAL GOOGLE AI PRO PACKAGE SECTION (Sitting right below Software Packages with Disclaimer Banner) -->
  <section id="google-pro" class="reveal">
    <div class="google-pro-container">
      <!-- Prominent Google Pro Disclaimer Banner as Ordered by Client -->
      <div class="gpro-disclaimer-box" style="margin-bottom: 2.5rem; background: linear-gradient(135deg, rgba(30, 58, 138, 0.45), rgba(15, 23, 42, 0.85)); border: 2px solid #38bdf8; border-radius: var(--radius-xl); padding: 1.75rem 2rem; box-shadow: 0 0 30px rgba(56, 189, 248, 0.2); text-align: center;">
        <div style="display:inline-flex; align-items:center; gap:8px; background: rgba(56,189,248,0.2); color: #38bdf8; font-weight: 800; font-size: 0.88rem; padding: 4px 16px; border-radius: 999px; margin-bottom: 0.85rem;">
          ℹ️ <span data-i18n="gpro_disclaimer_badge">স্পেশাল প্রো ক্লাউড নোটিশ</span>
        </div>
        <p style="color: #f1f5f9; font-size: 1.08rem; line-height: 1.7; max-width: 960px; margin: 0 auto; font-weight: 500;" data-i18n="gpro_disclaimer_text">
          ফ্রি এপিআই দিয়েও আমাদের সফটওয়্যারটি চলবে, কোনো সমস্যা নেই। তবে কোটা লিমিটের কোনো ঝুঁকি ছাড়া নিশ্চিন্তে আনলিমিটেড হাই-কোয়ালিটি ভিডিও জেনারেট করতে চাইলে এবং ভিডিও ও অডিওর সর্বোচ্চ সিনেমাটিক কোয়ালিটি পেতে চাইলে অবশ্যই আমাদের গুগল প্রো প্যাকেজগুলো গ্রহণ করতে পারেন।
        </p>
      </div>

      <div style="text-align: center; margin-bottom: 2.75rem;">
        <div style="display:inline-flex; align-items:center; gap:12px; background:rgba(255,255,255,0.06); padding:8px 24px; border-radius:999px; border:1px solid rgba(66,133,244,0.35); margin-bottom:1.25rem;">
          <svg width="26" height="26" viewBox="0 0 48 48" style="vertical-align:middle;">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          <span style="font-weight:800; font-size:1.15rem; color:#ffffff; letter-spacing:0.5px;">Google AI Pro Cloud Engine</span>
          <span style="background:#38bdf8; color:#020617; font-size:0.75rem; font-weight:800; padding:2px 8px; border-radius:999px;">OFFICIAL</span>
        </div>
        <h2 style="font-size: 2.2rem; color: #60a5fa; margin-bottom: 0.85rem;" data-i18n="gpro_title">
          কোন ঝামেলা ছাড়াই ভিডিও তৈরির জন্য স্পেশাল গুগল AI Pro প্যাকেজ
        </h2>
        <p class="lead" style="color: #cbd5e1; max-width: 840px; margin: 0 auto;" data-i18n="gpro_lead">
          কোটা লিমিট শেষ হওয়া বা রোবোটিক সাউন্ডের কোনো ঝামেলা ছাড়া আনলিমিটেড ক্রিয়েশন! সরাসরি গুগল প্রো ক্লাউড, হাই-রেজুলেশন সিনেমাটিক মডেল ও নিরাপদ ১৫০ জিবি ক্লাউড ড্রাইভ ব্যাকআপ আপনার জিমেইলে।
        </p>
      </div>

      <!-- Feature Highlights -->
      <div class="gpro-features-grid">
        <div class="gpro-feat-item">
          <span class="gpro-feat-icon">⚡</span>
          <div>
            <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;" data-i18n="gpro_feat1_title">গুগল Nano Banana ও VEO-3 সিনেমাটিক API</strong>
            <span style="color: #94a3b8; font-size: 0.9rem;" data-i18n="gpro_feat1_desc">আল্ট্রা-এইচডি সিনেমাটিক ভিডিও সিন ও স্টুডিও কোয়ালিটি ইমেজ জেনারেশন ফুল এক্সেস।</span>
          </div>
        </div>

        <div class="gpro-feat-item">
          <span class="gpro-feat-icon">🎙️</span>
          <div>
            <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;" data-i18n="gpro_feat2_title">আল্ট্রা-ন্যাচারাল রোবোটিকলেস TTS</strong>
            <span style="color: #94a3b8; font-size: 0.9rem;" data-i18n="gpro_feat2_desc">১০০% মানবিক অনুভূতির বাংলা ও বহুভাষিক ভয়েসওভার — রোবোটিক টোনমুক্ত।</span>
          </div>
        </div>

        <div class="gpro-feat-item">
          <span class="gpro-feat-icon">📈</span>
          <div>
            <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;" data-i18n="gpro_feat3_title">হাই CTR ভাইরাল টপিক ও স্ক্রিপ্ট</strong>
            <span style="color: #94a3b8; font-size: 0.9rem;" data-i18n="gpro_feat3_desc">ইউটিউব ও মেটা অ্যালগরিদম টার্গেটেড ভাইরাল টপিক রিসার্চ ও ক্যাচি হুক জেনারেশন।</span>
          </div>
        </div>

        <div class="gpro-feat-item">
          <span class="gpro-feat-icon">💬</span>
          <div>
            <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;" data-i18n="gpro_feat4_title">২৪/৭ আনলিমিটেড স্মার্ট চ্যাট ও মনিটরিং</strong>
            <span style="color: #94a3b8; font-size: 0.9rem;" data-i18n="gpro_feat4_desc">যেকোনো টেকনিক্যাল সাপোর্টে সার্বক্ষণিক ডেডিকেটেড এআই কনসালট্যান্ট ও মানব টিম।</span>
          </div>
        </div>

        <div class="gpro-feat-item" style="grid-column: 1 / -1;">
          <span class="gpro-feat-icon">☁️</span>
          <div>
            <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;" data-i18n="gpro_feat5_title">ফুটেজ স্টোরেজের জন্য ১৫০ জিবি গুগল ক্লাউড ড্রাইভ</strong>
            <span style="color: #94a3b8; font-size: 0.9rem;" data-i18n="gpro_feat5_desc">ভিডিও, অডিও ও মেটাডাটা ব্যাকআপের জন্য ডেডিকেটেড হাই-স্পিড গুগল ক্লাউড ড্রাইভ সরাসরি আপনার জিমেইলে কনফিগার হবে।</span>
          </div>
        </div>
      </div>

      <!-- Pricing Plans -->
      <div class="gpro-plans-grid" style="grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));">
        <!-- Test Account (1 Month) -->
        <div class="gpro-plan-card">
          <div>
            <h3 style="color: #e2e8f0; font-size: 1.25rem; margin-bottom: 0.35rem;">টেস্ট একাউন্ট</h3>
            <p style="color: #94a3b8; font-size: 0.88rem; margin-bottom: 1rem;">৩০ দিনের ফুল প্রো টেস্ট এক্সেস</p>
            <div class="plan-price-amount">১২০ ৳</div>
            <ul class="plan-features-list">
              <li>✓ Gemini 3.1 & Nano API এক্সেস</li>
              <li>✓ রোবোটিকলেস প্রিমিয়াম ন্যাচারাল TTS</li>
              <li>✓ ৫০ জিবি ক্লাউড ফুটেজ স্পেস</li>
              <li>✓ ১ মাস নিরবচ্ছিন্ন মেয়াদ</li>
            </ul>
          </div>
          <a href="/order.php?product=google_pro&plan=1" class="btn" style="width:100%; text-align:center;">অর্ডার করুন (১২০ ৳)</a>
        </div>

        <!-- Startup Plan (12 Months) -->
        <div class="gpro-plan-card">
          <div>
            <h3 style="color: #ffffff; font-size: 1.25rem; margin-bottom: 0.35rem;">স্টার্টআপ একাউন্ট</h3>
            <p style="color: #94a3b8; font-size: 0.88rem; margin-bottom: 1rem;">১২ মাসের আনলিমিটেড সার্ভিস</p>
            <div class="plan-price-amount">৯৯৯ ৳</div>
            <ul class="plan-features-list">
              <li>✓ Nano Banana ও Veo-3 API এক্সেস</li>
              <li>✓ রোবোটিকলেস প্রিমিয়াম ন্যাচারাল TTS</li>
              <li>✓ ১০০ জিবি ডেডিকেটেড গুগল ক্লাউড</li>
              <li>✓ ১২ মাস ফুল ভ্যালিডিটি</li>
              <li>✓ মেগা ডিসকাউন্ট সেভিংস প্যাকেজ</li>
            </ul>
          </div>
          <a href="/order.php?product=google_pro&plan=12" class="btn" style="width:100%; text-align:center; background:linear-gradient(135deg, #06b6d4, #2563eb);">অর্ডার করুন (৯৯৯ ৳)</a>
        </div>

        <!-- Business VIP Plan (18 Months) -->
        <div class="gpro-plan-card popular">
          <span class="popular-badge">জনপ্রিয় চয়েস</span>
          <div>
            <h3 style="color: #e2e8f0; font-size: 1.25rem; margin-bottom: 0.35rem;">বিজনেস একাউন্ট</h3>
            <p style="color: #94a3b8; font-size: 0.88rem; margin-bottom: 1rem;">১৮ মাসের দীর্ঘমেয়াদী প্যাকেজ</p>
            <div class="plan-price-amount">১২৯৯ ৳</div>
            <ul class="plan-features-list">
              <li>✓ Nano Banana ও Veo-3 API এক্সেস</li>
              <li>✓ রোবোটিকলেস প্রিমিয়াম ন্যাচারাল TTS</li>
              <li>✓ ১৫০ জিবি ডেডিকেটেড গুগল ক্লাউড ড্রাইভ</li>
              <li>✓ ১৮ মাস সম্পূর্ণ লাইসেন্স মেয়াদ</li>
              <li>✓ ভিআইপি প্রায়োরিটি সাপোর্ট</li>
            </ul>
          </div>
          <a href="/order.php?product=google_pro&plan=18" class="btn" style="width:100%; text-align:center;">অর্ডার করুন (১২৯৯ ৳)</a>
        </div>

        <!-- Relax Business (2 Accounts, 18 Months) -->
        <div class="gpro-plan-card">
          <div>
            <h3 style="color: #c084fc; font-size: 1.25rem; margin-bottom: 0.35rem;">রিল্যাক্স বিজনেস</h3>
            <p style="color: #94a3b8; font-size: 0.88rem; margin-bottom: 1rem;">২টি একাউন্ট (১৮ মাস ভ্যালিডিটি)</p>
            <div class="plan-price-amount">১৯৯৯ ৳</div>
            <ul class="plan-features-list">
              <li>✓ ২টি ফুল ডেডিকেটেড জেমিনি প্রো অ্যাকাউন্ট</li>
              <li>✓ আনলিমিটেড কোটা ও লাইফটাইম ব্যাকআপ পুল</li>
              <li>✓ ৩০০ জিবি সুপার ক্লাউড স্টোরেজ ভল্ট</li>
              <li>✓ ১৮ মাস মেয়াদ + ডিরেক্ট ভিআইপি সাপোর্ট</li>
            </ul>
          </div>
          <a href="/order.php?product=google_pro&plan=24" class="btn" style="width:100%; text-align:center; background:linear-gradient(135deg, #a855f7, #6366f1);">অর্ডার করুন (১৯৯৯ ৳)</a>
        </div>
      </div>
    </div>
  </section>

  <!-- Feature Cards & 3-Column Suite (Zero Tabs, 100% Direct Visibility) -->
  <section id="features" class="reveal">
    <div class="section-head">
      <h2 data-i18n="features_suite_title">৩টি সফটওয়্যার প্যাকেজের পূর্ণাঙ্গ ফিচার ও সুবিধাসমূহ</h2>
      <p class="lead" data-i18n="features_suite_lead">কোনো ক্লিক বা ফিল্টার ছাড়াই ৩টি সফটওয়্যারের প্রতিটি ফিচার ও অনন্য সুবিধাসমূহ পাশাপাশি তুলনা করে দেখুন।</p>
    </div>

    <!-- 3-Column Modern Feature & Capabilities Suite (Zero Tabs, All Direct) -->
    <div class="feature-suite-3col-grid">
      <!-- Box 1: Social Media Content Automation Engine -->
      <div class="feat-box feat-box-video">
        <div class="feat-box-top">
          <div class="feat-box-identity">
            <img src="/assets/img/logo_video_studio.png?v=<?= filemtime(__DIR__ . '/assets/img/logo_video_studio.png') ?>" alt="Video Content Studio Logo" class="feat-product-logo">
            <span class="engine-top-badge badge-cyan">🎬 ফুল কন্টেন্ট পাওয়ারহাউজ</span>
          </div>
          <div class="feat-box-price-wrap">
            <span class="feat-current-price">৳৩,৯৯৯</span>
            <span class="feat-old-price">৳১০,০০০</span>
            <span class="feat-license-tag">লাইফটাইম লাইসেন্স • এককালীন ফি</span>
          </div>
        </div>
        <h3 class="feat-box-title" data-i18n="pkg1_title">১. Automovie Pro - Social Media Content Automation Engine</h3>
        <p class="feat-box-lead">ইউটিউব, ফেসবুক ও টিকটকের জন্য সম্পূর্ণ স্বয়ংক্রিয় ভাইরাল ভিডিও তৈরি, ট্রান্সলেশন ও মাল্টি-প্ল্যাটফর্ম পাবলিশিং।</p>
        
        <div class="feat-box-checklist-title">✨ অন্তর্ভুক্ত সকল ফিচার ও সুবিধাসমূহ:</div>
        <ul class="feat-box-checklist">
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>সম্পূর্ণ অটো শর্ট ও লং ভিডিও তৈরি:</strong> নির্দিষ্ট সময়ে ফুল এআই শর্টস ও ৫ মিনিটের লং স্টোরি ভিডিও নিজে তৈরি করে।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>ভাইরাল হুক ও চিত্রনাট্য জেনারেশন:</strong> Google ও YouTube ট্রেন্ডস অ্যানালাইসিস করে স্বয়ংক্রিয় ট্রেন্ডিং টপিক ও স্ক্রিপ্ট তৈরি।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>১০০% মানবিক বাংলা ও বহুভাষিক ভয়েসওভার:</strong> সম্পূর্ণ রোবোটিকলেস ন্যাচারাল প্রো অডিও।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>কাইনেটিক মোশন কার্ড ও সিনেমাটিক ভিজ্যুয়াল:</strong> স্ক্রিপ্টের সাথে নিখুঁতভাবে ম্যাচ করা এইচডি ভিজ্যুয়াল ক্লিপস।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>এক মাস্টার ভিডিও থেকে ৬ ভাষায় ট্রান্সলেশন:</strong> একই ভিডিও বাংলা, হিন্দি, উর্দু, তামিল, মালয়ালম ও ইংরেজিতে তৈরি করে বিশ্বব্যাপী রিচ।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>একসাথে ৬টি YouTube + ৬টি Facebook + ৬টি TikTok:</strong> স্বয়ংক্রিয় নির্দিষ্ট শিডিউলে ভিডিও আপলোড।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>SEO থাম্বনেইল, টাইটেল ও মেটাডাটা:</strong> আকর্ষণীয় ক্লিকেবল থাম্বনেইল, টাইটেল, ডেসক্রিপশন ও ট্যাগ জেনারেটর।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>সোশ্যাল মিডিয়া ইঞ্জিনিয়ার দ্বারা অর্গানিক শেয়ার:</strong> প্রাসঙ্গিক ফেসবুক গ্রুপসমূহে স্বয়ংক্রিয় ভিডিও শেয়ারিং।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>২৪/৭ স্মার্ট কমেন্ট ও ইনবক্স রেসপন্স:</strong> ভিউয়ারদের কমেন্টের তাৎক্ষণিক উত্তর ও এআই কাস্টমার এনগেজমেন্ট।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>Agnes ভিডিও ইঞ্জিন ও ইমেজ ফলব্যাক:</strong> কোনো ফ্রেম আটকে না থেকে নিরবচ্ছিন্ন ভিডিও রেন্ডারিং।</div>
          </li>
        </ul>
        <div class="feat-box-footer">
          <a href="#buy" class="btn btn-engine-order" onclick="window.selectEngineRadio('video_studio')">অর্ডার করুন (৳৩,৯৯৯)</a>
        </div>
      </div>

      <!-- Box 2: FB Business Manager & Ad Automation Engine -->
      <div class="feat-box feat-box-business">
        <div class="feat-box-top">
          <div class="feat-box-identity">
            <img src="/assets/img/logo_fb_business.png?v=<?= filemtime(__DIR__ . '/assets/img/logo_fb_business.png') ?>" alt="FB Business & Ad Engine Logo" class="feat-product-logo">
            <span class="engine-top-badge badge-amber">💼 বিজনেস ও সেলস ম্যানেজার</span>
          </div>
          <div class="feat-box-price-wrap">
            <span class="feat-current-price">৳২,৯৯৯</span>
            <span class="feat-old-price">৳৮,৫০০</span>
            <span class="feat-license-tag">লাইফটাইম লাইসেন্স • এককালীন ফি</span>
          </div>
        </div>
        <h3 class="feat-box-title" data-i18n="pkg2_title">২. Automovie Pro - FB Business Manager & Ad Automation Engine</h3>
        <p class="feat-box-lead">ব্যবসা ও প্রডাক্টের হাই-কনভার্টিং সেলস ব্যানার, কাইনেটিক বিজ্ঞাপন ভিডিও ও মেসেঞ্জার সেলস সাপোর্ট।</p>
        
        <div class="feat-box-checklist-title">✨ অন্তর্ভুক্ত সকল ফিচার ও সুবিধাসমূহ:</div>
        <ul class="feat-box-checklist">
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>হাই-কনভার্টিং সেলস ব্যানার ও অফার গ্রাফিক্স:</strong> প্রডাক্টের ছবি, আকর্ষণীয় মূল্যছাড় ও জরুরি যোগাযোগের তথ্য সহ প্রিমিয়াম ব্যানার।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>কাইনেটিক বিজ্ঞাপন ভিডিও জেনারেশন:</strong> সোশ্যাল মিডিয়ায় দ্রুত বিক্রির জন্য ৩০-৭০ সেকেন্ডের ডায়নামিক ভিডিও বিজ্ঞাপন।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>টার্গেটেড ফেসবুক গ্রুপ ও মার্কেটপ্লেসে অটো-শেয়ার:</strong> অর্গানিক সেলস লিড সংগ্রহের জন্য নিয়মিত পোস্ট শেয়ার।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>২৪/৭ ইনস্ট্যান্ট মেসেঞ্জার ও কমেন্ট সেলস রিপ্লাই:</strong> পণ্যের দাম, স্টক ও অর্ডার সংক্রান্ত প্রশ্নের তাৎক্ষণিক উত্তর।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>প্রোডাক্ট ক্যাটালগ ও স্পেশাল ক্যাম্পেইন ম্যানেজমেন্ট:</strong> একাধিক পণ্য ও অফার স্বয়ংক্রিয় প্রমোশন পরিচালনা।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>একসাথে ৬টি ফেসবুক পেজ ও ডেস্টিনেশন:</strong> একাধিক ব্র্যান্ড পেজ একসাথে এক ড্যাশবোর্ড থেকে হ্যান্ডেল করার সুবিধা।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>ফেসবুক পেজ পোস্ট ও দৈনিক স্টোরি শিডিউলার:</strong> নির্দিষ্ট সময়সূচিতে পোস্ট ও ৯:১৬ স্টোরি স্বয়ংক্রিয় পাবলিশ।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>অটোপাইলট পোস্ট হিলার ও অডিট গার্ড:</strong> ভুল পোস্ট স্বয়ংক্রিয় সংশোধন ও পেজের নিরাপত্তা বজায় রাখা।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>কাস্টমার ইনকোয়ারি লিড ক্যাপচার:</strong> আগ্রহী ক্রেতাদের তথ্য সংগ্রহ ও ফলো-আপ সুবিধা।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>নিরাপদ হিউম্যান সিমুলেশন পোস্টিং:</strong> ফেসবুক অ্যালগরিদম মেনে অ্যাকাউন্টের শতভাগ সুরক্ষা।</div>
          </li>
        </ul>
        <div class="feat-box-footer">
          <a href="#buy" class="btn btn-engine-order btn-amber" onclick="window.selectEngineRadio('fb_business')">অর্ডার করুন (৳২,৯৯৯)</a>
        </div>
      </div>

      <!-- Box 3: FB Profile & Page Post Automation Engine -->
      <div class="feat-box feat-box-profile">
        <div class="feat-box-top">
          <div class="feat-box-identity">
            <img src="/assets/img/logo_profile_page.png?v=<?= filemtime(__DIR__ . '/assets/img/logo_profile_page.png') ?>" alt="Social AutoPilot Engine Logo" class="feat-product-logo">
            <span class="engine-top-badge badge-emerald">📱 প্রোফাইল ও পেজ অটো-পাইলট</span>
          </div>
          <div class="feat-box-price-wrap">
            <span class="feat-current-price">৳১,৯৯৯</span>
            <span class="feat-old-price">৳৬,৫০০</span>
            <span class="feat-license-tag">লাইফটাইম লাইসেন্স • এককালীন ফি</span>
          </div>
        </div>
        <h3 class="feat-box-title" data-i18n="pkg3_title">৩. Automovie Pro - FB Profile & Page Post Automation Engine</h3>
        <p class="feat-box-lead">ব্যক্তিগত প্রোফাইল ও পেজের জন্য ইসলামিক বা মোটিভেশনাল পোস্ট ও গোল্ডেন এমবলেম ব্যানার অটোমেশন।</p>
        
        <div class="feat-box-checklist-title">✨ অন্তর্ভুক্ত সকল ফিচার ও সুবিধাসমূহ:</div>
        <ul class="feat-box-checklist">
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>খাঁটি ইসলামিক হাদিস/কোরআনের বাণী বা অনুপ্রেরণামূলক উক্তি:</strong> স্বয়ংক্রিয় নির্ভরযোগ্য কন্টেন্ট নির্বাচন।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>গোল্ডেন এমবলেম ব্যানার ও ব্র্যান্ড ফটো ফ্রেম:</strong> আপনার পেজের লোগো ও ফ্রেম সহ আকর্ষণীয় কোট ব্যানার ডিজাইন।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>প্রাসঙ্গিক বাংলা স্ট্যাটাস ও ক্যাপশন রাইটিং:</strong> অডিয়েন্স এনগেজমেন্ট ও রিচ বাড়ানোর জন্য নিখুঁত লেখা।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>প্রোফাইল ও পেজে হিউম্যান-লাইক পোস্টিং:</strong> কোনো রোবোটিক স্প্যাম ছাড়াই নিরাপদ ব্রাউজার সিমুলেশনে পোস্ট পাবলিশ।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>নিশভিত্তিক কমিউনিটি গ্রুপে অর্গানিক শেয়ারিং:</strong> ফলোয়ার ও পরিচিতি বৃদ্ধির জন্য গ্রুপে পোস্ট পৌঁছে দেওয়া।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>ফ্রেন্ড ও ফলোয়ার এনগেজমেন্ট অটোমেশন:</strong> লাইক ও কমেন্টে সক্রিয় থাকার সুবিধা।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>ওয়ান-টাইম কানেক্ট ও সেশন কুকি সেভার:</strong> প্রতিদিন বারবার অ্যাকাউন্টে লগইনের ঝামেলা নেই।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>ইন-অ্যাপ ডেস্কটপ হেল্পার ও ক্যাপচা অ্যালার্ট:</strong> সেটআপ ও ব্যবহারে তাৎক্ষণিক গাইডলাইন।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>৩০ সেকেন্ডের গ্রেসফুল ওয়াচডগ ও অটো-রিট্রাই:</strong> কোনো ব্রাউজার ড্রপ হলে নিরাপদ অটোমেটিক রিকভারি।</div>
          </li>
          <li>
            <span class="feat-chk">✓</span>
            <div><strong>লাইফটাইম লাইসেন্স ও আজীবন সাপোর্ট:</strong> কোনো মাসিক সাবস্ক্রিপশন চার্জ ছাড়া আজীবন ব্যবহার।</div>
          </li>
        </ul>
        <div class="feat-box-footer">
          <a href="#buy" class="btn btn-engine-order btn-emerald" onclick="window.selectEngineRadio('profile_page')">অর্ডার করুন (৳১,৯৯৯)</a>
        </div>
      </div>
    </div>

    <?php
    $catalogByTier = [
        'video_studio' => [],
        'fb_business' => [],
        'profile_page' => []
    ];
    foreach ($catalog as $feat) {
        $t = $feat['tier'] ?? 'video_studio';
        if (!isset($catalogByTier[$t])) {
            $catalogByTier[$t] = [];
        }
        $catalogByTier[$t][] = $feat;
    }
    ?>

    <!-- Visual Feature Galleries for Each Software (No tabs, all directly visible) -->
    <div class="feature-visual-galleries">
      <!-- Section 1: Video Studio Gallery -->
      <div class="feat-gallery-section">
        <h4 class="gallery-subheading" style="color:#38bdf8;">🎬 ১. Social Media Content Automation Engine — ভিজ্যুয়াল ফিচারসমূহ</h4>
        <div class="feature-grid">
          <?php foreach ($catalogByTier['video_studio'] as $feat):
              $f = amp_feature_for_lang($feat, $uiLang);
              $img = '/assets/img/' . rawurlencode($f['image']);
              ?>
            <article class="feature-card" data-feat-id="<?= e($f['id']) ?>" data-tier="video_studio">
              <div class="feature-img-wrap">
                <span class="tier-pill tier-video">🎬 Social Media Engine (৳৩,৯৯৯)</span>
                <img class="feature-img" src="<?= e($img) ?>" alt="<?= e($f['title']) ?>" loading="lazy" width="800" height="450">
              </div>
              <div class="feature-card-body">
                <h3 class="feature-title"><?= e($f['title']) ?></h3>
                <p class="feature-detail"><?= e($f['detail']) ?></p>
              </div>
            </article>
          <?php endforeach; ?>
        </div>
      </div>

      <!-- Section 2: FB Business Gallery -->
      <div class="feat-gallery-section">
        <h4 class="gallery-subheading" style="color:#fbbf24;">💼 ২. FB Business Manager & Ad Automation Engine — ভিজ্যুয়াল ফিচারসমূহ</h4>
        <div class="feature-grid">
          <?php foreach ($catalogByTier['fb_business'] as $feat):
              $f = amp_feature_for_lang($feat, $uiLang);
              $img = '/assets/img/' . rawurlencode($f['image']);
              ?>
            <article class="feature-card" data-feat-id="<?= e($f['id']) ?>" data-tier="fb_business">
              <div class="feature-img-wrap">
                <span class="tier-pill tier-business">💼 FB Business Engine (৳২,৯৯৯)</span>
                <img class="feature-img" src="<?= e($img) ?>" alt="<?= e($f['title']) ?>" loading="lazy" width="800" height="450">
              </div>
              <div class="feature-card-body">
                <h3 class="feature-title"><?= e($f['title']) ?></h3>
                <p class="feature-detail"><?= e($f['detail']) ?></p>
              </div>
            </article>
          <?php endforeach; ?>
        </div>
      </div>

      <!-- Section 3: Profile Page Gallery -->
      <div class="feat-gallery-section">
        <h4 class="gallery-subheading" style="color:#34d399;">📱 ৩. FB Profile & Page Post Automation Engine — ভিজ্যুয়াল ফিচারসমূহ</h4>
        <div class="feature-grid">
          <?php foreach ($catalogByTier['profile_page'] as $feat):
              $f = amp_feature_for_lang($feat, $uiLang);
              $img = '/assets/img/' . rawurlencode($f['image']);
              ?>
            <article class="feature-card" data-feat-id="<?= e($f['id']) ?>" data-tier="profile_page">
              <div class="feature-img-wrap">
                <span class="tier-pill tier-profile">📱 FB Profile Engine (৳১,৯৯৯)</span>
                <img class="feature-img" src="<?= e($img) ?>" alt="<?= e($f['title']) ?>" loading="lazy" width="800" height="450">
              </div>
              <div class="feature-card-body">
                <h3 class="feature-title"><?= e($f['title']) ?></h3>
                <p class="feature-detail"><?= e($f['detail']) ?></p>
              </div>
            </article>
          <?php endforeach; ?>
        </div>
      </div>
    </div>
  </section>

  <!-- Core Software Purchase Form -->
  <section id="buy" class="reveal">
    <div class="purchase-wrapper">
      <div class="section-head" style="margin-bottom: 1.5rem;">
        <h2 data-i18n="purchase">অর্ডার ও লাইসেন্সিং (লাইফটাইম লাইসেন্স)</h2>
        <p class="lead" style="max-width: 780px; margin: 0.5rem auto 1rem; color: #94a3b8; font-size: 1rem;">
          আমাদের ৩টি স্বতন্ত্র অটোমেশন ইঞ্জিনের মধ্যে আপনার প্রয়োজন ও বাজেট অনুযায়ী যেকোনো প্যাকেজ বেছে নিন। এককালীন ওয়ান-টাইম ফি, কোনো মাসিক সাবস্ক্রিপশন চার্জ নেই — আজীবন ফ্রি আপডেট সহ লাইফটাইম লাইসেন্স।
        </p>
        <div class="packages-tier-summary-bar">
          <span class="tier-summary-chip is-active" data-engine-pill="video_studio" onclick="window.selectEngineRadio('video_studio')">
            <span>🎬 ১. Social Media Engine</span>
            <span class="chip-price">৳৩,৯৯৯</span>
          </span>
          <span class="tier-summary-chip" data-engine-pill="fb_business" onclick="window.selectEngineRadio('fb_business')">
            <span>💼 ২. FB Business & Ads</span>
            <span class="chip-price">৳২,৯৯৯</span>
          </span>
          <span class="tier-summary-chip" data-engine-pill="profile_page" onclick="window.selectEngineRadio('profile_page')">
            <span>📱 ৩. Profile & Page Pilot</span>
            <span class="chip-price">৳১,৯৯৯</span>
          </span>
        </div>
      </div>

      <form class="purchase" method="post" action="/purchase.php" id="purchaseForm">
        <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
        <input type="hidden" name="plan_name" id="orderPlanName" value="AutoMovie Pro - Social Media Content Automation Engine (Lifetime License)">
        <input type="hidden" name="amount" id="orderAmount" value="3999">
        <input type="hidden" name="base_langs" id="baseLangs" value="en,bn">
        <input type="hidden" name="addon_langs" id="addonLangs" value="">

        <!-- 3 Distinct Software Engines Selection Cards -->
        <fieldset class="engine-picker-fieldset">
          <legend data-i18n="select_software_package">আপনার প্রয়োজনীয় AutoMovie Pro ইঞ্জিনটি নির্বাচন করুন</legend>
          <div class="engine-selector-grid">
            <label class="engine-select-card active" data-engine="video_studio">
              <input type="radio" name="product_type" value="video_studio" data-base-price="3999" data-plan-title="AutoMovie Pro - Social Media Content Automation Engine (Lifetime License)" checked>
              <div class="engine-select-inner">
                <div class="engine-select-top">
                  <span class="engine-pill pill-cyan">🎬 ফুল কন্টেন্ট পাওয়ারহাউজ</span>
                  <span class="engine-select-price">৳৩,৯৯৯</span>
                </div>
                <h4 data-i18n="engine1_radio_title">১. Social Media Content Automation Engine</h4>
                <p>সম্পূর্ণ এআই ভিডিও তৈরি, বহুভাষিক ট্রান্সলেশন এবং YouTube, Facebook ও TikTok-এ ১৮টি চ্যানেলে অটো আপলোড।</p>
              </div>
            </label>

            <label class="engine-select-card" data-engine="fb_business">
              <input type="radio" name="product_type" value="fb_business" data-base-price="2999" data-plan-title="AutoMovie Pro - FB Business Manager & Ad Automation Engine (Lifetime License)">
              <div class="engine-select-inner">
                <div class="engine-select-top">
                  <span class="engine-pill pill-amber">💼 বিজনেস ও সেলস ম্যানেজার</span>
                  <span class="engine-select-price">৳২,৯৯৯</span>
                </div>
                <h4 data-i18n="engine2_radio_title">২. FB Business Manager & Ad Automation Engine</h4>
                <p>সেলস ব্যানার, প্রমোশনাল বিজ্ঞাপন ভিডিও, গ্রুপ সমূহে অর্গানিক শেয়ার ও মেসেঞ্জারে ২৪/৭ স্মার্ট সেলস রিপ্লাই।</p>
              </div>
            </label>

            <label class="engine-select-card" data-engine="profile_page">
              <input type="radio" name="product_type" value="profile_page" data-base-price="1999" data-plan-title="AutoMovie Pro - FB Profile & Page Post Automation Engine (Lifetime License)">
              <div class="engine-select-inner">
                <div class="engine-select-top">
                  <span class="engine-pill pill-emerald">📱 প্রোফাইল ও পেজ অটো-পাইলট</span>
                  <span class="engine-select-price">৳১,৯৯৯</span>
                </div>
                <h4 data-i18n="engine3_radio_title">৩. FB Profile & Page Post Automation Engine</h4>
                <p>ইসলামিক হাদিস/উক্তি ব্যানার তৈরি, টাইমলাইনে অটো পোস্ট এবং গ্রুপ সমূহে নিরাপদ অর্গানিক শেয়ারিং।</p>
              </div>
            </label>
          </div>
        </fieldset>

        <!-- Dynamic Selected Plan Details Card -->
        <div class="selected-plan-summary-box" id="selectedPlanSummaryBox">
          <div class="spsb-header">
            <span class="spsb-badge">বর্তমানে নির্বাচিত ইঞ্জিন ও লাইসেন্স</span>
            <div class="spsb-price" id="heroSelectedPrice">৳৩,৯৯৯</div>
          </div>
          <h3 class="spsb-title" id="heroSelectedPlanName">১. Social Media Content Automation Engine</h3>
          <p class="spsb-desc" id="heroSelectedPlanNote">Social Media Engine — লাইফটাইম লাইসেন্স (ইংরেজি + ১টি ব্যক্তিগত ভাষা অন্তর্ভুক্ত)</p>
          <div class="spsb-addon-hint" id="addonNoteDisplay">💡 অতিরিক্ত প্রতি ভাষা মাত্র ৳<?= (int) $addonPrice ?> (নিচে থেকে বেছে নিতে পারেন)</div>
        </div>

        <div class="form-group">
          <label><span data-i18n="name">আপনার পূর্ণ নাম</span></label>
          <input name="name" required maxlength="120" autocomplete="name" placeholder="John Doe">
        </div>

        <div class="form-group">
          <label><span data-i18n="whatsapp">WhatsApp নম্বর (অ্যাক্টিভেশনের জন্য)</span></label>
          <input name="whatsapp" required placeholder="+8801..." maxlength="32" inputmode="tel">
        </div>

        <div class="form-group">
          <label><span data-i18n="email_opt">ইমেইল অ্যাড্রেস (ঐচ্ছিক)</span></label>
          <input name="email" type="email" maxlength="120" autocomplete="email" placeholder="example@mail.com">
        </div>

        <fieldset class="lang-pick">
          <legend data-i18n="pick_personal_lang">কোর প্যাকেজে ইংরেজির সাথে আপনার প্রাথমিক ভাষা বেছে নিন</legend>
          <p class="hint" data-i18n="en_included">ইংরেজি ডিফল্টভাবে সব প্যাকেজে সক্রিয় থাকে।</p>
          <div class="lang-chips" id="personalLangChips">
            <?php foreach ($langCatalog as $code => $label):
                if ($code === 'en') {
                    continue;
                }
                ?>
              <label class="chip">
                <input type="radio" name="personal_lang" value="<?= e($code) ?>" <?= $code === 'bn' ? 'checked' : '' ?> required>
                <span><?= e($label) ?> (<?= e(strtoupper($code)) ?>)</span>
              </label>
            <?php endforeach; ?>
          </div>
        </fieldset>

        <fieldset class="lang-pick">
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

        <!-- Coupon Box -->
        <div class="coupon-box">
          <label style="font-size:0.88rem; color:#93c5fd; font-weight:600;" data-i18n="coupon_label">🎟️ ডিসকাউন্ট কুপন কোড (যেমন: VIP500):</label>
          <div class="coupon-input-group">
            <input type="text" id="couponCodeInput" name="coupon_code" placeholder="কুপন কোড লিখুন" data-i18n-placeholder="coupon_placeholder">
            <button type="button" class="coupon-btn" id="applyCouponBtn" data-i18n="coupon_btn">অ্যাপ্লাই</button>
          </div>
          <div id="couponStatusMsg" class="coupon-msg"></div>
        </div>

        <div class="total-line">
          <span data-i18n="total_due">সর্বমোট পরিশোধযোগ্য</span>
          <strong id="totalDisplay">৳৩,৯৯৯</strong>
        </div>

        <button class="btn" type="submit" style="width:100%; font-size:1.1rem; padding:1rem;" data-i18n="pay_now">অর্ডার কনফার্ম করুন</button>
        <p style="text-align:center; margin-top:1rem;">
          <a class="btn-wa-inline" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="or_whatsapp">অথবা WhatsApp-এ সরাসরি অর্ডার সম্পন্ন করুন</a>
        </p>
      </form>
    </div>
  </section>

  <?php
  $approvedReviews = [];
  try {
      $revStmt = $pdo->query('SELECT name, rating, review_text, platform, avatar, channel_badge, channel_name FROM reviews WHERE is_approved = 1 ORDER BY id DESC');
      $approvedReviews = $revStmt ? $revStmt->fetchAll(PDO::FETCH_ASSOC) : [];
  } catch (\Throwable $e) {}

  if (count($approvedReviews) < 10 && function_exists('amp_get_default_50_reviews')) {
      $approvedReviews = amp_get_default_50_reviews();
  }
  ?>
  <!-- Authentic Verified Customer Reviews (Interactive Carousel Slider) -->
  <section id="reviews" class="reveal">
    <div class="section-head" style="margin-bottom: 2rem;">
      <h2 data-i18n="reviews_title">ভেরিফাইড ক্রিয়েটরদের বাস্তব মতামত ও রেটিং</h2>
      <p class="lead" data-i18n="reviews_lead">সফল ইউটিউবার, ফেসবুক পেজ ওনার এবং ডিজিটাল এজেন্সির সরাসরি অভিজ্ঞতা। স্লাইড করে অথবা বাটনে ক্লিক করে সব রিভিউ দেখতে পারেন।</p>
    </div>

    <div class="reviews-carousel-container">
      <button type="button" class="carousel-arrow prev" id="revPrevBtn" aria-label="Previous Reviews">❮</button>

      <div class="reviews-carousel-track" id="revCarouselTrack">
        <?php foreach ($approvedReviews as $rev): 
          $revPlat = (string) ($rev['platform'] ?? 'Content Creator');
          $platBadge = $rev['channel_badge'] ?? '▶️ YouTube';
          $platClass = 'plat-yt';
          if (stripos($revPlat, 'facebook') !== false || stripos($revPlat, 'islamic') !== false || stripos($revPlat, 'business') !== false) {
              $platBadge = $rev['channel_badge'] ?? '🌐 Meta / FB';
              $platClass = 'plat-fb';
          } elseif (stripos($revPlat, 'tiktok') !== false) {
              $platBadge = $rev['channel_badge'] ?? '🎵 TikTok';
              $platClass = 'plat-tt';
          } elseif (stripos($revPlat, 'agency') !== false || stripos($revPlat, 'freelancer') !== false) {
              $platBadge = $rev['channel_badge'] ?? '💼 Digital Agency';
              $platClass = 'plat-agency';
          }
          $revAvatar = !empty($rev['avatar']) ? $rev['avatar'] : '/assets/img/agents/ayesha.png';
          $chanName = !empty($rev['channel_name']) ? $rev['channel_name'] : $revPlat;
        ?>
          <article class="review-slide-card">
            <div>
              <div class="review-stars">
                <span><?= str_repeat('★', max(1, min(5, (int) ($rev['rating'] ?? 5)))) ?></span>
                <span class="verified-pill">✓ ভেরিফাইড ইউজার</span>
              </div>
              <p class="review-text">"<?= e((string) ($rev['review_text'] ?? '')) ?>"</p>
            </div>
            <div class="review-author-wrap">
              <div class="review-avatar-wrap">
                <img class="review-avatar-img" src="<?= e($revAvatar) ?>" alt="<?= e((string) ($rev['name'] ?? 'Creator')) ?>" loading="lazy" width="46" height="46">
              </div>
              <div class="review-author-details">
                <strong class="review-author-name"><?= e((string) ($rev['name'] ?? 'Creator')) ?></strong>
                <div class="review-channel-meta">
                  <span class="platform-badge <?= e($platClass) ?>"><?= e($platBadge) ?></span>
                  <span class="channel-location"><?= e($chanName) ?></span>
                </div>
              </div>
            </div>
          </article>
        <?php endforeach; ?>
      </div>

      <button type="button" class="carousel-arrow next" id="revNextBtn" aria-label="Next Reviews">❯</button>
    </div>

    <div class="carousel-controls-bottom">
      <div class="carousel-counter" id="revCounter">১ - ৩</div>
    </div>
  </section>

  <!-- FAQ Section (Fully Internationalized) -->
  <section id="faq" class="reveal">
    <div class="section-head">
      <h2 data-i18n="faq">সাধারণ জিজ্ঞাসাসমূহ (FAQ)</h2>
      <p class="lead">অটোমুভি প্রো কেনার আগে সচরাচর যে প্রশ্নগুলো সবার মনে আসে</p>
    </div>
    <div class="faq-list" id="faqDefault">
      <details open>
        <summary data-i18n="faq1_q">আমার কি ভিডিও এডিটিং-এর কোনো অভিজ্ঞতা থাকা লাগবে?</summary>
        <p data-i18n="faq1_a">না, বিন্দুমাত্র এডিটিং অভিজ্ঞতা লাগবে না! প্রিমিয়ার প্রো বা আফটার ইফেক্টসের কোনো জটিলতা নেই। আপনি শুধু নিশ বেছে দেবেন — স্ক্রিপ্ট তৈরি, বাংলা ভয়েসওভার, সিনেমাটিক সিন ও সাবটাইটেল সবকিছু অটোমুভি প্রো নিজেই স্বয়ংক্রিয়ভাবে করে দেবে।</p>
      </details>
      <details>
        <summary data-i18n="faq2_q">আমি কি এটা মোবাইল দিয়ে চালাতে পারব নাকি শুধু কম্পিউটারে চলবে?</summary>
        <p data-i18n="faq2_a">অটোমুভি প্রো একটি হাই-পারফরম্যান্স Windows ডেস্কটপ সফটওয়্যার (Windows 10/11)। তবে আমাদের স্পেশাল স্মার্টফোন কম্প্যানিয়ন UI রয়েছে, যার মাধ্যমে আপনি যেকোনো স্থান থেকে মোবাইল দিয়েই আপনার কম্পিউটারের সফটওয়্যার মনিটর ও ক্যাপচা সলভ করতে পারবেন।</p>
      </details>
      <details>
        <summary data-i18n="faq3_q">ভিডিওগুলো কি আসলেই ইউটিউব বা ফেসবুকে মনিটাইজ হবে নাকি কপিরাইট আসবে?</summary>
        <p data-i18n="faq3_a">১০০% মনিটাইজেশন ফ্রেন্ডলি! আমাদের সফটওয়্যারের প্রতিটি ভিজ্যুয়াল, ব্যাকগ্রাউন্ড মিউজিক এবং ভয়েসওভার মেটা ও ইউটিউবের সর্বশেষ পলিসি অনুযায়ী তৈরি। প্রতিটি ভিডিও অনন্য (Unique) এবং কোনো কপিরাইট ক্লেইমের ঝামেলা নেই।</p>
      </details>
      <details>
        <summary data-i18n="faq4_q">আমার পিসি বন্ধ থাকলেও কি ভিডিও অটোমেটিক আপলোড হবে?</summary>
        <p data-i18n="faq4_a">সফটওয়্যারটি আপনার কম্পিউটারের ব্যাকগ্রাউন্ডে কাজ করে। তাই শিডিউল অনুযায়ী ভিডিও তৈরি ও আপলোড হওয়ার সময় পিসি অন ও ইন্টারনেট কানেক্টেড থাকতে হবে। তবে স্ক্রিনের সামনে বসে থাকতে হয় না — পিসিতে অন্যান্য কাজ করলেও ব্যাকগ্রাউন্ডে নিরবচ্ছিন্ন আপলোড চলবে।</p>
      </details>
      <details>
        <summary data-i18n="faq5_q">৩টি সফটওয়্যার প্যাকেজের মধ্যে কোনটা আমার জন্য সেরা?</summary>
        <p data-i18n="faq5_a">১) Automovie Pro - Social Media Content Automation Engine (৳৩,৯৯৯): ফুল এআই শর্টস ও লং ভিডিও অটোমেশন এবং ইউটিউব/মেটা মনিটাইজেশনের জন্য সেরা। ২) Automovie Pro - FB Business Manager & Ad Automation Engine (৳২,৯৯৯): পেজ ও শপের সেলস ব্যানার, অ্যাড ভিডিও ও অর্গানিক গ্রুপ শেয়ারিংয়ের জন্য পারফেক্ট। ৩) Automovie Pro - FB Profile & Page Post Automation Engine (৳১,৯৯৯): ব্যক্তিগত প্রোফাইল ও পেজে ইসলামিক বা অনুপ্রেরণামূলক পোস্ট ও ফলোয়ার বৃদ্ধির জন্য সেরা।</p>
      </details>
      <details>
        <summary data-i18n="faq6_q">কেনার পর কতক্ষণ পর আমি সফটওয়্যার ডাউনলোড করতে পারব?</summary>
        <p data-i18n="faq6_a">সাথে সাথে ইনস্ট্যান্ট ডেলিভারি! অর্ডার ফর্ম সাবমিট করে পেমেন্ট সম্পন্ন হওয়ামাত্র আপনার WhatsApp ও ইমেইলে সরাসরি সফটওয়্যার ডাউনলোড লিংক, লাইসেন্স কি এবং সহজ ১-ক্লিক ভিডিও সেটআপ গাইড পাঠিয়ে দেওয়া হবে।</p>
      </details>
      <details>
        <summary data-i18n="faq7_q">লাইসেন্সের মেয়াদ কতদিন? ভবিষ্যতে কি নতুন আপডেট পাব?</summary>
        <p data-i18n="faq7_a">এটি সম্পূর্ণ লাইফটাইম লাইসেন্স (Lifetime License) — কোনো গোপন মাসিক চার্জ নেই। একবার কিনলে আজীবন ব্যবহার করতে পারবেন। এছাড়া সফটওয়্যারের সকল ভবিষ্যৎ বাগফিক্স ও পারফরম্যান্স আপডেট আজীবন ফ্রিতে পাবেন।</p>
      </details>
      <details>
        <summary data-i18n="faq8_q">আমার কম্পিউটার কনফিগারেশন কেমন হওয়া দরকার?</summary>
        <p data-i18n="faq8_a">যেকোনো সাধারণ Windows 10 বা 11 ল্যাপটপ অথবা ডেস্কটপ পিসিতে এটি মসৃণভাবে চলে। নূন্যতম 4GB RAM (8GB রেকমেন্ডেড) এবং সাধারণ ইন্টারনেট কানেকশন থাকলেই চলবে। কোনো দামি গ্রাফিক্স কার্ডের প্রয়োজন নেই।</p>
      </details>
    </div>
  </section>

  <!-- Site Footer -->
  <footer class="site-footer">
    <div>
      &copy; 2025 <?= e($brand) ?>. <span data-i18n="rights_reserved">সর্বস্বত্ব সংরক্ষিত।</span>
    </div>
    <div>
      <span data-i18n="footer_note">Windows ডেস্কটপ সফটওয়্যার — হাই-পারফরম্যান্স কন্টেন্ট অটোমেশন ইঞ্জিন।</span>
    </div>
    <div>
      <a href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp</a>
    </div>
  </footer>

  <!-- Floating Multi-Agent Live Support & WhatsApp Launcher Widget -->
  <div id="ampChat" class="amp-chat" aria-live="polite">
    <!-- 1. Sleek Floating Launcher Button -->
    <button type="button" class="amp-chat-launcher" id="ampChatLauncher" aria-label="Open Live Support">
      <div class="launcher-avatar-wrap">
        <img src="/assets/img/agents/ayesha.png" id="ampLauncherAvatar" alt="Support Agent">
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
            <img src="/assets/img/agents/ayesha.png" id="ampChoiceAvatar" alt="Support Agent">
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
            <img src="/assets/img/agents/ayesha.png" id="ampChatAvatarImg" alt="Support Agent">
          </div>
          <div class="amp-chat-name">
            <strong id="ampChatAgentName">আয়েশা (Ayesha)</strong>
            <span><span class="online-dot" style="width:6px; height:6px;"></span> <span id="ampChatAgentStatus">সিনিয়র কাস্টমার কনসালট্যান্ট</span></span>
          </div>
        </div>
        <div class="amp-chat-head-actions">
          <button type="button" class="amp-chat-sound" id="ampChatSoundToggle" title="সাউন্ড মিউট / আনমিউট">🔊</button>
          <button type="button" class="amp-chat-reset" id="ampChatReset" title="নতুন চ্যাট শুরু করুন">🔄</button>
          <button type="button" class="amp-chat-back" id="ampChatBack" title="মেনুতে ফিরুন">↩</button>
          <button type="button" class="amp-chat-close" id="ampChatClose" aria-label="Close">✕</button>
        </div>
      </header>

      <!-- Connecting Overlay (Fake Loading Simulation) -->
      <div class="amp-connecting-overlay" id="ampConnectingOverlay" style="display: none;">
        <div class="connecting-spinner-wrap">
          <div class="connecting-pulse-ring"></div>
          <div class="connecting-avatar-wrap">
            <img src="/assets/img/agents/ayesha.png" id="ampConnectingAvatar" class="connecting-avatar" alt="Agent">
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

  <script>
    document.addEventListener('DOMContentLoaded', () => {
      // 1. Verified Reviews Interactive Carousel Slider
      const track = document.getElementById('revCarouselTrack');
      const prevBtn = document.getElementById('revPrevBtn');
      const nextBtn = document.getElementById('revNextBtn');
      const counter = document.getElementById('revCounter');

      if (track) {
        const cards = track.querySelectorAll('.review-slide-card');
        const totalCards = cards.length;

        const getCardWidth = () => {
          if (!cards.length) return 340;
          return cards[0].offsetWidth + 24; // width + gap
        };

        const updateCounter = () => {
          if (!counter || totalCards === 0) return;
          const cardWidth = getCardWidth();
          const scrollPos = track.scrollLeft;
          const visibleCards = Math.max(1, Math.round(track.clientWidth / cardWidth));
          const currentIndex = Math.min(totalCards - 1, Math.max(0, Math.round(scrollPos / cardWidth)));
          const endNum = Math.min(totalCards, currentIndex + visibleCards);
          counter.textContent = `${currentIndex + 1} - ${endNum}`;
        };

        if (prevBtn) {
          prevBtn.addEventListener('click', () => {
            track.scrollBy({ left: -getCardWidth(), behavior: 'smooth' });
          });
        }

        if (nextBtn) {
          nextBtn.addEventListener('click', () => {
            const maxScroll = track.scrollWidth - track.clientWidth;
            if (track.scrollLeft >= maxScroll - 15) {
              track.scrollTo({ left: 0, behavior: 'smooth' });
            } else {
              track.scrollBy({ left: getCardWidth(), behavior: 'smooth' });
            }
          });
        }

        let autoScrollTimer = null;
        const startAutoScroll = () => {
          stopAutoScroll();
          autoScrollTimer = setInterval(() => {
            const maxScroll = track.scrollWidth - track.clientWidth;
            if (track.scrollLeft >= maxScroll - 15) {
              track.scrollTo({ left: 0, behavior: 'smooth' });
            } else {
              track.scrollBy({ left: getCardWidth(), behavior: 'smooth' });
            }
          }, 4500);
        };

        const stopAutoScroll = () => {
          if (autoScrollTimer) {
            clearInterval(autoScrollTimer);
            autoScrollTimer = null;
          }
        };

        track.addEventListener('scroll', updateCounter, { passive: true });
        track.addEventListener('mouseenter', stopAutoScroll);
        track.addEventListener('mouseleave', startAutoScroll);
        track.addEventListener('touchstart', stopAutoScroll, { passive: true });
        track.addEventListener('touchend', startAutoScroll, { passive: true });

        startAutoScroll();
        updateCounter();
      }
    });
  </script>

</body>
</html>
