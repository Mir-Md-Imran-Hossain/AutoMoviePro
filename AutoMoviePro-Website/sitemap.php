<?php
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';
header('Content-Type: application/xml; charset=utf-8');
$base = rtrim((string) ($config['site_url'] ?? ''), '/');
$langs = amp_cms_langs();
echo '<?xml version="1.0" encoding="UTF-8"?>';
?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <?php foreach ($langs as $lang): ?>
  <url>
    <loc><?= htmlspecialchars($base . '/?lang=' . $lang) ?></loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
    <?php foreach ($langs as $hl): ?>
    <xhtml:link rel="alternate" hreflang="<?= htmlspecialchars($hl) ?>" href="<?= htmlspecialchars($base . '/?lang=' . $hl) ?>" />
    <?php endforeach; ?>
    <xhtml:link rel="alternate" hreflang="x-default" href="<?= htmlspecialchars($base . '/?lang=en') ?>" />
  </url>
  <?php endforeach; ?>
  <url>
    <loc><?= htmlspecialchars($base . '/guide.html') ?></loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
</urlset>
