"""
AutoMovie Pro - Phase 1 Security Hardening & Rate-Limiting Test Suite
Verifies:
1. Unauthorized access to admin_mobile.php, sms_gateway.php, and payment_ledger.php returns 401.
2. Valid key allows access (200 OK with expected JSON payload).
3. Universal Rate Limiting triggers 429 on all hardened endpoints:
   - admin/login.php
   - api/login.php
   - api/request_otp.php
   - api/reset_password.php
   - api/marketing-chat.php
4. OTP Brute-force lockout: 3 failed attempts invalidates OTP code immediately.
"""

import os
import sys
import time
import json
import socket
import sqlite3
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

PHP_PATH = r"C:\wamp64\bin\php\php8.2.29\php.exe"
BASE_DIR = Path(r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update")
WEB_DIR = BASE_DIR / "AutoMoviePro-Website"
DB_PATH = WEB_DIR / "storage" / "local_demo.sqlite"
PORT = 8877
BASE_URL = f"http://127.0.0.1:{PORT}"

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

def clear_rate_limits():
    """Clears rate limit tracker and sets baseline live keys in SQLite to ensure predictable test runs"""
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute("DELETE FROM rate_limit_tracker")
            conn.execute("INSERT OR REPLACE INTO site_settings (setting_key, setting_value) VALUES ('agent_master_secret', 'amp_agent_master_live_key_2026')")
            conn.execute("INSERT OR REPLACE INTO site_settings (setting_key, setting_value) VALUES ('sms_gateway_secret', 'amp_sms_gateway_live_secret_2026')")
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

def make_request(url, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    if data is not None and isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
    elif data is not None and isinstance(data, str):
        data = data.encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, body
    except Exception as e:
        return 0, str(e)

def main():
    print("==================================================================")
    print("🔒 RUNNING AUTOMOVIE PRO PHASE 1 SECURITY & HARDENING VERIFICATION")
    print("==================================================================")

    # 1. Start PHP Built-in Server
    server_proc = None
    if not is_port_in_use(PORT):
        print(f"[*] Starting PHP server on port {PORT}...")
        server_proc = subprocess.Popen(
            [PHP_PATH, "-S", f"127.0.0.1:{PORT}", "-t", str(WEB_DIR)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(1.5)
    else:
        print(f"[*] Port {PORT} already active, using existing server.")

    all_passed = True

    try:
        clear_rate_limits()

        # -------------------------------------------------------------
        # Test 1: Unauthorized access returns 401
        # -------------------------------------------------------------
        print("\n--- TEST 1: Unauthorized Access Prevention (Expect 401) ---")
        endpoints_to_test = [
            ("GET", f"{BASE_URL}/api/admin_mobile.php?action=metrics", None),
            ("POST", f"{BASE_URL}/api/admin_mobile.php?action=killswitch", {"customer_id": 1}),
            ("GET", f"{BASE_URL}/api/sms_gateway.php", None),
            ("POST", f"{BASE_URL}/api/sms_gateway.php", {"txn_id": "TEST1234", "amount": 100}),
            ("GET", f"{BASE_URL}/api/payment_ledger.php", None),
            ("POST", f"{BASE_URL}/api/payment_ledger.php", {"amount": 500, "notes": "Hacker withdrawal"})
        ]

        for method, url, payload in endpoints_to_test:
            code, body = make_request(url, method=method, data=payload)
            passed = (code == 401)
            status_text = "PASS ✓ (401 Unauthorized)" if passed else f"FAIL ✗ (Got {code})"
            ep_name = url.split("?")[0].replace(BASE_URL, "")
            print(f"  [{method}] {ep_name} -> {status_text}")
            if not passed:
                all_passed = False
                print(f"      Response: {body[:150]}")

        # -------------------------------------------------------------
        # Test 2: Valid key allows access (Expect 200 OK)
        # -------------------------------------------------------------
        print("\n--- TEST 2: Valid Key Authorization (Expect 200 OK) ---")
        auth_header = {"X-Agent-Key": "amp_agent_master_live_key_2026"}
        sms_auth_header = {"X-Gateway-Secret": "amp_sms_gateway_live_secret_2026"}

        auth_tests = [
            ("GET", f"{BASE_URL}/api/admin_mobile.php?action=metrics", auth_header, None),
            ("GET", f"{BASE_URL}/api/payment_ledger.php", auth_header, None),
            ("GET", f"{BASE_URL}/api/sms_gateway.php", sms_auth_header, None),
            ("POST", f"{BASE_URL}/api/payment_ledger.php", auth_header, {"amount": 250, "notes": "Test withdrawal", "agent_name": "Test Simi Drug"})
        ]

        for method, url, headers, payload in auth_tests:
            code, body = make_request(url, method=method, headers=headers, data=payload)
            passed = (code == 200)
            status_text = "PASS ✓ (200 OK)" if passed else f"FAIL ✗ (Got {code})"
            ep_name = url.split("?")[0].replace(BASE_URL, "")
            print(f"  [{method}] {ep_name} -> {status_text}")
            if not passed:
                all_passed = False
                print(f"      Response: {body[:150]}")

        # -------------------------------------------------------------
        # Test 2b: Key Rotation & Backdoor Lockdown Verification
        # -------------------------------------------------------------
        print("\n--- TEST 2b: Key Rotation & Backdoor Lockdown (No Hardcoded Bypass) ---")
        rotated_agent_key = "custom_rotated_agent_key_987654"
        rotated_sms_key = "custom_rotated_sms_gateway_321654"

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("INSERT OR REPLACE INTO site_settings (setting_key, setting_value) VALUES ('agent_master_secret', ?)", (rotated_agent_key,))
        conn.execute("INSERT OR REPLACE INTO site_settings (setting_key, setting_value) VALUES ('sms_gateway_secret', ?)", (rotated_sms_key,))
        conn.commit()
        conn.close()

        # Step 1: Old hardcoded keys MUST now fail with 401
        old_key_tests = [
            ("GET", f"{BASE_URL}/api/admin_mobile.php?action=metrics", {"X-Agent-Key": "amp_agent_master_live_key_2026"}),
            ("GET", f"{BASE_URL}/api/payment_ledger.php", {"X-Agent-Key": "amp_agent_master_live_key_2026"}),
            ("GET", f"{BASE_URL}/api/sms_gateway.php", {"X-Gateway-Secret": "amp_sms_gateway_live_secret_2026"}),
        ]
        for method, url, headers in old_key_tests:
            code, _ = make_request(url, method=method, headers=headers)
            passed = (code == 401)
            status_text = "PASS ✓ (401 Unauthorized - Backdoor Rejected)" if passed else f"FAIL ✗ (Got {code} - Backdoor Exists!)"
            ep_name = url.split("?")[0].replace(BASE_URL, "")
            print(f"  Old Key Rejection -> [{method}] {ep_name}: {status_text}")
            if not passed:
                all_passed = False

        # Step 2: New rotated keys MUST succeed with 200
        new_key_tests = [
            ("GET", f"{BASE_URL}/api/admin_mobile.php?action=metrics", {"X-Agent-Key": rotated_agent_key}),
            ("GET", f"{BASE_URL}/api/payment_ledger.php", {"X-Agent-Key": rotated_agent_key}),
            ("GET", f"{BASE_URL}/api/sms_gateway.php", {"X-Gateway-Secret": rotated_sms_key}),
        ]
        for method, url, headers in new_key_tests:
            code, _ = make_request(url, method=method, headers=headers)
            passed = (code == 200)
            status_text = "PASS ✓ (200 OK - Rotated Key Accepted)" if passed else f"FAIL ✗ (Got {code})"
            ep_name = url.split("?")[0].replace(BASE_URL, "")
            print(f"  Rotated Key Auth -> [{method}] {ep_name}: {status_text}")
            if not passed:
                all_passed = False

        # Restore default live keys in settings for remaining tests
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("INSERT OR REPLACE INTO site_settings (setting_key, setting_value) VALUES ('agent_master_secret', 'amp_agent_master_live_key_2026')")
        conn.execute("INSERT OR REPLACE INTO site_settings (setting_key, setting_value) VALUES ('sms_gateway_secret', 'amp_sms_gateway_live_secret_2026')")
        conn.commit()
        conn.close()

        # -------------------------------------------------------------
        # Test 3: Universal Rate Limiting (Expect 429 on threshold)
        # -------------------------------------------------------------
        print("\n--- TEST 3: Universal Rate Limiting (Expect 429 Too Many Requests) ---")
        clear_rate_limits()

        # 3a. api/marketing-chat.php (Threshold: 30)
        print("  [3a] Testing api/marketing-chat.php rate limiting...")
        chat_429 = False
        for i in range(35):
            code, _ = make_request(
                f"{BASE_URL}/api/marketing-chat.php",
                method="POST",
                data={"message": f"Hello test message {i}", "lang": "bn"}
            )
            if code == 429:
                chat_429 = True
                print(f"      Hit limit on request #{i+1} (Got 429 Too Many Requests) ✓")
                break
        if chat_429:
            print("      [PASS] marketing-chat.php rate limiter is ACTIVE ✓")
        else:
            print("      [FAIL] marketing-chat.php did not return 429!")
            all_passed = False

        clear_rate_limits()

        # 3b. api/login.php (Threshold: 10)
        print("  [3b] Testing api/login.php rate limiting...")
        login_429 = False
        for i in range(15):
            code, _ = make_request(
                f"{BASE_URL}/api/login.php",
                method="POST",
                data={"login_id": "FAKE_USER", "password": "wrong_password"}
            )
            if code == 429:
                login_429 = True
                print(f"      Hit limit on request #{i+1} (Got 429 Too Many Requests) ✓")
                break
        if login_429:
            print("      [PASS] api/login.php rate limiter is ACTIVE ✓")
        else:
            print("      [FAIL] api/login.php did not return 429!")
            all_passed = False

        clear_rate_limits()

        # 3c. api/request_otp.php (Threshold: 5)
        print("  [3c] Testing api/request_otp.php rate limiting...")
        otp_429 = False
        for i in range(10):
            code, _ = make_request(
                f"{BASE_URL}/api/request_otp.php",
                method="POST",
                data={"login_id": "AMP_NON_EXISTENT"}
            )
            if code == 429:
                otp_429 = True
                print(f"      Hit limit on request #{i+1} (Got 429 Too Many Requests) ✓")
                break
        if otp_429:
            print("      [PASS] api/request_otp.php rate limiter is ACTIVE ✓")
        else:
            print("      [FAIL] api/request_otp.php did not return 429!")
            all_passed = False

        clear_rate_limits()

        # 3d. admin/login.php (Threshold: 5)
        print("  [3d] Testing admin/login.php rate limiting...")
        admin_login_429 = False
        headers_form = {"Content-Type": "application/x-www-form-urlencoded"}
        for i in range(10):
            code, body = make_request(
                f"{BASE_URL}/admin/login.php",
                method="POST",
                headers=headers_form,
                data="username=admin&password=wrongpassword"
            )
            if code == 429:
                admin_login_429 = True
                print(f"      Hit limit on request #{i+1} (Got 429 Too Many Requests) ✓")
                break
        if admin_login_429:
            print("      [PASS] admin/login.php rate limiter is ACTIVE ✓")
        else:
            print("      [FAIL] admin/login.php did not return 429!")
            all_passed = False

        clear_rate_limits()

        # 3e. api/reset_password.php (Threshold: 5)
        print("  [3e] Testing api/reset_password.php rate limiting...")
        reset_429 = False
        for i in range(10):
            code, _ = make_request(
                f"{BASE_URL}/api/reset_password.php",
                method="POST",
                data={"login_id": "AMP_NON_EXISTENT", "otp": "123456", "new_password": "password123"}
            )
            if code == 429:
                reset_429 = True
                print(f"      Hit limit on request #{i+1} (Got 429 Too Many Requests) ✓")
                break
        if reset_429:
            print("      [PASS] api/reset_password.php rate limiter is ACTIVE ✓")
        else:
            print("      [FAIL] api/reset_password.php did not return 429!")
            all_passed = False

        # 3f. Proxy-Aware Rate Limiting (CF-Connecting-IP / X-Forwarded-For)
        print("  [3f] Testing Reverse Proxy IP Rate Limit isolation...")
        clear_rate_limits()
        # Max out IP 192.0.2.1
        for i in range(6):
            make_request(
                f"{BASE_URL}/api/request_otp.php",
                method="POST",
                headers={"CF-Connecting-IP": "192.0.2.1"},
                data={"login_id": "AMP_TEST_IP1"}
            )
        # IP 192.0.2.1 must now be 429
        code_ip1, _ = make_request(
            f"{BASE_URL}/api/request_otp.php",
            method="POST",
            headers={"CF-Connecting-IP": "192.0.2.1"},
            data={"login_id": "AMP_TEST_IP1"}
        )
        # Distinct IP 198.51.100.2 behind the same proxy MUST NOT be blocked (code != 429)
        code_ip2, _ = make_request(
            f"{BASE_URL}/api/request_otp.php",
            method="POST",
            headers={"CF-Connecting-IP": "198.51.100.2"},
            data={"login_id": "AMP_TEST_IP2"}
        )
        proxy_pass = (code_ip1 == 429 and code_ip2 != 429)
        if proxy_pass:
            print("      [PASS] Proxy-aware rate limiter isolates IP quotas correctly ✓")
        else:
            print(f"      [FAIL] Proxy rate limiting failed: ip1={code_ip1}, ip2={code_ip2}")
            all_passed = False

        # -------------------------------------------------------------
        # Test 4: OTP Brute-Force Lockout (3 Failed Attempts -> Invalidate)
        # -------------------------------------------------------------
        print("\n--- TEST 4: OTP Brute-Force Lockout in api/reset_password.php ---")
        clear_rate_limits()

        # Seed a test customer with an active OTP in SQLite
        conn = sqlite3.connect(str(DB_PATH))
        test_login = "AMP_TEST_SECURITY_USER"
        test_otp = "842109"
        conn.execute("DELETE FROM customers WHERE login_id = ?", (test_login,))
        import datetime
        expires_str = (datetime.datetime.now() + datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO customers (login_id, name, whatsapp, email, status, otp_code, otp_expires_at, otp_failed_attempts) "
            "VALUES (?, 'Security Test User', '8801700000000', 'sectest@automoviepro.com', 'active', ?, ?, 0)",
            (test_login, test_otp, expires_str)
        )
        conn.commit()
        conn.close()

        # Attempt 1: wrong OTP
        code1, body1 = make_request(
            f"{BASE_URL}/api/reset_password.php",
            method="POST",
            data={"login_id": test_login, "otp": "000000", "new_password": "NewSecretPass123"}
        )
        d1 = json.loads(body1)
        pass1 = (code1 == 400 and d1.get("error") == "invalid_otp")
        print(f"  Attempt 1 (Wrong OTP) -> code={code1}, error={d1.get('error')} ({'PASS ✓' if pass1 else 'FAIL ✗'})")

        # Attempt 2: wrong OTP
        code2, body2 = make_request(
            f"{BASE_URL}/api/reset_password.php",
            method="POST",
            data={"login_id": test_login, "otp": "000001", "new_password": "NewSecretPass123"}
        )
        d2 = json.loads(body2)
        pass2 = (code2 == 400 and d2.get("error") == "invalid_otp")
        print(f"  Attempt 2 (Wrong OTP) -> code={code2}, error={d2.get('error')} ({'PASS ✓' if pass2 else 'FAIL ✗'})")

        # Attempt 3: 3rd wrong OTP -> MUST invalidate OTP
        code3, body3 = make_request(
            f"{BASE_URL}/api/reset_password.php",
            method="POST",
            data={"login_id": test_login, "otp": "000002", "new_password": "NewSecretPass123"}
        )
        d3 = json.loads(body3)
        pass3 = (code3 == 400 and d3.get("error") == "otp_invalidated")
        print(f"  Attempt 3 (3rd Wrong OTP) -> code={code3}, error={d3.get('error')} ({'PASS ✓' if pass3 else 'FAIL ✗'})")

        # Verify database record: otp_code should be NULL
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT otp_code, otp_expires_at, otp_failed_attempts FROM customers WHERE login_id = ?", (test_login,))
        row = cur.fetchone()
        conn.close()

        db_cleared = (row[0] is None)
        print(f"  Database check: otp_code is NULL in DB -> {'PASS ✓' if db_cleared else 'FAIL ✗'}")

        # Attempt 4: Even with CORRECT OTP, it must now fail because OTP was invalidated
        code4, body4 = make_request(
            f"{BASE_URL}/api/reset_password.php",
            method="POST",
            data={"login_id": test_login, "otp": test_otp, "new_password": "NewSecretPass123"}
        )
        d4 = json.loads(body4)
        pass4 = (code4 == 400 and d4.get("error") == "no_otp_requested")
        print(f"  Attempt 4 (Original correct OTP after lockout) -> code={code4}, error={d4.get('error')} ({'PASS ✓' if pass4 else 'FAIL ✗'})")

        otp_lockout_passed = pass1 and pass2 and pass3 and db_cleared and pass4
        if not otp_lockout_passed:
            all_passed = False

        # 4b. Test WhatsApp / Phone Number Account Lookup for Password Reset
        print("\n--- TEST 4b: WhatsApp/Phone Account Identifier in api/reset_password.php ---")
        wa_test_user = "AMP_WA_TEST_USER"
        wa_test_phone = "8801999888777"
        wa_test_otp = "554433"
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM customers WHERE login_id = ? OR whatsapp = ?", (wa_test_user, wa_test_phone))
        conn.execute(
            "INSERT INTO customers (login_id, name, whatsapp, email, status, otp_code, otp_expires_at, otp_failed_attempts) "
            "VALUES (?, 'WA Test User', ?, 'watest@automoviepro.com', 'active', ?, ?, 0)",
            (wa_test_user, wa_test_phone, wa_test_otp, expires_str)
        )
        conn.commit()
        conn.close()

        code_wa, body_wa = make_request(
            f"{BASE_URL}/api/reset_password.php",
            method="POST",
            data={"whatsapp": wa_test_phone, "otp": wa_test_otp, "new_password": "NewWaPassword999"}
        )
        d_wa = json.loads(body_wa)
        pass_wa = (code_wa == 200 and d_wa.get("ok") is True)
        print(f"  Password Reset using WhatsApp phone identifier -> code={code_wa}, ok={d_wa.get('ok')} ({'PASS ✓' if pass_wa else 'FAIL ✗'})")
        if not pass_wa:
            all_passed = False

        # Cleanup test users
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM customers WHERE login_id = ?", (test_login,))
        conn.execute("DELETE FROM customers WHERE login_id = ? OR whatsapp = ?", (wa_test_user, wa_test_phone))
        conn.commit()
        conn.close()

        clear_rate_limits()

    finally:
        if server_proc:
            print("\n[*] Terminating PHP test server...")
            server_proc.terminate()
            server_proc.wait()

    print("\n==================================================================")
    if all_passed:
        print("🏆 ALL PHASE 1 SECURITY HARDENING TESTS PASSED SUCCESSFULLY! ✓")
        print("==================================================================")
        sys.exit(0)
    else:
        print("❌ SOME SECURITY TESTS FAILED. PLEASE REVIEW LOGS ABOVE.")
        print("==================================================================")
        sys.exit(1)

if __name__ == "__main__":
    main()
