<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['ok' => false, 'error' => 'method_not_allowed'], 405);
}

$customer = require_api_customer($pdo);
$raw = file_get_contents('php://input') ?: '';
$data = json_decode($raw, true);
if (!is_array($data)) {
    $data = $_POST;
}

$title = trim((string) ($data['title'] ?? ''));
if ($title === '') {
    json_response(['ok' => false, 'error' => 'title_required'], 400);
}

$videoType = ($data['video_type'] ?? 'short') === 'long' ? 'long' : 'short';
$desc = (string) ($data['description'] ?? '');
$platform = substr((string) ($data['platform'] ?? ''), 0, 40);
$status = substr((string) ($data['upload_status'] ?? 'generated'), 0, 40);
$remote = (string) ($data['remote_url'] ?? '');
$local = (string) ($data['local_path'] ?? '');
$channel = (string) ($data['channel_name'] ?? '');
$uploadedAt = !empty($data['uploaded_at']) ? $data['uploaded_at'] : null;
$meta = isset($data['meta']) ? json_encode($data['meta'], JSON_UNESCAPED_UNICODE) : null;

$stmt = $pdo->prepare(
    'INSERT INTO customer_jobs
     (customer_id, channel_name, video_type, title, description, platform, upload_status, uploaded_at, remote_url, local_path, meta_json, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())'
);
$stmt->execute([
    (int) $customer['id'],
    $channel !== '' ? $channel : null,
    $videoType,
    $title,
    $desc,
    $platform !== '' ? $platform : null,
    $status,
    $uploadedAt,
    $remote !== '' ? $remote : null,
    $local !== '' ? $local : null,
    $meta,
]);

$jobId = (int) $pdo->lastInsertId();
log_api($pdo, (int) $customer['id'], 'jobs_sync', "job={$jobId}");

json_response(['ok' => true, 'job_id' => $jobId]);
