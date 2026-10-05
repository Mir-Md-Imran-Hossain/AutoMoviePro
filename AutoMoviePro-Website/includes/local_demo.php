<?php
declare(strict_types=1);

/**
 * Local demo DB (SQLite) — no WAMP MySQL required.
 * Enabled when config.local.php exists OR .local-demo marker is present.
 */
function amp_local_demo_enabled(): bool
{
    $root = dirname(__DIR__);
    return is_file($root . '/config.local.php') || is_file($root . '/.local-demo');
}

function amp_local_demo_config(): array
{
    $root = dirname(__DIR__);
    if (is_file($root . '/config.local.php')) {
        /** @var array $cfg */
        $cfg = require $root . '/config.local.php';
        return $cfg;
    }
    return [
        'db_driver' => 'sqlite',
        'site_url' => 'http://127.0.0.1:8080',
        'site_name' => 'AutoMovie Pro',
        'download_url' => 'http://127.0.0.1:8080/downloads/AutoMoviePro-Setup.exe',
        'install_guide_url' => 'http://127.0.0.1:8080/guide.html',
        'whatsapp_token' => '',
        'whatsapp_phone_id' => '',
        'whatsapp_admin_number' => '8801684355055',
        'api_token_days' => 30,
        'timezone' => 'Asia/Dhaka',
        'local_demo' => true,
    ];
}

function amp_local_demo_pdo(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }
    $root = dirname(__DIR__);
    $dir = $root . '/storage';
    if (!is_dir($dir)) {
        mkdir($dir, 0755, true);
    }
    $path = $dir . '/local_demo.sqlite';
    $pdo = new PDO('sqlite:' . $path, null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec('PRAGMA foreign_keys = ON');
    amp_local_demo_schema($pdo);
    amp_local_demo_seed($pdo);
    return $pdo;
}

function amp_local_demo_schema(PDO $pdo): void
{
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS site_settings (
          setting_key TEXT PRIMARY KEY,
          setting_value TEXT NOT NULL
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS site_settings_i18n (
          setting_key TEXT NOT NULL,
          lang_code TEXT NOT NULL,
          setting_value TEXT NOT NULL,
          updated_at TEXT,
          PRIMARY KEY (setting_key, lang_code)
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS customers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          whatsapp TEXT NOT NULL,
          email TEXT,
          login_id TEXT UNIQUE,
          password_hash TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          notes TEXT,
          last_heartbeat_at TEXT,
          created_at TEXT,
          activated_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER,
          name TEXT NOT NULL,
          whatsapp TEXT NOT NULL,
          email TEXT,
          plan_name TEXT NOT NULL DEFAULT 'Standard',
          amount REAL NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'pending_payment',
          payment_method TEXT,
          sender_last_digits TEXT,
          txn_id TEXT,
          updated_at TEXT,
          languages_json TEXT,
          base_langs TEXT,
          addon_langs TEXT,
          created_at TEXT,
          approved_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          rating INTEGER NOT NULL DEFAULT 5,
          review_text TEXT NOT NULL,
          platform TEXT DEFAULT 'General',
          is_approved INTEGER NOT NULL DEFAULT 1,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS agent_sms_inbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          provider TEXT NOT NULL,
          sender_phone TEXT,
          sender_last_digits TEXT,
          txn_id TEXT NOT NULL,
          amount REAL NOT NULL,
          raw_message TEXT NOT NULL,
          is_matched INTEGER NOT NULL DEFAULT 0,
          matched_order_id INTEGER,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS cash_withdrawals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          agent_name TEXT NOT NULL DEFAULT 'Admin',
          amount REAL NOT NULL,
          notes TEXT,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS coupons (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT NOT NULL UNIQUE,
          discount_amount REAL NOT NULL DEFAULT 0,
          discount_percent INTEGER NOT NULL DEFAULT 0,
          min_order_amount REAL NOT NULL DEFAULT 0,
          is_active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS licenses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER NOT NULL,
          token TEXT NOT NULL UNIQUE,
          expires_at TEXT,
          revoked INTEGER NOT NULL DEFAULT 0,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS customer_languages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER NOT NULL,
          lang_code TEXT NOT NULL,
          unlocked_at TEXT,
          source TEXT NOT NULL DEFAULT 'purchase',
          UNIQUE (customer_id, lang_code)
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS google_pro_subscriptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER NOT NULL,
          order_id INTEGER,
          plan_duration_months INTEGER NOT NULL DEFAULT 1,
          price REAL NOT NULL DEFAULT 120.0,
          status TEXT NOT NULL DEFAULT 'pending_activation',
          target_email TEXT,
          google_pro_key TEXT,
          expires_at TEXT,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS language_orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER NOT NULL,
          lang_code TEXT NOT NULL,
          amount REAL NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'pending_payment',
          created_at TEXT,
          approved_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS customer_jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER NOT NULL,
          channel_name TEXT,
          video_type TEXT NOT NULL DEFAULT 'short',
          title TEXT NOT NULL,
          description TEXT,
          platform TEXT,
          upload_status TEXT NOT NULL DEFAULT 'generated',
          uploaded_at TEXT,
          remote_url TEXT,
          local_path TEXT,
          meta_json TEXT,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS api_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER,
          action TEXT NOT NULL,
          detail TEXT,
          ip_address TEXT,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS admins (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL,
          created_at TEXT
        )"
    );
    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS whatsapp_outbox (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_id INTEGER,
          to_number TEXT NOT NULL,
          message TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued',
          response TEXT,
          created_at TEXT
        )"
    );
}

function amp_local_demo_seed(PDO $pdo): void
{
    $defaults = [
        'hero_brand' => 'AutoMovie Pro',
        'hero_tagline' => '',
        'hero_cta' => '',
        'price_amount' => '2998',
        'price_label' => '',
        'language_addon_price' => '499',
        'whatsapp_number' => '8801684355055',
        'payment_instructions' => "লোকাল প্রিভিউ মোড। পেমেন্ট স্ক্রিনশট WhatsApp বাটনে পাঠান।\nLive: https://automoviepro.com",
        'how_it_works' => '',
        'features_text' => '',
        'faq_text' => '',
        'meta_title' => 'AutoMovie Pro — Local Preview | automoviepro.com',
        'meta_description' => 'Local preview of AutoMovie Pro marketing site (automoviepro.com).',
    ];
    $ins = $pdo->prepare(
        'INSERT OR IGNORE INTO site_settings (setting_key, setting_value) VALUES (?, ?)'
    );
    foreach ($defaults as $k => $v) {
        $ins->execute([$k, $v]);
    }

    $admin = $pdo->query("SELECT id FROM admins WHERE username = 'admin' LIMIT 1")->fetch();
    if (!$admin) {
        $hash = password_hash('admin123', PASSWORD_DEFAULT);
        $pdo->prepare('INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, datetime("now"))')
            ->execute(['admin', $hash]);
    }

    $cIns = $pdo->prepare('INSERT OR IGNORE INTO coupons (code, discount_amount, discount_percent, min_order_amount, is_active, created_at) VALUES (?, ?, ?, ?, 1, datetime("now"))');
    $cIns->execute(['LAUNCH500', 500.0, 0, 0.0]);
    $cIns->execute(['SUPER1000', 1000.0, 0, 4999.0]);
    $cIns->execute(['PRO200', 200.0, 0, 0.0]);

    // Seed initial demo customers and approved orders if empty
    $custCount = (int) $pdo->query("SELECT COUNT(*) FROM customers")->fetchColumn();
    if ($custCount === 0) {
        $now = date('Y-m-d H:i:s');
        $passHash = password_hash('CustomerPass123', PASSWORD_DEFAULT);
        
        // 1. Zahid Hasan (Base Package 2999)
        $pdo->prepare("INSERT INTO customers (name, email, whatsapp, login_id, password_hash, status, created_at, activated_at) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)")
            ->execute(['জাহিদ হাসান (Zahid Pharmacy)', 'zahid@pharmacy.com', '01711223344', 'zahid01', $passHash, $now, $now]);
        $c1Id = (int) $pdo->lastInsertId();
        $pdo->prepare("INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, payment_method, txn_id, status, created_at, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?)")
            ->execute([$c1Id, 'জাহিদ হাসান (Zahid Pharmacy)', '01711223344', 'zahid@pharmacy.com', 'Base Package', 2999.0, 'bkash', 'BL82KA9191', $now, $now]);
        $pdo->prepare("INSERT INTO licenses (customer_id, token, expires_at, revoked, created_at) VALUES (?, ?, datetime('now', '+30 days'), 0, ?)")
            ->execute([$c1Id, 'amp_tok_' . bin2hex(random_bytes(16)), $now]);

        // 2. Simi Akter (Full Package 4999)
        $pdo->prepare("INSERT INTO customers (name, email, whatsapp, login_id, password_hash, status, created_at, activated_at) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)")
            ->execute(['সিমি আক্তার (Simi Drug House)', 'simi@drughouse.com', '01699887766', 'simi02', $passHash, $now, $now]);
        $c2Id = (int) $pdo->lastInsertId();
        $pdo->prepare("INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, payment_method, txn_id, status, created_at, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?)")
            ->execute([$c2Id, 'সিমি আক্তার (Simi Drug House)', '01699887766', 'simi@drughouse.com', 'Full Package', 4999.0, 'nagad', '72JH891A', $now, $now]);
        $pdo->prepare("INSERT INTO licenses (customer_id, token, expires_at, revoked, created_at) VALUES (?, ?, datetime('now', '+30 days'), 0, ?)")
            ->execute([$c2Id, 'amp_tok_' . bin2hex(random_bytes(16)), $now]);

        // 3. Farhan Tanvir (Base Package 2999)
        $pdo->prepare("INSERT INTO customers (name, email, whatsapp, login_id, password_hash, status, created_at, activated_at) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)")
            ->execute(['ফারহান তানভীর', 'farhan@tanvir.media', '01811556677', 'farhan03', $passHash, $now, $now]);
        $c3Id = (int) $pdo->lastInsertId();
        $pdo->prepare("INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, payment_method, txn_id, status, created_at, approved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?)")
            ->execute([$c3Id, 'ফারহান তানভীর', '01811556677', 'farhan@tanvir.media', 'Base Package', 2999.0, 'bkash', 'BL99XZ7711', $now, $now]);
        $pdo->prepare("INSERT INTO licenses (customer_id, token, expires_at, revoked, created_at) VALUES (?, ?, datetime('now', '+30 days'), 0, ?)")
            ->execute([$c3Id, 'amp_tok_' . bin2hex(random_bytes(16)), $now]);
    }
}

/** SQLite-compatible set_setting override used in local demo. */
function amp_local_demo_patch_helpers(): void
{
    // set_setting uses MySQL ON DUPLICATE KEY — redefine via wrapper in bootstrap instead.
}
