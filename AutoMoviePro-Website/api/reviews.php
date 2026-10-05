<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';

$method = $_SERVER['REQUEST_METHOD'];

if ($method === 'GET') {
    // Return authentic verified customer reviews from database (no fake dummy reviews)
    $stmt = $pdo->query('
        SELECT name, rating, review_text, platform, created_at 
        FROM reviews 
        WHERE is_approved = 1 
        ORDER BY id DESC 
        LIMIT 12
    ');
    $rows = $stmt ? $stmt->fetchAll(PDO::FETCH_ASSOC) : [];

    echo json_encode(['ok' => true, 'reviews' => $rows], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($method === 'POST') {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true) ?? $_POST;

    $name = trim((string) ($data['name'] ?? 'Anonymous'));
    $rating = max(1, min(5, (int) ($data['rating'] ?? 5)));
    $reviewText = trim((string) ($data['review_text'] ?? ''));
    $platform = trim((string) ($data['platform'] ?? 'General'));

    if ($reviewText === '') {
        echo json_encode(['ok' => false, 'error' => 'Review text required'], JSON_UNESCAPED_UNICODE);
        exit;
    }

    // Require admin approval before publishing to avoid spam
    $isApproved = 0;

    try {
        $now = amp_sql_now($pdo);
        $stmt = $pdo->prepare("
            INSERT INTO reviews (name, rating, review_text, platform, is_approved, created_at) 
            VALUES (?, ?, ?, ?, ?, {$now})
        ");
        $stmt->execute([$name, $rating, $reviewText, $platform, $isApproved]);
        echo json_encode(['ok' => true, 'message' => 'রিভিউ প্রদানের জন্য ধন্যবাদ! অ্যাডমিন পর্যালোচনার পর এটি প্রদর্শিত হবে।'], JSON_UNESCAPED_UNICODE);
    } catch (Throwable $e) {
        echo json_encode(['ok' => false, 'error' => 'রিভিউ সংরক্ষণ ব্যর্থ: ' . $e->getMessage()], JSON_UNESCAPED_UNICODE);
    }
    exit;
}
