<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$candidates = [
    dirname(__DIR__, 2) . DIRECTORY_SEPARATOR . 'AutoMoviePro-Software' . DIRECTORY_SEPARATOR . 'Output' . DIRECTORY_SEPARATOR . '_admin_learning',
    dirname(__DIR__) . DIRECTORY_SEPARATOR . '..' . DIRECTORY_SEPARATOR . 'AutoMoviePro-Software' . DIRECTORY_SEPARATOR . 'Output' . DIRECTORY_SEPARATOR . '_admin_learning',
    getenv('AMP_ADMIN_LEARNING_DIR') ?: '',
];
$root = '';
foreach ($candidates as $c) {
    if ($c && is_dir($c)) {
        $root = $c;
        break;
    }
}

$lessons = [];
$inbox = [];
if ($root) {
    $lf = $root . DIRECTORY_SEPARATOR . 'lessons.json';
    if (is_file($lf)) {
        $lessons = json_decode((string) file_get_contents($lf), true) ?: [];
    }
    $inboxDir = $root . DIRECTORY_SEPARATOR . 'inbox';
    if (is_dir($inboxDir)) {
        foreach (glob($inboxDir . DIRECTORY_SEPARATOR . '*.json') ?: [] as $f) {
            $inbox[] = [
                'file' => basename($f),
                'data' => json_decode((string) file_get_contents($f), true),
            ];
        }
        usort($inbox, static function ($a, $b) {
            return strcmp($b['file'], $a['file']);
        });
    }
}

admin_header('Pipeline Learning', 'learning');
?>
<p>জেনারেশন ভুলগুলো এখানে রেকর্ড হয় — পাইপলাইন পরবর্তী রানে অটো-ফিক্স করে, অ্যাডমিন ইউজারদের কাছে লেসন পুশ করতে পারে।</p>
<?php if (!$root): ?>
  <p>Learning directory পাওয়া যায়নি। <code>AMP_ADMIN_LEARNING_DIR</code> সেট করুন অথবা Software <code>Output/_admin_learning</code> রাখুন।</p>
<?php else: ?>
  <p><code><?= e($root) ?></code></p>
  <h3>Active lessons</h3>
  <ul>
  <?php foreach (($lessons['items'] ?? []) as $item): ?>
    <li>
      <strong><?= e((string) ($item['kind'] ?? '')) ?></strong>
      — <?= e((string) ($item['title'] ?? '')) ?><br>
      <em>Fix:</em> <?= e((string) ($item['fix'] ?? '')) ?>
    </li>
  <?php endforeach; ?>
  </ul>
  <h3>Inbox</h3>
  <ol>
  <?php foreach (array_slice($inbox, 0, 40) as $row): ?>
    <li>
      <code><?= e($row['file']) ?></code><br>
      <?= e((string) (($row['data']['title'] ?? ''))) ?><br>
      <?= e((string) (($row['data']['detail'] ?? ''))) ?>
    </li>
  <?php endforeach; ?>
  </ol>
<?php endif; ?>
<?php admin_footer(); ?>
