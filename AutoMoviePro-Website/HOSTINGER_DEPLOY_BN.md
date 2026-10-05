# Hostinger-এ AutoMovie Pro ওয়েবসাইট লাইভ করা (ক্লিক বাই ক্লিক)

ডোমেইন: **https://automoviepro.com**  
ZIP: `AutoMoviePro-Website/dist/automoviepro-website-hostinger.zip` (প্যাক স্ক্রিপ্ট চালালে তৈরি হয়)

হোস্টিং প্যানেলে ডোমেইন “connecting / up to 24 hours” দেখালেও **ফাইল ও ডাটাবেস আগেই সেট** করা যায়। সাইট পাবলিক হতে DNS + SSL শেষ হওয়া পর্যন্ত অপেক্ষা।

---

## ০) আগে যা যা রাখবেন

- Hostinger লগইন (যে স্ক্রিনে `automoviepro.com` Dashboard)
- একটা শক্তিশালী অ্যাডমিন পাসওয়ার্ড (লিখে রাখুন)
- Binance Pay QR থাকলে সেই PNG (`binance-pay-qr.png`) — না থাকলে পরে আপলোড
- সফটওয়্যার `.exe` থাকলে `AutoMoviePro-Setup.exe` — না থাকলে পরে `downloads/` এ দিবেন

---

## ১) MySQL ডাটাবেস তৈরি

1. বাম মেনুতে **Databases** ক্লিক করুন।
2. **Create Database** / **MySQL Databases** খুলুন।
3. Database name দিন, উদাহরণ: `automoviepro` (Hostinger প্রিফিক্স যোগ করতে পারে, পুরো নাম কপি করুন)।
4. **Create User** — ইউজারনেম ও শক্ত পাসওয়ার্ড দিন। পাসওয়ার্ড সেভ করুন।
5. ইউজারকে ওই ডাটাবেসে **All Privileges** দিয়ে **Attach / Add user to database** করুন।
6. তিনটা জিনিস নোট করুন:
   - DB name (প্রিফিক্সসহ)
   - DB user (প্রিফিক্সসহ)
   - DB password
   - Host সাধারণত `localhost`

---

## ২) ওয়েবসাইট ZIP আপলোড (File Manager)

1. বাম মেনু **Files** → **File manager** → **Open**।
2. `automoviepro.com` সিলেক্ট করে ভিতরে ঢুকুন।
3. সাধারণত ফোল্ডার: **public_html** — এখানেই ওয়েবসাইটের রুট।
4. Hostinger ডিফল্ট `default.php` / `index.html` থাকলে সিলেক্ট করে **Delete** (নিজের সাইট চাপা পড়বে না)।
5. উপরের **Upload** ক্লিক করুন।
6. `automoviepro-website-hostinger.zip` সিলেক্ট করে আপলোড শেষ হতে দিন।
7. ZIP ফাইলে রাইট-ক্লিক (বা সিলেক্ট) → **Extract**।
8. Extract destination: **public_html** (বর্তমান ফোল্ডার)।
9. এক্সট্রাক্টের পর দেখুন এই ফাইলগুলো `public_html`-এর **সরাসরি ভিতরে** আছে (সাবফোল্ডার `AutoMoviePro-Website` এর ভিতরে নয়):
   - `index.php`
   - `order.php`
   - `.htaccess`
   - `api/`
   - `admin/`
   - `install/`
   - `assets/`
10. যদি এক্সট্রাক্ট হয়ে `public_html/AutoMoviePro-Website/index.php` হয়, তাহলে সেই ফোল্ডারের **সব ফাইল সিলেক্ট** করে `public_html`-এ **Move** করুন।
11. ZIP ফাইল ডিলিট করতে পারেন।
12. এই ফাইলগুলো যেন **আপলোড না হয়**: `config.local.php`, `.local-demo` — থাকলে ডিলিট করুন।

---

## ৩) ইনস্টলার চালান

1. ব্রাউজারে যান: `https://automoviepro.com/install/`  
   DNS এখনো না চললে Hostinger **Preview** বা temporary URL ব্যবহার করুন, কিন্তু **Site URL** ঘরে লিখবেনই: `https://automoviepro.com`
2. ফর্ম:
   - DB Host: `localhost`
   - DB Name / User / Password: ধাপ ১-এর নোট
   - Site URL: `https://automoviepro.com`
   - Admin Username: `admin` (বা আপনার পছন্দ)
   - Admin Password: শক্ত পাসওয়ার্ড
   - WhatsApp: `8801684355055`
3. **ইনস্টল করুন** চাপুন।
4. সফল হলে **অ্যাডমিন লগইন** লিংকে যান: `/admin/login.php`

ইনস্টল এরর এলে: DB নাম/ইউজার প্রিফিক্স ভুল, অথবা ইউজারকে ডাটাবেসে অ্যাটাচ করা হয়নি।

---

## ৪) ইনস্টল ফোল্ডার মুছুন (জরুরি)

1. File Manager → `public_html/install`
2. ফোল্ডার সিলেক্ট → **Delete**

এটা না মুছলে কেউ আবার ইনস্টলার খোলার চেষ্টা করতে পারে।

---

## ৫) SSL ও ডোমেইন

1. Dashboard-এ **SSL** সবুজ/অ্যাকটিভ না হলে **Security → SSL** থেকে ফ্রি SSL ইন্সটল করুন।
2. “Your domain is connecting” ব্যানার থাকলে ২৪ ঘণ্টা পর্যন্ত অপেক্ষা। পরে `https://automoviepro.com` খুলুন — লক আইকন থাকতে হবে।
3. `www` অটো-রিডিরেক্ট হবে `https://automoviepro.com`-এ।

---

## ৬) হেলথ চেক

ব্রাউজারে খুলুন:

`https://automoviepro.com/api/health.php`

আশা করা JSON:

```json
{"ok": true, "installed": true, "site": "https://automoviepro.com"}
```

`not_installed` বা `db_failed` এলে config.php / ডাটাবেস আবার চেক করুন।

হোমপেজ: `https://automoviepro.com` — লোগো, কভার, ফিচার ছবি দেখা যাবে।  
অর্ডার: `https://automoviepro.com/order.php`

---

## ৭) অ্যাডমিন প্যানেল

1. `https://automoviepro.com/admin/login.php`
2. ইনস্টলের ইউজার/পাস দিন।
3. **ওয়েবসাইট CMS** — দাম ৳২৯৯৮ / অ্যাডঅন ৳৪৯৯ ঠিক আছে কিনা দেখুন।
4. **প্রোমো লিংক** — চাইলে YouTube/Facebook চ্যানেল URL দিন (অ্যাপে দেখাবে)।
5. Binance QR: File Manager-এ `public_html/assets/img/binance-pay-qr.png` আপলোড করুন।

---

## ৮) সফটওয়্যার `.exe` (যখন রেডি)

1. File Manager → `public_html/downloads/`
2. `AutoMoviePro-Setup.exe` আপলোড করুন।
3. লিংক: `https://automoviepro.com/downloads/AutoMoviePro-Setup.exe`

কাস্টমার অ্যাপ্রুভ হলে WhatsApp মেসেজে এই লিংক যায়।

---

## ৯) কাস্টমার ফ্লো (সাবস্ক্রিপশন)

1. কাস্টমার সাইট থেকে **অর্ডার** করে পেমেন্ট + Txn ID WhatsApp-এ পাঠায়।
2. আপনি **অ্যাডমিন → পেমেন্ট কিউ → Approve**।
3. সিস্টেম দেয়: Login ID (`AMP…`) + পাসওয়ার্ড, এবং কেনা ভাষাগুলো আনলক করে (ইংরেজি + পার্সোনাল + অ্যাডঅন)।
4. WhatsApp আউটবক্সে মেসেজ লগ হয়। Cloud API না থাকলে আপনি নিজে সেই ID/পাস কাস্টমারকে পাঠাবেন (Approve স্ক্রিনেও দেখায়)।
5. বাড়তি ভাষা পরে কিনলে: **অ্যাডমিন → ভাষা কিউ → Approve**। কাস্টমার অ্যাপে Language Sync চাপবে।

---

## ১০) ডেস্কটপ অ্যাপ কানেক্ট

1. অ্যাপ খুলুন।
2. **API Base URL:** `https://automoviepro.com` (শেষে `/` বা `/api` নয়)।
3. Login ID + Password দিন → লগইন।
4. সফল হলে ওয়েবসাইট থেকে `unlocked` ভাষা অ্যাপে চলে আসে।
5. চ্যানেল সেটআপে ওই ভাষাগুলোই ব্যবহার হবে।

চেক (অ্যাডমিন): **কাস্টমার** লিস্টে heartbeat সময় আপডেট হয় (অ্যাপ চালু থাকলে ~৫ মিনিট পর পর)।  
**API লগ:** `login_ok`, `me`, `heartbeat`, `jobs_sync` দেখা যাবে।

---

## সমস্যা হলে

| লক্ষণ | কী করবেন |
|---|---|
| হোমপেজ Hostinger ডিফল্ট পেজ | `public_html/index.php` আছে কিনা; ডিফল্ট `index.html` মুছুন |
| `/install/` ৪০৪ | ZIP ভুল ফোল্ডারে এক্সট্রাক্ট |
| ইনস্টল DB error | ইউজারকে ডাটাবেসে privilege দিন; নাম প্রিফিক্সসহ |
| অ্যাপ `unauthorized` | API URL `https://automoviepro.com`; কাস্টমার status `active` |
| অ্যাপ `non_json_…` | এখনো DNS/SSL হয়নি, বা `public_html` ভুল |
| ভাষা অ্যাপে নেই | পেমেন্ট Approve হয়েছে কিনা; অ্যাপে Language Sync / রি-লগইন |
