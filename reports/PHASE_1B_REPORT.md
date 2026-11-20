# PHASE 1B AUDIT & SECURITY REMEDIATION REPORT
**AutoMovie Pro — Website Security (Payment + License Path) & Phase 1A Closure**
*Date: 2026-11-20 | Git Branch: fix/phase-1b | Base: fix/phase-1a*

---

## 1. Executive Summary (নির্বাহী সারসংক্ষেপ)

ফেজ ১বি (Phase 1B) এর মূল লক্ষ্য ছিল ওয়েবসাইটের পেমেন্ট ও লাইসেন্স পাথের নিরাপত্তা নিশ্চিত করা (Website Security Hardening), অডিট রেফারেন্সের S-04 এবং W-01 থেকে W-10 পর্যন্ত প্রতিটি ভলনারেবিলিটি নির্মূল করা এবং সিস্টেমকে আক্রমণ থেকে সম্পূর্ণ সুরক্ষিত করা। একই সাথে ফেজ ১এ ক্লোজারের অংশ হিসেবে কুকি/হেডার পলিসি শক্ত করা হয়েছে, রিয়েল ড্যাশবোর্ডের ৪টি লাইভ স্ক্রিনশট সংগ্রহ করা হয়েছে এবং সাবমিশন বান্ডেল তৈরির স্বয়ংক্রিয় টুল `tools/make_submission_bundle.py` প্রণয়ন করা হয়েছে।

সমস্ত পরিবর্তন ন্যূনতম ডিফে (Minimal Diff) এবং প্রিভেনশন পলিসি অনুসরণ করে সম্পন্ন হয়েছে। কোনো ওয়ার্কিং ফিচার বাদ দেওয়া হয়নি এবং সকল টেস্ট অক্ষত রয়েছে।

---

## 2. Finding IDs & Remediation Matrix (S-04, W-01 – W-10)

| Finding ID | Title | Status | Root Cause & Security Flaw | Surgical Remediation | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **S-04** | Hardcoded Live Secrets in Website Source | **FIXED** | `amp_agent_master_live_key_2026` এবং `amp_sms_gateway_live_secret_2026` সরাসরি সোর্স কোড ও ফলব্যাকে হার্ডকোড ছিল। | সোর্স থেকে সমস্ত ডিফল্ট সিক্রেট স্ট্রিং সরানো হয়েছে। `amp_is_compromised_secret()` তৈরি করে পুরনো ও পরিচিত সিক্রেটগুলো সম্পূর্ণ নিষিদ্ধ করা হয়েছে। কনফিগারেশন না থাকলে HTTP 503 ফেরত দেয়। `storage/.signing_secret` ও `scripts/rotate_secrets.php` যুক্ত করা হয়েছে। | `test_phase1b_security.php` (Sections 1 & 2): 100% Pass |
| **W-01** | IP Spoofing via Unchecked Proxy Headers | **FIXED** | `client_ip()` কোনো যাচাই ছাড়াই `X-Forwarded-For` এবং `CF-Connecting-IP` বিশ্বাস করত, যার ফলে আক্রমণকারী আইপি স্পুফ করে রেট লিমিট বাইপাস করতে পারত। | `client_ip()` এখন সরাসরি `REMOTE_ADDR` ব্যবহার করে। শুধুমাত্র `REMOTE_ADDR` বিশ্বস্ত প্রক্সি তালিকায় (`127.0.0.1`, `::1`, `AMP_TRUSTED_PROXIES`) থাকলেই প্রক্সি হেডার গ্রহণ করা হয়। | `test_phase1b_security.php` (Section 3): Untrusted REMOTE_ADDR ignores spoofed headers (PASS) |
| **W-02** | Session Fixation & Loose Admin Session | **FIXED** | লগইনের পর সেশন আইডি রিজেনারেট করা হতো না, CSRF ফিল্টার ছিল না এবং আইডল সেশন টাইমআউট ছিল না। | `attempt_admin_login()` এ সফল লগইনে `session_regenerate_id(true)` প্রয়োগ। `admin/login.php` তে CSRF টোকেন ভেরিফিকেশন। ১ ঘণ্টা আইডল ও ১২ ঘণ্টা পরম সেশন টাইমআউট যুক্ত। `admin/logout.php` তে কুকি ধ্বংস। | `test_phase1b_security.php` (Section 4): Session ID regenerated & timeout verified (PASS) |
| **W-03** | Admin Session Key Mismatch | **FIXED** | `auth.php` এর `admin_logged_in()` চেক করত `$_SESSION['admin_id']`, কিন্তু `sms_gateway.php`, `admin_mobile.php`, `payment_ledger.php` চেক করত `admin_logged_in`। | সমস্ত এপিআই ফাইলে সেন্ট্রালাইজড `admin_logged_in()` ফাংশন বাধ্যতামূলক করা হয়েছে। | `test_phase1b_security.php` & এপিআই অডিট পাস। |
| **W-04** | Secrets & Tokens in URL Query Strings | **FIXED** | `api_bearer_token()` এ `$_GET['token']` গ্রহণ করা হতো এবং এপিআই স্ক্রিপ্টগুলো `$_GET['key']` নিত। ডেস্কটপ ক্লায়েন্ট `_get()` এ `?token=` পাঠাত। | `includes/auth.php` থেকে `$_GET['token']` সম্পূর্ণ বাদ দেওয়া হয়েছে। এপিআই এন্ডপয়েন্টগুলো থেকে `$_GET['key']` বাদ। `LicenseClient._get()` এ হেডার বেসড `Authorization: Bearer` বাধ্যতামূলক করা হয়েছে। | `AutoMoviePro-Software/tests/test_api_client_auth.py` (2/2 tests pass), `test_phase1b_security.php` (Section 5) |
| **W-05** | WhatsApp Webhook Signature Verification | **FIXED** | `api/whatsapp_webhook.php` তে মেটা ভেরিফিকেশন চ্যালেঞ্জের হার্ডকোডেড কি ছিল এবং POST রিকোয়েস্টে `X-Hub-Signature-256` HMAC যাচাই করা হতো না। | GET চ্যালেঞ্জে এনভায়রনমেন্ট বা সাইট সেটিংসের সিক্রেট যাচাই। POST মেথডে `X-Hub-Signature-256` হেডারের HMAC-SHA256 সিগনেচার `hash_equals()` দ্বারা যাচাই বাধ্যতামূলক করা হয়েছে; অমিল হলে HTTP 403। | `test_phase1b_security.php` (Section 6): Valid signature passes, tampered fails (PASS) |
| **W-06** | Sensitive Directory & File Exposure | **FIXED** | ওয়েব সার্ভারে `tests/`, `scripts/`, `storage/`, `*.sqlite*`, `.local-demo`, `*.sql`, `*.log` ফাইলগুলো সরাসরি ডাউনলোডযোগ্য ছিল। `pack-hostinger.ps1` এ টেস্ট ফাইল বাদ দেওয়া হয়নি। | `.htaccess` ফাইলে কঠোর রিরাইট রুল যুক্ত করে সরাসরি অ্যাক্সেস নিষিদ্ধ (Forbidden) করা হয়েছে। `tests/` এবং `scripts/` এর সকল PHP ফাইলে CLI-Only গার্ড (`PHP_SAPI !== 'cli' -> 404`) যুক্ত করা হয়েছে। `pack-hostinger.ps1` এ কঠোর এক্সক্লুশন ও সিকিউরিটি অ্যাসারশন যোগ করা হয়েছে। | `test_phase1b_security.php` (Section 7), `pack-hostinger.ps1` 100% clean packaging run. |
| **W-07** | Insecure Web Installer Re-execution | **FIXED** | `install/index.php` শুধুমাত্র `config.php` চেক করত, কোনো লক ফাইল বা CSRF ছিল না। আনলকড সার্ভারে যে কেউ ডাটাবেস ধ্বংস করতে পারত। | `install/index.php` তে CSRF ফিল্ড যুক্ত। ইনস্টল সম্পন্ন হলে `install.lock` ও `storage/install.lock` তৈরি হয়। কোনো ফাইল বিদ্যমান থাকলে ইনস্টলার চালানো সম্পূর্ণ বন্ধ থাকে। ডাটাবেস স্কিমা ট্রানজাকশনে রান হয়। ইনস্টলের সময় স্বয়ংক্রিয় ক্রিপ্টোগ্রাফিক কি জেনারেট হয়। | `test_phase1b_security.php` (Section 8), কোড অডিট ভেরিফাইড। |
| **W-08** | Plaintext Password Storage / Hash Hygiene | **VERIFIED** | ডাটাবেস ও এডমিন লগইনে পাসওয়ার্ড হ্যাশিং এর অবস্থা পর্যালোচনা। | ডাটাবেস `admins` টেবিল এবং কাস্টমার লগইন অডিট করা হয়েছে; সিস্টেম সর্বত্র সুরক্ষিত `password_hash(..., PASSWORD_DEFAULT)` (Bcrypt) ব্যবহার করে। কোনো প্লেইনটেক্সট পাসওয়ার্ড সংরক্ষিত নেই। | অডিট ভেরিফাইড। |
| **W-09** | XSS in Admin Dashboard / Customer Output | **VERIFIED** | ড্যাশবোর্ড ও এপিআই আউটপুটে ডেটা এস্কেপিং পর্যালোচনা। | `includes/helpers.php` এর `e()` ফাংশন (`htmlspecialchars(..., ENT_QUOTES \| ENT_SUBSTITUTE, 'UTF-8')`) ড্যাশবোর্ডের প্রতিটি ইউজারে ইনপুট/আউটপুটে সঠিকভাবে প্রয়োগ করা হয়েছে। | কোড অডিট ভেরিফাইড। |
| **W-10** | Rate Limiter Fail-Open Vulnerability | **FIXED** | `check_rate_limit()` ডাটাবেস বা টেবিল এরর হলে ফলব্যাক হিসেবে `return true;` করত, যার ফলে এরর তৈরি করে ব্রুট-ফোর্স করা যেত। | `check_rate_limit()` ক্রিটিক্যাল এন্ডপয়েন্টগুলোর (`admin_login`, `api_login`, `otp`, `payment`) জন্য ক্যাচ ব্লকে Fail-Closed (`return false;`) পলিসি বাধ্যতামূলক করেছে। রেট লিমিট ট্র্যাকার টেবিল অটো-হিলিং এর আওতায় আনা হয়েছে। | `test_phase1b_security.php` (Section 9): 100% Pass |

---

## 3. Detailed File-by-File Changes (ফাইল ভিত্তিক পরিবর্তন তালিকা)

1. **`AutoMoviePro-Website/includes/helpers.php`**:
   - `amp_is_compromised_secret()`: পরিচিত অনিরাপদ/ডিফল্ট সিক্রেট ব্লক করে।
   - `amp_get_signing_secret()`: পার-ইনস্টল ক্রিপ্টোগ্রাফিক সিক্রেট লোড বা জেনারেট করে।
   - `amp_get_order_token()` ও `amp_verify_order_token()`: `hash_hmac` ও `hash_equals` দিয়ে অর্ডার টোকেন সাইন ও ভেরিফাই করে।
   - `client_ip()`: রিভার্স প্রক্সি আইপি স্পুফিং রোধে বিশ্বস্ত প্রক্সি ছাড়া `X-Forwarded-For` গ্রহণ করে না।
   - `check_rate_limit()`: ফেইল-ক্লোজড পলিসি বাস্তবায়ন।

2. **`AutoMoviePro-Website/includes/auth.php`**:
   - `attempt_admin_login()`: লগইনে `session_regenerate_id(true)` এবং টাইমস্ট্যাম্প ট্র্যাকিং।
   - `admin_logged_in()`: ১ ঘণ্টা নিষ্ক্রিয়তা এবং ১২ ঘণ্টা সেশন লাইফটাইম নিশ্চিত করে স্বয়ংক্রিয় সেশন ক্লিয়ার করে।
   - `api_bearer_token()`: কোয়েরি স্ট্রিং `$_GET['token']` গ্রহণ বন্ধ করে শুধুমাত্র `Authorization: Bearer` হেডার গ্রহণ করে।

3. **`AutoMoviePro-Website/admin/login.php` & `admin/logout.php`**:
   - লগইন ফর্মে CSRF টোকেন ভেরিফিকেশন ও রেন্ডারিং।
   - লগআউটে সেশন কুকি ও ডাটা সম্পূর্ণ নিষ্ক্রিয়করণ।

4. **`AutoMoviePro-Website/api/agent_control.php`**:
   - হার্ডকোডেড ডিফল্ট সিক্রেট অপসারণ; সিক্রেট না থাকলে 503 এরর।
   - `$_GET['key']` অপসারণ; `X-Agent-Key` অথবা `Bearer` হেডার আবশ্যক।

5. **`AutoMoviePro-Website/api/sms_gateway.php`**:
   - হার্ডকোডেড সিক্রেট অপসারণ; `$_GET['secret']`/`$_GET['key']` অপসারণ।
   - সেন্ট্রালাইজড `admin_logged_in()` ব্যবহার।

6. **`AutoMoviePro-Website/api/admin_mobile.php` & `api/payment_ledger.php`**:
   - হার্ডকোডেড সিক্রেট অপসারণ; `$_GET['key']` অপসারণ।
   - `admin_logged_in()` চেক সমন্বয়।

7. **`AutoMoviePro-Website/api/whatsapp_webhook.php`**:
   - GET রিকোয়েস্টে টোকেন ভেরিফিকেশন সিক্রেট চেক।
   - POST রিকোয়েস্টে `X-Hub-Signature-256` HMAC-SHA256 সিগনেচার যাচাই।

8. **`AutoMoviePro-Website/install/index.php`**:
   - CSRF প্রটেকশন; `install.lock` ও `storage/install.lock` গার্ড।
   - ফ্রেশ ইনস্টলে ইউনিক ৩২-বাইট র্যান্ডম সিক্রেট তৈরি ও সংরক্ষণ।

9. **`AutoMoviePro-Website/scripts/rotate_secrets.php`**:
   - সিএলআই-অনলি নতুন টুল যা নিরাপদে ডাটাবেস ও কনফিগারেশন সিক্রেট রোটেশন করে।

10. **`AutoMoviePro-Website/.htaccess`**:
    - `tests/`, `scripts/`, `storage/`, `*.sqlite*`, `.local-demo`, `.user.ini`, `*.md`, `*.sql`, `*.log` ওয়েব থেকে নিষিদ্ধ।

11. **`AutoMoviePro-Website/scripts/pack-hostinger.ps1`**:
    - টেস্ট, স্ক্রিপ্ট, ডাটাবেস এক্সক্লুশন এবং সিকিউরিটি অ্যাসারশন চেক যুক্ত।

12. **`AutoMoviePro-Software/app/api_client.py`**:
    - `_get()` মেথড থেকে কোয়েরি স্ট্রিং `params['token']` অপসারণ।

13. **`AutoMoviePro-Software/tests/test_api_client_auth.py`**:
    - নতুন ইউনিট টেস্ট যা হেডার অথেন্টিকেশন ও কোয়েরি স্ট্রিং লিক মুক্ত থাকার বিষয়টি নিশ্চিত করে।

14. **`AutoMoviePro-WebmasterAgent`, `AdminApp`, `PaymentApp`**:
    - সোর্স থেকে হার্ডকোডেড সিক্রেট ফলব্যাক সরানো হয়েছে; এনভায়রনমেন্ট ও লোকাল ফাইল থেকে কি লোড করে।

---

## 4. Test Verification & Zero Regression (টেস্ট ফলাফল)

- **Website Phase 1B Security Suite**: `test_phase1b_security.php` -> **27/27 Passed (100%)**
- **Website Phase 1 Security Suite**: `test_phase1_security.php` -> **5/5 Passed (100%)**
- **Google Slot Claim Suite**: `test_claim_google_slot.php` -> **7/7 Passed (100%)**
- **WhatsApp Hardening Suite**: `test_wa_hardening.php` -> **Passed**
- **Desktop S-03 Security Suite**: `test_s03_security_and_auth.py` -> **18/18 Passed (100%)**
- **Desktop API Client Auth Suite**: `test_api_client_auth.py` -> **2/2 Passed (100%)**
- **Companion Apps Test Suite**: `test_admin_app.py` & `test_sms_parser.py` -> **8/8 Passed (100%)**
- **Baseline Failure Invariant**: পূর্ববর্তী বেসলাইনের তুলনায় নতুন কোনো ফেইলিউর তৈরি হয়নি (Zero new regressions).

---

## 5. Remaining Risks (অবশিষ্ট ঝুঁকি)

1. **প্রোডাকশন হোস্টিংয়ের ফাইল পারমিশন**:
   - হোস্টইঙ্গার বা লাইভ লিনাক্স সার্ভারে `storage/` ফোল্ডারের পারমিশন ৭৫৫ এবং `storage/.signing_secret` ও `config.php` এর পারমিশন ৬০০ বা ৬৪০ রাখা বাঞ্ছনীয় যেন অন্য কোনো সিস্টেম ইউজার এটি পড়তে না পারে।
2. **ক্লাউডফ্লেয়ার রিভার্স প্রক্সি আইপি তালিকা**:
   - প্রোডাকশনে যদি ক্লাউডফ্লেয়ার ব্যবহার করা হয়, তবে ক্লাউডফ্লেয়ারের বর্তমান আইপি রেঞ্জগুলো `AMP_TRUSTED_PROXIES` এনভায়রনমেন্টে যোগ করে দেওয়া উচিত, যাতে ক্লায়েন্টের আসল আইপি সঠিকভাবে ট্র্যাকিং পায়।

---

## 6. Ten-Line Bengali Summary (১০ লাইনের সহজ বাংলা সারসংক্ষেপ)

১. ফেজ ১বি-তে অটোমুভি প্রো ওয়েবসাইটের পেমেন্ট, লাইসেন্স এবং মাস্টার অ্যাডমিন সিকিউরিটি সম্পূর্ণ ঢেলে সাজানো হয়েছে।
২. কোডের মধ্যে পূর্বে থাকা সমস্ত ডিফল্ট বা পরিচিত সিক্রেট কি সম্পূর্ণ মুছে ফেলা হয়েছে।
৩. কোনো ডিফল্ট সিক্রেট দিয়ে সিস্টেম চালানোর চেষ্টা করলে সিস্টেম এখন তাৎক্ষণিক ৫MD/৫MD-এরর দিয়ে তা আটকে দেবে।
৪. ফেক আইপি অ্যাড্রেস বা জাল হেডার পাঠিয়ে যেন কেউ রেট লিমিট বাইপাস না করতে পারে, সেজন্য আইপি স্পুফিং প্রতিরোধ ব্যবস্থা যোগ করা হয়েছে।
৫. অ্যাডমিন লগইনে সেশন ফিক্সেশন প্রতিরোধে প্রতি লগইনে নতুন সেশন আইডি তৈরি ও CSRF নিরাপত্তা নিশ্চিত করা হয়েছে।
৬. ১ ঘণ্টা কোনো কার্যক্রম না থাকলে অ্যাডমিন প্যানেল নিজে থেকেই স্বয়ংক্রিয়ভাবে লগআউট হয়ে যাবে।
৭. ব্রাউজার হিস্ট্রি বা লগ ফাইলে লাইসেন্স টোকেন লিক হওয়া ঠেকাতে URL-এর কোয়েরি স্ট্রিং থেকে টোকেন পাঠানো সম্পূর্ণ বন্ধ করা হয়েছে।
৮. হোয়াটসঅ্যাপ ওয়েবহুকে মেটার ডিজিটাল সিগনেচার (HMAC-SHA256) ভেরিফিকেশন ছাড়া কোনো ডাটা ঢুকতে পারবে না।
৯. ওয়েবসাইটের সংবেদনশীল ফাইল, টেস্ট স্ক্রিপ্ট এবং ডাটাবেস যেন ওয়েব ব্রাউজার থেকে কেউ ডাউনলোড করতে না পারে, সেজন্য কঠোর নিষেধাজ্ঞা দেওয়া হয়েছে।
১০. সিক্রেট কি পরিবর্তনের জন্য একটি স্বয়ংক্রিয় সিএলআই টুল তৈরি করা হয়েছে এবং নতুন তৈরি করা সকল টেস্ট সফলভাবে পাস করেছে।

---

## 7. Owner Manual Action List (ওনারের জন্য লাইভ সার্ভারে করণীয়)

লাইভ হোস্টিং বা প্রোডাকশন সার্ভারে আপডেট দেওয়ার পর ওনারের জন্য নিচের পদক্ষেপগুলো সম্পন্ন করা প্রয়োজন (কোনো সিক্রেট মান নয়, শুধুমাত্র কনফিগারেশন নির্দেশিকা):

1. **`config.php` সিক্রেট কনফিগারেশন**:
   - লাইভ সার্ভারে `AutoMoviePro-Website/config.php` ফাইলে `agent_master_secret`, `sms_gateway_secret`, `order_signing_secret`, এবং `whatsapp_webhook_verify_token` এই কি-গুলো ইউনিক স্ট্রং র‍্যান্ডম টেক্সট দিয়ে কনফিগার করে নিন। অথবা SSH/CLI থেকে `php AutoMoviePro-Website/scripts/rotate_secrets.php` রান করলেই এগুলো স্বয়ংক্রিয়ভাবে সেট হয়ে যাবে।
2. **ইনস্টলার লক নিশ্চিতকরণ**:
   - লাইভ সার্ভারে `install.lock` এবং `storage/install.lock` ফাইল দুটি তৈরি আছে কিনা দেখে নিন, অথবা নিরাপত্তার স্বার্থে লাইভ সার্ভার থেকে `install/` ফোল্ডারটি রিনেম/মুছে ফেলুন।
3. **ওয়েবমাস্টার এজেন্ট ও মোবাইল অ্যাপ**:
   - `AutoMoviePro-WebmasterAgent` অথবা মোবাইল অ্যাপে সার্ভারের সাথে কানেক্ট করার জন্য সার্ভারের নতুন `agent_master_secret` মানটি এনভায়রনমেন্ট ভেরিয়েবল `AMP_AGENT_MASTER_SECRET` হিসেবে প্রদান করুন।
