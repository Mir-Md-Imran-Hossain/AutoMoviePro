<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = $_POST['action'] ?? '';
    if ($action === 'add') {
        $pdo->prepare(
            'INSERT INTO promo_channels (platform, title, url, is_active, sort_order, created_at)
             VALUES (?, ?, ?, 1, ?, NOW())'
        )->execute([
            $_POST['platform'] === 'facebook' ? 'facebook' : 'youtube',
            trim((string) $_POST['title']),
            trim((string) $_POST['url']),
            (int) ($_POST['sort_order'] ?? 0),
        ]);
    } elseif ($action === 'toggle') {
        $pdo->prepare('UPDATE promo_channels SET is_active = 1 - is_active WHERE id = ?')
            ->execute([(int) $_POST['id']]);
    } elseif ($action === 'delete') {
        $pdo->prepare('DELETE FROM promo_channels WHERE id = ?')->execute([(int) $_POST['id']]);
    }
    redirect('/admin/promo.php');
}

$rows = $pdo->query('SELECT * FROM promo_channels ORDER BY sort_order ASC, id DESC')->fetchAll();
admin_header('প্রোমো FB / YT লিংক', 'promo');
?>
<p class="lead">প্রতিটি কাস্টমার অ্যাপ এই লিংকগুলো ফলো/সাবস্ক্রাইব ও স্ক্রল/প্লে করবে।</p>
<form method="post" class="stack" style="max-width:480px;margin-bottom:1.5rem">
  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
  <input type="hidden" name="action" value="add">
  <label>প্ল্যাটফর্ম
    <select name="platform"><option value="youtube">YouTube</option><option value="facebook">Facebook</option></select>
  </label>
  <label>টাইটেল <input name="title" required></label>
  <label>URL <input name="url" type="url" required></label>
  <label>Sort <input name="sort_order" type="number" value="0"></label>
  <button class="btn" type="submit">যোগ করুন</button>
</form>
<table class="data">
  <thead><tr><th>ID</th><th>প্ল্যাটফর্ম</th><th>টাইটেল</th><th>URL</th><th>অ্যাকটিভ</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($rows as $r): ?>
    <tr>
      <td><?= (int) $r['id'] ?></td>
      <td><?= e($r['platform']) ?></td>
      <td><?= e($r['title']) ?></td>
      <td><a href="<?= e($r['url']) ?>" target="_blank"><?= e($r['url']) ?></a></td>
      <td><?= (int) $r['is_active'] ? 'Yes' : 'No' ?></td>
      <td>
        <form method="post" style="display:inline">
          <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
          <input type="hidden" name="id" value="<?= (int) $r['id'] ?>">
          <button class="btn btn-sm btn-ghost" name="action" value="toggle">Toggle</button>
          <button class="btn btn-sm btn-danger" name="action" value="delete">Delete</button>
        </form>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
<?php admin_footer(); ?>
