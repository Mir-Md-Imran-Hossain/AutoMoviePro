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
  <link rel="stylesheet" href="/assets/css/site.css">
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
  <!-- Header Navigation -->
  <header class="site-header">
    <a class="logo-link" href="/?lang=<?= e($uiLang) ?>">
      <img class="logo-img" src="/assets/img/logo.png" alt="<?= e($brand) ?>" width="42" height="42">
      <div class="logo"><?= e($brand) ?> <span>SAAS</span></div>
    </a>
    <div class="header-actions">
       <div class="lang-switcher-wrap">
          <button type="button" class="lang-btn <?= $uiLang === 'bn' ? 'active' : '' ?>" onclick="ampSwitchLang('bn')">বাংলা</button>
          <button type="button" class="lang-btn <?= $uiLang === 'en' ? 'active' : '' ?>" onclick="ampSwitchLang('en')">English</button>
          <select id="siteLangSelect" class="lang-dropdown-compact" aria-label="Choose Language" onchange="ampSwitchLang(this.value)">
            <option value="bn" <?= $uiLang === 'bn' ? 'selected' : '' ?>>বাংলা (BN)</option>
            <option value="en" <?= $uiLang === 'en' ? 'selected' : '' ?>>English (EN)</option>
            <option value="hi" <?= $uiLang === 'hi' ? 'selected' : '' ?>>हिन्दी (HI)</option>
            <option value="ur" <?= $uiLang === 'ur' ? 'selected' : '' ?>>اردو (UR)</option>
            <option value="ta" <?= $uiLang === 'ta' ? 'selected' : '' ?>>தமிழ் (TA)</option>
            <option value="ml" <?= $uiLang === 'ml' ? 'selected' : '' ?>>മലയാളം (ML)</option>
          </select>
       </div>
      <a class="btn btn-sm btn-wa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp</a>
      <a class="btn btn-sm" href="#buy" data-i18n="buy_now">এখনই কিনুন</a>
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
          ম্যানুয়াল এডিটিং চিরতরে বন্ধ করুন। নিশ সিলেক্ট করুন একবার — আমাদের প্রো অ্যালগরিদম স্বয়ংক্রিয়ভাবে ভাইরাল স্ক্রিপ্ট, সিনেমাটিক ভিজ্যুয়াল, প্রফেশনাল ভয়েসওভার ও হার্ফবাজ সাবটাইটেল তৈরি করে ইউটিউব, ফেসবুক ও টিকটকে শিডিউল করবে।
        </p>
        <div class="cta-row">
          <a class="btn" href="#buy" data-i18n="buy_now">এখনই লাইসেন্স নিন</a>
          <a class="btn btn-ghost" href="#features" data-i18n="see_features">সব ফিচার এক্সপ্লোর করুন</a>
          <a class="btn btn-ghost btn-wa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp পরামর্শ</a>
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

  <!-- Income Matrix / Pitch Section -->
  <section id="income" class="reveal pitch-strip">
    <div class="section-head">
      <h2 data-i18n="income_title">৬×৬×৬ চ্যানেল নেটওয়ার্ক থেকে আলাদা প্যাসিভ ইনকাম</h2>
      <p class="lead" data-i18n="income_lead">একটি মাত্র প্ল্যাটফর্ম থেকে ৬টি YouTube চ্যানেল, ৬টি Facebook পেজ এবং ৬টি TikTok প্রোফাইল একযোগে পরিচালনা করুন। কোনো এডিটর হায়ার করার প্রয়োজন নেই — এক ক্লিকেই গ্লোবাল স্কেলিং।</p>
    </div>
    <div class="pitch-grid">
      <div class="pitch-card">
        <div class="pitch-card-icon">📺</div>
        <h3 data-i18n="pitch_yt">৬টি স্বতন্ত্র YouTube চ্যানেল</h3>
        <p>বিভিন্ন ভাষায় মনিটাইজড চ্যানেল গ্রো করুন এবং গ্লোবাল আরপিএম আয় করুন।</p>
      </div>
      <div class="pitch-card">
        <div class="pitch-card-icon">📱</div>
        <h3 data-i18n="pitch_fb">৬টি Facebook পেজ ও রিলস স্ট্রিম</h3>
        <p>মেটা ক্রিয়েটর প্রোগ্রাম ও অ্যাড ব্রেকস থেকে স্বয়ংক্রিয় আয়ের শক্তিশালী নেটওয়ার্ক।</p>
      </div>
      <div class="pitch-card">
        <div class="pitch-card-icon">🎵</div>
        <h3 data-i18n="pitch_tt">৬টি ভাইরাল TikTok গন্তব্য</h3>
        <p>শর্ট-ফর্ম কনটেন্টের মাধ্যমে হাইপার-গ্রোথ এবং ক্রিয়েটর রিওয়ার্ডস আর্ন করুন।</p>
      </div>
      <div class="pitch-card">
        <div class="pitch-card-icon">⏰</div>
        <h3 data-i18n="pitch_auto">ক্লাউড শিডিউলিং ও অটো-পাবলিশিং</h3>
        <p>পিসিতে বসে ঘণ্টার পর ঘণ্টা অপেক্ষা নয় — ব্যাকগ্রাউন্ডে স্বয়ংক্রিয় পাবলিশ।</p>
      </div>
    </div>
  </section>

  <!-- How It Works Section -->
  <section id="how" class="reveal">
    <div class="section-head">
      <h2 data-i18n="how_it_works">কীভাবে কাজ করে</h2>
      <p class="lead" data-i18n="how_lead">অটোমেশনের ৪টি সহজ ধাপ — আইডিয়া থেকে আন্তর্জাতিক রেভিনিউ।</p>
    </div>
    <ol class="flow-steps-grid">
      <li class="step-card">
        <div class="step-num">01</div>
        <p data-i18n="step1">নিশ সিলেক্ট করুন ও আপনার চ্যানেলগুলো নিরাপদে যুক্ত করুন (একবার লগইন)</p>
      </li>
      <li class="step-card">
        <div class="step-num">02</div>
        <p data-i18n="step2">AI স্বয়ংক্রিয়ভাবে ভাইরাল শর্টস ও লং ভিডিও তৈরি করে (স্ক্রিপ্ট + সিনেমাটিক সিন)</p>
      </li>
      <li class="step-card">
        <div class="step-num">03</div>
        <p data-i18n="step3">ইংরেজি মাস্টার থেকে স্বয়ংক্রিয়ভাবে নিখুঁত সাবটাইটেল ও লোকাল ভয়েসওভারে রূপান্তর</p>
      </li>
      <li class="step-card">
        <div class="step-num">04</div>
        <p data-i18n="step4">নির্ধারিত শিডিউল অনুযায়ী YouTube, Facebook এবং TikTok-এ সরাসরি অটো-আপলোড</p>
      </li>
    </ol>
    <?php if (trim($how) !== ''): ?>
      <div class="steps cms-block" style="max-width:800px; margin:2rem auto 0;"><?= nl2br(e($how)) ?></div>
    <?php endif; ?>
  </section>

  <!-- Feature Cards Grid -->
  <section id="features" class="reveal">
    <div class="section-head">
      <h2 data-i18n="features">পাওয়ারফুল ইন্ডাস্ট্রিয়াল ফিচারসমূহ</h2>
      <p class="lead" data-i18n="features_lead">বিশ্বমানের কনটেন্ট ক্রিয়েটর ও মিডিয়া এজেন্সির জন্য প্রস্তুত প্রতিটি টুলস। প্যাকেজ অনুযায়ী ফিল্টার করে দেখুন।</p>
    </div>

    <!-- Software Tier Filter Tabs -->
    <div class="feature-tabs-nav">
      <button type="button" class="feature-tab-btn active" data-filter="all">
        🔥 <span data-i18n="feat_tab_all">সব ফিচার (১৮টি)</span>
      </button>
      <button type="button" class="feature-tab-btn" data-filter="video_studio">
        🎬 <span data-i18n="feat_tab_video">১. Omni Video Studio (৳৩,৯৯৯)</span>
      </button>
      <button type="button" class="feature-tab-btn" data-filter="fb_business">
        💼 <span data-i18n="feat_tab_business">২. Omni FB Business Manager (৳২,৯৯৯)</span>
      </button>
      <button type="button" class="feature-tab-btn" data-filter="profile_page">
        📱 <span data-i18n="feat_tab_profile">৩. Omni FB Profile & Page Post (৳১,৯৯৯)</span>
      </button>
    </div>

    <div class="feature-grid" id="featureGrid">
      <?php foreach ($catalog as $feat):
          $f = amp_feature_for_lang($feat, $uiLang);
          $tier = $f['tier'] ?? 'video_studio';
          $img = '/assets/img/' . rawurlencode($f['image']);
          $tierBadge = [
              'video_studio' => ['cls' => 'tier-video', 'label' => '🎬 Video Studio (৳৩,৯৯৯)'],
              'fb_business' => ['cls' => 'tier-business', 'label' => '💼 FB Business (৳২,৯৯৯)'],
              'profile_page' => ['cls' => 'tier-profile', 'label' => '📱 Profile & Page (৳১,৯৯৯)'],
          ][$tier] ?? ['cls' => 'tier-video', 'label' => 'AutoMovie Pro'];
          ?>
        <article class="feature-card" data-feat-id="<?= e($f['id']) ?>" data-tier="<?= e($tier) ?>">
          <div class="feature-img-wrap">
            <span class="tier-pill <?= e($tierBadge['cls']) ?>"><?= e($tierBadge['label']) ?></span>
            <img class="feature-img" src="<?= e($img) ?>" alt="<?= e($f['title']) ?>" loading="lazy" width="800" height="450">
          </div>
          <div class="feature-card-body">
            <h3 class="feature-title"><?= e($f['title']) ?></h3>
            <p class="feature-detail"><?= e($f['detail']) ?></p>
          </div>
        </article>
      <?php endforeach; ?>
    </div>
  </section>

  <!-- SPECIAL GOOGLE AI PRO PACKAGE SECTION (Fully Internationalized) -->
  <section id="google-pro" class="reveal">
    <div class="google-pro-container">
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
            <div class="plan-price-amount">১৯৯ ৳</div>
            <ul class="plan-features-list">
              <li>✓ Gemini 3.1 & Nano API এক্সেস</li>
              <li>✓ রোবোটিকলেস প্রিমিয়াম ন্যাচারাল TTS</li>
              <li>✓ ৫০ জিবি ক্লাউড ফুটেজ স্পেস</li>
              <li>✓ ১ মাস নিরবচ্ছিন্ন মেয়াদ</li>
            </ul>
          </div>
          <a href="/order.php?product=google_pro&plan=1" class="btn" style="width:100%; text-align:center;">অর্ডার করুন (১৯৯ ৳)</a>
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

  <!-- 3 DISTINCT AUTOMOVIE PRO SOFTWARE PACKAGES -->
  <section id="software-packages" class="reveal" style="margin: 4.5rem 0;">
    <div style="max-width: 1200px; margin: 0 auto; padding: 0 1rem;">
      <div style="text-align: center; margin-bottom: 2.75rem;">
        <span class="gpro-pill" style="background: rgba(56, 189, 248, 0.2); border: 1px solid #38bdf8; color: #38bdf8;">💼 ৩টি স্বতন্ত্র অটোমেশন সফটওয়্যার প্যাকেজ</span>
        <h2 style="font-size: 2.3rem; color: #f8fafc; margin-top: 1.25rem; margin-bottom: 0.85rem;">
          আপনার প্রয়োজন অনুযায়ী সঠিক AutoMovie Pro প্যাকেজটি বেছে নিন
        </h2>
        <p class="lead" style="color: #cbd5e1; max-width: 860px; margin: 0 auto; font-size: 1.05rem;">
          প্রতিটি সফটওয়্যার সম্পূর্ণ লাইফটাইম লাইসেন্স সহ এককালীন ওয়ান-টাইম ফি। কোনো মাসিক চার্জ নেই, আজীবন ফ্রি আপডেট ও সাপোর্ট।
        </p>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.75rem;">
        <!-- Product 1: Video Studio -->
        <div style="background: rgba(11, 21, 40, 0.85); border: 2px solid #38bdf8; border-radius: var(--radius-xl); padding: 2rem; display: flex; flex-direction: column; justify-content: space-between; position: relative; box-shadow: 0 0 35px rgba(56, 189, 248, 0.15);">
          <span style="position: absolute; top: -14px; right: 24px; background: #38bdf8; color: #020617; font-size: 0.82rem; font-weight: 800; padding: 4px 14px; border-radius: 999px;">🎬 ফুল কন্টেন্ট পাওয়ারহাউজ</span>
          <div>
            <h3 style="color: #38bdf8; font-size: 1.35rem; margin-bottom: 0.5rem;">১. Omni Social Media Content Automation</h3>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 1.25rem;">
              ইউটিউব, ফেসবুক ও টিকটকের জন্য শর্ট ও লং ভিডিও তৈরি, রিলস, স্বয়ংক্রিয় শিডিউল আপলোড এবং কমেন্ট/ইনবক্স রেসপন্স।
            </p>
            <div style="margin-bottom: 1.5rem;">
              <span style="font-size: 2.3rem; font-weight: 900; color: #38bdf8;">৳৩,৯৯৯</span>
              <span style="color: #ef4444; text-decoration: line-through; font-size: 1.1rem; margin-left: 8px;">৳১০,০০০</span>
              <span style="display: block; font-size: 0.85rem; color: #64748b; margin-top: 4px;">এককালীন ওয়ান টাইম • লাইফটাইম লাইসেন্স</span>
            </div>
            <ul style="list-style: none; padding: 0; margin: 0 0 2rem; color: #cbd5e1; font-size: 0.92rem; line-height: 1.8;">
              <li>✓ সম্পূর্ণ স্বয়ংক্রিয় ভাইরাল টপিক রিসার্চ ও স্ক্রিপ্ট</li>
              <li>✓ ১০০% স্বাভাবিক মানবিক বাংলা এআই ভয়েসওভার</li>
              <li>✓ কাইনেটিক মোশন কার্ড ও সিনেমাটিক ভিজ্যুয়াল</li>
              <li>✓ ইংরেজি + ১টি ব্যক্তিগত ভাষা অন্তর্ভুক্ত</li>
              <li>✓ মাল্টি-ল্যাঙ্গুয়েজ অ্যাড-অন সুবিধা (+৳৪৯৯/ভাষা)</li>
            </ul>
          </div>
          <a href="/order.php?product=video_studio" class="btn" style="width: 100%; text-align: center; background: linear-gradient(135deg, #0284c7, #2563eb); font-weight: 700; padding: 0.9rem;">অর্ডার করুন (৳৩,৯৯৯)</a>
        </div>

        <!-- Product 2: FB Business Manager -->
        <div style="background: rgba(11, 21, 40, 0.85); border: 2px solid #f59e0b; border-radius: var(--radius-xl); padding: 2rem; display: flex; flex-direction: column; justify-content: space-between; position: relative; box-shadow: 0 0 35px rgba(245, 158, 11, 0.15);">
          <span style="position: absolute; top: -14px; right: 24px; background: #f59e0b; color: #020617; font-size: 0.82rem; font-weight: 800; padding: 4px 14px; border-radius: 999px;">💼 বিজনেস ও সেলস ম্যানেজার</span>
          <div>
            <h3 style="color: #fbbf24; font-size: 1.35rem; margin-bottom: 0.5rem;">২. Omni FB Business Manager & Ad</h3>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 1.25rem;">
              বিজনেস পেজের সেলস গ্রাফিক্স/ব্যানার তৈরি, কাইনেটিক বিজ্ঞাপন ভিডিও, গ্রুপে অর্গানিক শেয়ার এবং মেসেঞ্জার সেলস রিপ্লাই।
            </p>
            <div style="margin-bottom: 1.5rem;">
              <span style="font-size: 2.3rem; font-weight: 900; color: #fbbf24;">৳২,৯৯৯</span>
              <span style="color: #ef4444; text-decoration: line-through; font-size: 1.1rem; margin-left: 8px;">৳৮,৫০০</span>
              <span style="display: block; font-size: 0.85rem; color: #64748b; margin-top: 4px;">এককালীন ওয়ান টাইম • লাইফটাইম লাইসেন্স</span>
            </div>
            <ul style="list-style: none; padding: 0; margin: 0 0 2rem; color: #cbd5e1; font-size: 0.92rem; line-height: 1.8;">
              <li>✓ হাই-কনভার্টিং সেলস ব্যানার ও অফার গ্রাফিক্স</li>
              <li>✓ কাইনেটিক মোশন কার্ড সহ ৩০-৭০ সেকেন্ডের বিজ্ঞাপন ভিডিও</li>
              <li>✓ টার্গেটেড ফেসবুক গ্রুপে স্বয়ংক্রিয় অর্গানিক শেয়ার</li>
              <li>✓ ২৪/৭ স্মার্ট কাস্টমার ইনকোয়ারি সেলস রেসপন্স</li>
              <li>✓ প্রোডাক্ট ও সার্ভিসের স্পেশাল ক্যাম্পেইন ম্যানেজমেন্ট</li>
            </ul>
          </div>
          <a href="/order.php?product=fb_business" class="btn" style="width: 100%; text-align: center; background: linear-gradient(135deg, #d97706, #b45309); font-weight: 700; padding: 0.9rem;">অর্ডার করুন (৳২,৯৯৯)</a>
        </div>

        <!-- Product 3: Profile & Page Post -->
        <div style="background: rgba(11, 21, 40, 0.85); border: 2px solid #10b981; border-radius: var(--radius-xl); padding: 2rem; display: flex; flex-direction: column; justify-content: space-between; position: relative; box-shadow: 0 0 35px rgba(16, 185, 129, 0.15);">
          <span style="position: absolute; top: -14px; right: 24px; background: #10b981; color: #020617; font-size: 0.82rem; font-weight: 800; padding: 4px 14px; border-radius: 999px;">📝 প্রোফাইল ও পেজ অটোমেশন</span>
          <div>
            <h3 style="color: #34d399; font-size: 1.35rem; margin-bottom: 0.5rem;">৩. Omni Profile & Page Post Automation</h3>
            <p style="color: #94a3b8; font-size: 0.9rem; line-height: 1.5; margin-bottom: 1.25rem;">
              ব্যক্তিগত প্রোফাইল ও পেজের জন্য নির্দিষ্ট নিসভিত্তিক পোস্ট রাইটিং, ব্রান্ডেড কোট ব্যানার ও গ্রুপে অর্গানিক শেয়ার।
            </p>
            <div style="margin-bottom: 1.5rem;">
              <span style="font-size: 2.3rem; font-weight: 900; color: #34d399;">৳১,৯৯৯</span>
              <span style="color: #ef4444; text-decoration: line-through; font-size: 1.1rem; margin-left: 8px;">৳৬,৫০০</span>
              <span style="display: block; font-size: 0.85rem; color: #64748b; margin-top: 4px;">এককালীন ওয়ান টাইম • লাইফটাইম লাইসেন্স</span>
            </div>
            <ul style="list-style: none; padding: 0; margin: 0 0 2rem; color: #cbd5e1; font-size: 0.92rem; line-height: 1.8;">
              <li>✓ খাঁটি ইসলামিক হাদিস/কোরআন বা অনুপ্রেরণামূলক পোস্ট</li>
              <li>✓ স্বয়ংক্রিয় গোল্ডেন এমবলেম ব্যানার ও ফটো ফ্রেম</li>
              <li>✓ ফেসবুক প্রোফাইল ও পেজে হিউম্যান-লাইক শিডিউল পোস্ট</li>
              <li>✓ ইসলামিক ও শিক্ষণীয় গ্রুপে নিরাপদ অর্গানিক শেয়ারিং</li>
              <li>✓ ফ্রেন্ড ও ফলোয়ার এনগেজমেন্ট অটোমেশন</li>
            </ul>
          </div>
          <a href="/order.php?product=profile_page" class="btn" style="width: 100%; text-align: center; background: linear-gradient(135deg, #059669, #047857); font-weight: 700; padding: 0.9rem;">অর্ডার করুন (৳১,৯৯৯)</a>
        </div>
      </div>
    </div>
  </section>

  <!-- Core Software Purchase Form -->
  <section id="buy" class="reveal">
    <div class="purchase-wrapper">
      <div class="section-head" style="margin-bottom: 2rem;">
        <h2 data-i18n="purchase">অর্ডার ও লাইসেন্সিং</h2>
        <div class="price-block">
          <div class="amount">৳<?= e((string) (int) $price) ?></div>
          <div class="lead" data-i18n="price_base_note">লাইফটাইম লাইসেন্স — ইংরেজি + আপনার পছন্দের ১টি ভাষা অন্তর্ভুক্ত</div>
          <p class="addon-note" data-i18n="price_addon_note" data-i18n-vars='<?= e(json_encode(["n" => (int) $addonPrice], JSON_UNESCAPED_UNICODE)) ?>'>অতিরিক্ত প্রতি ভাষা মাত্র ৳<?= (int) $addonPrice ?></p>
        </div>
      </div>

      <form class="purchase" method="post" action="/purchase.php" id="purchaseForm">
        <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
        <input type="hidden" name="plan_name" value="Lifetime Core">
        <input type="hidden" name="amount" id="orderAmount" value="<?= e((string) (int) $price) ?>">
        <input type="hidden" name="base_langs" id="baseLangs" value="en,">
        <input type="hidden" name="addon_langs" id="addonLangs" value="">

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
          <label style="font-size:0.88rem; color:#93c5fd; font-weight:600;" data-i18n="coupon_label">🎟️ ডিসকাউন্ট কুপন কোড (যেমন: LAUNCH500):</label>
          <div class="coupon-input-group">
            <input type="text" id="couponCodeInput" name="coupon_code" placeholder="কুপন কোড লিখুন" data-i18n-placeholder="coupon_placeholder">
            <button type="button" class="coupon-btn" id="applyCouponBtn" data-i18n="coupon_btn">অ্যাপ্লাই</button>
          </div>
          <div id="couponStatusMsg" class="coupon-msg"></div>
        </div>

        <div class="total-line">
          <span data-i18n="total_due">সর্বমোট পরিশোধযোগ্য</span>
          <strong id="totalDisplay">৳<?= (int) $price ?></strong>
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
      $revStmt = $pdo->query('SELECT name, rating, review_text, platform FROM reviews WHERE is_approved = 1 ORDER BY id DESC');
      $approvedReviews = $revStmt ? $revStmt->fetchAll(PDO::FETCH_ASSOC) : [];
  } catch (\Throwable $e) {}

  if (count($approvedReviews) < 10 && function_exists('amp_get_default_50_reviews')) {
      $approvedReviews = amp_get_default_50_reviews();
  }
  $halfCount = (int) ceil(count($approvedReviews) / 2);
  $row1 = array_slice($approvedReviews, 0, $halfCount);
  $row2 = array_slice($approvedReviews, $halfCount);
  ?>
  <!-- Authentic Verified Customer Reviews (50+ Infinite Marquee Slider) -->
  <section id="reviews" class="reveal">
    <div class="section-head" style="margin-bottom: 2rem;">
      <div class="gpro-pill" style="margin-bottom: 0.75rem; background: linear-gradient(135deg, #f59e0b, #d97706); box-shadow: 0 0 20px rgba(245, 158, 11, 0.4);">
        🌟 ৫০+ সফল কন্টেন্ট ক্রিয়েটরের বাস্তব অভিজ্ঞতা
      </div>
      <h2 data-i18n="reviews_title">ভেরিফাইড ক্রিয়েটরদের বাস্তব মতামত ও রেটিং</h2>
      <p class="lead" data-i18n="reviews_lead">সফল ইউটিউবার, ফেসবুক পেজ ওনার এবং ডিজিটাল এজেন্সির সরাসরি অভিজ্ঞতা। মাউস রেখে যেকোনো রিভিউ থামিয়ে পড়তে পারেন।</p>
    </div>

    <div class="reviews-section-wrapper">
      <!-- Top Row Marquee (Scrolls Left) -->
      <div class="review-marquee-track track-top">
        <?php foreach (array_merge($row1, $row1) as $rev): ?>
          <article class="review-card-marquee">
            <div>
              <div class="review-stars">
                <span><?= str_repeat('★', max(1, min(5, (int) ($rev['rating'] ?? 5)))) ?></span>
                <span class="verified-pill">✓ ভেরিফাইড ইউজার</span>
              </div>
              <p class="review-text">"<?= e((string) ($rev['review_text'] ?? '')) ?>"</p>
            </div>
            <div class="review-author">
              <strong><?= e((string) ($rev['name'] ?? 'Creator')) ?></strong>
              <?php if (!empty($rev['platform'])): ?>
                <span class="platform-badge"><?= e((string) $rev['platform']) ?></span>
              <?php endif; ?>
            </div>
          </article>
        <?php endforeach; ?>
      </div>

      <!-- Bottom Row Marquee (Scrolls Right) -->
      <div class="review-marquee-track track-bottom">
        <?php foreach (array_merge($row2, $row2) as $rev): ?>
          <article class="review-card-marquee">
            <div>
              <div class="review-stars">
                <span><?= str_repeat('★', max(1, min(5, (int) ($rev['rating'] ?? 5)))) ?></span>
                <span class="verified-pill">✓ ভেরিফাইড ইউজার</span>
              </div>
              <p class="review-text">"<?= e((string) ($rev['review_text'] ?? '')) ?>"</p>
            </div>
            <div class="review-author">
              <strong><?= e((string) ($rev['name'] ?? 'Creator')) ?></strong>
              <?php if (!empty($rev['platform'])): ?>
                <span class="platform-badge"><?= e((string) $rev['platform']) ?></span>
              <?php endif; ?>
            </div>
          </article>
        <?php endforeach; ?>
      </div>
    </div>
  </section>
          </div>
        </article>
      <?php endforeach; ?>
    </div>
  </section>
  <?php endif; ?>

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
        <p data-i18n="faq5_a">১) Omni Video Studio (৳৩,৯৯৯): ফুল এআই শর্টস ও লং ভিডিও অটোমেশন এবং ইউটিউব/মেটা মনিটাইজেশনের জন্য সেরা। ২) Omni FB Business Manager (৳২,৯৯৯): পেজ ও শপের সেলস ব্যানার, অ্যাড ভিডিও ও অর্গানিক গ্রুপ শেয়ারিংয়ের জন্য পারফেক্ট। ৩) Omni Profile & Page Post (৳১,৯৯৯): ব্যক্তিগত প্রোফাইল ও পেজে ইসলামিক বা অনুপ্রেরণামূলক পোস্ট ও ফলোয়ার বৃদ্ধির জন্য সেরা।</p>
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
    <?php if (trim($faq) !== ''): ?>
      <div class="steps cms-block" style="max-width:820px; margin:2rem auto 0;"><?= nl2br(e($faq)) ?></div>
    <?php endif; ?>
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

  <!-- Floating Multi-Agent Live Support Widget -->
  <div id="ampChat" class="amp-chat" aria-live="polite">
    <button type="button" class="amp-chat-toggle" id="ampChatToggle">
      <span class="online-dot"></span>
      <span data-i18n="agent_toggle_btn">💬 লাইভ সাপোর্ট টিম (অনলাইন)</span>
    </button>
    <div class="amp-chat-panel is-hidden" id="ampChatPanel" hidden style="display: none;">
      <header class="amp-chat-head">
        <div class="amp-chat-agent-info">
          <div class="amp-chat-avatar" id="ampChatAvatar">
            <img src="/assets/img/agents/ayesha.png" id="ampChatAvatarImg" alt="Support Agent">
          </div>
          <div class="amp-chat-name">
            <strong id="ampChatAgentName" data-i18n="agent_name">আয়েশা (Ayesha)</strong>
            <span><span class="online-dot" style="width:6px; height:6px;"></span> <span id="ampChatAgentStatus" data-i18n="agent_status">সিনিয়র কাস্টমার কনসালট্যান্ট</span></span>
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

  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const tabBtns = document.querySelectorAll('.feature-tab-btn');
      const featCards = document.querySelectorAll('.feature-card');
      tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          tabBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const filter = btn.getAttribute('data-filter');
          featCards.forEach(card => {
            const cardTier = card.getAttribute('data-tier');
            if (filter === 'all' || cardTier === filter) {
              card.style.display = 'flex';
              setTimeout(() => { card.style.opacity = '1'; }, 10);
            } else {
              card.style.display = 'none';
            }
          });
        });
      });
    });
  </script>

</body>
</html>
