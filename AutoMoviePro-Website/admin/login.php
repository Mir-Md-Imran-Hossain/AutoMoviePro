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
    $error = 'ইউজারনেম অথবা পাসওয়ার্ড সঠিক নয়। পুনরায় চেষ্টা করুন।';
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
  <title>অ্যাডমিন লগইন — AutoMovie Pro Master Suite</title>
  <link rel="icon" type="image/png" href="/assets/img/favicon.png">
  <style>
    :root {
      --bg: #030712;
      --card-bg: rgba(11, 19, 36, 0.85);
      --border: rgba(56, 189, 248, 0.2);
      --cyan: #38bdf8;
      --blue: #2563eb;
      --text: #f8fafc;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: radial-gradient(circle at 50% 10%, rgba(56, 189, 248, 0.12), transparent 45%),
                  radial-gradient(circle at 10% 90%, rgba(99, 102, 241, 0.08), transparent 40%),
                  var(--bg);
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      color: var(--text);
      position: relative;
      overflow: hidden;
    }

    /* Ambient cyber grid lines */
    body::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background-image: linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
                        linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
      background-size: 40px 40px;
      pointer-events: none;
    }

    .login-container {
      width: 100%;
      max-width: 440px;
      padding: 1.5rem;
      position: relative;
      z-index: 10;
    }

    .login-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 2.75rem 2.25rem;
      backdrop-filter: blur(25px);
      box-shadow: 0 25px 60px rgba(0, 0, 0, 0.7), 0 0 40px rgba(56, 189, 248, 0.15);
      position: relative;
    }

    .brand-header {
      text-align: center;
      margin-bottom: 2rem;
    }

    .brand-logo-frame {
      width: 72px;
      height: 72px;
      margin: 0 auto 1.25rem;
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(37, 99, 235, 0.2));
      border: 1px solid rgba(56, 189, 248, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 25px rgba(56, 189, 248, 0.35);
    }

    .brand-logo-frame img {
      width: 48px;
      height: 48px;
      object-fit: contain;
    }

    .brand-title {
      font-size: 1.5rem;
      font-weight: 900;
      letter-spacing: 0.5px;
      margin: 0 0 0.35rem;
    }

    .brand-title span {
      color: var(--cyan);
    }

    .security-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.75rem;
      font-weight: 700;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      padding: 4px 12px;
      border-radius: 999px;
      margin-top: 4px;
    }

    .err-alert {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #fca5a5;
      padding: 0.85rem 1rem;
      border-radius: 10px;
      font-size: 0.88rem;
      font-weight: 600;
      margin-bottom: 1.5rem;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .form-group {
      margin-bottom: 1.35rem;
    }

    .form-group label {
      display: block;
      font-size: 0.88rem;
      font-weight: 700;
      color: #cbd5e1;
      margin-bottom: 0.5rem;
    }

    .input-wrapper {
      position: relative;
      display: flex;
      align-items: center;
    }

    .input-icon {
      position: absolute;
      left: 14px;
      font-size: 1.1rem;
      color: #64748b;
      pointer-events: none;
    }

    .form-input {
      width: 100%;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 12px;
      padding: 0.85rem 1rem 0.85rem 42px;
      color: #ffffff;
      font-size: 0.95rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s ease;
    }

    .form-input:focus {
      border-color: var(--cyan);
      box-shadow: 0 0 15px rgba(56, 189, 248, 0.35);
      background: rgba(15, 23, 42, 1);
    }

    .toggle-pass-btn {
      position: absolute;
      right: 12px;
      background: transparent;
      border: none;
      color: #94a3b8;
      cursor: pointer;
      font-size: 1.1rem;
      padding: 4px;
    }
    .toggle-pass-btn:hover { color: #ffffff; }

    .remember-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1.75rem;
      font-size: 0.85rem;
      color: var(--muted);
    }

    .remember-row label {
      display: flex;
      align-items: center;
      gap: 7px;
      cursor: pointer;
    }

    .btn-submit {
      width: 100%;
      background: linear-gradient(135deg, #0284c7, #2563eb);
      color: #ffffff;
      border: none;
      padding: 0.95rem 1.5rem;
      border-radius: 12px;
      font-weight: 800;
      font-size: 1rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      box-shadow: 0 8px 25px rgba(2, 132, 199, 0.4);
      transition: all 0.25s ease;
    }

    .btn-submit:hover {
      background: linear-gradient(135deg, #0369a1, #1d4ed8);
      transform: translateY(-2px);
      box-shadow: 0 12px 30px rgba(2, 132, 199, 0.55);
    }

    .login-footer {
      text-align: center;
      margin-top: 1.75rem;
      padding-top: 1.25rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      font-size: 0.82rem;
      color: #64748b;
    }

    .login-footer a {
      color: var(--cyan);
      text-decoration: none;
      font-weight: 600;
    }
    .login-footer a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="login-container">
    <div class="login-card">
      <div class="brand-header">
        <div class="brand-logo-frame">
          <img src="/assets/img/logo.png" alt="AutoMovie Pro Logo">
        </div>
        <h1 class="brand-title">AutoMovie Pro <span>ADMIN</span></h1>
        <div class="security-badge">
          <span>🔒</span> <span>সুরক্ষিত মাস্টার টার্মিনাল</span>
        </div>
      </div>

      <?php if ($error): ?>
        <div class="err-alert">
          <span>⚠️</span> <span><?= e($error) ?></span>
        </div>
      <?php endif; ?>

      <form method="post" autocomplete="on">
        <div class="form-group">
          <label for="usernameInput">অ্যাডমিন ইউজারনেম (Username)</label>
          <div class="input-wrapper">
            <span class="input-icon">👤</span>
            <input type="text" id="usernameInput" name="username" class="form-input" placeholder="admin" required autofocus autocomplete="username">
          </div>
        </div>

        <div class="form-group">
          <label for="passwordInput">পাসওয়ার্ড (Password)</label>
          <div class="input-wrapper">
            <span class="input-icon">🔑</span>
            <input type="password" id="passwordInput" name="password" class="form-input" placeholder="••••••••••••" required autocomplete="current-password">
            <button type="button" class="toggle-pass-btn" onclick="togglePasswordVisibility()" aria-label="Toggle password visibility">👁️</button>
          </div>
        </div>

        <div class="remember-row">
          <label>
            <input type="checkbox" name="remember" checked style="accent-color: var(--cyan);">
            <span>আমাকে মনে রাখুন</span>
          </label>
          <span style="color: #64748b;">Session v4.5</span>
        </div>

        <button type="submit" class="btn-submit">
          <span>🚀 অ্যাডমিন প্যানেলে প্রবেশ করুন</span>
        </button>
      </form>

      <div class="login-footer">
        পাসওয়ার্ড ভুলে গেলে বা কোনো সমস্যা হলে <br>
        <a href="https://wa.me/8801684355055" target="_blank" rel="noopener">📱 WhatsApp সাপোর্টে যোগাযোগ করুন</a>
      </div>
    </div>
  </div>

  <script>
    function togglePasswordVisibility() {
      const input = document.getElementById('passwordInput');
      if (input.type === 'password') {
        input.type = 'text';
      } else {
        input.type = 'password';
      }
    }
  </script>
</body>
</html>
