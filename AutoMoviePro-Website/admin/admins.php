<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';
$error = '';

$currentAdminUser = $_SESSION['admin_user'] ?? 'admin';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = (string) ($_POST['action'] ?? 'change_password');

    if ($action === 'change_password') {
        $oldPass = (string) ($_POST['old_password'] ?? '');
        $newPass = (string) ($_POST['new_password'] ?? '');
        $confirmPass = (string) ($_POST['confirm_password'] ?? '');

        if ($newPass === '' || strlen($newPass) < 6) {
            $error = 'নতুন পাসওয়ার্ড কমপক্ষে ৬ অক্ষরের হতে হবে।';
        } elseif ($newPass !== $confirmPass) {
            $error = 'নতুন পাসওয়ার্ড এবং কনফার্ম পাসওয়ার্ড মেলেনি!';
        } else {
            // Verify old password
            $stmt = $pdo->prepare("SELECT * FROM admins WHERE username = ? LIMIT 1");
            $stmt->execute([$currentAdminUser]);
            $adminRow = $stmt->fetch();

            if (!$adminRow || !password_verify($oldPass, (string) $adminRow['password_hash'])) {
                $error = 'বর্তমান পাসওয়ার্ডটি ভুল হয়েছে! সঠিক পাসওয়ার্ড দিন।';
            } else {
                $newHash = password_hash($newPass, PASSWORD_DEFAULT);
                $updateStmt = $pdo->prepare("UPDATE admins SET password_hash = ? WHERE id = ?");
                $updateStmt->execute([$newHash, (int) $adminRow['id']]);
                $message = 'আপনার অ্যাডমিন পাসওয়ার্ড সফলভাবে পরিবর্তন করা হয়েছে! পরবর্তী লগইনে নতুন পাসওয়ার্ড ব্যবহার করুন।';
            }
        }
    }
}

// Fetch all admins
$adminList = [];
try {
    $adminList = $pdo->query("SELECT id, username, created_at FROM admins ORDER BY id ASC")->fetchAll();
} catch (\Throwable $e) {}

admin_header('পাসওয়ার্ড ও অ্যাডমিন প্রোফাইল', 'admins');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<?php if ($error): ?>
  <div style="background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#fda4af; font-size:0.95rem;">
    ⚠️ <?= e($error) ?>
  </div>
<?php endif; ?>

<div style="display:grid; grid-template-columns: 1fr 340px; gap: 1.5rem; align-items: start;">
  
  <!-- Change Password Form -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>🛡️</span>
        <span>মাস্টার অ্যাডমিন পাসওয়ার্ড পরিবর্তন</span>
      </div>
    </div>

    <form method="post" class="admin-form" style="max-width:520px;">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="change_password">

      <div class="form-group">
        <label class="form-label">অ্যাডমিন ইউজারনেম</label>
        <input type="text" class="form-input" value="<?= e($currentAdminUser) ?>" readonly style="background:rgba(0,0,0,0.3); color:#94a3b8; cursor:not-allowed;">
      </div>

      <div class="form-group">
        <label class="form-label">বর্তমান পাসওয়ার্ড (Current Password)</label>
        <div style="position:relative;">
          <input type="password" name="old_password" id="old_password" class="form-input" required placeholder="বর্তমান পাসওয়ার্ড দিন" style="padding-right:40px;">
          <button type="button" onclick="togglePassVisibility('old_password', this)" style="position:absolute; right:10px; top:50%; transform:translateY(-50%); background:none; border:none; color:#94a3b8; cursor:pointer; font-size:1.1rem;">👁️</button>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">নতুন পাসওয়ার্ড (New Password)</label>
        <div style="position:relative;">
          <input type="password" name="new_password" id="new_password" class="form-input" required placeholder="কমপক্ষে ৬ অক্ষরের নতুন পাসওয়ার্ড দিন" minlength="6" style="padding-right:40px;">
          <button type="button" onclick="togglePassVisibility('new_password', this)" style="position:absolute; right:10px; top:50%; transform:translateY(-50%); background:none; border:none; color:#94a3b8; cursor:pointer; font-size:1.1rem;">👁️</button>
        </div>
        <small style="color:#64748b; font-size:0.75rem;">মজবুত পাসওয়ার্ডের জন্য অক্ষর, সংখ্যা ও স্পেশাল ক্যারেক্টার ব্যবহার করুন।</small>
      </div>

      <div class="form-group">
        <label class="form-label">নতুন পাসওয়ার্ড পুনরায় লিখুন (Confirm New Password)</label>
        <div style="position:relative;">
          <input type="password" name="confirm_password" id="confirm_password" class="form-input" required placeholder="নতুন পাসওয়ার্ডটি আবার লিখুন" minlength="6" style="padding-right:40px;">
          <button type="button" onclick="togglePassVisibility('confirm_password', this)" style="position:absolute; right:10px; top:50%; transform:translateY(-50%); background:none; border:none; color:#94a3b8; cursor:pointer; font-size:1.1rem;">👁️</button>
        </div>
      </div>

      <div style="margin-top:1.5rem;">
        <button type="submit" class="btn-admin btn-admin-primary" style="padding:10px 24px; font-size:0.95rem;">
          <span>🔒</span> <span>পাসওয়ার্ড আপডেট করুন</span>
        </button>
      </div>
    </form>
  </div>

  <!-- Admin Accounts List Card -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>👑</span>
        <span>অ্যাডমিন প্রোফাইল ইনফো</span>
      </div>
    </div>

    <div style="text-align:center; padding:1.5rem 0;">
      <div style="width:70px; height:70px; border-radius:50%; background:linear-gradient(135deg, #0284c7, #38bdf8); display:flex; align-items:center; justify-content:center; font-size:2rem; font-weight:800; color:#fff; margin:0 auto 12px; box-shadow:0 0 20px rgba(56,189,248,0.4);">
        A
      </div>
      <div style="font-size:1.1rem; font-weight:700; color:#f8fafc;"><?= e($currentAdminUser) ?></div>
      <div style="font-size:0.8rem; color:#38bdf8; margin-top:2px;">Master Super Administrator</div>
    </div>

    <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:1rem; margin-top:0.5rem;">
      <div style="font-size:0.85rem; font-weight:600; color:#94a3b8; margin-bottom:8px;">তালিকাভুক্ত অ্যাডমিন:</div>
      <?php foreach ($adminList as $adm): ?>
        <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 10px; background:rgba(255,255,255,0.02); border-radius:6px; margin-bottom:6px;">
          <div>
            <strong style="color:#f8fafc; font-size:0.9rem;"><?= e($adm['username']) ?></strong>
            <div style="font-size:0.75rem; color:#64748b;">তৈরি: <?= date('d M, Y', strtotime($adm['created_at'])) ?></div>
          </div>
          <span class="admin-badge badge-success" style="font-size:0.75rem;">Active</span>
        </div>
      <?php endforeach; ?>
    </div>

    <div style="margin-top:1.25rem; padding:10px; background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.2); border-radius:8px; font-size:0.78rem; color:#fde68a; line-height:1.5;">
      ⚠️ পাসওয়ার্ড ভুলে গেলে সরাসরি ডাটাবেজ অথবা হোস্ট ম্যানেজমেন্ট থেকে রিসেট করা সম্ভব।
    </div>
  </div>

</div>

<script>
function togglePassVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁️';
  }
}
</script>

<?php admin_footer(); ?>
