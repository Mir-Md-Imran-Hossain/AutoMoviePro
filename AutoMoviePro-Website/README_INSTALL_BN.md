# AutoMovie Pro Website — হোস্টিং ইনস্টল গাইড (বাংলা)

**ডোমেইন:** https://automoviepro.com

বিস্তারিত ক্লিক-বাই-ক্লিক: দেখুন `HOSTINGER_DEPLOY_BN.md`

## কী আপলোড করবেন
`scripts/pack-hostinger.ps1` চালিয়ে যে ZIP তৈরি হয়, সেটা Hostinger **File Manager → public_html**-এ আপলোড করে Extract করুন।  
`config.local.php` ও `.local-demo` আপলোড করবেন না।

## ধাপ (সংক্ষেপ)
1. Databases → MySQL তৈরি (নাম, ইউজার, পাস মনে রাখুন)।
2. File Manager → `public_html` → ZIP আপলোড → Extract। ডিফল্ট `index.html` মুছুন।
3. ব্রাউজার: `https://automoviepro.com/install/`
4. DB তথ্য দিন। **Site URL:** `https://automoviepro.com`
5. অ্যাডমিন ইউজার/পাস, WhatsApp (`8801968111593`) → **ইনস্টল করুন**।
6. `/admin/login.php` দিয়ে লগইন।
7. `install/` ফোল্ডার ডিলিট করুন।
8. চেক: `https://automoviepro.com/api/health.php` → `"ok": true`
9. `downloads/` এ `.exe` রাখুন যখন রেডি। Binance QR: `assets/img/binance-pay-qr.png`
10. (ঐচ্ছিক) `config.php` এ WhatsApp Cloud API টোকেন।

## ডেস্কটপ অ্যাপ
API Base URL: `https://automoviepro.com`  
কাস্টমার লগইন ID/পাস অ্যাডমিন **Approve**-এর পর WhatsApp/অ্যাডমিন স্ক্রিনে পাবে। কেনা ভাষা অ্যাপে অটো আনলক হয়।

## কাস্টমার ফ্লো
অর্ডার → WhatsApp Txn/স্ক্রিনশট → অ্যাডমিন Approve → লগইন + ডাউনলোড মেসেজ।
