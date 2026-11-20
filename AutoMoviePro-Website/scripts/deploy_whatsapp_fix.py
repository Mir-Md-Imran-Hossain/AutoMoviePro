import os
import ssl
import sys
import urllib.request

def upload(target_rel_path, local_file, auth_key, rest_key, base_url):
    # Strict TLS verification enabled
    ctx = ssl.create_default_context()
    
    with open(local_file, 'rb') as f:
        data = f.read()
    size = len(data)

    post_url = f"{base_url.rstrip('/')}/{target_rel_path}?override=true"
    req1 = urllib.request.Request(
        post_url,
        method='POST',
        headers={
            'X-Auth': auth_key,
            'X-Auth-Rest': rest_key,
            'Tus-Resumable': '1.0.0',
            'Upload-Length': str(size),
            'Upload-Offset': '0'
        }
    )
    with urllib.request.urlopen(req1, context=ctx) as r1:
        print(f"POST {target_rel_path}: {r1.status}")

    req2 = urllib.request.Request(
        post_url,
        data=data,
        method='PATCH',
        headers={
            'X-Auth': auth_key,
            'X-Auth-Rest': rest_key,
            'Tus-Resumable': '1.0.0',
            'Content-Type': 'application/offset+octet-stream',
            'Upload-Offset': '0'
        }
    )
    with urllib.request.urlopen(req2, context=ctx) as r2:
        offset = r2.headers.get('Upload-Offset')
        print(f"PATCH {target_rel_path}: {r2.status}, offset={offset}")

if __name__ == '__main__':
    auth_key = os.environ.get('HOSTINGER_AUTH_KEY', '').strip()
    rest_key = os.environ.get('HOSTINGER_REST_KEY', '').strip()
    base_url = os.environ.get('HOSTINGER_BASE_URL', '').strip()

    if not auth_key or not rest_key or not base_url:
        print("ERROR: Missing required environment variables:")
        print("  HOSTINGER_AUTH_KEY, HOSTINGER_REST_KEY, HOSTINGER_BASE_URL")
        print("Set them in environment before executing deployment.")
        sys.exit(1)

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    website_dir = os.path.join(repo_root, 'AutoMoviePro-Website')

    files = [
        ('admin/customers.php', os.path.join(website_dir, 'admin', 'customers.php')),
        ('admin/customer_view.php', os.path.join(website_dir, 'admin', 'customer_view.php')),
        ('admin/whatsapp_marketing.php', os.path.join(website_dir, 'admin', 'whatsapp_marketing.php')),
        ('api/login.php', os.path.join(website_dir, 'api', 'login.php')),
        ('api/wamanager_bridge.php', os.path.join(website_dir, 'api', 'wamanager_bridge.php')),
        ('includes/migrate.php', os.path.join(website_dir, 'includes', 'migrate.php')),
        ('includes/whatsapp.php', os.path.join(website_dir, 'includes', 'whatsapp.php')),
        ('api/claim_google_slot.php', os.path.join(website_dir, 'api', 'claim_google_slot.php')),
    ]

    for remote_rel, local_abs in files:
        if os.path.exists(local_abs):
            upload(remote_rel, local_abs, auth_key, rest_key, base_url)
        else:
            print(f"Skipping missing file: {local_abs}")
    print('ALL FILES SUCCESSFULLY SYNCED TO HOSTINGER!')
