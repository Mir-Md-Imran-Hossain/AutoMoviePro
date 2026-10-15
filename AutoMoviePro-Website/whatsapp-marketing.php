<?php
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';

$uiLang = strtolower(substr((string) ($_GET['lang'] ?? $_COOKIE['amp_ui_lang'] ?? 'bn'), 0, 2));
if (!in_array($uiLang, amp_cms_langs(), true)) {
    $uiLang = 'bn';
}

$brand = 'WAManager Pro';
$siteUrl = rtrim((string) ($config['site_url'] ?? 'https://automoviepro.com'), '/');
$waLink = amp_whatsapp_sales_link('Hi! I want to order WAManager Pro WhatsApp Marketing Suite (৳999/৳1999). Please guide me.');
?>
<!DOCTYPE html>
<html lang="bn" class="notranslate" translate="no">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="google" content="notranslate">
  <meta name="googlebot" content="notranslate">
  <title>WAManager Pro — Official WhatsApp Marketing & CRM Suite</title>
  <meta name="description" content="আনলিমিটেড বাল্ক মেসেজিং, অ্যান্টি-ব্যান স্পিনট্যাক্স, অটো-রিপ্লাই বট এবং বি২বি লিড ফাইন্ডার সহ দেশের সেরা হোয়াটসঅ্যাপ মার্কেটিং সফটওয়্যার। ১ বছর ৯৯৯ ৳ | ৩ বছর ১৯৯৯ ৳।">
  <meta property="og:title" content="WAManager Pro — WhatsApp Marketing & CRM Suite">
  <meta property="og:description" content="বাল্ক হোয়াটসঅ্যাপ মেসেজিং ও লিড জেনারেশনের অল-ইন-ওয়ান স্বয়ংক্রিয় সফটওয়্যার।">
  <meta property="og:image" content="<?= e($siteUrl) ?>/assets/img/logo_wa_marketing.png">
  <link rel="icon" type="image/png" href="/assets/img/logo_wa_marketing.png">
  <link rel="stylesheet" href="/assets/css/site.css?v=<?= filemtime(__DIR__ . '/assets/css/site.css') ?>">
  <style>
    :root {
      --wa-green: #25D366;
      --wa-dark-green: #128C7E;
      --wa-teal: #075E54;
      --wa-bg: #0b1528;
    }
    .wa-hero {
      padding: 5rem 1.5rem 3.5rem;
      text-align: center;
      background: radial-gradient(circle at 50% 20%, rgba(37, 211, 102, 0.15) 0%, rgba(11, 21, 40, 0) 70%);
      position: relative;
    }
    .wa-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 18px;
      background: rgba(37, 211, 102, 0.15);
      border: 1px solid rgba(37, 211, 102, 0.4);
      border-radius: 999px;
      color: var(--wa-green);
      font-size: 0.9rem;
      font-weight: 700;
      margin-bottom: 1.5rem;
    }
    .wa-title {
      font-size: clamp(2.2rem, 5vw, 3.5rem);
      font-weight: 900;
      line-height: 1.2;
      color: #ffffff;
      max-width: 900px;
      margin: 0 auto 1.25rem;
    }
    .wa-title span {
      background: linear-gradient(135deg, #25D366, #34d399);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .wa-lead {
      font-size: 1.15rem;
      color: #94a3b8;
      max-width: 760px;
      margin: 0 auto 2rem;
      line-height: 1.6;
    }
    .wa-features-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.75rem;
      max-width: 1200px;
      margin: 3rem auto;
      padding: 0 1.5rem;
    }
    .wa-feature-card {
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid rgba(37, 211, 102, 0.25);
      border-radius: var(--radius-lg);
      padding: 2rem;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      position: relative;
    }
    .wa-feature-card:hover {
      border-color: var(--wa-green);
      transform: translateY(-5px);
      box-shadow: 0 15px 35px rgba(0,0,0,0.5), 0 0 25px rgba(37, 211, 102, 0.25);
    }
    .wa-feat-icon {
      font-size: 2.2rem;
      margin-bottom: 1rem;
      display: inline-block;
    }
    .wa-pricing-section {
      max-width: 900px;
      margin: 4rem auto;
      padding: 0 1.5rem;
      text-align: center;
    }
    .wa-plans-wrap {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 2rem;
      margin-top: 2rem;
    }
    .wa-plan-box {
      background: linear-gradient(145deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.85));
      border: 2px solid rgba(37, 211, 102, 0.35);
      border-radius: var(--radius-xl);
      padding: 2.5rem 2rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.3s ease;
      position: relative;
    }
    .wa-plan-box:hover {
      border-color: var(--wa-green);
      box-shadow: 0 20px 45px rgba(37, 211, 102, 0.25);
      transform: translateY(-5px);
    }
    .wa-plan-box.recommended {
      border-color: var(--wa-green);
      box-shadow: 0 0 30px rgba(37, 211, 102, 0.3);
    }
    .rec-badge {
      position: absolute;
      top: -14px;
      left: 50%;
      transform: translateX(-50%);
      background: linear-gradient(135deg, #10b981, #059669);
      color: #fff;
      font-size: 0.8rem;
      font-weight: 800;
      padding: 4px 16px;
      border-radius: 999px;
      border: 1px solid #25D366;
    }
    .wa-btn {
      background: linear-gradient(135deg, #25D366, #128C7E);
      color: #000;
      font-weight: 800;
      font-size: 1.05rem;
      padding: 0.9rem 1.5rem;
      border-radius: var(--radius-md);
      text-decoration: none;
      display: inline-block;
      transition: all 0.2s ease;
      box-shadow: 0 4px 20px rgba(37, 211, 102, 0.4);
    }
    .wa-btn:hover {
      background: linear-gradient(135deg, #34d399, #10b981);
      transform: translateY(-2px);
      box-shadow: 0 6px 25px rgba(37, 211, 102, 0.6);
      color: #000;
    }
  </style>
</head>
<body class="notranslate" translate="no">
  <header class="site-header">
    <a class="logo-link" href="/">
      <img class="logo-img" src="/assets/img/logo_wa_marketing.png" alt="WAManager Pro" width="40" height="40" style="border-radius:8px;">
      <div class="logo">WAManager <span>PRO</span></div>
    </a>
    <div class="header-actions">
      <a class="btn btn-sm btn-ghost" href="/">হোমে ফিরুন</a>
      <a class="btn btn-sm" href="/order.php?product=wa_marketing" style="background:#25D366; color:#000; font-weight:bold;">অর্ডার করুন (৳৯৯৯)</a>
    </div>
  </header>

  <main>
    <!-- Hero -->
    <section class="wa-hero">
      <div class="wa-pill">
        <span>⚡ AutoMovie Pro ইকোসিস্টেমের অফিসিয়াল প্রোডাক্ট</span>
      </div>
      <h1 class="wa-title">
        আনলিমিটেড হোয়াটসঅ্যাপ মার্কেটিং ও <span>বি২বি লিড জেনারেশন</span> সফটওয়্যার
      </h1>
      <p class="wa-lead">
        কোনো অ্যাকাউন্ট ব্যান হওয়ার ঝুঁকি ছাড়াই স্মার্ট স্পিনট্যাক্স ও মানুষের মতো পেসিং দিয়ে বাল্ক মেসেজ পাঠান। সাথে থাকছে অটো-রিপ্লাই বট, বি২বি লিড স্ক্র্যাপার ও সার্বক্ষণিক আপডেট।
      </p>
      <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
        <a href="#pricing" class="wa-btn">সাবস্ক্রিপশন প্ল্যান দেখুন (৳৯৯৯ থেকে)</a>
        <a href="<?= e($waLink) ?>" target="_blank" rel="noopener" class="btn btn-ghost" style="border-color:#25D366; color:#25D366;">
          💬 WhatsApp-এ কথা বলুন
        </a>
      </div>
    </section>

    <!-- Key Capabilities Grid -->
    <section class="wa-features-grid">
      <div class="wa-feature-card">
        <span class="wa-feat-icon">📢</span>
        <h3 style="color:#25D366; font-size:1.25rem; margin-bottom:0.6rem;">আনলিমিটেড বাল্ক মেসেজিং</h3>
        <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6;">
          Excel বা CSV ফাইল থেকে হাজার হাজার কন্টাক্ট আপলোড করে এক ক্লিকে পার্সোনালাইজড মেসেজ পাঠান। কাস্টমারের নাম, অর্ডার তথ্য ডায়নামিকভাবে ট্যাগ হবে।
        </p>
      </div>

      <div class="wa-feature-card">
        <span class="wa-feat-icon">🛡️</span>
        <h3 style="color:#25D366; font-size:1.25rem; margin-bottom:0.6rem;">অ্যান্টি-ব্যান স্পিনট্যাক্স গার্ড</h3>
        <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6;">
          {হ্যালো|আসসালামু আলাইকুম|নমস্কার} এর মতো স্পিনট্যাক্স ভ্যারিয়েশন ও র‍্যান্ডম স্লিপ ডিলে ব্যবহারের ফলে মেটা কখনো রোবট হিসেবে চিহ্নিত করতে পারে না।
        </p>
      </div>

      <div class="wa-feature-card">
        <span class="wa-feat-icon">🤖</span>
        <h3 style="color:#25D366; font-size:1.25rem; margin-bottom:0.6rem;">স্মার্ট অটো-রিপ্লাই বট</h3>
        <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6;">
          ২৪ ঘণ্টা আপনার অনুপস্থিতিতেও কাস্টমারের পণ্যের দাম, লোকেশন বা অর্ডারের প্রশ্নের সাথে সাথে স্বয়ংক্রিয় নিখুঁত উত্তর প্রদান করবে এআই বট।
        </p>
      </div>

      <div class="wa-feature-card">
        <span class="wa-feat-icon">📍</span>
        <h3 style="color:#25D366; font-size:1.25rem; margin-bottom:0.6rem;">Google Maps বি২বি লিড স্ক্র্যাপার</h3>
        <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6;">
          যেকোনো এলাকা বা ক্যাটাগরি (যেমন: Dhaka Restaurant, Chittagong Clothing) লিখে সার্চ করলেই রিয়েল কাস্টমার ও প্রতিষ্ঠানের ফোন নম্বর ও ঠিকানা স্ক্র্যাপ হয়ে যাবে।
        </p>
      </div>

      <div class="wa-feature-card">
        <span class="wa-feat-icon">👥</span>
        <h3 style="color:#25D366; font-size:1.25rem; margin-bottom:0.6rem;">গ্রুপ মেম্বার এক্সট্রাক্টর</h3>
        <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6;">
          আপনি যেসব হোয়াটসঅ্যাপ গ্রুপে যুক্ত আছেন, সেখানকার সব অ্যাক্টিভ মেম্বারের ফোন নম্বর ১ ক্লিকে এক্সপোর্ট করে সরাসরি মার্কেটিং শুরু করুন।
        </p>
      </div>

      <div class="wa-feature-card">
        <span class="wa-feat-icon">🔄</span>
        <h3 style="color:#25D366; font-size:1.25rem; margin-bottom:0.6rem;">সবসময় নতুন নতুন ফিচার আপডেট</h3>
        <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6;">
          আমাদের ডেডিকেটেড ইঞ্জিনিয়ারিং টিম নিয়মিত নতুন ফিচার ও হোয়াটসঅ্যাপ অ্যালগরিদম আপডেট সফটওয়্যারে পুশ করে, ফলে আপনার সফটওয়্যার সর্বদা আপ-টু-ডেট থাকবে।
        </p>
      </div>
    </section>

    <!-- Pricing Section -->
    <section id="pricing" class="wa-pricing-section">
      <span class="wa-pill">💰 অফিশিয়াল সাবস্ক্রিপশন প্রাইসিং</span>
      <h2 style="font-size:2.2rem; color:#fff; margin-bottom:0.5rem;">আপনার জন্য উপযুক্ত প্ল্যানটি বেছে নিন</h2>
      <p style="color:#94a3b8;">যেকোনো প্ল্যানেই পাবেন আনলিমিটেড বাল্ক মেসেজিং, অটো-রিপ্লাই বট এবং রেগুলার সফটওয়্যার আপডেট।</p>

      <div class="wa-plans-wrap">
        <!-- 1 Year Plan -->
        <div class="wa-plan-box">
          <div>
            <h3 style="color:#fff; font-size:1.5rem; margin-bottom:0.5rem;">১ বছর সাবস্ক্রিপশন</h3>
            <p style="color:#94a3b8; font-size:0.9rem; margin-bottom:1.5rem;">১২ মাস নিরবচ্ছিন্ন ব্যবহার ও আপডেট</p>
            <div style="font-size:2.8rem; font-weight:900; color:#25D366; margin-bottom:0.5rem;">
              ৳৯৯৯ <span style="font-size:1.1rem; color:#ef4444; text-decoration:line-through;">৳২,৯৯৯</span>
            </div>
            <p style="font-size:0.85rem; color:#6ee7b7; margin-bottom:1.5rem;">(১ বছরের সম্পূর্ণ লাইসেন্স)</p>
            <ul style="text-align:left; color:#cbd5e1; font-size:0.92rem; line-height:2; list-style:none; padding:0; margin-bottom:2rem;">
              <li>✓ আনলিমিটেড বাল্ক মেসেজিং</li>
              <li>✓ অ্যান্টি-ব্যান স্পিনট্যাক্স ফিল্টার</li>
              <li>✓ স্বয়ংক্রিয় এআই অটো-রিপ্লাই বট</li>
              <li>✓ Google Maps B2B লিড স্ক্র্যাপার</li>
              <li>✓ গ্রুপ মেম্বার এক্সট্রাক্টর</li>
              <li>✓ ১ বছর নিয়মিত নতুন ফিচার ও আপডেট</li>
              <li>✓ ফুল স্ট্যান্ডার্ড টেকনিক্যাল সাপোর্ট</li>
            </ul>
          </div>
          <a href="/order.php?product=wa_marketing&plan=1" class="wa-btn" style="width:100%; text-align:center;">
            ১ বছরের লাইসেন্স নিন (৳৯৯৯)
          </a>
        </div>

        <!-- 3 Years Plan (Recommended) -->
        <div class="wa-plan-box recommended">
          <span class="rec-badge">🔥 সর্বাধিক জনপ্রিয় সেভিংস প্ল্যান</span>
          <div>
            <h3 style="color:#fff; font-size:1.5rem; margin-bottom:0.5rem;">৩ বছর সাবস্ক্রিপশন</h3>
            <p style="color:#94a3b8; font-size:0.9rem; margin-bottom:1.5rem;">৩৬ মাস দীর্ঘমেয়াদী রিল্যাক্স প্যাকেজ</p>
            <div style="font-size:2.8rem; font-weight:900; color:#25D366; margin-bottom:0.5rem;">
              ৳১,৯৯৯ <span style="font-size:1.1rem; color:#ef4444; text-decoration:line-through;">৳৫,৫০০</span>
            </div>
            <p style="font-size:0.85rem; color:#6ee7b7; margin-bottom:1.5rem;">(৩ বছরের মেগা ডিসকাউন্ট লাইসেন্স)</p>
            <ul style="text-align:left; color:#cbd5e1; font-size:0.92rem; line-height:2; list-style:none; padding:0; margin-bottom:2rem;">
              <li>✓ আনলিমিটেড বাল্ক মেসেজিং</li>
              <li>✓ অ্যান্টি-ব্যান স্পিনট্যাক্স ফিল্টার</li>
              <li>✓ স্বয়ংক্রিয় এআই অটো-রিপ্লাই বট</li>
              <li>✓ Google Maps B2B লিড স্ক্র্যাপার</li>
              <li>✓ গ্রুপ মেম্বার এক্সট্রাক্টর</li>
              <li>✓ <strong>৩৬ মাস নিরবচ্ছিন্ন নতুন ফিচার ও আপডেট</strong></li>
              <li>✓ <strong>ভিআইপি প্রায়োরিটি সাপোর্ট ২৪/৭</strong></li>
              <li>✓ মেগা সেভিংস (প্রতি বছর মাত্র ৳৬৬৬)</li>
            </ul>
          </div>
          <a href="/order.php?product=wa_marketing&plan=3" class="wa-btn" style="width:100%; text-align:center; background:linear-gradient(135deg, #10b981, #059669); color:#fff;">
            ৩ বছরের লাইসেন্স নিন (৳১,৯৯৯)
          </a>
        </div>
      </div>
    </section>
  </main>

  <footer style="border-top:1px solid rgba(255,255,255,0.08); padding:2.5rem 1.5rem; text-align:center; color:#64748b; font-size:0.9rem;">
    <p>© <?= date('Y') ?> AutoMovie Pro & WAManager Pro Suite. সর্বস্বত্ব সংরক্ষিত।</p>
    <p style="margin-top:0.5rem;">অফিসিয়াল হেল্পলাইন ও WhatsApp: <strong style="color:#25D366;">+8801968111593</strong></p>
  </footer>
</body>
</html>
