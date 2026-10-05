<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

/**
 * Peer customer videos for trust-browse engagement.
 * Returns other customers' uploaded YouTube/Facebook remote URLs only.
 */
$customer = require_api_customer($pdo);
$me = (int) $customer['id'];
$limit = (int) ($_GET['limit'] ?? 40);
if ($limit < 1) {
    $limit = 40;
}
if ($limit > 100) {
    $limit = 100;
}

$sql = "SELECT j.id, j.customer_id, j.channel_name, j.video_type, j.title, j.description,
               j.platform, j.remote_url AS url, j.uploaded_at, j.created_at
        FROM customer_jobs j
        WHERE j.customer_id <> ?
          AND j.remote_url IS NOT NULL
          AND j.remote_url <> ''
          AND (
            LOWER(COALESCE(j.platform,'')) IN ('youtube','facebook')
            OR j.remote_url LIKE '%youtube.com%'
            OR j.remote_url LIKE '%youtu.be%'
            OR j.remote_url LIKE '%facebook.com%'
            OR j.remote_url LIKE '%fb.watch%'
          )
          AND (
            j.upload_status IN ('uploaded','published','ready','live')
            OR j.uploaded_at IS NOT NULL
            OR j.remote_url LIKE 'http%'
          )
        ORDER BY COALESCE(j.uploaded_at, j.created_at) DESC
        LIMIT {$limit}";

$stmt = $pdo->prepare($sql);
$stmt->execute([$me]);
$rows = $stmt->fetchAll();

$videos = [];
foreach ($rows as $r) {
    $url = (string) ($r['url'] ?? '');
    $platform = strtolower((string) ($r['platform'] ?? ''));
    if ($platform === '' || !in_array($platform, ['youtube', 'facebook'], true)) {
        if (str_contains($url, 'youtube.com') || str_contains($url, 'youtu.be')) {
            $platform = 'youtube';
        } elseif (str_contains($url, 'facebook.com') || str_contains($url, 'fb.watch')) {
            $platform = 'facebook';
        } else {
            continue;
        }
    }
    $videos[] = [
        'id' => (int) $r['id'],
        'customer_id' => (int) $r['customer_id'],
        'channel_name' => $r['channel_name'],
        'video_type' => $r['video_type'],
        'title' => $r['title'],
        'description' => $r['description'],
        'platform' => $platform,
        'url' => $url,
        'uploaded_at' => $r['uploaded_at'],
    ];
}

log_api($pdo, $me, 'peer_videos', 'count=' . count($videos));

json_response(['ok' => true, 'videos' => $videos, 'count' => count($videos)]);
