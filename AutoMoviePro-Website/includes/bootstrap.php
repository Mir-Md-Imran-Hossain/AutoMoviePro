<?php
declare(strict_types=1);

session_start();

require_once __DIR__ . '/local_demo.php';

$configPath = dirname(__DIR__) . '/config.php';
$useLocalDemo = !is_file($configPath) && amp_local_demo_enabled();

if (!is_file($configPath) && !$useLocalDemo) {
    $req = $_SERVER['REQUEST_URI'] ?? '';
    if (strpos($req, 'install') === false) {
        $base = rtrim(str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '')), '/');
        if (str_ends_with($base, '/admin') || str_ends_with($base, '/api')) {
            $base = dirname($base);
        }
        if ($base === '/' || $base === '\\' || $base === '.') {
            $base = '';
        }
        header('Location: ' . $base . '/install/');
        exit;
    }
    return;
}

$config = $useLocalDemo ? amp_local_demo_config() : require $configPath;
date_default_timezone_set($config['timezone'] ?? 'Asia/Dhaka');

require_once __DIR__ . '/db.php';
require_once __DIR__ . '/helpers.php';
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/whatsapp.php';
require_once __DIR__ . '/migrate.php';
require_once __DIR__ . '/billing.php';
require_once __DIR__ . '/cms_i18n.php';
require_once __DIR__ . '/features_catalog.php';

if ($useLocalDemo || !empty($config['local_demo'])) {
    $pdo = amp_local_demo_pdo();
    ensure_amp_migrations($pdo);
    ensure_cms_i18n_table($pdo);
} else {
    $pdo = db_connect($config);
    ensure_amp_migrations($pdo);
    ensure_cms_i18n_table($pdo);
}
