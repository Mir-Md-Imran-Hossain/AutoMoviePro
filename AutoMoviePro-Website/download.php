<?php
/**
 * AutoMovie Pro — Secure Cryptographic Expiring Download Portal
 * 72-Hour One-Time Cryptographic Token Security Guard
 */
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';
require __DIR__ . '/includes/release_service.php';
require_once __DIR__ . '/includes/billing.php';

$rel = amp_current_release($pdo);
$version = $rel['version'] ?? 'Latest (v8.2.0)';
$token = trim((string) ($_GET['token'] ?? ''));
$isDownloadAction = isset($_GET['download']) || isset($_GET['stream']) || ((string) ($_GET['action'] ?? '') === 'get');

$tokenCheck = null;
if ($token !== '') {
    $tokenCheck = amp_verify_download_token($pdo, $token);
}

// Handle Direct Stream / Binary Download Execution
if ($token !== '' && $isDownloadAction) {
    if (!$tokenCheck || !$tokenCheck['valid']) {
        // Fall through to display error message
    } else {
        // Atomically consume token (one-time download protection)
        $consumed = amp_consume_download_token($pdo, $token);
        if (!$consumed) {
            $tokenCheck = [
                'valid' => false,
                'reason' => 'already_used',
                'seconds_left' => 0,
            ];
        } else {
            // Locate binary installer on disk
            $downloadsDir = amp_downloads_dir();
            $canonical = amp_canonical_installer_name();
            $targetFiles = [
                $downloadsDir . DIRECTORY_SEPARATOR . $canonical,
                $downloadsDir . DIRECTORY_SEPARATOR . 'AutoMoviePro_Installer_Latest.exe',
                $downloadsDir . DIRECTORY_SEPARATOR . 'AutoMoviePro-Setup.exe',
            ];

            $filePath = null;
            foreach ($targetFiles as $tf) {
                if (is_file($tf)) {
                    $filePath = $tf;
                    break;
                }
            }

            if ($filePath && is_readable($filePath)) {
                while (ob_get_level()) {
                    ob_end_clean();
                }
                header('Content-Description: File Transfer');
                header('Content-Type: application/octet-stream');
                header('Content-Disposition: attachment; filename="' . basename($filePath) . '"');
                header('Content-Transfer-Encoding: binary');
                header('Expires: 0');
                header('Cache-Control: must-revalidate, post-check=0, pre-check=0');
                header('Pragma: public');
                header('Content-Length: ' . (string) filesize($filePath));
                readfile($filePath);
                exit;
            } else {
                // Disk file not pre-built — redirect to configured public release URL
                $url = amp_release_public_url($config);
                header('Location: ' . $url);
                exit;
            }
        }
    }
}

$product = strtolower(trim((string) ($_GET['product'] ?? ($tokenCheck['record']['product'] ?? 'software'))));
$isFBSuite = ($product === 'omnisocial' || $product === 'fbsuite' || $product === 'business');
$brand = setting($pdo, 'hero_brand', 'AutoMovie Pro');
$waSupport = amp_whatsapp_sales_link('Hi, I need assistance regarding my AutoMovie Pro download link.');
?><!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= $isFBSuite ? 'AutoMovie Pro FB Suite ডাউনলোড' : 'AutoMovie Pro — সিকিউর ডাউনলোড' ?></title>
  <link rel="stylesheet" href="/assets/css/site.css">
  <link rel="icon" type="image/png" href="/assets/img/logo.png">
  <meta name="robots" content="noindex, nofollow">
</head>
<body style="background: radial-gradient(circle at top center, #0f172a 0%, #020617 100%); min-height: 100vh; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif;">
  
  <header style="padding: 1.5rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: center;">
    <a href="/" style="text-decoration: none; color: #fff; display: inline-flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1.25rem;">
      <img src="/assets/img/logo.png" alt="AutoMovie Pro" width="36" height="36" style="border-radius: 8px;">
      <span>AutoMovie Pro <span style="color: #38bdf8; font-size: 0.85rem; background: rgba(56,189,248,0.15); padding: 2px 8px; border-radius: 99px;">PORTAL</span></span>
    </a>
  </header>

  <main class="wrap" style="max-width: 680px; margin: 3rem auto; padding: 2rem 1.5rem; background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); backdrop-filter: blur(12px);">
    
    <?php if ($token === ''): ?>
      <!-- NO TOKEN PROVIDED -->
      <div style="text-align: center; padding: 1.5rem 0;">
        <div style="font-size: 3.5rem; margin-bottom: 1rem;">🔒</div>
        <h1 style="font-size: 1.6rem; color: #f1f5f9; margin-bottom: 0.75rem;">ডাউনলোড অ্যাক্সেস সংরক্ষিত</h1>
        <p style="color: #94a3b8; font-size: 1rem; line-height: 1.6; margin-bottom: 1.75rem;">
          সফটওয়্যার ডাউনলোডের জন্য একটি ভেরিফাইড <strong>৭২ ঘণ্টার ক্রিপ্টোগ্রাফিক ওয়ান-টাইম ডাউনলোড টোকেন</strong> আবশ্যক।
          আপনার পেমেন্ট অনুমোদনের পর প্রাপ্ত WhatsApp বার্তা অথবা ইমেইলের সিকিউর লিঙ্কটি ব্যবহার করুন।
        </p>

        <div style="background: rgba(30, 41, 59, 0.7); border: 1px dashed rgba(56, 189, 248, 0.4); border-radius: 12px; padding: 1.25rem; margin-bottom: 1.75rem; text-align: left;">
          <h4 style="color: #38bdf8; margin-top: 0; margin-bottom: 0.5rem; font-size: 1rem;">💡 কীভাবে ডাউনলোড লিঙ্ক পাবেন?</h4>
          <ol style="margin: 0; padding-left: 1.25rem; color: #cbd5e1; font-size: 0.9rem; line-height: 1.6;">
            <li>ওয়েবসাইটে বিকাশ/নগদে অর্ডার সম্পন্ন করে TrxID সাবমিট করুন।</li>
            <li>অ্যাডমিন ভেরিফাই করলেই আপনার WhatsApp ও ইমেইলে সুরক্ষিত ওয়ান-টাইম ডাউনলোড লিঙ্ক যাবে।</li>
            <li>পূর্বের অর্ডার ভেরিফাই করতে নিচের বাটনে ক্লিক করুন।</li>
          </ol>
        </div>

        <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
          <a class="btn" href="/#pricing" style="background: linear-gradient(135deg, #0284c7, #2563eb); text-decoration: none;">অর্ডার প্যাকেজ দেখুন</a>
          <a class="btn btn-ghost" href="<?= e($waSupport) ?>" target="_blank" rel="noopener" style="text-decoration: none;">WhatsApp সাপোর্ট</a>
        </div>
      </div>

    <?php elseif (!$tokenCheck['valid']): ?>
      <!-- INVALID / EXPIRED / CONSUMED TOKEN -->
      <div style="text-align: center; padding: 1.5rem 0;">
        <div style="font-size: 3.5rem; margin-bottom: 1rem;">
          <?= $tokenCheck['reason'] === 'expired' ? '⏳' : ($tokenCheck['reason'] === 'already_used' ? '🚫' : '⚠️') ?>
        </div>

        <h1 style="font-size: 1.6rem; color: #ef4444; margin-bottom: 0.75rem;">
          <?php if ($tokenCheck['reason'] === 'expired'): ?>
            ডাউনলোড লিংকের ৭২ ঘণ্টার মেয়াদ শেষ
          <?php elseif ($tokenCheck['reason'] === 'already_used'): ?>
            ওয়ান-টাইম ডাউনলোড টোকেনটি ইতিমধ্যে ব্যবহৃত হয়েছে
          <?php else: ?>
            অবৈধ ডাউনলোড টোকেন (Invalid Token)
          <?php endif; ?>
        </h1>

        <p style="color: #cbd5e1; font-size: 0.98rem; line-height: 1.6; margin-bottom: 1.75rem;">
          <?php if ($tokenCheck['reason'] === 'expired'): ?>
            নিরাপত্তার স্বার্থে ক্রিপ্টোগ্রাফিক ডাউনলোড লিংকের সর্বোচ্চ মেয়াদ ৭২ ঘণ্টা নির্ধারিত। এই লিংকের মেয়াদ উত্তীর্ণ হয়ে গেছে।
          <?php elseif ($tokenCheck['reason'] === 'already_used'): ?>
            এই সিকিউর লিঙ্কটি ওয়ান-টাইম (একবার ব্যবহারযোগ্য)। এটি থেকে ইতিমধ্যে সফলভাবে সফটওয়্যার ইনস্টলার ডাউনলোড করা হয়েছে।
          <?php else: ?>
            প্রদত্ত লিঙ্কটি অসম্পূর্ণ বা ভুল। অনুগ্রহ করে আপনার WhatsApp-এ পাঠানো সঠিক সম্পূর্ণ লিঙ্কটি ব্রাউজারে পেস্ট করুন।
          <?php endif; ?>
        </p>

        <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 1.25rem; margin-bottom: 2rem; color: #fca5a5; font-size: 0.92rem;">
          📌 সফটওয়্যার পুনরায় ডাউনলোড করতে বা নতুন লিঙ্ক পেতে আপনার রেজিস্টার্ড WhatsApp নম্বর অথবা TrxID সহ আমাদের সাপোর্টে মেসেজ দিন। তাৎক্ষণিক সমাধান পেয়ে যাবেন।
        </div>

        <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
          <a class="btn" href="<?= e($waSupport) ?>" target="_blank" rel="noopener" style="background: #10b981; color: #022c22; font-weight: 700; text-decoration: none;">
            📲 WhatsApp সাপোর্টে নতুন লিঙ্ক চান
          </a>
          <a class="btn btn-ghost" href="/" style="text-decoration: none;">হোমে ফিরুন</a>
        </div>
      </div>

    <?php else: ?>
      <!-- VALID TOKEN — ACTIVE ONE-TIME DOWNLOAD -->
      <?php 
        $hoursLeft = round($tokenCheck['seconds_left'] / 3600, 1);
        $expDate = date('d M, Y — h:i A', strtotime($tokenCheck['expires_at']));
      ?>
      <div style="text-align: center; margin-bottom: 2rem;">
        <span style="display: inline-flex; align-items: center; gap: 6px; background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; color: #6ee7b7; padding: 5px 14px; border-radius: 99px; font-size: 0.82rem; font-weight: 600; margin-bottom: 1rem;">
          🔒 ক্রিপ্টোগ্রাফিক ওয়ান-টাইম সিকিউর টোকেন অ্যাক্টিভ
        </span>
        <h1 style="font-size: 1.8rem; color: #fff; margin-bottom: 0.5rem;">
          <?= $isFBSuite ? '🤖 AutoMovie Pro FB Suite ডাউনলোড' : '🎬 AutoMovie Pro ডাউনলোড' ?>
        </h1>
        <p style="color: #94a3b8; font-size: 0.95rem;">পেমেন্ট অনুমোদনের জন্য ধন্যবাদ! নিচের সুরক্ষিত বাটন থেকে সফটওয়্যার সংগ্রহ করুন।</p>
      </div>

      <!-- Security Meta Card -->
      <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 1.25rem; margin-bottom: 1.75rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; text-align: left;">
        <div>
          <span style="color: #64748b; font-size: 0.8rem; text-transform: uppercase;">বর্তমান ভার্সন</span><br>
          <strong style="color: #38bdf8; font-size: 1rem;"><?= htmlspecialchars($version, ENT_QUOTES, 'UTF-8') ?></strong>
        </div>
        <div>
          <span style="color: #64748b; font-size: 0.8rem; text-transform: uppercase;">টোকেন মেয়াদ অবশিষ্ট</span><br>
          <strong style="color: #f59e0b; font-size: 1rem;">⏳ <?= e((string) $hoursLeft) ?> ঘণ্টা</strong>
          <small style="color: #94a3b8; display: block; font-size: 0.75rem;"><?= e($expDate) ?> পর্যন্ত</small>
        </div>
      </div>

      <!-- One-time Warning -->
      <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 10px; padding: 0.9rem 1.1rem; margin-bottom: 1.75rem; font-size: 0.88rem; color: #fde68a; display: flex; align-items: center; gap: 10px;">
        <span style="font-size: 1.25rem;">⚠️</span>
        <div>
          <strong>একবার ব্যবহারযোগ্য (One-Time Protection):</strong> ডাউনলোড শুরু হওয়ার সাথে সাথেই এই ক্রিপ্টোগ্রাফিক টোকেনটি লক হয়ে যাবে।
        </div>
      </div>

      <!-- Download Button Triggering Direct Stream -->
      <div style="text-align: center; margin-bottom: 2rem;">
        <a class="btn" style="background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-size: 1.15rem; font-weight: 700; padding: 1rem 2.2rem; border-radius: 12px; text-decoration: none; display: inline-flex; align-items: center; gap: 10px; box-shadow: 0 8px 25px rgba(16,185,129,0.35);" 
           href="download.php?token=<?= urlencode($token) ?>&download=1" 
           onclick="return confirm('ডাউনলোড শুরু করবেন? এটি একটি ওয়ান-টাইম সিকিউর লিঙ্ক।');">
          ⬇️ ১-ক্লিকে ইনস্টলার ডাউনলোড শুরু করুন
        </a>
      </div>

      <!-- Setup Guide -->
      <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 12px; padding: 1.25rem; font-size: 0.9rem; color: #cbd5e1;">
        <strong style="color: #38bdf8; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;">🚀 সেটআপ ও প্রথমবার ব্যবহারের নিয়ম:</strong>
        <ol style="margin: 0; padding-left: 1.25rem; line-height: 1.7;">
          <li>ডাউনলোডকৃত ইনস্টলার ফাইলটি (.exe) রান করে ইনস্টল সম্পন্ন করুন।</li>
          <li>আপনার WhatsApp-এ প্রেরিত <strong>Login ID</strong> ও <strong>পাসওয়ার্ড</strong> প্রবেশ করিয়ে সফটওয়্যারে ঢুকুন।</li>
          <li>সফটওয়্যার প্রথমবার যে পিসিতে চালু করবেন, সেটি স্বয়ংক্রিয়ভাবে লক হয়ে সুরক্ষিত থাকবে।</li>
          <li>ভবিষ্যতে নতুন আপডেট এলে সফটওয়্যারের ভেতর থেকেই স্বয়ংক্রিয়ভাবে আপডেট গ্রহণ করতে পারবেন।</li>
        </ol>
      </div>
    <?php endif; ?>

  </main>

  <footer style="text-align: center; padding: 2rem 1rem; color: #64748b; font-size: 0.85rem;">
    &copy; <?= date('Y') ?> AutoMovie Pro. সকল স্বত্ব সংরক্ষিত। সুরক্ষিত ওয়ান-টাইম ডেলিভারি সিস্টেম।
  </footer>

</body>
</html>
