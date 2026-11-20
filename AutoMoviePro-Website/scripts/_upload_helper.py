import os
import ssl
import sys
import urllib.request

def upload_file_to_hostinger(target_rel_path, file_bytes, auth_key, rest_key, base_url):
    """Uploads a file to Hostinger via TUS protocol with strict TLS verification."""
    # Strict TLS verification enabled
    ctx = ssl.create_default_context()
    size = len(file_bytes)

    # Step 1: POST creation
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

    # Step 2: PATCH upload
    patch_url = post_url
    req2 = urllib.request.Request(
        patch_url,
        data=file_bytes,
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
        print(f"PATCH {target_rel_path}: {r2.status}, offset={r2.headers.get('Upload-Offset')}")
    return True

if __name__ == '__main__':
    auth_key = os.environ.get('HOSTINGER_AUTH_KEY', '').strip()
    rest_key = os.environ.get('HOSTINGER_REST_KEY', '').strip()
    base_url = os.environ.get('HOSTINGER_BASE_URL', '').strip()

    if not auth_key or not rest_key or not base_url:
        print("ERROR: Missing required environment variables:")
        print("  HOSTINGER_AUTH_KEY, HOSTINGER_REST_KEY, HOSTINGER_BASE_URL")
        print("Set them in environment before executing upload.")
        sys.exit(1)

    if len(sys.argv) > 2:
        local_path = sys.argv[1]
        remote_path = sys.argv[2]
        with open(local_path, 'rb') as f:
            content = f.read()
        upload_file_to_hostinger(remote_path, content, auth_key, rest_key, base_url)
    else:
        print("Usage: python _upload_helper.py <local_path> <remote_path>")
