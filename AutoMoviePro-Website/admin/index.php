<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$total = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status != 'removed'")->fetchColumn();
$active = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'active'")->fetchColumn();
$pending = (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status = 'pending_payment'")->fetchColumn();
$uploadsToday = (int) $pdo->query("SELECT COUNT(*) FROM customer_jobs WHERE DATE(created_at) = CURDATE()")->fetchColumn();

admin_header('ড্যাশবোর্ড', 'dashboard');
?>
<div class="stats">
  <div class="stat"><span>মোট কাস্টমার</span><b><?= $total ?></b></div>
  <div class="stat"><span>অ্যাকটিভ</span><b><?= $active ?></b></div>
  <div class="stat"><span>পেন্ডিং পেমেন্ট</span><b><?= $pending ?></b></div>
  <div class="stat"><span>আজকের জব</span><b><?= $uploadsToday ?></b></div>
</div>
<p class="lead">পেমেন্ট অ্যাপ্রুভ করতে <a href="/admin/orders.php">পেমেন্ট কিউ</a> দেখুন।</p>
<?php admin_footer(); ?>
