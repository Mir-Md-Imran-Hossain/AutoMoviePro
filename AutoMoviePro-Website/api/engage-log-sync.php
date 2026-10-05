<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_response(['ok' => false, 'error' => 'method_not_allowed'], 405);
}

$customer = require_api_customer($pdo);
$data = amp_request_json();
if (!$data) {
    $data = $_POST;
}

$day = trim((string) ($data['day'] ?? date('Y-m-d')));
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $day)) {
    $day = date('Y-m-d');
}

$events = $data['events'] ?? [];
if (!is_array($events)) {
    json_response(['ok' => false, 'error' => 'events_required'], 400);
}

$cid = (int) $customer['id'];
$now = amp_sql_now($pdo);
$ins = $pdo->prepare(
    "INSERT INTO engage_activity_logs
      (customer_id, day, platform, action, url, title, detail, ok, meta_json, local_id, created_at, synced_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {$now})"
);

$saved = 0;
foreach ($events as $ev) {
    if (!is_array($ev)) {
        continue;
    }
    $action = substr(trim((string) ($ev['action'] ?? '')), 0, 80);
    if ($action === '') {
        continue;
    }
    $platform = substr(trim((string) ($ev['platform'] ?? '')), 0, 40);
    $url = substr(trim((string) ($ev['url'] ?? '')), 0, 500);
    $title = substr(trim((string) ($ev['title'] ?? '')), 0, 300);
    $detail = substr(trim((string) ($ev['detail'] ?? '')), 0, 1000);
    $ok = !empty($ev['ok']) ? 1 : 0;
    $localId = isset($ev['local_id']) ? (int) $ev['local_id'] : null;
    $meta = $ev['meta'] ?? null;
    if (is_array($meta)) {
        $meta = json_encode($meta, JSON_UNESCAPED_UNICODE);
    } elseif (is_string($meta) && $meta !== '') {
        // keep as-is
    } else {
        $meta = null;
    }
    $created = trim((string) ($ev['created_at'] ?? ''));
    if ($created === '') {
        $created = date('Y-m-d H:i:s');
    }

    $ins->execute([
        $cid,
        $day,
        $platform !== '' ? $platform : null,
        $action,
        $url !== '' ? $url : null,
        $title !== '' ? $title : null,
        $detail !== '' ? $detail : null,
        $ok,
        $meta,
        $localId,
        $created,
    ]);
    $saved++;
}

log_api($pdo, $cid, 'engage_log_sync', "day={$day};saved={$saved}");

json_response(['ok' => true, 'saved' => $saved, 'day' => $day]);
