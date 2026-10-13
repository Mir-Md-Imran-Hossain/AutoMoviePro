<?php
declare(strict_types=1);

/**
 * Intelligent AI Sales Consultant "আয়েশা" (powered by Gemini & Grok via includes/agent_llm.php)
 */
header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/agent_llm.php';

$raw = file_get_contents('php://input');
$data = json_decode($raw ?: '{}', true) ?? $_POST;

$userMsg = trim((string) ($data['message'] ?? ''));
$history = (array) ($data['history'] ?? []);
$lang = strtolower(substr((string) ($data['lang'] ?? 'bn'), 0, 2));
if (!in_array($lang, amp_cms_langs(), true)) {
    $lang = 'bn';
}

if ($userMsg === '') {
    $userMsg = 'আসসালামু আলাইকুম';
}

$price = (float) setting($pdo, 'price_amount', '2998');
$addon = (float) setting($pdo, 'language_addon_price', '499');

$system = amp_agent_system_prompt($lang, $price, $addon);
$messages = [];
foreach (array_slice($history, -8) as $h) {
    if (!is_array($h)) {
        continue;
    }
    $role = (($h['role'] ?? '') === 'assistant' || ($h['role'] ?? '') === 'bot') ? 'assistant' : 'user';
    $content = trim((string) ($h['content'] ?? ''));
    if ($content !== '') {
        $messages[] = ['role' => $role, 'content' => $content];
    }
}
$messages[] = ['role' => 'user', 'content' => $userMsg];

// Check for custom directive from Master Agent
$customDirective = setting($pdo, 'ayesha_custom_directive', '');
if (!empty($customDirective)) {
    $system .= "\n\n[MASTER AGENT EXECUTIVE DIRECTIVE]: " . $customDirective;
}

$sessionId = trim((string) ($data['session_id'] ?? 'sess_' . substr(md5($_SERVER['REMOTE_ADDR'] ?? 'guest'), 0, 12)));

// Log customer incoming message
try {
    $pdo->prepare("INSERT INTO customer_chat_logs (session_id, sender, message, lang) VALUES (?, 'customer', ?, ?)")
        ->execute([$sessionId, $userMsg, $lang]);
} catch (\Throwable $e) {}

$llm = amp_agent_chat_llm($config, $system, $messages);
if ($llm !== null && $llm !== '') {
    $parsed = amp_agent_parse_llm_payload($llm);
    $replyText = $parsed['reply'];
    
    // Log Ayesha's reply
    try {
        $pdo->prepare("INSERT INTO customer_chat_logs (session_id, sender, message, lang) VALUES (?, 'bot', ?, ?)")
            ->execute([$sessionId, $replyText, $lang]);
    } catch (\Throwable $e) {}

    echo json_encode([
        'ok' => true,
        'session_id' => $sessionId,
        'agent_name' => 'আয়েশা (সিনিয়র সেলস কনসালট্যান্ট)',
        'reply' => $replyText,
        'suggestions' => $parsed['meta']['suggestions'] ?: ['প্যাকেজের দাম কত?', 'পেমেন্ট কিভাবে করব?', 'কুপন কোড দিন', 'কিভাবে ভিডিও বানায়?'],
        'mode' => 'llm'
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// Cordial intelligent fallback in Bengali as Ayesha
$fallback = "আসসালামু আলাইকুম! আমি আয়েশা, AutoMovie Pro-এর সিনিয়র কনসালট্যান্ট।\n\nআমাদের অফিসিয়াল ৩টি প্যাকেজ:\n১. ভিডিও স্টুডিও (৳৩,৯৯৯): ফুল ভিডিও স্টুডিও, অটো-সাবটাইটেল ও ইউটিউব/ফেসবুক পাবলিশিং।\n২. ফেসবুক বিজনেস ম্যানেজার (৳২,৯৯৯): মেটা বিজনেস স্যুট, অ্যাড ক্যাম্পেইন ও প্রোমো ব্যানার।\n৩. ফেসবুক প্রোফাইল ও পেজ (৳১,৯৯৯): কোটস ও পোস্ট অটো পাইলট।\n\nবিকাশ/নগদ/রকেটে অনুমোদিত এজেন্টে ক্যাশ আউট করে ৩-৪ ডিজিট সাবমিট করলেই ৫ মিনিটে আপনার লাইসেন্স স্বয়ংক্রিয়ভাবে সক্রিয় হয়ে যাবে। আপনি কোন প্যাকেজে অর্ডার করতে চান?";

// Log fallback reply
try {
    $pdo->prepare("INSERT INTO customer_chat_logs (session_id, sender, message, lang) VALUES (?, 'bot', ?, ?)")
        ->execute([$sessionId, $fallback, $lang]);
} catch (\Throwable $e) {}

echo json_encode([
    'ok' => true,
    'session_id' => $sessionId,
    'agent_name' => 'আয়েশা (সিনিয়র সেলস কনসালট্যান্ট)',
    'reply' => $fallback,
    'suggestions' => ['প্যাকেজের দাম কত?', 'পেমেন্ট কিভাবে করব?', 'কুপন কোড দিন', 'কিভাবে ভিডিও বানায়?'],
    'mode' => 'fallback'
], JSON_UNESCAPED_UNICODE);
