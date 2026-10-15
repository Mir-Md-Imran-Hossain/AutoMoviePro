<?php
declare(strict_types=1);

/**
 * WAManager Pro Commercial Licensing Gateway API
 * Handles hardware fingerprint binding, activation, verification, and licensing enforcement.
 */

require dirname(__DIR__) . '/includes/bootstrap.php';

ensure_amp_migrations($pdo);

header('Content-Type: application/json; charset=utf-8');

$method = $_SERVER['REQUEST_METHOD'];
if ($method !== 'POST' && $method !== 'GET') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

$rawInput = file_get_contents('php://input');
$data = json_decode($rawInput, true);
if (!is_array($data)) {
    $data = $_POST;
}

$action = trim((string) ($data['action'] ?? $_GET['action'] ?? 'verify'));
$licenseSecret = get_setting($pdo, 'wamanager_license_salt', 'WAM_PRO_SIGNING_SALT_98457201_SECURE');

// Helper to sign activation tokens
function wam_sign_token(string $key, string $hwid, string $salt): string
{
    return hash_hmac('sha256', "{$key}|{$hwid}|WAM_ENTERPRISE", $salt);
}

// -------------------------------------------------------------
// ACTION 1: ACTIVATE LICENSE
// -------------------------------------------------------------
if ($action === 'activate') {
    $licenseKey = strtoupper(trim((string) ($data['license_key'] ?? '')));
    $hardwareId = trim((string) ($data['hardware_id'] ?? ''));
    $machineName = trim((string) ($data['machine_name'] ?? 'Windows PC'));
    $appVersion = trim((string) ($data['app_version'] ?? '1.0.0'));

    if ($licenseKey === '' || $hardwareId === '') {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => 'missing_parameters', 'message' => 'লাইসেন্স কি এবং হার্ডওয়্যার আইডি প্রদান করা আবশ্যক।']);
        exit;
    }

    // Check in wamanager_licenses table
    $st = $pdo->prepare("SELECT * FROM wamanager_licenses WHERE license_key = ? LIMIT 1");
    $st->execute([$licenseKey]);
    $lic = $st->fetch(PDO::FETCH_ASSOC);

    // If not found in dedicated wamanager_licenses, check if it's an approved AutoMovie Pro customer login ID or token
    if (!$lic) {
        $stCust = $pdo->prepare("SELECT * FROM customers WHERE (login_id = ? OR whatsapp = ?) AND status = 'active' LIMIT 1");
        $stCust->execute([$licenseKey, $licenseKey]);
        $cust = $stCust->fetch(PDO::FETCH_ASSOC);

        if ($cust) {
            // Auto-provision WAManager Pro license for this customer
            $licId = 'wam_' . bin2hex(random_bytes(8));
            $pdo->prepare(
                "INSERT INTO wamanager_licenses (id, license_key, customer_name, customer_phone, customer_email, plan_tier, status, max_devices, created_at)
                 VALUES (?, ?, ?, ?, ?, 'wamanager_pro', 'active', 1, NOW())"
            )->execute([$licId, $licenseKey, (string)$cust['name'], (string)$cust['whatsapp'], (string)($cust['email'] ?? '')]);

            $st->execute([$licenseKey]);
            $lic = $st->fetch(PDO::FETCH_ASSOC);
        }
    }

    if (!$lic) {
        http_response_code(404);
        echo json_encode(['ok' => false, 'error' => 'license_not_found', 'message' => 'প্রদত্ত লাইসেন্স কি-টি পাওয়া যায়নি। অনুগ্রহ করে সঠিক কি প্রদান করুন।']);
        exit;
    }

    if ($lic['status'] !== 'active') {
        http_response_code(403);
        echo json_encode(['ok' => false, 'error' => 'license_' . $lic['status'], 'message' => 'এই লাইসেন্সটির মেয়াদ শেষ অথবা স্থগিত করা হয়েছে।']);
        exit;
    }

    // Hardware Lock Binding Check
    $boundHwid = trim((string) ($lic['hardware_id'] ?? ''));
    if ($boundHwid !== '' && strtoupper($boundHwid) !== strtoupper($hardwareId)) {
        http_response_code(403);
        echo json_encode([
            'ok' => false,
            'error' => 'device_locked_to_another_pc',
            'message' => 'এই লাইসেন্সটি ইতিমধ্যে অন্য একটি কম্পিউটারে লক করা রয়েছে। একই সাথে একাধিক কম্পিউটারে ব্যবহার অনুমোদিত নয়। পিসি পরিবর্তনের জন্য সাপোর্টে যোগাযোগ করুন।'
        ]);
        exit;
    }

    // First time activation on this hardware -> Bind it
    if ($boundHwid === '') {
        $pdo->prepare("UPDATE wamanager_licenses SET hardware_id = ?, machine_name = ?, activated_at = NOW() WHERE id = ?")
            ->execute([$hardwareId, $machineName, $lic['id']]);
    }

    $token = wam_sign_token($licenseKey, $hardwareId, $licenseSecret);

    echo json_encode([
        'ok' => true,
        'message' => 'লাইসেন্স সফলভাবে অ্যাক্টিভেট হয়েছে!',
        'activation_token' => $token,
        'license' => [
            'license_key' => $lic['license_key'],
            'customer_name' => $lic['customer_name'],
            'tier' => $lic['plan_tier'],
            'status' => 'active',
            'is_lifetime' => true,
            'hardware_id' => $hardwareId,
            'activated_at' => $lic['activated_at'] ?: date('Y-m-d H:i:s'),
        ]
    ]);
    exit;
}

// -------------------------------------------------------------
// ACTION 2: VERIFY LICENSE / HEARTBEAT
// -------------------------------------------------------------
elseif ($action === 'verify') {
    $licenseKey = strtoupper(trim((string) ($data['license_key'] ?? '')));
    $hardwareId = trim((string) ($data['hardware_id'] ?? ''));
    $token = trim((string) ($data['token'] ?? ''));

    if ($licenseKey === '' || $hardwareId === '' || $token === '') {
        http_response_code(400);
        echo json_encode(['ok' => false, 'valid' => false, 'error' => 'missing_parameters']);
        exit;
    }

    $expectedToken = wam_sign_token($licenseKey, $hardwareId, $licenseSecret);
    if (!hash_equals($expectedToken, $token)) {
        http_response_code(403);
        echo json_encode(['ok' => false, 'valid' => false, 'error' => 'invalid_signature_token']);
        exit;
    }

    $st = $pdo->prepare("SELECT * FROM wamanager_licenses WHERE license_key = ? LIMIT 1");
    $st->execute([$licenseKey]);
    $lic = $st->fetch(PDO::FETCH_ASSOC);

    if (!$lic || $lic['status'] !== 'active') {
        http_response_code(403);
        echo json_encode(['ok' => false, 'valid' => false, 'error' => 'license_inactive']);
        exit;
    }

    if (strtoupper(trim((string)$lic['hardware_id'])) !== strtoupper($hardwareId)) {
        http_response_code(403);
        echo json_encode(['ok' => false, 'valid' => false, 'error' => 'hwid_mismatch']);
        exit;
    }

    echo json_encode([
        'ok' => true,
        'valid' => true,
        'status' => 'active',
        'tier' => $lic['plan_tier'],
        'server_time' => date('Y-m-d H:i:s')
    ]);
    exit;
}

// -------------------------------------------------------------
// ACTION 3: ADMIN GENERATE NEW LICENSE KEYS
// -------------------------------------------------------------
elseif ($action === 'admin_generate') {
    require_admin();

    $custName = trim((string) ($data['customer_name'] ?? 'বাণিজ্যিক গ্রাহক'));
    $custPhone = trim((string) ($data['customer_phone'] ?? ''));
    $custEmail = trim((string) ($data['customer_email'] ?? ''));
    $planTier = trim((string) ($data['plan_tier'] ?? 'wamanager_pro'));

    // Generate clean 16-character license key: WAM-PRO-XXXX-XXXX-XXXX
    $keyRaw = strtoupper(bin2hex(random_bytes(6)));
    $licKey = 'WAM-' . substr($keyRaw, 0, 4) . '-' . substr($keyRaw, 4, 4) . '-' . substr($keyRaw, 8, 4);

    $id = 'wam_' . bin2hex(random_bytes(8));
    $pdo->prepare(
        "INSERT INTO wamanager_licenses (id, license_key, customer_name, customer_phone, customer_email, plan_tier, status, max_devices, created_at)
         VALUES (?, ?, ?, ?, ?, ?, 'active', 1, NOW())"
    )->execute([$id, $licKey, $custName, $custPhone, $custEmail, $planTier]);

    echo json_encode([
        'ok' => true,
        'license_key' => $licKey,
        'customer_name' => $custName,
        'plan_tier' => $planTier,
        'message' => 'নতুন লাইসেন্স কি সফলভাবে তৈরি হয়েছে!'
    ]);
    exit;
}

http_response_code(400);
echo json_encode(['ok' => false, 'error' => 'unknown_action']);
