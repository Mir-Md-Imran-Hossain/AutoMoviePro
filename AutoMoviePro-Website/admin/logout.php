<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
$_SESSION = [];
if (ini_get('session.use_cookies')) {
    $params = session_get_cookie_params();
    setcookie(session_name(), '', time() - 42000,
        $params['path'], $params['domain'],
        $params['secure'], $params['httponly']
    );
}
if (session_status() === PHP_SESSION_ACTIVE) {
    session_destroy();
}
redirect('/admin/login.php');
