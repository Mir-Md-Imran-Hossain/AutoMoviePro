<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$day = trim((string) ($_GET['day'] ?? date('Y-m-d')));
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $day)) {
    $day = date('Y-m-d');
}
$customerId = (int) ($_GET['customer_id'] ?? 0);

$params = [$day];
$sql = 'SELECT e.*, c.name AS customer_name, c.login_id
        FROM engage_activity_logs e
        LEFT JOIN customers c ON c.id = e.customer_id
        WHERE e.day = ?';
if ($customerId > 0) {
    $sql .= ' AND e.customer_id = ?';
    $params[] = $customerId;
}
$sql .= ' ORDER BY e.id DESC LIMIT 500';

$stmt = $pdo->prepare($sql);
$stmt->execute($params);
$rows = $stmt->fetchAll();

$customers = $pdo->query(
    "SELECT DISTINCT c.id, c.name, c.login_id
     FROM engage_activity_logs e
     JOIN customers c ON c.id = e.customer_id
     ORDER BY c.name ASC
     LIMIT 200"
)->fetchAll();

admin_header('ট্রাস্ট ব্রাউজ লগ', 'engage');
?>
<form method="get" class="row" style="gap:0.75rem;align-items:end;margin-bottom:1rem">
  <label>দিন
    <input type="date" name="day" value="<?= e($day) ?>">
  </label>
  <label>কাস্টমার
    <select name="customer_id">
      <option value="0">সব</option>
      <?php foreach ($customers as $c): ?>
        <option value="<?= (int) $c['id'] ?>" <?= $customerId === (int) $c['id'] ? 'selected' : '' ?>>
          <?= e($c['name']) ?> (<?= e($c['login_id'] ?? ('#' . $c['id'])) ?>)
        </option>
      <?php endforeach; ?>
    </select>
  </label>
  <button class="btn" type="submit">ফিল্টার</button>
</form>

<p class="muted">প্রতি ইউজারের ব্যাকগ্রাউন্ড ব্রাউজ / লাইক / কমেন্ট / শেয়ার লগ — দিন অনুযায়ী।</p>

<table class="data">
  <thead>
    <tr>
      <th>সময়</th>
      <th>কাস্টমার</th>
      <th>প্ল্যাটফর্ম</th>
      <th>অ্যাকশন</th>
      <th>টাইটেল / ডিটেইল</th>
      <th>লিংক</th>
      <th>OK</th>
    </tr>
  </thead>
  <tbody>
  <?php foreach ($rows as $r): ?>
    <tr>
      <td><?= e($r['created_at']) ?></td>
      <td>
        <a href="/admin/customer_view.php?id=<?= (int) $r['customer_id'] ?>">
          <?= e($r['customer_name'] ?? ('#' . $r['customer_id'])) ?>
        </a>
      </td>
      <td><?= e($r['platform'] ?? '—') ?></td>
      <td><code><?= e($r['action']) ?></code></td>
      <td>
        <?= e($r['title'] ?? '') ?>
        <?php if (!empty($r['detail'])): ?>
          <br><small style="color:var(--muted)"><?= e(mb_strimwidth((string) $r['detail'], 0, 140, '…')) ?></small>
        <?php endif; ?>
      </td>
      <td>
        <?php if (!empty($r['url'])): ?>
          <a href="<?= e($r['url']) ?>" target="_blank" rel="noopener">খুলুন</a>
        <?php else: ?>—<?php endif; ?>
      </td>
      <td><?= !empty($r['ok']) ? '✓' : '✗' ?></td>
    </tr>
  <?php endforeach; ?>
  <?php if (!$rows): ?>
    <tr><td colspan="7">এই দিনে কোনো লগ নেই</td></tr>
  <?php endif; ?>
  </tbody>
</table>
<?php admin_footer(); ?>
