# -*- coding: utf-8 -*-
import urllib.request
import ssl
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {
    'Host': 'automoviepro.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

def fetch(url):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return resp.read().decode('utf-8', errors='ignore')

print("Fetching live index from Hostinger (automoviepro.com)...")
try:
    index_html = fetch('https://193.203.184.176/')
    print(f"Index HTML size: {len(index_html)} bytes")
    
    # Check 1: Hero description
    hero_check = "প্যাসিভ ইনকাম করার সুবর্ণ সুযোগ" in index_html
    print(f"1. Hero desc updated in HTML: {hero_check}")
    
    # Check 2: Income lead
    income_check = "আমাদের বর্তমানে ৬টিরও বেশি ভাষা" in index_html
    print(f"2. Income lead updated in HTML: {income_check}")
    
    # Check 3: How it works & 3-Box Workflow Architecture
    how_check = "৩টি স্বতন্ত্র অটোমেশন ইঞ্জিনের" in index_html and "wfBoxSocial" in index_html and "wfBoxBusiness" in index_html and "wfBoxProfile" in index_html
    print(f"3. 3-Box Workflows updated in HTML: {how_check}")
    
    # Check 3b: 3-Column Comparative Feature Suite (No Tabs)
    feat_suite_check = "feature-suite-3col-grid" in index_html and "feat-box-video" in index_html and "feat-box-business" in index_html and "feat-box-profile" in index_html
    print(f"3b. 3-Column Feature Suite updated in HTML: {feat_suite_check}")
    
    # Check 4: Engine order buttons
    btn1_check = 'data-i18n="engine1_order_btn"' in index_html
    btn2_check = 'data-i18n="engine2_order_btn"' in index_html
    btn3_check = 'data-i18n="engine3_order_btn"' in index_html
    print(f"4. Engine buttons have unique keys: {btn1_check and btn2_check and btn3_check}")
    
    # Check 5: Package titles
    pkg_check = 'data-i18n="pkg1_title"' in index_html
    print(f"5. Package titles have pkg1_title: {pkg_check}")
    
    # Check 6: Radio card titles
    radio_check = 'data-i18n="engine1_radio_title"' in index_html
    print(f"6. Buy radio titles have engine1_radio_title: {radio_check}")
    
    # Check 7: Asset cache busters
    cache_css = 'assets/css/site.css?v=' in index_html
    cache_js = 'assets/js/i18n-site.js?v=' in index_html
    print(f"7. Cache buster on site.css: {cache_css}")
    print(f"8. Cache buster on i18n-site.js: {cache_js}")

except Exception as e:
    print(f"Error fetching index: {e}")

print("\nFetching live i18n-site.js from Hostinger...")
try:
    js_text = fetch('https://193.203.184.176/assets/js/i18n-site.js')
    print(f"i18n JS size: {len(js_text)} bytes")
    
    bn_hero = "প্যাসিভ ইনকাম করার সুবর্ণ সুযোগ" in js_text
    en_hero = "A golden opportunity" in js_text
    hi_hero = "सुनहरा अवसर" in js_text
    ur_hero = "سنہری موقع" in js_text
    ta_hero = "பொன்னான வாய்ப்பு" in js_text
    ml_hero = "സുവർണ്ണാവസരം" in js_text
    bn_income = "আমাদের বর্তমানে ৬টিরও বেশি ভাষা" in js_text
    
    print(f"9.  PACKS.bn.hero_desc updated: {bn_hero}")
    print(f"10. PACKS.en.hero_desc updated: {en_hero}")
    print(f"11. PACKS.hi.hero_desc updated: {hi_hero}")
    print(f"12. PACKS.ur.hero_desc updated: {ur_hero}")
    print(f"13. PACKS.ta.hero_desc updated: {ta_hero}")
    print(f"14. PACKS.ml.hero_desc updated: {ml_hero}")
    print(f"15. PACKS.bn.income_lead updated: {bn_income}")
    
    all_passed = all([
        hero_check, income_check, how_check, feat_suite_check,
        btn1_check, pkg_check, radio_check,
        cache_css, cache_js,
        bn_hero, en_hero, hi_hero, ur_hero, ta_hero, ml_hero, bn_income
    ])
    print(f"\nOVERALL PRODUCTION VERIFICATION: {'>>> ALL 16 CRITICAL CHECKS PASSED <<<' if all_passed else 'SOME CHECKS PENDING'}")
except Exception as e:
    print(f"Error fetching i18n-site.js: {e}")
