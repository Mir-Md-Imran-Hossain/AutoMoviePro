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

admin_header('API লগ', 'logs');
?>
<table class="data">
  <thead><tr><th>সময়</th><th>কাস্টমার</th><th>অ্যাকশন</th><th>ডিটেইল</th><th>IP</th></tr></thead>
  <tbody>
  <?php foreach ($rows as $r): ?>
    <tr>
      <td><?= e($r['created_at']) ?></td>
      <td><?= e($r['customer_name'] ?? ('#' . $r['customer_id'])) ?> <?= e($r['login_id'] ?? '') ?></td>
      <td><?= e($r['action']) ?></td>
      <td><?= e($r['detail'] ?? '') ?></td>
      <td><?= e($r['ip_address'] ?? '') ?></td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
<?php admin_footer(); ?>
