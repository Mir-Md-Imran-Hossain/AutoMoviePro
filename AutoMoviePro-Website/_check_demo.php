<?php
require __DIR__ . '/includes/local_demo.php';
$p = amp_local_demo_pdo();
echo "sqlite_ok\n";
echo "price=" . $p->query("SELECT setting_value FROM site_settings WHERE setting_key='price_amount'")->fetchColumn() . "\n";
