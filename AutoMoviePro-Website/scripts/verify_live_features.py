import urllib.request
import ssl
import re
import sys
import http.cookiejar
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPSHandler(context=ctx)
)

# 1. Login
post_data = urllib.parse.urlencode({'username': 'admin', 'password': 'AutoMovie@2026'}).encode('utf-8')
login_req = urllib.request.Request(
    'https://193.203.184.176/admin/login.php', 
    data=post_data, 
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'}
)
opener.open(login_req)

# 2. Get CSRF from whatsapp_marketing.php
wa_req = urllib.request.Request(
    'https://193.203.184.176/admin/whatsapp_marketing.php', 
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'}
)
with opener.open(wa_req) as r:
    html = r.read().decode('utf-8', errors='ignore')
    csrf_m = re.search(r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']', html)
    csrf = csrf_m.group(1) if csrf_m else ''

print('CSRF Token:', csrf[:15] + '...')

# 3. Add Lead
add_data = urllib.parse.urlencode({
    'csrf': csrf,
    'action': 'add_lead',
    'name': 'Tanvir Ahmed',
    'phone': '01911223344',
    'interest_package': 'Omni Video Content Studio',
    'notes': 'Test lead created from admin panel'
}).encode('utf-8')

post_lead = urllib.request.Request(
    'https://193.203.184.176/admin/whatsapp_marketing.php?tab=leads', 
    data=add_data, 
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'}
)
with opener.open(post_lead) as r:
    res = r.read().decode('utf-8', errors='ignore')
    print('Lead Added Success Banner:', 'নতুন লিড সফলভাবে যুক্ত করা হয়েছে' in res)
    print('Lead Name visible in table:', 'Tanvir Ahmed' in res)
    print('Lead Phone visible in table:', '01911223344' in res)
    print('1-Click WhatsApp Link generated:', 'https://wa.me/8801911223344' in res)

# 4. Test Saving Agent Settings
agent_get = urllib.request.Request(
    'https://193.203.184.176/admin/agent_settings.php', 
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'}
)
with opener.open(agent_get) as r:
    agent_html = r.read().decode('utf-8', errors='ignore')
    csrf_agent_m = re.search(r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']', agent_html)
    csrf_agent = csrf_agent_m.group(1) if csrf_agent_m else ''

save_agent_data = urllib.parse.urlencode({
    'csrf': csrf_agent,
    'agent_primary_persona': 'ayesha',
    'agent_chat_active': '1',
    'agent_discount_allowed': '1',
    'agent_discount_mode': 'consultative',
    'agent_discount_type': 'flat',
    'agent_initial_discount_amount': '500',
    'agent_max_discount_amount': '1000',
    'agent_pkg_video_studio_init': '500',
    'agent_pkg_video_studio_max': '1000',
    'agent_pkg_fb_business_init': '300',
    'agent_pkg_fb_business_max': '600',
    'agent_pkg_profile_page_init': '200',
    'agent_pkg_profile_page_max': '400',
    'agent_coupon_prefix': 'VIP500',
    'agent_followup_reminder_hours': '24',
    'agent_free_addon_lang': '1',
    'agent_ask_whatsapp_for_demo': '1',
    'agent_auto_queue_whatsapp_welcome': '1'
}).encode('utf-8')

post_agent = urllib.request.Request(
    'https://193.203.184.176/admin/agent_settings.php',
    data=save_agent_data,
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'}
)
with opener.open(post_agent) as r:
    agent_res = r.read().decode('utf-8', errors='ignore')
    print('Agent Settings Saved Banner:', 'সেটিংস সফলভাবে সংরক্ষিত ও লাইভ আপডেট হয়েছে' in agent_res)
    print('Coupon VIP500 synced:', 'VIP500' in agent_res)
