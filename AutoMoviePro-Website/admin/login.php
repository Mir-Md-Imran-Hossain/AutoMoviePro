<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $user = trim((string) ($_POST['username'] ?? ''));
    $pass = (string) ($_POST['password'] ?? '');
    if (attempt_admin_login($pdo, $user, $pass)) {
        redirect('/admin/index.php');
    }
    $error = 'লগইন ব্যর্থ';
}
if (admin_logged_in()) {
    redirect('/admin/index.php');
}
?>
<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Admin Login</title>
  <link rel="stylesheet" href="/assets/css/site.css">
</head>
<body class="install-body">
  <main class="install-card">
    <h1>অ্যাডমিন লগইন</h1>
    <?php if ($error): ?><p class="err"><?= e($error) ?></p><?php endif; ?>
    <form method="post" class="stack">
      <label>Username <input name="username" required></label>
      <label>Password <input name="password" type="password" required></label>
      <button class="btn" type="submit">লগইন</button>
    </form>
  </main>
</body>
</html>
