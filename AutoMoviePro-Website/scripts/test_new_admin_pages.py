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
req = urllib.request.Request('https://193.203.184.176/admin/login.php', headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'})
with opener.open(req) as r:
    html = r.read().decode('utf-8', errors='ignore')
    csrf_m = re.search(r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']', html)
    csrf = csrf_m.group(1) if csrf_m else ''

post_data = urllib.parse.urlencode({'csrf': csrf, 'username': 'admin', 'password': 'AutoMovie@2026'}).encode('utf-8')
login_req = urllib.request.Request(
    'https://193.203.184.176/admin/login.php', 
    data=post_data, 
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'}
)
with opener.open(login_req) as r:
    print('Login successful!')

# 2. Check the new pages
pages_to_check = [
    '/admin/agent_settings.php',
    '/admin/whatsapp_marketing.php',
    '/admin/whatsapp_marketing.php?tab=outbox',
    '/admin/whatsapp_marketing.php?tab=templates',
    '/admin/whatsapp_marketing.php?tab=broadcast',
    '/admin/whatsapp_marketing.php?tab=settings',
    '/admin/index.php'
]

print('\n--- Verifying Live Deployed Pages ---')
for p in pages_to_check:
    test_req = urllib.request.Request('https://193.203.184.176' + p, headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'})
    with opener.open(test_req) as resp:
        body = resp.read().decode('utf-8', errors='ignore')
        title_m = re.search(r'<title>(.*?)</title>', body)
        title = title_m.group(1) if title_m else 'No title'
        has_sidebar = 'admin-sidebar' in body
        print(f'{p:<45} | Status: {resp.status} | Sidebar: {has_sidebar} | Title: {title}')
