<?php
declare(strict_types=1);

require_once __DIR__ . '/whatsapp.php';

function ensure_drip_sequence_tables(PDO $pdo): void
{
    $driver = (string) $pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
    $isSqlite = ($driver === 'sqlite');

    // 1. drip_campaigns
    $pdo->exec($isSqlite ? "
        CREATE TABLE IF NOT EXISTS drip_campaigns (
            id VARCHAR(64) PRIMARY KEY,
            campaign_key VARCHAR(64) UNIQUE NOT NULL,
            title VARCHAR(160) NOT NULL,
            trigger_type VARCHAR(64) NOT NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )" : "
        CREATE TABLE IF NOT EXISTS drip_campaigns (
            id VARCHAR(64) PRIMARY KEY,
            campaign_key VARCHAR(64) UNIQUE NOT NULL,
            title VARCHAR(160) NOT NULL,
            trigger_type VARCHAR(64) NOT NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    );

    // 2. drip_steps (Stages: 1 to 6)
    $pdo->exec($isSqlite ? "
        CREATE TABLE IF NOT EXISTS drip_steps (
            id VARCHAR(64) PRIMARY KEY,
            campaign_id VARCHAR(64) NOT NULL,
            step_number INT NOT NULL,
            delay_hours INT NOT NULL,
            stage_name VARCHAR(80) NOT NULL,
            message_template TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, step_number)
        )" : "
        CREATE TABLE IF NOT EXISTS drip_steps (
            id VARCHAR(64) PRIMARY KEY,
            campaign_id VARCHAR(64) NOT NULL,
            step_number INT NOT NULL,
            delay_hours INT NOT NULL,
            stage_name VARCHAR(80) NOT NULL,
            message_template TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY camp_step (campaign_id, step_number)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    );

    // 3. drip_subscribers (Tracks lead progression through the 6 stages)
    $pdo->exec($isSqlite ? "
        CREATE TABLE IF NOT EXISTS drip_subscribers (
            id VARCHAR(64) PRIMARY KEY,
            campaign_id VARCHAR(64) NOT NULL,
            phone VARCHAR(32) NOT NULL,
            name VARCHAR(120) NOT NULL,
            target_package VARCHAR(64) DEFAULT 'video_studio',
            current_step INT NOT NULL DEFAULT 0,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            enrolled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_drip_sent_at DATETIME NULL,
            last_customer_reply_at DATETIME NULL,
            next_drip_at DATETIME NOT NULL,
            metadata_json TEXT NULL
        )" : "
        CREATE TABLE IF NOT EXISTS drip_subscribers (
            id VARCHAR(64) PRIMARY KEY,
            campaign_id VARCHAR(64) NOT NULL,
            phone VARCHAR(32) NOT NULL,
            name VARCHAR(120) NOT NULL,
            target_package VARCHAR(64) DEFAULT 'video_studio',
            current_step INT NOT NULL DEFAULT 0,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            enrolled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_drip_sent_at DATETIME NULL,
            last_customer_reply_at DATETIME NULL,
            next_drip_at DATETIME NOT NULL,
            metadata_json TEXT NULL,
            INDEX idx_drip_sched (status, next_drip_at),
            INDEX idx_phone (phone)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    );

    // 4. drip_logs
    $pdo->exec($isSqlite ? "
        CREATE TABLE IF NOT EXISTS drip_logs (
            id VARCHAR(64) PRIMARY KEY,
            subscriber_id VARCHAR(64) NOT NULL,
            step_number INT NOT NULL,
            phone VARCHAR(32) NOT NULL,
            rendered_message TEXT NOT NULL,
            dispatch_status VARCHAR(32) NOT NULL,
            account_used VARCHAR(64) NULL,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )" : "
        CREATE TABLE IF NOT EXISTS drip_logs (
            id VARCHAR(64) PRIMARY KEY,
            subscriber_id VARCHAR(64) NOT NULL,
            step_number INT NOT NULL,
            phone VARCHAR(32) NOT NULL,
            rendered_message TEXT NOT NULL,
            dispatch_status VARCHAR(32) NOT NULL,
            account_used VARCHAR(64) NULL,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_sub (subscriber_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    );

    // 5. Ensure whatsapp_leads has last_customer_reply_at
    try {
        $pdo->exec("ALTER TABLE whatsapp_leads ADD COLUMN last_customer_reply_at DATETIME NULL");
    } catch (\Throwable $e) {}
}

function seed_default_drip_campaign(PDO $pdo): void
{
    $campId = 'camp_abandoned_lead_v1';
    $stCheck = $pdo->prepare("SELECT id FROM drip_campaigns WHERE id = ? LIMIT 1");
    $stCheck->execute([$campId]);
    if ($stCheck->fetch()) {
        return;
    }

    $pdo->prepare("
        INSERT INTO drip_campaigns (id, campaign_key, title, trigger_type, is_active)
        VALUES (?, 'abandoned_lead_v1', 'Multi-Day Unconverted & Abandoned Follow-Up', 'unconverted_inquiry', 1)
    ")->execute([$campId]);

    $steps = [
        [
            'step' => 1,
            'delay' => 24, // Day 1
            'name' => 'Curiosity & Empathy Hook',
            'template' => "{আসসালামু আলাইকুম|শুভ অপরাহ্ন} {name}! {আশা করি ভালো আছেন|কেমন আছেন ভাই}? 🌸\n\n{গতকাল|কিছুক্ষণ আগে} আপনি AutoMovie Pro-এর {package} প্যাকেজটি {দেখেছিলেন|সম্পর্কে জানতে চেয়েছিলেন}।\n\n{ভিডিও বানাতে গিয়ে বা কনটেন্ট নিয়ে কি কোনো জায়গায় আটকে গেছেন|পিসির কনফিগারেশন নিয়ে কি কোনো প্রশ্ন আছে}? {আমাদের টিম আপনাকে সম্পূর্ণ ফ্রিতে সহযোগিতা করতে প্রস্তুত|কোনো দ্বিধা ছাড়াই আমাকে জানান, আমি হেল্প করছি}।\n\n{সফটওয়্যারটির ১-ক্লিক ভিডিও তৈরির একটি ডেমো কি হোয়াটসঅ্যাপে শেয়ার করব|আপনি কি একটি লাইভ ডেমো ভিডিও দেখতে চান}? 😊"
        ],
        [
            'step' => 2,
            'delay' => 48, // Day 2
            'name' => 'Case Study & Social Proof',
            'template' => "{আসসালামু আলাইকুম|হ্যালো} {name} ভাই! 🎬\n\n{অনেকেই ভাবেন|অনেকেরই কমন প্রশ্ন থাকে}—\"ক্যামেরার সামনে না এসে বা ভয়েস না দিয়ে কি সত্যিই চ্যানেল মনিটাইজ করা সম্ভব?\"\n\n{একটি বাস্তব উদাহরণ শেয়ার করি|আমাদের একজন নিয়মিত ব্যবহারকারীর কথা বলি}—রংপুরের তানভীর ভাই, যিনি গত মাসে AutoMovie Pro দিয়ে প্রতিদিন মাত্র ১৫ মিনিটে ২০টি হিস্ট্রি রিলস বানিয়েছেন। কোনো এডিটিং অভিজ্ঞতা ছাড়াই তার পেজের ভিউ ৩.৫ লাখ ছাড়িয়েছে এবং মনিটাইজেশনের দ্বারপ্রান্তে! 🚀\n\n👉 {প্যাকেজের বিস্তারিত ও রিভিউ দেখতে এখানে ভিজিট করুন|অফিশিয়াল ডেমো ও বিস্তারিত তথ্য দেখুন}:\n{link}\n\n{কোন ক্যাটাগরির ভিডিও বানাতে চান আমাকে জানাতে পারেন, আমি আইডিয়া দিচ্ছি|আপনার পরিকল্পনা আমাকে জানাতে পারেন}।"
        ],
        [
            'step' => 3,
            'delay' => 72, // Day 3
            'name' => 'Objection Crusher',
            'template' => "{আসসালামু আলাইকুম|শুভ সকাল} {name}! 💻\n\n{সফটওয়্যারটি ব্যবহারের আগে অনেকের মনে এই ৩টি প্রশ্ন আসে|নতুন ইউজারদের মনে কিছু কমন প্রশ্ন থাকে}:\n\n১. {ভারী কম্পিউটার বা গ্রাফিক্স কার্ড লাগবে|দামি পিসি লাগবে}?\n👉 {একদমই না! সাধারণ Core i3/i5 এবং মাত্র 4GB RAM থাকলেই অনায়াসে ফুল 4K ভিডিও রেন্ডার হবে।|কোনো GPU দরকার নেই।}\n\n২. {এডিটিং শিখতে হবে|কোনো এডিটিং অভিজ্ঞতা লাগবে}?\n👉 {না! সফটওয়্যারটি নিজেই স্ক্রিপ্ট, ভয়েস, সাবটাইটেল ও ব্যাকগ্রাউন্ড ফুটেজ স্বয়ংক্রিয়ভাবে জোড়া লাগিয়ে ভিডিও তৈরি করে।|১০০% স্বয়ংক্রিয় এআই ইঞ্জিন।}\n\n৩. {অনেক সময় নষ্ট হবে|সারাদিন বসে থাকতে হবে}?\n👉 {মাত্র ৫ মিনিটে আপনার কাজ শেষ!|বাকি কাজ সফটওয়্যার নিজে করবে।}\n\n{আপনার পিসির স্পেসিফিকেশন আমাকে জানালে আমি চেক করে দিচ্ছি|যেকোনো সহায়তায় আমরা এনিডেস্ক দিয়ে সেটআপ করে দিতে প্রস্তুত}। 🤝"
        ],
        [
            'step' => 4,
            'delay' => 120, // Day 5
            'name' => 'Urgency Flash (VIP500 Voucher)',
            'template' => "{বিশেষ বিজ্ঞপ্তি|জরুরি অফার আপডেট} {name}! ⏳\n\n{আপনার আগ্রহের প্রতি সম্মান জানিয়ে|আপনার জন্য বিশেষভাবে} আমাদের ম্যানেজমেন্ট থেকে একটি **{coupon}** কুপন কোড রিজার্ভ রাখা হয়েছিল, যার মাধ্যমে আপনি {package}-এ সরাসরি **৳৫০০ ইনস্ট্যান্ট ছাড়** পাচ্ছেন ({price}-এর বদলে মাত্র {offer_price})! 🎁\n\n⚠️ {তবে কুপনটির মেয়াদ আজ রাত ১২টায় শেষ হচ্ছে|আজকের পর স্পেশাল কনসেশনটি স্বয়ংক্রিয়ভাবে এক্সপায়ার হয়ে যাবে}।\n\n👉 {link}?coupon={coupon}\n\n{আমি কি কুপনটি আপনার নামে লক করে রাখব|পেমেন্ট সংক্রান্ত তথ্যে আমাকে রিপ্লাই দিতে পারেন}?"
        ],
        [
            'step' => 5,
            'delay' => 168, // Day 7
            'name' => 'Chris Voss Breakup Message',
            'template' => "{আসসালামু আলাইকুম|শ্রদ্ধেয়} {name}।\n\n{মনে হচ্ছে এখন হয়তো আপনার জন্য AutoMovie Pro শুরু করার উপযুক্ত সময় নয়|হয়তো আপনি অন্য কাজে ব্যস্ত আছেন}, আর তাই আমি আপনাকে বারবার মেসেজ দিয়ে বিরক্ত করতে চাই না। 🌿\n\n{আপনার অনুমতি নিয়ে আমরা আপনার ফাইল ও পেন্ডিং ডিসকাউন্ট স্লটটি ক্লোজ করছি|সিস্টেম থেকে আপনার রিজার্ভেশনটি অবমুক্ত করে দিচ্ছি যাতে অন্য ক্রিয়েটর সুযোগটি পান}।\n\n{ভবিষ্যতে যেকোনো প্রয়োজনে আমাদের দরজা খোলা থাকবে|পরবর্তীতে কনটেন্ট অটোমেশনে প্রয়োজন হলে ভিজিট করতে পারেন}:\n🌐 {link}\n\n{আপনার সর্বাঙ্গীন সাফল্য ও সুস্বাস্থ্য কামনা করছি|ভালো থাকবেন, শুভকামনা রইল}। ধন্যবাদ! 🙏"
        ],
        [
            'step' => 6,
            'delay' => 336, // Day 14
            'name' => 'Cold Lead Reactivation',
            'template' => "{আসসালামু আলাইকুম|হ্যালো} {name} ভাই! অনেক দিন পর আপনাকে নক করছি। আশা করি চমৎকার আছেন। ✨\n\n{আপনাকে একটি দারুণ আপডেট দিতে চাচ্ছি|আমাদের সিস্টেমে বড় টেকনিক্যাল মাইলফলক এসেছে}—AutoMovie Pro-এর সম্পূর্ণ নতুন **v4.6 হাই-স্পিড টার্বো ইঞ্জিন** রিলিজ হয়েছে! 🚀\n\n{প্রধান আপডেট}:\n• {আল্ট্রা-ফাস্ট ৪K রেন্ডারিং স্পিড (৩ গুণ দ্রুততর)|হাই-স্পিড ক্লাউড-লোকাল হাইব্রিড রেন্ডারার}\n• {বাংলা ও ইংরেজি ভাষার মানুষের মতো ন্যাচারাল নিউরাল এআই ভয়েস|স্বচ্ছ ও নিখুঁত ভয়েসওভার}\n• {রিলস ও শর্টসের ১-ক্লিক ভাইরাল ক্যাপশন জেনারেটর|স্মার্ট অটো-পোস্টিং}\n\n{নতুন ভার্সনের ১ মিনিটের ডেমো ভিডিও দেখতে চাইলে আমাকে 'DEMO' লিখে পাঠান, আমি পাঠিয়ে দিচ্ছি|আপনি কি নতুন ফিচারের একটি দ্রুত ভিডিও দেখতে চান}? 😊"
        ]
    ];

    $insStep = $pdo->prepare("
        INSERT INTO drip_steps (id, campaign_id, step_number, delay_hours, stage_name, message_template)
        VALUES (?, ?, ?, ?, ?, ?)
    ");

    foreach ($steps as $s) {
        $stepId = 'dstep_' . $s['step'] . '_' . bin2hex(random_bytes(4));
        $insStep->execute([$stepId, $campId, $s['step'], $s['delay'], $s['name'], $s['template']]);
    }
}

class AmpDripEngine
{
    public static function enrollSubscriber(
        PDO $pdo,
        string $phone,
        string $name,
        string $campaignKey = 'abandoned_lead_v1',
        string $targetPackage = 'video_studio',
        array $metadata = []
    ): bool {
        $cleanPhone = whatsapp_clean_phone($phone, true);
        if (strlen($cleanPhone) < 10) {
            return false;
        }

        if (self::hasPurchased($pdo, $cleanPhone)) {
            return false;
        }

        if (self::isOptedOut($pdo, $cleanPhone)) {
            return false;
        }

        $stCamp = $pdo->prepare("SELECT id FROM drip_campaigns WHERE campaign_key = ? AND is_active = 1 LIMIT 1");
        $stCamp->execute([$campaignKey]);
        $campId = $stCamp->fetchColumn();
        if (!$campId) {
            return false;
        }

        $stSub = $pdo->prepare("SELECT id, status FROM drip_subscribers WHERE campaign_id = ? AND phone = ? LIMIT 1");
        $stSub->execute([$campId, $cleanPhone]);
        $existing = $stSub->fetch(PDO::FETCH_ASSOC);

        $now = date('Y-m-d H:i:s');
        $firstStepAt = date('Y-m-d H:i:s', time() + (24 * 3600));

        if ($existing) {
            if (in_array($existing['status'], ['completed', 'converted', 'opted_out'], true)) {
                return false;
            }
            return true;
        }

        $subId = 'sub_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
        $ins = $pdo->prepare("
            INSERT INTO drip_subscribers (id, campaign_id, phone, name, target_package, current_step, status, enrolled_at, next_drip_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, 0, 'active', ?, ?, ?)
        ");
        return $ins->execute([
            $subId,
            $campId,
            $cleanPhone,
            $name ?: 'সম্মানিত গ্রাহক',
            $targetPackage,
            $now,
            $firstStepAt,
            json_encode($metadata, JSON_UNESCAPED_UNICODE)
        ]);
    }

    public static function recordCustomerReply(PDO $pdo, string $phone, string $message): void
    {
        $clean = whatsapp_clean_phone($phone, true);
        $now = date('Y-m-d H:i:s');

        try {
            $pdo->prepare("UPDATE whatsapp_leads SET last_customer_reply_at = ? WHERE clean_phone = ?")->execute([$now, $clean]);
        } catch (\Throwable $e) {}

        if (whatsapp_detect_opt_out_intent($message)) {
            whatsapp_handle_opt_out($pdo, $clean, 'Keyword Opt-Out: ' . mb_substr($message, 0, 50));
            $pdo->prepare("UPDATE drip_subscribers SET status = 'opted_out' WHERE phone = ?")->execute([$clean]);
            return;
        }

        $pdo->prepare("UPDATE drip_subscribers SET last_customer_reply_at = ?, status = 'paused' WHERE phone = ? AND status = 'active'")
            ->execute([$now, $clean]);
    }

    public static function hasPurchased(PDO $pdo, string $cleanPhone): bool
    {
        $st = $pdo->prepare("
            SELECT COUNT(*) FROM orders 
            WHERE status IN ('approved', 'active') 
              AND (REPLACE(whatsapp, '+', '') = ? OR REPLACE(whatsapp, '+', '') = ?)
        ");
        $normNoPlus = ltrim($cleanPhone, '+');
        $normWith88 = str_starts_with($normNoPlus, '880') ? $normNoPlus : ('880' . ltrim($normNoPlus, '0'));
        $st->execute([$normNoPlus, $normWith88]);
        return ((int) $st->fetchColumn()) > 0;
    }

    public static function isOptedOut(PDO $pdo, string $cleanPhone): bool
    {
        $st1 = $pdo->prepare("SELECT COUNT(*) FROM suppression_records WHERE phone = ? OR phone = ?");
        $st1->execute([$cleanPhone, '+' . $cleanPhone]);
        if (((int) $st1->fetchColumn()) > 0) return true;

        $st2 = $pdo->prepare("SELECT COUNT(*) FROM contacts WHERE (phone = ? OR phone = ?) AND consent_status = 'opted_out'");
        $st2->execute([$cleanPhone, '+' . $cleanPhone]);
        return ((int) $st2->fetchColumn()) > 0;
    }

    public static function processDueDrips(PDO $pdo, array $config, int $batchLimit = 15): array
    {
        $now = date('Y-m-d H:i:s');
        $processed = 0;
        $skipped = 0;
        $completed = 0;

        // Respectful business hours guard (09:00 - 22:00)
        if (!whatsapp_is_within_business_hours()) {
            return ['processed' => 0, 'skipped' => 0, 'completed' => 0, 'reason' => 'outside_business_hours'];
        }

        $st = $pdo->prepare("
            SELECT s.*, c.campaign_key 
            FROM drip_subscribers s
            JOIN drip_campaigns c ON s.campaign_id = c.id
            WHERE s.status = 'active' AND s.next_drip_at <= ? AND c.is_active = 1
            ORDER BY s.next_drip_at ASC
            LIMIT ?
        ");
        $st->bindValue(1, $now);
        $st->bindValue(2, $batchLimit, PDO::PARAM_INT);
        $st->execute();
        $dueSubs = $st->fetchAll(PDO::FETCH_ASSOC);

        foreach ($dueSubs as $sub) {
            $phone = (string) $sub['phone'];
            $subId = (string) $sub['id'];
            $currentStep = (int) $sub['current_step'];
            $nextStepNum = $currentStep + 1;

            if (self::hasPurchased($pdo, $phone)) {
                $pdo->prepare("UPDATE drip_subscribers SET status = 'converted' WHERE id = ?")->execute([$subId]);
                $skipped++;
                continue;
            }

            if (self::isOptedOut($pdo, $phone)) {
                $pdo->prepare("UPDATE drip_subscribers SET status = 'opted_out' WHERE id = ?")->execute([$subId]);
                $skipped++;
                continue;
            }

            if (!empty($sub['last_customer_reply_at'])) {
                $replyTime = strtotime($sub['last_customer_reply_at']);
                if ((time() - $replyTime) < (12 * 3600)) {
                    $postponed = date('Y-m-d H:i:s', time() + (24 * 3600));
                    $pdo->prepare("UPDATE drip_subscribers SET next_drip_at = ? WHERE id = ?")->execute([$postponed, $subId]);
                    $skipped++;
                    continue;
                }
            }

            // Frequency cap: Ensure at least 48h since any previous sent broadcast
            if (!whatsapp_check_recipient_frequency_cap($pdo, $phone, 48)) {
                $postponed = date('Y-m-d H:i:s', time() + (24 * 3600));
                $pdo->prepare("UPDATE drip_subscribers SET next_drip_at = ? WHERE id = ?")->execute([$postponed, $subId]);
                $skipped++;
                continue;
            }

            $stStep = $pdo->prepare("SELECT * FROM drip_steps WHERE campaign_id = ? AND step_number = ? LIMIT 1");
            $stStep->execute([$sub['campaign_id'], $nextStepNum]);
            $step = $stStep->fetch(PDO::FETCH_ASSOC);

            if (!$step) {
                $pdo->prepare("UPDATE drip_subscribers SET status = 'completed' WHERE id = ?")->execute([$subId]);
                $completed++;
                continue;
            }

            $tokenData = [
                'name' => $sub['name'],
                'phone' => '+' . $phone,
                'package' => $sub['target_package'] === 'video_studio' ? 'AutoMovie Pro 4K Video Studio' : ($sub['target_package'] === 'fb_business' ? 'Facebook Business & Ads Engine' : 'AutoMovie Pro'),
                'price' => '৳৩,৯৯৯',
                'offer_price' => '৳৩,৪৯৯',
                'coupon' => 'VIP500',
                'link' => 'https://automoviepro.com/order.php',
            ];
            $messageText = whatsapp_render_message((string) $step['message_template'], $tokenData);

            $disp = whatsapp_antiban_dispatch($pdo, $config, $phone, $messageText, 'normal', 'drip_step_' . $nextStepNum);

            $logId = 'dlog_' . round(microtime(true) * 1000) . '_' . mt_rand(100, 999);
            $stLog = $pdo->prepare("INSERT INTO drip_logs (id, subscriber_id, step_number, phone, rendered_message, dispatch_status, account_used, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)");
            $stLog->execute([
                $logId,
                $subId,
                $nextStepNum,
                $phone,
                $messageText,
                !empty($disp['success']) ? 'sent' : 'queued',
                $disp['account_used'] ?? 'primary',
                $now
            ]);

            $stNext = $pdo->prepare("SELECT delay_hours FROM drip_steps WHERE campaign_id = ? AND step_number = ? LIMIT 1");
            $stNext->execute([$sub['campaign_id'], $nextStepNum + 1]);
            $nextDelay = $stNext->fetchColumn();

            if ($nextDelay !== false) {
                $nextHours = (int) $nextDelay;
                $enrolledTime = strtotime($sub['enrolled_at']);
                $nextDripTime = date('Y-m-d H:i:s', $enrolledTime + ($nextHours * 3600));
                
                $pdo->prepare("UPDATE drip_subscribers SET current_step = ?, last_drip_sent_at = ?, next_drip_at = ? WHERE id = ?")
                    ->execute([$nextStepNum, $now, $nextDripTime, $subId]);
            } else {
                $pdo->prepare("UPDATE drip_subscribers SET current_step = ?, last_drip_sent_at = ?, status = 'completed' WHERE id = ?")
                    ->execute([$nextStepNum, $now, $subId]);
                $completed++;
            }

            $processed++;
        }

        return [
            'processed' => $processed,
            'skipped' => $skipped,
            'completed' => $completed
        ];
    }
}
