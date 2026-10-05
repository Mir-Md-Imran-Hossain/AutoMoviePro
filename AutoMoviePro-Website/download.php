<?php
/**
 * Optional customer download page after payment approval.
 * Login with site credentials not required if they have the WhatsApp link;
 * this page also shows the current public installer URL.
 */
declare(strict_types=1);
require __DIR__ . '/includes/bootstrap.php';
require __DIR__ . '/includes/release_service.php';

$rel = amp_current_release($pdo);
$url = amp_release_public_url($config);
$version = $rel ? (string) $rel['version'] : 'latest';
?><!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ডাউনলোড — AutoMovie Pro</title>
  <link rel="stylesheet" href="/assets/css/site.css">
  <link rel="icon" type="image/png" href="/assets/img/logo.png">
</head>
<body>
  <main class="wrap" style="max-width:640px;margin:3rem auto;padding:1.5rem">
    <h1>AutoMovie Pro ডাউনলোড</h1>
    <p>পেমেন্ট অনুমোদনের পর এই বাটন থেকে সফটওয়্যার ডাউনলোড করুন। আলাদা স্টোরেজ লাগে না — ফাইল আমাদের ওয়েবসাইট সার্ভারেই থাকে।</p>
    <p>বর্তমান ভার্সন: <strong><?= htmlspecialchars($version, ENT_QUOTES, 'UTF-8') ?></strong></p>
    <p><a class="btn" href="<?= htmlspecialchars($url, ENT_QUOTES, 'UTF-8') ?>">ডাউনলোড করুন</a></p>
    <p class="muted">ইনস্টলের পর ওয়েবসাইটের লগইন দিয়ে অ্যাপে ঢুকুন। পরে নতুন ভার্সন এলে অ্যাপে ২৪ ঘণ্টার নোটিফিকেশন আসবে — আপডেটে আপনার ডাটা থাকবে।</p>
  </main>
</body>
</html>
