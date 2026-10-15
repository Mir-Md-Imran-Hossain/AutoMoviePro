<?php
declare(strict_types=1);

/**
 * Soft migrations for existing installs (CREATE IF NOT EXISTS / ADD COLUMN safe).
 */
function ensure_amp_migrations(PDO $pdo): void
{
    static $done = false;
    if ($done) {
        return;
    }
    $done = true;

    // Ensure hardware lock & OTP reset columns on customers
    try {
        $pdo->exec("ALTER TABLE customers ADD COLUMN hardware_id VARCHAR(100) NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE customers ADD COLUMN hardware_locked_at DATETIME NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE customers ADD COLUMN otp_code VARCHAR(16) NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE customers ADD COLUMN otp_expires_at DATETIME NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE customers ADD COLUMN tier VARCHAR(64) NULL DEFAULT 'video_studio'");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE customers ADD COLUMN plan VARCHAR(64) NULL DEFAULT 'video_studio'");
    } catch (\Throwable $e) {}

    // Ensure payment verification and status columns on orders table
    try {
        $pdo->exec("ALTER TABLE orders ADD COLUMN payment_method VARCHAR(32) NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE orders ADD COLUMN sender_last_digits VARCHAR(16) NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE orders ADD COLUMN txn_id VARCHAR(64) NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE orders ADD COLUMN updated_at DATETIME NULL");
    } catch (\Throwable $e) {}
    try {
        $pdo->exec("ALTER TABLE orders MODIFY COLUMN status VARCHAR(32) NOT NULL DEFAULT 'pending_payment'");
    } catch (\Throwable $e) {}

    // Ensure reviews table exists
    try {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS reviews (
              id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
              name VARCHAR(120) NOT NULL,
              rating TINYINT UNSIGNED NOT NULL DEFAULT 5,
              review_text TEXT NOT NULL,
              platform VARCHAR(60) NULL DEFAULT 'General',
              is_approved TINYINT(1) NOT NULL DEFAULT 1,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        );
    } catch (\Throwable $e) {}

    // Ensure agent_sms_inbox table exists
    try {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS agent_sms_inbox (
              id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
              provider VARCHAR(32) NOT NULL,
              sender_phone VARCHAR(32) NULL,
              sender_last_digits VARCHAR(8) NULL,
              txn_id VARCHAR(64) NOT NULL,
              amount DECIMAL(10,2) NOT NULL,
              raw_message TEXT NOT NULL,
              is_matched TINYINT(1) NOT NULL DEFAULT 0,
              matched_order_id INT UNSIGNED NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              INDEX (txn_id),
              INDEX (sender_last_digits)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        );
    } catch (\Throwable $e) {}

    // Ensure cash_withdrawals table exists
    try {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS cash_withdrawals (
              id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
              agent_name VARCHAR(120) NOT NULL DEFAULT 'Admin',
              amount DECIMAL(10,2) NOT NULL,
              notes TEXT NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        );
    } catch (\Throwable $e) {}

    // Ensure coupons table exists
    try {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS coupons (
              id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
              code VARCHAR(32) NOT NULL UNIQUE,
              discount_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
              discount_percent TINYINT UNSIGNED NOT NULL DEFAULT 0,
              min_order_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
              is_active TINYINT(1) NOT NULL DEFAULT 1,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        );
    } catch (\Throwable $e) {}




    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS customer_languages (
          id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          customer_id INT UNSIGNED NOT NULL,
          lang_code VARCHAR(8) NOT NULL,
          unlocked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          source VARCHAR(40) NOT NULL DEFAULT 'purchase',
          UNIQUE KEY uniq_customer_lang (customer_id, lang_code),
          FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    );

    try {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS language_orders (
              id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
              customer_id INT UNSIGNED NOT NULL,
              lang_code VARCHAR(16) NOT NULL,
              amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
              status VARCHAR(32) NOT NULL DEFAULT 'pending_payment',
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              approved_at DATETIME NULL,
              INDEX idx_customer (customer_id),
              INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        );
    } catch (\Throwable $e) {}

    $pdo->exec(
        "CREATE TABLE IF NOT EXISTS google_pro_subscriptions (
          id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          customer_id INT UNSIGNED NOT NULL,
          order_id INT UNSIGNED,
          plan_duration_months INT UNSIGNED NOT NULL DEFAULT 1,
          price DECIMAL(10,2) NOT NULL DEFAULT 120.00,
          status VARCHAR(30) NOT NULL DEFAULT 'pending_activation',
          target_email VARCHAR(255),
          google_pro_key VARCHAR(255),
          expires_at DATETIME,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          INDEX idx_customer (customer_id),
          INDEX idx_order (order_id),
          INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    );

    // Ensure download_tokens table exists for 72-hour one-time cryptographic tokens
    try {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS download_tokens (
              id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
              token VARCHAR(64) NOT NULL UNIQUE,
              order_id INT UNSIGNED NULL,
              customer_id INT UNSIGNED NULL,
              product VARCHAR(64) NOT NULL DEFAULT 'software',
              expires_at DATETIME NOT NULL,
              is_used TINYINT(1) NOT NULL DEFAULT 0,
              used_at DATETIME NULL,
              download_count INT NOT NULL DEFAULT 0,
              max_downloads INT NOT NULL DEFAULT 1,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_token (token),
              INDEX idx_order (order_id),
              INDEX idx_expires (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        );
    } catch (\Throwable $e) {}

    // Seed default coupons if missing
    try {
        $cCheck = $pdo->prepare('SELECT id FROM coupons WHERE code = ? LIMIT 1');
        $cIns = $pdo->prepare('INSERT INTO coupons (code, discount_amount, discount_percent, min_order_amount, is_active) VALUES (?, ?, ?, ?, 1)');
        
        $cCheck->execute(['LAUNCH500']);
        if (!$cCheck->fetch()) {
            $cIns->execute(['LAUNCH500', 500.0, 0, 0.0]);
        }
        $cCheck->execute(['SUPER1000']);
        if (!$cCheck->fetch()) {
            $cIns->execute(['SUPER1000', 1000.0, 0, 4999.0]);
        }
        $cCheck->execute(['PRO200']);
        if (!$cCheck->fetch()) {
            $cIns->execute(['PRO200', 200.0, 0, 0.0]);
        }
    } catch (\Throwable $e) {}

    // Seed default price if missing
    $stmt = $pdo->prepare('SELECT setting_value FROM site_settings WHERE setting_key = ? LIMIT 1');
    $stmt->execute(['language_addon_price']);
    if (!$stmt->fetch()) {
        $ins = $pdo->prepare(
            'INSERT INTO site_settings (setting_key, setting_value) VALUES (?, ?)'
        );
        $ins->execute(['language_addon_price', '499']);
    }

    // Ensure default admin user exists if table is empty
    try {
        $admCount = (int) $pdo->query("SELECT COUNT(*) FROM admins")->fetchColumn();
        if ($admCount === 0) {
            $defaultHash = password_hash('Admin@2026', PASSWORD_DEFAULT);
            $insAdm = $pdo->prepare("INSERT INTO admins (username, password_hash) VALUES (?, ?)");
            $insAdm->execute(['admin', $defaultHash]);
        }
    } catch (\Throwable $e) {}

    // Ensure customer_chat_logs table exists
    try {
        $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        if ($driver === 'sqlite') {
            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS customer_chat_logs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  visitor_id VARCHAR(64) NULL,
                  session_id VARCHAR(64) NULL,
                  customer_ip VARCHAR(64) NULL,
                  lang VARCHAR(8) NOT NULL DEFAULT 'bn',
                  agent_id VARCHAR(32) NOT NULL DEFAULT 'ayesha',
                  agent_name VARCHAR(64) NOT NULL DEFAULT 'আয়েশা (Ayesha)',
                  user_message TEXT NULL,
                  bot_reply TEXT NULL,
                  chosen_package VARCHAR(64) NULL,
                  whatsapp_handoff TINYINT(1) NOT NULL DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"
            );
            try { $pdo->exec("ALTER TABLE customer_chat_logs ADD COLUMN visitor_id VARCHAR(64) NULL"); } catch (\Throwable $e) {}
            try { $pdo->exec("ALTER TABLE customer_chat_logs ADD COLUMN chosen_package VARCHAR(64) NULL"); } catch (\Throwable $e) {}

            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS customer_visitor_profiles (
                  visitor_id VARCHAR(64) PRIMARY KEY,
                  customer_name VARCHAR(120) NULL,
                  customer_phone VARCHAR(32) NULL,
                  first_seen_at DATETIME NOT NULL,
                  last_seen_at DATETIME NOT NULL,
                  visit_count INT NOT NULL DEFAULT 1,
                  assigned_agent_id VARCHAR(32) NOT NULL DEFAULT 'ayesha',
                  assigned_agent_name VARCHAR(64) NOT NULL DEFAULT 'আয়েশা (Ayesha)',
                  last_interested_package VARCHAR(64) NULL,
                  last_objection VARCHAR(120) NULL,
                  conversation_summary TEXT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"
            );
        } else {
            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS customer_chat_logs (
                  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                  visitor_id VARCHAR(64) NULL,
                  session_id VARCHAR(64) NULL,
                  customer_ip VARCHAR(64) NULL,
                  lang VARCHAR(8) NOT NULL DEFAULT 'bn',
                  agent_id VARCHAR(32) NOT NULL DEFAULT 'ayesha',
                  agent_name VARCHAR(64) NOT NULL DEFAULT 'আয়েশা (Ayesha)',
                  user_message TEXT NULL,
                  bot_reply TEXT NULL,
                  chosen_package VARCHAR(64) NULL,
                  whatsapp_handoff TINYINT(1) NOT NULL DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX (visitor_id),
                  INDEX (session_id),
                  INDEX (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            );
            try { $pdo->exec("ALTER TABLE customer_chat_logs ADD COLUMN visitor_id VARCHAR(64) NULL"); } catch (\Throwable $e) {}
            try { $pdo->exec("ALTER TABLE customer_chat_logs ADD COLUMN chosen_package VARCHAR(64) NULL"); } catch (\Throwable $e) {}

            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS customer_visitor_profiles (
                  visitor_id VARCHAR(64) PRIMARY KEY,
                  customer_name VARCHAR(120) NULL,
                  customer_phone VARCHAR(32) NULL,
                  first_seen_at DATETIME NOT NULL,
                  last_seen_at DATETIME NOT NULL,
                  visit_count INT NOT NULL DEFAULT 1,
                  assigned_agent_id VARCHAR(32) NOT NULL DEFAULT 'ayesha',
                  assigned_agent_name VARCHAR(64) NOT NULL DEFAULT 'আয়েশা (Ayesha)',
                  last_interested_package VARCHAR(64) NULL,
                  last_objection VARCHAR(120) NULL,
                  conversation_summary TEXT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX (assigned_agent_id),
                  INDEX (last_seen_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            );
        }
    } catch (\Throwable $e) {}

    // Ensure whatsapp_leads table exists
    try {
        $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        if ($driver === 'sqlite') {
            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS whatsapp_leads (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name VARCHAR(120) NOT NULL DEFAULT 'ওয়েবসাইট ভিজিটর',
                  phone VARCHAR(32) NOT NULL,
                  clean_phone VARCHAR(32) NOT NULL,
                  source VARCHAR(40) NOT NULL DEFAULT 'chat',
                  interest_package VARCHAR(64) NULL DEFAULT 'video_studio',
                  status VARCHAR(32) NOT NULL DEFAULT 'new',
                  last_message TEXT NULL,
                  notes TEXT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"
            );
        } else {
            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS whatsapp_leads (
                  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                  name VARCHAR(120) NOT NULL DEFAULT 'ওয়েবসাইট ভিজিটর',
                  phone VARCHAR(32) NOT NULL,
                  clean_phone VARCHAR(32) NOT NULL,
                  source VARCHAR(40) NOT NULL DEFAULT 'chat',
                  interest_package VARCHAR(64) NULL DEFAULT 'video_studio',
                  status VARCHAR(32) NOT NULL DEFAULT 'new',
                  last_message TEXT NULL,
                  notes TEXT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX (clean_phone),
                  INDEX (status),
                  INDEX (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            );
        }
    } catch (\Throwable $e) {}

    // Ensure whatsapp_templates table exists
    try {
        $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        if ($driver === 'sqlite') {
            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS whatsapp_templates (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_key VARCHAR(64) NOT NULL UNIQUE,
                  title VARCHAR(120) NOT NULL,
                  category VARCHAR(40) NOT NULL DEFAULT 'general',
                  body TEXT NOT NULL,
                  is_active TINYINT(1) NOT NULL DEFAULT 1,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"
            );
        } else {
            $pdo->exec(
                "CREATE TABLE IF NOT EXISTS whatsapp_templates (
                  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                  template_key VARCHAR(64) NOT NULL UNIQUE,
                  title VARCHAR(120) NOT NULL,
                  category VARCHAR(40) NOT NULL DEFAULT 'general',
                  body TEXT NOT NULL,
                  is_active TINYINT(1) NOT NULL DEFAULT 1,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  INDEX (category)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            );
        }
    } catch (\Throwable $e) {}

    // Seed default WhatsApp templates if missing
    try {
        $tplCheck = $pdo->prepare('SELECT id FROM whatsapp_templates WHERE template_key = ? LIMIT 1');
        $tplIns = $pdo->prepare('INSERT INTO whatsapp_templates (template_key, title, category, body, is_active) VALUES (?, ?, ?, ?, 1)');
        
        $defaultTemplates = [
            'welcome_demo' => [
                '🎬 ডেমো ভিডিও ও স্বাগতম বার্তা',
                'welcome',
                "আসসালামু আলাইকুম {name}! AutoMovie Pro-তে আগ্রহ প্রকাশের জন্য আপনাকে ধন্যবাদ।\n\nআমাদের ৩টি প্যাকেজের ফুল লাইভ ভিডিও ডেমো দেখতে পারেন এখানে:\n👉 https://automoviepro.com/#features \n\nআপনার যদি কোনো প্রশ্ন থাকে বা ডেমো দেখার পর কোনো প্যাকেজ সম্পর্কে জানতে চান, আমাকে নিঃসঙ্কোচে জানাতে পারেন।"
            ],
            'vip_discount' => [
                '🎟️ স্পেশাল ভিআইপি ডিসকাউন্ট ভাউচার',
                'discount',
                "প্রিয় {name}, আপনার জন্য সুখবর!\n\nAutoMovie Pro টিম থেকে আপনার জন্য স্পেশাল ৳{discount} নগদ ছাড়ের একটি সিক্রেট কুপন কোড [{coupon}] অ্যাক্টিভেট করা হয়েছে!\n\n🎁 সাথে পাচ্ছেন ১টি অতিরিক্ত আন্তর্জাতিক ভাষা (মূল্য ৳৪৯৯) আজীবন সম্পূর্ণ ফ্রি!\n\n⚡ অফারটি আগামী ২৪ ঘণ্টা কার্যকর থাকবে। সরাসরি অর্ডার করতে নিচের লিংকে ক্লিক করুন:\n👉 https://automoviepro.com/order.php?coupon={coupon}"
            ],
            'order_followup' => [
                '⏰ পেন্ডিং অর্ডার পেমেন্ট রিমাইন্ডার',
                'order',
                "আসসালামু আলাইকুম {name}! AutoMovie Pro-তে আপনার অর্ডার #{order_id} পেন্ডিং রয়েছে।\n\nআপনার নির্বাচিত প্যাকেজ: {package} (৳{price})।\n\nবিকাশ/নগদে ক্যাশ আউট সম্পন্ন করে আপনার ট্রানজেকশন আইডি (TxnID) ওয়েবসাইটে সাবমিট করলে অথবা এই WhatsApp-এ দিলে এখনই আপনার লাইসেন্স ও ডাউনলোড ফাইল অ্যাক্টিভেট হয়ে যাবে।"
            ],
            'license_delivery' => [
                '🔑 সফটওয়্যার লাইসেন্স ডেলিভারি',
                'delivery',
                "মুবারকবাদ {name}! আপনার পেমেন্ট অনুমোদিত হয়েছে এবং আপনার অ্যাকাউন্ট সক্রিয় করা হয়েছে।\n\n• সফটওয়্যার: {package}\n• লগইন ID: {login_id}\n• পাসওয়ার্ড: {password}\n• ডাউনলোড লিংক: {download_url}\n• ভিডিও গাইড: {guide_url}\n\nসফটওয়্যারটি ইনস্টল করে উপরের আইডি ও পাসওয়ার্ড দিয়ে লগইন করুন।"
            ],
            'mega_announcement' => [
                '📢 মেগা আপডেট ও বিশেষ অফার বার্তা',
                'broadcast',
                "প্রিয় কনটেন্ট ক্রিয়েটর {name},\n\nAutoMovie Pro-তে যুক্ত হয়েছে নতুন পাওয়ারফুল ভিডিও জেনারেশন ও সোশ্যাল অটোমেশন ফিচার!\n\nআপনার ড্যাশবোর্ড থেকে আজই নতুন ভার্সন আপডেট করে নিন: https://automoviepro.com/download.php \n\nযেকোনো টেকনিক্যাল সাপোর্টের জন্য আমরা সার্বক্ষণিক আছি।"
            ]
        ];

        foreach ($defaultTemplates as $k => [$title, $cat, $body]) {
            $tplCheck->execute([$k]);
            if (!$tplCheck->fetch()) {
                $tplIns->execute([$k, $title, $cat, $body]);
            }
        }
    } catch (\Throwable $e) {}

    // Seed default AI agent discount & WhatsApp automation settings if missing
    $agentDefaults = [
        'agent_primary_persona' => 'ayesha',
        'agent_chat_active' => '1',
        'agent_discount_allowed' => '1',
        'agent_discount_mode' => 'consultative',
        'agent_discount_type' => 'flat',
        'agent_initial_discount_amount' => '500',
        'agent_max_discount_amount' => '1000',
        'agent_initial_discount_percent' => '15',
        'agent_max_discount_percent' => '25',
        'agent_pkg_video_studio_init' => '500',
        'agent_pkg_video_studio_max' => '1000',
        'agent_pkg_fb_business_init' => '300',
        'agent_pkg_fb_business_max' => '600',
        'agent_pkg_profile_page_init' => '200',
        'agent_pkg_profile_page_max' => '400',
        'agent_free_addon_lang' => '1',
        'agent_coupon_prefix' => 'VIP500',
        'agent_followup_reminder_hours' => '24',
        'agent_custom_instructions' => '',
        'agent_ask_whatsapp_for_demo' => '1',
        'agent_auto_queue_whatsapp_welcome' => '1',
        'wa_auto_welcome_chat' => '1',
        'wa_auto_order_placed' => '1',
        'wa_auto_order_approved' => '1',
        'admin_notify_whatsapp' => '8801968111593'
    ];

    try {
        $stCheck = $pdo->prepare('SELECT setting_value FROM site_settings WHERE setting_key = ? LIMIT 1');
        $stIns = $pdo->prepare('INSERT INTO site_settings (setting_key, setting_value) VALUES (?, ?)');
        foreach ($agentDefaults as $sKey => $sVal) {
            $stCheck->execute([$sKey]);
            if (!$stCheck->fetch()) {
                $stIns->execute([$sKey, $sVal]);
            }
        }
    } catch (\Throwable $e) {}

    ensure_wamanager_migrations($pdo);
}

function ensure_wamanager_migrations(PDO $pdo): void
{
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    $isSqlite = ($driver === 'sqlite');

    $schema = [
        'wa_accounts' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_accounts (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                phone VARCHAR(32) NULL,
                provider_type VARCHAR(32) NOT NULL DEFAULT 'cloud_api',
                status VARCHAR(32) NOT NULL DEFAULT 'disconnected',
                session_health INT DEFAULT 100,
                api_config TEXT NULL,
                messages_sent_count INT DEFAULT 0,
                last_active_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_accounts (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                phone VARCHAR(32) NULL,
                provider_type VARCHAR(32) NOT NULL DEFAULT 'cloud_api',
                status VARCHAR(32) NOT NULL DEFAULT 'disconnected',
                session_health INT DEFAULT 100,
                api_config TEXT NULL,
                messages_sent_count INT DEFAULT 0,
                last_active_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (provider_type),
                INDEX (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_contacts' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_contacts (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                phone VARCHAR(32) NOT NULL UNIQUE,
                country_code VARCHAR(16) NOT NULL DEFAULT '880',
                email VARCHAR(120) NULL,
                business_name VARCHAR(160) NULL,
                tags TEXT NULL,
                notes TEXT NULL,
                source VARCHAR(64) DEFAULT 'manual',
                consent_status VARCHAR(32) NOT NULL DEFAULT 'opted_in',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_contacts (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                phone VARCHAR(32) NOT NULL UNIQUE,
                country_code VARCHAR(16) NOT NULL DEFAULT '880',
                email VARCHAR(120) NULL,
                business_name VARCHAR(160) NULL,
                tags TEXT NULL,
                notes TEXT NULL,
                source VARCHAR(64) DEFAULT 'manual',
                consent_status VARCHAR(32) NOT NULL DEFAULT 'opted_in',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (phone),
                INDEX (consent_status),
                INDEX (source)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_contact_groups' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_contact_groups (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                description TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_contact_groups (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                description TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_group_members' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_group_members (
                group_id VARCHAR(64) NOT NULL,
                contact_id VARCHAR(64) NOT NULL,
                added_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, contact_id)
            )" :
            "CREATE TABLE IF NOT EXISTS wa_group_members (
                group_id VARCHAR(64) NOT NULL,
                contact_id VARCHAR(64) NOT NULL,
                added_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, contact_id),
                INDEX (group_id),
                INDEX (contact_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_campaigns' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_campaigns (
                id VARCHAR(64) PRIMARY KEY,
                title VARCHAR(160) NOT NULL,
                account_id VARCHAR(64) NULL,
                account_ids TEXT NULL,
                rotate_message_count INT DEFAULT 2,
                group_id VARCHAR(64) NULL,
                target_audience VARCHAR(64) DEFAULT 'group',
                template_id VARCHAR(64) NULL,
                custom_message TEXT NOT NULL,
                attachment_url TEXT NULL,
                attachment_type VARCHAR(32) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'draft',
                total_recipients INT DEFAULT 0,
                sent_count INT DEFAULT 0,
                delivered_count INT DEFAULT 0,
                failed_count INT DEFAULT 0,
                opt_out_skipped INT DEFAULT 0,
                jitter_min_seconds INT DEFAULT 3,
                jitter_max_seconds INT DEFAULT 8,
                scheduled_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_campaigns (
                id VARCHAR(64) PRIMARY KEY,
                title VARCHAR(160) NOT NULL,
                account_id VARCHAR(64) NULL,
                account_ids TEXT NULL,
                rotate_message_count INT DEFAULT 2,
                group_id VARCHAR(64) NULL,
                target_audience VARCHAR(64) DEFAULT 'group',
                template_id VARCHAR(64) NULL,
                custom_message TEXT NOT NULL,
                attachment_url TEXT NULL,
                attachment_type VARCHAR(32) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'draft',
                total_recipients INT DEFAULT 0,
                sent_count INT DEFAULT 0,
                delivered_count INT DEFAULT 0,
                failed_count INT DEFAULT 0,
                opt_out_skipped INT DEFAULT 0,
                jitter_min_seconds INT DEFAULT 3,
                jitter_max_seconds INT DEFAULT 8,
                scheduled_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (status),
                INDEX (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_campaign_jobs' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_campaign_jobs (
                id VARCHAR(64) PRIMARY KEY,
                campaign_id VARCHAR(64) NOT NULL,
                account_id VARCHAR(64) NULL,
                recipient_phone VARCHAR(32) NOT NULL,
                recipient_name VARCHAR(120) NOT NULL,
                rendered_content TEXT NOT NULL,
                attachment_url TEXT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                error_message TEXT NULL,
                sent_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_campaign_jobs (
                id VARCHAR(64) PRIMARY KEY,
                campaign_id VARCHAR(64) NOT NULL,
                account_id VARCHAR(64) NULL,
                recipient_phone VARCHAR(32) NOT NULL,
                recipient_name VARCHAR(120) NOT NULL,
                rendered_content TEXT NOT NULL,
                attachment_url TEXT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                error_message TEXT NULL,
                sent_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (campaign_id),
                INDEX (status),
                INDEX (recipient_phone)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_inbox_messages' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_inbox_messages (
                id VARCHAR(64) PRIMARY KEY,
                account_id VARCHAR(64) NULL,
                direction VARCHAR(16) NOT NULL DEFAULT 'inbound',
                sender_phone VARCHAR(32) NOT NULL,
                recipient_phone VARCHAR(32) NOT NULL,
                sender_name VARCHAR(120) NULL,
                message_body TEXT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'delivered',
                is_read TINYINT(1) DEFAULT 0,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_inbox_messages (
                id VARCHAR(64) PRIMARY KEY,
                account_id VARCHAR(64) NULL,
                direction VARCHAR(16) NOT NULL DEFAULT 'inbound',
                sender_phone VARCHAR(32) NOT NULL,
                recipient_phone VARCHAR(32) NOT NULL,
                sender_name VARCHAR(120) NULL,
                message_body TEXT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'delivered',
                is_read TINYINT(1) DEFAULT 0,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (sender_phone),
                INDEX (recipient_phone),
                INDEX (is_read),
                INDEX (timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_auto_reply_rules' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_auto_reply_rules (
                id VARCHAR(64) PRIMARY KEY,
                keyword VARCHAR(120) NOT NULL,
                match_type VARCHAR(32) NOT NULL DEFAULT 'contains',
                response_text TEXT NOT NULL,
                is_active TINYINT(1) DEFAULT 1,
                priority INT DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_auto_reply_rules (
                id VARCHAR(64) PRIMARY KEY,
                keyword VARCHAR(120) NOT NULL,
                match_type VARCHAR(32) NOT NULL DEFAULT 'contains',
                response_text TEXT NOT NULL,
                is_active TINYINT(1) DEFAULT 1,
                priority INT DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_business_leads' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_business_leads (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                phone VARCHAR(32) NOT NULL,
                address TEXT NULL,
                website VARCHAR(200) NULL,
                category VARCHAR(80) NOT NULL,
                city VARCHAR(80) NOT NULL DEFAULT 'Dhaka',
                source VARCHAR(64) DEFAULT 'lead_finder',
                status VARCHAR(32) DEFAULT 'new',
                collected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_business_leads (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(160) NOT NULL,
                phone VARCHAR(32) NOT NULL,
                address TEXT NULL,
                website VARCHAR(200) NULL,
                category VARCHAR(80) NOT NULL,
                city VARCHAR(80) NOT NULL DEFAULT 'Dhaka',
                source VARCHAR(64) DEFAULT 'lead_finder',
                status VARCHAR(32) DEFAULT 'new',
                collected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (category),
                INDEX (city),
                INDEX (phone)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_media_library' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_media_library (
                id VARCHAR(64) PRIMARY KEY,
                file_name VARCHAR(200) NOT NULL,
                file_url TEXT NOT NULL,
                file_type VARCHAR(32) NOT NULL DEFAULT 'image',
                file_size INT DEFAULT 0,
                uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_media_library (
                id VARCHAR(64) PRIMARY KEY,
                file_name VARCHAR(200) NOT NULL,
                file_url TEXT NOT NULL,
                file_type VARCHAR(32) NOT NULL DEFAULT 'image',
                file_size INT DEFAULT 0,
                uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wa_audit_logs' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wa_audit_logs (
                id VARCHAR(64) PRIMARY KEY,
                action VARCHAR(64) NOT NULL,
                details TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wa_audit_logs (
                id VARCHAR(64) PRIMARY KEY,
                action VARCHAR(64) NOT NULL,
                details TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (action),
                INDEX (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

        'wamanager_licenses' => $isSqlite ?
            "CREATE TABLE IF NOT EXISTS wamanager_licenses (
                id VARCHAR(64) PRIMARY KEY,
                license_key VARCHAR(64) NOT NULL UNIQUE,
                customer_name VARCHAR(120) NOT NULL,
                customer_phone VARCHAR(32) NOT NULL,
                customer_email VARCHAR(120) NULL,
                hardware_id VARCHAR(100) NULL,
                machine_name VARCHAR(120) NULL,
                plan_tier VARCHAR(64) NOT NULL DEFAULT 'wamanager_pro',
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                max_devices INT DEFAULT 1,
                activated_at DATETIME NULL,
                expires_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )" :
            "CREATE TABLE IF NOT EXISTS wamanager_licenses (
                id VARCHAR(64) PRIMARY KEY,
                license_key VARCHAR(64) NOT NULL UNIQUE,
                customer_name VARCHAR(120) NOT NULL,
                customer_phone VARCHAR(32) NOT NULL,
                customer_email VARCHAR(120) NULL,
                hardware_id VARCHAR(100) NULL,
                machine_name VARCHAR(120) NULL,
                plan_tier VARCHAR(64) NOT NULL DEFAULT 'wamanager_pro',
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                max_devices INT DEFAULT 1,
                activated_at DATETIME NULL,
                expires_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX (license_key),
                INDEX (hardware_id),
                INDEX (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ];

    foreach ($schema as $tbl => $sql) {
        try {
            $pdo->exec($sql);
        } catch (\Throwable $e) {}
    }

    // Seed default contact groups
    try {
        $stGroup = $pdo->prepare("SELECT id FROM wa_contact_groups WHERE id = ? LIMIT 1");
        $insGroup = $pdo->prepare("INSERT INTO wa_contact_groups (id, name, description) VALUES (?, ?, ?)");
        $defaultGroups = [
            ['vip_customers', '🌟 ভিআইপি কাস্টমার (VIP Buyers)', 'যারা ইতিমধ্যে AutoMovie Pro লাইসেন্স ক্রয় করেছেন'],
            ['pending_leads', '⏳ পেন্ডিং অর্ডার ও লিড', 'ওয়েবসাইট ও চ্যাটে আগ্রহী কিন্তু এখনও পেমেন্ট করেননি'],
            ['ecommerce_owners', '🛍️ ই-কমার্স ও শপ ওনার্স', 'অনলাইন শপ, ড্রপশিপিং ও প্রোডাক্ট বিজনেসের কাস্টমার'],
            ['video_creators', '🎬 ইউটিউব ও রিলস ক্রিয়েটর', 'কনটেন্ট ক্রিয়েটর ও ডিজিটাল মিডিয়া চ্যানেল মালিক'],
            ['agency_b2b', '🏢 ডিজিটাল এজেন্সি ও মার্কেটার', 'এজেন্সি ও ক্লায়েন্ট সার্ভিসের জন্য সফটওয়্যার সন্ধানকারী']
        ];
        foreach ($defaultGroups as [$gid, $gname, $gdesc]) {
            $stGroup->execute([$gid]);
            if (!$stGroup->fetch()) {
                $insGroup->execute([$gid, $gname, $gdesc]);
            }
        }
    } catch (\Throwable $e) {}

    // Seed default primary account
    try {
        $stAcc = $pdo->prepare("SELECT id FROM wa_accounts WHERE id = ? LIMIT 1");
        $stAcc->execute(['primary_cloud_api']);
        if (!$stAcc->fetch()) {
            $insAcc = $pdo->prepare("INSERT INTO wa_accounts (id, name, phone, provider_type, status, session_health, api_config) VALUES (?, ?, ?, ?, ?, ?, ?)");
            $initialCfg = json_encode([
                'access_token' => '',
                'phone_number_id' => '',
                'business_account_id' => '',
                'webhook_verify_token' => 'automoviepro_wa_webhook_secure_key_2026'
            ]);
            $insAcc->execute(['primary_cloud_api', 'Official Cloud API (Primary)', '+8801968111593', 'cloud_api', 'disconnected', 100, $initialCfg]);
        }
    } catch (\Throwable $e) {}

    // Seed default auto-reply rules
    try {
        $stRule = $pdo->prepare("SELECT id FROM wa_auto_reply_rules WHERE id = ? LIMIT 1");
        $insRule = $pdo->prepare("INSERT INTO wa_auto_reply_rules (id, keyword, match_type, response_text, is_active, priority) VALUES (?, ?, ?, ?, 1, ?)");
        $defaultRules = [
            ['rule_price', 'দাম|মূল্য|price|cost|koto', 'contains', "আসসালামু আলাইকুম! AutoMovie Pro-এর ৩টি স্পেশাল আজীবন লাইসেন্স প্যাকেজ রয়েছে:\n\n১. 4K Video Studio — ৳৩,৯৯৯ (ভিডিও তৈরি + অটো আপলোড + সোশ্যাল হাব)\n২. FB Business & Ad — ৳২,৯৯৯ (মার্কেটিং ব্যানার + অটো রিপ্লাই)\n৩. Profile AutoPilot — ৳১,৯৯৯ (ব্যক্তিগত প্রোফাইল অটো-পোস্ট)\n\nওয়েবসাইটে গিয়ে সরাসরি ডেমো দেখে অর্ডার করতে পারেন:\n👉 https://automoviepro.com/#pricing", 1],
            ['rule_demo', 'demo|ভিডিও ডেমো|কাজ কেমন|কিভাবে কাজ করে', 'contains', "আমাদের ৩টি প্যাকেজের পূর্ণাঙ্গ লাইভ ভিডিও ডেমো দেখতে ক্লিক করুন:\n👉 https://automoviepro.com/#features \n\nযেকোনো প্রশ্ন থাকলে আমাদের জানান!", 2],
            ['rule_order', 'order|কিনতে চাই|অর্ডার|payment|bkash', 'contains', "অর্ডার করার প্রক্রিয়া একদম সহজ:\n১. ভিজিট করুন: https://automoviepro.com/order.php \n২. প্যাকেজ নির্বাচন করে বিকাশ/নগদে ক্যাশ আউট করুন।\n৩. TrxID সাবমিট করলেই সাথে সাথে সফটওয়্যার ডাউনলোড লিংক ও লাইসেন্স পেয়ে যাবেন!", 3]
        ];
        foreach ($defaultRules as [$rid, $rk, $rmt, $rrp, $rprio]) {
            $stRule->execute([$rid]);
            if (!$stRule->fetch()) {
                $insRule->execute([$rid, $rk, $rmt, $rrp, $rprio]);
            }
        }
    } catch (\Throwable $e) {}
}

function amp_lang_catalog(): array
{
    return [
        'en' => 'English',
        'bn' => 'Bangla',
        'hi' => 'Hindi',
        'ur' => 'Urdu',
        'ta' => 'Tamil',
        'ml' => 'Malayalam',
    ];
}

function amp_customer_unlocked_langs(PDO $pdo, int $customerId): array
{
    $stmt = $pdo->prepare(
        'SELECT lang_code FROM customer_languages WHERE customer_id = ? ORDER BY id ASC'
    );
    $stmt->execute([$customerId]);
    $codes = [];
    foreach ($stmt->fetchAll() as $row) {
        $codes[] = (string) $row['lang_code'];
    }
    if (!in_array('en', $codes, true)) {
        array_unshift($codes, 'en');
    }
    return array_values(array_unique($codes));
}

function amp_unlock_customer_lang(PDO $pdo, int $customerId, string $langCode, string $source = 'purchase'): void
{
    $langCode = strtolower(trim($langCode));
    $catalog = amp_lang_catalog();
    if (!isset($catalog[$langCode]) || $langCode === 'en') {
        return;
    }
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    if ($driver === 'sqlite') {
        $stmt = $pdo->prepare(
            'INSERT OR IGNORE INTO customer_languages (customer_id, lang_code, unlocked_at, source)
             VALUES (?, ?, datetime("now"), ?)'
        );
    } else {
        $stmt = $pdo->prepare(
            'INSERT IGNORE INTO customer_languages (customer_id, lang_code, unlocked_at, source)
             VALUES (?, ?, NOW(), ?)'
        );
    }
    $stmt->execute([$customerId, $langCode, $source]);
}
