<?php
declare(strict_types=1);

/**
 * App release management — single live installer under /downloads on this server.
 * No external object storage required.
 */

function amp_downloads_dir(): string
{
    $dir = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'downloads';
    if (!is_dir($dir)) {
        @mkdir($dir, 0755, true);
    }
    return $dir;
}

function amp_canonical_installer_name(): string
{
    return 'AutoMoviePro-Setup.exe';
}

function amp_release_public_url(array $config): string
{
    $configured = trim((string) ($config['download_url'] ?? ''));
    if ($configured !== '') {
        return $configured;
    }
    $site = rtrim((string) ($config['site_url'] ?? 'https://automoviepro.com'), '/');
    return $site . '/downloads/' . amp_canonical_installer_name();
}

function amp_current_release(PDO $pdo): ?array
{
    $row = $pdo->query(
        'SELECT * FROM app_releases WHERE is_current = 1 ORDER BY id DESC LIMIT 1'
    )->fetch();
    return $row ?: null;
}

function amp_version_compare_norm(string $a, string $b): int
{
    $na = preg_replace('/[^0-9.]/', '', $a) ?: '0';
    $nb = preg_replace('/[^0-9.]/', '', $b) ?: '0';
    return version_compare($na, $nb);
}

/**
 * Publish uploaded installer as the only current version.
 * Previous current file is removed; DB marks only this row current.
 *
 * @return array{ok:bool,error?:string,release?:array}
 */
function amp_publish_release(
    PDO $pdo,
    array $config,
    string $tmpUploadPath,
    string $version,
    string $notes = '',
    int $forceHours = 24,
    bool $forceUpdate = true,
    string $publishedBy = 'admin'
): array {
    $version = trim($version);
    if ($version === '' || !preg_match('/^[0-9]+(\.[0-9]+){0,3}$/', $version)) {
        return ['ok' => false, 'error' => 'invalid_version'];
    }
    if (!is_file($tmpUploadPath) || filesize($tmpUploadPath) < 1000) {
        return ['ok' => false, 'error' => 'empty_upload'];
    }

    $dir = amp_downloads_dir();
    $canonical = amp_canonical_installer_name();
    $dest = $dir . DIRECTORY_SEPARATOR . $canonical;
    $backup = $dir . DIRECTORY_SEPARATOR . 'AutoMoviePro-Setup.prev.exe';

    // Rotate previous binary aside, then replace
    if (is_file($dest)) {
        @unlink($backup);
        @rename($dest, $backup);
    }
    if (!@rename($tmpUploadPath, $dest) && !@copy($tmpUploadPath, $dest)) {
        // restore backup if replace failed
        if (is_file($backup) && !is_file($dest)) {
            @rename($backup, $dest);
        }
        return ['ok' => false, 'error' => 'move_failed'];
    }
    @unlink($tmpUploadPath);
    // Remove previous installer after successful replace
    if (is_file($backup)) {
        @unlink($backup);
    }

    $sha = hash_file('sha256', $dest) ?: null;
    $size = (int) filesize($dest);
    $forceHours = max(1, min(168, $forceHours));
    $now = date('Y-m-d H:i:s');

    $pdo->beginTransaction();
    try {
        $pdo->exec('UPDATE app_releases SET is_current = 0 WHERE is_current = 1');
        // Drop older non-current rows (keep last 3 for audit)
        $old = $pdo->query('SELECT id FROM app_releases WHERE is_current = 0 ORDER BY id DESC')->fetchAll();
        if (count($old) > 3) {
            $dropIds = array_map(static fn ($r) => (int) $r['id'], array_slice($old, 3));
            if ($dropIds) {
                $in = implode(',', $dropIds);
                $pdo->exec("DELETE FROM app_releases WHERE id IN ({$in})");
            }
        }
        $stmt = $pdo->prepare(
            'INSERT INTO app_releases
              (version, file_name, file_path, sha256, file_size, release_notes, force_update, force_hours, published_at, published_by, is_current)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)'
        );
        $relPath = 'downloads/' . $canonical;
        $stmt->execute([
            $version,
            $canonical,
            $relPath,
            $sha,
            $size,
            $notes,
            $forceUpdate ? 1 : 0,
            $forceHours,
            $now,
            $publishedBy,
        ]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        return ['ok' => false, 'error' => 'db_failed:' . $e->getMessage()];
    }

    $release = amp_current_release($pdo);
    return ['ok' => true, 'release' => $release ?: []];
}

/**
 * Payload for desktop update-check.
 */
function amp_update_check_payload(PDO $pdo, array $config, string $clientVersion = '0.0.0'): array
{
    $rel = amp_current_release($pdo);
    $download = amp_release_public_url($config);
    if (!$rel) {
        // Fallback: file on disk without DB row
        $path = amp_downloads_dir() . DIRECTORY_SEPARATOR . amp_canonical_installer_name();
        if (is_file($path)) {
            return [
                'ok' => true,
                'update_available' => false,
                'latest_version' => $clientVersion,
                'client_version' => $clientVersion,
                'download_url' => $download,
                'force_update' => false,
                'message' => 'no_release_meta',
            ];
        }
        return [
            'ok' => true,
            'update_available' => false,
            'latest_version' => $clientVersion,
            'client_version' => $clientVersion,
            'download_url' => $download,
            'force_update' => false,
            'message' => 'no_release',
        ];
    }

    $latest = (string) $rel['version'];
    $available = amp_version_compare_norm($latest, $clientVersion) > 0;
    $force = (int) ($rel['force_update'] ?? 1) === 1;
    $hours = max(1, (int) ($rel['force_hours'] ?? 24));
    $published = strtotime((string) $rel['published_at']) ?: time();
    $deadline = $published + ($hours * 3600);
    $now = time();

    return [
        'ok' => true,
        'update_available' => $available,
        'latest_version' => $latest,
        'client_version' => $clientVersion,
        'download_url' => $download,
        'sha256' => $rel['sha256'] ?? null,
        'file_size' => (int) ($rel['file_size'] ?? 0),
        'release_notes' => (string) ($rel['release_notes'] ?? ''),
        'force_update' => $force && $available,
        'force_hours' => $hours,
        'published_at' => (string) $rel['published_at'],
        'force_deadline_utc' => gmdate('c', $deadline),
        'seconds_until_force' => max(0, $deadline - $now),
        'past_deadline' => $available && $force && $now >= $deadline,
        'preserves_data' => true,
        'preserves_login' => true,
        'message' => $available
            ? ($now >= $deadline && $force
                ? 'update_required_now'
                : 'update_available_within_deadline')
            : 'up_to_date',
    ];
}
