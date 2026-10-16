<?php
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';

$orderId = (int) ($_GET['order'] ?? 0);
$stmt = $pdo->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
$stmt->execute([$orderId]);
$order = $stmt->fetch();
if (!$order) {
    redirect('/');
}

$uiLang = strtolower(substr((string) ($_GET['lang'] ?? $_COOKIE['amp_ui_lang'] ?? 'bn'), 0, 2));
if (!in_array($uiLang, amp_cms_langs(), true)) {
    $uiLang = 'bn';
}

$brand = setting($pdo, 'hero_brand', 'AutoMovie Pro');

$langsNote = '';
if (!empty($order['base_langs'])) {
    $langsNote = 'Languages: ' . (string) $order['base_langs'];
    if (!empty($order['addon_langs'])) {
        $langsNote .= ' + ' . (string) $order['addon_langs'];
    }
}

$isGooglePro = str_contains((string)($order['plan_name'] ?? ''), 'Google AI Pro');
try {
    $subCheck = $pdo->prepare('SELECT * FROM google_pro_subscriptions WHERE order_id = ? LIMIT 1');
    $subCheck->execute([(int)$order['id']]);
    if ($subCheck->fetch()) {
        $isGooglePro = true;
    }
} catch (\Throwable) {}

$gmailHandoffMsg = "আমার Google AI Pro অর্ডার আইডি: #{$order['id']}, নাম: {$order['name']}। আমার জিমেইল আইডি হলো: [এখানে আপনার জিমেইল লিখুন]। অনুগ্রহ করে আমার ১৫০ জিবি ক্লাউড স্টোরেজ ও এপিআই এক্সেস কনফিগার করে দিন।";
$gmailWaLink = 'https://wa.me/8801968111593?text=' . rawurlencode($gmailHandoffMsg);

$isApproved = in_array((string)($order['status'] ?? ''), ['approved', 'active'], true);
$customer = null;
$license = null;
if ($isApproved && !empty($order['customer_id'])) {
    $custStmt = $pdo->prepare('SELECT * FROM customers WHERE id = ? LIMIT 1');
    $custStmt->execute([(int)$order['customer_id']]);
    $customer = $custStmt->fetch();

    $licStmt = $pdo->prepare('SELECT * FROM licenses WHERE customer_id = ? AND revoked = 0 ORDER BY id DESC LIMIT 1');
    $licStmt->execute([(int)$order['customer_id']]);
    $license = $licStmt->fetch();
}

$hasPaymentSubmitted = !empty($order['txn_id']) || !empty($order['payment_screenshot']) || in_array((string)($order['status'] ?? ''), ['under_review', 'approved', 'active'], true);

$prefill = 'AutoMovie Pro payment — Order #' . $order['id']
    . ' — ' . $order['name']
    . ' — ৳' . number_format((float) $order['amount'], 0)
    . ($langsNote !== '' ? ' — ' . $langsNote : '')
    . "\nTxn ID: ";
$waLink = amp_whatsapp_sales_link($prefill);

$waPrefill = "AutoMovie Pro Payment Proof\n"
    . "Order: #{$order['id']}\n"
    . "Name: {$order['name']}\n"
    . "Package: {$order['plan_name']}\n"
    . "Amount: ৳" . number_format((float) $order['amount'], 0) . "\n"
    . (!empty($order['txn_id']) ? "TrxID: {$order['txn_id']}\n" : "")
    . (!empty($order['payment_method']) ? "Method: {$order['payment_method']}\n" : "");
$waProofLink = 'https://wa.me/8801968111593?text=' . rawurlencode($waPrefill);
?>
<!DOCTYPE html>
<html lang="<?= e($uiLang) ?>" class="notranslate" translate="no"<?= $uiLang === 'ur' ? ' dir="rtl"' : '' ?>>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="google" content="notranslate">
  <meta name="googlebot" content="notranslate">
  <title><?= e($brand) ?> — <?= $isApproved ? 'Account Activated' : 'Pending Verification' ?></title>
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <link rel="stylesheet" href="/assets/css/site.css">
  <meta name="robots" content="noindex">
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
      <a class="btn btn-sm btn-wa" href="<?= e($waLink) ?>" target="_blank" rel="noopener" data-i18n="wa_send">WhatsApp</a>
    </div>
  </header>
  <section class="reveal in">

    <?php if ($isApproved): ?>
      <!-- INSTANT APPROVED DISPLAY -->
      <div id="approvedView" class="approved-container" style="background: linear-gradient(135deg, #064e3b, #022c22); border: 2px solid #10b981; border-radius: 16px; padding: 2rem 1.5rem; margin: 1.5rem 0 2rem; text-align: center; box-shadow: 0 10px 30px rgba(16, 185, 129, 0.25);">
        <div style="font-size: 3rem; margin-bottom: 0.5rem;">🎉</div>
        <h2 style="color: #6ee7b7; font-size: 1.5rem; margin-bottom: 0.5rem; font-weight: 700;">অভিনন্দন! আপনার অ্যাকাউন্ট প্রস্তুত ও সক্রিয় হয়েছে</h2>
        <p style="color: #d1fae5; font-size: 1rem; max-width: 600px; margin: 0 auto 1.5rem;">
          অর্ডার #<?= (int) $order['id'] ?> সফলভাবে ভেরিফাই ও অনুমোদিত হয়েছে। সফটওয়্যারটি ডাউনলোড করে নিচের ক্রেডেনশিয়াল ব্যবহার করে লগইন করুন।
        </p>

        <div style="background: rgba(0,0,0,0.4); border: 1px solid #10b981; border-radius: 12px; padding: 1.25rem; max-width: 440px; margin: 0 auto 1.5rem; text-align: left;">
          <div style="margin-bottom: 0.75rem; color: #fff;">
            <span style="color: #94a3b8; font-size: 0.85rem;">লগইন আইডি (Login ID):</span><br>
            <strong style="font-size: 1.25rem; color: #38bdf8; font-family: monospace;"><?= e($customer['login_id'] ?? $order['whatsapp']) ?></strong>
          </div>
          <div style="margin-bottom: 0.75rem; color: #fff;">
            <span style="color: #94a3b8; font-size: 0.85rem;">পাসওয়ার্ড (Password):</span><br>
            <span style="font-size: 0.95rem; color: #f59e0b;">(অ্যাপ্রুভালের সময় আপনার WhatsApp-এ পাঠানো হয়েছে)</span>
          </div>
          <?php if (!empty($license['token'])): ?>
            <div style="margin-bottom: 0.75rem; color: #fff;">
              <span style="color: #94a3b8; font-size: 0.85rem;">লাইসেন্স টোকেন:</span><br>
              <code style="background: #0f172a; padding: 3px 8px; border-radius: 4px; color: #38bdf8; font-size: 0.85rem; word-break: break-all;"><?= e($license['token']) ?></code>
            </div>
          <?php endif; ?>
          <div style="color: #94a3b8; font-size: 0.82rem; border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 0.5rem;">
            🔒 <em>নোট: সফটওয়্যার প্রথমবার যে কম্পিউটারে ওপেন করবেন, সেটি স্থায়ীভাবে লক হয়ে যাবে।</em>
          </div>
        </div>

        <a href="/downloads/AutoMoviePro_Installer_Latest.exe" class="btn" style="background: #10b981; color: #022c22; font-weight: 800; font-size: 1.1rem; padding: 0.9rem 1.8rem; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 6px 20px rgba(16,185,129,0.4); text-decoration: none;">
          ⬇️ ১-ক্লিকে ইনস্টলার ডাউনলোড করুন (AutoMoviePro.exe)
        </a>
      </div>
    <?php endif; ?>

    <div id="pendingSection" style="<?= $isApproved ? 'display:none;' : '' ?>">
      
      <?php if ($hasPaymentSubmitted): ?>
        <!-- STATE A: PAYMENT SUBMITTED & UNDER ACTIVE REVIEW -->
        <div class="under-review-card" style="background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(30, 58, 138, 0.35)); border: 2px solid #38bdf8; border-radius: 16px; padding: 2rem 1.5rem; margin: 1.5rem 0 2rem; box-shadow: 0 10px 30px rgba(56, 189, 248, 0.2); text-align: center;">
          <div style="font-size: 3rem; margin-bottom: 0.5rem;">⏳</div>
          <span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; font-size: 0.85rem; font-weight: 800; padding: 4px 14px; border-radius: 9999px; text-transform: uppercase; border: 1px solid #38bdf8;">
            যাচাই প্রক্রিয়াধীন (Under Verification)
          </span>
          <h2 style="color: #f1f5f9; font-size: 1.55rem; margin-top: 0.75rem; margin-bottom: 0.5rem; font-weight: 700;">
            আপনার অর্ডার ও পেমেন্ট তথ্য সফলভাবে গৃহীত হয়েছে!
          </h2>
          <p style="color: #cbd5e1; font-size: 1rem; max-width: 650px; margin: 0 auto 1.5rem; line-height: 1.6;">
            অর্ডার <strong>#<?= (int) $order['id'] ?></strong>-এর পেমেন্ট অ্যাডমিন টিম বিকাশ/নগদ স্টেটমেন্টের সাথে যাচাই করছে। সাধারণত ৫ থেকে ১৫ মিনিটের মধ্যে অনুমোদন হওয়ামাত্র এই পেজে স্বয়ংক্রিয়ভাবে অ্যাকাউন্ট লগইন ও সফটওয়্যার ডাউনলোড বাটন আনলক হবে।
          </p>

          <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; max-width: 520px; margin: 0 auto 1.5rem; text-align: left;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.92rem; color: #cbd5e1; border-bottom: 1px dashed rgba(255,255,255,0.15); padding-bottom: 0.75rem; margin-bottom: 0.75rem;">
              <div>
                <span style="color: #94a3b8; font-size: 0.8rem; display: block;">গ্রাহকের নাম:</span>
                <strong style="color: #fff;"><?= e($order['name']) ?></strong>
              </div>
              <div>
                <span style="color: #94a3b8; font-size: 0.8rem; display: block;">WhatsApp নম্বর:</span>
                <strong style="color: #38bdf8;"><?= e($order['whatsapp']) ?></strong>
              </div>
              <div>
                <span style="color: #94a3b8; font-size: 0.8rem; display: block;">নির্বাচিত প্যাকেজ:</span>
                <span style="color: #f59e0b; font-weight: 600;"><?= e($order['plan_name']) ?></span>
              </div>
              <div>
                <span style="color: #94a3b8; font-size: 0.8rem; display: block;">সর্বমোট প্রদেয়:</span>
                <strong style="color: #10b981; font-size: 1.1rem;">৳<?= number_format((float) $order['amount'], 0) ?></strong>
              </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.92rem; color: #cbd5e1;">
              <div>
                <span style="color: #94a3b8; font-size: 0.8rem; display: block;">পেমেন্ট মেথড:</span>
                <strong style="color: #fff; text-transform: uppercase;"><?= e($order['payment_method'] ?: 'bKash / Nagad') ?></strong>
              </div>
              <div>
                <span style="color: #94a3b8; font-size: 0.8rem; display: block;">ট্রানজেকশন আইডি (TrxID):</span>
                <code style="background: #0f172a; color: #38bdf8; padding: 2px 6px; border-radius: 4px; font-weight: 700;"><?= e($order['txn_id'] ?: 'স্ক্রিনশট জমা দিয়েছেন') ?></code>
              </div>
            </div>

            <?php if (!empty($order['sender_last_digits'])): ?>
              <div style="margin-top: 0.5rem; font-size: 0.85rem; color: #94a3b8;">
                প্রেরক শেষ ডিজিট: <strong style="color: #fff;"><?= e($order['sender_last_digits']) ?></strong>
              </div>
            <?php endif; ?>

            <?php if (!empty($order['payment_screenshot'])): ?>
              <div style="margin-top: 1rem; border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 0.75rem;">
                <span style="color: #94a3b8; font-size: 0.82rem; display: block; margin-bottom: 6px;">📸 জমা দেওয়া পেমেন্ট স্ক্রিনশট:</span>
                <a href="<?= e($order['payment_screenshot']) ?>" target="_blank" rel="noopener">
                  <img src="<?= e($order['payment_screenshot']) ?>" alt="Payment Receipt" style="max-height: 140px; max-width: 100%; border-radius: 8px; border: 1.5px solid #38bdf8; box-shadow: 0 4px 15px rgba(0,0,0,0.5);">
                </a>
                <small style="color: #38bdf8; display: block; margin-top: 4px;">🔍 বড় করে দেখতে ছবিতে ক্লিক করুন</small>
              </div>
            <?php endif; ?>
          </div>

          <div style="display: flex; justify-content: center; align-items: center; gap: 8px; margin-bottom: 1.5rem; color: #93c5fd; font-size: 0.88rem;">
            <span class="online-dot"></span>
            <span>লাইভ ভেরিফিকেশন সক্রিয় • প্রতি কয়েক সেকেন্ড পর পর স্বয়ংক্রিয়ভাবে চেক হচ্ছে…</span>
          </div>

          <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
            <a href="<?= e($waProofLink ?? $waLink) ?>" target="_blank" rel="noopener" class="btn" style="background: #25D366; color: #042f2e; font-weight: 800; padding: 0.85rem 1.6rem; border-radius: 10px; text-decoration: none; display: inline-flex; align-items: center; gap: 8px;">
              <span>💬</span> WhatsApp-এ কথা বলুন বা দ্রুত কনফার্ম করুন
            </a>
            <button type="button" class="btn btn-ghost" onclick="document.getElementById('editPaymentBox').style.display = (document.getElementById('editPaymentBox').style.display === 'none' ? 'block' : 'none');" style="padding: 0.85rem 1.4rem; border-radius: 10px; font-size: 0.9rem;">
              ✏️ তথ্য পরিবর্তন বা নতুন স্ক্রিনশট আপলোড
            </button>
          </div>
        </div>
      <?php endif; ?>

      <!-- PAYMENT INSTRUCTIONS & VERIFICATION SUBMISSION SECTION -->
      <div id="editPaymentBox" style="<?= $hasPaymentSubmitted ? 'display:none;' : '' ?>">
        <div style="text-align: center; margin-bottom: 1.5rem;">
          <h2 data-i18n="wait_title" style="font-size: 1.6rem; margin-bottom: 0.35rem;">অর্ডার #<?= (int) $order['id'] ?> পেয়েছি • পেমেন্ট সম্পন্ন করুন</h2>
          <p class="lead" style="margin-bottom: 0.5rem; color: #cbd5e1;">
            নির্বাচিত প্যাকেজ: <strong><?= e($order['plan_name']) ?></strong>
          </p>
          <div style="display: inline-block; background: rgba(56, 189, 248, 0.15); border: 1.5px solid #38bdf8; border-radius: 999px; padding: 6px 20px; font-size: 1.35rem; font-weight: 800; color: #38bdf8;">
            সর্বমোট প্রদেয়: ৳<?= e(number_format((float) $order['amount'], 0)) ?><?= $langsNote !== '' ? ' — ' . e($langsNote) : '' ?>
          </div>
        </div>

        <?php if ($isGooglePro): ?>
          <!-- DEDICATED GOOGLE AI PRO NOTICE -->
          <div class="google-pro-notice-box" style="background: linear-gradient(135deg, #064e3b, #022c22); border: 2px solid #10b981; border-radius: 16px; padding: 1.5rem; margin: 1rem 0 1.5rem; text-align: center; box-shadow: 0 10px 30px rgba(16, 185, 129, 0.25);">
            <span style="background: #10b981; color: #022c22; font-size: 0.8rem; font-weight: 800; padding: 4px 14px; border-radius: 9999px; text-transform: uppercase;">ডেডিকেটেড সার্ভিস</span>
            <h3 style="color: #6ee7b7; font-size: 1.3rem; margin-top: 0.6rem; margin-bottom: 0.35rem; font-weight: 700;">Google AI Pro ও ১৫০ জিবি ক্লাউড ড্রাইভ অ্যাক্টিভেশন</h3>
            <p style="color: #d1fae5; font-size: 0.95rem; line-height: 1.6; max-width: 650px; margin: 0 auto 1.25rem;">
              পেমেন্ট সম্পন্ন করে নিচের সবুজ বাটনে ক্লিক করে আপনার <strong>জিমেইল (Gmail)</strong> ঠিকানা পাঠিয়ে দিন যাতে আমাদের টিম ১৫০ জিবি ক্লাউড ভল্ট ও এপিআই প্রস্তুত করতে পারে।
            </p>
            <a href="<?= e($gmailWaLink) ?>" target="_blank" rel="noopener" class="btn" style="background: #10b981; color: #042f2e; font-weight: 800; font-size: 1rem; padding: 0.85rem 1.5rem; border-radius: 10px; display: inline-flex; align-items: center; gap: 8px; text-decoration: none;">
              <span>📱</span> হোয়াটসঅ্যাপে আপনার জিমেইল আইডি পাঠান
            </a>
          </div>
        <?php endif; ?>

        <!-- Interactive Payment Methods Cards -->
        <div style="background: rgba(15, 23, 42, 0.8); border: 1.5px solid #0284c7; border-radius: 16px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 4px 25px rgba(2, 132, 199, 0.2);">
          <div style="display:flex; align-items:center; gap:8px; margin-bottom: 0.75rem;">
            <span style="font-size:1.4rem;">💳</span>
            <h3 style="color:#38bdf8; font-size:1.2rem; margin:0; font-weight:700;">পেমেন্ট করবেন যেভাবে (ক্যাশ আউট)</h3>
          </div>
          <p style="color:#cbd5e1; font-size:0.92rem; line-height:1.6; margin-bottom: 1.25rem;">
            নিচের যেকোনো একটি অনুমোদিত নম্বরে <strong>ক্যাশ আউট (Cash Out)</strong> করে পেমেন্ট সম্পন্ন করুন। নম্বর কপি করতে বাটনে ক্লিক করুন:
          </p>

          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.85rem; margin-bottom: 1.5rem;">
            <!-- bKash Agent -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #e11d48; border-radius: 10px; padding: 1rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #fda4af; font-size: 0.95rem;">বিকাশ এজেন্ট</strong>
                <span style="background: #e11d48; color: #fff; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">ক্যাশ আউট</span>
              </div>
              <div style="font-family: monospace; font-size: 1.2rem; color: #fff; font-weight: 800; margin: 4px 0 2px;">
                01756160993
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(Zahid Pharmacy)</small>
              <button type="button" class="btn btn-sm" onclick="navigator.clipboard.writeText('01756160993'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='নম্বর কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #e11d48; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight:600;">
                নম্বর কপি করুন
              </button>
            </div>

            <!-- Nagad Agent -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #ea580c; border-radius: 10px; padding: 1rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #fdba74; font-size: 0.95rem;">নগদ এজেন্ট</strong>
                <span style="background: #ea580c; color: #fff; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">ক্যাশ আউট</span>
              </div>
              <div style="font-family: monospace; font-size: 1.2rem; color: #fff; font-weight: 800; margin: 4px 0 2px;">
                01611-824811
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(Simi Drug House)</small>
              <button type="button" class="btn btn-sm" onclick="navigator.clipboard.writeText('01611824811'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='নম্বর কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #ea580c; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight:600;">
                নম্বর কপি করুন
              </button>
            </div>

            <!-- Rocket Agent -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #8b5cf6; border-radius: 10px; padding: 1rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #c4b5fd; font-size: 0.95rem;">রকেট এজেন্ট</strong>
                <span style="background: #8b5cf6; color: #fff; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">ক্যাশ আউট</span>
              </div>
              <div style="font-family: monospace; font-size: 1.2rem; color: #fff; font-weight: 800; margin: 4px 0 2px;">
                01756160993-5
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(এজেন্ট ক্যাশ আউট)</small>
              <button type="button" class="btn btn-sm" onclick="navigator.clipboard.writeText('017561609935'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='নম্বর কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #8b5cf6; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-weight:600;">
                নম্বর কপি করুন
              </button>
            </div>

            <!-- Binance Pay -->
            <div style="background: rgba(30, 41, 59, 0.95); border: 1.5px solid #f59e0b; border-radius: 10px; padding: 1rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <strong style="color: #fde68a; font-size: 0.95rem;">Binance Pay</strong>
                <span style="background: #f59e0b; color: #000; font-size: 0.72rem; padding: 2px 7px; border-radius: 4px; font-weight: 700;">USDT</span>
              </div>
              <div style="font-family: monospace; font-size: 1.1rem; color: #fff; font-weight: 800; margin: 4px 0 2px;">
                ChatEarly Ai
              </div>
              <small style="color: #94a3b8; font-size: 0.75rem; display: block; margin-bottom: 8px;">(Binance Pay ID / QR)</small>
              <button type="button" class="btn btn-sm" onclick="navigator.clipboard.writeText('ChatEarly Ai'); this.innerText='কপি হয়েছে ✓'; setTimeout(()=>this.innerText='আইডি কপি করুন', 2000);" style="width: 100%; padding: 6px 8px; font-size: 0.82rem; background: #f59e0b; color: #000; font-weight:700; border: none; border-radius: 6px; cursor: pointer;">
                আইডি কপি করুন
              </button>
            </div>
          </div>
        </div>

        <!-- Verification Form with Screenshot Upload -->
        <div class="verify-box" style="background:#0f172a; border:1px solid #1e293b; border-radius:16px; padding:1.75rem; margin-top:2rem; box-shadow:0 10px 25px rgba(0,0,0,0.25);">
          <h3 style="color:#38bdf8; margin-bottom:0.75rem; font-size:1.25rem;">⚡ পেমেন্ট তথ্য ও স্ক্রিনশট জমা দিন</h3>
          <p style="color:#cbd5e1; font-size:0.95rem; margin-bottom:1.5rem; line-height:1.5;">
            টাকা পাঠানোর পর নিচের ফর্মে আপনার ট্রানজেকশন আইডি (TrxID) অথবা প্রেরক নম্বরের শেষ ৩-৪ ডিজিট লিখুন এবং পেমেন্টের স্ক্রিনশট আপলোড করুন। অ্যাডমিন ভেরিফাই করলেই আপনার একাউন্ট ও ১-ক্লিক সফটওয়্যার ডাউনলোড আনলক হয়ে যাবে।
          </p>

          <form id="verifyPaymentForm" enctype="multipart/form-data" style="display:grid; grid-template-columns:1fr 1fr; gap:1rem;">
            <input type="hidden" name="order_id" value="<?= (int) $order['id'] ?>">
            
            <div>
              <label style="display:block; color:#cbd5e1; font-size:0.88rem; font-weight:600; margin-bottom:0.35rem;">পেমেন্ট মেথড</label>
              <select name="payment_method" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #475569;">
                <option value="bkash">বিকাশ এজেন্ট: 01756160993 (Zahid Pharmacy)</option>
                <option value="nagad">নগদ এজেন্ট: 01611-824811 (Simi Drug House)</option>
                <option value="rocket">রকেট এজেন্ট: 01756160993-5</option>
                <option value="binance">Binance Pay (ChatEarly Ai)</option>
                <option value="bank">ব্যাংক ট্রান্সফার (DBBL)</option>
              </select>
            </div>

            <div>
              <label style="display:block; color:#cbd5e1; font-size:0.88rem; font-weight:600; margin-bottom:0.35rem;">প্রেরক নম্বরের শেষ ৩-৪ ডিজিট</label>
              <input type="text" name="sender_last_digits" value="<?= e($order['sender_last_digits'] ?? '') ?>" placeholder="যেমন: 0998" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #475569;">
            </div>

            <div style="grid-column:1 / -1;">
              <label style="display:block; color:#cbd5e1; font-size:0.88rem; font-weight:600; margin-bottom:0.35rem;">ট্রানজেকশন আইডি (Txn ID - বিকাশ/নগদ/রকেট)</label>
              <input type="text" name="txn_id" id="txnIdInput" value="<?= e($order['txn_id'] ?? '') ?>" placeholder="যেমন: BL92KA871X (বিকাশ) অথবা 71A3BC45 (নগদ)" maxlength="24" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #475569; text-transform:uppercase; font-family:monospace; font-weight:600; letter-spacing:1px;" oninput="this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, '');">
              <small style="color:#94a3b8; font-size:0.78rem; display:block; margin-top:4px;">💡 বিকাশ/নগদ এসএমএস-এর TrxID টি নির্ভুলভাবে লিখুন। প্রতিটি TrxID শুধুমাত্র একবার গ্রহণযোগ্য।</small>
            </div>

            <!-- Screenshot Upload Input with Preview -->
            <div style="grid-column:1 / -1;">
              <label style="display:block; color:#cbd5e1; font-size:0.88rem; font-weight:600; margin-bottom:0.35rem;">
                📸 পেমেন্টের স্ক্রিনশট আপলোড করুন (ছবি / মানি রসিদ):
              </label>
              <div style="border: 2px dashed #0284c7; border-radius: 8px; padding: 1.25rem; text-align: center; background: rgba(30, 41, 59, 0.5); cursor: pointer;" onclick="document.getElementById('pendingScreenshotInput').click();">
                <input type="file" id="pendingScreenshotInput" name="payment_screenshot" accept="image/*" style="display: none;" onchange="previewPendingScreenshot(this)">
                <div id="pendingUploadPrompt">
                  <span style="font-size: 2rem;">📎</span>
                  <p style="margin: 6px 0 2px; color: #38bdf8; font-size: 0.95rem; font-weight: 600;">পেমেন্ট স্ক্রিনশট সিলেক্ট করতে এখানে ক্লিক করুন</p>
                  <small style="color: #94a3b8; font-size: 0.78rem;">JPG, PNG, WEBP ফরম্যাট (সর্বোচ্চ 10MB)</small>
                </div>
                <div id="pendingScreenshotWrap" style="display: none; margin-top: 8px;">
                  <img id="pendingScreenshotImg" src="" alt="Screenshot Preview" style="max-height: 160px; max-width:100%; border-radius: 6px; border: 1.5px solid #38bdf8; box-shadow: 0 4px 12px rgba(0,0,0,0.4);">
                  <p id="pendingScreenshotName" style="color: #34d399; font-size: 0.85rem; margin-top: 6px; font-weight: 600;"></p>
                </div>
              </div>
            </div>

            <div style="grid-column:1 / -1; margin-top: 0.5rem;">
              <button type="submit" class="btn" style="width:100%; padding:1rem; font-size:1.15rem; background:linear-gradient(135deg, #0284c7, #2563eb); font-weight:700; border-radius:10px;">
                পেমেন্ট তথ্য ও স্ক্রিনশট সাবমিট করুন
              </button>
            </div>
          </form>

          <!-- Instant Result Display -->
          <div id="verifyResult" style="<?= (!empty($order['txn_id']) || !empty($order['payment_screenshot'])) ? 'display:block;' : 'display:none;' ?> margin-top:1.5rem; padding:1.25rem; border-radius:12px; background:#1e293b; border:1px solid #38bdf8;">
            <?php if (!empty($order['txn_id']) || !empty($order['payment_screenshot'])): ?>
              <div style="color:#f59e0b; font-weight:600;">
                ⏳ আপনার পেমেন্ট তথ্য জমা হয়েছে। অ্যাডমিন টিম বিকাশ/নগদ মিলিয়ে অনুমোদন করলে স্বয়ংক্রিয়ভাবে ডাউনলোড ও লগইন আনলক হবে।
              </div>
            <?php endif; ?>
          </div>
        </div>
      </div>
    </div>

    <script>
      let isOrderActive = <?= $isApproved ? 'true' : 'false' ?>;

      function previewPendingScreenshot(input) {
        if (input.files && input.files[0]) {
          const file = input.files[0];
          const reader = new FileReader();
          reader.onload = function(e) {
            const promptEl = document.getElementById('pendingUploadPrompt');
            const wrap = document.getElementById('pendingScreenshotWrap');
            const img = document.getElementById('pendingScreenshotImg');
            const nameEl = document.getElementById('pendingScreenshotName');
            if (promptEl) promptEl.style.display = 'none';
            if (img) img.src = e.target.result;
            if (nameEl) nameEl.textContent = '✓ ' + file.name + ' (' + (file.size / 1024).toFixed(0) + ' KB)';
            if (wrap) wrap.style.display = 'block';
          };
          reader.readAsDataURL(file);
        }
      }

      function renderLiveApproved(data) {
        isOrderActive = true;
        const pendingSec = document.getElementById('pendingSection');
        if (pendingSec) pendingSec.style.display = 'none';

        let appView = document.getElementById('approvedView');
        if (!appView) {
          appView = document.createElement('div');
          appView.id = 'approvedView';
          document.querySelector('section.reveal').prepend(appView);
        }

        appView.innerHTML = `
          <div class="approved-container" style="background: linear-gradient(135deg, #064e3b, #022c22); border: 2px solid #10b981; border-radius: 16px; padding: 2rem 1.5rem; margin: 1.5rem 0 2rem; text-align: center; box-shadow: 0 10px 30px rgba(16, 185, 129, 0.25);">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">🎉</div>
            <h2 style="color: #6ee7b7; font-size: 1.5rem; margin-bottom: 0.5rem; font-weight: 700;">অভিনন্দন! আপনার অ্যাকাউন্ট প্রস্তুত ও সক্রিয় হয়েছে</h2>
            <p style="color: #d1fae5; font-size: 1rem; max-width: 600px; margin: 0 auto 1.5rem;">
              অ্যাডমিন টিম আপনার পেমেন্ট সফলভাবে ভেরিফাই করেছে। সফটওয়্যারটি ডাউনলোড করে নিচের ক্রেডেনশিয়াল ব্যবহার করে লগইন করুন।
            </p>

            <div style="background: rgba(0,0,0,0.4); border: 1px solid #10b981; border-radius: 12px; padding: 1.25rem; max-width: 440px; margin: 0 auto 1.5rem; text-align: left;">
              <div style="margin-bottom: 0.75rem; color: #fff;">
                <span style="color: #94a3b8; font-size: 0.85rem;">লগইন আইডি (Login ID):</span><br>
                <strong style="font-size: 1.25rem; color: #38bdf8; font-family: monospace;">${data.customer?.login_id || 'User'}</strong>
              </div>
              <div style="margin-bottom: 0.75rem; color: #fff;">
                <span style="color: #94a3b8; font-size: 0.85rem;">পাসওয়ার্ড (Password):</span><br>
                <span style="font-size: 0.95rem; color: #f59e0b;">${data.temporary_password ? '<strong>' + data.temporary_password + '</strong>' : '(আপনার WhatsApp-এ পাঠানো হয়েছে)'}</span>
              </div>
              ${data.license_token ? `
                <div style="margin-bottom: 0.75rem; color: #fff;">
                  <span style="color: #94a3b8; font-size: 0.85rem;">লাইসেন্স টোকেন:</span><br>
                  <code style="background: #0f172a; padding: 3px 8px; border-radius: 4px; color: #38bdf8; font-size: 0.85rem; word-break: break-all;">${data.license_token}</code>
                </div>
              ` : ''}
              <div style="color: #94a3b8; font-size: 0.82rem; border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 0.5rem;">
                🔒 <em>নোট: সফটওয়্যার প্রথমবার যে কম্পিউটারে ওপেন করবেন, সেটি স্থায়ীভাবে লক হয়ে যাবে।</em>
              </div>
            </div>

            <a href="${data.download_url || '/downloads/AutoMoviePro_Installer_Latest.exe'}" class="btn" style="background: #10b981; color: #022c22; font-weight: 800; font-size: 1.1rem; padding: 0.9rem 1.8rem; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 6px 20px rgba(16,185,129,0.4); text-decoration: none;">
              ⬇️ ১-ক্লিকে ইনস্টলার ডাউনলোড করুন (AutoMoviePro.exe)
            </a>
          </div>
        `;
      }

      async function checkOrderStatusLive() {
        if (isOrderActive) return;
        try {
          const res = await fetch('/api/order_status.php?order_id=<?= (int)$order['id'] ?>');
          const data = await res.json();
          if (data.ok && data.is_approved) {
            renderLiveApproved(data);
          }
        } catch (err) {}
      }

      if (!isOrderActive) {
        setInterval(checkOrderStatusLive, 5000);
      }

      document.getElementById('verifyPaymentForm')?.addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn = this.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.innerText = 'জমা হচ্ছে ও যাচাই করা হচ্ছে...';

        const formData = new FormData(this);

        try {
          const res = await fetch('/api/verify_payment.php', {
            method: 'POST',
            body: formData
          });
          const data = await res.json();
          const resultBox = document.getElementById('verifyResult');
          resultBox.style.display = 'block';

          if (data.ok) {
            if (data.status === 'active' || data.status === 'approved') {
              renderLiveApproved({
                customer: { login_id: data.credentials?.login_id },
                temporary_password: data.credentials?.temporary_password,
                license_token: data.credentials?.license_token,
                download_url: data.download_url
              });
            } else {
              resultBox.innerHTML = `
                <div style="color:#10b981; font-weight:700; font-size:1.05rem; margin-bottom:0.5rem;">
                  ✓ ${data.message}
                </div>
                <p style="color:#cbd5e1; font-size:0.92rem; margin-bottom:0.75rem;">
                  আপনার পেমেন্ট তথ্য ও স্ক্রিনশট সফলভাবে ডাটাবেজে সংরক্ষিত হয়েছে। অ্যাডমিন টিম বিকাশ/নগদ মিলিয়ে অনুমোদন করলেই এই পেজে স্বয়ংক্রিয়ভাবে ডাউনলোড ও লগইন আনলক হবে।
                </p>
                <a href="${data.download_url}" class="btn" style="display:inline-block; text-decoration:none; background:#0284c7; font-weight:bold; padding:0.6rem 1.25rem; border-radius:6px; font-size:0.95rem;">
                  ⬇ ইনস্টলার এখনই ডাউনলোড করে রাখুন
                </a>
              `;
              // Quick re-check
              setTimeout(checkOrderStatusLive, 3000);
            }
          } else {
            resultBox.innerHTML = `<div style="color:#ef4444; font-weight:600;">✕ ${data.error}</div>`;
          }
        } catch (err) {
          alert('নেটওয়ার্ক সমস্যা হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।');
        } finally {
          btn.disabled = false;
          btn.innerText = 'পেমেন্ট তথ্য ও স্ক্রিনশট সাবমিট করুন';
        }
      });
    </script>

    <div class="cta-row" style="margin-top:1.5rem">
      <a class="btn btn-wa" target="_blank" rel="noopener" href="<?= e($waLink) ?>" data-i18n="wa_send">WhatsApp-এ স্ক্রিনশট / Txn ID পাঠান</a>
      <a class="btn btn-ghost" href="/?lang=<?= e($uiLang) ?>" data-i18n="home">হোমে ফিরুন</a>
    </div>
  </section>
  <script src="/assets/js/i18n-site.js"></script>
</body>
</html>

