<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $id = (int) ($_POST['id'] ?? 0);
    $status = (string) ($_POST['status'] ?? 'open');
    $note = trim((string) ($_POST['admin_note'] ?? ''));
    if (!in_array($status, ['open', 'in_progress', 'resolved'], true)) {
        $status = 'open';
    }
    if ($id > 0) {
        if ($status === 'resolved') {
            $pdo->prepare(
                'UPDATE agent_tickets SET status = ?, admin_note = ?, resolved_at = NOW() WHERE id = ?'
            )->execute([$status, $note !== '' ? $note : null, $id]);
        } else {
            $pdo->prepare(
                'UPDATE agent_tickets SET status = ?, admin_note = ? WHERE id = ?'
            )->execute([$status, $note !== '' ? $note : null, $id]);
        }
    }
    redirect('/admin/tickets.php');
}

$rows = $pdo->query(
    "SELECT t.*, c.name, c.login_id, c.whatsapp AS cust_whatsapp
     FROM agent_tickets t
     LEFT JOIN customers c ON c.id = t.customer_id
     ORDER BY (CASE WHEN t.status = 'open' THEN 1 WHEN t.status = 'in_progress' THEN 2 ELSE 3 END), t.id DESC
     LIMIT 200"
)->fetchAll();

admin_header('এজেন্ট টিকেট ও সাপোর্ট', 'tickets');
?>
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; flex-wrap:wrap; gap:10px;">
  <p class="lead" style="margin:0;">গ্রাহক ও সিস্টেম সাপোর্ট টিকেট — সর্বোচ্চ ৭২ ঘণ্টার মধ্যে সমাধান ও ফিডব্যাক প্রদান করুন।</p>
</div>

<table class="table">
  <thead>
    <tr>
      <th>#টিকিট</th>
      <th>গ্রাহক / যোগাযোগ</th>
      <th>ক্যাটাগরি</th>
      <th>অভিযোগ / পরামর্শের বিবরণ</th>
      <th>স্ট্যাটাস</th>
      <th>অ্যাকশন ও রিপ্লাই</th>
    </tr>
  </thead>
  <tbody>
  <?php foreach ($rows as $r): 
    $ticketNum = 'AMP-TK' . str_pad((string)$r['id'], 4, '0', STR_PAD_LEFT);
    $waPhone = preg_replace('/\D+/', '', (string)($r['cust_whatsapp'] ?? ''));
    if ($waPhone === '') {
        // Check if message has contact info embedded like [যোগাযোগ: 01...]
        if (preg_match('/\[যোগাযোগ:\s*([0-9+]+)\]/', (string)($r['message'] ?? ''), $m)) {
            $waPhone = preg_replace('/\D+/', '', $m[1]);
        }
    }
    if ($waPhone !== '' && str_starts_with($waPhone, '01')) {
        $waPhone = '88' . $waPhone;
    }
  ?>
    <tr>
      <td><strong><?= e($ticketNum) ?></strong></td>
      <td>
        <strong><?= e($r['name'] ?? 'গ্রাহক (Guest / Local App)') ?></strong><br>
        <?php if (!empty($r['login_id'])): ?>
          <code><?= e($r['login_id']) ?></code><br>
        <?php endif; ?>
        <?php if ($waPhone !== ''): ?>
          <span style="color:#10b981; font-weight:bold;">📱 +<?= e($waPhone) ?></span>
        <?php endif; ?>
      </td>
      <td><span class="badge" style="background:#1e293b; color:#38bdf8;"><?= e(mb_substr((string) ($r['reason'] ?? 'সাধারণ সাপোর্ট'), 0, 100)) ?></span></td>
      <td style="max-width:320px;">
        <div style="font-size:0.9rem; line-height:1.5; color:#cbd5e1;"><?= nl2br(e(mb_substr((string) ($r['message'] ?? ''), 0, 300))) ?></div>
        <?php if (!empty($r['screenshot_note'])): ?>
          <details style="margin-top:4px;"><summary style="cursor:pointer; font-size:0.8rem; color:#f59e0b;">স্ক্রিনশট নোট</summary><pre style="font-size:0.8rem;"><?= e($r['screenshot_note']) ?></pre></details>
        <?php endif; ?>
      </td>
      <td>
        <?php 
          $badgeColor = $r['status'] === 'open' ? '#ef4444' : ($r['status'] === 'in_progress' ? '#f59e0b' : '#10b981');
        ?>
        <span class="badge" style="background:<?= $badgeColor ?>; color:#fff; text-transform:uppercase; font-size:0.75rem;"><?= e($r['status']) ?></span>
      </td>
      <td>
        <form method="post" class="stack" style="gap:6px;">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="id" value="<?= (int) $r['id'] ?>">
          <select name="status" style="padding:4px 8px; border-radius:6px; background:#0f172a; color:#fff; border:1px solid #334155;">
            <?php foreach (['open' => '🔴 Open', 'in_progress' => '🟡 In Progress', 'resolved' => '🟢 Resolved'] as $stKey => $stLbl): ?>
              <option value="<?= $stKey ?>" <?= $r['status'] === $stKey ? 'selected' : '' ?>><?= $stLbl ?></option>
            <?php endforeach; ?>
          </select>
          <textarea name="admin_note" rows="2" placeholder="সমাধান বা অ্যাডমিন নোট লিখুন..." style="width:100%; font-size:0.85rem; padding:4px;"><?= e($r['admin_note'] ?? '') ?></textarea>
          <div style="display:flex; gap:6px; align-items:center;">
            <button class="btn btn-sm" type="submit" style="padding:4px 10px;">💾 সেভ</button>
            <?php if ($waPhone !== ''): 
              $replyText = rawurlencode("আসসালামু আলাইকুম!\nAutoMovie Pro সাপোর্ট টিম থেকে আপনার টিকিট ({$ticketNum}) এর সমাধান ও আপডেট:\n" . ($r['admin_note'] ?: "আপনার সমস্যার সমাধান সম্পন্ন হয়েছে। সফটওয়্যার রিস্টার্ট দিয়ে পুনরায় পরীক্ষা করার অনুরোধ রইল। ধন্যবাদ!"));
            ?>
              <a href="https://wa.me/<?= e($waPhone) ?>?text=<?= $replyText ?>" target="_blank" class="btn btn-sm" style="background:#10b981; color:#fff; text-decoration:none; padding:4px 8px; white-space:nowrap;">
                💬 WhatsApp রিপ্লাই
              </a>
            <?php endif; ?>
          </div>
        </form>
      </td>
    </tr>
  <?php endforeach; ?>
  <?php if (!$rows): ?>
    <tr><td colspan="6" class="muted" style="text-align:center; padding:2rem;">কোনো পেন্ডিং সাপোর্ট বা অভিযোগ টিকেট নেই।</td></tr>
  <?php endif; ?>
  </tbody>
</table>
<?php admin_footer(); ?>

