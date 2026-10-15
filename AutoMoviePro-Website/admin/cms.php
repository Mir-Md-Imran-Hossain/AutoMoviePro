<?php
declare(strict_types=1);
require dirname(__DIR__) . '/includes/bootstrap.php';
require __DIR__ . '/_layout.php';
require_admin();

$i18nKeys = [
    'hero_brand' => 'ব্র্যান্ড নাম',
    'hero_tagline' => 'হিরো ট্যাগলাইন',
    'hero_cta' => 'CTA বাটন টেক্সট',
    'price_label' => 'প্রাইস লেবেল',
    'payment_instructions' => 'পেমেন্ট ইনস্ট্রাকশন',
    'how_it_works' => 'কীভাবে কাজ করে (CMS)',
    'features_text' => 'অতিরিক্ত ফিচার টেক্সট',
    'faq_text' => 'FAQ (অতিরিক্ত)',
    'meta_title' => 'SEO Title',
    'meta_description' => 'SEO Description',
];

$globalKeys = [
    'price_amount' => 'কোর প্রাইস (৳) — ডিফল্ট 2998',
    'language_addon_price' => 'অতিরিক্ত ভাষা প্রাইস (৳) — ডিফল্ট 499',
    'whatsapp_number' => 'সেলস WhatsApp (লিংক-অনলি; সাইটে নম্বর দেখাবে না)',
];

$editLang = strtolower(substr((string) ($_GET['lang'] ?? 'bn'), 0, 2));
if (!in_array($editLang, amp_cms_langs(), true)) {
    $editLang = 'bn';
}

$flash = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && csrf_verify($_POST['csrf'] ?? null)) {
    $action = (string) ($_POST['action'] ?? 'save');

    if ($action === 'save_global') {
        foreach ($globalKeys as $k => $_) {
            if (isset($_POST[$k])) {
                $val = (string) $_POST[$k];
                if ($k === 'whatsapp_number') {
                    $val = preg_replace('/\D+/', '', $val) ?: '8801968111593';
                }
                set_setting($pdo, $k, $val);
            }
        }
        $flash = 'গ্লোবাল সেটিংস সেভ হয়েছে';
    }

    if ($action === 'save_i18n') {
        $srcLang = strtolower(substr((string) ($_POST['edit_lang'] ?? 'bn'), 0, 2));
        $propagate = !empty($_POST['propagate']);
        $overwrite = !empty($_POST['overwrite']);
        foreach ($i18nKeys as $k => $_) {
            if (!isset($_POST[$k])) {
                continue;
            }
            $val = (string) $_POST[$k];
            if ($propagate) {
                amp_cms_propagate_translate($pdo, $k, $srcLang, $val, $overwrite);
            } else {
                set_setting_i18n($pdo, $k, $srcLang, $val);
            }
        }
        $flash = $propagate
            ? 'কনটেন্ট সেভ + অন্য ভাষায় অটো অনুবাদ/সিঙ্ক হয়েছে'
            : 'এই ভাষার কনটেন্ট সেভ হয়েছে';
        $editLang = $srcLang;
    }

    if ($action === 'upload_feature_image') {
        $fname = basename((string) ($_POST['image_name'] ?? ''));
        if ($fname !== '' && preg_match('/^feat-[\w\-]+\.png$/i', $fname) && isset($_FILES['image']) && is_uploaded_file($_FILES['image']['tmp_name'])) {
            $dir = dirname(__DIR__) . '/assets/img';
            if (!is_dir($dir)) {
                mkdir($dir, 0755, true);
            }
            $dest = $dir . '/' . $fname;
            if (move_uploaded_file($_FILES['image']['tmp_name'], $dest)) {
                $flash = 'ইমেজ আপডেট: ' . $fname;
            } else {
                $flash = 'আপলোড ব্যর্থ';
            }
        } else {
            $flash = 'অবৈধ ইমেজ নাম বা ফাইল';
        }
    }

    redirect('/admin/cms.php?lang=' . rawurlencode($editLang) . '&saved=1&msg=' . rawurlencode($flash));
}

admin_header('ওয়েবসাইট CMS', 'cms');
if (!empty($_GET['saved'])): ?>
  <p class="ok"><?= e((string) ($_GET['msg'] ?? 'সেভ হয়েছে')) ?></p>
<?php endif; ?>

<p class="lead" style="max-width:52rem">
  ভাষা বেছে এডিট করুন। <strong>অন্য ভাষায় অটো সিঙ্ক</strong> চালু থাকলে এক ভাষায় সেভ করলে বাকি ভাষা MyMemory দিয়ে আপডেট হয় (খালি থাকলে;Overwrite দিলে সব ওভাররাইট)।
  WhatsApp নম্বর শুধু <code>wa.me</code> লিংকে ব্যবহার হয় — পাবলিক পেজে নম্বর দেখানো হয় না।
</p>

<div class="lang-tabs" style="display:flex;flex-wrap:wrap;gap:0.4rem;margin:1rem 0">
  <?php foreach (amp_cms_langs() as $lc): ?>
    <a class="btn btn-sm <?= $lc === $editLang ? '' : 'btn-ghost' ?>" href="?lang=<?= e($lc) ?>"><?= e(strtoupper($lc)) ?></a>
  <?php endforeach; ?>
</div>

<h3>গ্লোবাল (সব ভাষা)</h3>
<form method="post" class="admin-form stack" style="max-width:640px;margin-bottom:2rem">
  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
  <input type="hidden" name="action" value="save_global">
  <?php foreach ($globalKeys as $k => $label): ?>
    <label><?= e($label) ?>
      <input name="<?= e($k) ?>" value="<?= e(setting($pdo, $k, $k === 'price_amount' ? '3999' : ($k === 'language_addon_price' ? '499' : '8801968111593'))) ?>">
    </label>
  <?php endforeach; ?>
  <button class="btn" type="submit">গ্লোবাল সেভ</button>
</form>

<h3>কনটেন্ট — <?= e(strtoupper($editLang)) ?></h3>
<form method="post" class="admin-form stack" style="max-width:640px;margin-bottom:2rem">
  <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
  <input type="hidden" name="action" value="save_i18n">
  <input type="hidden" name="edit_lang" value="<?= e($editLang) ?>">
  <?php foreach ($i18nKeys as $k => $label): ?>
    <label><?= e($label) ?>
      <?php
        $val = setting_i18n($pdo, $k, $editLang, setting($pdo, $k, '')) ?? '';
        $long = in_array($k, ['payment_instructions', 'how_it_works', 'features_text', 'faq_text', 'meta_description', 'hero_tagline'], true);
      ?>
      <?php if ($long): ?>
        <textarea name="<?= e($k) ?>"><?= e($val) ?></textarea>
      <?php else: ?>
        <input name="<?= e($k) ?>" value="<?= e($val) ?>">
      <?php endif; ?>
    </label>
  <?php endforeach; ?>
  <label style="display:flex;align-items:center;gap:0.5rem;color:var(--ink)">
    <input type="checkbox" name="propagate" value="1" checked style="width:auto">
    অন্য ৫ ভাষায় অটো অনুবাদ / সিঙ্ক করুন
  </label>
  <label style="display:flex;align-items:center;gap:0.5rem;color:var(--ink)">
    <input type="checkbox" name="overwrite" value="1" style="width:auto">
    আগে থেকে থাকা অনুবাদ ওভাররাইট করুন
  </label>
  <button class="btn" type="submit">এই ভাষা সেভ (+ সিঙ্ক)</button>
</form>

<h3>ফিচার ইমেজ রিপ্লেস</h3>
<p class="lead">প্লেসহোল্ডার ইমেজ পরে এখান থেকে বদলাতে পারবেন। ফাইল নাম একই রাখুন।</p>
<div class="stack" style="max-width:720px">
  <?php foreach (amp_features_catalog() as $feat):
      $img = (string) ($feat['image'] ?? '');
      if ($img === '') {
          continue;
      }
      $f = amp_feature_for_lang($feat, 'en');
      $src = '/assets/img/' . rawurlencode($img);
      ?>
    <form method="post" enctype="multipart/form-data" class="admin-form" style="display:grid;grid-template-columns:120px 1fr;gap:0.75rem;align-items:center;border:1px solid var(--line);padding:0.75rem;border-radius:0.5rem">
      <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
      <input type="hidden" name="action" value="upload_feature_image">
      <input type="hidden" name="image_name" value="<?= e($img) ?>">
      <img src="<?= e($src) ?>?t=<?= time() ?>" alt="" width="120" height="68" style="object-fit:cover;border-radius:0.3rem;background:#111">
      <div>
        <strong><?= e($f['title']) ?></strong>
        <div style="font-size:0.8rem;color:var(--muted)"><?= e($img) ?></div>
        <input type="file" name="image" accept="image/png,image/jpeg,image/webp" required>
        <button class="btn btn-sm" type="submit" style="margin-top:0.4rem">আপলোড / রিপ্লেস</button>
      </div>
    </form>
  <?php endforeach; ?>
</div>
<?php admin_footer(); ?>
