<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $id = (int) ($_POST['id'] ?? 0);
    $action = $_POST['action'] ?? '';
    if ($id > 0) {
        if ($action === 'activate') {
            $pdo->prepare("UPDATE customers SET status = 'active', activated_at = COALESCE(activated_at, NOW()) WHERE id = ?")
                ->execute([$id]);
        } elseif ($action === 'deactivate') {
            $pdo->prepare("UPDATE customers SET status = 'inactive' WHERE id = ?")->execute([$id]);
            $pdo->prepare('UPDATE licenses SET revoked = 1 WHERE customer_id = ?')->execute([$id]);
        } elseif ($action === 'remove') {
            $pdo->prepare("UPDATE customers SET status = 'removed' WHERE id = ?")->execute([$id]);
            $pdo->prepare('UPDATE licenses SET revoked = 1 WHERE customer_id = ?')->execute([$id]);
        }
    }
    redirect('/admin/customers.php');
}

$rows = $pdo->query(
    "SELECT * FROM customers WHERE status != 'removed' ORDER BY id DESC"
)->fetchAll();

admin_header('কাস্টমার', 'customers');
?>
<table class="data">
  <thead>
    <tr>
      <th>ID</th><th>নাম</th><th>WhatsApp</th><th>Login</th><th>স্ট্যাটাস</th>
      <th>দিন</th><th>Heartbeat</th><th>অ্যাকশন</th>
    </tr>
  </thead>
  <tbody>
  <?php foreach ($rows as $r): ?>
    <tr>
      <td><a href="/admin/customer_view.php?id=<?= (int) $r['id'] ?>"><?= (int) $r['id'] ?></a></td>
      <td><?= e($r['name']) ?></td>
      <td><?= e($r['whatsapp']) ?></td>
      <td><?= e($r['login_id'] ?? '—') ?></td>
      <td><span class="badge <?= e($r['status']) ?>"><?= e($r['status']) ?></span></td>
      <td><?= days_since($r['activated_at'] ?: $r['created_at']) ?></td>
      <td><?= e($r['last_heartbeat_at'] ?? '—') ?></td>
      <td>
        <form method="post" style="display:inline">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="id" value="<?= (int) $r['id'] ?>">
          <?php if ($r['status'] !== 'active'): ?>
            <button class="btn btn-sm btn-ok" name="action" value="activate">Active</button>
          <?php endif; ?>
          <?php if ($r['status'] === 'active'): ?>
            <button class="btn btn-sm btn-ghost" name="action" value="deactivate">Deactive</button>
          <?php endif; ?>
          <button class="btn btn-sm btn-danger" name="action" value="remove" onclick="return confirm('রিমুভ করবেন?')">Remove</button>
        </form>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
<?php admin_footer(); ?>
