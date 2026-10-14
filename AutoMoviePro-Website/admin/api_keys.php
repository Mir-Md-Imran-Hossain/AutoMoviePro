<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_once dirname(__DIR__) . '/includes/agent_llm.php';
require_admin();

$message = '';
$testResult = null;

if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = (string) ($_POST['action'] ?? 'save');

    if ($action === 'save') {
        $gemini = trim((string) ($_POST['gemini_api_key'] ?? ''));
        $groq = trim((string) ($_POST['groq_api_key'] ?? ''));
        $openrouter = trim((string) ($_POST['openrouter_api_key'] ?? ''));
        $xai = trim((string) ($_POST['xai_api_key'] ?? ''));

        set_setting($pdo, 'gemini_api_key', $gemini);
        set_setting($pdo, 'groq_api_key', $groq);
        set_setting($pdo, 'openrouter_api_key', $openrouter);
        set_setting($pdo, 'xai_api_key', $xai);

        $message = 'এআই এপিআই কি (API Keys) সফলভাবে সেভ ও কনফিগার করা হয়েছে!';
    } elseif ($action === 'test_ai') {
        $startTime = microtime(true);
        $testMsg = [['role' => 'user', 'content' => 'Hello! Reply in 3 words.']];
        $sysPrompt = 'You are a fast test AI.';
        
        $res = amp_agent_chat_llm($config, $sysPrompt, $testMsg, $pdo);
        $elapsed = round((microtime(true) - $startTime) * 1000);

        if ($res !== null && $res !== '') {
            $testResult = [
                'success' => true,
                'time_ms' => $elapsed,
                'reply' => $res,
            ];
        } else {
            $testResult = [
                'success' => false,
                'time_ms' => $elapsed,
                'error' => 'এআই সার্ভিস থেকে কোনো সাড়া পাওয়া যায়নি। অনুগ্রহ করে আপনার এপিআই কি সঠিক আছে কিনা যাচাই করুন অথবা অন্য একটি কি প্রদান করুন।',
            ];
        }
    }
}

$curGemini = setting($pdo, 'gemini_api_key', '');
$curGroq = setting($pdo, 'groq_api_key', '');
$curOpenRouter = setting($pdo, 'openrouter_api_key', '');
$curXai = setting($pdo, 'xai_api_key', '');

admin_header('এআই এপিআই কি সেটিংস', 'api_keys');
?>

<?php if ($message): ?>
  <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:12px 18px; margin-bottom:1.5rem; color:#6ee7b7; font-size:0.95rem;">
    ✓ <?= e($message) ?>
  </div>
<?php endif; ?>

<?php if ($testResult !== null): ?>
  <?php if ($testResult['success']): ?>
    <div style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4); border-radius:10px; padding:14px 20px; margin-bottom:1.5rem; color:#6ee7b7; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;">
      <div>
        <strong>✓ এআই কানেকশন সফল ও সুপার-ফাস্ট!</strong>
        <div style="font-size:0.85rem; color:#a7f3d0; margin-top:2px;">রেসপন্স সময়: <strong><?= $testResult['time_ms'] ?>ms</strong> • এআই রিপ্লাই: "<?= e($testResult['reply']) ?>"</div>
      </div>
      <span class="admin-badge badge-success" style="font-size:0.85rem;">Status: ONLINE & HEALTHY</span>
    </div>
  <?php else: ?>
    <div style="background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.4); border-radius:10px; padding:14px 20px; margin-bottom:1.5rem; color:#fda4af;">
      <strong>⚠️ এআই টেস্ট ফেইলড:</strong>
      <div style="font-size:0.88rem; color:#fecdd3; margin-top:4px;"><?= e($testResult['error']) ?></div>
    </div>
  <?php endif; ?>
<?php endif; ?>

<!-- Explainer Card -->
<div class="admin-card" style="margin-bottom: 2rem; border-left:4px solid #a855f7;">
  <h3 style="margin-top:0; font-size:1.15rem; color:#f8fafc; display:flex; align-items:center; gap:8px;">
    <span>🧠</span> <span>আমাদের এআই ইঞ্জিন ও অটো-রোলেভার সিস্টেম</span>
  </h3>
  <p style="color:#94a3b8; font-size:0.92rem; line-height:1.6; margin-bottom:0.75rem;">
    আপনার ওয়েবসাইটের কাস্টমার সাপোর্ট এজেন্ট (আয়েশা, তানিয়া ও নীরব) এই এপিআই কি-এর মাধ্যমে সরাসরি কাস্টমারদের সাথে বাংলায় কথা বলে এবং প্যাকেজ বিক্রি করতে সাহায্য করে।
  </p>
  <p style="color:#cbd5e1; font-size:0.85rem; margin-bottom:0;">
    💡 <strong>টিপস:</strong> আপনি <strong>Google AI Studio (aistudio.google.com)</strong> অথবা <strong>Groq Cloud (console.groq.com)</strong> থেকে সম্পূর্ণ ফ্রিতে এপিআই কি তৈরি করে এখানে যুক্ত করতে পারেন।
  </p>
</div>

<div style="display:grid; grid-template-columns: 1fr 340px; gap: 1.5rem; align-items: start;">
  
  <!-- Form to Edit Keys -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>🔑</span>
        <span>এআই এপিআই কি কনফিগারেশন</span>
      </div>
    </div>

    <form method="post" class="admin-form">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="save">

      <div class="form-group">
        <label class="form-label">
          <span>Google Gemini API Key</span>
          <span style="color:#10b981; font-size:0.75rem;">(প্রস্তাবিত — সুপার ফাস্ট ও সম্পূর্ণ ফ্রি)</span>
        </label>
        <input type="password" name="gemini_api_key" class="form-input" value="<?= e($curGemini) ?>" placeholder="AIzaSy..." style="letter-spacing:1px;">
        <small style="color:#64748b; font-size:0.75rem;">Google AI Studio থেকে পাওয়া Gemini 2.5 Flash / Flash Lite Key।</small>
      </div>

      <div class="form-group">
        <label class="form-label">
          <span>Groq API Key (বিকল্প ব্যাকআপ)</span>
          <span style="color:#38bdf8; font-size:0.75rem;">(অতি দ্রুত গতিসম্পন্ন Llama 3)</span>
        </label>
        <input type="password" name="groq_api_key" class="form-input" value="<?= e($curGroq) ?>" placeholder="gsk_..." style="letter-spacing:1px;">
        <small style="color:#64748b; font-size:0.75rem;">Groq এর মাধ্যমে 800+ tokens/sec গতিতে Llama 3 দিয়ে রিপ্লাই দেয়।</small>
      </div>

      <div class="form-group">
        <label class="form-label">
          <span>OpenRouter API Key (ঐচ্ছিক ব্যাকআপ)</span>
        </label>
        <input type="password" name="openrouter_api_key" class="form-input" value="<?= e($curOpenRouter) ?>" placeholder="sk-or-v1-..." style="letter-spacing:1px;">
        <small style="color:#64748b; font-size:0.75rem;">DeepSeek বা Claude 3.5 Sonnet ব্যবহারের জন্য।</small>
      </div>

      <div class="form-group">
        <label class="form-label">
          <span>xAI (Grok) API Key (ঐচ্ছিক)</span>
        </label>
        <input type="password" name="xai_api_key" class="form-input" value="<?= e($curXai) ?>" placeholder="xai-..." style="letter-spacing:1px;">
      </div>

      <div style="margin-top:1.5rem;">
        <button type="submit" class="btn-admin btn-admin-primary" style="padding:10px 22px; font-size:0.95rem;">
          <span>💾</span> <span>এপিআই কি সংরক্ষণ করুন</span>
        </button>
      </div>
    </form>
  </div>

  <!-- Test AI Live Card -->
  <div class="admin-card">
    <div class="card-header">
      <div class="card-title">
        <span>⚡</span>
        <span>লাইভ টেস্ট ডায়াগনস্টিক</span>
      </div>
    </div>

    <p style="color:#94a3b8; font-size:0.85rem; line-height:1.5; margin-bottom:1.25rem;">
      আপনার সেভ করা এপিআই কি সঠিকভাবে কাজ করছে কিনা এবং এআই এজেন্টদের সার্ভার অনলাইনে আছে কিনা তা ১ ক্লিকে টেস্ট করুন।
    </p>

    <form method="post">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="test_ai">
      <button type="submit" class="btn-admin" style="width:100%; justify-content:center; padding:12px; background:linear-gradient(135deg, #0284c7, #0369a1); color:#fff; font-weight:700; border-radius:8px;">
        <span>🚀</span> <span>এআই কানেকশন টেস্ট করুন</span>
      </button>
    </form>

    <div style="margin-top:1.5rem; padding:12px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:8px;">
      <div style="font-size:0.8rem; color:#94a3b8; margin-bottom:6px;">সিস্টেম মেকানিক্স:</div>
      <div style="font-size:0.75rem; color:#64748b; line-height:1.5;">
        • যদি কখনো কোনো একটি এপিআই কি-তে কোটা শেষ হয়, আমাদের সিস্টেম স্বয়ংক্রিয়ভাবে পরবর্তী ব্যাকআপ কি-তে রোটেট করে। ফলে ওয়েবসাইট কখনোই ডাউন হয় না।
      </div>
    </div>
  </div>

</div>

<?php admin_footer(); ?>
