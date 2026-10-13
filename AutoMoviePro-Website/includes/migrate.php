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
