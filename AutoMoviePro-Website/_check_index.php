<?php
$_SERVER['REQUEST_URI'] = '/';
$_SERVER['SCRIPT_NAME'] = '/index.php';
$_SERVER['HTTP_HOST'] = '127.0.0.1:8080';
chdir(__DIR__);
ob_start();
include __DIR__ . '/index.php';
$o = ob_get_clean();
echo (str_contains($o, 'AutoMovie Pro') ? "INDEX_OK\n" : "INDEX_FAIL\n");
echo (str_contains($o, 'feature-grid') ? "FEATURES_OK\n" : "FEATURES_FAIL\n");
echo 'len=' . strlen($o) . "\n";
if (!str_contains($o, 'AutoMovie Pro')) {
    echo substr($o, 0, 500);
}
