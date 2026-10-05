<?php
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';

$uiLang = strtolower(substr((string) ($_GET['lang'] ?? $_COOKIE['amp_ui_lang'] ?? 'bn'), 0, 2));
if (!in_array($uiLang, amp_cms_langs(), true)) {
    $uiLang = 'bn';
}

$brand = setting_i18n($pdo, 'hero_brand', $uiLang, setting($pdo, 'hero_brand', 'AutoMovie Pro')) ?? 'AutoMovie Pro';
$tagline = setting_i18n($pdo, 'hero_tagline', $uiLang, '') ?? '';
$cta = setting_i18n($pdo, 'hero_cta', $uiLang, '') ?? '';
$price = (float) setting($pdo, 'price_amount', '2998');
$addonPrice = (float) setting($pdo, 'language_addon_price', '499');
$priceLabel = setting_i18n($pdo, 'price_label', $uiLang, '') ?? '';
$how = setting_i18n($pdo, 'how_it_works', $uiLang, '') ?? '';
$faq = setting_i18n($pdo, 'faq_text', $uiLang, '') ?? '';
$metaTitle = setting_i18n($pdo, 'meta_title', $uiLang, 'AutoMovie Pro — Auto Video for 6 Markets') ?? 'AutoMovie Pro';
$metaDesc = setting_i18n(
    $pdo,
    'meta_description',
    $uiLang,
    'AutoMovie Pro: auto short & long videos, 6 languages, up to 6 YouTube + 6 Facebook + 6 TikTok channels. Lifetime from ৳2998 (2 languages).'
) ?? '';
$siteUrl = rtrim((string) ($config['site_url'] ?? ''), '/');
$waLink = amp_whatsapp_sales_link(
    "Hi! I want AutoMovie Pro (৳{$price} for 2 languages). Please help me order."
);
$catalog = amp_features_catalog();
$langCatalog = amp_lang_catalog();
$useCmsTagline = trim($tagline) !== '';
$useCmsCta = trim($cta) !== '';
$useCmsPriceLabel = trim($priceLabel) !== '';

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
  <header class="site-header">
    <a class="logo-link" href="/?lang=<?= e($uiLang) ?>">
      <img class="logo-img" src="/assets/img/logo.png" alt="<?= e($brand) ?>" width="40" height="40">
      <div class="logo"><?= e($brand) ?> <span>SAAS</span></div>
    </a>
    <div class="header-actions">
      <select id="siteLangSelect" aria-label="Language"></select>
      <a class="btn btn-sm btn-wa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp</a>
      <?php if ($useCmsCta): ?>
        <a class="btn btn-sm" href="#buy"><?= e($cta) ?></a>
      <?php else: ?>
        <a class="btn btn-sm" href="#buy" data-i18n="buy_now">এখনই কিনুন</a>
      <?php endif; ?>
    </div>
  </header>

  <section class="hero">
    <div class="hero-brand-block">
      <img class="hero-logo" src="/assets/img/logo.png" alt="<?= e($brand) ?>" width="96" height="96">
      <h1 class="hero-brand"><?= e($brand) ?></h1>
      <?php if ($useCmsTagline): ?>
        <p class="hero-tag"><?= e($tagline) ?></p>
      <?php else: ?>
        <p class="hero-tag" data-i18n="site_tagline">নিশ সিলেক্ট করুন — ৬ ভাষায় অটো ভিডিও ও মাল্টি-চ্যানেল আপলোড</p>
      <?php endif; ?>
      <div class="cta-row">
        <?php if ($useCmsCta): ?>
          <a class="btn" href="#buy"><?= e($cta) ?></a>
        <?php else: ?>
          <a class="btn" href="#buy" data-i18n="buy_now">এখনই কিনুন</a>
        <?php endif; ?>
        <a class="btn btn-ghost" href="#features" data-i18n="see_features">সব ফিচার দেখুন</a>
        <a class="btn btn-ghost btn-wa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp</a>
      </div>
    </div>
  </section>

  <section id="income" class="reveal pitch-strip">
    <h2 data-i18n="income_title">৬×৬×৬ চ্যানেল থেকে আলাদা আলাদা ইনকাম</h2>
    <p class="lead" data-i18n="income_lead">একটি সফটওয়্যার — ৬টি YouTube, ৬টি Facebook, ৬টি TikTok গন্তব্য। ভিডিও জেনারেশনে আলাদা সময় নষ্ট নয়; স্বপ্নের কনটেন্ট ক্রিয়েটর হয়ে উঠুন।</p>
    <ul class="pitch-points">
      <li data-i18n="pitch_yt">৬টি YouTube চ্যানেল আলাদা আলাদা বাজারে</li>
      <li data-i18n="pitch_fb">৬টি Facebook পেজ/প্রোফাইল স্ট্রিম</li>
      <li data-i18n="pitch_tt">৬টি TikTok গন্তব্য</li>
      <li data-i18n="pitch_auto">শেডিউল চালু রাখুন — PC-তে বসে এডিট করতে হবে না</li>
    </ul>
  </section>

  <section id="how" class="reveal">
    <h2 data-i18n="how_it_works">কীভাবে কাজ করে</h2>
    <p class="lead" data-i18n="how_lead">নিশ বেছে নিন → অটো জেনারেট → লোকালাইজ → মাল্টি-চ্যানেলে আপলোড।</p>
    <ol class="flow-steps">
      <li data-i18n="step1">নিশ ও চ্যানেল কানেক্ট (একবার লগইন / কুকি সেভ)</li>
      <li data-i18n="step2">শর্ট বা লং ভিডিও অটো তৈরি (Agnes বা ইমেজ→ভিডিও)</li>
      <li data-i18n="step3">ইংরেজি মাস্টার থেকে অন্য ভাষায় ভয়েস + সাবটাইটেল</li>
      <li data-i18n="step4">শিডিউল অনুযায়ী YouTube / Facebook / TikTok-এ পাঠান</li>
    </ol>
    <?php if (trim($how) !== ''): ?>
      <div class="steps cms-block"><?= nl2br(e($how)) ?></div>
    <?php endif; ?>
  </section>

  <section id="features" class="reveal">
    <h2 data-i18n="features">ফিচার</h2>
    <p class="lead" data-i18n="features_lead">প্রতিটি ফিচার — সংক্ষিপ্ত নাম এবং কীভাবে কাজ করে।</p>
    <div class="feature-grid" id="featureGrid">
      <?php foreach ($catalog as $feat):
          $f = amp_feature_for_lang($feat, $uiLang);
          $img = '/assets/img/' . rawurlencode($f['image']);
          ?>
        <article class="feature-card" data-feat-id="<?= e($f['id']) ?>">
          <img class="feature-img" src="<?= e($img) ?>" alt="<?= e($f['title']) ?>" loading="lazy" width="640" height="360">
          <h3 class="feature-title"><?= e($f['title']) ?></h3>
          <p class="feature-detail"><?= e($f['detail']) ?></p>
        </article>
      <?php endforeach; ?>
    </div>
  </section>

  <!-- SPECIAL GOOGLE AI PRO PACKAGE SECTION -->
  <section id="google-pro" class="reveal" style="background: linear-gradient(145deg, #0b1528, #070d18); border: 2px solid #2563eb; border-radius: 24px; padding: 3rem 1.5rem; margin: 3.5rem auto; max-width: 1100px; box-shadow: 0 20px 50px rgba(37, 99, 235, 0.25);">
    <div style="text-align: center; margin-bottom: 2.5rem;">
      <span style="background: #2563eb; color: #ffffff; font-size: 0.82rem; font-weight: 700; padding: 6px 16px; border-radius: 9999px; text-transform: uppercase; letter-spacing: 1px; display: inline-block; box-shadow: 0 0 15px rgba(37,99,235,0.6);">স্পেশাল অফার</span>
      <h2 style="font-size: 2rem; color: #60a5fa; margin-top: 1rem; margin-bottom: 0.75rem; font-weight: 800;">কোন ঝামেলা ছাড়াই ভিডিও তৈরির জন্য স্পেশাল গুগল AI Pro প্যাকেজ</h2>
      <p class="lead" style="color: #cbd5e1; max-width: 820px; margin: 0 auto; font-size: 1.05rem;">
        কোটা লিমিটেশন বা রোবট সাউন্ডের ঝামেলা ছাড়া আনলিমিটেড ক্রিয়েশন! সরাসরি গুগল প্রো ক্লাউড, হাই-রেজুলেশন মডেল ও নিরাপদ ১৫০ জিবি ড্রাইভ ব্যাকআপ।
      </p>
    </div>

    <!-- Feature Highlights -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.25rem; margin-bottom: 3rem;">
      <div style="background: #111d33; border: 1px solid #1e3a8a; border-radius: 14px; padding: 1.25rem; display: flex; gap: 1rem; align-items: flex-start;">
        <span style="font-size: 1.8rem; line-height: 1;">⚡</span>
        <div>
          <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;">গুগল Nano Banana ও VEO-3 স্পেশাল API</strong>
          <span style="color: #94a3b8; font-size: 0.9rem;">আল্ট্রা-এইচডি সিনেমাটিক ভিডিও সিন ও প্রফেশনাল ইমেজ জেনারেশন ফুল এক্সেস।</span>
        </div>
      </div>

      <div style="background: #111d33; border: 1px solid #1e3a8a; border-radius: 14px; padding: 1.25rem; display: flex; gap: 1rem; align-items: flex-start;">
        <span style="font-size: 1.8rem; line-height: 1;">🎙️</span>
        <div>
          <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;">আল্ট্রা-ন্যাচারাল রোবোটিকলেস TTS</strong>
          <span style="color: #94a3b8; font-size: 0.9rem;">১০০% মানবিক অনুভূতির বাংলা ও বহুভাষিক ভয়েসওভার — রোবোটিক টোনহীন।</span>
        </div>
      </div>

      <div style="background: #111d33; border: 1px solid #1e3a8a; border-radius: 14px; padding: 1.25rem; display: flex; gap: 1rem; align-items: flex-start;">
        <span style="font-size: 1.8rem; line-height: 1;">📈</span>
        <div>
          <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;">হাই CTR এসইও টপিক ও স্ক্রিপ্ট</strong>
          <span style="color: #94a3b8; font-size: 0.9rem;">ইউটিউব ও মেটা অ্যালগরিদম টার্গেটেড ভাইরাল টপিক রিসার্চ ও এঙ্গেজিং হুক।</span>
        </div>
      </div>

      <div style="background: #111d33; border: 1px solid #1e3a8a; border-radius: 14px; padding: 1.25rem; display: flex; gap: 1rem; align-items: flex-start;">
        <span style="font-size: 1.8rem; line-height: 1;">💬</span>
        <div>
          <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;">২৪/৭ আনলিমিটেড চ্যাটিং ও মনিটরিং</strong>
          <span style="color: #94a3b8; font-size: 0.9rem;">যেকোনো টেকনিক্যাল সাপোর্টে সার্বক্ষণিক ডেডিকেটেড এআই ও হিউম্যান টিম সহায়তা।</span>
        </div>
      </div>

      <div style="background: #111d33; border: 1px solid #1e3a8a; border-radius: 14px; padding: 1.25rem; display: flex; gap: 1rem; align-items: flex-start; grid-column: 1 / -1;">
        <span style="font-size: 1.8rem; line-height: 1;">☁️</span>
        <div>
          <strong style="color: #93c5fd; font-size: 1.05rem; display: block; margin-bottom: 0.25rem;">ফুটেজ স্টোরের জন্য ১৫০ জিবি গুগল ক্লাউড স্টোরেজ</strong>
          <span style="color: #94a3b8; font-size: 0.9rem;">ভিডিও, অডিও ও মেটাডাটা ব্যাকআপের জন্য ডেডিকেটেড হাই-স্পিড গুগল ড্রাইভ ভল্ট সরাসরি আপনার অ্যাকাউন্টে কনফিগার করা হবে।</span>
        </div>
      </div>
    </div>

    <!-- 3 Pricing Plans -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.5rem; max-width: 960px; margin: 0 auto;">
      <!-- Plan 1 -->
      <div style="background: #0f172a; border: 1px solid #334155; border-radius: 18px; padding: 2rem 1.5rem; text-align: center; display: flex; flex-direction: column; justify-content: space-between; transition: transform 0.2s;">
        <div>
          <h3 style="color: #e2e8f0; font-size: 1.25rem; margin-bottom: 0.5rem;">মাসিক প্ল্যান</h3>
          <p style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 1.25rem;">৩০ দিনের ফুল প্রো এক্সেস</p>
          <div style="font-size: 2.25rem; font-weight: 800; color: #38bdf8; margin-bottom: 1rem;">১২০ ৳</div>
          <ul style="list-style: none; padding: 0; margin: 0 0 1.5rem; text-align: left; font-size: 0.88rem; color: #cbd5e1; line-height: 1.8;">
            <li>✓ Nano Banana & Veo-3 API</li>
            <li>✓ রোবোটিকলেস প্রিমিয়াম TTS</li>
            <li>✓ ১৫০ জিবি গুগল ক্লাউড ড্রাইভ</li>
            <li>✓ ১ মাস ভ্যালিডিটি</li>
          </ul>
        </div>
        <a href="/order.php?product=google_pro&plan=1" class="btn" style="width: 100%; padding: 0.75rem; background: #0284c7; text-align: center;">অর্ডার করুন (১২০ ৳)</a>
      </div>

      <!-- Plan 2 -->
      <div style="background: #0f172a; border: 2px solid #38bdf8; border-radius: 18px; padding: 2rem 1.5rem; text-align: center; display: flex; flex-direction: column; justify-content: space-between; position: relative; box-shadow: 0 10px 30px rgba(56,189,248,0.2);">
        <span style="position: absolute; top: -12px; left: 50%; transform: translateX(-50%); background: #38bdf8; color: #04111d; font-size: 0.75rem; font-weight: 800; padding: 3px 12px; border-radius: 9999px;">জনপ্রিয় চয়েস</span>
        <div>
          <h3 style="color: #ffffff; font-size: 1.25rem; margin-bottom: 0.5rem;">বাৎসরিক প্ল্যান</h3>
          <p style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 1.25rem;">১২ মাসের আনলিমিটেড সার্ভিস</p>
          <div style="font-size: 2.25rem; font-weight: 800; color: #38bdf8; margin-bottom: 1rem;">৯৯৯ ৳</div>
          <ul style="list-style: none; padding: 0; margin: 0 0 1.5rem; text-align: left; font-size: 0.88rem; color: #cbd5e1; line-height: 1.8;">
            <li>✓ Nano Banana & Veo-3 API</li>
            <li>✓ রোবোটিকলেস প্রিমিয়াম TTS</li>
            <li>✓ ১৫০ জিবি গুগল ক্লাউড ড্রাইভ</li>
            <li>✓ ১২ মাস নিরবচ্ছিন্ন ভ্যালিডিটি</li>
            <li>✓ স্পেশাল ডিসকাউন্ট সেভিংস</li>
          </ul>
        </div>
        <a href="/order.php?product=google_pro&plan=12" class="btn" style="width: 100%; padding: 0.75rem; background: linear-gradient(135deg, #0284c7, #2563eb); font-weight: 700; text-align: center;">অর্ডার করুন (৯৯৯ ৳)</a>
      </div>

      <!-- Plan 3 -->
      <div style="background: #0f172a; border: 1px solid #334155; border-radius: 18px; padding: 2rem 1.5rem; text-align: center; display: flex; flex-direction: column; justify-content: space-between;">
        <div>
          <h3 style="color: #e2e8f0; font-size: 1.25rem; margin-bottom: 0.5rem;">স্পেশাল প্ল্যান</h3>
          <p style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 1.25rem;">১৮ মাসের দীর্ঘমেয়াদী প্যাকেজ</p>
          <div style="font-size: 2.25rem; font-weight: 800; color: #38bdf8; margin-bottom: 1rem;">১২৯৯ ৳</div>
          <ul style="list-style: none; padding: 0; margin: 0 0 1.5rem; text-align: left; font-size: 0.88rem; color: #cbd5e1; line-height: 1.8;">
            <li>✓ Nano Banana & Veo-3 API</li>
            <li>✓ রোবোটিকলেস প্রিমিয়াম TTS</li>
            <li>✓ ১৫০ জিবি গুগল ক্লাউড ড্রাইভ</li>
            <li>✓ ১৮ মাস সম্পূর্ণ লাইসেন্স মেয়াদ</li>
            <li>✓ ভিআইপি প্রায়োরিটি সাপোর্ট</li>
          </ul>
        </div>
        <a href="/order.php?product=google_pro&plan=18" class="btn" style="width: 100%; padding: 0.75rem; background: #0284c7; text-align: center;">অর্ডার করুন (১২৯৯ ৳)</a>
      </div>
    </div>
  </section>

  <section id="buy" class="reveal">
    <h2 data-i18n="purchase">পারচেজ</h2>
    <div class="price-block">
      <div class="amount">৳<?= e((string) (int) $price) ?></div>
      <?php if ($useCmsPriceLabel): ?>
        <div class="lead"><?= e($priceLabel) ?></div>
      <?php else: ?>
        <div class="lead" data-i18n="price_base_note">লাইফটাইম — ইংরেজি + আপনার দেশের ১টি ভাষা সহ</div>
      <?php endif; ?>
      <p class="addon-note" data-i18n="price_addon_note" data-i18n-vars='<?= e(json_encode(["n" => (int) $addonPrice], JSON_UNESCAPED_UNICODE)) ?>'>অতিরিক্ত প্রতি ভাষা ৳<?= (int) $addonPrice ?></p>
    </div>

    <form class="purchase" method="post" action="/purchase.php" id="purchaseForm">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="plan_name" value="Lifetime Core">
      <input type="hidden" name="amount" id="orderAmount" value="<?= e((string) (int) $price) ?>">
      <input type="hidden" name="base_langs" id="baseLangs" value="en,">
      <input type="hidden" name="addon_langs" id="addonLangs" value="">

      <label><span data-i18n="name">নাম</span> <input name="name" required maxlength="120" autocomplete="name"></label>
      <label><span data-i18n="whatsapp">WhatsApp নম্বর</span> <input name="whatsapp" required placeholder="8801..." maxlength="32" inputmode="tel"></label>
      <label><span data-i18n="email_opt">ইমেইল (ঐচ্ছিক)</span> <input name="email" type="email" maxlength="120" autocomplete="email"></label>

      <fieldset class="lang-pick">
        <legend data-i18n="pick_personal_lang">কোর প্যাকেজে ইংরেজি + আপনার ভাষা</legend>
        <p class="hint" data-i18n="en_included">ইংরেজি সবসময় অন্তর্ভুক্ত।</p>
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
        <legend data-i18n="pick_addon_langs">অতিরিক্ত ভাষা আনলক (+৳<?= (int) $addonPrice ?> / ভাষা)</legend>
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

      <div class="coupon-box">
        <label style="font-size:0.85rem; color:#94a3b8;">🎟️ ডিসকাউন্ট কুপন কোড (যেমন: LAUNCH500):</label>
        <div class="coupon-input-group">
          <input type="text" id="couponCodeInput" name="coupon_code" placeholder="কুপন কোড লিখুন" style="max-width:200px;">
          <button type="button" class="coupon-btn" id="applyCouponBtn">অ্যাপ্লাই</button>
        </div>
        <div id="couponStatusMsg" class="coupon-msg"></div>
      </div>

      <div class="total-line">
        <span data-i18n="total_due">মোট</span>
        <strong id="totalDisplay">৳<?= (int) $price ?></strong>
      </div>

      <button class="btn" type="submit" data-i18n="pay_now">অর্ডার কনফার্ম করুন</button>
      <p class="hint"><a class="btn-wa-inline" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="or_whatsapp">অথবা WhatsApp-এ অর্ডার করুন</a></p>
    </form>
  </section>

  <?php
  $revStmt = $pdo->query('SELECT name, rating, review_text, platform FROM reviews WHERE is_approved = 1 ORDER BY id DESC LIMIT 6');
  $approvedReviews = $revStmt ? $revStmt->fetchAll(PDO::FETCH_ASSOC) : [];
  ?>
  <?php if (!empty($approvedReviews)): ?>
  <!-- Authentic Verified Customer Reviews (No fake dummy reviews) -->
  <section id="reviews" class="reveal" style="margin: 4rem 0;">
    <h2 style="text-align:center; font-size:2rem; margin-bottom:0.5rem;">🌟 গ্রাহকদের অভিজ্ঞতা ও রিভিউ</h2>
    <p class="lead" style="text-align:center; color:#94a3b8; max-width:650px; margin:0 auto 2.5rem auto;">
      অটোমুভি প্রো ব্যবহারকারী গ্রাহকদের সরাসরি মতামত।
    </p>

    <div class="review-grid" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:1.5rem;">
      <?php foreach ($approvedReviews as $rev): ?>
        <article style="background:#0f172a; border:1px solid #1e293b; border-radius:14px; padding:1.5rem; box-shadow:0 8px 20px rgba(0,0,0,0.15);">
          <div style="color:#f59e0b; font-size:1.2rem; margin-bottom:0.5rem;">
            <?= str_repeat('★', max(1, min(5, (int) ($rev['rating'] ?? 5)))) ?>
          </div>
          <p style="color:#cbd5e1; font-size:0.95rem; line-height:1.6; margin-bottom:1rem;">
            "<?= e((string) ($rev['review_text'] ?? '')) ?>"
          </p>
          <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.85rem; color:#64748b; border-top:1px solid #1e293b; padding-top:0.75rem;">
            <strong style="color:#e2e8f0;"><?= e((string) ($rev['name'] ?? 'গ্রাহক')) ?></strong>
            <?php if (!empty($rev['platform'])): ?>
              <span style="background:#1e293b; padding:2px 8px; border-radius:6px; color:#38bdf8;"><?= e((string) $rev['platform']) ?></span>
            <?php endif; ?>
          </div>
        </article>
      <?php endforeach; ?>
    </div>
  </section>
  <?php endif; ?>

  <section id="faq" class="reveal">
    <h2 data-i18n="faq">FAQ</h2>
    <div class="faq-list" id="faqDefault">
      <details open>
        <summary data-i18n="faq1_q">প্রাইস কত?</summary>
        <p data-i18n="faq1_a">৳২৯৯৮ = ইংরেজি + ১টি ব্যক্তিগত ভাষা। প্রতিটি অতিরিক্ত ভাষা ৳৪৯৯।</p>
      </details>
      <details>
        <summary data-i18n="faq2_q">কতগুলো চ্যানেল যোগ করা যায়?</summary>
        <p data-i18n="faq2_a">প্রতি ভাষা/বাজার স্ট্র্যাটেজিতে মিলিয়ে সর্বোচ্চ ৬ YouTube + ৬ Facebook + ৬ TikTok গন্তব্য।</p>
      </details>
      <details>
        <summary data-i18n="faq3_q">পেমেন্ট কীভাবে?</summary>
        <p data-i18n="faq3_a">অর্ডার সাবমিটের পর WhatsApp-এ স্ক্রিনশট পাঠান — টিম ম্যানুয়ালি অ্যাক্টিভেট করবে।</p>
      </details>
      <details>
        <summary>লাইসেন্সের মেয়াদ কতদিন? নতুন আপডেট আসলে কী হবে?</summary>
        <p>AutoMovie Pro এর মূল লাইসেন্স সম্পূর্ণ <strong>আজীবন মেয়াদের (Lifetime License)</strong>। কোনো মাসিক সাবস্ক্রিপশন ফি নেই। ভবিষ্যতে নতুন কোনো বড় মেগা ফিচার, বিশেষ ফাংশনালিটি বা নতুন প্রিমিয়াম থিম যুক্ত হলে কেবল সেই নির্দিষ্ট অ্যাড-অনগুলোর জন্য সামান্য ফি প্রদান করতে হবে। আপনার কোর লাইসেন্স আজীবন সক্রিয় থাকবে।</p>
      </details>
    </div>
    <?php if (trim($faq) !== ''): ?>
      <div class="steps cms-block"><?= nl2br(e($faq)) ?></div>
    <?php endif; ?>
  </section>

  <footer class="site-footer">
    &copy; <?= date('Y') ?> <?= e($brand) ?>.
    <span data-i18n="footer_note">Windows ডেস্কটপ সফটওয়্যার।</span>
    <a href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="chat_whatsapp">WhatsApp</a>
  </footer>

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
