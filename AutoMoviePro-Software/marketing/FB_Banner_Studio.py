import os
import time
import base64
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"E:\AI Assistant\Automations\Generated_Banners"
os.makedirs(OUTPUT_DIR, exist_ok=True)
LOGO_PATH = r"E:\AI Assistant\Automations\logo_automovie_transparent.png"

with open(LOGO_PATH, "rb") as f:
    LOGO_BASE64 = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"

# ==============================================================================
# Modern High-Converting HTML Marketing Banner Templates
# Fully Updated with Correct Official Numbers, Cash Out Agents & Personal bKash/Nagad
# ==============================================================================

SHARED_FOOTER_HTML = """
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
"""

TEMPLATES = [
    # 1. Lifetime Deal & Software Core Features Banner
    {
        "id": "banner_lifetime_deal",
        "html": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@600;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 85% 15%, rgba(99, 102, 241, 0.25) 0%, transparent 50%),
                radial-gradient(circle at 10% 90%, rgba(16, 185, 129, 0.2) 0%, transparent 40%),
                #090D16;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 50px;
    position: relative;
    overflow: hidden;
  }
  .bg-grid {
    position: absolute; inset: 0;
    background-image: linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px),
                      linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
  }
  .header { display: flex; justify-content: space-between; align-items: center; z-index: 2; }
  .brand { display: flex; align-items: center; gap: 15px; }
  .brand-logo-img {
    width: 48px; height: 48px; object-fit: contain;
    filter: drop-shadow(0 0 16px rgba(99, 102, 241, 0.7));
    border: none; background: transparent;
  }
  .brand-name { font-family: 'Inter', sans-serif; font-size: 28px; font-weight: 800; letter-spacing: -0.5px; }
  .brand-name span { color: #818CF8; }
  .ltd-badge {
    background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.5);
    color: #F87171; padding: 8px 18px; border-radius: 30px; font-weight: 700; font-size: 16px;
    display: flex; align-items: center; gap: 8px;
  }
  .content { display: flex; justify-content: space-between; align-items: center; z-index: 2; margin: 15px 0; }
  .main-info { max-width: 650px; }
  .tagline { color: #38BDF8; font-size: 20px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .headline { font-size: 44px; font-weight: 700; line-height: 1.25; margin-bottom: 20px; }
  .headline span { background: linear-gradient(90deg, #60A5FA, #A78BFA); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .features-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .feature-item {
    background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(10px); padding: 12px 16px; border-radius: 12px;
    display: flex; align-items: center; gap: 12px; font-size: 17px; font-weight: 600;
  }
  .feature-icon { color: #34D399; font-size: 18px; }
  .price-card {
    background: linear-gradient(145deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
    border: 1px solid rgba(99, 102, 241, 0.4);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), 0 0 30px rgba(99, 102, 241, 0.2);
    border-radius: 24px; padding: 30px 35px; text-align: center; width: 380px;
  }
  .price-title { color: #94A3B8; font-size: 17px; font-weight: 600; text-transform: uppercase; margin-bottom: 6px; }
  .old-price { color: #64748B; font-size: 20px; text-decoration: line-through; }
  .price-amount { font-family: 'Inter', sans-serif; font-size: 54px; font-weight: 900; color: #38BDF8; margin: 2px 0; }
  .price-sub { color: #10B981; font-size: 15px; font-weight: 700; margin-bottom: 18px; }
  .cta-btn {
    background: linear-gradient(135deg, #3B82F6, #6366F1); color: #fff;
    padding: 12px; border-radius: 12px; font-weight: 700; font-size: 17px;
    display: block; box-shadow: 0 10px 20px rgba(59, 130, 246, 0.4);
  }
  .footer {
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(255, 255, 255, 0.12); padding-top: 14px; z-index: 2;
  }
  .contact-col { display: flex; align-items: center; gap: 8px; color: #E2E8F0; font-size: 16px; font-weight: 700; }
  .contact-col span { color: #22C55E; font-size: 18px; }
  .pay-col {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 6px 14px; border-radius: 8px; color: #CBD5E1; font-size: 13.5px; display: flex; gap: 12px;
  }
  .pay-col b { color: #38BDF8; font-weight: 700; }
  .web-link { font-family: 'Inter', sans-serif; color: #38BDF8; font-size: 18px; font-weight: 800; }
</style>
</head>
<body>
  <div class="bg-grid"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-name">AutoMovie <span>Pro</span></div>
    </div>
    <div class="ltd-badge">🔥 সীমিত সময়ের লাইফটাইম অফার</div>
  </div>
  <div class="content">
    <div class="main-info">
      <div class="tagline">১০০% সম্পূর্ণ অটোমেটেড কন্টেন্ট ক্রিয়েশন প্ল্যাটফর্ম</div>
      <div class="headline">একবার রান করলেই স্ক্রিপ্ট থেকে পাবলিশ — <span>ফুল অটোপাইলট!</span></div>
      <div class="features-grid">
        <div class="feature-item"><span class="feature-icon">✓</span> ট্রেন্ডিং টপিক ও সিনেমাটিক স্ক্রিপ্ট</div>
        <div class="feature-item"><span class="feature-icon">✓</span> মানুষের মতো ন্যাচারাল ভয়েসওভার</div>
        <div class="feature-item"><span class="feature-icon">✓</span> ৫০+ ভাষায় অটো ডাবিং ও লোকালাইজেশন</div>
        <div class="feature-item"><span class="feature-icon">✓</span> ফেসবুক ও ইউটিউবে অটো আপলোড ও এসইও</div>
      </div>
    </div>
    <div class="price-card">
      <div class="price-title">এককালীন লাইফটাইম ডিল</div>
      <div class="old-price">৳৮,৯৯৯</div>
      <div class="price-amount">৳২,৯৯৮</div>
      <div class="price-sub">আজীবন ব্যবহার • নো মান্থলি সাবস্ক্রিপশন</div>
      <div class="cta-btn">অর্ডার করতে ভিজিট করুন</div>
    </div>
  </div>
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
</body>
</html>"""
    },

    # 2. Google AI Pro Accounts Banner
    {
        "id": "banner_google_pro",
        "html": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@600;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 15% 20%, rgba(234, 67, 53, 0.15) 0%, transparent 40%),
                radial-gradient(circle at 85% 20%, rgba(66, 133, 244, 0.2) 0%, transparent 50%),
                radial-gradient(circle at 50% 90%, rgba(52, 168, 83, 0.15) 0%, transparent 40%),
                #0A0F1D;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 50px;
    position: relative;
    overflow: hidden;
  }
  .bg-grid {
    position: absolute; inset: 0;
    background-image: linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px),
                      linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
  }
  .header { display: flex; justify-content: space-between; align-items: center; z-index: 2; }
  .brand { display: flex; align-items: center; gap: 15px; }
  .logo-badge {
    background: #fff; width: 44px; height: 44px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 20px rgba(66, 133, 244, 0.5); font-size: 24px;
  }
  .brand-name { font-family: 'Inter', sans-serif; font-size: 26px; font-weight: 800; }
  .brand-name span { color: #4285F4; }
  .shield-badge {
    background: rgba(52, 168, 83, 0.15); border: 1px solid rgba(52, 168, 83, 0.4);
    color: #34A853; padding: 8px 18px; border-radius: 30px; font-weight: 700; font-size: 16px;
  }
  .title-section { text-align: center; z-index: 2; margin: 5px 0; }
  .tagline { color: #FBBC05; font-size: 19px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px; }
  .headline { font-size: 40px; font-weight: 700; }
  .headline span { color: #4285F4; }
  .cards-row { display: flex; justify-content: center; gap: 20px; z-index: 2; margin: 10px 0; }
  .plan-card {
    background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(15px); border-radius: 20px; padding: 22px 25px;
    width: 320px; text-align: center;
  }
  .plan-card.featured {
    background: linear-gradient(145deg, rgba(66, 133, 244, 0.15), rgba(15, 23, 42, 0.8));
    border: 2px solid #4285F4; box-shadow: 0 10px 30px rgba(66, 133, 244, 0.3);
    position: relative;
  }
  .popular-tag {
    position: absolute; top: -14px; left: 50%; transform: translateX(-50%);
    background: #4285F4; color: #fff; font-size: 12px; font-weight: 800;
    padding: 3px 12px; border-radius: 12px; text-transform: uppercase;
  }
  .plan-duration { font-size: 20px; font-weight: 700; color: #E2E8F0; margin-bottom: 4px; }
  .plan-price { font-family: 'Inter', sans-serif; font-size: 42px; font-weight: 900; color: #38BDF8; margin: 4px 0; }
  .plan-feature { color: #94A3B8; font-size: 14.5px; margin: 3px 0; }
  .footer {
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(255, 255, 255, 0.12); padding-top: 14px; z-index: 2;
  }
  .contact-col { display: flex; align-items: center; gap: 8px; color: #E2E8F0; font-size: 16px; font-weight: 700; }
  .contact-col span { color: #22C55E; font-size: 18px; }
  .pay-col {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 6px 14px; border-radius: 8px; color: #CBD5E1; font-size: 13.5px; display: flex; gap: 12px;
  }
  .pay-col b { color: #38BDF8; font-weight: 700; }
  .web-link { font-family: 'Inter', sans-serif; color: #38BDF8; font-size: 18px; font-weight: 800; }
</style>
</head>
<body>
  <div class="bg-grid"></div>
  <div class="header">
    <div class="brand">
      <div class="logo-badge">☁️</div>
      <div class="brand-name">Google <span>AI Pro</span> Account</div>
    </div>
    <div class="shield-badge">🛡️ ১০০% অফিসিয়াল ও ভেরিফাইড গ্যারান্টি</div>
  </div>
  <div class="title-section">
    <div class="tagline">আনলিমিটেড এআই ও ক্লাউড স্টোরেজ সল্যুশন</div>
    <div class="headline">প্রিমিয়াম কাজের জন্য সেরা <span>গুগল প্রো প্যাকেজ</span></div>
  </div>
  <div class="cards-row">
    <div class="plan-card">
      <div class="plan-duration">১ মাস প্যাকেজ</div>
      <div class="plan-price">৳১২০</div>
      <div class="plan-feature">✓ আনলিমিটেড AI অ্যাক্সেস</div>
      <div class="plan-feature">✓ 150GB গুগল ক্লাউড ভল্ট</div>
      <div class="plan-feature">✓ ইনস্ট্যান্ট অ্যাক্টিভেশন</div>
    </div>
    <div class="plan-card featured">
      <div class="popular-tag">সবচেয়ে জনপ্রিয়</div>
      <div class="plan-duration">১ বছর (১২ মাস)</div>
      <div class="plan-price">৳৯৯৯</div>
      <div class="plan-feature">✓ আনলিমিটেড AI অ্যাক্সেস</div>
      <div class="plan-feature">✓ 150GB গুগল ক্লাউড ভল্ট</div>
      <div class="plan-feature">✓ ৩৬৫ দিন ফুল গ্যারান্টি</div>
    </div>
    <div class="plan-card">
      <div class="plan-duration">১.৫ বছর (১৮ মাস)</div>
      <div class="plan-price">৳১,২৯৯</div>
      <div class="plan-feature">✓ আনলিমিটেড AI অ্যাক্সেস</div>
      <div class="plan-feature">✓ 150GB গুগল ক্লাউড ভল্ট</div>
      <div class="plan-feature">✓ সর্বোচ্চ সাশ্রয়ী স্পেশাল ডিল</div>
    </div>
  </div>
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
</body>
</html>"""
    },

    # 3. YouTube Faceless Automation Blueprint Banner
    {
        "id": "banner_youtube_faceless",
        "html": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@600;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 20% 20%, rgba(239, 68, 68, 0.25) 0%, transparent 40%),
                radial-gradient(circle at 80% 80%, rgba(59, 130, 246, 0.2) 0%, transparent 40%),
                #080C14;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 50px;
    position: relative;
    overflow: hidden;
  }
  .header { display: flex; justify-content: space-between; align-items: center; z-index: 2; }
  .brand { display: flex; align-items: center; gap: 14px; }
  .brand-logo-img {
    width: 48px; height: 48px; object-fit: contain;
    filter: drop-shadow(0 0 16px rgba(239, 68, 68, 0.7));
    border: none; background: transparent;
  }
  .brand-name { font-family: 'Inter', sans-serif; font-size: 26px; font-weight: 800; }
  .brand-name span { color: #EF4444; }
  .yt-badge {
    background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4);
    color: #EF4444; padding: 8px 18px; border-radius: 30px; font-weight: 700; font-size: 16px;
    display: flex; align-items: center; gap: 8px;
  }
  .content { display: flex; justify-content: space-between; align-items: center; z-index: 2; margin: 15px 0; }
  .main-info { max-width: 680px; }
  .tagline { color: #EF4444; font-size: 20px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .headline { font-size: 44px; font-weight: 700; line-height: 1.25; margin-bottom: 20px; }
  .headline span { color: #F87171; }
  .steps-box { display: flex; flex-direction: column; gap: 10px; }
  .step-item {
    background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 11px 18px; border-radius: 12px; display: flex; align-items: center; gap: 14px; font-size: 17px; font-weight: 600;
  }
  .step-num { background: #EF4444; color: #fff; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-family: 'Inter'; font-size: 14px; font-weight: 800; }
  .price-card {
    background: linear-gradient(145deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
    border: 1px solid rgba(239, 68, 68, 0.4);
    box-shadow: 0 20px 40px rgba(0,0,0,0.5), 0 0 30px rgba(239, 68, 68, 0.2);
    border-radius: 24px; padding: 30px 35px; text-align: center; width: 380px;
  }
  .price-title { color: #94A3B8; font-size: 17px; font-weight: 600; text-transform: uppercase; margin-bottom: 6px; }
  .price-amount { font-family: 'Inter', sans-serif; font-size: 54px; font-weight: 900; color: #F87171; margin: 2px 0; }
  .price-sub { color: #34D399; font-size: 15px; font-weight: 700; margin-bottom: 18px; }
  .cta-btn {
    background: linear-gradient(135deg, #EF4444, #DC2626); color: #fff;
    padding: 12px; border-radius: 12px; font-weight: 700; font-size: 17px;
    display: block; box-shadow: 0 10px 20px rgba(239, 68, 68, 0.4);
  }
  .footer {
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(255, 255, 255, 0.12); padding-top: 14px; z-index: 2;
  }
  .contact-col { display: flex; align-items: center; gap: 8px; color: #E2E8F0; font-size: 16px; font-weight: 700; }
  .contact-col span { color: #22C55E; font-size: 18px; }
  .pay-col {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 6px 14px; border-radius: 8px; color: #CBD5E1; font-size: 13.5px; display: flex; gap: 12px;
  }
  .pay-col b { color: #38BDF8; font-weight: 700; }
  .web-link { font-family: 'Inter', sans-serif; color: #38BDF8; font-size: 18px; font-weight: 800; }
</style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-name">AutoMovie <span>Pro</span></div>
    </div>
    <div class="yt-badge">▶ ফেসলেস ইউটিউব ও ফেসবুক অটোমেশন</div>
  </div>
  <div class="content">
    <div class="main-info">
      <div class="tagline">প্যাসিভ ইনকামের আল্টিমেট অটোমেশন পাওয়ারহাউস</div>
      <div class="headline">চেহারা না দেখিয়েই সফল চ্যানেল চালান — <span>১০০% ফুল অটোমেটিক!</span></div>
      <div class="steps-box">
        <div class="step-item"><div class="step-num">১</div> সফটওয়্যার নিজেই ট্রেন্ডিং টপিক ও সিনেমাটিক স্ক্রিপ্ট লিখবে</div>
        <div class="step-item"><div class="step-num">২</div> মানুষের মতো ন্যাচারাল কণ্ঠ ও ফুল এইচডি ভিজ্যুয়াল রেন্ডার হবে</div>
        <div class="step-item"><div class="step-num">৩</div> নো এডিটিং স্কিল — থাম্বনেইল, এসইও টাইটেল সহ সরাসরি অটো-পাবলিশ</div>
      </div>
    </div>
    <div class="price-card">
      <div class="price-title">আজীবন ব্যবহারের লাইসেন্স</div>
      <div class="price-amount">৳২,৯৯৮</div>
      <div class="price-sub">লাইফটাইম এক্সেস • আনলিমিটেড ভিডিও তৈরি</div>
      <div class="cta-btn">অর্ডার করতে ভিজিট করুন</div>
    </div>
  </div>
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
</body>
</html>"""
    },

    # 4. Multilingual Dubbing Banner
    {
        "id": "banner_multilingual",
        "html": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@600;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 10% 20%, rgba(16, 185, 129, 0.25) 0%, transparent 45%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.2) 0%, transparent 45%),
                #070B12;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 50px;
    position: relative;
    overflow: hidden;
  }
  .header { display: flex; justify-content: space-between; align-items: center; z-index: 2; }
  .brand { display: flex; align-items: center; gap: 14px; }
  .brand-logo-img {
    width: 48px; height: 48px; object-fit: contain;
    filter: drop-shadow(0 0 16px rgba(16, 185, 129, 0.7));
    border: none; background: transparent;
  }
  .brand-name { font-family: 'Inter', sans-serif; font-size: 26px; font-weight: 800; }
  .brand-name span { color: #10B981; }
  .lang-pill {
    background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4);
    color: #34D399; padding: 8px 18px; border-radius: 30px; font-weight: 700; font-size: 16px;
  }
  .content { display: flex; justify-content: space-between; align-items: center; z-index: 2; margin: 15px 0; }
  .main-info { max-width: 680px; }
  .tagline { color: #10B981; font-size: 20px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
  .headline { font-size: 43px; font-weight: 700; line-height: 1.25; margin-bottom: 18px; }
  .headline span { color: #34D399; }
  .flags-box { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
  .flag-badge {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 8px 16px; border-radius: 20px; font-size: 16px; font-weight: 600; color: #E2E8F0;
  }
  .price-card {
    background: linear-gradient(145deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
    border: 1px solid rgba(16, 185, 129, 0.4);
    box-shadow: 0 20px 40px rgba(0,0,0,0.5), 0 0 30px rgba(16, 185, 129, 0.2);
    border-radius: 24px; padding: 30px 35px; text-align: center; width: 380px;
  }
  .price-title { color: #94A3B8; font-size: 17px; font-weight: 600; text-transform: uppercase; margin-bottom: 6px; }
  .price-amount { font-family: 'Inter', sans-serif; font-size: 54px; font-weight: 900; color: #34D399; margin: 2px 0; }
  .price-sub { color: #A78BFA; font-size: 15px; font-weight: 700; margin-bottom: 18px; }
  .cta-btn {
    background: linear-gradient(135deg, #10B981, #059669); color: #fff;
    padding: 12px; border-radius: 12px; font-weight: 700; font-size: 17px;
    display: block; box-shadow: 0 10px 20px rgba(16, 185, 129, 0.4);
  }
  .footer {
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(255, 255, 255, 0.12); padding-top: 14px; z-index: 2;
  }
  .contact-col { display: flex; align-items: center; gap: 8px; color: #E2E8F0; font-size: 16px; font-weight: 700; }
  .contact-col span { color: #22C55E; font-size: 18px; }
  .pay-col {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 6px 14px; border-radius: 8px; color: #CBD5E1; font-size: 13.5px; display: flex; gap: 12px;
  }
  .pay-col b { color: #38BDF8; font-weight: 700; }
  .web-link { font-family: 'Inter', sans-serif; color: #38BDF8; font-size: 18px; font-weight: 800; }
</style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-name">AutoMovie <span>Pro</span></div>
    </div>
    <div class="lang-pill">🌐 গ্লোবাল লোকাল ট্রান্সলেশন ইঞ্জিন</div>
  </div>
  <div class="content">
    <div class="main-info">
      <div class="tagline">৫০+ আন্তর্জাতিক ভাষায় এক ক্লিকে ডাবিং ও লোকালাইজেশন</div>
      <div class="headline">আপনার কন্টেন্ট পৌঁছে দিন <span>বিশ্বের কোটি কোটি দর্শকের কাছে!</span></div>
      <div class="flags-box">
        <div class="flag-badge">🇧🇩 বাংলা</div>
        <div class="flag-badge">🇬🇧 English</div>
        <div class="flag-badge">🇮🇳 हिन्दी (Hindi)</div>
        <div class="flag-badge">🇮🇳 தமிழ் (Tamil)</div>
        <div class="flag-badge">🇵🇰 اردو (Urdu)</div>
        <div class="flag-badge">🇪🇸 Español</div>
        <div class="flag-badge">🇫🇷 Français</div>
      </div>
    </div>
    <div class="price-card">
      <div class="price-title">সফটওয়্যার লাইফটাইম ডিল</div>
      <div class="price-amount">৳২,৯৯৮</div>
      <div class="price-sub">প্রতিটি অতিরিক্ত ভাষা অ্যাড-অন মাত্র ৳৪৯৯</div>
      <div class="cta-btn">অর্ডার করতে ভিজিট করুন</div>
    </div>
  </div>
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
</body>
</html>"""
    },

    # 5. Reels & Shorts Viral Factory Banner
    {
        "id": "banner_shorts_reels",
        "html": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@600;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 80% 20%, rgba(244, 63, 94, 0.25) 0%, transparent 45%),
                radial-gradient(circle at 20% 80%, rgba(168, 85, 247, 0.2) 0%, transparent 45%),
                #090910;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 50px;
    position: relative;
    overflow: hidden;
  }
  .header { display: flex; justify-content: space-between; align-items: center; z-index: 2; }
  .brand { display: flex; align-items: center; gap: 14px; }
  .brand-logo-img {
    width: 48px; height: 48px; object-fit: contain;
    filter: drop-shadow(0 0 16px rgba(244, 63, 94, 0.7));
    border: none; background: transparent;
  }
  .brand-name { font-family: 'Inter', sans-serif; font-size: 26px; font-weight: 800; }
  .brand-name span { color: #F43F5E; }
  .pill { background: rgba(244, 63, 94, 0.15); border: 1px solid rgba(244, 63, 94, 0.4); color: #FB7185; padding: 8px 18px; border-radius: 30px; font-weight: 700; font-size: 16px; }
  .content { display: flex; justify-content: space-between; align-items: center; z-index: 2; margin: 15px 0; }
  .main-info { max-width: 680px; }
  .tagline { color: #F43F5E; font-size: 20px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
  .headline { font-size: 43px; font-weight: 700; line-height: 1.25; margin-bottom: 20px; }
  .headline span { color: #FDA4AF; }
  .cards-list { display: flex; flex-direction: column; gap: 10px; }
  .card-item { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); padding: 11px 18px; border-radius: 12px; font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 12px; }
  .price-card {
    background: linear-gradient(145deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
    border: 1px solid rgba(244, 63, 94, 0.4);
    border-radius: 24px; padding: 30px 35px; text-align: center; width: 380px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.5), 0 0 30px rgba(244, 63, 94, 0.2);
  }
  .price-title { color: #94A3B8; font-size: 17px; font-weight: 600; text-transform: uppercase; margin-bottom: 6px; }
  .price-amount { font-family: 'Inter', sans-serif; font-size: 54px; font-weight: 900; color: #FB7185; margin: 2px 0; }
  .price-sub { color: #34D399; font-size: 15px; font-weight: 700; margin-bottom: 18px; }
  .cta-btn { background: linear-gradient(135deg, #F43F5E, #E11D48); color: #fff; padding: 12px; border-radius: 12px; font-weight: 700; font-size: 17px; display: block; }
  .footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255, 255, 255, 0.12); padding-top: 14px; z-index: 2; }
  .contact-col { display: flex; align-items: center; gap: 8px; color: #E2E8F0; font-size: 16px; font-weight: 700; }
  .contact-col span { color: #22C55E; font-size: 18px; }
  .pay-col {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 6px 14px; border-radius: 8px; color: #CBD5E1; font-size: 13.5px; display: flex; gap: 12px;
  }
  .pay-col b { color: #38BDF8; font-weight: 700; }
  .web-link { font-family: 'Inter', sans-serif; color: #38BDF8; font-size: 18px; font-weight: 800; }
</style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-name">AutoMovie <span>Pro</span></div>
    </div>
    <div class="pill">⚡ ভাইরাল শর্টস ও রিলস মেকিং ইঞ্জিন</div>
  </div>
  <div class="content">
    <div class="main-info">
      <div class="tagline">প্রতিদিন ৫-১০টি ভাইরাল শর্টস তৈরি করুন সম্পূর্ণ অটোমেটিক</div>
      <div class="headline">সোশ্যাল মিডিয়া ফলোয়ার বাড়িয়ে নিন <span>১০ গুণ দ্রুত!</span></div>
      <div class="cards-list">
        <div class="card-item">📱 ৯:১৬ ভার্টিক্যাল ফরম্যাটে আল্ট্রা-এইচডি অটো রেন্ডারিং</div>
        <div class="card-item">✨ স্টাইলিশ ও ডায়নামিক কালারফুল অটো-ক্যাপশন বার্নিং</div>
        <div class="card-item">🚀 ফেসবুক ও ইউটিউবে সরাসরি অটো-আপলোড ও ভাইরাল এসইও</div>
      </div>
    </div>
    <div class="price-card">
      <div class="price-title">আজীবন ব্যবহারের ডিল</div>
      <div class="price-amount">৳২,৯৯৮</div>
      <div class="price-sub">লাইফটাইম এক্সেস • আনলিমিটেড রিলস</div>
      <div class="cta-btn">অর্ডার করতে ভিজিট করুন</div>
    </div>
  </div>
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
</body>
</html>"""
    },

    # 6. Agency & Business Automation Banner
    {
        "id": "banner_agency_solution",
        "html": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@600;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 15% 15%, rgba(14, 165, 233, 0.25) 0%, transparent 45%),
                radial-gradient(circle at 85% 85%, rgba(99, 102, 241, 0.2) 0%, transparent 45%),
                #080C16;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 50px;
    position: relative;
    overflow: hidden;
  }
  .header { display: flex; justify-content: space-between; align-items: center; z-index: 2; }
  .brand { display: flex; align-items: center; gap: 14px; }
  .brand-logo-img {
    width: 48px; height: 48px; object-fit: contain;
    filter: drop-shadow(0 0 16px rgba(14, 165, 233, 0.7));
    border: none; background: transparent;
  }
  .brand-name { font-family: 'Inter', sans-serif; font-size: 26px; font-weight: 800; }
  .brand-name span { color: #0EA5E9; }
  .pill { background: rgba(14, 165, 233, 0.15); border: 1px solid rgba(14, 165, 233, 0.4); color: #38BDF8; padding: 8px 18px; border-radius: 30px; font-weight: 700; font-size: 16px; }
  .content { display: flex; justify-content: space-between; align-items: center; z-index: 2; margin: 15px 0; }
  .main-info { max-width: 680px; }
  .tagline { color: #0EA5E9; font-size: 20px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
  .headline { font-size: 43px; font-weight: 700; line-height: 1.25; margin-bottom: 20px; }
  .headline span { color: #38BDF8; }
  .cards-list { display: flex; flex-direction: column; gap: 10px; }
  .card-item { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); padding: 11px 18px; border-radius: 12px; font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 12px; }
  .price-card {
    background: linear-gradient(145deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
    border: 1px solid rgba(14, 165, 233, 0.4);
    border-radius: 24px; padding: 30px 35px; text-align: center; width: 380px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.5), 0 0 30px rgba(14, 165, 233, 0.2);
  }
  .price-title { color: #94A3B8; font-size: 17px; font-weight: 600; text-transform: uppercase; margin-bottom: 6px; }
  .price-amount { font-family: 'Inter', sans-serif; font-size: 54px; font-weight: 900; color: #38BDF8; margin: 2px 0; }
  .price-sub { color: #10B981; font-size: 15px; font-weight: 700; margin-bottom: 18px; }
  .cta-btn { background: linear-gradient(135deg, #0EA5E9, #0284C7); color: #fff; padding: 12px; border-radius: 12px; font-weight: 700; font-size: 17px; display: block; }
  .footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255, 255, 255, 0.12); padding-top: 14px; z-index: 2; }
  .contact-col { display: flex; align-items: center; gap: 8px; color: #E2E8F0; font-size: 16px; font-weight: 700; }
  .contact-col span { color: #22C55E; font-size: 18px; }
  .pay-col {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 6px 14px; border-radius: 8px; color: #CBD5E1; font-size: 13.5px; display: flex; gap: 12px;
  }
  .pay-col b { color: #38BDF8; font-weight: 700; }
  .web-link { font-family: 'Inter', sans-serif; color: #38BDF8; font-size: 18px; font-weight: 800; }
</style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-name">AutoMovie <span>Pro</span></div>
    </div>
    <div class="pill">💼 এজেন্সি ও ফ্রিল্যান্সার পাওয়ার হাউস</div>
  </div>
  <div class="content">
    <div class="main-info">
      <div class="tagline">প্রোডাকশন স্পিড বাড়িয়ে নিন ১০০ গুণ বেশি</div>
      <div class="headline">ক্লায়েন্টদের জন্য বাল্ক ভিডিও তৈরি করুন — <span>সুপারফাস্ট!</span></div>
      <div class="cards-list">
        <div class="card-item">💼 কোনো ডেডলাইন মিস হবে না — নিমিষেই এক্সপ্লেনার ভিডিও</div>
        <div class="card-item">🌐 একই ভিডিও একাধিক ভাষায় ডাবিং করে অতিরিক্ত আর্নিং</div>
        <div class="card-item">💻 আনলিমিটেড লোকাল প্রজেক্ট ম্যানেজমেন্ট ড্যাশবোর্ড</div>
      </div>
    </div>
    <div class="price-card">
      <div class="price-title">এককালীন লাইফটাইম ডিল</div>
      <div class="price-amount">৳২,৯৯৮</div>
      <div class="price-sub">আজীবন ব্যবহার • আনলিমিটেড ক্লায়েন্ট ভিডিও</div>
      <div class="cta-btn">অর্ডার করতে ভিজিট করুন</div>
    </div>
  </div>
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
</body>
</html>"""
    },

    # 7. OmniSocial AI Hub — Autonomous Social Media AI Software ($1999 Lifetime)
    {
        "id": "banner_omnisocial_ai",
        "html": """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@600;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 85% 15%, rgba(6, 182, 212, 0.25) 0%, transparent 55%),
                radial-gradient(circle at 10% 90%, rgba(168, 85, 247, 0.25) 0%, transparent 45%),
                #050811;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 38px 48px; position: relative; overflow: hidden;
  }
  .bg-grid {
    position: absolute; inset: 0;
    background-image: linear-gradient(to right, rgba(0, 242, 254, 0.04) 1px, transparent 1px),
                      linear-gradient(to bottom, rgba(0, 242, 254, 0.04) 1px, transparent 1px);
    background-size: 36px 36px; pointer-events: none;
  }
  .header { display: flex; justify-content: space-between; align-items: center; z-index: 2; }
  .brand { display: flex; align-items: center; gap: 14px; }
  .brand-logo-img {
    width: 46px; height: 46px; object-fit: contain;
    filter: drop-shadow(0 0 16px rgba(0, 242, 254, 0.8));
    border: none; background: transparent;
  }
  .brand-name { font-family: 'Inter', sans-serif; font-size: 27px; font-weight: 800; letter-spacing: -0.5px; }
  .brand-name span { color: #00F2FE; }
  .badge-deal {
    background: linear-gradient(135deg, rgba(168, 85, 247, 0.3), rgba(6, 182, 212, 0.3));
    border: 1px solid #00F2FE; color: #E0E7FF;
    padding: 6px 18px; border-radius: 30px; font-size: 14.5px; font-weight: 700;
  }
  .content { display: flex; justify-content: space-between; align-items: center; gap: 30px; z-index: 2; margin: 10px 0; }
  .main-info { flex: 1.25; }
  .tagline { color: #00F2FE; font-size: 18px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
  .headline { font-size: 38px; font-weight: 700; line-height: 1.25; margin-bottom: 16px; }
  .headline span { color: #A855F7; text-shadow: 0 0 20px rgba(168, 85, 247, 0.5); }
  .cards-list { display: flex; flex-direction: column; gap: 10px; }
  .card-item {
    background: rgba(255, 255, 255, 0.04); border-left: 4px solid #00F2FE;
    padding: 10px 16px; border-radius: 0 10px 10px 0; font-size: 16.5px; font-weight: 600; color: #E2E8F0;
  }
  .price-card {
    flex: 0.85; background: linear-gradient(145deg, rgba(15, 23, 42, 0.85), rgba(5, 8, 17, 0.95));
    border: 2px solid #00F2FE; box-shadow: 0 0 30px rgba(0, 242, 254, 0.25);
    border-radius: 20px; padding: 26px 22px; text-align: center;
  }
  .price-title { color: #94A3B8; font-size: 16px; font-weight: 600; text-transform: uppercase; }
  .price-amount { font-family: 'Inter', sans-serif; font-size: 50px; font-weight: 900; color: #00F2FE; margin: 6px 0; }
  .price-sub { color: #34D399; font-size: 14px; font-weight: 600; margin-bottom: 16px; }
  .cta-btn {
    background: linear-gradient(135deg, #00F2FE, #3B82F6); color: #050811;
    font-size: 16px; font-weight: 800; padding: 12px 18px; border-radius: 12px; text-transform: uppercase;
  }
  .footer {
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(255, 255, 255, 0.1); padding-top: 12px; z-index: 2;
  }
  .contact-col { display: flex; align-items: center; gap: 8px; color: #E2E8F0; font-size: 15px; font-weight: 700; }
  .contact-col span { color: #22C55E; font-size: 17px; }
  .pay-col {
    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 5px 12px; border-radius: 8px; color: #CBD5E1; font-size: 13px; display: flex; gap: 10px;
  }
  .pay-col b { color: #00F2FE; font-weight: 700; }
  .web-link { font-family: 'Inter', sans-serif; color: #00F2FE; font-size: 17px; font-weight: 800; }
</style>
</head>
<body>
  <div class="bg-grid"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-name">AutoMovie Pro <span>Social Engine</span></div>
    </div>
    <div class="badge-deal">⚡ নতুন রিলিজ • অটোপাইলট সোশ্যাল রোবট</div>
  </div>
  <div class="content">
    <div class="main-info">
      <div class="tagline">১০০% স্বয়ংক্রিয় সোশ্যাল মিডিয়া ম্যানেজার</div>
      <div class="headline">ফেসবুক পেজ ও প্রোফাইল চলবে <span>হিউম্যান লাইক রোবটে!</span></div>
      <div class="cards-list">
        <div class="card-item">🤖 নোটিফিকেশন চেক, ফিড স্ক্রোলিং ও হিউম্যান লাইক অর্গানিক কাজ</div>
        <div class="card-item">🎨 স্বয়ংক্রিয় এআই ব্যানার তৈরি ও নির্ভুল শিডিউল পোস্টিং</div>
        <div class="card-item">⚡ একবার ইনস্টল — পিসি অন হলেই নিজে থেকে অটোপাইলট রান</div>
      </div>
    </div>
    <div class="price-card">
      <div class="price-title">এককালীন লাইফটাইম ডিল</div>
      <div class="price-amount">৳১,৯৯৯</div>
      <div class="price-sub">ওয়ান টাইম পেমেন্ট • আজীবন লাইফটাইম সাপোর্ট</div>
      <div class="cta-btn">অর্ডার করতে এখনই ভিজিট করুন</div>
    </div>
  </div>
  <div class="footer">
    <div class="contact-col">📞 হেল্পলাইন / WhatsApp: <span>+880 1684-355055</span></div>
    <div class="pay-col">
      <div>বিকাশ এজেন্ট: <b>01756160993</b></div>
      <div>নগদ এজেন্ট: <b>01611-824811</b></div>
      <div>পার্সোনাল: <b>01717820998</b></div>
    </div>
    <div class="web-link">🌐 automoviepro.com</div>
  </div>
</body>
</html>"""
    }
]

def render_banners():
    print("[BANNER STUDIO] Initializing Chromium Engine...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        
        for item in TEMPLATES:
            banner_id = item["id"]
            html_content = item["html"].replace("{LOGO_BASE64}", LOGO_BASE64)
            output_file = os.path.join(OUTPUT_DIR, f"{banner_id}.png")
            
            print(f"[BANNER STUDIO] Rendering {banner_id}...")
            page.set_content(html_content)
            page.wait_for_timeout(1000) # wait for web fonts to load
            page.screenshot(path=output_file)
            print(f"[BANNER STUDIO] Saved: {output_file}")
            
        browser.close()
    print("[BANNER STUDIO] All high-converting banners rendered successfully!")

if __name__ == "__main__":
    render_banners()
