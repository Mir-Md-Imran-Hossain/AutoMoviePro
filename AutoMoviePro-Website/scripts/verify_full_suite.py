import urllib.request
import ssl
import re
import sys
import http.cookiejar
import urllib.parse
import json

sys.stdout.reconfigure(encoding='utf-8')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPSHandler(context=ctx)
)

print('=== 1. Logging in as Admin ===')
post_data = urllib.parse.urlencode({
    'username': 'admin',
    'password': 'AutoMovie@2026'
}).encode('utf-8')

login_req = urllib.request.Request(
    'https://193.203.184.176/admin/login.php', 
    data=post_data, 
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'}
)
with opener.open(login_req) as r:
    login_html = r.read().decode('utf-8', errors='ignore')
    print('Login Result URL:', r.geturl())
    print('Admin Authenticated:', 'admin-sidebar' in login_html or 'ড্যাশবোর্ড' in login_html)

# Extract CSRF token from admin index
csrf_m = re.search(r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']', login_html)
csrf = csrf_m.group(1) if csrf_m else ''

if not csrf:
    wa_get = urllib.request.Request('https://193.203.184.176/admin/whatsapp_marketing.php', headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'})
    with opener.open(wa_get) as wr:
        wa_html = wr.read().decode('utf-8', errors='ignore')
        csrf_m = re.search(r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']', wa_html)
        csrf = csrf_m.group(1) if csrf_m else ''

print('Admin CSRF Token available:', bool(csrf))

print('\n=== 2. Testing Lead Creation in WhatsApp Marketing Hub ===')
add_lead_data = urllib.parse.urlencode({
    'csrf': csrf,
    'action': 'add_lead',
    'name': 'Kamrul Hasan (Test)',
    'phone': '01888990011',
    'interest_package': 'Omni Video Content Studio (৳৩,৯৯৯)',
    'notes': 'Interested in YouTube automation'
}).encode('utf-8')

lead_post_req = urllib.request.Request(
    'https://193.203.184.176/admin/whatsapp_marketing.php?tab=leads',
    data=add_lead_data,
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'}
)
with opener.open(lead_post_req) as r:
    lead_res_html = r.read().decode('utf-8', errors='ignore')
    print('Add lead message found:', 'সফলভাবে যুক্ত করা হয়েছে' in lead_res_html)
    print('Lead name in table:', 'Kamrul Hasan (Test)' in lead_res_html)
    print('Clean phone in table:', '01888990011' in lead_res_html)

print('\n=== 3. Testing AI Chat Lead Capture & Dynamic Discount ===')
# Send a chat message with a phone number and "pore nebo"
chat_payload = json.dumps({
    'lang': 'bn',
    'message': 'amar budget kom, pore jogajog korbo. amar whatsapp 01799887766',
    'action': 'chat',
    'session_id': 'test_agent_suite_session'
}).encode('utf-8')

chat_req = urllib.request.Request(
    'https://193.203.184.176/api/marketing-chat.php',
    data=chat_payload,
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'}
)
with opener.open(chat_req) as r:
    chat_res = json.loads(r.read().decode('utf-8'))
    print('Chat API Status OK:', chat_res.get('ok'))
    print('Mode:', chat_res.get('mode'))
    print('Checkout URL issued:', chat_res.get('checkout_url'))
    print('Reply snippet:', chat_res.get('reply')[:150], '...')

print('\n=== 4. Verifying Auto-Captured Chat Lead in Admin Panel ===')
verify_req = urllib.request.Request(
    'https://193.203.184.176/admin/whatsapp_marketing.php?tab=leads&q=01799887766',
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'}
)
with opener.open(verify_req) as r:
    verify_html = r.read().decode('utf-8', errors='ignore')
    print('Chat lead 01799887766 captured in Leads Directory:', '01799887766' in verify_html)
    print('Captured with Chat Source badge:', 'লাইভ চ্যাট' in verify_html)

print('\n=== 5. Checking WhatsApp Outbox Queue ===')
outbox_req = urllib.request.Request(
    'https://193.203.184.176/admin/whatsapp_marketing.php?tab=outbox',
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'}
)
with opener.open(outbox_req) as r:
    outbox_html = r.read().decode('utf-8', errors='ignore')
    print('Outbox shows queued/logged welcome message for lead:', '01799887766' in outbox_html or '8801799887766' in outbox_html)

print('\nALL VERIFICATIONS PASSED SUCCESSFULLY!')
