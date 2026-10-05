"""C02 — Customer Windows auth / account / entitlement / access (paid APIs = 0)."""
from __future__ import annotations

import inspect
import json
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.customer_auth import (
    ACCOUNT_ACTIVE,
    ACCOUNT_DISABLED,
    ACCOUNT_DISABLED_STATE,
    ACCOUNT_PENDING,
    ACCOUNT_UNKNOWN,
    AUTHENTICATED,
    AUTH_ERROR,
    ENTITLEMENT_ACTIVE,
    ENTITLEMENT_EXPIRED,
    ENTITLEMENT_NONE,
    ENTITLEMENT_REQUIRED,
    ENTITLEMENT_SUSPENDED,
    ENTITLEMENT_UNKNOWN,
    IDENTITY_FIELDS,
    SESSION_EXPIRED,
    UNAUTHENTICATED,
    authenticate,
    can_customer_produce,
    clear_session,
    ensure_session_columns,
    evaluate_session,
    logout,
    map_account_state,
    map_entitlement_state,
    persist_session,
    require_authenticated_session,
    sanitize_auth_error,
    to_identity_projection,
)
from app.customer_foundation import build_foundation_snapshot


def _ready_foundation() -> dict:
    return build_foundation_snapshot(
        media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
        operational={"status": "READY", "production_ready": True, "issues": []},
        api_readiness={"active": True},
    )


def _blocked_foundation() -> dict:
    return build_foundation_snapshot(
        media_cap={"FFMPEG_AVAILABLE": False, "FFPROBE_AVAILABLE": False},
        operational={"status": "BLOCKED", "production_ready": False, "issues": ["x"]},
        api_readiness={"active": True},
    )


def _unknown_foundation() -> dict:
    return build_foundation_snapshot(
        media_cap={},
        operational={"status": "READY", "production_ready": True, "issues": []},
        api_readiness={"active": True},
    )


class C02AuthBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "c02.db"
        from app import db as store

        self._store = store
        self._orig_db = store.DB_PATH
        store.DB_PATH = self.db_path
        store.init_db()
        ensure_session_columns()

    def tearDown(self):
        self._store.DB_PATH = self._orig_db


class C02AuthenticationTests(C02AuthBase):
    def test_01_unauthenticated_startup(self):
        idn = evaluate_session()
        self.assertEqual(idn["auth_state"], UNAUTHENTICATED)
        self.assertFalse(idn["logged_in"])
        self.assertFalse(idn["production_access"])
        self.assertIn("sign in", idn["message"].lower())

    def test_02_valid_login_local(self):
        with patch("app.customer_auth.local_login_permitted", return_value=True):
            res = authenticate("admin", "admin123", "local")
        self.assertTrue(res["ok"])
        idn = evaluate_session()
        self.assertEqual(idn["auth_state"], AUTHENTICATED)
        self.assertTrue(idn["logged_in"])
        self.assertEqual(idn["account_state"], ACCOUNT_ACTIVE)
        self.assertEqual(idn["entitlement_state"], ENTITLEMENT_ACTIVE)

    def test_03_invalid_credentials(self):
        with patch("app.customer_auth.local_login_permitted", return_value=False), patch(
            "app.api_client.LicenseClient"
        ) as LC:
            LC.return_value.login.side_effect = RuntimeError("bad password token=sekrit")
            res = authenticate("u", "wrong", "https://example.test")
        self.assertFalse(res["ok"])
        self.assertEqual(res["auth_state"], AUTH_ERROR)
        self.assertNotIn("sekrit", json.dumps(res))

    def test_04_session_restoration(self):
        persist_session(
            login_id="restored",
            token="local-dev-token",
            customer={"id": 1, "name": "R", "status": "active", "plan": "dev", "entitlement": "active"},
            api_base="local",
            auth_mode="local_dev",
        )
        idn = evaluate_session()
        self.assertEqual(idn["auth_state"], AUTHENTICATED)
        self.assertEqual(idn["login_id"], "restored")
        self.assertTrue(require_authenticated_session())

    def test_05_expired_session(self):
        persist_session(
            login_id="old",
            token="local-dev-token",
            customer={"id": 1, "name": "O", "status": "active", "plan": "dev", "entitlement": "active"},
            api_base="local",
            auth_mode="local_dev",
        )
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        with self._store.db() as conn:
            conn.execute("UPDATE session SET expires_at=? WHERE id=1", (past,))
        idn = evaluate_session()
        self.assertEqual(idn["auth_state"], SESSION_EXPIRED)
        self.assertFalse(idn["logged_in"])
        self.assertIsNone(require_authenticated_session())

    def test_06_logout(self):
        with patch("app.customer_auth.local_login_permitted", return_value=True):
            authenticate("admin", "admin123", "local")
        out = logout()
        self.assertTrue(out["ok"])
        self.assertEqual(out["identity"]["auth_state"], UNAUTHENTICATED)
        self.assertIsNone(self._store.get_session())

    def test_07_logout_invalidates_protected_access(self):
        with patch("app.customer_auth.local_login_permitted", return_value=True):
            authenticate("admin", "admin123", "local")
        self.assertTrue(can_customer_produce(foundation=_ready_foundation())["allowed"])
        logout()
        denied = can_customer_produce(foundation=_ready_foundation())
        self.assertFalse(denied["allowed"])
        self.assertIn(denied["block_reason"], ("unauthenticated", UNAUTHENTICATED.lower()))

    def test_08_auth_error_missing_credentials(self):
        res = authenticate("", "", "local")
        self.assertFalse(res["ok"])
        self.assertEqual(res["auth_state"], AUTH_ERROR)

    def test_09_duplicate_login_replaces_session(self):
        with patch("app.customer_auth.local_login_permitted", return_value=True):
            authenticate("admin", "admin123", "local")
            authenticate("admin2", "admin123", "local")
        sess = self._store.get_session()
        self.assertEqual(sess["login_id"], "admin2")
        self.assertEqual(evaluate_session()["auth_state"], AUTHENTICATED)

    def test_10_safe_auth_error_projection(self):
        dirty = sanitize_auth_error("failed password=abc123 Bearer xyzsk-ABCDEFGH12345678")
        self.assertNotIn("abc123", dirty)
        self.assertNotIn("xyz", dirty.lower().replace("[redacted]", ""))
        self.assertIn("[redacted]", dirty)
        proj = to_identity_projection(
            {
                "auth_state": AUTH_ERROR,
                "message": "We couldn't verify your account right now. Please try again.",
                "token": "should-not-appear",
                "password": "nope",
            }
        )
        self.assertNotIn("token", proj)
        self.assertNotIn("password", proj)
        for k in proj:
            self.assertIn(k, IDENTITY_FIELDS)


class C02AccountTests(C02AuthBase):
    def _put(self, customer, auth_mode="license"):
        persist_session(
            login_id="u",
            token="tok-license",
            customer=customer,
            api_base="https://lic.test",
            auth_mode=auth_mode,
        )

    def test_11_active_account(self):
        self.assertEqual(map_account_state({"status": "active"}), ACCOUNT_ACTIVE)
        self._put({"id": 1, "status": "active", "plan": "pro", "entitlement": "active"})
        self.assertEqual(evaluate_session()["account_state"], ACCOUNT_ACTIVE)

    def test_12_disabled_account(self):
        self.assertEqual(map_account_state({"status": "disabled"}), ACCOUNT_DISABLED_STATE)
        self._put({"id": 1, "status": "disabled", "plan": "pro", "entitlement": "active"})
        idn = evaluate_session()
        self.assertEqual(idn["auth_state"], ACCOUNT_DISABLED)
        self.assertFalse(idn["production_access"])

    def test_13_pending_account(self):
        self.assertEqual(map_account_state({"status": "pending"}), ACCOUNT_PENDING)
        self._put({"id": 1, "status": "pending", "plan": "pro", "entitlement": "active"})
        idn = evaluate_session()
        self.assertEqual(idn["account_state"], ACCOUNT_PENDING)
        self.assertEqual(idn["auth_state"], ENTITLEMENT_REQUIRED)

    def test_14_unknown_account(self):
        self.assertEqual(map_account_state({"name": "x"}), ACCOUNT_UNKNOWN)
        self._put({"id": 1, "name": "x"}, auth_mode="license")
        idn = evaluate_session()
        self.assertEqual(idn["account_state"], ACCOUNT_UNKNOWN)
        self.assertEqual(idn["auth_state"], AUTH_ERROR)

    def test_15_authenticated_but_disabled_cannot_produce(self):
        self._put({"id": 1, "status": "disabled", "plan": "pro", "entitlement": "active"})
        d = can_customer_produce(foundation=_ready_foundation())
        self.assertFalse(d["allowed"])
        self.assertEqual(d["block_reason"], "account_disabled")


class C02EntitlementTests(C02AuthBase):
    def _put(self, customer):
        persist_session(
            login_id="u",
            token="tok",
            customer=customer,
            api_base="https://lic.test",
            auth_mode="license",
        )

    def test_16_active_entitlement(self):
        self.assertEqual(map_entitlement_state({"entitlement": "active"}, auth_mode="license"), ENTITLEMENT_ACTIVE)
        self._put({"id": 1, "status": "active", "entitlement": "active", "plan": "pro"})
        self.assertEqual(evaluate_session()["entitlement_state"], ENTITLEMENT_ACTIVE)

    def test_17_no_entitlement(self):
        self.assertEqual(map_entitlement_state({"entitlement": "none"}, auth_mode="license"), ENTITLEMENT_NONE)
        self._put({"id": 1, "status": "active", "entitlement": "none"})
        idn = evaluate_session()
        self.assertEqual(idn["entitlement_state"], ENTITLEMENT_NONE)
        self.assertEqual(idn["auth_state"], ENTITLEMENT_REQUIRED)

    def test_18_expired_entitlement(self):
        self.assertEqual(map_entitlement_state({"entitlement": "expired"}), ENTITLEMENT_EXPIRED)
        self._put({"id": 1, "status": "active", "entitlement": "expired"})
        self.assertEqual(evaluate_session()["entitlement_state"], ENTITLEMENT_EXPIRED)

    def test_19_suspended_entitlement(self):
        self.assertEqual(map_entitlement_state({"entitlement": "suspended"}), ENTITLEMENT_SUSPENDED)
        self._put({"id": 1, "status": "active", "entitlement": "suspended"})
        self.assertEqual(evaluate_session()["entitlement_state"], ENTITLEMENT_SUSPENDED)

    def test_20_unknown_entitlement(self):
        # empty customer → UNKNOWN
        self.assertEqual(map_entitlement_state({}, auth_mode=""), ENTITLEMENT_UNKNOWN)

    def test_21_authenticated_no_entitlement_cannot_produce(self):
        self._put({"id": 1, "status": "active", "entitlement": "none"})
        d = can_customer_produce(foundation=_ready_foundation())
        self.assertFalse(d["allowed"])
        self.assertTrue(str(d["block_reason"]).startswith("entitlement_"))


class C02AuthorizationTests(C02AuthBase):
    def test_22_full_path_allowed(self):
        persist_session(
            login_id="ok",
            token="local-dev-token",
            customer={"id": 1, "status": "active", "plan": "dev", "entitlement": "active"},
            api_base="local",
            auth_mode="local_dev",
        )
        d = can_customer_produce(foundation=_ready_foundation())
        self.assertTrue(d["allowed"])
        self.assertTrue(d["identity"]["production_allowed"])

    def test_23_unauthenticated_c01_ready_blocked(self):
        d = can_customer_produce(foundation=_ready_foundation())
        self.assertFalse(d["allowed"])

    def test_24_entitlement_expired_blocked(self):
        persist_session(
            login_id="u",
            token="tok",
            customer={"id": 1, "status": "active", "entitlement": "expired"},
            api_base="https://x",
            auth_mode="license",
        )
        self.assertFalse(can_customer_produce(foundation=_ready_foundation())["allowed"])

    def test_25_account_disabled_blocked(self):
        persist_session(
            login_id="u",
            token="tok",
            customer={"id": 1, "status": "disabled", "entitlement": "active"},
            api_base="https://x",
            auth_mode="license",
        )
        self.assertFalse(can_customer_produce(foundation=_ready_foundation())["allowed"])

    def test_26_c01_readiness_blocked(self):
        persist_session(
            login_id="ok",
            token="local-dev-token",
            customer={"id": 1, "status": "active", "plan": "dev", "entitlement": "active"},
            api_base="local",
            auth_mode="local_dev",
        )
        d = can_customer_produce(foundation=_blocked_foundation())
        self.assertFalse(d["allowed"])
        self.assertEqual(d["block_reason"], "production_prerequisites_blocked")

    def test_27_c01_readiness_unknown_blocked(self):
        persist_session(
            login_id="ok",
            token="local-dev-token",
            customer={"id": 1, "status": "active", "plan": "dev", "entitlement": "active"},
            api_base="local",
            auth_mode="local_dev",
        )
        d = can_customer_produce(foundation=_unknown_foundation())
        self.assertFalse(d["allowed"])
        self.assertEqual(d["block_reason"], "production_prerequisites_blocked")


class C02SecurityTests(C02AuthBase):
    def test_28_secrets_absent_from_customer_projection(self):
        persist_session(
            login_id="sec",
            token="super-secret-access-token",
            customer={
                "id": 9,
                "name": "Sec",
                "status": "active",
                "plan": "dev",
                "entitlement": "active",
                "api_key": "sk-LEAK",
                "password": "pw",
            },
            api_base="local",
            auth_mode="local_dev",
        )
        idn = evaluate_session()
        blob = json.dumps(idn)
        self.assertNotIn("super-secret", blob)
        self.assertNotIn("sk-LEAK", blob)
        self.assertNotIn("password", blob)
        self.assertNotIn("api_key", blob)
        for k in idn:
            self.assertIn(k, IDENTITY_FIELDS)

    def test_29_secrets_absent_from_sanitize_and_login_errors(self):
        msg = sanitize_auth_error("Authorization: Bearer tokensecret api_key=abc")
        self.assertNotIn("tokensecret", msg)
        self.assertNotIn("abc", msg)
        with patch("app.customer_auth.local_login_permitted", return_value=False), patch(
            "app.api_client.LicenseClient"
        ) as LC:
            LC.return_value.login.side_effect = Exception("password=hunter2 token=xyz")
            res = authenticate("a", "b", "https://x")
        self.assertNotIn("hunter2", json.dumps(res))
        self.assertNotIn("xyz", json.dumps(res))

    def test_30_no_production_auth_bypass(self):
        src = inspect.getsource(__import__("app.customer_auth", fromlist=["can_customer_produce"]).can_customer_produce)
        self.assertNotIn("ALWAYS_ALLOW", src)
        self.assertNotIn("bypass_auth", src.lower())
        main_src = inspect.getsource(__import__("app.main", fromlist=["generate"]).generate)
        self.assertIn("can_customer_produce", main_src)
        # Unauthenticated must not produce even with ready foundation
        self.assertFalse(can_customer_produce(foundation=_ready_foundation())["allowed"])


class C02IntegrationTests(C02AuthBase):
    def test_31_status_includes_identity_no_token(self):
        from app.main import status

        with patch("app.customer_auth.local_login_permitted", return_value=True):
            authenticate("admin", "admin123", "local")
        with patch("pipeline.compose.probe_media_tool_capability", return_value={
            "FFMPEG_AVAILABLE": True,
            "FFPROBE_AVAILABLE": True,
        }):
            out = status()
        self.assertIn("identity", out)
        self.assertNotIn("token", json.dumps(out.get("identity") or {}))
        self.assertNotIn("local-dev-token", json.dumps(out))

    def test_32_workspace_requires_session(self):
        from app.main import workspace

        out = workspace()
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "login_required")
        self.assertEqual(out["identity"]["auth_state"], UNAUTHENTICATED)

    def test_33_generate_blocked_unauthenticated(self):
        from app.main import generate

        with patch("app.main._require_session", return_value=None):
            out = generate({"channel_id": 1, "video_type": "short"})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("error"), "login_required")

    def test_34_login_response_has_no_token(self):
        from app.main import login

        with patch("app.customer_auth.local_login_permitted", return_value=True):
            # login endpoint calls authenticate internally
            pass
        with patch("app.customer_auth.authenticate") as auth:
            auth.return_value = {
                "ok": True,
                "mode": "local_dev",
                "identity": {"auth_state": AUTHENTICATED, "logged_in": True},
                "customer": {"id": 1, "name": "L", "login_id": "admin", "status": "active", "plan": "dev"},
            }
            resp = login({"login_id": "admin", "password": "x", "api_base_url": "local"})
        body = json.loads(resp.body.decode())
        self.assertTrue(body["ok"])
        self.assertNotIn("token", body)
        self.assertNotIn("password", json.dumps(body))

    def test_35_single_auth_authority_module(self):
        auth_path = Path(__file__).resolve().parents[1] / "app" / "customer_auth.py"
        self.assertTrue(auth_path.is_file())
        main_src = Path(__file__).resolve().parents[1] / "app" / "main.py"
        text = main_src.read_text(encoding="utf-8")
        self.assertIn("from app.customer_auth import can_customer_produce", text)
        self.assertIn("from app.customer_auth import authenticate", text)
        # No parallel produce gate in foundation
        from app import customer_foundation as cf

        self.assertFalse(hasattr(cf, "can_customer_produce"))


if __name__ == "__main__":
    unittest.main()
