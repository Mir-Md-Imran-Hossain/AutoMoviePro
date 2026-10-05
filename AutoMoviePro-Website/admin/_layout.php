<?php
declare(strict_types=1);

function admin_header(string $title, string $active = ''): void
{
    $items = [
        'dashboard' => ['/admin/index.php', 'ড্যাশবোর্ড'],
        'customers' => ['/admin/customers.php', 'কাস্টমার'],
        'orders' => ['/admin/orders.php', 'পেমেন্ট কিউ'],
        'promo' => ['/admin/promo.php', 'প্রোমো লিংক'],
        'cms' => ['/admin/cms.php', 'ওয়েবসাইট CMS'],
        'learning' => ['/admin/pipeline_learning.php', 'Pipeline Learning'],
        'logs' => ['/admin/logs.php', 'API লগ'],
    ];
    echo '<!DOCTYPE html><html lang="bn"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">';
    echo '<title>' . e($title) . ' — Admin</title><link rel="stylesheet" href="/assets/css/site.css"></head>';
    echo '<body class="admin-body"><div class="admin-shell"><aside class="admin-nav">';
    echo '<div class="logo" style="margin-bottom:1rem">AMP <span>Admin</span></div>';
    foreach ($items as $key => [$href, $label]) {
        $cls = $active === $key ? 'active' : '';
        echo '<a class="' . $cls . '" href="' . e($href) . '">' . e($label) . '</a>';
    }
    echo '<a href="/admin/logout.php">লগআউট</a></aside><main class="admin-main">';
    echo '<h2 style="font-family:var(--font-display);margin-top:0">' . e($title) . '</h2>';
}

function admin_footer(): void
{
    echo '</main></div></body></html>';
}
