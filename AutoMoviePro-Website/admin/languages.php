<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';
$error = '';
$catalog = amp_lang_catalog();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!csrf_verify($_POST['csrf'] ?? null)) {
        $error = 'সেশনের মেয়াদ শেষ হয়েছে বা ফর্মের টোকেন মেয়াদোত্তীর্ণ। অনুগ্রহ করে পৃষ্ঠাটি রিলোড করে পুনরায় ফর্ম পূরণ করুন।';
    } else {
        $orderId = (int) ($_POST['order_id'] ?? 0);
        $action = $_POST['action'] ?? '';
        $stmt = $pdo->prepare('SELECT * FROM language_orders WHERE id = ?');
        $stmt->execute([$orderId]);
        $order = $stmt->fetch();

        if ($order && $action === 'reject') {
            $pdo->prepare("UPDATE language_orders SET status = 'rejected' WHERE id = ?")
                ->execute([$orderId]);
            $message = 'ভাষা আবেদন রিজেক্ট হয়েছে।';
        }

        if ($order && $action === 'approve' && $order['status'] === 'pending_payment') {
            $customerId = (int) $order['customer_id'];
            $lang = (string) $order['lang_code'];
            amp_unlock_customer_lang($pdo, $customerId, $lang, 'admin_approve');
            $nowVal = date('Y-m-d H:i:s');
            $pdo->prepare("UPDATE language_orders SET status = 'approved', approved_at = ? WHERE id = ?")
                ->execute([$nowVal, $orderId]);

            $cust = $pdo->prepare('SELECT name, whatsapp FROM customers WHERE id = ?');
            $cust->execute([$customerId]);
            $c = $cust->fetch();
            if ($c && !empty($c['whatsapp'])) {
                $langName = $catalog[$lang] ?? $lang;
                $body = "AutoMovie Pro: আপনার {$langName} ভাষা অ্যাপ্রুভ হয়েছে। সফটওয়্যারে Language Sync চাপুন।";
                $cleanWa = preg_replace('/\D+/', '', (string)$c['whatsapp']);
                if (str_starts_with($cleanWa, '01')) $cleanWa = '880' . substr($cleanWa, 1);
                whatsapp_antiban_dispatch($pdo, $config, $cleanWa, $body, 'high', 'language_unlocked', $customerId, (string)$orderId, $c['name']);
            }
            $message = 'ভাষা অ্যাপ্রুভ সম্পন্ন ও কাস্টমারের WhatsApp-এ স্বয়ংক্রিয় নোটিফিকেশন পাঠানো হয়েছে।';
        }
    }
}

$pending = $pdo->query(
    "SELECT lo.*, c.name, c.login_id, c.whatsapp
     FROM language_orders lo
     JOIN customers c ON c.id = lo.customer_id
     WHERE lo.status = 'pending_payment'
     ORDER BY lo.id ASC"
)->fetchAll();
$recent = $pdo->query(
    "SELECT lo.*, c.name, c.login_id
     FROM language_orders lo
     JOIN customers c ON c.id = lo.customer_id
     WHERE lo.status != 'pending_payment'
     ORDER BY lo.id DESC LIMIT 40"
)->fetchAll();

admin_header('ভাষা পেমেন্ট কিউ', 'languages');
?>
<?php if ($message): ?><p class="ok"><?= e($message) ?></p><?php endif; ?>
<?php if ($error): ?><p class="err" style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); border-radius:8px; padding:10px 14px; margin-bottom:1.5rem; color:#fca5a5; font-size:0.95rem; font-weight:700;">⚠️ <?= e($error) ?></p><?php endif; ?>

<p class="lead">প্রতিটি আবেদন = একটি নতুন ভাষা আনলক (সর্বোচ্চ ৬)। অ্যাপ্রুভের পর কাস্টমার অ্যাপে Sync করবে।</p>

<h3>পেন্ডিং</h3>
<table class="data">
  <thead>
    <tr>
      <th>ID</th><th>কাস্টমার</th><th>ভাষা</th><th>টাকা</th><th>রেফ</th><th>নোট</th><th>সময়</th><th></th>
    </tr>
  </thead>
  <tbody>
  <?php foreach ($pending as $o): ?>
    <tr>
      <td><?= (int) $o['id'] ?></td>
      <td><?= e($o['name']) ?> <span class="muted">(<?= e((string) ($o['login_id'] ?? '')) ?>)</span></td>
      <td><?= e($catalog[$o['lang_code']] ?? $o['lang_code']) ?></td>
      <td><?= e((string) $o['amount']) ?></td>
      <td><?= e((string) ($o['payment_ref'] ?? '—')) ?></td>
      <td><?= e((string) ($o['payment_note'] ?? '—')) ?></td>
      <td><?= e($o['created_at']) ?></td>
      <td>
        <form method="post" style="display:inline">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="order_id" value="<?= (int) $o['id'] ?>">
          <button class="btn btn-sm btn-ok" name="action" value="approve">Approve</button>
          <button class="btn btn-sm btn-danger" name="action" value="reject">Reject</button>
        </form>
      </td>
    </tr>
  <?php endforeach; ?>
  <?php if (!$pending): ?><tr><td colspan="8">কোনো পেন্ডিং নেই</td></tr><?php endif; ?>
  </tbody>
</table>

<h3>সাম্প্রতিক</h3>
<table class="data">
  <thead><tr><th>ID</th><th>কাস্টমার</th><th>ভাষা</th><th>স্ট্যাটাস</th><th>অ্যাপ্রুভ</th></tr></thead>
  <tbody>
  <?php foreach ($recent as $o): ?>
    <tr>
      <td><?= (int) $o['id'] ?></td>
      <td><?= e($o['name']) ?></td>
      <td><?= e($catalog[$o['lang_code']] ?? $o['lang_code']) ?></td>
      <td><span class="badge"><?= e($o['status']) ?></span></td>
      <td><?= e($o['approved_at'] ?? '—') ?></td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
<?php admin_footer(); ?>
