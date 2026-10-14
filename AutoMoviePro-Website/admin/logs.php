<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$rows = $pdo->query(
    'SELECT a.*, c.name AS customer_name, c.login_id
     FROM api_logs a
     LEFT JOIN customers c ON c.id = a.customer_id
     ORDER BY a.id DESC LIMIT 200'
)->fetchAll();

admin_header('সিস্টেম ট্র্যাকিং ও এপিআই লগ', 'logs');
?>

<div class="admin-card">
  <div class="card-header">
    <div class="card-title">
      <span>📋</span>
      <span>সিস্টেম এপিআই ও সিকিউরিটি লগ (সর্বশেষ ২০০টি)</span>
    </div>
    <span style="font-size:0.85rem; color:#94a3b8;">অটোমেটেড সিকিউরিটি মনিটরিং</span>
  </div>

  <div style="overflow-x:auto;">
    <table class="admin-table">
      <thead>
        <tr>
          <th style="width:170px;">সময়</th>
          <th style="width:200px;">কাস্টমার / ইউজার</th>
          <th style="width:160px;">অ্যাকশন</th>
          <th>ডিটেইল</th>
          <th style="width:130px; text-align:right;">IP অ্যাড্রেস</th>
        </tr>
      </thead>
      <tbody>
        <?php if (empty($rows)): ?>
          <tr>
            <td colspan="5" style="text-align:center; padding:3rem; color:#64748b;">
              কোনো সিস্টেম লগ পাওয়া যায়নি।
            </td>
          </tr>
        <?php else: ?>
          <?php foreach ($rows as $r): ?>
            <tr>
              <td style="color:#94a3b8; font-size:0.85rem;">
                <?= date('d M Y, h:i A', strtotime($r['created_at'])) ?>
              </td>
              <td>
                <div style="font-weight:600; color:#f8fafc; font-size:0.9rem;">
                  <?= e($r['customer_name'] ?? ('Customer #' . $r['customer_id'])) ?>
                </div>
                <?php if (!empty($r['login_id'])): ?>
                  <div style="font-size:0.75rem; color:#38bdf8;"><?= e($r['login_id']) ?></div>
                <?php endif; ?>
              </td>
              <td>
                <span class="admin-badge badge-info" style="font-size:0.75rem;">
                  <?= e($r['action']) ?>
                </span>
              </td>
              <td style="color:#cbd5e1; font-size:0.88rem;">
                <?= e($r['detail'] ?? '—') ?>
              </td>
              <td style="text-align:right; font-family:monospace; font-size:0.8rem; color:#94a3b8;">
                <?= e($r['ip_address'] ?? '—') ?>
              </td>
            </tr>
          <?php endforeach; ?>
        <?php endif; ?>
      </tbody>
    </table>
  </div>
</div>

<?php admin_footer(); ?>
