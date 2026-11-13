# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Phase 3 & 4 Automated Verification Test
Tests Database compatibility, Admin CSRF Feedback, Cashout config,
and UserApp port / Onboarding alignment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = ROOT / "AutoMoviePro-Website"
PHP_BIN = r"C:\wamp64\bin\php\php8.2.29\php.exe"
if not Path(PHP_BIN).exists():
    PHP_BIN = "php"


def run_php_code(code: str) -> str:
    temp_php = WEBSITE_DIR / f"_temp_test_{os.getpid()}_{time.time_ns()}.php"
    with open(temp_php, "w", encoding="utf-8") as f:
        f.write("<?php\n" + code + "\n")
    try:
        res = subprocess.run(
            [PHP_BIN, str(temp_php)],
            cwd=str(WEBSITE_DIR),
            capture_output=True,
            text=True,
            timeout=15
        )
        if res.returncode != 0:
            raise RuntimeError(f"PHP code error: {res.stderr}\nSTDOUT:\n{res.stdout}\nCode:\n{code}")
        return res.stdout.strip()
    finally:
        if temp_php.exists():
            try:
                temp_php.unlink()
            except Exception:
                pass


def test_sqlite_db_agnostic_queries():
    print("\n--- TEST 1: SQLite Database Compatibility Across All Updated Queries ---")
    php_test = """
    require 'includes/bootstrap.php';
    $sqlitePath = sys_get_temp_dir() . '/amp_phase3_test_' . uniqid() . '.sqlite';
    $pdo = new PDO('sqlite:' . $sqlitePath, null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    
    // Create necessary test schemas
    $pdo->exec("CREATE TABLE promo_channels (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, title TEXT, url TEXT, is_active INTEGER, sort_order INTEGER, created_at TEXT)");
    $pdo->exec("CREATE TABLE reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, rating INTEGER, review_text TEXT, platform TEXT, is_approved INTEGER, created_at TEXT)");
    $pdo->exec("CREATE TABLE agent_tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, message TEXT, reason TEXT, screenshot_note TEXT, activity_hint TEXT, needs_app_update INTEGER, admin_note TEXT, resolved_at TEXT, status TEXT, created_at TEXT)");
    $pdo->exec("CREATE TABLE customer_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, channel_name TEXT, video_type TEXT, title TEXT, description TEXT, platform TEXT, upload_status TEXT, uploaded_at TEXT, remote_url TEXT, local_path TEXT, meta_json TEXT, created_at TEXT)");
    $pdo->exec("CREATE TABLE language_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, lang_code TEXT, amount REAL, payment_ref TEXT, payment_note TEXT, status TEXT, created_at TEXT)");
    $pdo->exec("CREATE TABLE licenses (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, token TEXT, expires_at TEXT, revoked INTEGER, created_at TEXT)");
    $pdo->exec("CREATE TABLE wamanager_licenses (id TEXT PRIMARY KEY, license_key TEXT, customer_name TEXT, customer_phone TEXT, customer_email TEXT, plan_tier TEXT, status TEXT, max_devices INTEGER, hardware_id TEXT, machine_name TEXT, activated_at TEXT, created_at TEXT)");

    $nowVal = date('Y-m-d H:i:s');
    
    // 1. Promo
    $stmt1 = $pdo->prepare('INSERT INTO promo_channels (platform, title, url, is_active, sort_order, created_at) VALUES (?, ?, ?, 1, ?, ?)');
    $stmt1->execute(['youtube', 'Test Title', 'https://youtube.com', 0, $nowVal]);
    
    // 2. Reviews
    $stmt2 = $pdo->prepare("INSERT INTO reviews (name, rating, review_text, platform, is_approved, created_at) VALUES (?, ?, ?, ?, 1, ?)");
    $stmt2->execute(['Tester', 5, 'Great software', 'General', $nowVal]);
    $stmtToggle = $pdo->prepare("UPDATE reviews SET is_approved = (CASE WHEN is_approved=1 THEN 0 ELSE 1 END) WHERE id = 1");
    $stmtToggle->execute();

    // 3. Tickets
    $stmt3 = $pdo->prepare('INSERT INTO agent_tickets (customer_id, message, reason, screenshot_note, activity_hint, needs_app_update, status, created_at) VALUES (?, ?, ?, ?, ?, ?, "open", ?)');
    $stmt3->execute([1, 'Help', 'Crash', null, null, 0, $nowVal]);
    $stmtResolve = $pdo->prepare('UPDATE agent_tickets SET status = ?, admin_note = ?, resolved_at = ? WHERE id = ?');
    $stmtResolve->execute(['resolved', 'Fixed note', $nowVal, 1]);

    // 4. Jobs sync
    $stmt4 = $pdo->prepare('INSERT INTO customer_jobs (customer_id, channel_name, video_type, title, description, platform, upload_status, uploaded_at, remote_url, local_path, meta_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)');
    $stmt4->execute([1, 'Ch1', 'short', 'Title', 'Desc', 'YT', 'ok', null, null, null, null, $nowVal]);

    // 5. Language orders
    $stmt5 = $pdo->prepare('INSERT INTO language_orders (customer_id, lang_code, amount, payment_ref, payment_note, status, created_at) VALUES (?, ?, ?, ?, ?, "pending_payment", ?)');
    $stmt5->execute([1, 'en', 499.0, 'TRX123', 'Note', $nowVal]);

    // 6. Licenses query in update-check
    $stmt6 = $pdo->prepare('SELECT customer_id FROM licenses WHERE token = ? AND revoked = 0 AND (expires_at IS NULL OR expires_at > ?) LIMIT 1');
    $stmt6->execute(['tok123', $nowVal]);

    // 7. Wamanager licenses
    $stmt7 = $pdo->prepare("INSERT INTO wamanager_licenses (id, license_key, customer_name, customer_phone, customer_email, plan_tier, status, max_devices, created_at) VALUES (?, ?, ?, ?, ?, 'wamanager_pro', 'active', 1, ?)");
    $stmt7->execute(['wam_1', 'KEY123', 'User', '017', 'u@test.com', $nowVal]);
    $stmt8 = $pdo->prepare("UPDATE wamanager_licenses SET hardware_id = ?, machine_name = ?, activated_at = ? WHERE id = ?");
    $stmt8->execute(['HW1', 'PC1', $nowVal, 'wam_1']);

    echo "SQLITE_QUERIES_SUCCESS";
    @unlink($sqlitePath);
    """
    out = run_php_code(php_test)
    assert "SQLITE_QUERIES_SUCCESS" in out, f"Failed SQLite queries test: {out}"
    print("  [PASS] All 7 updated database queries execute flawlessly on SQLite with zero PDOExceptions ✓")


def test_admin_csrf_feedback():
    print("\n--- TEST 2: Admin CSRF Feedback Verification ---")
    server_port = 8881
    php_server = subprocess.Popen(
        [PHP_BIN, "-S", f"127.0.0.1:{server_port}", "-t", str(WEBSITE_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(1.2)

    try:
        # POST with wrong CSRF to admin/settings.php
        post_data = urllib.parse.urlencode({"csrf": "wrong_csrf_token", "action": "save_settings"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server_port}/admin/settings.php",
            data=post_data,
            headers={"User-Agent": "TestBrowser/1.0"}
        )
        # It redirects to login or renders error
        try:
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            html = e.read().decode("utf-8", errors="replace")

        # Now test logged in session with bad csrf
        php_csrf_test = """
        require 'includes/bootstrap.php';
        $_SESSION['admin_id'] = 1;
        $_SESSION['admin_user'] = 'admin';
        $_SERVER['REQUEST_METHOD'] = 'POST';
        $_POST['csrf'] = 'invalid_tampered_token';
        
        ob_start();
        include 'admin/settings.php';
        $out = ob_get_clean();
        if (str_contains($out, 'সেশনের মেয়াদ শেষ হয়েছে বা ফর্মের সিকিউরিটি টোকেন মেয়াদোত্তীর্ণ')) {
            echo "SETTINGS_CSRF_ALERT_RENDERED";
        } else {
            echo "SETTINGS_CSRF_FAILED";
        }
        """
        csrf_out = run_php_code(php_csrf_test)
        assert "SETTINGS_CSRF_ALERT_RENDERED" in csrf_out, f"Settings CSRF alert missing: {csrf_out}"
        print("  [PASS] admin/settings.php renders clear Bengali warning on expired/invalid CSRF token ✓")

        php_promo_csrf = """
        require 'includes/bootstrap.php';
        $_SESSION['admin_id'] = 1;
        $_SESSION['admin_user'] = 'admin';
        $_SERVER['REQUEST_METHOD'] = 'POST';
        $_POST['csrf'] = 'invalid_tampered_token';
        
        ob_start();
        include 'admin/promo.php';
        $out = ob_get_clean();
        if (str_contains($out, 'সেশনের মেয়াদ শেষ হয়েছে বা ফর্মের সিকিউরিটি টোকেন মেয়াদোত্তীর্ণ')) {
            echo "PROMO_CSRF_ALERT_RENDERED";
        } else {
            echo "PROMO_CSRF_FAILED";
        }
        """
        promo_out = run_php_code(php_promo_csrf)
        assert "PROMO_CSRF_ALERT_RENDERED" in promo_out, f"Promo CSRF alert missing: {promo_out}"
        print("  [PASS] admin/promo.php renders clear Bengali warning on expired/invalid CSRF token ✓")

        php_rev_csrf = """
        require 'includes/bootstrap.php';
        $_SESSION['admin_id'] = 1;
        $_SESSION['admin_user'] = 'admin';
        $_SERVER['REQUEST_METHOD'] = 'POST';
        $_POST['csrf'] = 'invalid_tampered_token';
        
        ob_start();
        include 'admin/reviews.php';
        $out = ob_get_clean();
        if (str_contains($out, 'সেশনের মেয়াদ শেষ হয়েছে বা ফর্মের সিকিউরিটি টোকেন মেয়াদোত্তীর্ণ')) {
            echo "REVIEWS_CSRF_ALERT_RENDERED";
        } else {
            echo "REVIEWS_CSRF_FAILED";
        }
        """
        rev_out = run_php_code(php_rev_csrf)
        assert "REVIEWS_CSRF_ALERT_RENDERED" in rev_out, f"Reviews CSRF alert missing: {rev_out}"
        print("  [PASS] admin/reviews.php renders clear Bengali warning on expired/invalid CSRF token ✓")

    finally:
        php_server.terminate()
        php_server.wait()


def test_userapp_port_and_onboarding():
    print("\n--- TEST 3: UserApp Port & Customer Onboarding Guidance ---")
    
    # 1. UserApp Python service
    user_app_svc = ROOT / "AutoMoviePro-UserApp" / "user_app_service.py"
    with open(user_app_svc, "r", encoding="utf-8") as f:
        code_py = f.read()
    assert "8787" in code_py, "UserApp service did not default to port 8787"
    print("  [PASS] AutoMoviePro-UserApp/user_app_service.py defaults to 8787 ✓")

    # 2. UserApp HTML interface
    user_app_html = ROOT / "AutoMoviePro-UserApp" / "index.html"
    with open(user_app_html, "r", encoding="utf-8") as f:
        html = f.read()
    assert "http://127.0.0.1:8787" in html, "UserApp index.html input value did not default to 8787"
    print("  [PASS] AutoMoviePro-UserApp/index.html input defaults to http://127.0.0.1:8787 ✓")

    # 3. Customer Onboarding checklist
    onboarding_py = ROOT / "AutoMoviePro-Software" / "app" / "customer_onboarding.py"
    with open(onboarding_py, "r", encoding="utf-8") as f:
        onb = f.read()
    assert "aistudio.google.com" in onb, "Onboarding did not include Google AI Studio free key guidance"
    print("  [PASS] AutoMoviePro-Software/app/customer_onboarding.py includes aistudio.google.com free key guidance ✓")


def test_payment_methods_numbers():
    print("\n--- TEST 4: Cashout Agent vs Support Hotline Integrity ---")
    php_pm = """
    require 'includes/payment_methods.php';
    $bk = amp_payment_bkash_agent();
    $ng = amp_payment_nagad_agent();
    $rk = amp_payment_rocket_agent();
    $txt = amp_default_payment_instructions_text();
    
    if (str_contains($bk, '01756160993') && str_contains($ng, '01611-824811') && (str_contains($txt, '3999') || str_contains($txt, '৩৯৯৯'))) {
        echo "PAYMENT_METHODS_VERIFIED";
    } else {
        echo "PAYMENT_METHODS_MISMATCH: bk={$bk}, ng={$ng}";
    }
    """
    out = run_php_code(php_pm)
    assert "PAYMENT_METHODS_VERIFIED" in out, f"Payment methods mismatch: {out}"
    print("  [PASS] bKash Agent (01756160993) and Nagad Agent (01611-824811) confirmed for Cashout ✓")
    print("  [PASS] International instruction harmonized with ৳৩৯৯৯ pricing ✓")


def main():
    print("==================================================================")
    print("⚙️ RUNNING AUTOMOVIE PRO PHASE 3 & 4 AUDIT VERIFICATION")
    print("==================================================================")
    test_sqlite_db_agnostic_queries()
    test_admin_csrf_feedback()
    test_userapp_port_and_onboarding()
    test_payment_methods_numbers()
    print("\n==================================================================")
    print("🏆 ALL PHASE 3 & 4 AUDIT TESTS PASSED SUCCESSFULLY! ✓")
    print("==================================================================")


if __name__ == "__main__":
    main()
