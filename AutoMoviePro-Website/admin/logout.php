<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
$_SESSION = [];
session_destroy();
redirect('/admin/login.php');
