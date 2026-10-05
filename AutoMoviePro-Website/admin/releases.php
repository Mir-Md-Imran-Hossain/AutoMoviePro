<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require dirname(__DIR__) . '/includes/release_service.php';
require __DIR__ . '/_layout.php';
require_admin();

$flash = '';
$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = (string) ($_POST['action'] ?? 'publish');
    if ($action === 'publish') {
        $version = trim((string) ($_POST['version'] ?? ''));
        $notes = trim((string) ($_POST['release_notes'] ?? ''));
        $forceHours = (int) ($_POST['force_hours'] ?? 24);
        $forceUpdate = isset($_POST['force_update']);
        $file = $_FILES['installer'] ?? null;
        if (!$file || (int) ($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
            $error = 'ইনস্টলার ফাইল আপলোড হয়নি।';
        } else {
            $tmp = (string) ($file['tmp_name'] ?? '');
            $name = (string) ($file['name'] ?? '');
            if (!preg_match('/\.(exe|msi|zip)$/i', $name)) {
                $error = 'শুধু .exe / .msi / .zip অনুমোদিত।';
            } else {
                $staging = amp_downloads_dir() . DIRECTORY_SEPARATOR . '_upload_' . bin2hex(random_bytes(6)) . '.bin';
                if (!@move_uploaded_file($tmp, $staging)) {
                    $error = 'স্টেজিং ফেইল — PHP upload_tmp_dir / downloads পারমিশন চেক করুন।';
                } else {
                    $adminName = (string) ($_SESSION['admin_username'] ?? 'admin');
                    $res = amp_publish_release(
                        $pdo,
                        $config,
                        $staging,
                        $version,
                        $notes,
                        $forceHours,
                        $forceUpdate,
                        $adminName
                    );
                    if (!empty($res['ok'])) {
                        $flash = 'নতুন ভার্সন ' . e($version) . ' লাইভ। পুরনো ইনস্টলার রিমুভ হয়েছে। সব ক্লায়েন্ট ২৪ঘণ্টার নোটিফিকেশন পাবে।';
                    } else {
                        $error = 'পাবলিশ ফেইল: ' . e((string) ($res['error'] ?? 'unknown'));
                        @unlink($staging);
                    }
                }
            }
        }
    }
}

$current = amp_current_release($pdo);
$history = $pdo->query('SELECT * FROM app_releases ORDER BY id DESC LIMIT 8')->fetchAll();
$publicUrl = amp_release_public_url($config);
$diskFile = amp_downloads_dir() . DIRECTORY_SEPARATOR . amp_canonical_installer_name();
$diskOk = is_file($diskFile);

admin_header('সফটওয়্যার রিলিজ / আপডেট', 'releases');
?>
<?php if ($flash): ?><p class="ok"><?= $flash ?></p><?php endif; ?>
<?php if ($error): ?><p class="err"><?= $error ?></p><?php endif; ?>

<p class="lead">
  নতুন Setup আপলোড করলে সিস্টেম সেটাকে <strong>downloads/<?= e(amp_canonical_installer_name()) ?></strong> এ বসায়,
  আগের ফাইল মুছে দেয়, এবং সব ইউজার অ্যাপে <strong>২৪ ঘণ্টার আপডেট নোটিফিকেশন</strong> যায়।
  আপডেটে ইউজারের <code>data/</code>, লগইন, চ্যানেল, সেশন অক্ষুণ্ণ থাকে।
</p>

<div class="card" style="margin-bottom:1.25rem">
  <h3 style="margin-top:0">বর্তমান লাইভ</h3>
  <?php if ($current): ?>
    <p>
      ভার্সন: <strong><?= e((string) $current['version']) ?></strong><br>
      সাইজ: <?= number_format(((int) $current['file_size']) / 1048576, 1) ?> MB<br>
      SHA256: <code style="font-size:0.75rem;word-break:break-all"><?= e((string) ($current['sha256'] ?? '')) ?></code><br>
      পাবলিশ: <?= e((string) $current['published_at']) ?><br>
      ফোর্স উইন্ডো: <?= (int) $current['force_hours'] ?> ঘণ্টা<br>
      ডাউনলোড URL: <a href="<?= e($publicUrl) ?>" target="_blank"><?= e($publicUrl) ?></a><br>
      ডিস্ক ফাইল: <?= $diskOk ? '✓ আছে' : '✗ নেই' ?>
    </p>
  <?php else: ?>
    <p class="muted">এখনো কোনো রিলিজ পাবলিশ হয়নি। নিচে প্রথম Setup আপলোড করুন।</p>
    <p>টার্গেট URL: <a href="<?= e($publicUrl) ?>"><?= e($publicUrl) ?></a> — ডিস্ক: <?= $diskOk ? 'ফাইল আছে (মেটা নেই)' : 'ফাইল নেই' ?></p>
  <?php endif; ?>
</div>

<form method="post" enctype="multipart/form-data" class="stack" style="max-width:520px;margin-bottom:2rem">
  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
  <input type="hidden" name="action" value="publish">
  <label>নতুন ভার্সন (যেমন 1.2.0)
    <input name="version" required pattern="[0-9]+(\.[0-9]+){0,3}" placeholder="1.2.0"
           value="<?= e((string) ($_POST['version'] ?? '')) ?>">
  </label>
  <label>Setup ফাইল (.exe)
    <input type="file" name="installer" accept=".exe,.msi,.zip" required>
  </label>
  <label>রিলিজ নোট
    <textarea name="release_notes" rows="3" placeholder="কী কী ফিক্স/ফিচার…"></textarea>
  </label>
  <label>ফোর্স আপডেট উইন্ডো (ঘণ্টা)
    <input type="number" name="force_hours" min="1" max="168" value="24">
  </label>
  <label style="display:flex;gap:0.5rem;align-items:center">
    <input type="checkbox" name="force_update" value="1" checked>
    সব ইউজারকে ডেডলাইনের মধ্যে আপডেট বাধ্যতামূলক
  </label>
  <button class="btn" type="submit">আপলোড ও লাইভ করুন</button>
</form>

<h3>ইতিহাস</h3>
<table class="data">
  <thead><tr><th>ID</th><th>Version</th><th>Current</th><th>Size</th><th>Published</th><th>Force h</th></tr></thead>
  <tbody>
  <?php foreach ($history as $r): ?>
    <tr>
      <td><?= (int) $r['id'] ?></td>
      <td><?= e((string) $r['version']) ?></td>
      <td><?= (int) $r['is_current'] ? '✓' : '' ?></td>
      <td><?= number_format(((int) $r['file_size']) / 1048576, 1) ?> MB</td>
      <td><?= e((string) $r['published_at']) ?></td>
      <td><?= (int) $r['force_hours'] ?></td>
    </tr>
  <?php endforeach; ?>
  <?php if (!$history): ?>
    <tr><td colspan="6" class="muted">খালি</td></tr>
  <?php endif; ?>
  </tbody>
</table>
<?php admin_footer(); ?>
