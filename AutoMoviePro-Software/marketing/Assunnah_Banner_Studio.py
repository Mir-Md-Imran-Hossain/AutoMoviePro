import os
import time
import base64
from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"E:\AI Assistant\Automations\Assunnah_Banners"
os.makedirs(OUTPUT_DIR, exist_ok=True)
LOGO_PATH = r"E:\AI Assistant\Automations\logo_assunnah_transparent.png"

with open(LOGO_PATH, "rb") as f:
    LOGO_BASE64 = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"

SHARED_FOOTER_EN = """
  <div class="footer">
    <div class="footer-left">🌐 www.assunnahpath.com</div>
    <div class="footer-center">✉️ assunnahpath@gmail.com</div>
    <div class="footer-right">Authentic Knowledge • Spiritual Serenity</div>
  </div>
"""

SHARED_FOOTER_BN = """
  <div class="footer">
    <div class="footer-left">🌐 www.assunnahpath.com/bangla</div>
    <div class="footer-center">✉️ assunnahpathbangla@gmail.com</div>
    <div class="footer-right">বিশুদ্ধ জ্ঞান • আত্মিক প্রশান্তি</div>
  </div>
"""

TEMPLATES = [
    # --------------------------------------------------------------------------
    # 1. Tawakkul (Surah At-Talaq 65:3) - ENGLISH
    # --------------------------------------------------------------------------
    {
        "id": "banner_tawakkul",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Playfair+Display:ital,wght@0,600;1,600&family=Amiri:wght@700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 15%, rgba(212, 175, 55, 0.18) 0%, transparent 60%),
                radial-gradient(circle at 10% 85%, rgba(16, 185, 129, 0.12) 0%, transparent 50%),
                #070D12;
    font-family: 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Cinzel', serif; font-size: 25px; font-weight: 700; color: #F5E6BE; letter-spacing: 1px; }}
  .topic-pill {{
    background: rgba(212, 175, 55, 0.15); border: 1px solid rgba(212, 175, 55, 0.4);
    color: #E6CA65; padding: 6px 18px; border-radius: 20px; font-size: 13.5px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 32px; color: #D4AF37; margin-bottom: 16px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Playfair Display', serif; font-size: 32px; font-style: italic; line-height: 1.45;
    color: #F8FAFC; margin-bottom: 20px;
  }}
  .quote-text span {{ color: #E6CA65; }}
  .source-tag {{
    font-family: 'Cinzel', serif; color: #94A3B8; font-size: 15px; font-weight: 600; letter-spacing: 1.5px;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; letter-spacing: 0.5px; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Cinzel', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">As-Sunnah Path</div>
    </div>
    <div class="topic-pill">Divine Wisdom • Tawakkul</div>
  </div>
  <div class="quote-box">
    <div class="arabic">وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ ۚ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ</div>
    <div class="quote-text">"And whoever relies upon Allah — <span>He is sufficient for him</span>. Indeed, Allah will accomplish His purpose."</div>
    <div class="source-tag">— Surah At-Talaq [65:3]</div>
  </div>
  {SHARED_FOOTER_EN}
</body>
</html>"""
    },

    # --------------------------------------------------------------------------
    # 1. Tawakkul (Surah At-Talaq 65:3) - BANGLA
    # --------------------------------------------------------------------------
    {
        "id": "banner_tawakkul_bn",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Amiri:wght@700&family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 15%, rgba(212, 175, 55, 0.18) 0%, transparent 60%),
                radial-gradient(circle at 10% 85%, rgba(16, 185, 129, 0.12) 0%, transparent 50%),
                #070D12;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Hind Siliguri', serif; font-size: 26px; font-weight: 700; color: #F5E6BE; }}
  .topic-pill {{
    background: rgba(212, 175, 55, 0.15); border: 1px solid rgba(212, 175, 55, 0.4);
    color: #E6CA65; padding: 6px 18px; border-radius: 20px; font-size: 14px; font-weight: 600;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 32px; color: #D4AF37; margin-bottom: 16px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Hind Siliguri', serif; font-size: 32px; font-weight: 600; line-height: 1.5;
    color: #F8FAFC; margin-bottom: 18px;
  }}
  .quote-text span {{ color: #E6CA65; }}
  .source-tag {{
    font-family: 'Hind Siliguri', serif; color: #94A3B8; font-size: 16px; font-weight: 600;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Hind Siliguri', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">আস-সুন্নাহ পাথ বাংলা</div>
    </div>
    <div class="topic-pill">ঐশী প্রজ্ঞা • তাওয়াক্কুল</div>
  </div>
  <div class="quote-box">
    <div class="arabic">وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ ۚ إِنَّ اللَّهَ بَالِغُ أَمْرِهِ</div>
    <div class="quote-text">"আর যে ব্যক্তি আল্লাহর ওপর ভরসা করে, <span>তার জন্য তিনিই যথেষ্ট</span>। নিশ্চয় আল্লাহ তাঁর কাজ সম্পন্ন করবেনই।"</div>
    <div class="source-tag">— সূরা আত-তালাক [৬৫:৩]</div>
  </div>
  {SHARED_FOOTER_BN}
</body>
</html>"""
    },

    # --------------------------------------------------------------------------
    # 2. Ease After Hardship (Surah Ash-Sharh 94:5-6) - ENGLISH
    # --------------------------------------------------------------------------
    {
        "id": "banner_ease_after_hardship",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Playfair+Display:ital,wght@0,600;1,600&family=Amiri:wght@700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 20%, rgba(59, 130, 246, 0.16) 0%, transparent 60%),
                radial-gradient(circle at 80% 80%, rgba(212, 175, 55, 0.14) 0%, transparent 50%),
                #080C14;
    font-family: 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Cinzel', serif; font-size: 25px; font-weight: 700; color: #F5E6BE; letter-spacing: 1px; }}
  .topic-pill {{
    background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.4);
    color: #93C5FD; padding: 6px 18px; border-radius: 20px; font-size: 13.5px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 32px; color: #D4AF37; margin-bottom: 16px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Playfair Display', serif; font-size: 32px; font-style: italic; line-height: 1.45;
    color: #F8FAFC; margin-bottom: 20px;
  }}
  .quote-text span {{ color: #60A5FA; }}
  .source-tag {{
    font-family: 'Cinzel', serif; color: #94A3B8; font-size: 15px; font-weight: 600; letter-spacing: 1.5px;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; letter-spacing: 0.5px; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Cinzel', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">As-Sunnah Path</div>
    </div>
    <div class="topic-pill">Divine Promise • Hope & Sabr</div>
  </div>
  <div class="quote-box">
    <div class="arabic">فَإِنَّ مَعَ الْعُسْرِ يُسْرًا • إِنَّ مَعَ الْعُسْرِ يُسْرًا</div>
    <div class="quote-text">"For indeed, with hardship <span>will be ease</span>. Indeed, with hardship will be ease."</div>
    <div class="source-tag">— Surah Ash-Sharh [94:5-6]</div>
  </div>
  {SHARED_FOOTER_EN}
</body>
</html>"""
    },

    # --------------------------------------------------------------------------
    # 2. Ease After Hardship (Surah Ash-Sharh 94:5-6) - BANGLA
    # --------------------------------------------------------------------------
    {
        "id": "banner_ease_after_hardship_bn",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Amiri:wght@700&family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 20%, rgba(59, 130, 246, 0.16) 0%, transparent 60%),
                radial-gradient(circle at 80% 80%, rgba(212, 175, 55, 0.14) 0%, transparent 50%),
                #080C14;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Hind Siliguri', serif; font-size: 26px; font-weight: 700; color: #F5E6BE; }}
  .topic-pill {{
    background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.4);
    color: #93C5FD; padding: 6px 18px; border-radius: 20px; font-size: 14px; font-weight: 600;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 32px; color: #D4AF37; margin-bottom: 16px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Hind Siliguri', serif; font-size: 32px; font-weight: 600; line-height: 1.5;
    color: #F8FAFC; margin-bottom: 18px;
  }}
  .quote-text span {{ color: #60A5FA; }}
  .source-tag {{
    font-family: 'Hind Siliguri', serif; color: #94A3B8; font-size: 16px; font-weight: 600;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Hind Siliguri', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">আস-সুন্নাহ পাথ বাংলা</div>
    </div>
    <div class="topic-pill">ঐশী প্রতিশ্রুতি • আশা ও সবর</div>
  </div>
  <div class="quote-box">
    <div class="arabic">فَإِنَّ مَعَ الْعُسْرِ يُسْرًا • إِنَّ مَعَ الْعُسْرِ يُسْرًا</div>
    <div class="quote-text">"নিশ্চয় কষ্টের সাথেই <span>স্বস্তি রয়েছে</span>। অবশ্যই কষ্টের সাথেই স্বস্তি রয়েছে।"</div>
    <div class="source-tag">— সূরা আশ-শারহ [৯৪:৫-৬]</div>
  </div>
  {SHARED_FOOTER_BN}
</body>
</html>"""
    },

    # --------------------------------------------------------------------------
    # 3. Seeking Sacred Knowledge (Sahih Muslim 2699) - ENGLISH
    # --------------------------------------------------------------------------
    {
        "id": "banner_seeking_knowledge",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Playfair+Display:ital,wght@0,600;1,600&family=Amiri:wght@700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 15%, rgba(16, 185, 129, 0.16) 0%, transparent 60%),
                radial-gradient(circle at 15% 85%, rgba(212, 175, 55, 0.14) 0%, transparent 50%),
                #070E12;
    font-family: 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Cinzel', serif; font-size: 25px; font-weight: 700; color: #F5E6BE; letter-spacing: 1px; }}
  .topic-pill {{
    background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4);
    color: #6EE7B7; padding: 6px 18px; border-radius: 20px; font-size: 13.5px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .hadith-prefix {{
    font-family: 'Cinzel', serif; color: #D4AF37; font-size: 14.5px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px;
  }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 30px; color: #D4AF37; margin-bottom: 14px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Playfair Display', serif; font-size: 31px; font-style: italic; line-height: 1.45;
    color: #F8FAFC; margin-bottom: 18px;
  }}
  .quote-text span {{ color: #34D399; }}
  .source-tag {{
    font-family: 'Cinzel', serif; color: #94A3B8; font-size: 15px; font-weight: 600; letter-spacing: 1.5px;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; letter-spacing: 0.5px; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Cinzel', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">As-Sunnah Path</div>
    </div>
    <div class="topic-pill">Prophetic Tradition • Sacred Knowledge</div>
  </div>
  <div class="quote-box">
    <div class="hadith-prefix">The Messenger of Allah ﷺ Said:</div>
    <div class="arabic">مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ</div>
    <div class="quote-text">"Whoever travels a path in search of knowledge, <span>Allah will make easy for him a path to Paradise</span>."</div>
    <div class="source-tag">— Sahih Muslim [2699]</div>
  </div>
  {SHARED_FOOTER_EN}
</body>
</html>"""
    },

    # --------------------------------------------------------------------------
    # 3. Seeking Sacred Knowledge (Sahih Muslim 2699) - BANGLA
    # --------------------------------------------------------------------------
    {
        "id": "banner_seeking_knowledge_bn",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Amiri:wght@700&family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 15%, rgba(16, 185, 129, 0.16) 0%, transparent 60%),
                radial-gradient(circle at 15% 85%, rgba(212, 175, 55, 0.14) 0%, transparent 50%),
                #070E12;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Hind Siliguri', serif; font-size: 26px; font-weight: 700; color: #F5E6BE; }}
  .topic-pill {{
    background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4);
    color: #6EE7B7; padding: 6px 18px; border-radius: 20px; font-size: 14px; font-weight: 600;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .hadith-prefix {{
    font-family: 'Hind Siliguri', serif; color: #D4AF37; font-size: 16px; font-weight: 700; margin-bottom: 10px;
  }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 30px; color: #D4AF37; margin-bottom: 14px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Hind Siliguri', serif; font-size: 31px; font-weight: 600; line-height: 1.5;
    color: #F8FAFC; margin-bottom: 18px;
  }}
  .quote-text span {{ color: #34D399; }}
  .source-tag {{
    font-family: 'Hind Siliguri', serif; color: #94A3B8; font-size: 16px; font-weight: 600;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Hind Siliguri', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">আস-সুন্নাহ পাথ বাংলা</div>
    </div>
    <div class="topic-pill">নবীজির সুন্নাহ • দ্বীনি ইলম</div>
  </div>
  <div class="quote-box">
    <div class="hadith-prefix">রাসূলুল্লাহ সাল্লাল্লাহু আলাইহি ওয়া সাল্লাম বলেছেন:</div>
    <div class="arabic">مَنْ سَلَكَ طَرِيقًا يَلْتَمِسُ فِيهِ عِلْمًا سَهَّلَ اللَّهُ لَهُ بِهِ طَرِيقًا إِلَى الْجَنَّةِ</div>
    <div class="quote-text">"যে ব্যক্তি জ্ঞান অর্জনের উদ্দেশ্যে কোনো পথ অবলম্বন করে, <span>আল্লাহ তার জন্য জান্নাতের পথ সহজ করে দেন</span>।"</div>
    <div class="source-tag">— সহীহ মুসলিম [২৬৯৯]</div>
  </div>
  {SHARED_FOOTER_BN}
</body>
</html>"""
    },

    # --------------------------------------------------------------------------
    # 4. Peace in Remembrance (Surah Ar-Ra'd 13:28) - ENGLISH
    # --------------------------------------------------------------------------
    {
        "id": "banner_remembrance_dhikr",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Playfair+Display:ital,wght@0,600;1,600&family=Amiri:wght@700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 20%, rgba(139, 92, 246, 0.16) 0%, transparent 60%),
                radial-gradient(circle at 85% 85%, rgba(212, 175, 55, 0.14) 0%, transparent 50%),
                #0A0A14;
    font-family: 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Cinzel', serif; font-size: 25px; font-weight: 700; color: #F5E6BE; letter-spacing: 1px; }}
  .topic-pill {{
    background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.4);
    color: #C4B5FD; padding: 6px 18px; border-radius: 20px; font-size: 13.5px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 31px; color: #D4AF37; margin-bottom: 16px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Playfair Display', serif; font-size: 32px; font-style: italic; line-height: 1.45;
    color: #F8FAFC; margin-bottom: 20px;
  }}
  .quote-text span {{ color: #A78BFA; }}
  .source-tag {{
    font-family: 'Cinzel', serif; color: #94A3B8; font-size: 15px; font-weight: 600; letter-spacing: 1.5px;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; letter-spacing: 0.5px; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Cinzel', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">As-Sunnah Path</div>
    </div>
    <div class="topic-pill">Inner Peace • Dhikr of Allah</div>
  </div>
  <div class="quote-box">
    <div class="arabic">الَّذِينَ آمَنُوا وَتَطْمَئِنُّ قُلُوبُهُم بِذِكْرِ اللَّهِ ۗ أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ</div>
    <div class="quote-text">"Unquestionably, by the remembrance of Allah, <span>hearts find rest</span>."</div>
    <div class="source-tag">— Surah Ar-Ra'd [13:28]</div>
  </div>
  {SHARED_FOOTER_EN}
</body>
</html>"""
    },

    # --------------------------------------------------------------------------
    # 4. Peace in Remembrance (Surah Ar-Ra'd 13:28) - BANGLA
    # --------------------------------------------------------------------------
    {
        "id": "banner_remembrance_dhikr_bn",
        "html": f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Amiri:wght@700&family=Hind+Siliguri:wght@500;600;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px;
    background: radial-gradient(circle at 50% 20%, rgba(139, 92, 246, 0.16) 0%, transparent 60%),
                radial-gradient(circle at 85% 85%, rgba(212, 175, 55, 0.14) 0%, transparent 50%),
                #0A0A14;
    font-family: 'Hind Siliguri', 'Inter', sans-serif;
    color: #FFFFFF;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 40px 55px; position: relative; overflow: hidden;
  }}
  .bg-pattern {{
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(212, 175, 55, 0.08) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  .header {{ display: flex; justify-content: space-between; align-items: center; z-index: 2; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand-logo-img {{
    width: 62px; height: 62px; object-fit: contain;
    filter: drop-shadow(0 0 14px rgba(212, 175, 55, 0.65));
    border: none; background: transparent;
  }}
  .brand-title {{ font-family: 'Hind Siliguri', serif; font-size: 26px; font-weight: 700; color: #F5E6BE; }}
  .topic-pill {{
    background: rgba(139, 92, 246, 0.15); border: 1px solid rgba(139, 92, 246, 0.4);
    color: #C4B5FD; padding: 6px 18px; border-radius: 20px; font-size: 14px; font-weight: 600;
  }}
  .quote-box {{ text-align: center; z-index: 2; margin: auto 0; padding: 0 35px; }}
  .arabic {{
    font-family: 'Amiri', serif; font-size: 31px; color: #D4AF37; margin-bottom: 16px; line-height: 1.7; direction: rtl;
  }}
  .quote-text {{
    font-family: 'Hind Siliguri', serif; font-size: 32px; font-weight: 600; line-height: 1.5;
    color: #F8FAFC; margin-bottom: 18px;
  }}
  .quote-text span {{ color: #A78BFA; }}
  .source-tag {{
    font-family: 'Hind Siliguri', serif; color: #94A3B8; font-size: 16px; font-weight: 600;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(212, 175, 55, 0.25); padding-top: 14px; z-index: 2;
    font-size: 14px; color: #94A3B8;
  }}
  .footer-left {{ color: #38BDF8; font-weight: 600; }}
  .footer-center {{ color: #E2E8F0; font-weight: 500; }}
  .footer-right {{ font-family: 'Hind Siliguri', serif; color: #D4AF37; font-weight: 600; }}
</style>
</head>
<body>
  <div class="bg-pattern"></div>
  <div class="header">
    <div class="brand">
      <img src="{LOGO_BASE64}" class="brand-logo-img">
      <div class="brand-title">আস-সুন্নাহ পাথ বাংলা</div>
    </div>
    <div class="topic-pill">আত্মার প্রশান্তি • আল্লাহর জিকির</div>
  </div>
  <div class="quote-box">
    <div class="arabic">الَّذِينَ آمَنُوا وَتَطْمَئِنُّ قُلُوبُهُم بِذِكْرِ اللَّهِ ۗ أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ</div>
    <div class="quote-text">"জেনে রেখো, আল্লাহর স্মরণেই কেবল <span>অন্তরসমূহ প্রশান্ত হয়</span>।"</div>
    <div class="source-tag">— সূরা আর-রাদ [১৩:২৮]</div>
  </div>
  {SHARED_FOOTER_BN}
</body>
</html>"""
    }
]

def render_islamic_banners():
    print("[ISLAMIC BANNER STUDIO] Initializing Chromium Engine...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        
        for item in TEMPLATES:
            banner_id = item["id"]
            html_content = item["html"]
            output_file = os.path.join(OUTPUT_DIR, f"{banner_id}.png")
            
            print(f"[ISLAMIC BANNER STUDIO] Rendering {banner_id}...")
            page.set_content(html_content)
            page.wait_for_timeout(1000)
            page.screenshot(path=output_file)
            print(f"[ISLAMIC BANNER STUDIO] Saved: {output_file}")
            
        browser.close()
    print("[ISLAMIC BANNER STUDIO] All English & Bengali twin banners rendered successfully!")

if __name__ == "__main__":
    render_islamic_banners()
