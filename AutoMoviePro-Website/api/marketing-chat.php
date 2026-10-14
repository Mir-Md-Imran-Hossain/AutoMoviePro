<?php
declare(strict_types=1);
/**
 * Marketing chat — LLM sales agent (per UI language) + WhatsApp order handoff.
 */
require dirname(__DIR__) . '/includes/bootstrap.php';
require_once dirname(__DIR__) . '/includes/agent_llm.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'POST only']);
    exit;
}

$raw = file_get_contents('php://input');
$data = json_decode($raw ?: '{}', true);
if (!is_array($data)) {
    $data = $_POST;
}

$lang = strtolower(substr((string) ($data['lang'] ?? 'bn'), 0, 2));
if (!in_array($lang, amp_cms_langs(), true)) {
    $lang = 'bn';
}
$message = trim((string) ($data['message'] ?? ''));
$action = strtolower(trim((string) ($data['action'] ?? 'chat')));
$history = $data['history'] ?? [];
if (!is_array($history)) {
    $history = [];
}
$draft = is_array($data['draft'] ?? null) ? $data['draft'] : [];

$price = (float) setting($pdo, 'price_amount', '3999');
$addon = (float) setting($pdo, 'language_addon_price', '499');

$agentId = (string) ($data['agent_id'] ?? 'ayesha');
$agentName = (string) ($data['agent_name'] ?? 'আয়েশা (Ayesha)');
$agentRole = (string) ($data['agent_role'] ?? 'সিনিয়র কাস্টমার কনসালট্যান্ট');

if ($action === 'greet' || $message === '') {
    $greetUser = match ($lang) {
        'en' => "Say a short warm hello as {$agentName}, the AutoMovie Pro sales consultant and ask how you can help (features, pricing, packages, or order).",
        'bn' => "আপনি {$agentName}, AutoMovie Pro টিমের একজন আন্তরিক প্রতিনিধি। অত্যন্ত বিনীতভাবে সালাম দিয়ে নিজের নাম বলুন এবং কাস্টমারকে কীভাবে সাহায্য করতে পারেন (প্যাকেজ, দাম বা অর্ডার) তা জানতে চান।",
        'hi' => 'छोटा सा गर्मजोशी भरा नमस्ते दो और पूछो कैसे मदद कर सकते हो (कीमत, भाषा, चैनल, ऑर्डर)।',
        'ur' => 'مختصر گرم جو شی سے سلام کہو اور پوچھو کیسے مدد کر سکتے ہو (قیمت، زبان، چینل، آرڈر)۔',
        'ta' => 'சுருக்கமான அன்பான வணக்கம் சொல்லி எப்படி உதவலாம் என்று கேள் (விலை, மொழி, சேனல், ஆர்டர்).',
        'ml' => 'ചെറിയ ഊഷ്മള നമസ്കാരം പറഞ്ഞ് എങ്ങനെ സഹായിക്കാമെന്ന് ചോദിക്കൂ (വില, ഭാഷ, ചാനൽ, ഓർഡർ).',
        default => 'Greet briefly and offer help.',
    };
    $message = $greetUser;
}

$system = amp_agent_system_prompt($lang, $price, $addon, $agentName, $agentRole);
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
$messages[] = ['role' => 'user', 'content' => $message];

$llm = amp_agent_chat_llm($config, $system, $messages, $pdo);
if ($llm === null || $llm === '') {
    // Soft fallback — still language-specific, not one English blob
    $fallback = match ($lang) {
        'en' => "Hi! I'm here to help with AutoMovie Pro.\nCore price ৳" . (int) $price . " (English + 1 language). Extra language ৳" . (int) $addon . ".\nAsk me anything, or say you want to order.",
        'bn' => "আসসালামু আলাইকুম! আমি {$agentName}, AutoMovie Pro টিম থেকে বলছি।\nআমাদের বাণিজ্যিক প্যাকেজ ও ফিচার বা অর্ডার সম্পর্কে আপনার যেকোনো প্রশ্ন থাকলে বলুন, আমি বুঝিয়ে দিচ্ছি।",
        'hi' => "नमस्ते! AutoMovie Pro में मदद के लिए मैं हूँ।\nमुख्य पैकेज ৳" . (int) $price . " (अंग्रेज़ी + आपकी 1 भाषा)। अतिरिक्त भाषा ৳" . (int) $addon . "।\nकीमत, चैनल या ऑर्डर पूछ सकते हैं।",
        'ur' => "السلام علیکم! AutoMovie Pro میں مدد کے لیے میں موجود ہوں۔\nبنیادی پیکیج ৳" . (int) $price . " (انگریزی + آپ کی 1 زبان)۔ اضافی زبان ৳" . (int) $addon . "۔\nقیمت، چینل یا آرڈر پوچھیں۔",
        'ta' => "வணக்கம்! AutoMovie Pro உதவ நான் இங்கே இருக்கிறேன்.\nமுக்கிய பேக்கேஜ் ৳" . (int) $price . " (ஆங்கிலம் + உங்கள் 1 மொழி). கூடுதல் மொழி ৳" . (int) $addon . ".\nவிலை, சேனல் அல்லது ஆர்டர் கேளுங்கள்.",
        'ml' => "നമസ്കാരം! AutoMovie Pro സഹായിക്കാൻ ഞാൻ ഇ�്ടുണ്ട്.\nമെയിൻ പാക്കേജ് ৳" . (int) $price . " (ഇംഗ്ലീഷ് + നിങ്ങളുടെ 1 ഭാഷ). അധിക ഭാഷ ৳" . (int) $addon . ".\nവില, ചാനൽ അല്ലെങ്കിൽ ഓർഡർ ചോദിക്കാം.",
        default => 'Hello! How can I help with AutoMovie Pro?',
    };
    $fallbackOut = [
        'ok' => true,
        'reply' => $fallback,
        'draft' => $draft,
        'suggestions' => match ($lang) {
            'en' => ['What is the price?', 'How many channels?', 'I want to order'],
            'bn' => ['দাম কত?', 'কয়টা চ্যানেল?', 'অর্ডার করতে চাই'],
            'hi' => ['कीमत क्या है?', 'कितने चैनल?', 'ऑर्डर करना है'],
            'ur' => ['قیمت کیا ہے؟', 'کتنے چینل؟', 'آرڈر کرنا ہے'],
            'ta' => ['விலை என்ன?', 'எத்தனை சேனல்?', 'ஆர்டர் செய்ய'],
            'ml' => ['വില എത്ര?', 'എത്ര ചാനൽ?', 'ഓർഡർ ചെയ്യണം'],
            default => [],
        },
        'mode' => 'fallback',
    ];

    try {
        $cIp = client_ip();
        $sessId = (string) ($data['session_id'] ?? bin2hex(random_bytes(8)));
        $logStmt = $pdo->prepare(
            "INSERT INTO customer_chat_logs (session_id, customer_ip, lang, agent_id, agent_name, user_message, bot_reply, whatsapp_handoff) 
             VALUES (?, ?, ?, ?, ?, ?, ?, 0)"
        );
        $logStmt->execute([
            $sessId,
            $cIp,
            $lang,
            $agentId,
            $agentName,
            $action === 'greet' ? '[স্বাগত বার্তা সম্ভাষণ]' : $message,
            $fallback
        ]);
    } catch (\Throwable $e) {}

    echo json_encode($fallbackOut, JSON_UNESCAPED_UNICODE);
    exit;
}

$parsed = amp_agent_parse_llm_payload($llm);
$meta = $parsed['meta'];
$newDraft = array_merge($draft, is_array($meta['draft'] ?? null) ? $meta['draft'] : []);

$out = [
    'ok' => true,
    'reply' => $parsed['reply'],
    'draft' => $newDraft,
    'suggestions' => $meta['suggestions'] ?: [],
    'mode' => 'llm',
];

$isWaHandoff = 0;
if (!empty($meta['open_whatsapp']) || trim((string) ($meta['wa_prefill'] ?? '')) !== '') {
    $prefill = trim((string) ($meta['wa_prefill'] ?? ''));
    if ($prefill === '') {
        $prefill = 'AutoMovie Pro order from website chat';
    }
    $out['whatsapp_url'] = amp_whatsapp_sales_link($prefill);
    $out['open_whatsapp'] = !empty($meta['open_whatsapp']);
    $isWaHandoff = 1;
}

try {
    $cIp = client_ip();
    $sessId = (string) ($data['session_id'] ?? bin2hex(random_bytes(8)));
    $logStmt = $pdo->prepare(
        "INSERT INTO customer_chat_logs (session_id, customer_ip, lang, agent_id, agent_name, user_message, bot_reply, whatsapp_handoff) 
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    );
    $logStmt->execute([
        $sessId,
        $cIp,
        $lang,
        $agentId,
        $agentName,
        $action === 'greet' ? '[স্বাগত বার্তা সম্ভাষণ]' : $message,
        $parsed['reply'],
        $isWaHandoff
    ]);
} catch (\Throwable $e) {}

echo json_encode($out, JSON_UNESCAPED_UNICODE);
