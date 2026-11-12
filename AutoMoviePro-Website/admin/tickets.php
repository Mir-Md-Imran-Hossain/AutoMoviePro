<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$ticketError = null;
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!csrf_verify($_POST['csrf'] ?? null)) {
        $ticketError = 'সেশনের মেয়াদ শেষ হয়েছে বা ফর্মের সিকিউরিটি টোকেন মেয়াদোত্তীর্ণ। অনুগ্রহ করে পৃষ্ঠাটি রিলোড করে পুনরায় চেষ্টা করুন।';
    } else {
        $id = (int) ($_POST['id'] ?? 0);
        $status = (string) ($_POST['status'] ?? 'open');
        $note = trim((string) ($_POST['admin_note'] ?? ''));
        if (!in_array($status, ['open', 'in_progress', 'resolved'], true)) {
            $status = 'open';
        }
        if ($id > 0) {
            $nowVal = date('Y-m-d H:i:s');
            if ($status === 'resolved') {
                $pdo->prepare(
                    'UPDATE agent_tickets SET status = ?, admin_note = ?, resolved_at = ? WHERE id = ?'
                )->execute([$status, $note !== '' ? $note : null, $nowVal, $id]);
            } else {
                $pdo->prepare(
                    'UPDATE agent_tickets SET status = ?, admin_note = ? WHERE id = ?'
                )->execute([$status, $note !== '' ? $note : null, $id]);
            }

        // Auto-dispatch WhatsApp reply to customer if phone number exists and note is given
        if (!empty($_POST['send_whatsapp_reply']) || !empty($_POST['send_wa'])) {
            try {
                $tStmt = $pdo->prepare('SELECT t.*, c.name, c.whatsapp AS cust_whatsapp FROM agent_tickets t LEFT JOIN customers c ON c.id = t.customer_id WHERE t.id = ?');
                $tStmt->execute([$id]);
                $tData = $tStmt->fetch();
                if ($tData) {
                    $targetWa = trim((string)($tData['cust_whatsapp'] ?: ($tData['user_phone'] ?? '')));
                    if ($targetWa !== '') {
                        $cName = $tData['name'] ?: 'গ্রাহক';
                        $ticketNum = 'TCK-' . str_pad((string)$id, 5, '0', STR_PAD_LEFT);
                        $stBangla = ($status === 'resolved') ? 'সমাধান করা হয়েছে (Resolved)' : (($status === 'in_progress') ? 'প্রক্রিয়াধীন রয়েছে (In Progress)' : 'উন্মুক্ত (Open)');
                        $replyMsg = "আসসালামু আলাইকুম {$cName}!\nAutoMovie Pro সাপোর্ট টিম থেকে আপনার টিকিট ({$ticketNum}) এর আপডেট:\n\n"
                                  . "📌 স্ট্যাটাস: {$stBangla}\n"
                                  . "💬 সমাধানের বিবরণ:\n" . ($note ?: "আপনার সমস্যার সমাধান সম্পন্ন হয়েছে। সফটওয়্যার রিস্টার্ট দিয়ে পুনরায় পরীক্ষা করার অনুরোধ রইল।\n\nধন্যবাদ!");
                        $cleanWa = preg_replace('/\D+/', '', $targetWa);
                        if (str_starts_with($cleanWa, '01')) $cleanWa = '880' . substr($cleanWa, 1);
                        whatsapp_antiban_dispatch($pdo, $config, $cleanWa, $replyMsg, 'high', 'support_ticket_reply', (int)($tData['customer_id'] ?? 0), null, $cName);
                    }
                }
            } catch (\Throwable $eTick) {}
        }
    }
    redirect('/admin/tickets.php');
}
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

<?php if (!empty($ticketError)): ?>
  <div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#fca5a5; font-size:0.95rem; font-weight:600;">
    ⚠️ <?= e($ticketError) ?>
  </div>
<?php endif; ?>
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
          <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
            <button class="btn btn-sm" type="submit" style="padding:4px 10px;">💾 সেভ</button>
            <?php if ($waPhone !== ''): ?>
              <button class="btn btn-sm" type="submit" name="send_whatsapp_reply" value="1" style="background:#10b981; color:#fff; padding:4px 10px; font-weight:700; white-space:nowrap;" title="সার্ভারের WhatsApp গেটওয়ে থেকে সরাসরি গ্রাহকের মোবাইলে নোটিফিকেশন যাবে">
                ⚡ সেভ ও অটো WhatsApp রিপ্লাই
              </button>
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

