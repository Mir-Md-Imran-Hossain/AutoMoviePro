<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';

$method = $_SERVER['REQUEST_METHOD'];
$action = $_GET['action'] ?? 'metrics';

if ($method === 'GET' && $action === 'metrics') {
    // 1. Total lifetime sales
    $revStmt = $pdo->query("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active')");
    $totalRev = (float) $revStmt->fetchColumn();

    // 2. Today's revenue
    $todayStmt = $pdo->query("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active') AND DATE(created_at) = CURDATE()");
    $todayRev = (float) $todayStmt->fetchColumn();

    // 3. Customers count
    $custCountStmt = $pdo->query("SELECT COUNT(*) FROM customers");
    $custCount = (int) $custCountStmt->fetchColumn();

    // 4. Pending orders count
    $pendStmt = $pdo->query("SELECT COUNT(*) FROM orders WHERE status = 'pending_payment'");
    $pendingOrders = (int) $pendStmt->fetchColumn();

    // 5. Recent Customers
    $custsStmt = $pdo->query("SELECT id, name, whatsapp, email, plan, status, created_at FROM customers ORDER BY id DESC LIMIT 15");
    $customers = $custsStmt->fetchAll();

    // 6. Current broadcast notice
    $noticeStmt = $pdo->prepare("SELECT setting_value FROM site_settings WHERE setting_key = 'broadcast_notice' LIMIT 1");
    $noticeStmt->execute();
    $notice = (string) ($noticeStmt->fetchColumn() ?: 'স্বাগতম AutoMovie Pro তে! নিরবচ্ছিন্ন ভিডিও উৎপাদন ও প্রকাশনা চলছে।');

    echo json_encode([
        'ok' => true,
        'metrics' => [
            'total_revenue' => $totalRev,
            'today_revenue' => $todayRev,
            'customer_count' => $custCount,
            'pending_orders' => $pendingOrders,
            'broadcast_notice' => $notice
        ],
        'customers' => $customers
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($method === 'POST') {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true) ?? $_POST;

    if ($action === 'killswitch') {
        $customerId = (int) ($data['customer_id'] ?? 0);
        $newStatus = trim((string) ($data['status'] ?? 'banned')); // 'banned' or 'active'

        if ($customerId <= 0) {
            echo json_encode(['ok' => false, 'error' => 'Invalid customer ID']);
            exit;
        }

        // Update customer
        $up = $pdo->prepare('UPDATE customers SET status = ? WHERE id = ?');
        $up->execute([$newStatus, $customerId]);

        // Revoke or unrevoke license
        $revokedVal = ($newStatus === 'banned') ? 1 : 0;
        $licUp = $pdo->prepare('UPDATE licenses SET revoked = ? WHERE customer_id = ?');
        $licUp->execute([$revokedVal, $customerId]);

        echo json_encode([
            'ok' => true,
            'customer_id' => $customerId,
            'status' => $newStatus,
            'message' => ($newStatus === 'banned') ? "গ্রাহক #{$customerId} এর লাইসেন্স তাৎক্ষণিকভাবে ব্লক করা হয়েছে। পিসিতে লক কার্যকর হয়েছে।" : "গ্রাহক #{$customerId} এর লাইসেন্স পুনরায় সক্রিয় করা হয়েছে।"
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }

    if ($action === 'broadcast') {
        $notice = trim((string) ($data['notice'] ?? ''));
        if ($notice === '') {
            echo json_encode(['ok' => false, 'error' => 'Notice text cannot be empty']);
            exit;
        }

        // Upsert site_settings
        $check = $pdo->prepare("SELECT setting_key FROM site_settings WHERE setting_key = 'broadcast_notice' LIMIT 1");
        $check->execute();
        if ($check->fetch()) {
            $up = $pdo->prepare("UPDATE site_settings SET setting_value = ? WHERE setting_key = 'broadcast_notice'");
            $up->execute([$notice]);
        } else {
            $ins = $pdo->prepare("INSERT INTO site_settings (setting_key, setting_value) VALUES ('broadcast_notice', ?)");
            $ins->execute([$notice]);
        }

        echo json_encode([
            'ok' => true,
            'notice' => $notice,
            'message' => 'নোটিশটি সকল গ্রাহকের সফটওয়্যারে সফলভাবে ব্রডকাস্ট করা হয়েছে।'
        ], JSON_UNESCAPED_UNICODE);
        exit;
    }
}

http_response_code(405);
echo json_encode(['ok' => false, 'error' => 'Method Not Allowed']);
