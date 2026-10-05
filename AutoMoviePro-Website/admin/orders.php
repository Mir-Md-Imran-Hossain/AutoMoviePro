<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';

require_once dirname(__DIR__) . '/includes/billing.php';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $orderId = (int) ($_POST['order_id'] ?? 0);
    $action = $_POST['action'] ?? '';
    
    if ($action === 'deliver_google_pro') {
        $subId = (int) ($_POST['sub_id'] ?? 0);
        $targetEmail = trim((string) ($_POST['target_email'] ?? ''));
        $googleProKey = trim((string) ($_POST['google_pro_key'] ?? ''));

        $subStmt = $pdo->prepare('SELECT s.*, c.name, c.whatsapp FROM google_pro_subscriptions s JOIN customers c ON s.customer_id = c.id WHERE s.id = ?');
        $subStmt->execute([$subId]);
        $sub = $subStmt->fetch();
        if ($sub) {
            $months = max(1, (int) ($sub['plan_duration_months'] ?? 1));
            $days = $months * 30;
            $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
            if ($driver === 'sqlite') {
                $upSql = "UPDATE google_pro_subscriptions SET status = 'active', target_email = ?, google_pro_key = ?, expires_at = datetime('now', '+' || ? || ' days') WHERE id = ?";
                $pdo->prepare($upSql)->execute([$targetEmail, $googleProKey, $days, $subId]);
            } else {
                $upSql = "UPDATE google_pro_subscriptions SET status = 'active', target_email = ?, google_pro_key = ?, expires_at = DATE_ADD(NOW(), INTERVAL ? DAY) WHERE id = ?";
                $pdo->prepare($upSql)->execute([$targetEmail, $googleProKey, $days, $subId]);
            }

            if (!empty($sub['order_id'])) {
                $pdo->prepare("UPDATE orders SET status = 'approved' WHERE id = ? AND status != 'approved'")->execute([(int) $sub['order_id']]);
            }

            // Send delivery confirmation on customer's WhatsApp
            $delMsg = "🎉 আপনার AutoMovie Pro 'Google AI Pro' প্যাকেজ সফলভাবে একটিভ ও ডেলিভার করা হয়েছে!\n"
                . "কনফিগার করা জিমেইল: {$targetEmail}\n"
                . "১৫০ জিবি ক্লাউড ড্রাইভ: Active\n"
                . "আপনার Google Pro API Key: {$googleProKey}\n\n"
                . "ডেস্কটপ সফটওয়্যারে প্রো-কি প্রবেশ করিয়ে আনলিমিটেড কোটা ও রোবোটিকলেস জেনারেশন উপভোগ করুন।";
            whatsapp_queue($pdo, $config, (string) $sub['whatsapp'], $delMsg, (int) $sub['customer_id']);

            $message = "Google Pro সাবস্ক্রিপশন #{$subId} সফলভাবে 'Active & Delivered' করা হয়েছে এবং গ্রাহককে কী পাঠানো হয়েছে।";
        }
    }

    if ($orderId > 0) {
        $stmt = $pdo->prepare('SELECT * FROM orders WHERE id = ?');
        $stmt->execute([$orderId]);
        $order = $stmt->fetch();

        if ($order && $action === 'reject') {
            $pdo->prepare("UPDATE orders SET status = 'rejected' WHERE id = ?")->execute([$orderId]);
            if ($order['customer_id']) {
                $pdo->prepare("UPDATE customers SET status = 'removed' WHERE id = ? AND status = 'pending'")
                    ->execute([(int) $order['customer_id']]);
            }
            $message = 'অর্ডার রিজেক্ট হয়েছে।';
        }

        if ($order && in_array($action, ['approve', 'approve_and_send', 'approve_only'], true) && in_array($order['status'], ['pending_payment', 'under_review'], true)) {
            $sendNotif = ($action !== 'approve_only');
            $res = amp_approve_order($pdo, $config, $orderId, $sendNotif);
            if ($res['ok']) {
                $cleanWa = preg_replace('/\D+/', '', (string)$order['whatsapp']);
                if (str_starts_with($cleanWa, '01')) {
                    $cleanWa = '88' . $cleanWa;
                }
                $siteUrl = rtrim((string)($config['site_url'] ?? 'https://automoviepro.com'), '/');
                $dlLink = $siteUrl . '/downloads/AutoMoviePro_Installer_Latest.exe';
                $waMsg = "আসসালামু আলাইকুম {$order['name']},\n\n"
                       . "আপনার AutoMovie Pro অর্ডার #{$orderId} সফলভাবে অ্যাপ্রুভ করা হয়েছে এবং আজীবন মেয়াদের (Lifetime) লাইসেন্স সক্রিয় করা হয়েছে! 🎉\n\n"
                       . "আপনার লগইন তথ্য:\n"
                       . "👤 Login ID: {$res['login_id']}\n"
                       . "🔑 Password: {$res['password']}\n"
                       . "🎫 License Token: {$res['token']}\n\n"
                       . "ডেস্কটপ ইনস্টলার ডাউনলোড লিংক:\n"
                       . "📥 {$dlLink}\n\n"
                       . "সফটওয়্যারটি ডাউনলোড করে রান করুন এবং উপরোক্ত Login ID ও Password দিয়ে লগইন করুন। কোনো সমস্যায় এই হোয়াটসঅ্যাপে যোগাযোগ করুন। ধন্যবাদ!";
                $waShareUrl = "https://wa.me/{$cleanWa}?text=" . rawurlencode($waMsg);

                $approvedCard = [
                    'order_id' => $orderId,
                    'name' => $order['name'],
                    'whatsapp' => $order['whatsapp'],
                    'clean_wa' => $cleanWa,
                    'login_id' => $res['login_id'],
                    'password' => $res['password'],
                    'token' => $res['token'] ?? '',
                    'wa_share_url' => $waShareUrl,
                    'auto_dispatch' => ($action === 'approve_and_send'),
                ];
                if ($action === 'approve_and_send') {
                    $autoDispatchUrl = $waShareUrl;
                    $message = "অর্ডার #{$orderId} ১-ক্লিকে সফলভাবে অনুমোদিত হয়েছে! ইমেইল প্রেরণ করা হয়েছে এবং WhatsApp মেসেজিং উইন্ডো স্বয়ংক্রিয়ভাবে ওপেন করা হয়েছে।";
                } elseif ($action === 'approve_only') {
                    $message = "অর্ডার #{$orderId} শুধুমাত্র অনুমোদিত হয়েছে (কোনো অটোমেটিক মেসেজ পাঠানো হয়নি)।";
                } else {
                    $message = "অর্ডার #{$orderId} সফলভাবে অ্যাপ্রুভ হয়েছে। লগইন তথ্য নিচে প্রদর্শিত হলো।";
                }
            } else {
                $message = "অ্যাপ্রুভ ব্যর্থ: " . ($res['error'] ?? 'Unknown error');
            }
        }
    }
}

$approvedCard = $approvedCard ?? null;
$autoDispatchUrl = $autoDispatchUrl ?? null;

$pending = $pdo->query(
    "SELECT * FROM orders WHERE status IN ('pending_payment', 'under_review') ORDER BY id DESC"
)->fetchAll();
$recent = $pdo->query(
    "SELECT * FROM orders WHERE status NOT IN ('pending_payment', 'under_review') ORDER BY id DESC LIMIT 50"
)->fetchAll();

$googleSubs = [];
try {
    $googleSubs = $pdo->query(
        "SELECT s.*, c.name as customer_name, c.whatsapp as customer_whatsapp 
         FROM google_pro_subscriptions s 
         JOIN customers c ON s.customer_id = c.id 
         ORDER BY s.id DESC LIMIT 50"
    )->fetchAll();
} catch (\Throwable) {}

admin_header('পেমেন্ট কিউ ও ম্যানুয়াল অ্যাপ্রুভাল', 'orders');
if ($message): ?><p class="ok"><?= e($message) ?></p><?php endif; ?>

<?php if ($approvedCard): ?>
  <div style="background: linear-gradient(135deg, #064e3b, #022c22); border: 2px solid #10b981; border-radius: 14px; padding: 1.5rem; margin-bottom: 2rem; color: #fff; box-shadow:0 8px 24px rgba(16,185,129,0.25);">
    <h3 style="color:#6ee7b7; margin-top:0; margin-bottom:0.5rem; font-size:1.25rem;">🎉 অর্ডার #<?= (int) $approvedCard['order_id'] ?> সফলভাবে অনুমোদিত ও আজীবন মেয়াদের (Lifetime) লাইসেন্স অ্যাক্টিভ হয়েছে!</h3>
    <p style="color:#d1fae5; font-size:0.9rem; margin-bottom:1rem;">গ্রাহকের জন্য অ্যাকাউন্ট প্রস্তুত এবং আজীবন মেয়াদের লাইসেন্স টোকেন জেনারেট করা হয়েছে।</p>
    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:0.75rem; margin:1rem 0; background:rgba(0,0,0,0.35); padding:1rem; border-radius:10px; border:1px solid rgba(255,255,255,0.1);">
      <div><strong>গ্রাহক:</strong> <?= e($approvedCard['name']) ?></div>
      <div><strong>WhatsApp:</strong> <?= e($approvedCard['whatsapp']) ?></div>
      <div><strong>Login ID:</strong> <span style="font-family:monospace; background:#0f172a; padding:3px 8px; border-radius:4px; color:#38bdf8; font-weight:bold;"><?= e($approvedCard['login_id']) ?></span></div>
      <div><strong>Password:</strong> <span style="font-family:monospace; background:#0f172a; padding:3px 8px; border-radius:4px; color:#f59e0b; font-weight:bold;"><?= e($approvedCard['password']) ?></span></div>
    </div>
    <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
      <a href="<?= e($approvedCard['wa_share_url']) ?>" target="_blank" rel="noopener" class="btn" style="background:#10b981; color:#022c22; font-weight:bold; font-size:0.95rem; padding:0.65rem 1.25rem; border-radius:8px; text-decoration:none; display:inline-flex; align-items:center; gap:8px;">
        📲 WhatsApp মেসেজ উইন্ডো খুলুন (Send on WhatsApp)
      </a>
      <?php if (!empty($approvedCard['auto_dispatch'])): ?>
        <span style="color:#a7f3d0; font-size:0.85rem;">✓ WhatsApp উইন্ডো স্বয়ংক্রিয়ভাবে ওপেন করা হয়েছে</span>
      <?php endif; ?>
    </div>
  </div>
  <?php if (!empty($autoDispatchUrl)): ?>
    <script>
      window.addEventListener('DOMContentLoaded', function() {
        const w = window.open(<?= json_encode($autoDispatchUrl) ?>, '_blank');
        if (!w) {
          console.log('Popup blocked; admin can click the green button directly.');
        }
      });
    </script>
  <?php endif; ?>
<?php endif; ?>

<h3>পেন্ডিং ও আন্ডার-রিভিউ সফটওয়্যার অর্ডার</h3>
<p style="color:#64748b; font-size:0.9rem; margin-bottom:1rem;">গ্রাহকদের পাঠানো বিকাশ, নগদ ও বাইন্যান্স পেমেন্ট যাচাই করে অনুমোদন করুন। ১-ক্লিক বাটনে স্বয়ংক্রিয়ভাবে ইমেইল যাবে এবং WhatsApp মেসেজ ওপেন হবে।</p>
<table class="data" style="margin-bottom:2.5rem;">
  <thead>
    <tr>
      <th>ID</th>
      <th>গ্রাহক ও WhatsApp</th>
      <th>প্ল্যান ও টাকা</th>
      <th>পেমেন্ট তথ্য (TrxID)</th>
      <th>স্ট্যাটাস</th>
      <th>অর্ডার সময়</th>
      <th>অ্যাকশন</th>
    </tr>
  </thead>
  <tbody>
  <?php foreach ($pending as $o): ?>
    <?php 
      $rawWa = preg_replace('/\D+/', '', (string)$o['whatsapp']);
      $waUrl = 'https://wa.me/' . (str_starts_with($rawWa, '01') ? '88' . $rawWa : $rawWa);
      $isReview = ($o['status'] === 'under_review');
    ?>
    <tr style="<?= $isReview ? 'background:rgba(245, 158, 11, 0.08);' : '' ?>">
      <td><strong>#<?= (int) $o['id'] ?></strong></td>
      <td>
        <strong><?= e($o['name']) ?></strong><br>
        <a href="<?= e($waUrl) ?>" target="_blank" rel="noopener" style="color:#10b981; text-decoration:none; font-weight:600; font-size:0.85rem;">
          📱 <?= e($o['whatsapp']) ?>
        </a>
      </td>
      <td>
        <?= e($o['plan_name']) ?><br>
        <strong style="color:#38bdf8;">৳<?= e((string) $o['amount']) ?></strong>
      </td>
      <td>
        <span style="font-weight:600; text-transform:uppercase; color:#cbd5e1;"><?= e($o['payment_method'] ?: 'bKash / Nagad') ?></span><br>
        <?php if (!empty($o['txn_id'])): ?>
          TrxID: <code style="background:#0f172a; color:#38bdf8; padding:2px 6px; border-radius:4px; font-weight:bold;"><?= e($o['txn_id']) ?></code><br>
        <?php endif; ?>
        <?php if (!empty($o['sender_last_digits'])): ?>
          <small style="color:#94a3b8;">প্রেরক শেষ ডিজিট: <strong><?= e($o['sender_last_digits']) ?></strong></small>
        <?php endif; ?>
      </td>
      <td>
        <?php if ($isReview): ?>
          <span class="badge" style="background:#f59e0b; color:#000; font-weight:bold; font-size:0.8rem; padding:4px 8px; border-radius:6px;">
            ⚡ TrxID জমা দিয়েছে (যাচাই করুন)
          </span>
        <?php else: ?>
          <span class="badge" style="background:#475569; color:#cbd5e1; font-size:0.8rem; padding:4px 8px; border-radius:6px;">
            টাকা পাঠানোর অপেক্ষায়
          </span>
        <?php endif; ?>
      </td>
      <td><small style="color:#64748b;"><?= e($o['created_at']) ?></small></td>
      <td style="white-space:nowrap;">
        <form method="post" style="display:inline-flex; align-items:center; gap:6px; flex-wrap:wrap;">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="order_id" value="<?= (int) $o['id'] ?>">
          <button class="btn btn-sm btn-ok" name="action" value="approve_and_send" style="background:linear-gradient(135deg, #10b981, #059669); font-weight:bold; padding:6px 12px; border-radius:6px; white-space:nowrap;" onclick="return confirm('অর্ডার #<?= (int) $o['id'] ?> ১-ক্লিকে অনুমোদন ও সরাসরি WhatsApp + Email পাঠাবেন?');">
            ⚡ অনুমোদন ও সরাসরি WhatsApp+Email
          </button>
          <button class="btn btn-sm btn-ghost" name="action" value="approve_only" style="padding:6px 10px; font-size:0.8rem; border-color:#0284c7; color:#38bdf8; white-space:nowrap;" onclick="return confirm('মেসেজ ছাড়া শুধুমাত্র অর্ডার #<?= (int) $o['id'] ?> অনুমোদন করবেন?');">
            অনুমোদন (মেসেজ ছাড়া)
          </button>
          <button class="btn btn-sm btn-danger" name="action" value="reject" onclick="return confirm('অর্ডারটি বাতিল করবেন?');" style="padding:6px 10px;">
            Reject
          </button>
        </form>
      </td>
    </tr>
  <?php endforeach; ?>
  <?php if (!$pending): ?><tr><td colspan="7" style="text-align:center; padding:1.5rem; color:#64748b;">কোনো পেন্ডিং বা আন্ডার-রিভিউ অর্ডার নেই</td></tr><?php endif; ?>
  </tbody>
</table>

<h3>🚀 Google AI Pro প্যাকেজ ডেলিভারি ম্যানেজমেন্ট</h3>
<p style="color:#64748b; font-size:0.9rem; margin-bottom:1rem;">গ্রাহকের দেওয়া Gmail অ্যাড্রেস স্টোর করুন এবং Google Pro API Key ইনপুট দিয়ে 'Active & Delivered' বাটনে ক্লিক করুন। গ্রাহকের WhatsApp-এ স্বয়ংক্রিয়ভাবে নোটিফিকেশন পাঠানো হবে।</p>
<table class="data" style="margin-bottom:2.5rem;">
  <thead>
    <tr>
      <th>Sub ID</th>
      <th>গ্রাহক ও মোবাইল</th>
      <th>অর্ডার</th>
      <th>প্ল্যান মেয়াদ</th>
      <th>টাকা</th>
      <th>গ্রাহকের Gmail</th>
      <th>Google Pro Key</th>
      <th>স্ট্যাটাস</th>
      <th>ডেলিভারি অ্যাকশন</th>
    </tr>
  </thead>
  <tbody>
  <?php foreach ($googleSubs as $sub): ?>
    <tr>
      <td>#<?= (int) $sub['id'] ?></td>
      <td>
        <strong><?= e($sub['customer_name'] ?? '—') ?></strong><br>
        <small style="color:#64748b;"><?= e($sub['customer_whatsapp'] ?? '—') ?></small>
      </td>
      <td>#<?= (int) ($sub['order_id'] ?? 0) ?></td>
      <td><?= (int) ($sub['plan_duration_months'] ?? 1) ?> মাস</td>
      <td>৳<?= e((string)$sub['price']) ?></td>
      <td colspan="4" style="padding:0.4rem;">
        <form method="post" style="display:flex; gap:6px; align-items:center;">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="action" value="deliver_google_pro">
          <input type="hidden" name="sub_id" value="<?= (int) $sub['id'] ?>">
          
          <input type="email" name="target_email" value="<?= e($sub['target_email'] ?? '') ?>" placeholder="গ্রাহকের Gmail" style="padding:4px 8px; font-size:0.85rem; width:160px;" required>
          <input type="text" name="google_pro_key" value="<?= e($sub['google_pro_key'] ?? '') ?>" placeholder="Google Pro Key" style="padding:4px 8px; font-size:0.85rem; width:180px;" required>
          <span class="badge" style="<?= $sub['status'] === 'active' ? 'background:#10b981; color:#fff;' : 'background:#f59e0b; color:#fff;' ?>">
            <?= e($sub['status']) ?>
          </span>
          <button class="btn btn-sm btn-ok" style="white-space:nowrap; font-weight:bold;">Active & Delivered</button>
        </form>
      </td>
    </tr>
  <?php endforeach; ?>
  <?php if (!$googleSubs): ?><tr><td colspan="9">কোনো Google Pro সাবস্ক্রিপশন অর্ডার নেই</td></tr><?php endif; ?>
  </tbody>
</table>

<h3>সাম্প্রতিক সম্পূর্ণ অর্ডার তালিকা</h3>
<table class="data">
  <thead><tr><th>ID</th><th>নাম</th><th>WhatsApp</th><th>প্ল্যান</th><th>পেমেন্ট তথ্য</th><th>স্ট্যাটাস</th><th>অ্যাপ্রুভ সময়</th></tr></thead>
  <tbody>
  <?php foreach ($recent as $o): ?>
    <tr>
      <td>#<?= (int) $o['id'] ?></td>
      <td><strong><?= e($o['name']) ?></strong></td>
      <td><?= e($o['whatsapp']) ?></td>
      <td><?= e($o['plan_name']) ?> (৳<?= e((string)$o['amount']) ?>)</td>
      <td>
        <?= e($o['payment_method'] ?? '—') ?>
        <?= !empty($o['txn_id']) ? ' — <code>' . e($o['txn_id']) . '</code>' : '' ?>
      </td>
      <td>
        <span class="badge" style="<?= $o['status'] === 'approved' ? 'background:#10b981; color:#fff;' : 'background:#ef4444; color:#fff;' ?>">
          <?= e($o['status']) ?>
        </span>
      </td>
      <td><?= e($o['approved_at'] ?? '—') ?></td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
<?php admin_footer(); ?>

