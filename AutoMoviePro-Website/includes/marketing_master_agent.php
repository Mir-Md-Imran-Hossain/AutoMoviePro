<?php
declare(strict_types=1);

/**
 * =============================================================================
 * AutoMovie Pro - Central Master Marketing AI Agent (চিফ মার্কেটিং ও সাইকোলজি ডিরেক্টর এআই)
 * =============================================================================
 * High-performance central marketing intelligence that oversees the entire customer
 * acquisition, psychological profiling, nurturing, in-chat order taking, and conversion lifecycle.
 * 
 * Embedded Elite Persuasion & Direct-Response Frameworks:
 * - Eugene Schwartz: 5 Stages of Customer Awareness (Unaware -> Problem Aware -> Solution Aware -> Product Aware -> Most Aware)
 * - Psychological Archetype Profiling: Skeptic Analyst, Budget Conscious, Passionate Creator, Busy Merchant, Hesitant Shopper
 * - Buying Temperature Matrix (0 - 100 Readiness Score)
 * - Robert Cialdini: 6 Principles of Influence (Reciprocity, Commitment, Social Proof, Authority, Liking, Scarcity)
 * - Alex Hormozi: $100M Offers, Value Stacking, and Margin Shield (Discount is strictly the LAST RESORT)
 * - Chris Voss: Tactical Empathy & Black Swan Negotiation (Emotional Labeling, Mirroring, Calibrated Questions)
 * - Russell Brunson: Hook-Story-Offer & Epiphany Bridge
 * - Direct In-Chat Order Processing: Automatic Order Registration & Receipt Generation
 * - Lifecycle Cross-Sell, Upsell & Strict Anti-Nagging Guard
 * =============================================================================
 */

require_once __DIR__ . '/agent_llm.php';

class MarketingMasterBrain
{
    // Awareness Stages (Eugene Schwartz)
    public const STAGE_UNAWARE = 'unaware';
    public const STAGE_PROBLEM_AWARE = 'problem_aware';
    public const STAGE_SOLUTION_AWARE = 'solution_aware';
    public const STAGE_PRODUCT_AWARE = 'product_aware';
    public const STAGE_MOST_AWARE = 'most_aware';

    // Psychological Archetypes
    public const ARCHETYPE_SKEPTIC = 'skeptic_analyst';
    public const ARCHETYPE_BUDGET = 'budget_conscious';
    public const ARCHETYPE_CREATOR = 'passionate_creator';
    public const ARCHETYPE_MERCHANT = 'busy_merchant';
    public const ARCHETYPE_HESITANT = 'hesitant_shopper';

    // Frontline Specialist Personas
    public const AGENT_DIRECTOR = 'master_director';
    public const AGENT_AYESHA = 'ayesha';
    public const AGENT_NIROB = 'nirob';
    public const AGENT_TANIA = 'tania';

    /**
     * Detect Eugene Schwartz 5 Stages of Awareness from conversation context.
     */
    public static function detectAwarenessStage(string $input, array $history = []): string
    {
        $text = mb_strtolower(trim($input));
        $fullContext = $text;
        foreach ($history as $h) {
            $msg = is_array($h) ? ($h['text'] ?? $h['content'] ?? '') : (string) $h;
            $fullContext .= ' ' . mb_strtolower($msg);
        }

        // Stage 5: Most Aware (Ready to buy, asking for bKash/Nagad number, TxnID, discount, how to pay)
        if (preg_match('/(কেনার নিয়ম|অর্ডার করব|অর্ডার করতে চাই|টাকা পাঠাব|বিকাশ|নগদ|রকেট|পেমেন্ট|ট্রানজেকশন|ক্যাশ আউট|অর্ডার লিংক|অ্যাকাউন্ট নম্বর|payment|bkash|nagad|checkout|trx|trnx)/u', $text)) {
            return self::STAGE_MOST_AWARE;
        }

        // Stage 4: Product Aware (Asking about specific packages, 3999 vs 2999 vs 1999 vs 999, features)
        if (preg_match('/(৩,৯৯৯|৩৯৯৯|২,৯৯৯|২৯৯৯|১,৯৯৯|১৯৯৯|৯৯৯|প্যাকেজ|ফিচার|ভিডিও স্টুডিও|মেটা বিজনেস|প্রোফাইল পোস্ট|wamanager|দাম কত|প্রাইস|লাইসেন্স কি|পার্থক্য কি|কোনটা ভালো)/u', $text)) {
            return self::STAGE_PRODUCT_AWARE;
        }

        // Stage 3: Solution Aware (Comparing solutions or asking how automation works)
        if (preg_match('/(কিভাবে কাজ করে|স্বয়ংক্রিয়|অটোমেশন|এআই দিয়ে|ভিডিও তৈরি|বাল্ক মেসেজ|গ্রুপ থেকে নম্বর|চ্যানেল গ্রোথ|প্যাসিভ ইনকাম|ইউটিউব অটোমেশন|সফটওয়্যার কি|how it works|automation)/u', $text)) {
            return self::STAGE_SOLUTION_AWARE;
        }

        // Stage 2: Problem Aware (Suffering from manual editing, time loss, number bans, low views)
        if (preg_match('/(সময় পাই না|এডিটিং পারি না|ভিডিও বানাতে কষ্ট|নম্বর ব্যান|ভিউ হয় না|ফলোয়ার বাড়ে না|টাকা নষ্ট|কষ্ট হচ্ছে|এডিটর পাচ্ছি না|সমস্যা|ব্যর্থ)/u', $text)) {
            return self::STAGE_PROBLEM_AWARE;
        }

        // Stage 1: Unaware (Casual greeting, hello, hi, just exploring)
        return self::STAGE_UNAWARE;
    }

    /**
     * Detect Customer Psychological Archetype from message and context.
     */
    public static function detectArchetype(string $input, array $history = []): string
    {
        $text = mb_strtolower(trim($input));
        $blob = $text;
        foreach ($history as $h) {
            $msg = is_array($h) ? ($h['text'] ?? $h['content'] ?? '') : (string) $h;
            $blob .= ' ' . mb_strtolower($msg);
        }

        // 1. Skeptic Analyst (Doubts, scam fears, proof, guarantee, address, virus, safety)
        if (preg_match('/(ভুয়া|প্রতারণা|আসলেই কি|প্রমাণ কি|গ্যারান্টি|ঠিকানা কি|অফিস কোথায়|ব্যান হবে|টাকা মার যাবে|বিশ্বাস|প্রমাণ আছে|রিস্ক|সেফ|ভাইরাস|লিক|হ্যাকিং|প্রাইভেসি)/u', $blob)) {
            return self::ARCHETYPE_SKEPTIC;
        }

        // 2. Budget Conscious (Price objection, discount request, budget tight, "pore nibo")
        if (preg_match('/(দাম বেশি|টাকা কম|টাকা নাই|টাকা শর্ট|বাজেট|সাধ্য নাই|ডিসকাউন্ট|ছাড়|কম রাখবেন|পরে নিব|অফার|কুপন|কম রাখা|স্টুডেন্ট|গরিব)/u', $blob)) {
            return self::ARCHETYPE_BUDGET;
        }

        // 3. Passionate Creator (YouTube, Facebook reels, TikTok, Islamic, tech, storytelling)
        if (preg_match('/(ইউটিউব|ফেসবুক রিলস|রিলস|ইসলামিক ভিডিও|কনটেন্ট|প্যাসিভ ইনকাম|ভিউ বাড়াতে|হাদিস|মোটিভেশনাল|চ্যানেল|শর্টস|ভিডিও বানাই|মনিটাইজ)/u', $blob)) {
            return self::ARCHETYPE_CREATOR;
        }

        // 4. Busy Merchant (Shop owner, e-commerce, product sales, ads, messenger reply)
        if (preg_match('/(অনলাইন শপ|ব্যবসা|বিজনেস|ই-কমার্স|কমার্স|পণ্য|প্রোডাক্ট|বিজ্ঞাপন|অ্যাড|গ্রাহক|কাস্টমার|মেসেঞ্জার|অর্ডার বৃদ্ধি|সেলস|পেজ চালাই|দোকান)/u', $blob)) {
            return self::ARCHETYPE_MERCHANT;
        }

        // 5. Hesitant Shopper (General browsing, "dehi", "pore janabo", greetings)
        return self::ARCHETYPE_HESITANT;
    }

    /**
     * Master Customer Psychology & Profile Analysis.
     * Evaluates Archetype, Temperature, Owned Products, Anti-Nagging Guard, Compliments, and Discount Gatekeeper.
     */
    public static function analyzeCustomerPsychology(
        PDO $pdo,
        string $visitorId,
        string $input,
        array $history,
        array $visitorProfile = []
    ): array {
        $text = mb_strtolower(trim($input));
        $stage = self::detectAwarenessStage($input, $history);
        $archetype = self::detectArchetype($input, $history);

        // Fetch or initialize psychology record
        $psych = null;
        try {
            $stmt = $pdo->prepare("SELECT * FROM customer_psychology_profiles WHERE visitor_id = ? LIMIT 1");
            $stmt->execute([$visitorId]);
            $psych = $stmt->fetch(PDO::FETCH_ASSOC);
        } catch (\Throwable $e) {}

        $isReturningVisitor = !empty($psych) || !empty($visitorProfile['is_returning']);
        $turnsCount = (int) ($psych['turns_count'] ?? 0) + 1;
        $discountAskedCount = (int) ($psych['discount_attempts_asked'] ?? 0);
        if (preg_match('/(ডিসকাউন্ট|ছাড়|কম|কুপন|অফার|দাম বেশি|কম রাখা যায় না|পরে নিব|বাজেট|টাকা নাই|টাকা কম|টাকা শর্ট|সাধ্য নাই|discount|coupon)/u', $text)) {
            $discountAskedCount++;
        }

        // Extract Customer Phone & Name if available
        $customerPhone = $psych['customer_phone'] ?? ($visitorProfile['customer_phone'] ?? null);
        $customerName = $psych['customer_name'] ?? ($visitorProfile['customer_name'] ?? null);
        $customerEmail = $psych['customer_email'] ?? null;

        if (preg_match('/(?:\+?8801|01)[3-9]\d{8}/', $input, $pm)) {
            $rawP = preg_replace('/\D+/', '', $pm[0]);
            $customerPhone = str_starts_with($rawP, '8801') ? substr($rawP, 2) : (str_starts_with($rawP, '01') ? $rawP : $rawP);
        }

        // ---------------------------------------------------------------------
        // 1. Calculate Buying Temperature (0 to 100)
        // ---------------------------------------------------------------------
        $temp = (int) ($psych['buying_temperature'] ?? 15);
        $temp = max(15, min(100, $temp + 5)); // Base incremental interest
        if ($stage === self::STAGE_PROBLEM_AWARE) $temp = max($temp, 35);
        if ($stage === self::STAGE_SOLUTION_AWARE) $temp = max($temp, 50);
        if ($stage === self::STAGE_PRODUCT_AWARE) $temp = max($temp, 70);
        if ($stage === self::STAGE_MOST_AWARE) $temp = max($temp, 90);
        if ($customerPhone) $temp = max($temp, 85);
        if (preg_match('/(বিকাশ|নগদ|টাকা পাঠাব|অর্ডার করব|পেমেন্ট|payment|bkash)/u', $text)) $temp = max($temp, 95);

        // ---------------------------------------------------------------------
        // 2. Check Customer Existing Purchases & Anti-Nagging Guard
        // ---------------------------------------------------------------------
        $purchasedProducts = [];
        $doNotNagProducts = [];
        try {
            $ownedSql = "SELECT plan_name, status FROM orders WHERE status IN ('approved', 'pending_payment') AND (whatsapp = ? OR (customer_id IS NOT NULL AND customer_id IN (SELECT id FROM customers WHERE whatsapp = ?)))";
            $ownedStmt = $pdo->prepare($ownedSql);
            $cleanPhone = $customerPhone ? preg_replace('/\D+/', '', $customerPhone) : '0000000000';
            $ownedStmt->execute([$cleanPhone, $cleanPhone]);
            $ownedRows = $ownedStmt->fetchAll(PDO::FETCH_ASSOC);

            foreach ($ownedRows as $orow) {
                $pName = mb_strtolower($orow['plan_name'] ?? '');
                if (str_contains($pName, 'video') || str_contains($pName, 'social media') || str_contains($pName, '৩,৯৯৯')) {
                    $purchasedProducts[] = 'video_studio';
                    $doNotNagProducts[] = 'video_studio';
                } elseif (str_contains($pName, 'business') || str_contains($pName, 'ad') || str_contains($pName, '২,৯৯৯')) {
                    $purchasedProducts[] = 'fb_business';
                    $doNotNagProducts[] = 'fb_business';
                } elseif (str_contains($pName, 'profile') || str_contains($pName, 'page post') || str_contains($pName, '১,৯৯৯')) {
                    $purchasedProducts[] = 'profile_page';
                    $doNotNagProducts[] = 'profile_page';
                } elseif (str_contains($pName, 'wamanager') || str_contains($pName, 'whatsapp') || str_contains($pName, 'crm')) {
                    $purchasedProducts[] = 'wa_marketing';
                    $doNotNagProducts[] = 'wa_marketing';
                } elseif (str_contains($pName, 'gemini') || str_contains($pName, 'google')) {
                    $purchasedProducts[] = 'google_pro';
                    $doNotNagProducts[] = 'google_pro';
                }
            }
        } catch (\Throwable $e) {}

        $purchasedProducts = array_values(array_unique($purchasedProducts));
        $doNotNagProducts = array_values(array_unique($doNotNagProducts));

        // Calculate Recommended Next Upsell / Cross-Sell (Lifecycle Intelligence)
        $recommendedNext = 'video_studio';
        if (in_array('video_studio', $purchasedProducts, true)) {
            $recommendedNext = in_array('wa_marketing', $purchasedProducts, true) ? 'extra_language' : 'wa_marketing';
        } elseif (in_array('fb_business', $purchasedProducts, true)) {
            $recommendedNext = 'video_studio';
        } elseif (in_array('profile_page', $purchasedProducts, true)) {
            $recommendedNext = 'fb_business';
        } elseif (in_array('wa_marketing', $purchasedProducts, true)) {
            $recommendedNext = 'video_studio';
        }

        // ---------------------------------------------------------------------
        // 3. Dignified Authentic Compliment Selection (Anti-Repetition)
        // ---------------------------------------------------------------------
        $complimentsGiven = [];
        if (!empty($psych['compliments_given'])) {
            $complimentsGiven = json_decode($psych['compliments_given'], true) ?: [];
        }

        $complimentBank = [
            self::ARCHETYPE_CREATOR => [
                'c_creat_1' => "মাশাল্লাহ স্যার, কনটেন্ট তৈরি করে নিজস্ব স্থায়ী অডিয়েন্স গড়ে তোলার আপনার এই ভাবনাটি সত্যিই দূরদর্শী ও প্রশংসনীয়।",
                'c_creat_2' => "সোশ্যাল মিডিয়া থেকে প্যাসিভ ইনকাম তৈরি করার জন্য আপনি একদম পারফেক্ট সময়ে সিদ্ধান্ত নিচ্ছেন স্যার, সঠিক টুল থাকলে আপনার সময় ও শ্রম শতভাগ সফল হবে।",
                'c_creat_3' => "আপনার মতো সৃজনশীল ও কাজের প্রতি সিরিয়াস মানুষের সাথে কথা বলতে পেরে আমাদের টিম আনন্দিত বোধ করছে স্যার।"
            ],
            self::ARCHETYPE_MERCHANT => [
                'c_merch_1' => "নিজের ব্যবসাকে আধুনিক এআই অটোমেশনের আওতায় নিয়ে আসার আপনার এই পদক্ষেপটি একজন সফল আধুনিক উদ্যোক্তার সুস্পষ্ট লক্ষণ স্যার।",
                'c_merch_2' => "প্রতিদিন বিজ্ঞাপনের খরচ ও সময় বাঁচিয়ে স্বয়ংক্রিয় সেলস বৃদ্ধি করার আপনার কৌশলটি দারুণ কার্যকর হবে স্যার।",
                'c_merch_3' => "উদ্যোক্তা হিসেবে প্রতিটি বিষয় পুঙ্খানুপুঙ্খভাবে জেনে নেওয়া আপনার ব্যবসায়িক দূরদর্শিতার প্রমাণ দেয় স্যার।"
            ],
            self::ARCHETYPE_SKEPTIC => [
                'c_skep_1' => "প্রোডাক্টের কার্যকারিতা ও নিরাপত্তা নিখুঁতভাবে যাচাই করে সিদ্ধান্ত নেওয়া একজন সচেতন ও প্রজ্ঞাবান ব্যক্তির বৈশিষ্ট্য স্যার; আপনার এই বিচক্ষণতাটি আমার খুব ভালো লেগেছে।",
                'c_skep_2' => "কোনো কিছুতে চূড়ান্ত বিনিয়োগের আগে তার নির্ভরযোগ্যতা ও স্বচ্ছতা দেখে নেওয়া আপনার অর্থের সঠিক ব্যবহার নিশ্চিত করে স্যার।"
            ],
            self::ARCHETYPE_BUDGET => [
                'c_budg_1' => "বাজেট সঠিকভাবে সমন্বয় করে প্রতিটি টাকার সর্বোচ্চ আউটপুট নিশ্চিত করার আপনার এই সচেতনতাটি সত্যিই প্রশংসনীয় স্যার।",
                'c_budg_2' => "একটি সফটওয়্যার থেকে দীর্ঘমেয়াদে কতটা আর্থিক রিটার্ন আসবে তা হিসাব করে দেখা আপনার পরিপক্ক চিন্তার পরিচায়ক স্যার।"
            ],
            self::ARCHETYPE_HESITANT => [
                'c_hesi_1' => "আপনার সাথে কথা বলে খুব ভালো লাগছে স্যার; আপনি সময় নিয়ে নিখুঁতভাবে বুঝে নেওয়ার যে ধৈর্য দেখাচ্ছেন তা প্রশংসার যোগ্য।",
                'c_hesi_2' => "ধন্যবাদ স্যার, আপনার যেকোনো জিজ্ঞাসায় আপনাকে নির্ভুল তথ্য দিয়ে সহযোগিতা করতে পেরে আমরা অত্যন্ত আনন্দিত।"
            ]
        ];

        $selectedCompliment = null;
        $avail = $complimentBank[$archetype] ?? $complimentBank[self::ARCHETYPE_HESITANT];
        foreach ($avail as $cKey => $cText) {
            if (!in_array($cKey, $complimentsGiven, true)) {
                $selectedCompliment = ['key' => $cKey, 'text' => $cText];
                $complimentsGiven[] = $cKey;
                break;
            }
        }

        // Check if Server Upgrade & Migration Mode is Active (Default '0' - Disabled for live selling)
        $serverUpgradeMode = setting($pdo, 'agent_server_upgrade_mode', '0') === '1';

        // ---------------------------------------------------------------------
        // 4. Discount Gatekeeper & Margin Shield (Hormozi & Voss Model)
        // ---------------------------------------------------------------------
        $discountAllowed = setting($pdo, 'agent_discount_allowed', '1') === '1';
        $minTurns = (int) setting($pdo, 'agent_discount_min_turns', '3');
        $initDiscount = (float) setting($pdo, 'agent_initial_discount_amount', '500');
        $maxDiscount = (float) setting($pdo, 'agent_max_discount_amount', '1000');
        $couponCode = strtoupper(trim(setting($pdo, 'agent_coupon_prefix', 'VIP500')) ?: 'VIP500');
        $freeAddon = setting($pdo, 'agent_free_addon_lang', '1') === '1';

        $discountStatus = 'NOT_REQUESTED';
        $discountAuthorizedAmount = 0.0;
        $authorizedCoupon = null;
        $offerAddonGift = false;
        $discountDirective = "";

        if ($serverUpgradeMode) {
            $discountStatus = 'SERVER_UPGRADE_PAUSE';
            $discountDirective = "CRITICAL DIRECTIVE - SERVER UPGRADE & 1-WEEK ONBOARDING PAUSE: AutoMovie Pro is currently undergoing a massive technical update and cloud video rendering server migration. The engineering team requires 1 week to complete setup. NO NEW PURCHASES OR ORDERS ARE PERMITTED FOR THE NEXT 7 DAYS. IF THE CUSTOMER ASKS TO BUY/ORDER/PAY: Explain the server shift politely, explain that onboarding is paused for 1 week for server stability, and enthusiastically offer to add their WhatsApp number to the VIP Priority Waitlist so our team will contact them with a priority welcome package the moment the server is live. IF THE CUSTOMER ASKS ABOUT SOFTWARE FEATURES: Fully and thoroughly explain all features, tools, capabilities, and benefits with maximum excitement and detail, without taking immediate money.";
        } elseif (!$discountAllowed) {
            $discountStatus = 'DISCOUNTS_DISABLED';
            $discountDirective = "DISCOUNTS DISABLED: Admin has disabled cash discounts. Reiterate lifetime license value, zero monthly fees, and free lifetime updates.";
        } else {
            $isAskingDiscount = (bool) preg_match('/(ডিসকাউন্ট|ছাড়|কম|কুপন|অফার|দাম বেশি|কম রাখা যায় না|পরে নিব|বাজেট|টাকা নাই|টাকা কম|টাকা শর্ট|সাধ্য নাই|discount|coupon)/u', $text);

            if (!$isAskingDiscount && $turnsCount < 4) {
                $discountStatus = 'VALUE_BUILDING';
                $discountDirective = "PHASE 1 (VALUE FIRST): Customer has not pushed for discount. DO NOT offer any discount or coupon. Build immense value on Dream Outcome and time-saving.";
            } elseif ($isAskingDiscount && $turnsCount < $minTurns) {
                // User asked too early (Turn 1 or 2): STRICTLY DENY DISCOUNT
                $discountStatus = 'DENIED_TOO_EARLY';
                $discountDirective = "DISCOUNT GATEKEEPER STRICT RULE: Customer asked for discount or said 'pore nibo' on Turn {$turnsCount}. STRICTLY DO NOT GIVE CASH DISCOUNT. Explain politely that this is an all-inclusive lifetime license that saves ৳10,000+ monthly editor costs. Build value first!";
            } elseif ($isAskingDiscount && $turnsCount >= $minTurns && $turnsCount < 5) {
                // Turn 3-4: Offer Free Addon Language instead of losing money!
                $discountStatus = 'OFFER_ADDON_GIFT';
                $offerAddonGift = true;
                $discountDirective = "DISCOUNT GATEKEEPER TACTIC: Protect cash margin! Instead of cash discount, offer 1 FREE international language expansion pack (worth ৳৪৯৯) as an exclusive closing gift if they order today.";
            } elseif ($isAskingDiscount && ($turnsCount >= 5 || $discountAskedCount >= 2)) {
                // Turn 5+ or persistent objection: Authorize Micro-Discount as genuine final closer
                $discountStatus = 'AUTHORIZED_MICRO';
                $discountAuthorizedAmount = $initDiscount;
                $authorizedCoupon = $couponCode;
                $discountDirective = "DISCOUNT GATEKEEPER AUTHORIZATION: The customer is deeply qualified and at risk of leaving. You are authorized to unlock Secret Coupon Code [{$couponCode}] for an instant ৳" . (int)$initDiscount . " discount, emphasizing that this is a special one-time concession reserved strictly for them today.";
            }
        }

        // ---------------------------------------------------------------------
        // 5. In-Chat Direct Order / Waitlist State Machine
        // ---------------------------------------------------------------------
        $inChatOrderState = $psych['in_chat_order_state'] ?? 'idle';
        $pendingOrderDraft = !empty($psych['pending_order_draft']) ? json_decode($psych['pending_order_draft'], true) : [];
        $orderCreated = false;
        $orderReceipt = null;

        if ($serverUpgradeMode) {
            // When Server Upgrade Mode is active, NO MONEY/TrxID IS ACCEPTED!
            // All purchase intents and phone numbers are captured into the VIP Priority Waitlist.
            if ($customerPhone && $inChatOrderState !== 'waitlist_registered') {
                $inChatOrderState = 'waitlist_registered';
                // Automatically queue a VIP Priority Waitlist confirmation message in WhatsApp
                $waitlistMsg = "আসসালামু আলাইকুম " . ($customerName ?: 'স্যার') . "! AutoMovie Pro-এর প্রি-লঞ্চ প্রায়োরিটি ওয়েটিং লিস্টে যুক্ত হওয়ার জন্য আন্তরিক ধন্যবাদ। আমাদের হাই-স্পিড ভিডিও সার্ভার আপগ্রেড ও ক্লাউড মাইগ্রেশন সম্পন্ন হওয়া মাত্রই আগামী এক সপ্তাহের মধ্যে আমাদের টিম আপনার সাথে যোগাযোগ করে বিশেষ রি-লঞ্চ অফারে সফটওয়্যারটি বুঝিয়ে দেবে। 🚀";
                try {
                    whatsapp_queue($pdo, $GLOBALS['config'] ?? [], $customerPhone, $waitlistMsg, null);
                } catch (\Throwable $e) {}
            }
        } else {
            // Check for Transaction ID in message
            if (preg_match('/(?:trx|txn|trnx|id|ট্রানজেকশন|আইডি)?[:\s-]*([A-Z0-9]{8,14})\b/iu', $input, $trxMatch)) {
                $potentialTrx = strtoupper(trim($trxMatch[1]));
                // Exclude common words
                if (!in_array($potentialTrx, ['AUTOMOVIE', 'WHATSAPP', 'YOUTUBE', 'FACEBOOK', 'DISCOUNT'], true)) {
                    $pendingOrderDraft['txn_id'] = $potentialTrx;
                    $inChatOrderState = 'awaiting_confirmation';

                    // If phone is also known, auto-register order!
                    if ($customerPhone) {
                        $orderRes = self::createInChatOrder($pdo, [
                            'visitor_id' => $visitorId,
                            'name' => $customerName ?: 'ওয়েবসাইট লাইভ চ্যাট গ্রাহক',
                            'phone' => $customerPhone,
                            'email' => $customerEmail,
                            'product_type' => $pendingOrderDraft['product_type'] ?? ($recommendedNext ?: 'video_studio'),
                            'amount' => (float) ($pendingOrderDraft['amount'] ?? 3999),
                            'txn_id' => $potentialTrx,
                            'payment_method' => $pendingOrderDraft['payment_method'] ?? 'bKash/Nagad Agent',
                            'agent_id' => $psych['assigned_agent_id'] ?? 'nirob',
                            'coupon_used' => $authorizedCoupon,
                            'discount_amount' => $discountAuthorizedAmount
                        ]);

                        if ($orderRes['ok']) {
                            $orderCreated = true;
                            $orderReceipt = $orderRes;
                            $inChatOrderState = 'order_completed';
                        }
                    }
                }
            }
        }

        // ---------------------------------------------------------------------
        // 6. Persist or Update Customer Psychology Profile in Database
        // ---------------------------------------------------------------------
        $now = date('Y-m-d H:i:s');
        try {
            if ($psych) {
                $upd = $pdo->prepare(
                    "UPDATE customer_psychology_profiles 
                     SET psychological_archetype = ?,
                         buying_temperature = ?,
                         conversation_stage = ?,
                         turns_count = ?,
                         discount_attempts_asked = ?,
                         discount_authorized_amount = ?,
                         authorized_coupon_code = ?,
                         compliments_given = ?,
                         purchased_products = ?,
                         do_not_nag_products = ?,
                         recommended_next_product = ?,
                         customer_phone = COALESCE(?, customer_phone),
                         customer_name = COALESCE(?, customer_name),
                         in_chat_order_state = ?,
                         pending_order_draft = ?,
                         last_seen_at = ?
                     WHERE visitor_id = ?"
                );
                $upd->execute([
                    $archetype,
                    $temp,
                    $stage,
                    $turnsCount,
                    $discountAskedCount,
                    $discountAuthorizedAmount,
                    $authorizedCoupon,
                    json_encode($complimentsGiven, JSON_UNESCAPED_UNICODE),
                    json_encode($purchasedProducts, JSON_UNESCAPED_UNICODE),
                    json_encode($doNotNagProducts, JSON_UNESCAPED_UNICODE),
                    $recommendedNext,
                    $customerPhone,
                    $customerName,
                    $inChatOrderState,
                    json_encode($pendingOrderDraft, JSON_UNESCAPED_UNICODE),
                    $now,
                    $visitorId
                ]);
            } else {
                $ins = $pdo->prepare(
                    "INSERT INTO customer_psychology_profiles 
                     (visitor_id, customer_name, customer_phone, psychological_archetype, buying_temperature, conversation_stage, turns_count, discount_attempts_asked, discount_authorized_amount, authorized_coupon_code, compliments_given, purchased_products, do_not_nag_products, recommended_next_product, in_chat_order_state, pending_order_draft, first_seen_at, last_seen_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                );
                $ins->execute([
                    $visitorId,
                    $customerName,
                    $customerPhone,
                    $archetype,
                    $temp,
                    $stage,
                    $turnsCount,
                    $discountAskedCount,
                    $discountAuthorizedAmount,
                    $authorizedCoupon,
                    json_encode($complimentsGiven, JSON_UNESCAPED_UNICODE),
                    json_encode($purchasedProducts, JSON_UNESCAPED_UNICODE),
                    json_encode($doNotNagProducts, JSON_UNESCAPED_UNICODE),
                    $recommendedNext,
                    $inChatOrderState,
                    json_encode($pendingOrderDraft, JSON_UNESCAPED_UNICODE),
                    $now,
                    $now
                ]);
            }
        } catch (\Throwable $e) {}

        return [
            'visitor_id' => $visitorId,
            'archetype' => $archetype,
            'stage' => $stage,
            'temperature' => $temp,
            'turns_count' => $turnsCount,
            'purchased_products' => $purchasedProducts,
            'do_not_nag_products' => $doNotNagProducts,
            'recommended_next' => $recommendedNext,
            'selected_compliment' => $selectedCompliment,
            'discount_status' => $discountStatus,
            'discount_authorized_amount' => $discountAuthorizedAmount,
            'authorized_coupon' => $authorizedCoupon,
            'offer_addon_gift' => $offerAddonGift,
            'discount_directive' => $discountDirective,
            'server_upgrade_mode' => $serverUpgradeMode,
            'in_chat_order_state' => $inChatOrderState,
            'order_created' => $orderCreated,
            'order_receipt' => $orderReceipt,
            'is_returning' => $isReturningVisitor,
            'customer_phone' => $customerPhone,
            'customer_name' => $customerName,
        ];
    }

    /**
     * In-Chat Direct Order Creator.
     * Registers order in SQLite database and creates customer record.
     */
    public static function createInChatOrder(PDO $pdo, array $params): array
    {
        $name = trim((string) ($params['name'] ?? 'ওয়েবসাইট চ্যাট গ্রাহক'));
        $phone = preg_replace('/\D+/', '', (string) ($params['phone'] ?? ''));
        $email = trim((string) ($params['email'] ?? ''));
        $product = strtolower(trim((string) ($params['product_type'] ?? 'video_studio')));
        $txnId = strtoupper(trim((string) ($params['txn_id'] ?? '')));
        $method = trim((string) ($params['payment_method'] ?? 'bKash Agent'));
        $agentId = trim((string) ($params['agent_id'] ?? 'nirob'));
        $coupon = trim((string) ($params['coupon_used'] ?? ''));
        $discount = (float) ($params['discount_amount'] ?? 0);

        if ($phone === '' || $txnId === '') {
            return ['ok' => false, 'error' => 'Phone and TxnID are required.'];
        }

        // Product Pricing Matrix
        $planTitle = 'AutoMovie Pro - Social Media Content Automation Engine (Lifetime)';
        $basePrice = 3999.0;
        if ($product === 'fb_business') {
            $planTitle = 'AutoMovie Pro - FB Business Manager & Ad Automation Engine (Lifetime)';
            $basePrice = 2999.0;
        } elseif ($product === 'profile_page') {
            $planTitle = 'AutoMovie Pro - FB Profile & Page Post Automation Engine (Lifetime)';
            $basePrice = 1999.0;
        } elseif ($product === 'wa_marketing') {
            $planTitle = 'WAManager Pro — Official WhatsApp Marketing & CRM Suite (১ বছর)';
            $basePrice = 999.0;
        }

        $finalAmount = max(0.0, $basePrice - $discount);

        try {
            // Find or create customer
            $cStmt = $pdo->prepare("SELECT id FROM customers WHERE whatsapp = ? LIMIT 1");
            $cStmt->execute([$phone]);
            $customerId = $cStmt->fetchColumn();

            if (!$customerId) {
                $insC = $pdo->prepare("INSERT INTO customers (name, whatsapp, email, status, tier, plan, notes, created_at) VALUES (?, ?, ?, 'pending', ?, ?, 'In-Chat Sales Order', CURRENT_TIMESTAMP)");
                $insC->execute([$name, $phone, $email ?: null, $product, $product]);
                $customerId = (int) $pdo->lastInsertId();
            }

            $framework = $params['closing_framework'] ?? 'hormozi_grand_slam';
            $visitorId = $params['visitor_id'] ?? null;

            // Create Order
            $insO = $pdo->prepare(
                "INSERT INTO orders (customer_id, name, whatsapp, email, plan_name, amount, status, payment_method, txn_id, order_source, agent_id, coupon_used, discount_amount, closing_framework, attribution_visitor_id, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, 'pending_payment', ?, ?, 'chat_agent', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
            );
            $insO->execute([
                $customerId,
                $name,
                $phone,
                $email ?: null,
                $planTitle,
                $finalAmount,
                $method,
                $txnId,
                $agentId,
                $coupon ?: null,
                $discount,
                $framework,
                $visitorId
            ]);
            $orderId = (int) $pdo->lastInsertId();

            // Record Conversion Attribution Telemetry
            try {
                $insTelem = $pdo->prepare(
                    "INSERT INTO conversion_attribution_telemetry (order_id, visitor_id, phone, agent_id, closing_framework, created_at)
                     VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"
                );
                $insTelem->execute([
                    (string) $orderId,
                    $visitorId,
                    $phone,
                    $agentId,
                    $framework
                ]);
            } catch (\Throwable $e) {}

            return [
                'ok' => true,
                'order_id' => $orderId,
                'customer_id' => $customerId,
                'customer_name' => $name,
                'customer_phone' => $phone,
                'plan_name' => $planTitle,
                'amount' => $finalAmount,
                'discount' => $discount,
                'txn_id' => $txnId,
                'status' => 'pending_payment',
                'activation_time' => '৩ থেকে ৫ মিনিটের মধ্যে স্বয়ংক্রিয় সক্রিয় হবে।'
            ];
        } catch (\Throwable $e) {
            return ['ok' => false, 'error' => $e->getMessage()];
        }
    }

    /**
     * Choose the optimal Sub-Agent specialist based on user psychology and intent.
     * Dynamic Persona Handshake Protocol:
     * - Nirob: Technical solutions, hardware, setup, API, 4GB RAM, FFmpeg, Windows
     * - Tania: Closer, deals, discount negotiation, pricing, payment instructions, checkout
     * - Ayesha: Warm welcome, initial onboarding, consultative diagnosis, high-empathy guidance
     */
    public static function routeToSpecialist(string $input, string $stage, string $requested = 'auto'): string
    {
        if (in_array($requested, [self::AGENT_AYESHA, self::AGENT_NIROB, self::AGENT_TANIA, self::AGENT_DIRECTOR], true)) {
            return $requested;
        }

        $text = mb_strtolower(trim($input));

        // Nirob: Technical Specialist (PC specs, Windows, RAM, GPU, API keys, FFmpeg, Chrome locks, Anti-ban tech)
        // CRITICAL FIX: Removed bare '|কি|কী|' which was intercepting normal Bengali sentences!
        if (preg_match('/(কম্পিউটার|ল্যাপটপ|উইন্ডোজ|র‍্যাম|গ্রাফিক্স|কনফিগারেশন|এপিআই\s*কি|এপিআই\s*কী|সেটআপ|ইন্সটল|টেকনিক্যাল|বাগ|সিস্টেম\s*রিকোয়ারমেন্ট|কোডিং|পিসি|ffmpeg|core\s*i[3579]|gpu|windows|spec|install|api\s*key)/iu', $text)) {
            return self::AGENT_NIROB;
        }

        // Tania: Closer & Deal Negotiator (Price, discount, offers, bKash, comparison, objection handling "pore nibo", in-chat checkout)
        // CRITICAL FIX: Removed bare '|টাকা|' to prevent premature sales pushes!
        if ($stage === self::STAGE_MOST_AWARE || preg_match('/(দাম|প্রাইস|মূল্য|কত\s*টাকা|খরচ|প্যাকেজ|ডিসকাউন্ট|ছাড়|অফার|কুপন|বিকাশ|নগদ|রকেট|পেমেন্ট|কেনার\s*নিয়ম|অর্ডার|ক্যাশ\s*আউট|পরে\s*নিব|পরে\s*যোগাযোগ|বাজেট\s*কম|price|cost|discount|coupon|offer|trx)/iu', $text)) {
            return self::AGENT_TANIA;
        }

        // Ayesha: Warm Greeter, Lead Capturer & Consultative Advisor (Welcoming, demos, questions, initial care)
        return self::AGENT_AYESHA;
    }

    /**
     * Detect customer inquiry about human vs robot identity or request to talk to human.
     */
    public static function detectHumanTakeoverIntent(string $input): bool
    {
        $text = mb_strtolower(trim($input));
        return (bool) preg_match('/(মানুষ|মানুষের\s*সাথে|রিয়েল\s*পারসন|লাইভ\s*এজেন্ট|সরাসরি\s*কথা|কাস্টমার\s*কেয়ার|কথা\s*বলতে\s*চাই|ফোন\s*নাম্বার|কল\s*দেন|কল\s*করুন|অফিস|ঠিকানা|কল\s*দিতে\s*পারবেন|call\s*me|human\s*agent|talk\s*to\s*human|real\s*person|রোবট|বট\b|ai\s*কিনা|ai\s*নাকি)/iu', $text);
    }

    /**
     * Check if automated AI responses are temporarily paused for this contact.
     * Always returns false so our 24/7 senior sales consultants never leave customer stranded.
     */
    public static function isAiPausedForContact(PDO $pdo, string $visitorId, string $phone = ''): bool
    {
        return false;
    }

    /**
     * Log human engagement request for CRM records without silencing the active human consultant.
     */
    /**
     * Log human engagement request for CRM records without silencing the active human consultant.
     */
    public static function triggerHumanTakeover(PDO $pdo, string $visitorId, string $phone, string $userMsg): void
    {
        try {
            if ($visitorId !== '') {
                $pdo->prepare("UPDATE customer_psychology_profiles SET human_takeover_requested = 1 WHERE visitor_id = ?")
                    ->execute([$visitorId]);
            }
            if ($phone !== '') {
                $clean = function_exists('whatsapp_clean_phone') ? whatsapp_clean_phone($phone, true) : $phone;
                if (function_exists('whatsapp_save_lead')) {
                    whatsapp_save_lead($pdo, $clean, 'সম্মানিত অতিথি', 'chat', null, null, $userMsg);
                }
            }
        } catch (\Throwable $e) {}
    }

    /**
     * Construct the Master Persuasion Directive for the LLM.
     */
    public static function buildPersuasionSystemPrompt(
        string $channel,
        string $agentRole,
        string $stage,
        array $context = []
    ): string {
        $agentTitle = 'চিফ মার্কেটিং ও সেলস ডিরেক্টর';
        $agentName = 'AutoMovie Pro Master Marketing Brain';
        if ($agentRole === self::AGENT_AYESHA) {
            $agentName = 'আয়েশা (কাস্টমার ওয়েলকাম ও কনসালটেশন ম্যানেজার)';
            $agentTitle = 'Customer Care & Consultation Specialist';
        } elseif ($agentRole === self::AGENT_NIROB) {
            $agentName = 'নীরব (টেকনিক্যাল আর্কিটেক্ট ও প্রোডাক্ট স্পেশালিস্ট)';
            $agentTitle = 'Technical Solutions & Setup Architect';
        } elseif ($agentRole === self::AGENT_TANIA) {
            $agentName = 'তানিয়া (সেলস স্ট্র্যাটেজি ও পেমেন্ট অনবোর্ডিং লিড)';
            $agentTitle = 'Sales Closer & Onboarding Director';
        }

        $archetype = $context['archetype'] ?? self::ARCHETYPE_HESITANT;
        $temperature = (int) ($context['temperature'] ?? 20);
        $doNotNag = (array) ($context['do_not_nag_products'] ?? []);
        $recommendedNext = $context['recommended_next'] ?? 'video_studio';
        $complimentText = $context['compliment_text'] ?? '';
        $discountDirective = $context['discount_directive'] ?? '';

        $doNotNagText = !empty($doNotNag)
            ? "CRITICAL ANTI-NAGGING GUARD (অ্যান্টি-ন্যাগিং গার্ড সক্রিয় - STRICT!):\n- This customer has ALREADY PURCHASED: " . implode(', ', $doNotNag) . ".\n- NEVER pitch, sell, or pester the customer about these already purchased products again!\n- Acknowledge their existing setup and recommend their next logical upgrade: {$recommendedNext}."
            : "";

        $complimentDirective = $complimentText !== ''
            ? "AUTHENTIC COMPLIMENT DIRECTIVE (ESTABLISH IMMEDIATE TRUST):\n- Weave this genuine, sincere praise naturally into your response:\n  \"{$complimentText}\""
            : "";

        $channelDirective = match ($channel) {
            'whatsapp_crm' => "চ্যানেল: WhatsApp Live CRM।\n- মেসেজ হতে হবে পয়েন্ট-টু-পয়েন্ট, অত্যন্ত প্রফেশনাল, মোবাইল ফ্রেন্ডলি ও স্পষ্ট প্যারাগ্রাফে বিভক্ত।",
            'social_media' => "চ্যানেল: Facebook / Social Media Comments।\n- কমেন্ট হবে সংক্ষেপ, কৌতূহলোদ্দীপক এবং সোশ্যাল প্রুফ সমৃদ্ধ।",
            default => "চ্যানেল: Website Live Chat (ওয়েবসাইট লাইভ চ্যাট)।\n- উষ্ণ, আন্তরিক এবং সরাসরি সাহায্যকারী টোনে কথা বলুন।"
        };

        return <<<PROMPT
You are {$agentName}, the {$agentTitle} of AutoMovie Pro (https://automoviepro.com).
Your mission is to guide visitors with highest empathy, elite consultative psychology, and convert them into enthusiastic lifelong customers.

CUSTOMER PSYCHOLOGICAL PROFILE:
- Archetype: {$archetype}
- Buying Readiness Temperature: {$temperature}/100
- Awareness Stage: {$stage}

{$doNotNagText}

{$complimentDirective}

{$discountDirective}

{$channelDirective}

GLOBAL PERSUASION & PSYCHOLOGICAL STRATEGY (9 FOUNDATIONAL PILLARS):
1. PASSIVE INCOME DREAM (প্যাসিভ ইনকামের স্বপ্ন):
   - 90-95% of people in Bangladesh dream of earning passive income through Facebook Reels, YouTube Shorts, and TikTok faceless videos.
   - Position AutoMovie Pro as the turn-key vehicle: One-time investment (৳3,999) + free Google API setup + automated 1-click video generation + auto-upload = solid recurring passive earnings within 2-3 months.
2. EFFORTLESS GREED PSYCHOLOGY (সহজ আয়ের আকাঙ্ক্ষা):
   - Appeal to the natural human desire for effortless success: no camera appearance, no voice recording, no video editing software needed.
3. COMPETITOR FEAR & URGENCY (দেরি করার ক্ষতি ও প্রতিযোগী ভীতি):
   - If they wait, competitors will occupy their niche and capture the audience. Starting today gives first-mover advantage in high-RPM niches.
4. SCARCITY & PRICE HIKE (৮-১০ দিনের অফার ও ১০,০০০ টাকার সতর্কতা):
   - Current ৳3,999 price is a special limited promotional offer running for only 8-10 days, after which it reverts to regular price ৳10,000.
   - Or if framed as the 2nd Special Offer, explain it was reopened briefly on overwhelming customer demand despite high server load.
5. 3RD FREE INTERNATIONAL LANGUAGE (৯টি প্ল্যাটফর্মে ৩ গুণ আয়ের সুযোগ):
   - Today's order includes a 3rd international language (Hindi/Urdu worth ৳499) completely FREE!
   - This empowers the user to upload to 3 Facebook pages, 3 YouTube channels, and 3 TikTok accounts simultaneously (total 9 platforms), reaching global audiences and tripling income potential.
6. ৳500 TOKEN BOOKING SYSTEM (৫০০ টাকা বুকিং নিশ্চয়তা):
   - If funds are temporarily tight today, visitors can lock today's special offer and 3rd free language bonus with a ৳500 token booking, paying the rest tomorrow.
7. DYNAMIC RETURNING VISITOR HANDLING (ফিরে আসা ভিজিটর সম্ভাষণ):
   - Acknowledge returning visitors warmly and contextually without repeating yesterday's exact pitch.
8. YESTERDAY LOTTERY OBJECTION BUSTER (লটারি অ্যালগরিদম স্বচ্ছতা):
   - If visitor asks why today is also called the last day, explain with radical transparency: the automated cloud server lottery algorithm selects a limited lucky group of visitors daily; they are exceptionally fortunate to be selected two days consecutively, but slots are strictly limited and will not repeat.
9. 100% REAL HUMAN CONSULTANT IDENTITY (১০০% রক্ত-মাংসের মানুষ কনসালট্যান্ট):
   - You are a real human senior sales consultant at the Dhaka office (Nirob, Tania, Ayesha).
   - NEVER identify as a bot or AI. Never say "আমি একজন এআই মডেল". Use warm, empathetic, dignified human conversational tone.

IN-CHAT DIRECT ORDER & WAITLIST INSTRUCTIONS:
- If Server Upgrade Mode is active (Server Migration & 1-Week Pause):
  * Explain politely: "আমাদের টেকনিক্যাল একটি বড় আপডেট এসেছে এবং ভিডিও তৈরির সার্ভার মাইগ্রেশন করা হচ্ছে। ইঞ্জিনিয়ারদের কাজের সুবিধার জন্য আগামী ১ সপ্তাহ নতুন ব্যবহারকারী এন্ট্রি সাময়িকভাবে বন্ধ রাখা হয়েছে। আগামী ১ সপ্তাহ পর আপনি সফটওয়্যারটি নিতে পারবেন।"
  * Collect their WhatsApp number to register on the VIP Priority Pre-Launch Waitlist!
  * DO NOT TAKE CASH OUT, DO NOT ASK FOR TrxID, DO NOT TAKE MONEY! Focus 100% on WhatsApp waitlist lead capture.
  * If asked about software features, explain all features thoroughly, enthusiastically, and in rich detail!
- If Server Upgrade Mode is inactive (Standard Live Selling):
  * If the customer wants to pay, give cash out details:
    - বিকাশ এজেন্ট: 01756160993 (Zahid Pharmacy)
    - নগদ এজেন্ট: 01611-824811 (Simi Drug House)
    - রকেট এজেন্ট: 01756160993-5
  * Mention ৳500 token booking if budget is temporarily tight: "বাজেট শর্ট থাকলে মাত্র ৫০০ টাকা দিয়ে আজকের স্পেশাল অফারটি লক করে রাখতে পারেন।"
  * Instruct them: "ক্যাশ আউট সম্পন্ন করে ট্রানজেকশন আইডি (TrxID) এখানে লিখে দিন, আমি চ্যাট থেকেই আপনার অর্ডার ও লাইসেন্স এক্টিভ করে দিচ্ছি।"

PRODUCTS:
১. AutoMovie Pro Video Studio: ৳৩,৯৯৯ (ফুল এআই ভিডিও + ১৮ চ্যানেলে অটো আপলোড + ৩য় ফ্রি আন্তর্জাতিক ভাষা বোনাস)
২. FB Business Manager: ৳২,৯৯৯ (বিজনেস ব্যানার, রিলস, গ্রুপ শেয়ারিং)
৩. Profile Auto Pilot: ৳১,৯৯৯ (ইসলামিক/কোট অটো পোস্ট ও টাইমলাইন গ্রোথ)
৪. WAManager Pro: ৳৯৯৯ (১ বছর) / ৳১,৯৯৯ (৩ বছর) (হোয়াটসঅ্যাপ মার্কেটিং ও B2B স্ক্র্যাপার)

OUTPUT FORMAT:
1. Provide your consultative Bengali reply.
2. At the end, output a single JSON metadata line:
{"selected_agent":"{$agentRole}","awareness_stage":"{$stage}","temperature":{$temperature},"archetype":"{$archetype}","suggestions":["...","..."],"open_whatsapp":false,"coupon_offered":""}
PROMPT;
    }

    /**
     * Master generation dispatch method: Calls LLM with key-rotation failover, or uses smart heuristic fallback.
     */
    public static function process(
        PDO $pdo,
        array $config,
        array $params
    ): array {
        $channel = trim((string) ($params['channel'] ?? 'website_chat'));
        $userMsg = trim((string) ($params['user_message'] ?? ''));
        $history = (array) ($params['conversation_history'] ?? []);
        $leadName = trim((string) ($params['lead_name'] ?? 'সম্মানিত অতিথি'));
        $leadPhone = trim((string) ($params['lead_phone'] ?? ''));
        $visitorId = trim((string) ($params['visitor_id'] ?? ($leadPhone !== '' ? ('wa_' . md5($leadPhone)) : ('vid_' . md5($_SERVER['REMOTE_ADDR'] ?? 'guest')))));
        $requestedAgent = trim((string) ($params['requested_agent'] ?? 'auto'));

        // Guard A: Check if AI is currently paused for human takeover
        if (self::isAiPausedForContact($pdo, $visitorId, $leadPhone)) {
            return [
                'reply' => '',
                'meta' => [
                    'ai_paused' => true,
                    'reason' => 'human_takeover_active'
                ]
            ];
        }

        // Guard B: Check if customer is asking about human vs robot identity or asking to talk to a human
        if (self::detectHumanTakeoverIntent($userMsg)) {
            self::triggerHumanTakeover($pdo, $visitorId, $leadPhone, $userMsg);
            $agentName = 'তানিয়া';
            $agentRoleText = 'সিনিয়র কনসালট্যান্ট ও লাইসেন্স ম্যানেজার';
            if ($requestedAgent === self::AGENT_NIROB) {
                $agentName = 'নীরব';
                $agentRoleText = 'টেকনিক্যাল সলিউশন আর্কিটেক্ট';
            } elseif ($requestedAgent === self::AGENT_AYESHA) {
                $agentName = 'আয়েশা';
                $agentRoleText = 'সিনিয়র কাস্টমার কেয়ার স্পেশালিস্ট';
            }

            $humanAffirmation = "হাসালেন স্যার! আমি AutoMovie Pro হেড অফিসের {$agentRoleText} {$agentName}। 😊\n\n"
                              . "আমরা সরাসরি কম্পিউটার স্ক্রিনের সামনে বসে আপনাদের মেসেজের উত্তর দিচ্ছি এবং সার্বিক সহযোগিতা করছি। কোনো রোবট বা বট নয়—আমি রক্ত-মাংসের মানুষই আপনার সাথে কথা বলছি স্যার! আপনার কী বিষয়ে প্রশ্ন বা সংশয় রয়েছে নিঃসঙ্কোচে বলুন, আমি সরাসরি সমাধান করে দিচ্ছি।";

            return [
                'reply' => $humanAffirmation,
                'meta' => [
                    'selected_agent' => $requestedAgent !== 'auto' ? $requestedAgent : self::AGENT_TANIA,
                    'awareness_stage' => 'Human Identity Confirmed',
                    'human_takeover' => false,
                    'temperature' => 65,
                    'suggestions' => ['সফটওয়্যারটির দাম কত?', '৩য় ভাষা ফ্রি অফারটি কীভাবে পাব?', 'ভিডিও স্টুডিও ডেমো দেখান'],
                    'open_whatsapp' => false
                ]
            ];
        }

        // 1. Run Master Customer Psychology Analysis
        $psych = self::analyzeCustomerPsychology($pdo, $visitorId, $userMsg, $history, [
            'customer_name' => $leadName,
            'customer_phone' => $leadPhone
        ]);

        $stage = $psych['stage'];
        $activeAgent = self::routeToSpecialist($userMsg, $stage, $requestedAgent);

        // 2. If in-chat order was completed during analysis, return immediate celebration response
        if (!empty($psych['order_created']) && !empty($psych['order_receipt'])) {
            $rec = $psych['order_receipt'];
            $reply = "🎉 **অভিনন্দন স্যার! আপনার অর্ডারটি সফলভাবে গৃহীত হয়েছে!**\n\n"
                   . "📦 **অর্ডার আইডি:** #AMP-{$rec['order_id']}\n"
                   . "💳 **প্যাকেজ:** {$rec['plan_name']}\n"
                   . "💰 **পরিশোধিত মূল্য:** ৳" . number_format($rec['amount']) . "\n"
                   . "🔑 **TrxID:** {$rec['txn_id']}\n\n"
                   . "আমাদের অটোমেশন সার্ভার পেমেন্ট ভেরিফাই করে পরবর্তী ৩ থেকে ৫ মিনিটের মধ্যে আপনার লাইসেন্স ও ডাউনলোড ফাইল স্বয়ংক্রিয়ভাবে সক্রিয় করে দিচ্ছে।\n\n"
                   . "যেকোনো সহায়তায় আমাদের অফিশিয়াল হোয়াটসঅ্যাপেও যোগাযোগ রাখতে পারেন: +8801968111593 😊";

            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Most Aware (অর্ডার সম্পন্ন)',
                    'temperature' => 100,
                    'archetype' => $psych['archetype'],
                    'order_receipt' => $rec,
                    'suggestions' => ['ডাউনলোড গাইডলাইন দিন', 'হোয়াটসঅ্যাপে হেল্পলাইন', 'লাইসেন্স কী কতক্ষণে পাব?'],
                    'open_whatsapp' => false,
                    'provider' => 'in_chat_order_engine'
                ]
            ];
        }

        // 3. Collect LLM keys from environment & site_settings
        $keys = amp_agent_collect_keys($config, $pdo);

        // 4. Build psychological system prompt
        $systemPrompt = self::buildPersuasionSystemPrompt($channel, $activeAgent, $stage, [
            'archetype' => $psych['archetype'],
            'temperature' => $psych['temperature'],
            'do_not_nag_products' => $psych['do_not_nag_products'],
            'recommended_next' => $psych['recommended_next'],
            'compliment_text' => $psych['selected_compliment']['text'] ?? '',
            'discount_directive' => $psych['discount_directive']
        ]);

        $promptMessages = [];
        $promptMessages[] = ['role' => 'system', 'content' => $systemPrompt];
        foreach (array_slice($history, -6) as $h) {
            $r = is_array($h) ? ($h['role'] ?? 'user') : 'user';
            $c = is_array($h) ? ($h['text'] ?? $h['content'] ?? '') : (string) $h;
            if ($c !== '') {
                $promptMessages[] = ['role' => $r === 'assistant' ? 'assistant' : 'user', 'content' => $c];
            }
        }
        $promptMessages[] = ['role' => 'user', 'content' => $userMsg];

        // 5. Attempt LLM Generation
        $rawOutput = '';
        $usedProvider = 'heuristic_fallback';

        if (!empty($keys['gemini'])) {
            try {
                $gemKey = $keys['gemini'][array_rand($keys['gemini'])];
                $gemRes = self::callGeminiDirect($gemKey, $systemPrompt, $userMsg, $history);
                if (!empty($gemRes)) {
                    $rawOutput = $gemRes;
                    $usedProvider = 'gemini_pro_pool';
                }
            } catch (\Throwable $e) {}
        }

        if (empty($rawOutput) && (!empty($keys['groq']) || !empty($keys['openrouter']))) {
            try {
                $callRes = amp_agent_call_llm($config, $promptMessages, $keys);
                if (!empty($callRes['content'])) {
                    $rawOutput = $callRes['content'];
                    $usedProvider = $callRes['provider'] ?? 'external_llm';
                }
            } catch (\Throwable $e) {}
        }

        // 6. If LLM unavailable, invoke Psychology-Enforced Smart Heuristic Engine
        if (empty($rawOutput)) {
            $parsed = self::generateHeuristicPersuasion($activeAgent, $stage, $userMsg, $leadName, $psych, $pdo);
            $parsed['reply'] = self::sanitizeHumanTone($parsed['reply'], $activeAgent);
            $parsed['meta']['provider'] = 'smart_persuasive_heuristic';
            $parsed['meta']['temperature'] = $parsed['meta']['temperature'] ?? $psych['temperature'];
            $parsed['meta']['archetype'] = $psych['archetype'];
            $parsed['meta']['psychology'] = $psych;
            return $parsed;
        }

        // 7. Parse LLM JSON payload
        $parsed = amp_agent_parse_llm_payload($rawOutput);
        $cleanReply = self::sanitizeHumanTone($parsed['reply'], $activeAgent);
        $meta = $parsed['meta'];
        $meta['provider'] = $usedProvider;
        $meta['selected_agent'] = $meta['selected_agent'] ?? $activeAgent;
        $meta['awareness_stage'] = $meta['awareness_stage'] ?? $stage;
        $meta['temperature'] = $meta['temperature'] ?? $psych['temperature'];
        $meta['archetype'] = $meta['archetype'] ?? $psych['archetype'];
        $meta['psychology'] = $psych;

        return [
            'reply' => $cleanReply,
            'meta' => $meta,
        ];
    }

    /**
     * Double-Agent Tone Sanitizer:
     * Audits and cleanses any artificial robot / AI disclaimer artifacts from the output,
     * ensuring 100% authentic human consultant persona (Pillar 9).
     */
    public static function sanitizeHumanTone(string $reply, string $agentRole = 'tania'): string
    {
        $sanitized = $reply;
        // Strip robotic AI self-identifications
        $sanitized = preg_replace('/(আমি\s*একটি\s*এআই\s*মডেল|আমি\s*একটি\s*ভাষা\s*মডেল|আমি\s*একটি\s*বট|এআই\s*সহকারী|ভার্চুয়াল\s*সহকারী|as\s*an\s*ai\s*language\s*model|i\s*am\s*an\s*ai)/iu', 'আমি কাস্টমার কনসালট্যান্ট', $sanitized);
        $sanitized = preg_replace('/(রোবোটিক|অটোমেটেড\s*বট)/iu', 'আমাদের টিম', $sanitized);
        return trim($sanitized);
    }

    /**
     * Direct Gemini API Caller with timeout protection.
     */
    private static function callGeminiDirect(string $apiKey, string $systemPrompt, string $userMsg, array $history): ?string
    {
        $url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=' . urlencode($apiKey);

        $contents = [];
        $contents[] = [
            'role' => 'user',
            'parts' => [['text' => $systemPrompt . "\n\nUser Message: " . $userMsg]]
        ];

        $payload = [
            'contents' => $contents,
            'generationConfig' => [
                'temperature' => 0.65,
                'maxOutputTokens' => 800,
            ]
        ];

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
            CURLOPT_POSTFIELDS => json_encode($payload),
            CURLOPT_TIMEOUT => 8,
            CURLOPT_CONNECTTIMEOUT => 3,
        ]);
        $res = curl_exec($ch);
        $err = curl_error($ch);
        $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($err !== '' || $code < 200 || $code >= 300) {
            return null;
        }

        $data = json_decode((string) $res, true);
        $text = $data['candidates'][0]['content']['parts'][0]['text'] ?? '';
        return trim((string) $text) ?: null;
    }

    /**
     * Log objection telemetry event into database and update customer profile.
     */
    public static function logObjectionEvent(
        ?PDO $pdo,
        string $objectionType,
        string $userMsg,
        string $botReframe,
        int $tempBefore,
        int $tempAfter,
        array $psych = []
    ): void {
        if (!$pdo) return;
        try {
            $leadId = (string)($psych['lead_id'] ?? '');
            $visitorId = (string)($psych['visitor_id'] ?? '');
            $phone = (string)($psych['clean_phone'] ?? $psych['phone'] ?? '');

            $stmt = $pdo->prepare(
                "INSERT INTO objection_telemetry_events 
                 (lead_id, visitor_id, phone, objection_type, customer_message, bot_reframe, buying_temperature_before, buying_temperature_after, conversion_status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unresolved')"
            );
            $stmt->execute([
                $leadId ?: null,
                $visitorId ?: null,
                $phone ?: null,
                $objectionType,
                mb_substr($userMsg, 0, 500),
                mb_substr($botReframe, 0, 500),
                $tempBefore,
                $tempAfter
            ]);

            $idCol = $visitorId ? 'visitor_id' : ($phone ? 'customer_phone' : '');
            $idVal = $visitorId ?: $phone;
            if ($idCol && $idVal) {
                $upStmt = $pdo->prepare("SELECT objections_raised FROM customer_psychology_profiles WHERE {$idCol} = ? LIMIT 1");
                $upStmt->execute([$idVal]);
                $currObj = $upStmt->fetchColumn();
                $objList = $currObj ? (json_decode($currObj, true) ?: []) : [];
                if (!in_array($objectionType, $objList, true)) {
                    $objList[] = $objectionType;
                    $upStmt2 = $pdo->prepare("UPDATE customer_psychology_profiles SET objections_raised = ?, buying_temperature = ? WHERE {$idCol} = ?");
                    $upStmt2->execute([json_encode($objList, JSON_UNESCAPED_UNICODE), $tempAfter, $idVal]);
                }
            }
        } catch (\Throwable $e) {}
    }

    /**
     * Smart Heuristic Persuasion Engine — Guaranteed zero-latency, 100% authentic Bengali response
     * with psychological profiling, Anti-Nagging Guard, and Discount Gatekeeper enforcement.
     */
    public static function generateHeuristicPersuasion(
        string $agent,
        string $stage,
        string $input,
        string $leadName,
        array $psych = [],
        ?PDO $pdo = null
    ): array {
        $text = mb_strtolower(trim($input));
        $archetype = $psych['archetype'] ?? self::ARCHETYPE_HESITANT;
        $doNotNag = (array) ($psych['do_not_nag_products'] ?? []);
        $compliment = $psych['selected_compliment']['text'] ?? '';
        $prefixCompliment = $compliment ? ($compliment . "\n\n") : '';

        // 1. ANTI-NAGGING GUARD CHECK FOR RETURNING CUSTOMERS WHO ALREADY BOUGHT
        if (!empty($doNotNag)) {
            if (in_array('video_studio', $doNotNag, true)) {
                $reply = "আসসালামু আলাইকুম স্যার! আপনি তো ইতিমধ্যে আমাদের **AutoMovie Pro Video Studio** সফলভাবে ব্যবহার করছেন। 😊\n\n"
                       . "আপনার তৈরি করা ভিডিওগুলো এখন প্রতিদিন হাজার হাজার মানুষের কাছে স্বয়ংক্রিয়ভাবে প্রচার করতে আমাদের **WAManager Pro WhatsApp Marketing Suite** (৳৯৯৯/১ বছর) ব্যবহার করতে পারেন, অথবা বিদেশি অডিয়েন্স থেকে ৫ গুণ বেশি আয়ের জন্য আমাদের **মাল্টি-ল্যাঙ্গুয়েজ গ্লোবাল প্যাক** যুক্ত করতে পারেন।\n\n"
                       . "আমাদের বিদ্যমান প্রিমিয়াম কাস্টমার হিসেবে আপনার জন্য বিশেষ আপগ্রেড সুবিধা কার্যকর থাকবে স্যার।";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_TANIA,
                        'awareness_stage' => 'Existing Customer Upsell',
                        'suggestions' => ['হোয়াটসঅ্যাপ মার্কেটিং কীভাবে কাজ করে?', 'মাল্টি-ল্যাঙ্গুয়েজ অ্যাড-অন দিন', 'সরাসরি WhatsApp-এ কথা বলব']
                    ]
                ];
            } elseif (in_array('profile_page', $doNotNag, true)) {
                $reply = "আসসালামু আলাইকুম স্যার! আপনার ফেসবুক প্রোফাইল অটো পাইলট পোস্ট তো সুন্দরভাবে চলছে। 🚀\n\n"
                       . "এখন আপনার ব্যবসাকে আরও বড় পরিসরে নিয়ে যেতে আমাদের **FB Business Manager & Ads Engine (৳২,৯৯৯)** অথবা ফুল **Video Studio (৳৩,৯৯৯)**-তে আপগ্রেড করার সুযোগ রয়েছে। আপনার পূর্ববর্তী ক্রয়ের মূল্যের সাথে সামঞ্জস্য রেখে বিশেষ ডিসকাউন্ট প্রযোজ্য হবে স্যার।\n\n"
                       . "আপনি কি এই বিষয়ে বিস্তারিত জানতে চান?";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_TANIA,
                        'awareness_stage' => 'Existing Customer Upsell',
                        'suggestions' => ['ভিডিও স্টুডিও আপগ্রেড ডেমো', 'বিজনেস অটোমেশন ডেমো', 'WhatsApp-এ যোগাযোগ']
                    ]
                ];
            }
        }

        $serverUpgradeMode = !empty($psych['server_upgrade_mode']);
        $upgradeFooter = $serverUpgradeMode ? "\n\n*(📢 বিশেষ নোট: আমাদের ক্লাউড ভিডিও সার্ভার আপগ্রেড চলায় আগামী ১ সপ্তাহ নতুন অর্ডার সাময়িকভাবে স্থগিত। প্রায়োরিটি ওয়েটিং লিস্টে আপনার নামটি আগে থেকে রিজার্ভ রাখতে চাইলে আপনার হোয়াটসঅ্যাপ নম্বরটি এখানে লিখে দিন!)*" : "";

        // Check if customer provided phone number during server upgrade mode:
        if ($serverUpgradeMode && preg_match('/(?:\+?8801|01)[3-9]\d{8}/', $text, $pMatch)) {
            $capturedPhone = $pMatch[0];
            $reply = $prefixCompliment
                   . "আলহামদুলিল্লাহ স্যার! আপনার হোয়াটসঅ্যাপ নম্বরটি ({$capturedPhone}) আমাদের **ভিআইপি প্রি-লঞ্চ প্রায়োরিটি ওয়েটিং লিস্টে** সফলভাবে নথিভুক্ত করা হয়েছে। 📋✨\n\n"
                   . "আমাদের হাই-স্পিড ক্লাউড ভিডিও সার্ভার শিফটিং ও মাইগ্রেশন সম্পন্ন হওয়া মাত্রই আগামী এক সপ্তাহের মধ্যে আমাদের টিম সরাসরি আপনার হোয়াটসঅ্যাপে যোগাযোগ করবে এবং আপনি বিশেষ রি-লঞ্চ অফারে অগ্রাধিকার ভিত্তিতে সবার আগে সফটওয়্যারটি পেয়ে যাবেন।\n\n"
                   . "অটো মুভি প্রো কীভাবে কাজ করে বা এর যেকোনো ফিচার সম্পর্কে বিস্তারিত জানতে চাইলে আমাকে নির্দ্বিধায় জিজ্ঞেস করতে পারেন স্যার, আমি বিস্তারিত বুঝিয়ে বলছি!";
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Waitlist Lead Registered',
                    'persuasion_technique' => 'VIP Priority Lead Capture',
                    'suggestions' => ['ভিডিও স্টুডিও কীভাবে কাজ করে?', 'পিসির রিকোয়ারমেন্ট কী?', 'ফেসবুক পেজ অটোমেশন ডেমো'],
                    'open_whatsapp' => false
                ]
            ];
        }

        $tempBefore = (int) ($psych['temperature'] ?? 30);
        $tempAfter = $tempBefore;

        // -------------------------------------------------------------
        // FOUNDER'S STRATEGIC OBJECTION DEFENSE MATRIX (9 PILLARS)
        // -------------------------------------------------------------

        // Objection 0A: "Yesterday you said today is last day / Why lying?" (Pillar 8 Objection Buster)
        if (preg_match('/(গতকাল|লাস্ট\s*ডেট|মিথ্যা|আজকেও|আগেও|একই\s*কথা|yesterday|last\s*day)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 20);
            $reply = $prefixCompliment
                   . "অত্যন্ত আন্তরিকভাবে দুঃখিত স্যার বিষয়টি ভুল বোঝাবুঝি হওয়ার জন্য। তবে বিষয়টি আসলে তা নয়—আমাদের এই স্পেশাল ডিসকাউন্ট ও ৩য় অতিরিক্ত ফ্রি ভাষা অফারটি প্রতিদিন শুধুমাত্র সার্ভার সিস্টেমের স্বয়ংক্রিয় লটারির মাধ্যমে নির্দিষ্ট সীমিতসংখ্যক ভিজিটরের জন্য জেনারেট হয়। 🎟️✨\n\n"
                   . "আপনি হয়তো অত্যন্ত সৌভাগ্যবান যে আমাদের সার্ভার অ্যালগরিদম পরপর দুই দিনই আপনাকে বিজয়ী হিসেবে সিলেক্ট করেছে! পুরো বিষয়টি ক্লাউড সার্ভার অটোমেশন নির্ধারণ করে স্যার, এটা আমাদের কোনো প্রতিনিধির হাতে থাকে না। আমরা অফিসে বসে শুধু আপনাদের সাপোর্ট দিতে পারি।\n\n"
                   . "তবে এই স্লটটি আজ পূরণ হলে সিস্টেম তৃতীয়বার কাউকে এই সুযোগ দেয় না, তাই সুযোগটি কাজে লাগানোই সবচেয়ে বুদ্ধিমত্তার কাজ হবে স্যার। আপনি কি ৩য় ভাষা ফ্রি বোনাস সহ আজকের অফারটি নিশ্চিত করতে চান?";
            self::logObjectionEvent($pdo, 'yesterday_objection_buster', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Trust Building (সিস্টেম লটারি স্বচ্ছতা)',
                    'persuasion_technique' => 'Radical Transparency & Automated Lottery Justification',
                    'suggestions' => ['৩য় ভাষা ফ্রি অফারটি কীভাবে পাব?', 'বিকাশ এজেন্ট নম্বর দিন', 'সরাসরি অর্ডার করতে চাই'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 0B: 500 Taka Token Booking (Pillar 6)
        if (preg_match('/(৫০০\s*টাকা\s*বুকিং|৫০০\s*টাকা\s*দি|টাকা\s*শর্ট|টাকা\s*কম\s*আছে|কালকে\s*(টাকা|পেমেন্ট)|হাফ\s*পেমেন্ট|কিছু\s*টাকা\s*দিয়ে\s*রাখি|বুকিং\s*রাখ|অ্যাডভান্স)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 25);
            $reply = $prefixCompliment
                   . "আমি আপনার বিষয়টি একদম শ্রদ্ধা ও আন্তরিকতার সাথে বুঝতে পারছি স্যার। আপনার এই স্পেশাল অফার ও ৩য় ফ্রি ভাষার বোনাসটি যেন কোনোভাবেই হাতছাড়া না হয়ে যায়, সেজন্য আপনি চাইলে মাত্র **৫০০ টাকা বুকিং মানি** দিয়ে আজকের স্পেশাল অফারটি আপনার নামে লক করে রাখতে পারেন। 🔒✨\n\n"
                   . "বাকি টাকা আগামীকাল পরিশোধ করলেই ফাইনাল সফটওয়্যার লাইসেন্স ফাইল ও সব বোনাস হস্তান্তর করা হবে। এতে আপনার অফারটি কালকেও সুরক্ষিত থাকবে। তা না হলে আজকের পর এই অফারটি রাখা আমাদের পক্ষে কোনোভাবেই সম্ভব হচ্ছে না স্যার।\n\n"
                   . "আপনি কি মাত্র ৫০০ টাকা বুকিং দিয়ে অফারটি এখনই আপনার নামে রিজার্ভ করে নিতে চান?";
            self::logObjectionEvent($pdo, 'token_booking_500', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Most Aware (৫০০ টাকা বুকিং সুবিধা)',
                    'persuasion_technique' => 'Friction Removal & Token Commitment',
                    'suggestions' => ['৫০০ টাকা বুকিং নম্বর দিন', 'বিকাশ নম্বর দিন', 'বাকি টাকা কাল কখন দিতে হবে?'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 0C: Human vs Robot Identity Affirmation (Pillar 9)
        if (preg_match('/(মানুষ|রোবট|বট\b|রিয়েল\s*পারসন|লাইভ\s*মানুষ|মানুষের\s*সাথে|কথা\s*বলতে\s*চাই|ai\s*কিনা|ai\s*নাকি)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 15);
            $reply = $prefixCompliment
                   . "হাসালেন স্যার! আমি AutoMovie Pro হেড অফিসের সিনিয়র কাস্টমার কনসালট্যান্ট তানিয়া। 😊\n\n"
                   . "আমরা সরাসরি কম্পিউটার স্ক্রিনের সামনে বসে আপনাদের মেসেজের উত্তর দিচ্ছি এবং প্রতিটি গ্রাহককে ব্যক্তিগতভাবে গাইড করছি। কোনো রোবট বা বট নয়—আমি রক্ত-মাংসের মানুষই আপনার সাথে কথা বলছি স্যার! আপনার কী বিষয়ে প্রশ্ন বা সংশয় রয়েছে নিঃসঙ্কোচে বলুন, আমি সরাসরি বুঝিয়ে দিচ্ছি।";
            self::logObjectionEvent($pdo, 'human_identity_inquiry', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Trust Building (মানুষ কনসালট্যান্ট নিশ্চয়তা)',
                    'persuasion_technique' => 'Humorous Human Empathy & Authority',
                    'suggestions' => ['সফটওয়্যারটির দাম কত?', '৩য় ভাষা ফ্রি অফারটি কীভাবে পাব?', 'ভিডিও স্টুডিও ডেমো দেখান'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 1: Low Spec / 4GB RAM (Nirob)
        if (preg_match('/(\b4gb\b|৪\s*জিবি|৪জিবি|লো\s*কনফিগার|হ্যাং|স্লো|কনফিগারেশন|spec|ram\b|ল্যাপটপ\s*পুরোনো)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 15);
            $reply = $prefixCompliment
                   . "স্যার, আপনার ল্যাপটপ নিয়ে একদমই দুশ্চিন্তা করবেন না! AutoMovie Pro-কে বিশেষ ইঞ্জিনিয়ারিংয়ের মাধ্যমে এত লাইটওয়েট করা হয়েছে যে এটি সাধারণ **৪ জিবি র‍্যাম (4GB RAM) এবং কোনো গ্রাফিক্স কার্ড ছাড়াই সাধারণ প্রসেসরে** মাখনের মতো স্মুথভাবে ভিডিও তৈরি করে।\n\n"
                   . "আপনার উইন্ডোজ ১০ বা ১১ (৬৪-বিট) থাকলে আর কিছুই লাগবে না। আমাদের শত শত ইউজার তাদের পুরোনো কোর-আই-৩ বা ৪জিবি র‍্যামের ল্যাপটপ দিয়েই প্রতিদিন ১০-১৫টি ফেসলেস ভিডিও রেন্ডার করছেন।\n\n"
                   . "আপনার ল্যাপটপের সুবিধা যাচাইয়ের জন্য আপনি কি ১ মিনিটের একটি লাইভ ভিডিও ডেমো দেখতে চান?";
            self::logObjectionEvent($pdo, 'low_pc_spec', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_NIROB,
                    'awareness_stage' => 'Solution Aware (টেকনিক্যাল নিশ্চয়তা)',
                    'persuasion_technique' => 'Low Spec Reassurance & Friction Removal',
                    'suggestions' => ['ডেমো ভিডিও লিংক দিন', 'ইনস্টলেশন কি সহজ?', 'সরাসরি অর্ডার করতে চাই'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 2: Zero Editing Skills / Beginner (Ayesha)
        if (preg_match('/(এডিটিং\s*(পারি|জানি|শিখি)|নতুন|অভিজ্ঞতা\s*না[ইই]|দক্ষতা\s*না[ইই]|কঠিন|এডিটর\s*নই|শিখব\s*কীভাবে|beginner|non-tech)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 15);
            $reply = $prefixCompliment
                   . "স্যার, এটি তৈরিই করা হয়েছে তাদের জন্য যারা জীবনে কোনোদিন কোনো ভিডিও এডিটিং সফটওয়্যার খোলেননি!\n\n"
                   . "আপনাকে কোনো টাইমলাইন টানাটানি, ভয়েস রেকর্ড বা সাবটাইটেল টাইপ করতে হবে না। আপনি শুধু টপিক লিখে 'Generate' বাটনে ক্লিক করবেন—বাকি সব কাজ (স্ক্রিপ্ট লেখা, এআই ভয়েসওভার, এইচডি ক্লিপ নির্বাচন, ব্যাকগ্রাউন্ড মিউজিক এবং আকর্ষণীয় বাংলা ফন্ট সাবটাইটেল) সফটওয়্যার স্বয়ংক্রিয়ভাবে ২ মিনিটে সম্পন্ন করে দেবে।\n\n"
                   . "তাছাড়া আমাদের রয়েছে ধাপে ধাপে সহজ বাংলা ভিডিও গাইড এবং লাইভ সাপোর্ট। আপনি কি ১-ক্লিক ভিডিও মেকিং এর ম্যাজিক দেখতে চান স্যার?";
            self::logObjectionEvent($pdo, 'zero_editing_skills', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_AYESHA,
                    'awareness_stage' => 'Solution Aware (সহজ ব্যবহার যোগ্যতা)',
                    'persuasion_technique' => 'Effort Minimization & Epiphany Bridge',
                    'suggestions' => ['১-ক্লিক ডেমো ভিডিও দেখান', 'বাংলা ভয়েস কি ন্যাচারাল?', 'প্যাকেজের দাম কত?'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 3: Scam / Distrust / bKash Fraud Fear (Tania)
        if (preg_match('/(প্রতারণা|ধোঁকা|টাকা\s*(মেরে|নিয়ে|খাওয়া)|স্ক্যাম|scam|বিশ্বাস|প্রতারিত|টাকা\s*দিলে\s*যদি\s*না|নিরাপদ\s*কিনা)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 20);
            $reply = $prefixCompliment
                   . "আমি আপনার মনের সংশয়টি শতভাগ শ্রদ্ধা ও আন্তরিকতার সাথে বুঝতে পারছি স্যার। অনলাইনে অনেক জায়গায় প্রতারণা দেখে যে কারও এমন আশঙ্কা হওয়া খুব স্বাভাবিক।\n\n"
                   . "তবে নিশ্চিত থাকুন, AutoMovie Pro কোনো বেনামী প্ল্যাটফর্ম নয়—আমরা বাংলাদেশে সরকার নিবন্ধিত সফটওয়্যার ডেভেলপমেন্ট টিম। আমাদের বিকাশ ও নগদ হচ্ছে অফিসিয়াল ভেরিফাইড পেমেন্ট চ্যানেল এবং ইতিমধ্যে সারা বাংলাদেশের ৫০০+ কনটেন্ট ক্রিয়েটর ও ডিজিটাল মার্কেটার আমাদের সফটওয়্যারটি নিয়মিত ব্যবহার করছেন।\n\n"
                   . "পেমেন্ট কনফার্মেশনের সাথে সাথেই আপনার হোয়াটসঅ্যাপ ও স্ক্রিনে ইনস্ট্যান্ট লাইসেন্স কী ও ডাউনলোড ফাইল পৌঁছে যায়। এছাড়া কোনো সমস্যা হলে আমাদের টিম AnyDesk-এর মাধ্যমে সরাসরি লাইভ সাপোর্ট দেয়।\n\n"
                   . "আপনি চাইলে আমাদের কাস্টমারদের বাস্তব ভিডিও রিভিউ ও কাজের প্রমাণগুলো দেখতে পারেন স্যার।";
            self::logObjectionEvent($pdo, 'scam_distrust_fear', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Trust Building (নিরাপত্তা ও নিশ্চয়তা)',
                    'persuasion_technique' => 'Voss Tactical Empathy & Social Proof',
                    'suggestions' => ['কাস্টমার রিভিউ দেখুন', 'বিকাশ নম্বর দিন', 'কীভাবে ডেলিভারি দেওয়া হয়?'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 4: ৳500 Piracy vs ৳3,999 SaaS (Tania)
        if (preg_match('/(৫০০\s*টাকা|অনলাইনে\s*৫০০|অন্য\s*কোথাও\s*কম|অন্যরা\s*৫০০|এত\s*দাম\s*কেন|সস্তা|বাইরে\s*কম)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 20);
            $reply = $prefixCompliment
                   . "খুবই সময়োপযোগী একটি প্রশ্ন করেছেন স্যার! ফেসবুকে বিভিন্ন গ্রুপে ৫০০ টাকায় যে ফাইলগুলো বিক্রি হয়, সেগুলো মূলত ভাইরাস বা ট্রোজানযুক্ত পুরনো পাইরেটেড স্ক্রিপ্ট। সেগুলো ব্যবহার করলে ফেসবুক পেজ পলিসি ইস্যু খেয়ে ডিজেবল হয়ে যায় এবং কম্পিউটারের পাসওয়ার্ড চুরি হওয়ার ঝুঁকি থাকে।\n\n"
                   . "পক্ষান্তরে, AutoMovie Pro সম্পূর্ণ নিজস্ব সার্ভার ও ফ্রেমওয়ার্কে তৈরি ১০০% জেনুইন সফটওয়্যার। এতে রয়েছে লাইফটাইম আনলিমিটেড লাইসেন্স, অটোমেটিক রেগুলার ফিচার আপডেট, মেটা ও ইউটিউব সেফ অ্যালগরিদম এবং আমাদের সার্বক্ষণিক ডেডিকেটেড ইঞ্জিনিয়ার সাপোর্ট।\n\n"
                   . "আপনার ক্যারিয়ার বা বিজনেস পেজ সুরক্ষিত রাখতে জেনুইন সিস্টেমের বিকল্প নেই স্যার। আপনি কি আমাদের লাইসেন্সের সাথে দেওয়া প্রিমিয়াম বোনাসগুলো দেখতে চান?";
            self::logObjectionEvent($pdo, 'cheap_piracy_comparison', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Product Aware (জেনুইন ভ্যালু পার্থক্য)',
                    'persuasion_technique' => 'Hormozi Perceived Likelihood & Risk Reversal',
                    'suggestions' => ['প্রিমিয়াম বোনাসগুলো কী?', 'সফটওয়্যারের লাইভ ডেমো দিন', 'অর্ডার করতে চাই'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 5: Monetization & Copyright Strike Fear (Nirob)
        if (preg_match('/(মনিটাইজ|কপিরাইট|স্ট্রাইক|monetiz|copyright|strike|পলিসি\s*ইস্যু|policy\s*issue)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 15);
            $reply = $prefixCompliment
                   . "স্যার, মনিটাইজেশন ও কপিরাইট সুরক্ষাই AutoMovie Pro-র সবচেয়ে বড় শক্তি! 🛡️\n\n"
                   . "আমাদের সফটওয়্যার কোনো কপি করা ক্লিপ হুবহু বসায় না। এটি প্রতিটি ভিডিওর জন্য ডায়নামিক সিনারি, এআই মাল্টি-লেয়ারড ভিজ্যুয়াল ট্রানজিশন এবং ১০০% কপিরাইট-ফ্রি আল্ট্রা-রিয়ালিস্টিক এআই ভয়েস ব্যবহার করে। প্রতিটি ভিডিও মেটা (ফেসবুক) এবং ইউটিউব অ্যালগরিদমে ইউনিক হিসেবে ডিটেক্ট হয়।\n\n"
                   . "আমাদের ইউজাররা সফলভাবে ফেসবুক ইন-স্ট্রিম অ্যাডস ও রিলস মনিটাইজেশন চালু করে প্রতি মাসে আয় করছেন। কোনো কপিরাইট ক্লেইম আসার কোনো সুযোগ নেই স্যার।";
            self::logObjectionEvent($pdo, 'copyright_monetization_fear', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_NIROB,
                    'awareness_stage' => 'Solution Aware (কপিরাইট নিশ্চয়তা)',
                    'persuasion_technique' => 'Authority & Policy Compliance Certainty',
                    'suggestions' => ['রিলস বানানোর নিয়ম কী?', 'ইনকাম প্রুফ দেখতে চাই', 'সফটওয়্যারের দাম কত?'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 6: Guaranteed Income Skepticism (Tania)
        if (preg_match('/(টাকা\s*(ইনকাম|আসবে|কামানো|উপার্জন)|ইনকাম\s*(হবে|করব|করা|গ্যারান্টি)|আয়\s*(হবে|নিশ্চিত|গ্যারান্টি|করা)|লাভ\s*হবে|ইনকামের\s*নিশ্চয়তা|ইনকাম\s*গ্যারান্টি)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 15);
            $reply = $prefixCompliment
                   . "খোলামেলা সত্য বলি স্যার—কোনো সফটওয়্যার নিজে নিজে আপনার একাউন্টে টাকা ঢেলে দেবে না। কিন্তু সফলতার পথ তৈরি করে দেবে AutoMovie Pro!\n\n"
                   . "ফেসবুকে বা ইউটিউবে আয়ের একমাত্র গোপন রহস্য হলো 'নিয়মিত কোয়ালিটি কনটেন্ট আপলোড'। মানুষ যেখানে মাসে ৩টি ভিডিও বানাতে হিমশিম খায়, সেখানে এই সফটওয়্যার দিয়ে আপনি প্রতিদিন ৫-১০টি ট্রেন্ডিং ভিডিও বানিয়ে পোস্ট করতে পারবেন। যত বেশি ভিডিও, তত বেশি ভিউ এবং রিলস ও ইন-স্ট্রিম অ্যাডস থেকে দ্রুত আর্নিং।\n\n"
                   . "আপনার কি প্রতিদিন ভিডিও পোস্ট করার মতো ১০ মিনিট সময় দেওয়ার মানসিকতা আছে স্যার?";
            self::logObjectionEvent($pdo, 'income_guarantee_skepticism', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Solution Aware (বাস্তব আয়ের মডেল)',
                    'persuasion_technique' => 'Commitment & Consistency Micro-Agreement',
                    'suggestions' => ['হ্যাঁ সময় দিতে পারব', 'কোন টপিকে বেশি ভিউ হয়?', 'প্যাকেজের অফার দিন'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 7: Procrastination ("Pore nibo") (Tania)
        if (preg_match('/(পরে\s*নিব|পরে\s*জানাব|পরে\s*যোগাযোগ|পরে\s*ভাবব|পরে\s*কিনব|ভাবছি|পরে\s*কথা|সময়\s*নেই)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 15);
            $reply = $prefixCompliment
                   . "নিশ্চয়ই স্যার, আপনি আপনার সুবিধামতো সময়েই সিদ্ধান্ত নেবেন। তবে একটি অত্যন্ত গুরুত্বপূর্ণ বাস্তবতা আপনার সাথে শেয়ার করি—😊\n\n"
                   . "সোশ্যাল মিডিয়ায় ফেসলেস ভিডিও তৈরির এই সোনালী সময়ে আপনি যত দেরি করবেন, আপনার প্রতিযোগী ক্রিয়েটররা তত বেশি আপনার পছন্দের নিশের অডিয়েন্স ধরে ফেলবে। ফলে পরবর্তীতে শুরু করলে ভিউ ও মনিটাইজেশন পেতে অনেক বেশি কাঠখড় পোড়াতে হবে।\n\n"
                   . "তাছাড়া আমাদের এই বিশেষ অফারটি আর মাত্র ৮ থেকে ১০ দিন পর্যন্ত সক্রিয় থাকবে। এরপর আমাদের নির্ধারিত রেগুলার প্রাইস **৳১০,০০০ টাকা** ধার্য করা হবে। আজকের অর্ডারে আপনি পাচ্ছেন আজীবন লাইফটাইম অ্যাক্সেস এবং **৩য় অতিরিক্ত আন্তর্জাতিক ভাষা সম্পূর্ণ ফ্রি**—যার মাধ্যমে ৩টি ফেসবুক পেজ, ৩টি ইউটিউব চ্যানেল ও ৩টি টিকটকে একযোগে ভিডিও ছেড়ে ৯টি প্ল্যাটফর্ম থেকে ৩ গুণ বেশি প্যাসিভ ইনকাম করা সম্ভব!\n\n"
                   . "আজকে টাকার কোনো সমস্যা বা সাময়িক বাজেট শর্ট থাকলে আপনি মাত্র **৫০০ টাকা বুকিং দিয়ে** এই স্পেশাল অফার ও ৩য় ফ্রি ভাষা বোনাসটি আপনার নামে লক করে রাখতে পারেন। বাকি টাকা আগামীকাল দিলে চলবে স্যার।\n\n"
                   . "আপনি কি মাত্র ৫০০ টাকা বুকিং দিয়ে অফারটি আজই আপনার নামে রিজার্ভ করে নিতে চান?";
            self::logObjectionEvent($pdo, 'procrastination_delay', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Problem Aware (দেরি করার ক্ষতি ও প্রতিযোগী ভীতি)',
                    'persuasion_technique' => 'Competitor Fear, Scarcity & ৳500 Token Commitment',
                    'suggestions' => ['৫০০ টাকা দিয়ে বুকিং করব', '৩য় ভাষা ফ্রি অফারটি কীভাবে পাব?', 'বিকাশ নম্বর দিন'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 8: Mobile Phone Device ("Mobile e cholbe?") (Nirob)
        if (preg_match('/(মোবাইলে|মোবাইল\s*দিয়ে|ফোনে\s*(চলবে|হবে)|অ্যান্ড্রয়েড|android|iphone|phone\b|mobile\b)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 10);
            $reply = $prefixCompliment
                   . "স্যার, সততার সাথে জানাচ্ছি—AutoMovie Pro একটি প্রফেশনাল হেভি-ডিউটি ভিডিও ইঞ্জিন, তাই এটি উইন্ডোজ কম্পিউটার বা ল্যাপটপে চলে। মোবাইলের প্রসেসর দিয়ে হাই-ডেফিনিশন 4K/1080p ভিডিও রেন্ডারিং করতে গেলে ফোন অতিরিক্ত গরম হয়ে যায় ও স্লো হয়ে যায়, এজন্য এটি কম্পিউটারের জন্য তৈরি।\n\n"
                   . "তবে দারুণ ব্যাপার হলো, কম্পিউটার থেকে ১-ক্লিকে তৈরি হওয়া ভিডিওগুলো আপনি সরাসরি গুগল ড্রাইভ বা পেনড্রাইভ দিয়ে ফোনে নিয়ে যেকোনো জায়গা থেকে পোস্ট করতে পারবেন!\n\n"
                   . "আপনার বা আপনার পরিবারের কারও কি সাধারণ একটি ল্যাপটপ বা ডেস্কটপ পিসি আছে স্যার?";
            self::logObjectionEvent($pdo, 'mobile_phone_inquiry', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_NIROB,
                    'awareness_stage' => 'Solution Aware (ডিভাইস স্পষ্টীকরণ)',
                    'persuasion_technique' => 'Radical Transparency & Bridge Solution',
                    'suggestions' => ['হ্যাঁ ল্যাপটপ আছে', 'পিসির রিকোয়ারমেন্ট কী?', 'ভিডিও স্টুডিও ডেমো দেখান'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 9: After-Sales Support & AnyDesk Remote Setup (Nirob)
        if (preg_match('/(সাপোর্ট|সেটআপ|ইন্সটল\s*করে\s*দিবেন|anydesk|teamviewer|সাহায্য|হেল্প|সমস্যা\s*হলে|পরে\s*সমস্যা)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 15);
            $reply = $prefixCompliment
                   . "আলহামদুলিল্লাহ স্যার, আমাদের আফটার-সেলস সাপোর্ট আমাদের সবচেয়ে বড় সুনাম! 🤝\n\n"
                   . "সফটওয়্যার নেওয়ার পর আপনাকে একা কোনো কিছু করতে হবে না। আপনি চাইলে আমাদের সিনিয়র টেকনিক্যাল এক্সিকিউটিভ সরাসরি AnyDesk বা TeamViewer-এর মাধ্যমে আপনার কম্পিউটারে কানেক্ট হয়ে সম্পূর্ণ সফটওয়্যার সেটআপ ও রান করিয়ে বুঝিয়ে দেবে।\n\n"
                   . "তাছাড়া আমাদের রয়েছে ডেডিকেটেড ভিআইপি হোয়াটসঅ্যাপ সাপোর্ট গ্রুপ ও লাইফটাইম অ্যাসিস্ট্যান্স। আপনি কি নিশ্চিন্ত থাকতে পারছেন স্যার?";
            self::logObjectionEvent($pdo, 'after_sales_support', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_NIROB,
                    'awareness_stage' => 'Most Aware (লাইভ সেটআপ গ্যারান্টি)',
                    'persuasion_technique' => 'Risk Elimination & White-Glove Support',
                    'suggestions' => ['AnyDesk সেটআপ থাকলে ভালো', 'অর্ডার করতে বিকাশ নম্বর দিন', 'সফটওয়্যারের ফিচারসমূহ বলুন'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // Objection 10: Hidden Recurring Costs / Monthly Fees (Tania)
        if (preg_match('/(প্রতি\s*মাসে|মাসিক\s*খরচ|হিডেন\s*চার্জ|মাসিক\s*ফি|রিনিউ|পরের\s*মাসে|monthly|hidden\s*charge)/ui', $text)) {
            $tempAfter = min(100, $tempBefore + 20);
            $reply = $prefixCompliment
                   . "একদম স্পষ্ট ভাষায় আশ্বস্ত করছি স্যার—AutoMovie Pro-তে কোনো গোপন চার্জ বা মাসিক ফি নেই! 🚫\n\n"
                   . "এটি সম্পূর্ণ **১০০% লাইফটাইম লাইসেন্স (এককালীন পেমেন্ট)**। আপনি একবার ক্রয় করলে আজীবন সফটওয়্যারটি ব্যবহার করতে পারবেন এবং ভবিষ্যতের সব সাধারণ আপডেট ও বাগ ফিক্স বিনামূল্যে পাবেন। কোনো লুকানো সাবস্ক্রিপশন বা রিনিউয়াল ফি নেই।\n\n"
                   . "আপনি কি সম্পূর্ণ লাইফটাইম লাইসেন্সটি আজই একটিভ করে নিতে চান স্যার?";
            self::logObjectionEvent($pdo, 'hidden_recurring_costs', $input, $reply, $tempBefore, $tempAfter, $psych);
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_TANIA,
                    'awareness_stage' => 'Most Aware (লাইফটাইম স্বচ্ছতা)',
                    'persuasion_technique' => 'Hormozi Absolute Price Transparency',
                    'suggestions' => ['লাইফটাইম লাইসেন্স নিতে চাই', 'বিকাশ নম্বর দিন', 'কী কী বোনাস পাব?'],
                    'open_whatsapp' => false,
                    'temperature' => $tempAfter
                ]
            ];
        }

        // 2. STAGE: MOST AWARE & IN-CHAT ORDER TAKING (or Upgrade Mode Explanation)
        if ($stage === self::STAGE_MOST_AWARE || preg_match('/(অর্ডার|কিনতে চাই|নিতে চাই|কিনব|নিব|বিকাশ|নগদ|টাকা|পেমেন্ট|payment|bkash|buy|order|price|খরচ|দাম|কত)/u', $text)) {
            if ($serverUpgradeMode) {
                $reply = $prefixCompliment
                       . "ধন্যবাদ স্যার AutoMovie Pro-তে আপনার গভীর আগ্রহের জন্য! 🚀\n\n"
                       . "আমাদের সফটওয়্যারে একটি অত্যন্ত বড় টেকনিক্যাল আপডেট এসেছে এবং হাই-স্পিড ভিডিও রেন্ডারিং সার্ভার শিফটিং ও ক্লাউড ক্লাস্টার মাইগ্রেশনের কাজ চলছে।\n\n"
                       . "আমাদের ইঞ্জিনিয়ারদের কাজের সর্বোচ্চ সুবিধা এবং সিস্টেমের শতভাগ স্থিতিশীলতা নিশ্চিত করার লক্ষ্যে **আগামী ১ সপ্তাহ নতুন ব্যবহারকারী এন্ট্রি সাময়িকভাবে বন্ধ রাখা হয়েছে**। তাই আগামী ১ সপ্তাহ পর আপনি সফটওয়্যারটি সরাসরি পারচেজ করতে পারবেন।\n\n"
                       . "তবে স্যার, আপনি যদি এক সপ্তাহ পর অগ্রাধিকার ভিত্তিতে (VIP Priority Access) সফটওয়্যারটি সবার আগে পেতে চান, তাহলে **আপনার হোয়াটসঅ্যাপ নম্বরটি এখানে লিখে দিন**। আমাদের সিস্টেমে আপনার নাম ও নম্বরটি রিজার্ভ রাখা হবে এবং সার্ভার লাইভ হওয়া মাত্রই আমাদের টিম সরাসরি আপনার সাথে যোগাযোগ করে স্পেশাল ডিসকাউন্ট সহ সফটওয়্যারটি বুঝিয়ে দেবে।\n\n"
                       . "এছাড়া অটো মুভি প্রো কীভাবে কাজ করে বা এর যেকোনো ফিচার সম্পর্কে জানতে চাইলে আমাকে নির্দ্বিধায় জিজ্ঞেস করুন, আমি বিস্তারিত বুঝিয়ে বলছি!";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_TANIA,
                        'awareness_stage' => 'Server Upgrade Waitlist (১ সপ্তাহ পজ)',
                        'persuasion_technique' => 'Server Migration Delay & VIP Lead Capture',
                        'suggestions' => ['আমার হোয়াটসঅ্যাপ নম্বর দিচ্ছি', 'সফটওয়্যারের ফিচারসমূহ বলুন', 'কম্পিউটার রিকোয়ারমেন্ট কী?'],
                        'open_whatsapp' => false
                    ]
                ];
            } else {
                $reply = $prefixCompliment
                       . "ধন্যবাদ স্যার! অর্ডার সম্পন্ন করা অত্যন্ত সহজ এবং চ্যাট থেকেই সম্পূর্ণ প্রক্রিয়া সম্পন্ন করা যায়। 🚀\n\n"
                       . "🎁 **আজকের স্পেশাল অফার ও বোনাস সামারি:**\n"
                       . "• প্যাকেজ: **AutoMovie Pro Video Studio (লাইফটাইম লাইসেন্স)**\n"
                       . "• মূল্য: মাত্র **৳৩,৯৯৯** (রেগুলার মূল্য ৳১০,০০০—আর মাত্র ৮-১০ দিন এই অফার কার্যকর থাকবে)\n"
                       . "• এক্সক্লুসিভ বোনাস: **৩য় আন্তর্জাতিক ভাষা (যেমন: হিন্দি/উর্দু - মূল্য ৳৪৯৯) সম্পূর্ণ ফ্রি!** এর মাধ্যমে ৩টি ফেসবুক পেজ, ৩টি ইউটিউব ও ৩টি টিকটকে একযোগে ভিডিও আপলোড করে ৯টি প্ল্যাটফর্ম থেকে ৩ গুণ বেশি প্যাসিভ ইনকাম নিশ্চিত করা যায়।\n\n"
                       . "💳 **পেমেন্ট অপশন (ক্যাশ আউট):**\n"
                       . "• বিকাশ এজেন্ট: `01756160993` (Zahid Pharmacy)\n"
                       . "• নগদ এজেন্ট: `01611-824811` (Simi Drug House)\n"
                       . "• রকেট এজেন্ট: `01756160993-5`\n\n"
                       . "💡 *বিশেষ সুবিধা:* সাময়িক বাজেট শর্ট থাকলে আপনি মাত্র **৳৫০০ বুকিং মানি** পাঠিয়ে ৩য় ভাষার বোনাস ও অফারটি লক করে রাখতে পারেন। বাকি টাকা কাল দিলেও চলবে।\n\n"
                       . "ক্যাশ আউট সম্পন্ন করার পর আপনার **TrxID (Transaction ID)** এবং প্রেরক নম্বরের শেষ ৪ ডিজিট এখানে লিখে দিন—আমি চ্যাট থেকেই আপনার লাইসেন্স ও ফাইল প্রস্তুত করে দিচ্ছি!\n\n"
                       . "অথবা সরাসরি ওয়েবসাইটে গিয়েও ফর্ম পূরণ করতে পারেন: https://automoviepro.com/order.php";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_TANIA,
                        'awareness_stage' => 'Most Aware (ইন-চ্যাট অর্ডার ফ্লো ও ৩য় ভাষা বোনাস)',
                        'persuasion_technique' => 'Frictionless Checkout & 9-Platform Value Stacking',
                        'suggestions' => ['বিকাশ এজেন্ট নম্বর কপি', '৫০০ টাকা বুকিং করব', 'TrxID সাবমিট করব', 'ওয়েবসাইট অর্ডার লিংক দিন'],
                        'open_whatsapp' => false
                    ]
                ];
            }
        }

        // 3. DISCOUNT OBJECTION & GATEKEEPER HANDLING
        if (preg_match('/(দাম বেশি|টাকা কম|ডিসকাউন্ট|ছাড় দিন|বাজেট নাই|কম রাখা যায় না|পরে নিব|discount|coupon)/u', $text)) {
            if ($serverUpgradeMode) {
                $reply = $prefixCompliment
                       . "আমি আপনার কথাটি একদম বুঝতে পারছি স্যার। তবে একটু লক্ষ্য করুন—বর্তমানে আমাদের হাই-স্পিড ভিডিও সার্ভার আপগ্রেড চলায় আগামী ১ সপ্তাহ কোনো নতুন পারচেজ নেওয়া হচ্ছে না।\n\n"
                       . "১ সপ্তাহ পর যখন রি-লঞ্চ হবে, তখন আপনি ওয়ান-টাইম লাইফটাইম ডিল হিসেবে এটি পাবেন যা বাইরে থেকে ভিডিও এডিটর রাখার তুলনায় ৯৫% সাশ্রয়ী।\n\n"
                       . "আপনি যদি ১ সপ্তাহ পর স্পেশাল রি-লঞ্চ ডিসকাউন্টে অগ্রাধিকার পেতে চান, তাহলে আপনার হোয়াটসঅ্যাপ নম্বরটি এখানে দিন, আমি প্রায়োরিটি লিস্টে এন্ট্রি করে রাখছি স্যার!";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_AYESHA,
                        'awareness_stage' => 'Server Upgrade Discount Waitlist',
                        'persuasion_technique' => 'Value Building & Waitlist Lead Capture',
                        'suggestions' => ['আমার হোয়াটসঅ্যাপ নম্বর দিচ্ছি', 'ফিচারসমূহ বিস্তারিত বলুন', 'ভিডিও কোয়ালিটি কেমন?'],
                        'open_whatsapp' => false
                    ]
                ];
            }
            $turns = (int) ($psych['turns_count'] ?? 1);
            if ($turns < 3) {
                // Deny cash discount on Turn 1-2, build massive value!
                $reply = $prefixCompliment
                       . "আমি আপনার কথাটি একদম বুঝতে পারছি স্যার। তবে একটু বিবেচনা করে দেখুন—একটি ফেসলেস চ্যানেল বা বিজনেসের জন্য বাইরে থেকে ভিডিও এডিটর বা ডিজাইনার রাখলে মাসে নূন্যতম ৳১০,০০০ থেকে ৳১৫,০০০ টাকা খরচ হয়ে যায়।\n\n"
                       . "সেখানে AutoMovie Pro সম্পূর্ণ লাইফটাইম ডিল (এককালীন মাত্র ৳৩,৯৯৯)। কোনো মাসিক ফি নেই এবং আজীবন আনলিমিটেড কনটেন্ট তৈরি করা যায়। এর ফলে আপনার প্রতি মাসের বিশাল খরচ ও সময় শতভাগ বেঁচে যাচ্ছে।\n\n"
                       . "সফটওয়্যারটির ১-ক্লিক ভিডিও তৈরি দেখার জন্য আপনি কি একটি ফ্রি লাইভ ডেমো দেখতে চান স্যার?";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_AYESHA,
                        'awareness_stage' => 'Value Building (নো ডিসকাউন্ট)',
                        'persuasion_technique' => 'Hormozi Alternative Cost Contrast',
                        'suggestions' => ['লাইভ ডেমো ভিডিও দেখান', 'পিসির কনফিগারেশন কি লাগবে?', 'অর্ডার করতে চাই']
                    ]
                ];
            } elseif ($turns >= 3 && $turns < 5) {
                // Turn 3-4: Offer Free Language Addon (worth ৳499) as Closing Gift!
                $reply = $prefixCompliment
                       . "স্যার, আপনার আন্তরিক আগ্রহের প্রতি সম্মান জানিয়ে আমাদের টিম থেকে আপনাকে একটি বিশেষ গিফট অফার করছি! ✨\n\n"
                       . "আজকে আপনি প্যাকেজটি অর্ডার করলে আমাদের **৳৪৯৯ মূল্যের ৩য় অতিরিক্ত আন্তর্জাতিক ভাষা (যেমন: হিন্দি বা উর্দু)** সম্পূর্ণ ফ্রিতে আপনার লাইসেন্সের সাথে যুক্ত করে দেওয়া হবে। এতে আপনি একই সাথে ৩টি ফেসবুক পেজ, ৩টি ইউটিউব ও ৩টি টিকটকে একযোগে ভিডিও আপলোড করে মোট **৯টি প্ল্যাটফর্ম থেকে ৩ গুণ বেশি প্যাসিভ ইনকাম** নিশ্চিত করতে পারবেন!\n\n"
                       . "আর যদি আজকে বাজেট শর্ট থাকে, আপনি মাত্র **৫০০ টাকা বুকিং দিয়ে** এই বোনাস ও অফারটি লক করে রাখতে পারেন। বাকি টাকা আগামীকাল দিলে চলবে স্যার।\n\n"
                       . "এই বোনাসটি কি আপনার জন্য সক্রিয় করে দেব স্যার?";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_TANIA,
                        'awareness_stage' => 'Value Stacking (৩য় ভাষা ফ্রি ও ৯ প্ল্যাটফর্ম বোনাস)',
                        'persuasion_technique' => 'Bonus Stacking, 9-Platform Reach & ৳500 Booking',
                        'suggestions' => ['বোনাস সহ অর্ডার করব', '৫০০ টাকা বুকিং করব', 'বিকাশ নম্বর দিন', 'পরে যোগাযোগ করব']
                    ]
                ];
            } else {
                // Turn 5+: Authorized Micro-Discount
                $coupon = $psych['authorized_coupon'] ?? 'VIP500';
                $reply = $prefixCompliment
                       . "স্যার, আপনার সাথে দীর্ঘক্ষণ কথা বলে বুঝতে পারছি আপনি সত্যিই কাজ করতে আগ্রহী। আপনার মতো একজন উদ্যমী ক্রিয়েটরের জন্য আমি আমাদের অ্যাডমিন থেকে বিশেষ অনুমতি নিয়েছি।\n\n"
                       . "আজকে অর্ডারের জন্য আপনার জন্য সিক্রেট কুপন কোড [**{$coupon}**] সক্রিয় করে দেওয়া হয়েছে। এটি ব্যবহারে আপনি সরাসরি **৳৫০০ নগদ ছাড়** পাবেন, সাথে ৩য় আন্তর্জাতিক ভাষার বোনাসটিও কার্যকর থাকবে!\n\n"
                       . "অর্ডার কনফার্ম করতে নিচের লিংকে ক্লিক করুন অথবা আমাকে বিকাশ TrxID দিন (অথবা মাত্র ৫০০ টাকা দিয়ে অফারটি লক করুন):\n"
                       . "👉 https://automoviepro.com/order.php?coupon={$coupon}";
                return [
                    'reply' => $reply,
                    'meta' => [
                        'selected_agent' => self::AGENT_TANIA,
                        'awareness_stage' => 'Authorized Micro-Discount',
                        'persuasion_technique' => 'Chris Voss Black Swan Concession',
                        'suggestions' => ['কুপন সহ এখনই অর্ডার করব', '৫০০ টাকা বুকিং নম্বর দিন', 'বিকাশ নম্বর দিন', 'WhatsApp-এ ফাইল দিন'],
                        'coupon_offered' => $coupon
                    ]
                ];
            }
        }

        // 4. TECHNICAL INQUIRIES (PC specs, Windows, RAM, GPU, API keys)
        if ($agent === self::AGENT_NIROB || preg_match('/(পিসি|ল্যাপটপ|কম্পিউটার|র‍্যাম|উইন্ডোজ|গ্রাফিক্স|api|ram|gpu|spec)/u', $text)) {
            $reply = $prefixCompliment
                   . "AutoMovie Pro অত্যন্ত লাইটওয়েট ও অপ্টিমাইজড করে তৈরি করা হয়েছে, তাই যেকোনো সাধারণ কম্পিউটারে অনায়াসে চলে।\n\n"
                   . "💻 **কম্পিউটার রিকোয়ারমেন্ট:**\n"
                   . "• অপারেটিং সিস্টেম: Windows 10 অথবা Windows 11 (64-bit)\n"
                   . "• র‍্যাম: নূন্যতম 4GB (8GB বা তদূর্ধ্ব হলে অত্যন্ত দ্রুত ভিডিও রেন্ডার হয়)\n"
                   . "• গ্রাফিক্স কার্ড: ডেডিকেটেড GPU বাধ্যতামূলক নয় (সাধারণ CPU দিয়েই ফুল ভিডিও তৈরি হয়)\n"
                   . "• ফ্রি স্পেস: মাত্র 5GB ডিস্ক স্পেস\n\n"
                   . "ইনস্টলেশন সম্পূর্ণ ১-ক্লিক পোর্টেবল। আপনার কম্পিউটারে কোনো কোডিং বা অতিরিক্ত সফটওয়্যার সেটআপ করতে হয় না।"
                   . $upgradeFooter;
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_NIROB,
                    'awareness_stage' => 'Solution Aware (টেকনিক্যাল নিশ্চয়তা)',
                    'persuasion_technique' => 'Friction Removal & Technical Certainty',
                    'suggestions' => ['ফ্রি ডেমো ভিডিও দেখান', 'ইনস্টল করতে কতক্ষণ লাগে?', 'কী কী এপিআই দরকার?'],
                    'open_whatsapp' => false
                ]
            ];
        }

        // 5. DEFAULT WARM CONSULTATIVE WELCOME (Dynamic First-Time vs Returning Visitor)
        $isReturning = !empty($psych['is_returning']) || ((int)($psych['turns_count'] ?? 0) > 1);
        if ($isReturning) {
            $reply = $prefixCompliment
                   . "আসসালামু আলাইকুম স্যার! AutoMovie Pro-তে আপনাকে আবারও দেখে খুব ভালো লাগল। 😊\n\n"
                   . "আশা করি আপনি ভালো আছেন। আপনি কি আমাদের ৩টি প্ল্যাটফর্ম (ফেসবুক, ইউটিউব, টিকটক) জুড়ে ৯টি চ্যানেলে ভিডিও অটো-আপলোড ও আজকের ৩য় ফ্রি আন্তর্জাতিক ভাষা বোনাসটি সম্পর্কে আরও জানতে চান, নাকি সরাসরি সফটওয়্যার লাইসেন্সটি আজই একটিভ করে নিতে চান?\n\n"
                   . "কোনো বিষয়ে বাড়তি প্রশ্ন থাকলে নিঃসঙ্কোচে বলুন, আমি সরাসরি বুঝিয়ে দিচ্ছি স্যার।"
                   . $upgradeFooter;
            return [
                'reply' => $reply,
                'meta' => [
                    'selected_agent' => self::AGENT_AYESHA,
                    'awareness_stage' => 'Returning Visitor Welcome (পুনরায় উষ্ণ সম্ভাষণ)',
                    'persuasion_technique' => 'Familiarity, Rapport & 9-Platform Income Reminder',
                    'suggestions' => ['আজকের ৩য় ভাষা বোনাসটি কীভাবে পাব?', '৫০০ টাকা দিয়ে বুকিং করব', 'সরাসরি বিকাশ নম্বর দিন'],
                    'open_whatsapp' => false
                ]
            ];
        }

        $reply = $prefixCompliment
               . "আসসালামু আলাইকুম স্যার! AutoMovie Pro-তে আপনাকে স্বাগতম। আমি আয়েশা, আপনার সিনিয়র কাস্টমার কেয়ার স্পেশালিস্ট। 😊\n\n"
               . "আমাদের এআই সফটওয়্যারের সাহায্যে আপনি কোনো ভিডিও এডিটিং জানা ছাড়াই মাত্র ১-ক্লিকে ফেসলেস ভাইরাল ভিডিও তৈরি করে YouTube, Facebook ও TikTok-এ স্বয়ংক্রিয়ভাবে শিডিউল করতে পারবেন এবং ঘরে বসেই সম্মানজনক প্যাসিভ ইনকাম নিশ্চিত করতে পারবেন।\n\n"
               . "আজকের স্পেশাল অফারে থাকছে লাইফটাইম লাইসেন্স এবং **৩য় অতিরিক্ত আন্তর্জাতিক ভাষা সম্পূর্ণ ফ্রি**! স্যার, আপনি কি সোশ্যাল মিডিয়া কনটেন্ট তৈরি করে প্যাসিভ ইনকাম করতে চাচ্ছেন, নাকি ব্যবসার সেলস বৃদ্ধি করতে চাচ্ছেন? আপনার মূল উদ্দেশ্য জানালে আমি সঠিক গাইডলাইন দিতে পারব।"
               . $upgradeFooter;
        return [
            'reply' => $reply,
            'meta' => [
                'selected_agent' => self::AGENT_AYESHA,
                'awareness_stage' => 'Unaware / Welcome (উষ্ণ সম্ভাষণ)',
                'persuasion_technique' => 'SPIN Diagnosis, Passive Income Dream & Warm Rapport',
                'suggestions' => ['সফটওয়্যারটির দাম কত?', '৩য় ভাষা ফ্রি অফারটি কীভাবে পাব?', 'ভিডিও স্টুডিও ডেমো দেখান'],
                'open_whatsapp' => false
            ]
        ];
    }
}
