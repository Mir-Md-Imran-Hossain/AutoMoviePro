<?php
declare(strict_types=1);

/**
 * Shared payment methods block for landing / order / pending pages.
 * Fully supports Zahid Pharmacy / Simi Drug House cashout agents, Rocket, and Binance QR.
 */
function amp_payment_account_name(): string
{
    return 'Mir Md Imran Hossain';
}

function amp_payment_bkash_nagad_personal(): string
{
    return '01717820998';
}

function amp_payment_bkash_agent(): string
{
    return '01756160993 (Zahid Pharmacy)';
}

function amp_payment_nagad_agent(): string
{
    return '01611-824811 (Simi Drug House)';
}

function amp_payment_rocket_agent(): string
{
    return '01756160993-5';
}

function amp_default_payment_instructions_text(): string
{
    $name = amp_payment_account_name();
    $personal = amp_payment_bkash_nagad_personal();
    $bkAgent = amp_payment_bkash_agent();
    $ngAgent = amp_payment_nagad_agent();
    $rkAgent = amp_payment_rocket_agent();
    return <<<TXT
বাংলাদেশ (শুধু ক্যাশ আউট):
বিকাশ এজেন্ট: {$bkAgent}
নগদ এজেন্ট: {$ngAgent}
রকেট এজেন্ট: {$rkAgent}

বিদেশ (India/Pakistan/Worldwide):
Wise / Remitly / Xoom দিয়ে ৳২৯৯৯ বা ৳৯৯৯ + ক্যাশ-আউট/ট্রানজেকশন ফি মিলিয়ে পাঠান।
অথবা Binance Pay-তে \$16 USD বা \$26 USD (সব ৬টি ভাষা) পাঠান।

Personal bKash/Nagad: {$personal}
Account Name: {$name}

DBBL: {$name} | 1491510213367 | Manikganj | Routing 090560613 | SWIFT DBBLBDDH
Southeast Bank: {$name} | 12100002919 | Ghior | Routing 205560374 | SWIFT SEBDBDDH

Binance Pay: QR স্ক্যান করে ChatEarly Ai অ্যাকাউন্টে পেমেন্ট করুন।
পেমেন্টের পর Transaction ID ও লাস্ট ৩ ডিজিট ওয়েবসাইটে সাবমিট করুন — তৎক্ষণাৎ ১-ক্লিক সফটওয়্যার ডাউনলোড এবং লগইন পাবেন।
TXT;
}

function amp_render_payment_section(string $context = 'landing'): void
{
    $name = amp_payment_account_name();
    $personal = amp_payment_bkash_nagad_personal();
    $bkAgent = amp_payment_bkash_agent();
    $ngAgent = amp_payment_nagad_agent();
    $rkAgent = amp_payment_rocket_agent();
    $qr = '/assets/img/binance-pay-qr.png';
    ?>
  <div class="pay-grid">
    <article class="pay-card">
      <h3 data-i18n="pay_bd_title">বাংলাদেশ থেকে পেমেন্ট (ক্যাশ আউট)</h3>
      <p class="pay-note" data-i18n="pay_bd_note">শুধুমাত্র অনুমোদিত এজেন্ট নম্বরে <strong>ক্যাশ আউট</strong> করুন:</p>
      <ul class="pay-list">
        <li><span>বিকাশ এজেন্ট</span>: <strong><?= e($bkAgent) ?></strong></li>
        <li><span>নগদ এজেন্ট</span>: <strong><?= e($ngAgent) ?></strong></li>
        <li><span>রকেট এজেন্ট</span>: <strong><?= e($rkAgent) ?></strong></li>
      </ul>
      <p class="pay-hint" style="font-size:0.85rem; color:#64748b; margin-top:0.5rem;">
        *পেমেন্ট করার সময় রেফারেন্সে আপনার মোবাইল নম্বরের শেষ ৪ ডিজিট লিখুন।
      </p>
    </article>

    <article class="pay-card">
      <h3 data-i18n="pay_abroad_title">How to Pay from Abroad (International)</h3>
      <div class="pay-abroad">
        <p data-i18n="pay_abroad_apps">Use <strong>Wise.com</strong>, <strong>Remitly</strong> or <strong>Xoom</strong> app.</p>
        <p data-i18n="pay_abroad_amount">Send <strong>$16 USD</strong> (Core Package) or <strong>$26 USD</strong> (Full 6 Languages Unlimited) to:</p>
        <ul class="pay-list">
          <li>bKash / Nagad (Personal): <strong><?= e($personal) ?></strong></li>
          <li>Account Name: <strong><?= e($name) ?></strong></li>
        </ul>
        <p class="pay-note">Instant 1-click download link and login credentials unlocked upon verification.</p>
      </div>

      <details class="pay-banks" style="margin-top:0.75rem;">
        <summary data-i18n="pay_bank_summary">Bank Transfer Details</summary>
        <div class="pay-bank">
          <h4>Dutch Bangla Bank Limited (DBBL)</h4>
          <ul class="pay-list">
            <li>Ac. Name: <?= e($name) ?></li>
            <li>Ac. Number: <strong>1491510213367</strong></li>
            <li>Branch: Manikganj | Routing: 090560613</li>
          </ul>
        </div>
      </details>
    </article>

    <article class="pay-card pay-binance">
      <h3 data-i18n="pay_binance_title">Pay with Binance (USDT/Crypto)</h3>
      <p class="pay-note" data-i18n="pay_binance_note">Scan with Binance App — Payee: <strong>ChatEarly Ai</strong></p>
      <img class="binance-qr" src="<?= e($qr) ?>" alt="Binance Pay QR — ChatEarly Ai" width="280" height="380" loading="lazy" style="border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.1);">
    </article>
  </div>
    <?php
}
