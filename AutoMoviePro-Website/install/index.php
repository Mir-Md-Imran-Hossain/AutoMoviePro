<?php
declare(strict_types=1);

session_start();
$error = '';
$success = '';
$installed = is_file(dirname(__DIR__) . '/config.php');

if ($_SERVER['REQUEST_METHOD'] === 'POST' && !$installed) {
    $dbHost = trim($_POST['db_host'] ?? 'localhost');
    $dbName = trim($_POST['db_name'] ?? '');
    $dbUser = trim($_POST['db_user'] ?? '');
    $dbPass = (string) ($_POST['db_pass'] ?? '');
    $siteUrl = rtrim(trim($_POST['site_url'] ?? ''), '/');
    $adminUser = trim($_POST['admin_user'] ?? 'admin');
    $adminPass = (string) ($_POST['admin_pass'] ?? '');
    $whatsapp = preg_replace('/\D+/', '', (string) ($_POST['whatsapp_admin'] ?? '')) ?? '';

    if ($dbName === '' || $dbUser === '' || $adminPass === '' || $siteUrl === '') {
        $error = 'সব প্রয়োজনীয় ঘর পূরণ করুন।';
    } else {
        try {
            $dsn = "mysql:host={$dbHost};dbname={$dbName};charset=utf8mb4";
            $pdo = new PDO($dsn, $dbUser, $dbPass, [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            ]);
            $schema = require dirname(__DIR__) . '/includes/schema.php';
            foreach (array_filter(array_map('trim', explode(';', $schema))) as $sql) {
                if ($sql !== '') {
                    $pdo->exec($sql);
                }
            }
            $hash = password_hash($adminPass, PASSWORD_DEFAULT);
            $stmt = $pdo->prepare('INSERT INTO admins (username, password_hash) VALUES (?, ?)');
            $stmt->execute([$adminUser, $hash]);

            $defaults = [
                'hero_brand' => 'AutoMovie Pro',
                'hero_tagline' => 'নিশ সিলেক্ট করুন — অটো ভিডিও তৈরি ও YouTube/Facebook আপলোড',
                'hero_cta' => 'এখনই কিনুন',
                'price_amount' => '4999',
                'price_label' => 'লাইফটাইম লাইসেন্স',
                'whatsapp_number' => $whatsapp,
                'payment_instructions' => "পেমেন্ট সম্পন্ন করে স্ক্রিনশট এই WhatsApp নম্বরে পাঠান। অ্যাপ্রুভালের পর ডাউনলোড লিংক ও লগইন তথ্য SMS/WhatsApp-এ পাবেন।",
                'how_it_works' => "১) নিশ সিলেক্ট করুন\n২) চ্যানেল ও API সেটআপ করুন\n৩) নির্ধারিত সময়ে অটো ভিডিও জেনারেট ও আপলোড",
                'features_text' => "শর্ট ভিডিও সর্বোচ্চ ২ মিনিট\nলং ভিডিও সর্বোচ্চ ৫ মিনিট\nYouTube ও Facebook অটো আপলোড\nSEO-ফ্রেন্ডলি টাইটেল ও ডেসক্রিপশন",
                'faq_text' => "প্রশ্ন: ইনস্টল কীভাবে?\nউত্তর: ডাউনলোড করে START বা Setup চালান, লগইন করুন, চ্যানেল সেটআপ করুন।\n\nপ্রশ্ন: PC অফ থাকলে?\nউত্তর: জেনারেশন ও আপলোড PC অন থাকলেই চলে।",
                'meta_title' => 'AutoMovie Pro — অটো ভিডিও জেনারেশন সফটওয়্যার',
                'meta_description' => 'নিশ ভিত্তিক অটোমেটিক শর্ট ও লং ভিডিও তৈরি করে YouTube ও Facebook-এ আপলোড করুন।',
            ];
            $ins = $pdo->prepare(
                'INSERT INTO site_settings (setting_key, setting_value) VALUES (?, ?)
                 ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)'
            );
            foreach ($defaults as $k => $v) {
                $ins->execute([$k, $v]);
            }

            $configPhp = "<?php\nreturn [\n"
                . "    'db_host' => " . var_export($dbHost, true) . ",\n"
                . "    'db_name' => " . var_export($dbName, true) . ",\n"
                . "    'db_user' => " . var_export($dbUser, true) . ",\n"
                . "    'db_pass' => " . var_export($dbPass, true) . ",\n"
                . "    'db_charset' => 'utf8mb4',\n"
                . "    'site_url' => " . var_export($siteUrl, true) . ",\n"
                . "    'site_name' => 'AutoMovie Pro',\n"
                . "    'download_url' => " . var_export($siteUrl . '/downloads/AutoMoviePro-Setup.exe', true) . ",\n"
                . "    'install_guide_url' => " . var_export($siteUrl . '/guide.html', true) . ",\n"
                . "    'whatsapp_token' => '',\n"
                . "    'whatsapp_phone_id' => '',\n"
                . "    'whatsapp_admin_number' => " . var_export($whatsapp, true) . ",\n"
                . "    'api_token_days' => 30,\n"
                . "    'timezone' => 'Asia/Dhaka',\n"
                . "];\n";
            if (file_put_contents(dirname(__DIR__) . '/config.php', $configPhp) === false) {
                throw new RuntimeException('config.php লেখা যায়নি — ফোল্ডার পারমিশন চেক করুন।');
            }
            $success = 'ইনস্টল সম্পন্ন! এখন /admin/login.php এ যান এবং নিরাপত্তার জন্য /install ফোল্ডার ডিলিট বা রিনেম করুন।';
            $installed = true;
        } catch (Throwable $ex) {
            $error = 'ইনস্টল ব্যর্থ: ' . $ex->getMessage();
        }
    }
}
?>
<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoMovie Pro — Install</title>
  <link rel="stylesheet" href="/assets/css/site.css">
</head>
<body class="install-body">
  <main class="install-card">
    <h1>AutoMovie Pro সেটআপ</h1>
    <?php if ($installed && $success): ?>
      <p class="ok"><?= htmlspecialchars($success) ?></p>
      <p><a class="btn" href="/admin/login.php">অ্যাডমিন লগইন</a></p>
    <?php elseif ($installed): ?>
      <p class="ok">ইতিমধ্যে ইনস্টল আছে। নিরাপত্তার জন্য এই ফোল্ডার সরিয়ে ফেলুন।</p>
      <p><a class="btn" href="/">হোমে যান</a></p>
    <?php else: ?>
      <?php if ($error): ?><p class="err"><?= htmlspecialchars($error) ?></p><?php endif; ?>
      <form method="post" class="stack">
        <label>DB Host <input name="db_host" value="localhost" required></label>
        <label>DB Name <input name="db_name" required></label>
        <label>DB User <input name="db_user" required></label>
        <label>DB Password <input name="db_pass" type="password"></label>
        <label>Site URL <input name="site_url" placeholder="https://yourdomain.com" required></label>
        <label>Admin Username <input name="admin_user" value="admin" required></label>
        <label>Admin Password <input name="admin_pass" type="password" required></label>
        <label>পেমেন্ট WhatsApp (দেশ কোডসহ) <input name="whatsapp_admin" placeholder="8801..."></label>
        <button type="submit" class="btn">ইনস্টল করুন</button>
      </form>
    <?php endif; ?>
  </main>
</body>
</html>
