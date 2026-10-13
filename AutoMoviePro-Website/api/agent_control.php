<?php
declare(strict_types=1);

/**
 * AutoMovie Pro - Master Agent Control Hub API (RESTful JSON)
 * 
 * Secure, bi-directional API interface empowering an Autonomous Agent (Antigravity)
 * to control, inspect, modify, and supervise the entire AutoMovie Pro website, CMS,
 * payments, orders, licenses, coupons, AI chat (Ayesha), and emergency controls.
 */

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

require_once dirname(__DIR__) . '/includes/bootstrap.php';

// -----------------------------------------------------------------------------
// 1. Authentication & Security Layer
// -----------------------------------------------------------------------------
$agentKeyHeader = $_SERVER['HTTP_X_AGENT_KEY'] ?? $_SERVER['HTTP_AUTHORIZATION'] ?? '';
if (str_starts_with($agentKeyHeader, 'Bearer ')) {
    $agentKeyHeader = substr($agentKeyHeader, 7);
}

// Master agent key can be set in site_settings, config.php, or environment variable.
// Default fallback secret for initial setup:
$configuredKey = setting($pdo, 'agent_master_secret', '');
if (empty($configuredKey)) {
    $configuredKey = $config['agent_master_secret'] ?? getenv('AMP_AGENT_MASTER_SECRET') ?: 'amp_agent_master_live_key_2026';
    set_setting($pdo, 'agent_master_secret', $configuredKey);
}

// Ensure database table for chat logs exists so Agent can supervise all conversations
try {
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    if ($driver === 'sqlite') {
        $pdo->exec("CREATE TABLE IF NOT EXISTS customer_chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            customer_id INTEGER NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            lang TEXT DEFAULT 'bn',
            metadata TEXT NULL,
            is_overridden INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )");
        $pdo->exec("CREATE INDEX IF NOT EXISTS idx_chat_session ON customer_chat_logs(session_id)");
    } else {
        $pdo->exec("CREATE TABLE IF NOT EXISTS customer_chat_logs (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            session_id VARCHAR(64) NOT NULL,
            customer_id INT UNSIGNED NULL,
            sender ENUM('customer','bot','agent_human') NOT NULL,
            message TEXT NOT NULL,
            lang VARCHAR(8) DEFAULT 'bn',
            metadata JSON NULL,
            is_overridden TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_chat_session (session_id),
            INDEX idx_chat_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
    }
} catch (\Throwable $e) {}

// Verify Key
if ($agentKeyHeader !== $configuredKey && ($_GET['key'] ?? '') !== $configuredKey) {
    http_response_code(401);
    echo json_encode([
        'ok' => false,
        'error' => 'unauthorized',
        'message' => 'Invalid or missing Agent Master Key. Provide via X-Agent-Key header or key parameter.'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// -----------------------------------------------------------------------------
// 2. Request Routing
// -----------------------------------------------------------------------------
$method = $_SERVER['REQUEST_METHOD'];
$action = strtolower(trim((string) ($_GET['action'] ?? '')));

$rawInput = file_get_contents('php://input');
$payload = json_decode($rawInput ?: '{}', true);
if (!is_array($payload)) {
    $payload = $_POST;
}

function send_json(array $data, int $statusCode = 200): void {
    http_response_code($statusCode);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

// -----------------------------------------------------------------------------
// 3. Action Dispatcher
// -----------------------------------------------------------------------------
try {
    switch ($action) {
        
        // ---------------------------------------------------------------------
        // A. SYSTEM OVERVIEW & METRICS
        // ---------------------------------------------------------------------
        case 'status':
        case 'overview':
            // 1. Revenue
            $revApproved = (float) $pdo->query("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active')")->fetchColumn();
            $revToday = (float) $pdo->query("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status IN ('approved', 'active') AND DATE(created_at) = CURRENT_DATE")->fetchColumn();
            
            // 2. Customers
            $totalCust = (int) $pdo->query("SELECT COUNT(*) FROM customers")->fetchColumn();
            $activeCust = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'active'")->fetchColumn();
            $bannedCust = (int) $pdo->query("SELECT COUNT(*) FROM customers WHERE status = 'banned'")->fetchColumn();
            
            // 3. Orders
            $pendingOrders = (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status = 'pending_payment'")->fetchColumn();
            $approvedOrders = (int) $pdo->query("SELECT COUNT(*) FROM orders WHERE status = 'approved'")->fetchColumn();
            
            // 4. SMS Unmatched
            $unmatchedSms = 0;
            try {
                $unmatchedSms = (int) $pdo->query("SELECT COUNT(*) FROM agent_sms_inbox WHERE is_matched = 0")->fetchColumn();
            } catch (\Throwable $e) {}

            // 5. Active Chats Today
            $recentChats = 0;
            try {
                $recentChats = (int) $pdo->query("SELECT COUNT(DISTINCT session_id) FROM customer_chat_logs WHERE DATE(created_at) = CURRENT_DATE")->fetchColumn();
            } catch (\Throwable $e) {}

            send_json([
                'ok' => true,
                'status' => 'operational',
                'timestamp' => date('c'),
                'metrics' => [
                    'total_revenue_bdt' => $revApproved,
                    'today_revenue_bdt' => $revToday,
                    'total_customers' => $totalCust,
                    'active_customers' => $activeCust,
                    'banned_customers' => $bannedCust,
                    'pending_orders' => $pendingOrders,
                    'approved_orders' => $approvedOrders,
                    'unmatched_sms' => $unmatchedSms,
                    'active_chat_sessions_today' => $recentChats,
                ],
                'pricing' => [
                    'price_amount' => (float) setting($pdo, 'price_amount', '2998'),
                    'language_addon_price' => (float) setting($pdo, 'language_addon_price', '499'),
                    'google_pro_price' => 120.0,
                ],
                'emergency' => [
                    'maintenance_mode' => (bool) (int) setting($pdo, 'maintenance_mode', '0'),
                    'broadcast_notice' => setting($pdo, 'broadcast_notice', ''),
                ]
            ]);
            break;

        // ---------------------------------------------------------------------
        // B. CMS CONTENT MANAGEMENT (Multilingual & Global)
        // ---------------------------------------------------------------------
        case 'get_content':
            $key = trim((string) ($payload['key'] ?? $_GET['key'] ?? ''));
            $lang = trim((string) ($payload['lang'] ?? $_GET['lang'] ?? 'bn'));
            
            if (!empty($key)) {
                $val = setting_i18n($pdo, $key, $lang);
                send_json(['ok' => true, 'key' => $key, 'lang' => $lang, 'value' => $val]);
            }
            
            // Return all settings
            $stmt = $pdo->query("SELECT setting_key, setting_value FROM site_settings");
            $all = $stmt->fetchAll(PDO::FETCH_KEY_PAIR);
            send_json(['ok' => true, 'settings' => $all]);
            break;

        case 'update_content':
            $key = trim((string) ($payload['key'] ?? ''));
            $value = (string) ($payload['value'] ?? '');
            $lang = trim((string) ($payload['lang'] ?? ''));
            $autoTranslate = (bool) ($payload['propagate_translations'] ?? false);

            if (empty($key)) {
                send_json(['ok' => false, 'error' => 'missing_key'], 400);
            }

            if (!empty($lang)) {
                set_setting_i18n($pdo, $key, $lang, $value);
                if ($autoTranslate && function_exists('amp_cms_propagate_translate')) {
                    amp_cms_propagate_translate($pdo, $key, $lang, $value);
                }
            } else {
                set_setting($pdo, $key, $value);
            }

            send_json([
                'ok' => true,
                'message' => "Content key '{$key}' updated successfully.",
                'key' => $key,
                'value' => $value,
                'lang' => $lang ?: 'global'
            ]);
            break;

        case 'broadcast_notice':
            $notice = trim((string) ($payload['notice'] ?? ''));
            if ($notice === '') {
                send_json(['ok' => false, 'error' => 'empty_notice'], 400);
            }
            set_setting($pdo, 'broadcast_notice', $notice);
            send_json([
                'ok' => true,
                'broadcast_notice' => $notice,
                'message' => 'Broadcast banner updated across all website pages and user dashboards.'
            ]);
            break;

        // ---------------------------------------------------------------------
        // C. PAYMENT GATEWAYS & PRICING
        // ---------------------------------------------------------------------
        case 'get_payment_settings':
            send_json([
                'ok' => true,
                'pricing' => [
                    'price_amount' => (float) setting($pdo, 'price_amount', '2998'),
                    'language_addon_price' => (float) setting($pdo, 'language_addon_price', '499'),
                ],
                'payment_info' => [
                    'account_name' => amp_payment_account_name(),
                    'personal_bkash_nagad' => amp_payment_bkash_nagad_personal(),
                    'bkash_agent' => amp_payment_bkash_agent(),
                    'nagad_agent' => amp_payment_nagad_agent(),
                    'rocket_agent' => amp_payment_rocket_agent(),
                    'instructions' => amp_default_payment_instructions_text(),
                ]
            ]);
            break;

        case 'update_pricing':
            $newPrice = $payload['price_amount'] ?? null;
            $newAddon = $payload['language_addon_price'] ?? null;

            if ($newPrice !== null) {
                set_setting($pdo, 'price_amount', (string) ((float) $newPrice));
            }
            if ($newAddon !== null) {
                set_setting($pdo, 'language_addon_price', (string) ((float) $newAddon));
            }

            send_json([
                'ok' => true,
                'message' => 'Pricing updated successfully.',
                'price_amount' => (float) setting($pdo, 'price_amount', '2998'),
                'language_addon_price' => (float) setting($pdo, 'language_addon_price', '499')
            ]);
            break;

        // ---------------------------------------------------------------------
        // D. ORDER MANAGEMENT & AUTO-VERIFICATION
        // ---------------------------------------------------------------------
        case 'list_orders':
            $statusFilter = trim((string) ($payload['status'] ?? $_GET['status'] ?? ''));
            $limit = min(100, max(1, (int) ($payload['limit'] ?? $_GET['limit'] ?? 25)));

            $sql = "SELECT id, customer_id, name, whatsapp, email, plan_name, amount, status, payment_method, txn_id, sender_last_digits, created_at, approved_at FROM orders";
            $params = [];
            if (!empty($statusFilter)) {
                $sql .= " WHERE status = ?";
                $params[] = $statusFilter;
            }
            $sql .= " ORDER BY id DESC LIMIT {$limit}";

            $stmt = $pdo->prepare($sql);
            $stmt->execute($params);
            send_json(['ok' => true, 'orders' => $stmt->fetchAll()]);
            break;

        case 'approve_order':
            $orderId = (int) ($payload['order_id'] ?? 0);
            if ($orderId <= 0) {
                send_json(['ok' => false, 'error' => 'invalid_order_id'], 400);
            }

            $stmt = $pdo->prepare('SELECT * FROM orders WHERE id = ? LIMIT 1');
            $stmt->execute([$orderId]);
            $order = $stmt->fetch();
            if (!$order) {
                send_json(['ok' => false, 'error' => 'order_not_found'], 404);
            }

            // Update order status
            $up = $pdo->prepare("UPDATE orders SET status = 'approved', approved_at = CURRENT_TIMESTAMP WHERE id = ?");
            $up->execute([$orderId]);

            // Ensure customer active and set accurate package tier
            $custId = (int) ($order['customer_id'] ?? 0);
            $tier = function_exists('amp_determine_order_tier') ? amp_determine_order_tier($order) : 'video_studio';
            if ($custId > 0) {
                $cUp = $pdo->prepare("UPDATE customers SET status = 'active', tier = ?, plan = ?, activated_at = CURRENT_TIMESTAMP WHERE id = ?");
                $cUp->execute([$tier, $tier, $custId]);

                // Create or un-revoke license
                $lCheck = $pdo->prepare("SELECT id FROM licenses WHERE customer_id = ? AND revoked = 0 LIMIT 1");
                $lCheck->execute([$custId]);
                if (!$lCheck->fetch()) {
                    $token = bin2hex(random_bytes(16));
                    $insLic = $pdo->prepare("INSERT INTO licenses (customer_id, token, expires_at, revoked) VALUES (?, ?, NULL, 0)");
                    $insLic->execute([$custId, $token]);
                }
            }

            send_json([
                'ok' => true,
                'order_id' => $orderId,
                'customer_id' => $custId,
                'tier' => $tier,
                'plan' => $tier,
                'status' => 'approved',
                'message' => "Order #{$orderId} approved and license active!"
            ]);
            break;

        case 'reject_order':
            $orderId = (int) ($payload['order_id'] ?? 0);
            $reason = trim((string) ($payload['reason'] ?? 'Verification failed'));
            $up = $pdo->prepare("UPDATE orders SET status = 'rejected' WHERE id = ?");
            $up->execute([$orderId]);
            send_json(['ok' => true, 'order_id' => $orderId, 'status' => 'rejected', 'reason' => $reason]);
            break;

        // ---------------------------------------------------------------------
        // E. CUSTOMER MANAGEMENT & REMOTE KILL-SWITCH
        // ---------------------------------------------------------------------
        case 'list_customers':
            $limit = min(100, max(1, (int) ($payload['limit'] ?? $_GET['limit'] ?? 25)));
            $search = trim((string) ($payload['search'] ?? $_GET['search'] ?? ''));

            $sql = "SELECT id, name, whatsapp, email, login_id, status, tier, plan, notes, last_heartbeat_at, created_at, activated_at FROM customers";
            $params = [];
            if (!empty($search)) {
                $sql .= " WHERE name LIKE ? OR whatsapp LIKE ? OR email LIKE ? OR login_id LIKE ?";
                $term = "%{$search}%";
                $params = [$term, $term, $term, $term];
            }
            $sql .= " ORDER BY id DESC LIMIT {$limit}";

            $stmt = $pdo->prepare($sql);
            $stmt->execute($params);
            send_json(['ok' => true, 'customers' => $stmt->fetchAll()]);
            break;

        case 'killswitch':
            $customerId = (int) ($payload['customer_id'] ?? 0);
            $actionType = strtolower(trim((string) ($payload['status'] ?? 'banned'))); // 'banned' or 'active'

            if ($customerId <= 0) {
                send_json(['ok' => false, 'error' => 'invalid_customer_id'], 400);
            }

            $newStatus = ($actionType === 'active') ? 'active' : 'banned';
            $revoked = ($newStatus === 'banned') ? 1 : 0;

            $pdo->prepare("UPDATE customers SET status = ? WHERE id = ?")->execute([$newStatus, $customerId]);
            $pdo->prepare("UPDATE licenses SET revoked = ? WHERE customer_id = ?")->execute([$revoked, $customerId]);

            send_json([
                'ok' => true,
                'customer_id' => $customerId,
                'status' => $newStatus,
                'hardware_locked' => ($revoked === 1),
                'message' => ($newStatus === 'banned')
                    ? "গ্রাহক #{$customerId} এর লাইসেন্স তাৎক্ষণিকভাবে বন্ধ ও পিসি লক করা হয়েছে।"
                    : "গ্রাহক #{$customerId} এর লাইসেন্স সক্রিয় করা হয়েছে।"
            ]);
            break;

        // ---------------------------------------------------------------------
        // F. LIVE AI SALES AGENT (AYESHA) SUPERVISION & CHAT MANAGEMENT
        // ---------------------------------------------------------------------
        case 'get_chat_history':
            $sessionId = trim((string) ($payload['session_id'] ?? $_GET['session_id'] ?? ''));
            $limit = min(100, (int) ($payload['limit'] ?? $_GET['limit'] ?? 50));

            $sql = "SELECT id, session_id, sender, message, lang, is_overridden, created_at FROM customer_chat_logs";
            $params = [];
            if (!empty($sessionId)) {
                $sql .= " WHERE session_id = ?";
                $params[] = $sessionId;
            }
            $sql .= " ORDER BY id DESC LIMIT {$limit}";

            $stmt = $pdo->prepare($sql);
            $stmt->execute($params);
            send_json(['ok' => true, 'messages' => array_reverse($stmt->fetchAll())]);
            break;

        case 'agent_command_ayesha':
            // Send special guidance prompt or directive to Ayesha
            $instruction = trim((string) ($payload['instruction'] ?? ''));
            if (empty($instruction)) {
                send_json(['ok' => false, 'error' => 'missing_instruction'], 400);
            }

            set_setting($pdo, 'ayesha_custom_directive', $instruction);
            send_json([
                'ok' => true,
                'directive' => $instruction,
                'message' => 'New directive injected into Ayesha (AI Sales Consultant). Future visitor chats will follow this guidance.'
            ]);
            break;

        case 'agent_override_chat':
            // The master agent intervenes directly in a customer conversation
            $sessionId = trim((string) ($payload['session_id'] ?? ''));
            $replyMessage = trim((string) ($payload['reply'] ?? ''));

            if (empty($sessionId) || empty($replyMessage)) {
                send_json(['ok' => false, 'error' => 'missing_session_or_reply'], 400);
            }

            $ins = $pdo->prepare("INSERT INTO customer_chat_logs (session_id, sender, message, lang, is_overridden) VALUES (?, 'agent_human', ?, 'bn', 1)");
            $ins->execute([$sessionId, $replyMessage]);

            send_json([
                'ok' => true,
                'session_id' => $sessionId,
                'message' => 'Override message sent to visitor chat queue.',
                'reply' => $replyMessage
            ]);
            break;

        // ---------------------------------------------------------------------
        // G. COUPONS & PROMOTIONS MANAGEMENT
        // ---------------------------------------------------------------------
        case 'list_coupons':
            $stmt = $pdo->query("SELECT * FROM coupons ORDER BY id DESC");
            send_json(['ok' => true, 'coupons' => $stmt->fetchAll()]);
            break;

        case 'create_coupon':
            $code = strtoupper(trim((string) ($payload['code'] ?? '')));
            $discountAmount = (float) ($payload['discount_amount'] ?? 0);
            $discountPercent = (int) ($payload['discount_percent'] ?? 0);
            $minOrder = (float) ($payload['min_order_amount'] ?? 0);

            if (empty($code)) {
                send_json(['ok' => false, 'error' => 'missing_coupon_code'], 400);
            }

            $ins = $pdo->prepare("INSERT INTO coupons (code, discount_amount, discount_percent, min_order_amount, is_active) VALUES (?, ?, ?, ?, 1)");
            $ins->execute([$code, $discountAmount, $discountPercent, $minOrder]);

            send_json(['ok' => true, 'message' => "Coupon '{$code}' created successfully!"]);
            break;

        // ---------------------------------------------------------------------
        // H. EMERGENCY & HEALTH CONTROL
        // ---------------------------------------------------------------------
        case 'set_maintenance_mode':
            $enable = (bool) ($payload['enabled'] ?? false);
            set_setting($pdo, 'maintenance_mode', $enable ? '1' : '0');
            send_json([
                'ok' => true,
                'maintenance_mode' => $enable,
                'message' => $enable ? 'Maintenance mode enabled. Visitors will see maintenance screen.' : 'Maintenance mode disabled. Site is live.'
            ]);
            break;

        default:
            send_json([
                'ok' => false,
                'error' => 'invalid_action',
                'available_actions' => [
                    'overview' => 'Full dashboard metrics, revenue, customers, orders, pricing',
                    'get_content' => 'Fetch global or language-specific CMS text',
                    'update_content' => 'Update any website headline, text, or FAQ',
                    'broadcast_notice' => 'Push live alert banner across website and user app',
                    'get_payment_settings' => 'Read payment gateway numbers and instruction block',
                    'update_pricing' => 'Update core lifetime price and language addon price',
                    'list_orders' => 'Filter and view pending/approved orders with txn IDs',
                    'approve_order' => 'Approve order and automatically issue software license',
                    'reject_order' => 'Reject fake or unverified order',
                    'list_customers' => 'Search and inspect customers',
                    'killswitch' => 'Instantly freeze or unfreeze customer software access',
                    'get_chat_history' => 'Inspect customer chats with Ayesha',
                    'agent_command_ayesha' => 'Inject behavior directives to Ayesha AI agent',
                    'agent_override_chat' => 'Intervene and reply directly to a visitor chat',
                    'list_coupons' => 'View active coupons',
                    'create_coupon' => 'Create new discount coupon code',
                    'set_maintenance_mode' => 'Toggle maintenance lock'
                ]
            ], 400);
    }

} catch (\Throwable $e) {
    send_json([
        'ok' => false,
        'error' => 'server_error',
        'details' => $e->getMessage()
    ], 500);
}
