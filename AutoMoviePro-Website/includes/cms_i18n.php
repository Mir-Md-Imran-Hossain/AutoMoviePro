<?php
declare(strict_types=1);

/** Multilingual CMS helpers + free MyMemory auto-translate for other langs. */

function amp_cms_langs(): array
{
    return ['en', 'bn', 'hi', 'ur', 'ta', 'ml'];
}

function ensure_cms_i18n_table(PDO $pdo): void
{
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    if ($driver === 'sqlite') {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS site_settings_i18n (
              setting_key TEXT NOT NULL,
              lang_code TEXT NOT NULL,
              setting_value TEXT NOT NULL,
              updated_at TEXT,
              PRIMARY KEY (setting_key, lang_code)
            )"
        );
    } else {
        $pdo->exec(
            "CREATE TABLE IF NOT EXISTS site_settings_i18n (
              setting_key VARCHAR(100) NOT NULL,
              lang_code VARCHAR(8) NOT NULL,
              setting_value MEDIUMTEXT NOT NULL,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (setting_key, lang_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        );
    }
}

function setting_i18n(PDO $pdo, string $key, string $lang, ?string $default = null): ?string
{
    ensure_cms_i18n_table($pdo);
    $lang = strtolower(substr($lang, 0, 2));
    $stmt = $pdo->prepare(
        'SELECT setting_value FROM site_settings_i18n WHERE setting_key = ? AND lang_code = ? LIMIT 1'
    );
    $stmt->execute([$key, $lang]);
    $row = $stmt->fetch();
    if ($row) {
        return (string) $row['setting_value'];
    }
    // Fallback: base site_settings then default
    $base = setting($pdo, $key, null);
    return $base !== null ? $base : $default;
}

function set_setting_i18n(PDO $pdo, string $key, string $lang, string $value): void
{
    ensure_cms_i18n_table($pdo);
    $lang = strtolower(substr($lang, 0, 2));
    $stmt = $pdo->prepare(
        'INSERT INTO site_settings_i18n (setting_key, lang_code, setting_value)
         VALUES (?, ?, ?)
         ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)'
    );
    $stmt->execute([$key, $lang, $value]);
    // Keep legacy single-value in sync for primary marketing lang (bn) or en
    if ($lang === 'bn' || $lang === 'en') {
        set_setting($pdo, $key, $value);
    }
}

/**
 * When one language is updated, auto-fill other languages via MyMemory (best-effort).
 */
function amp_cms_propagate_translate(
    PDO $pdo,
    string $key,
    string $sourceLang,
    string $sourceValue,
    bool $overwrite = false
): array {
    ensure_cms_i18n_table($pdo);
    $sourceLang = strtolower(substr($sourceLang, 0, 2));
    set_setting_i18n($pdo, $key, $sourceLang, $sourceValue);
    $results = [$sourceLang => 'source'];
    $short = strlen(trim($sourceValue)) < 8;
    foreach (amp_cms_langs() as $lang) {
        if ($lang === $sourceLang) {
            continue;
        }
        if (!$overwrite) {
            $existing = setting_i18n($pdo, $key, $lang, null);
            if ($existing !== null && trim($existing) !== '') {
                $results[$lang] = 'kept';
                continue;
            }
        }
        if ($short) {
            set_setting_i18n($pdo, $key, $lang, $sourceValue);
            $results[$lang] = 'copied_short';
            continue;
        }
        $translated = amp_mymemory_translate($sourceValue, $sourceLang, $lang);
        if ($translated === '') {
            $results[$lang] = 'failed';
            continue;
        }
        set_setting_i18n($pdo, $key, $lang, $translated);
        $results[$lang] = 'translated';
        usleep(350000); // gentle rate limit
    }
    return $results;
}

function amp_mymemory_translate(string $text, string $from, string $to): string
{
    $from = strtolower(substr($from, 0, 2));
    $to = strtolower(substr($to, 0, 2));
    if ($from === $to || trim($text) === '') {
        return $text;
    }
    // MyMemory lang pairs
    $map = ['bn' => 'bn-BD', 'en' => 'en', 'hi' => 'hi-IN', 'ur' => 'ur-PK', 'ta' => 'ta-IN', 'ml' => 'ml-IN'];
    $langpair = ($map[$from] ?? $from) . '|' . ($map[$to] ?? $to);
    $url = 'https://api.mymemory.translated.net/get?q=' . rawurlencode(mb_substr($text, 0, 450))
        . '&langpair=' . rawurlencode($langpair);
    $ctx = stream_context_create(['http' => ['timeout' => 12]]);
    $raw = @file_get_contents($url, false, $ctx);
    if ($raw === false) {
        return '';
    }
    $json = json_decode($raw, true);
    $out = (string) ($json['responseData']['translatedText'] ?? '');
    if ($out === '' || stripos($out, 'INVALID') !== false) {
        return '';
    }
    return html_entity_decode($out, ENT_QUOTES | ENT_HTML5, 'UTF-8');
}

function amp_whatsapp_sales_link(string $prefill = ''): string
{
    $num = '8801684355055';
    $q = $prefill !== '' ? ('?text=' . rawurlencode($prefill)) : '';
    return 'https://wa.me/' . $num . $q;
}
