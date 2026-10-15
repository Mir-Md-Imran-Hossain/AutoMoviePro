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

$prefill = 'AutoMovie Pro payment — Order #' . $order['id']
    . ' — ' . $order['name']
    . ' — ৳' . number_format((float) $order['amount'], 0)
    . ($langsNote !== '' ? ' — ' . $langsNote : '')
    . "\nTxn ID: ";
$waLink = amp_whatsapp_sales_link($prefill);
?>
<!DOCTYPE html>
<html lang="<?= e($uiLang) ?>"<?= $uiLang === 'ur' ? ' dir="rtl"' : '' ?>>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= e($brand) ?> — <?= $isApproved ? 'Account Activated' : 'Pending Verification' ?></title>
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <link rel="stylesheet" href="/assets/css/site.css">
  <meta name="robots" content="noindex">
</head>
<body>
  <header class="site-header">
    <a class="logo-link" href="/?lang=<?= e($uiLang) ?>">
      <img class="logo-img" src="/assets/img/logo.png?v=<?= filemtime(__DIR__ . '/assets/img/logo.png') ?>" alt="<?= e($brand) ?>" width="40" height="40">
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
      <h2 data-i18n="wait_title">একটু অপেক্ষা করুন</h2>
      <p class="lead" data-i18n="wait_order" data-i18n-vars='<?= e(json_encode(["id" => (int) $order["id"]], JSON_UNESCAPED_UNICODE)) ?>'>অর্ডার #<?= (int) $order['id'] ?> পেয়েছি। পেমেন্ট যাচাই করে অ্যাক্টিভ করা হবে।</p>
      <p class="lead">৳<?= e(number_format((float) $order['amount'], 0)) ?><?= $langsNote !== '' ? ' — ' . e($langsNote) : '' ?></p>

      <?php if ($isGooglePro): ?>
        <!-- DEDICATED GOOGLE AI PRO NOTICE & WHATSAPP GMAIL BUTTON -->
        <div class="google-pro-notice-box" style="background: linear-gradient(135deg, #064e3b, #022c22); border: 2px solid #10b981; border-radius: 16px; padding: 1.75rem 1.25rem; margin: 1.5rem 0 2rem; text-align: center; box-shadow: 0 10px 30px rgba(16, 185, 129, 0.25);">
          <span style="background: #10b981; color: #022c22; font-size: 0.8rem; font-weight: 800; padding: 4px 14px; border-radius: 9999px; text-transform: uppercase;">ডেডিকেটেড সার্ভিস</span>
          <h3 style="color: #6ee7b7; font-size: 1.35rem; margin-top: 0.75rem; margin-bottom: 0.5rem; font-weight: 700;">Google AI Pro ও ১৫০ জিবি ক্লাউড ড্রাইভ অ্যাক্টিভেশন নির্দেশনা</h3>
          <p style="color: #d1fae5; font-size: 0.98rem; line-height: 1.6; max-width: 680px; margin: 0 auto 1.5rem;">
            এটি একটি ডেডিকেটেড প্রিমিয়াম সার্ভিস হওয়ায় অ্যাডমিন টিম ম্যানুয়ালি আপনার ক্লাউড ভল্ট ও এপিআই কনফিগার করবে। পেমেন্ট সম্পন্ন করে নিচের সবুজ বাটনে ক্লিক করে আপনার <strong>জিমেইল (Gmail)</strong> ঠিকানা পাঠিয়ে দিন।
          </p>
          <a href="<?= e($gmailWaLink) ?>" target="_blank" rel="noopener" class="btn" style="background: #10b981; color: #042f2e; font-weight: 800; font-size: 1.05rem; padding: 1rem 1.75rem; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 6px 20px rgba(16,185,129,0.4); text-decoration: none;">
            <span style="font-size: 1.25rem;">📱</span> হোয়াটসঅ্যাপে আপনার জিমেইল আইডি পাঠান (Click to send Gmail on WhatsApp)
          </a>
        </div>
      <?php endif; ?>

      <h3 data-i18n="payment_title">পেমেন্ট করবেন যেভাবে</h3>
      <?php amp_render_payment_section('pending'); ?>

      <!-- Instant Payment Verification & 1-Click Download Box -->
      <div class="verify-box" style="background:#0f172a; border:1px solid #1e293b; border-radius:16px; padding:1.5rem; margin-top:2rem; box-shadow:0 10px 25px rgba(0,0,0,0.2);">
        <h3 style="color:#38bdf8; margin-bottom:0.75rem;">⚡ তাৎক্ষণিক পেমেন্ট যাচাই ও ডাউনলোড আনলক</h3>
        <p style="color:#94a3b8; font-size:0.95rem; margin-bottom:1.25rem;">
          টাকা পাঠানোর পর নিচের ফর্মে আপনার ট্রানজেকশন আইডি অথবা যে নম্বর থেকে ক্যাশ-আউট করেছেন তার শেষ ৩-৪ ডিজিট লিখে সাবমিট করুন। অ্যাডমিন ভেরিফাই করলেই আপনার একাউন্ট প্রস্তুত ও সফটওয়্যার ডাউনলোড আনলক হয়ে যাবে।
        </p>

        <form id="verifyPaymentForm" style="display:grid; grid-template-columns:1fr 1fr; gap:1rem;">
          <input type="hidden" name="order_id" value="<?= (int) $order['id'] ?>">
          
          <div>
            <label style="display:block; color:#cbd5e1; font-size:0.85rem; margin-bottom:0.25rem;">পেমেন্ট মেথড</label>
            <select name="payment_method" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #334155;">
              <option value="bkash">বিকাশ এজেন্ট: 01756160993 (Zahid Pharmacy)</option>
              <option value="nagad">নগদ এজেন্ট: 01611-824811 (Simi Drug House)</option>
              <option value="rocket">রকেট এজেন্ট: 01756160993-5</option>
              <option value="binance">Binance Pay (ChatEarly Ai)</option>
              <option value="bank">ব্যাংক ট্রান্সফার (DBBL)</option>
            </select>
          </div>

          <div>
            <label style="display:block; color:#cbd5e1; font-size:0.85rem; margin-bottom:0.25rem;">প্রেরক নম্বরের শেষ ৩-৪ ডিজিট</label>
            <input type="text" name="sender_last_digits" value="<?= e($order['sender_last_digits'] ?? '') ?>" placeholder="যেমন: 0998" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #334155;">
          </div>

          <div style="grid-column:1 / -1;">
            <label style="display:block; color:#cbd5e1; font-size:0.85rem; margin-bottom:0.25rem;">ট্রানজেকশন আইডি (Txn ID - বিকাশ/নগদ/রকেট)</label>
            <input type="text" name="txn_id" id="txnIdInput" value="<?= e($order['txn_id'] ?? '') ?>" placeholder="যেমন: BL92KA871X (বিকাশ) অথবা 71A3BC45 (নগদ)" pattern="[A-Za-z0-9]{8,16}" title="৮ থেকে ১৬ অক্ষরের আলফানিউমেরিক TrxID দিন" style="width:100%; padding:0.75rem; border-radius:8px; background:#1e293b; color:#fff; border:1px solid #334155; text-transform:uppercase; font-family:monospace; font-weight:600; letter-spacing:1px;" oninput="this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, '');">
            <small style="color:#94a3b8; font-size:0.78rem; display:block; margin-top:4px;">💡 বিকাশ/নগদ এসএমএস-এর TrxID টি নির্ভুলভাবে লিখুন। প্রতিটি TrxID শুধুমাত্র একবার গ্রহণযোগ্য।</small>
          </div>

          <div style="grid-column:1 / -1;">
            <button type="submit" class="btn" style="width:100%; padding:0.85rem; font-size:1.05rem; background:linear-gradient(135deg, #0284c7, #2563eb); font-weight:600;">
              পেমেন্ট তথ্য সাবমিট করুন
            </button>
          </div>
        </form>

        <!-- Instant Result Display -->
        <div id="verifyResult" style="<?= !empty($order['txn_id']) ? 'display:block;' : 'display:none;' ?> margin-top:1.5rem; padding:1.25rem; border-radius:12px; background:#1e293b; border:1px solid #38bdf8;">
          <?php if (!empty($order['txn_id'])): ?>
            <div style="color:#f59e0b; font-weight:600;">
              ⏳ আপনার TrxID (<?= e($order['txn_id']) ?>) জমা হয়েছে। অ্যাডমিন টিম বিকাশ/নগদ মিলিয়ে অনুমোদন করলে স্বয়ংক্রিয়ভাবে ডাউনলোড ও লগইন আনলক হবে।
            </div>
          <?php endif; ?>
        </div>
      </div>
    </div>

    <script>
      let isOrderActive = <?= $isApproved ? 'true' : 'false' ?>;

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
        setInterval(checkOrderStatusLive, 6000);
      }

      document.getElementById('verifyPaymentForm')?.addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn = this.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.innerText = 'যাচাই করা হচ্ছে...';

        const formData = new FormData(this);
        const payload = Object.fromEntries(formData.entries());

        try {
          const res = await fetch('/api/verify_payment.php', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
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
                <p style="color:#94a3b8; font-size:0.9rem; margin-bottom:0.75rem;">
                  আপনার পেমেন্ট রিকোয়েস্ট গৃহীত হয়েছে। অ্যাডমিন টিম বিকাশ/নগদ মিলিয়ে সর্বোচ্চ ১৫-২০ মিনিটের মধ্যে অনুমোদন করে দেবে।
                </p>
                <a href="${data.download_url}" class="btn" style="display:inline-block; text-decoration:none; background:#0284c7; font-weight:bold; padding:0.6rem 1.25rem; border-radius:6px; font-size:0.95rem;">
                  ⬇ ইনস্টলার এখনই ডাউনলোড করে রাখুন
                </a>
              `;
            }
          } else {
            resultBox.innerHTML = `<div style="color:#ef4444; font-weight:600;">✕ ${data.error}</div>`;
          }
        } catch (err) {
          alert('নেটওয়ার্ক সমস্যা হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।');
        } finally {
          btn.disabled = false;
          btn.innerText = 'পেমেন্ট তথ্য সাবমিট করুন';
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

