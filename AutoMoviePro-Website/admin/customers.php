<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$message = '';
$error = '';
$createdCustomerModal = null;
$sentCredsModal = null;
$catalog = amp_lang_catalog();

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $id = (int) ($_POST['id'] ?? 0);
    $action = (string) ($_POST['action'] ?? '');

    // 1. Manually Create New Customer
    if ($action === 'create_manual_customer') {
        $name = trim((string) ($_POST['name'] ?? ''));
        $whatsapp = trim((string) ($_POST['whatsapp'] ?? ''));
        $email = trim((string) ($_POST['email'] ?? ''));
        $tier = trim((string) ($_POST['tier'] ?? 'video_studio'));
        $customPass = trim((string) ($_POST['password'] ?? ''));
        $customLangs = $_POST['languages'] ?? ['bn'];
        $txnId = trim((string) ($_POST['txn_id'] ?? ''));
        $amount = (float) ($_POST['amount'] ?? 0);

        if ($amount <= 0) {
            if ($tier === 'video_studio') $amount = 3999;
            elseif ($tier === 'fb_business') $amount = 2999;
            elseif ($tier === 'profile_page') $amount = 1999;
            elseif ($tier === 'wamanager_pro') $amount = 1999;
            elseif ($tier === 'google_pro') $amount = 999;
            else $amount = 3999;
        }

        if ($name === '' || strlen($whatsapp) < 10) {
            $error = 'কাস্টমারের নাম এবং সঠিক মোবাইল/WhatsApp নম্বর প্রদান করুন।';
        } else {
            $loginId = generate_login_id();
            $plainPass = ($customPass !== '') ? $customPass : random_password(10);
            $hash = password_hash($plainPass, PASSWORD_DEFAULT);
            $nowSql = amp_sql_now($pdo);

            // Insert into customers table
            $ins = $pdo->prepare(
                "INSERT INTO customers (name, whatsapp, email, login_id, password_hash, status, tier, plan, activated_at, created_at)
                 VALUES (?, ?, ?, ?, ?, 'active', ?, ?, {$nowSql}, {$nowSql})"
            );
            $ins->execute([$name, $whatsapp, ($email !== '' ? $email : null), $loginId, $hash, $tier, $tier]);
            $newCustId = (int) $pdo->lastInsertId();

            // Issue 100-year lifetime license
            $token = amp_issue_license($pdo, $newCustId, 36500);

            // Unlock languages
            if (is_array($customLangs)) {
                foreach ($customLangs as $lc) {
                    amp_unlock_customer_lang($pdo, $newCustId, (string)$lc, 'admin_manual');
                }
            }

            // Create approved manual order record for tracking
            $baseLangsStr = implode(',', is_array($customLangs) ? $customLangs : ['bn']);
            $ord = $pdo->prepare(
                "INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, status, payment_method, txn_id, base_langs, approved_at, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, 'approved', 'admin_manual', ?, ?, {$nowSql}, {$nowSql})"
            );
            $ord->execute([$newCustId, $name, $whatsapp, ($email !== '' ? $email : null), $tier, $amount, ($txnId !== '' ? $txnId : 'MANUAL_OFFLINE'), $baseLangsStr]);
            $newOrderId = (int) $pdo->lastInsertId();

            // Generate 72-hour one-time cryptographic download token
            $dlToken = amp_create_download_token($pdo, $newOrderId, $newCustId, 'software', 72);
            $siteUrl = rtrim((string) ($config['site_url'] ?? 'https://automoviepro.com'), '/');
            $dlUrl = $siteUrl . '/download.php?token=' . $dlToken;

            // Prepare WhatsApp credentials message
            $tierNameMap = [
                'video_studio' => 'Social Media Content Automation Engine (৳৩,৯৯৯)',
                'fb_business' => 'FB Business Manager & Ad Automation Engine (৳২,৯৯৯)',
                'profile_page' => 'FB Profile & Page Post Automation Engine (৳১,৯৯৯)',
                'wamanager_pro' => 'WAManager Pro Official WhatsApp Marketing Suite',
                'google_pro' => 'Google AI Pro Account with API',
            ];
            $tierLabel = $tierNameMap[$tier] ?? $tier;

            $waBody = "Assalamu Alaikum {$name},\n\n"
                    . "AutoMovie Pro-তে আপনাকে স্বাগতম! আপনার অ্যাকাউন্ট ও আজীবন লাইসেন্স সফলভাবে সক্রিয় করা হয়েছে! 🎉\n\n"
                    . "👤 লগইন ID: {$loginId}\n"
                    . "🔑 পাসওয়ার্ড: {$plainPass}\n"
                    . "🎫 লাইসেন্স টোকেন: {$token}\n"
                    . "📦 প্যাকেজ: {$tierLabel}\n\n"
                    . "🔒 সিকিউর ওয়ান-টাইম ডাউনলোড লিংক (মেয়াদ ৭২ ঘণ্টা):\n"
                    . "📥 {$dlUrl}\n\n"
                    . "সফটওয়্যারটি ডাউনলোড করে ইনস্টল করুন এবং উপরোক্ত Login ID ও Password দিয়ে লগইন করুন। যেকোনো প্রয়োজনে আমাদের সাথে সরাসরি WhatsApp-এ যোগাযোগ করতে পারেন।\n\n"
                    . "ধন্যবাদ,\nAutoMovie Pro টিম";

            // Queue background WhatsApp notification
            whatsapp_queue($pdo, $config, $whatsapp, $waBody, $newCustId);

            $waClean = preg_replace('/\D+/', '', $whatsapp);
            $directWaUrl = 'https://wa.me/' . (str_starts_with($waClean, '88') ? $waClean : ('88' . $waClean)) . '?text=' . rawurlencode($waBody);

            $createdCustomerModal = [
                'id' => $newCustId,
                'name' => $name,
                'whatsapp' => $whatsapp,
                'login_id' => $loginId,
                'password' => $plainPass,
                'token' => $token,
                'tier' => $tierLabel,
                'dlUrl' => $dlUrl,
                'waLink' => $directWaUrl,
                'waBody' => $waBody,
            ];
            $message = "কাস্টমার {$name} (#{$newCustId}) সফলভাবে যুক্ত করা হয়েছে এবং লগইন আইডি {$loginId} ইস্যু হয়েছে।";
        }
    }

    // 2. Send / Reset WhatsApp Credentials for Existing Customer
    if ($action === 'send_whatsapp_creds' && $id > 0) {
        $cStmt = $pdo->prepare('SELECT * FROM customers WHERE id = ?');
        $cStmt->execute([$id]);
        $cust = $cStmt->fetch();
        if ($cust) {
            $newPass = trim((string) ($_POST['new_password'] ?? ''));
            if ($newPass === '') {
                $newPass = random_password(10);
            }
            $hash = password_hash($newPass, PASSWORD_DEFAULT);
            $pdo->prepare('UPDATE customers SET password_hash = ? WHERE id = ?')->execute([$hash, $id]);

            // Get or issue license token
            $licStmt = $pdo->prepare('SELECT token FROM licenses WHERE customer_id = ? AND revoked = 0 ORDER BY id DESC LIMIT 1');
            $licStmt->execute([$id]);
            $lic = $licStmt->fetch();
            $token = $lic ? $lic['token'] : amp_issue_license($pdo, $id, 36500);

            // Fresh download token
            $dlToken = amp_create_download_token($pdo, null, $id, 'software', 72);
            $siteUrl = rtrim((string) ($config['site_url'] ?? 'https://automoviepro.com'), '/');
            $dlUrl = $siteUrl . '/download.php?token=' . $dlToken;

            $waBody = "Assalamu Alaikum {$cust['name']},\n\n"
                    . "আপনার AutoMovie Pro অ্যাকাউন্ট লগইন তথ্য ও ডাউনলোড লিংক:\n\n"
                    . "👤 লগইন ID: {$cust['login_id']}\n"
                    . "🔑 পাসওয়ার্ড: {$newPass}\n"
                    . "🎫 লাইসেন্স টোকেন: {$token}\n\n"
                    . "🔒 সিকিউর ডাউনলোড লিংক (মেয়াদ ৭২ ঘণ্টা):\n"
                    . "📥 {$dlUrl}\n\n"
                    . "সফটওয়্যার ওপেন করে উপরোক্ত ID ও Password দিয়ে লগইন করুন।\n\n"
                    . "AutoMovie Pro সাপোর্ট: 01968111593";

            whatsapp_queue($pdo, $config, (string)$cust['whatsapp'], $waBody, $id);

            $waClean = preg_replace('/\D+/', '', (string)$cust['whatsapp']);
            $directWaUrl = 'https://wa.me/' . (str_starts_with($waClean, '88') ? $waClean : ('88' . $waClean)) . '?text=' . rawurlencode($waBody);

            $sentCredsModal = [
                'id' => $id,
                'name' => $cust['name'],
                'whatsapp' => $cust['whatsapp'],
                'login_id' => $cust['login_id'],
                'password' => $newPass,
                'token' => $token,
                'dlUrl' => $dlUrl,
                'waLink' => $directWaUrl,
                'waBody' => $waBody,
            ];
            $message = "কাস্টমার #{$id} ({$cust['name']}) এর নতুন পাসওয়ার্ড সেট ও WhatsApp লগইন তথ্য তৈরি করা হয়েছে।";
        }
    }

    // 3. Status Actions
    if ($id > 0) {
        if ($action === 'activate') {
            $pdo->prepare("UPDATE customers SET status = 'active', activated_at = COALESCE(activated_at, NOW()) WHERE id = ?")
                ->execute([$id]);
            $message = "কাস্টমার #{$id} সফলভাবে সক্রিয় (Active) করা হয়েছে।";
        } elseif ($action === 'deactivate') {
            $pdo->prepare("UPDATE customers SET status = 'inactive' WHERE id = ?")->execute([$id]);
            $pdo->prepare('UPDATE licenses SET revoked = 1 WHERE customer_id = ?')->execute([$id]);
            $message = "কাস্টমার #{$id} সাময়িক নিষ্ক্রিয় (Inactive) করা হয়েছে।";
        } elseif ($action === 'remove') {
            $pdo->prepare("UPDATE customers SET status = 'removed' WHERE id = ?")->execute([$id]);
            $pdo->prepare('UPDATE licenses SET revoked = 1 WHERE customer_id = ?')->execute([$id]);
            $message = "কাস্টমার #{$id} সফলভাবে মুছে ফেলা হয়েছে।";
        }
    }
}

$search = trim((string) ($_GET['q'] ?? ''));
$filterStatus = trim((string) ($_GET['status'] ?? 'all'));

$where = ["status != 'removed'"];
$params = [];

if ($filterStatus !== 'all' && $filterStatus !== '') {
    $where[] = "status = ?";
    $params[] = $filterStatus;
}

if ($search !== '') {
    $where[] = "(name LIKE ? OR whatsapp LIKE ? OR login_id LIKE ?)";
    $params[] = "%{$search}%";
    $params[] = "%{$search}%";
    $params[] = "%{$search}%";
}

$whereSql = 'WHERE ' . implode(' AND ', $where);

$stmt = $pdo->prepare("SELECT * FROM customers {$whereSql} ORDER BY id DESC");
$stmt->execute($params);
$rows = $stmt->fetchAll();

// Stats
$totalCustomers = 0;
$activeCount = 0;
$pendingCount = 0;
try {
    $totalCustomers = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status != 'removed'")->fetchColumn();
    $activeCount = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'active'")->fetchColumn();
    $pendingCount = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'pending'")->fetchColumn();
} catch (\Throwable $e) {}

admin_header('কাস্টমার ও লাইসেন্স ম্যানেজমেন্ট', 'customers');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<?php if ($error): ?>
  <div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#fca5a5; font-size:0.95rem;">
    ✕ <?= e($error) ?>
  </div>
<?php endif; ?>

<!-- Top Metrics & Action Deck -->
<div class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin-bottom: 2rem;">
  <div class="stat-card">
    <div class="stat-label">মোট কাস্টমার</div>
    <div class="stat-value" style="color:#38bdf8;"><?= $totalCustomers ?> জন</div>
    <div class="stat-trend">রেজিস্টার্ড গ্রাহক সংখ্যা</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">সক্রিয় লাইসেন্স (Active)</div>
    <div class="stat-value" style="color:#10b981;"><?= $activeCount ?> জন</div>
    <div class="stat-trend" style="color:#a7f3d0;">সফটওয়্যার সক্রিয় ব্যবহারকারী</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">অপেক্ষমাণ / নতুন (Pending)</div>
    <div class="stat-value" style="color:#f59e0b;"><?= $pendingCount ?> জন</div>
    <div class="stat-trend" style="color:#fde68a;">অনুমোদনের অপেক্ষায়</div>
  </div>
  <div class="stat-card" style="display:flex; flex-direction:column; justify-content:center; background:linear-gradient(135deg, rgba(2,132,199,0.12), rgba(37,99,235,0.15)); border-color:rgba(56,189,248,0.3);">
    <button type="button" class="btn-admin btn-admin-primary" onclick="openManualCustomerModal()" style="padding:12px 18px; font-size:0.95rem; font-weight:700; width:100%; display:flex; align-items:center; justify-content:center; gap:8px;">
      <span>➕</span> <span>ম্যানুয়ালি কাস্টমার যুক্ত করুন</span>
    </button>
    <div style="font-size:0.75rem; color:#94a3b8; text-align:center; margin-top:6px;">অফলাইন/সরাসরি বিক্রির জন্য</div>
  </div>
</div>

<!-- Search & Filter Bar -->
<div class="admin-card" style="margin-bottom: 1.5rem; padding: 1.25rem;">
  <form method="get" style="display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;">
    <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:center;">
      <input type="text" name="q" value="<?= e($search) ?>" placeholder="নাম, WhatsApp বা Login ID দিয়ে খুঁজুন…" class="form-input" style="width:280px; padding:8px 14px; font-size:0.9rem;">
      
      <select name="status" class="form-input" style="width:160px; padding:8px 14px; font-size:0.9rem;">
        <option value="all" <?= $filterStatus === 'all' ? 'selected' : '' ?>>সকল স্ট্যাটাস</option>
        <option value="active" <?= $filterStatus === 'active' ? 'selected' : '' ?>>সক্রিয় (Active)</option>
        <option value="pending" <?= $filterStatus === 'pending' ? 'selected' : '' ?>>পেন্ডিং (Pending)</option>
        <option value="inactive" <?= $filterStatus === 'inactive' ? 'selected' : '' ?>>নিষ্ক্রিয় (Inactive)</option>
      </select>

      <button type="submit" class="btn-admin btn-admin-primary" style="padding:8px 16px;">
        🔍 খুঁজুন
      </button>
      <?php if ($search || $filterStatus !== 'all'): ?>
        <a href="/admin/customers.php" class="btn-admin btn-admin-ghost" style="padding:8px 14px;">
          রিসেট
        </a>
      <?php endif; ?>
    </div>

    <div>
      <button type="button" class="btn-admin" onclick="openManualCustomerModal()" style="background:#0284c7; color:#fff; font-weight:700; padding:8px 16px;">
        ➕ নতুন কাস্টমার
      </button>
    </div>
  </form>
</div>

<!-- Customers Table -->
<div class="admin-card">
  <div class="card-header">
    <div class="card-title">
      <span>👥</span>
      <span>গ্রাহক তালিকা (Customer Directory)</span>
    </div>
    <span style="font-size:0.85rem; color:#94a3b8;"><?= count($rows) ?> জন প্রদর্শিত</span>
  </div>

  <div style="overflow-x:auto;">
    <table class="admin-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>কাস্টমারের নাম ও WhatsApp</th>
          <th>Login ID</th>
          <th>প্যাকেজ / প্ল্যান</th>
          <th>স্ট্যাটাস</th>
          <th>ভাষা</th>
          <th>ব্যবহারকাল</th>
          <th>Heartbeat</th>
          <th style="text-align:right;">অ্যাকশন</th>
        </tr>
      </thead>
      <tbody>
        <?php if (empty($rows)): ?>
          <tr>
            <td colspan="9" style="text-align:center; padding:3rem; color:#64748b;">
              কোনো কাস্টমার পাওয়া যায়নি।
            </td>
          </tr>
        <?php else: ?>
          <?php foreach ($rows as $r): 
              $cid = (int) $r['id'];
              $waClean = preg_replace('/\D+/', '', (string) $r['whatsapp']);
              $waLink = 'https://wa.me/' . (str_starts_with($waClean, '88') ? $waClean : ('88' . $waClean));
              $unlockedLangs = amp_customer_unlocked_langs($pdo, $cid);
              ?>
            <tr>
              <td>
                <a href="/admin/customer_view.php?id=<?= $cid ?>" style="color:#38bdf8; font-weight:700; text-decoration:none;">
                  #<?= $cid ?>
                </a>
              </td>
              <td>
                <div style="font-weight:700; color:#f8fafc; font-size:0.95rem;">
                  <a href="/admin/customer_view.php?id=<?= $cid ?>" style="color:#f8fafc; text-decoration:none;">
                    <?= e($r['name']) ?>
                  </a>
                </div>
                <div style="font-size:0.82rem; margin-top:2px;">
                  <a href="<?= e($waLink) ?>" target="_blank" rel="noopener" style="color:#34d399; text-decoration:none; display:inline-flex; align-items:center; gap:4px;">
                    <span>📱</span> <span><?= e($r['whatsapp']) ?></span>
                  </a>
                </div>
              </td>
              <td>
                <code style="background:rgba(56,189,248,0.1); color:#38bdf8; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.85rem;">
                  <?= e($r['login_id'] ?? '—') ?>
                </code>
              </td>
              <td>
                <span class="admin-badge badge-info" style="font-size:0.75rem;">
                  <?= e($r['plan'] ?? $r['tier'] ?? 'video_studio') ?>
                </span>
              </td>
              <td>
                <?php if ($r['status'] === 'active'): ?>
                  <span class="admin-badge badge-success">সক্রিয় (Active)</span>
                <?php elseif ($r['status'] === 'pending'): ?>
                  <span class="admin-badge badge-warning">পেন্ডিং (Pending)</span>
                <?php else: ?>
                  <span class="admin-badge badge-danger"><?= e($r['status']) ?></span>
                <?php endif; ?>
              </td>
              <td>
                <div style="display:flex; flex-wrap:wrap; gap:4px;">
                  <?php foreach ($unlockedLangs as $ulc): ?>
                    <span style="background:#1e293b; color:#38bdf8; font-size:0.72rem; padding:2px 6px; border-radius:4px; border:1px solid #334155;">
                      <?= strtoupper(e($ulc)) ?>
                    </span>
                  <?php endforeach; ?>
                  <?php if (empty($unlockedLangs)): ?>
                    <span style="color:#64748b; font-size:0.75rem;">EN</span>
                  <?php endif; ?>
                </div>
              </td>
              <td style="color:#94a3b8; font-size:0.85rem;">
                <?= days_since($r['activated_at'] ?: $r['created_at']) ?> দিন
              </td>
              <td style="color:#94a3b8; font-size:0.8rem;">
                <?= e($r['last_heartbeat_at'] ?? '—') ?>
              </td>
              <td style="text-align:right; white-space:nowrap;">
                <!-- 1-Click Send WhatsApp Credentials Button -->
                <button type="button" class="btn-admin" style="background:#059669; color:#fff; padding:4px 8px; font-size:0.8rem; margin-right:4px;" onclick="openSendCredsModal(<?= $cid ?>, '<?= e(addslashes($r['name'])) ?>', '<?= e(addslashes($r['whatsapp'])) ?>', '<?= e(addslashes((string)($r['login_id'] ?? ''))) ?>')" title="হোয়াটসঅ্যাপে লগইন তথ্য পাঠান">
                  📲 WhatsApp তথ্য
                </button>

                <form method="post" style="display:inline-block; margin-right:4px;">
                  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
                  <input type="hidden" name="id" value="<?= $cid ?>">
                  <?php if ($r['status'] !== 'active'): ?>
                    <button class="btn-admin" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3); padding:4px 10px; font-size:0.8rem;" name="action" value="activate">
                      ✓ Active
                    </button>
                  <?php else: ?>
                    <button class="btn-admin" style="background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.3); padding:4px 10px; font-size:0.8rem;" name="action" value="deactivate">
                      Deactive
                    </button>
                  <?php endif; ?>
                  <button class="btn-admin" style="background:rgba(244,63,94,0.15); color:#f43f5e; border:1px solid rgba(244,63,94,0.3); padding:4px 8px; font-size:0.8rem;" name="action" value="remove" onclick="return confirm('এই কাস্টমারকে রিমুভ করবেন?')">
                    ✕
                  </button>
                </form>
                <a href="/admin/customer_view.php?id=<?= $cid ?>" class="btn-admin btn-admin-ghost" style="padding:4px 8px; font-size:0.8rem;" title="বিস্তারিত ও ভাষা ম্যানেজমেন্ট">
                  👁️
                </a>
              </td>
            </tr>
          <?php endforeach; ?>
        <?php endif; ?>
      </tbody>
    </table>
  </div>
</div>

<!-- MODAL: MANUAL CUSTOMER CREATION -->
<div id="manualCustomerModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.85); z-index:9999; align-items:center; justify-content:center; padding:1.25rem; backdrop-filter:blur(6px);">
  <div style="background:#0f172a; border:1px solid #38bdf8; border-radius:18px; max-width:620px; width:100%; max-height:90vh; overflow-y:auto; padding:2rem; color:#f8fafc; box-shadow:0 25px 50px rgba(0,0,0,0.7);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem; border-bottom:1px solid #1e293b; padding-bottom:1rem;">
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.6rem;">➕</span>
        <div>
          <strong style="color:#38bdf8; font-size:1.2rem;">ম্যানুয়ালি নতুন কাস্টমার তৈরি করুন</strong>
          <p style="margin:2px 0 0; font-size:0.82rem; color:#94a3b8;">সরাসরি পেমেন্ট প্রাপ্তির পর এক ক্লিকে লাইসেন্স ও WhatsApp মেসেজ ডেলিভারি</p>
        </div>
      </div>
      <button type="button" class="btn-admin btn-admin-ghost" onclick="closeManualCustomerModal()" style="font-size:1.1rem; padding:4px 10px;">✕</button>
    </div>

    <form method="post">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="create_manual_customer">

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem;">
        <div>
          <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">কাস্টমারের পূর্ণ নাম *</label>
          <input type="text" name="name" required placeholder="যেমন: মোঃ তানভীর হাসান" class="form-input" style="width:100%; padding:0.65rem;">
        </div>
        <div>
          <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">WhatsApp নম্বর *</label>
          <input type="text" name="whatsapp" required placeholder="যেমন: 01712345678" class="form-input" style="width:100%; padding:0.65rem;">
        </div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem;">
        <div>
          <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">ইমেইল অ্যাড্রেস (ঐচ্ছিক)</label>
          <input type="email" name="email" placeholder="customer@gmail.com" class="form-input" style="width:100%; padding:0.65rem;">
        </div>
        <div>
          <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">পেমেন্ট রেফারেন্স / TrxID</label>
          <input type="text" name="txn_id" placeholder="যেমন: BK991248 বা ক্যাশ" class="form-input" style="width:100%; padding:0.65rem;">
        </div>
      </div>

      <div style="margin-bottom:1rem;">
        <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">সফটওয়্যার প্যাকেজ / টিয়ার *</label>
        <select name="tier" id="manualTierSelect" class="form-input" style="width:100%; padding:0.7rem; background:#1e293b; color:#fff;" onchange="updateTierPricePreview(this.value)">
          <option value="video_studio">🎬 AutoMovie Pro - Social Media Content Automation Engine (৳৩,৯৯৯ - লাইফটাইম)</option>
          <option value="fb_business">💼 AutoMovie Pro - FB Business Manager & Ad Automation Engine (৳২,৯৯৯ - লাইফটাইম)</option>
          <option value="profile_page">📱 AutoMovie Pro - FB Profile & Page Post Automation Engine (৳১,৯৯৯ - লাইফটাইম)</option>
          <option value="wamanager_pro">🚀 WAManager Pro — Official WhatsApp Marketing Suite (৳১,৯৯৯)</option>
          <option value="google_pro">👑 Google AI Pro Account with API (৳৯৯৯)</option>
        </select>
      </div>

      <div style="margin-bottom:1rem;">
        <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:6px;">
          🌐 প্রাথমিক সক্রিয় ভাষা (ইংরেজি ডিফল্ট সক্রিয় থাকবে):
        </label>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:8px; background:#1e293b; padding:10px; border-radius:8px;">
          <?php foreach ($catalog as $code => $name): ?>
            <label style="display:flex; align-items:center; gap:6px; font-size:0.85rem; cursor:pointer;">
              <input type="checkbox" name="languages[]" value="<?= e($code) ?>" <?= in_array($code, ['bn', 'en']) ? 'checked' : '' ?>>
              <span><?= e($name) ?> (<?= strtoupper(e($code)) ?>)</span>
            </label>
          <?php endforeach; ?>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1.5rem;">
        <div>
          <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">কাস্টম পাসওয়ার্ড (খালি রাখলে স্বয়ংক্রিয় তৈরি হবে)</label>
          <input type="text" name="password" placeholder="খালি রাখুন অথবা নিজস্ব পাসওয়ার্ড দিন" class="form-input" style="width:100%; padding:0.65rem;">
        </div>
        <div>
          <label style="display:block; font-size:0.88rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">গৃহীত ফি (টাকা)</label>
          <input type="number" name="amount" id="manualAmountInput" value="3999" class="form-input" style="width:100%; padding:0.65rem;">
        </div>
      </div>

      <div style="background:rgba(2,132,199,0.1); border:1px solid rgba(56,189,248,0.3); border-radius:8px; padding:10px; font-size:0.82rem; color:#93c5fd; margin-bottom:1.25rem;">
        💡 <strong>অটোমেশন সুবিধাসমূহ:</strong> কাস্টমার তৈরি হওয়ার সাথে সাথে তার অ্যাকাউন্টে লাইফটাইম লাইসেন্স সক্রিয় হবে, ৭২ ঘণ্টার সিকিউর ওয়ান-টাইম ডাউনলোড লিংক তৈরি হবে এবং তার WhatsApp নম্বরে স্বয়ংক্রিয়ভাবে মেসেজ চলে যাবে।
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button type="button" class="btn-admin btn-admin-ghost" onclick="closeManualCustomerModal()">বাতিল</button>
        <button type="submit" class="btn-admin btn-admin-primary" style="padding:10px 22px; font-size:0.95rem; font-weight:700;">
          ✓ কাস্টমার তৈরি করুন ও WhatsApp পাঠান
        </button>
      </div>
    </form>
  </div>
</div>

<!-- MODAL: SEND / RESET WHATSAPP CREDENTIALS -->
<div id="sendCredsModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.85); z-index:9999; align-items:center; justify-content:center; padding:1.25rem; backdrop-filter:blur(6px);">
  <div style="background:#0f172a; border:1px solid #10b981; border-radius:18px; max-width:520px; width:100%; padding:2rem; color:#f8fafc; box-shadow:0 25px 50px rgba(0,0,0,0.7);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem; border-bottom:1px solid #1e293b; padding-bottom:0.75rem;">
      <strong style="color:#34d399; font-size:1.15rem; display:flex; align-items:center; gap:8px;">
        <span>📲</span> WhatsApp-এ লগইন তথ্য পাঠান
      </strong>
      <button type="button" class="btn-admin btn-admin-ghost" onclick="closeSendCredsModal()">✕</button>
    </div>

    <form method="post">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="send_whatsapp_creds">
      <input type="hidden" name="id" id="sendCredsCustId" value="0">

      <div style="background:#1e293b; padding:12px; border-radius:8px; margin-bottom:1rem; font-size:0.88rem; line-height:1.6;">
        গ্রাহকের নাম: <strong id="sendCredsCustName" style="color:#fff;">—</strong><br>
        WhatsApp: <strong id="sendCredsCustWa" style="color:#34d399;">—</strong><br>
        Login ID: <strong id="sendCredsCustLoginId" style="color:#38bdf8;">—</strong>
      </div>

      <div style="margin-bottom:1.25rem;">
        <label style="display:block; font-size:0.85rem; color:#cbd5e1; font-weight:600; margin-bottom:4px;">
          নতুন পাসওয়ার্ড দিন (খালি রাখলে স্বয়ংক্রিয় রেন্ডম পাসওয়ার্ড তৈরি হবে):
        </label>
        <input type="text" name="new_password" placeholder="যেমন: pass9821 বা খালি রাখুন" class="form-input" style="width:100%; padding:0.65rem;">
      </div>

      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button type="button" class="btn-admin btn-admin-ghost" onclick="closeSendCredsModal()">বাতিল</button>
        <button type="submit" class="btn-admin" style="background:#059669; color:#fff; font-weight:700; padding:10px 20px;">
          🚀 তথ্য তৈরি ও WhatsApp-এ পাঠান
        </button>
      </div>
    </form>
  </div>
</div>

<!-- SUCCESS POPUP: CREATED / SENT CREDENTIALS -->
<?php if ($createdCustomerModal || $sentCredsModal): 
    $modalData = $createdCustomerModal ?: $sentCredsModal;
    ?>
  <div id="successCredentialsModal" style="display:flex; position:fixed; inset:0; background:rgba(0,0,0,0.88); z-index:10000; align-items:center; justify-content:center; padding:1.25rem; backdrop-filter:blur(8px);">
    <div style="background:#0f172a; border:2px solid #10b981; border-radius:18px; max-width:580px; width:100%; padding:2rem; color:#f8fafc; box-shadow:0 25px 60px rgba(16,185,129,0.3);">
      <div style="text-align:center; margin-bottom:1.25rem;">
        <div style="font-size:2.8rem; margin-bottom:6px;">🎉</div>
        <h3 style="color:#34d399; font-size:1.35rem; margin:0 0 4px 0;">কাস্টমার লগইন তথ্য সফলভাবে তৈরি হয়েছে!</h3>
        <p style="color:#94a3b8; font-size:0.88rem; margin:0;">অ্যাকাউন্ট অ্যাক্টিভ হয়েছে এবং ব্যাকগ্রাউন্ড WhatsApp কিউতে পাঠানো হয়েছে।</p>
      </div>

      <div style="background:#090e17; border:1px solid #1e293b; border-radius:12px; padding:1.25rem; margin-bottom:1.25rem; font-family:monospace; font-size:0.9rem; line-height:1.8;">
        <div>👤 <strong>গ্রাহক:</strong> <?= e($modalData['name']) ?> (<?= e($modalData['whatsapp']) ?>)</div>
        <div>🔑 <strong>Login ID:</strong> <span style="color:#38bdf8; font-weight:700; font-size:1.05rem;"><?= e($modalData['login_id']) ?></span></div>
        <div>🔒 <strong>Password:</strong> <span style="color:#f59e0b; font-weight:700; font-size:1.05rem;"><?= e($modalData['password']) ?></span></div>
        <div style="font-size:0.8rem; color:#94a3b8; word-break:break-all;">🎫 <strong>License:</strong> <?= e($modalData['token']) ?></div>
        <div style="margin-top:6px; font-size:0.82rem; word-break:break-all;">
          📥 <strong>Download:</strong> <a href="<?= e($modalData['dlUrl']) ?>" target="_blank" style="color:#38bdf8;"><?= e($modalData['dlUrl']) ?></a>
        </div>
      </div>

      <div style="display:flex; flex-direction:column; gap:10px;">
        <a href="<?= e($modalData['waLink']) ?>" target="_blank" rel="noopener" class="btn-admin" style="background:#25d366; color:#0f172a; font-weight:800; font-size:1rem; padding:12px; text-align:center; text-decoration:none; border-radius:8px; display:flex; align-items:center; justify-content:center; gap:8px;">
          <span>💬</span> <span>১-ক্লিকে WhatsApp Web / App-এ পাঠান</span>
        </a>

        <div style="display:flex; gap:10px;">
          <button type="button" class="btn-admin btn-admin-ghost" style="flex:1;" onclick="copyCustomerCreds('<?= e(addslashes($modalData['login_id'])) ?>', '<?= e(addslashes($modalData['password'])) ?>', '<?= e(addslashes($modalData['dlUrl'])) ?>')">
            📋 লগইন তথ্য কপি করুন
          </button>
          <button type="button" class="btn-admin" style="background:#334155; color:#fff;" onclick="document.getElementById('successCredentialsModal').style.display='none'">
            বন্ধ করুন
          </button>
        </div>
      </div>
    </div>
  </div>
<?php endif; ?>

<script>
function openManualCustomerModal() {
  document.getElementById('manualCustomerModal').style.display = 'flex';
}
function closeManualCustomerModal() {
  document.getElementById('manualCustomerModal').style.display = 'none';
}
function openSendCredsModal(id, name, wa, loginId) {
  document.getElementById('sendCredsCustId').value = id;
  document.getElementById('sendCredsCustName').textContent = name;
  document.getElementById('sendCredsCustWa').textContent = wa;
  document.getElementById('sendCredsCustLoginId').textContent = loginId;
  document.getElementById('sendCredsModal').style.display = 'flex';
}
function closeSendCredsModal() {
  document.getElementById('sendCredsModal').style.display = 'none';
}
function updateTierPricePreview(tier) {
  const map = {
    'video_studio': 3999,
    'fb_business': 2999,
    'profile_page': 1999,
    'wamanager_pro': 1999,
    'google_pro': 999
  };
  const input = document.getElementById('manualAmountInput');
  if (input && map[tier]) {
    input.value = map[tier];
  }
}
function copyCustomerCreds(loginId, pass, dlUrl) {
  const text = `AutoMovie Pro লগইন তথ্য:\nLogin ID: ${loginId}\nPassword: ${pass}\nDownload Link: ${dlUrl}`;
  navigator.clipboard.writeText(text).then(() => {
    alert('লগইন তথ্য সফলভাবে ক্লিপবোর্ডে কপি হয়েছে!');
  });
}
</script>

<?php admin_footer(); ?>
