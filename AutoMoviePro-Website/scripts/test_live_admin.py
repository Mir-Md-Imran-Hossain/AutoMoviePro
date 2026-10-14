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

# 1. GET login page for CSRF token
req = urllib.request.Request('https://193.203.184.176/admin/login.php', headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'})
with opener.open(req) as resp:
    html = resp.read().decode('utf-8', errors='ignore')
    csrf_match = re.search(r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']', html)
    csrf = csrf_match.group(1) if csrf_match else ''
    print('Fetched CSRF token:', bool(csrf))

# 2. POST login credentials
data = urllib.parse.urlencode({
    'csrf': csrf,
    'username': 'admin',
    'password': 'AutoMovie@2026'
}).encode('utf-8')

post_req = urllib.request.Request(
    'https://193.203.184.176/admin/login.php', 
    data=data, 
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'}
)

try:
    with opener.open(post_req) as resp:
        res_html = resp.read().decode('utf-8', errors='ignore')
        print('Login response URL:', resp.geturl())
        print('Login success (dashboard/sidebar rendered):', 'admin-sidebar' in res_html or 'ড্যাশবোর্ড' in res_html)
except Exception as e:
    print('Login POST error:', e)

# 3. Test all pages
pages = [
    '/admin/index.php',
    '/admin/orders.php',
    '/admin/customers.php',
    '/admin/reviews.php',
    '/admin/coupons.php',
    '/admin/chat_logs.php',
    '/admin/broadcast.php',
    '/admin/settings.php',
    '/admin/api_keys.php',
    '/admin/admins.php',
    '/admin/cms.php',
    '/admin/logs.php'
]

print('\n--- Testing All Admin Pages ---')
for p in pages:
    p_req = urllib.request.Request(f'https://193.203.184.176{p}', headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'})
    try:
        with opener.open(p_req) as r:
            body = r.read().decode('utf-8', errors='ignore')
            has_sidebar = 'admin-sidebar' in body
            title_m = re.search(r'<title>(.*?)</title>', body)
            title = title_m.group(1) if title_m else 'No Title'
            print(f'{p:<24} | Status: {r.status} | Sidebar: {has_sidebar} | Title: {title}')
    except Exception as err:
        print(f'{p:<24} | FAILED: {err}')
