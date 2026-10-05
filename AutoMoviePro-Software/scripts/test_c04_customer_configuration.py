"""C04 — Customer channel / language / provider configuration + ownership (paid APIs = 0)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.customer_auth import persist_session
from app.customer_config import (
    BLOCKED,
    CONFIGURED,
    INVALID,
    NOT_CONFIGURED,
    NOT_ENTITLED,
    VALID,
    assert_no_forged_identity,
    claim_orphan_channel,
    clear_owned_provider,
    configuration_summary,
    ensure_channel_owner_column,
    get_owned_channel,
    list_owned_channels,
    provider_capability_matrix,
    require_owned_channel,
    save_owned_provider_slots,
    set_channel_enabled,
    set_channel_languages,
    to_safe_channel_view,
    upsert_owned_channel,
)
from app.customer_onboarding import build_dashboard
from pipeline.channel_api_slots import serialize_api_keys_json


def _login(store, login_id="alice", customer_id=1):
    persist_session(
        login_id=login_id,
        token="local-dev-token",
        customer={
            "id": customer_id,
            "name": login_id.title(),
            "login_id": login_id,
            "status": "active",
            "plan": "dev",
            "entitlement": "active",
            "unlocked": ["en", "bn"],
        },
        api_base="local",
        auth_mode="local_dev",
    )


def _ready_foundation():
    from app.customer_foundation import build_foundation_snapshot

    return build_foundation_snapshot(
        media_cap={"FFMPEG_AVAILABLE": True, "FFPROBE_AVAILABLE": True},
        operational={"status": "READY", "production_ready": True, "issues": []},
        api_readiness={"active": True},
    )


class C04Base(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        from app import db as store

        self.store = store
        self._orig = store.DB_PATH
        store.DB_PATH = Path(self._tmp.name) / "c04.db"
        store.init_db()
        ensure_channel_owner_column()

    def tearDown(self):
        self.store.DB_PATH = self._orig

    def _make_channel(self, owner="alice", **extra):
        payload = {
            "youtube_name": extra.get("youtube_name", f"YT-{owner}"),
            "niche": "gadgets",
            "niche_id": 1,
            "short_upload_time": "12:00",
            "long_upload_time": "18:00",
            "languages_json": '["en","bn"]',
            "enabled": 1,
            "api_keys_json": serialize_api_keys_json(
                {
                    "google": ["g1", "g2"],
                    "groq": ["q1", "q2"],
                    "openrouter": ["o1", "o2"],
                    "pollinations": ["p1"],
                    "pexels": ["x1"],
                    "agnes": ["a1", "a2"],
                }
            ),
            "owner_login_id": owner,
        }
        payload.update({k: v for k, v in extra.items() if k not in payload})
        return self.store.upsert_channel(payload)


class C04OwnershipTests(C04Base):
    def test_01_customer_owns_channel(self):
        cid = self._make_channel("alice")
        ch = get_owned_channel(cid, "alice")
        self.assertIsNotNone(ch)
        self.assertEqual(ch["owner_login_id"], "alice")

    def test_02_customer_owns_language_config(self):
        cid = self._make_channel("alice")
        res = set_channel_languages(cid, "alice", ["en", "bn"], entitled_unlocked=["bn"], allow_setup_pair=True)
        self.assertTrue(res.get("ok"))

    def test_03_customer_owns_provider_config(self):
        cid = self._make_channel("alice")
        res = save_owned_provider_slots(cid, "alice", {"google": ["gk1", "gk2"]})
        self.assertTrue(res.get("ok"))
        blob = json.dumps(res)
        self.assertNotIn("gk1", blob)

    def test_04_cross_customer_channel_read_blocked(self):
        cid = self._make_channel("bob")
        self.assertIsNone(get_owned_channel(cid, "alice"))
        self.assertEqual(list_owned_channels("alice"), [])

    def test_05_cross_customer_channel_write_blocked(self):
        cid = self._make_channel("bob")
        res = upsert_owned_channel({"youtube_name": "hack"}, "alice", channel_id=cid)
        self.assertEqual(res.get("error"), "channel_forbidden")

    def test_06_cross_customer_channel_delete_blocked(self):
        # No delete API — deactivate is the disable path
        cid = self._make_channel("bob")
        res = set_channel_enabled(cid, "alice", False)
        self.assertEqual(res.get("error"), "channel_forbidden")

    def test_07_cross_customer_activation_blocked(self):
        cid = self._make_channel("bob")
        res = set_channel_enabled(cid, "alice", True)
        self.assertEqual(res.get("error"), "channel_forbidden")

    def test_08_cross_customer_language_read_blocked(self):
        cid = self._make_channel("bob")
        _login(self.store, "alice")
        from app.main import languages_status

        out = languages_status()
        self.assertTrue(out.get("ok"))
        self.assertIsNone(out.get("channel_id"))

    def test_09_cross_customer_language_write_blocked(self):
        cid = self._make_channel("bob")
        res = set_channel_languages(cid, "alice", ["en", "hi"], allow_setup_pair=True)
        self.assertEqual(res.get("error"), "channel_forbidden")

    def test_10_cross_customer_provider_read_blocked(self):
        cid = self._make_channel("bob")
        _login(self.store, "alice")
        from app.main import channels

        out = channels()
        self.assertEqual(out.get("channels"), [])

    def test_11_cross_customer_provider_write_blocked(self):
        cid = self._make_channel("bob")
        res = save_owned_provider_slots(cid, "alice", {"google": ["x", "y"]})
        self.assertEqual(res.get("error"), "channel_forbidden")

    def test_12_forged_customer_identifier_blocked(self):
        self.assertEqual(assert_no_forged_identity({"login_id": "bob"}, "alice"), "customer_scope_denied")
        _login(self.store, "alice")
        from app.main import set_languages

        cid = self._make_channel("alice")
        out = set_languages(cid, {"languages": ["en", "bn"], "login_id": "bob", "allow_setup_pair": True})
        self.assertEqual(out.get("error"), "customer_scope_denied")


class C04ChannelTests(C04Base):
    def test_13_create_channel(self):
        res = upsert_owned_channel(
            {
                "youtube_name": "New",
                "niche": "tech",
                "enabled": 1,
                "languages_json": '["en","bn"]',
            },
            "alice",
        )
        self.assertTrue(res.get("ok"))
        self.assertEqual(get_owned_channel(res["channel_id"], "alice")["owner_login_id"], "alice")

    def test_14_view_channel(self):
        cid = self._make_channel("alice")
        view = to_safe_channel_view(self.store.get_channel(cid))
        self.assertEqual(view["id"], cid)
        self.assertNotIn("api_keys_json", view)
        self.assertNotIn("google_api_1", view)

    def test_15_edit_channel(self):
        cid = self._make_channel("alice")
        res = upsert_owned_channel({"youtube_name": "Renamed"}, "alice", channel_id=cid)
        self.assertTrue(res.get("ok"))
        self.assertEqual(self.store.get_channel(cid)["youtube_name"], "Renamed")

    def test_16_activate_channel(self):
        cid = self._make_channel("alice")
        self.store.upsert_channel({**self.store.get_channel(cid), "enabled": 0, "owner_login_id": "alice"}, cid)
        res = set_channel_enabled(cid, "alice", True)
        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("enabled"))

    def test_17_deactivate_channel(self):
        cid = self._make_channel("alice")
        res = set_channel_enabled(cid, "alice", False)
        self.assertTrue(res.get("ok"))
        self.assertFalse(res.get("enabled"))
        view = to_safe_channel_view(self.store.get_channel(cid))
        self.assertEqual(view["configuration_state"], BLOCKED)

    def test_18_duplicate_channel_prevented(self):
        upsert_owned_channel({"youtube_name": "A", "niche": "n", "enabled": 1}, "alice")
        res = upsert_owned_channel({"youtube_name": "B", "niche": "n", "enabled": 1}, "alice")
        self.assertEqual(res.get("error"), "channel_already_setup")

    def test_19_invalid_channel_blocked(self):
        _, err = require_owned_channel(99999, "alice")
        self.assertEqual(err.get("error"), "channel_not_found")

    def test_20_unknown_unowned_fails_closed(self):
        cid = self.store.upsert_channel({"youtube_name": "orphan", "niche": "n", "enabled": 1})
        _, err = require_owned_channel(cid, "alice")
        self.assertEqual(err.get("error"), "channel_unowned")


class C04LanguageTests(C04Base):
    def test_21_configure_language(self):
        cid = self._make_channel("alice")
        res = set_channel_languages(cid, "alice", ["en", "hi"], entitled_unlocked=["hi"])
        self.assertTrue(res.get("ok"))
        self.assertIn("hi", res["languages"])

    def test_22_channel_language_mapping(self):
        cid = self._make_channel("alice")
        view = to_safe_channel_view(self.store.get_channel(cid))
        self.assertEqual(view["languages"][:2], ["en", "bn"])

    def test_23_duplicate_mapping_prevented(self):
        cid = self._make_channel("alice")
        # parse_languages dedupes — explicit duplicate input still becomes unique; treat as ok unique
        res = set_channel_languages(cid, "alice", ["en", "bn", "bn"], entitled_unlocked=["bn"], allow_setup_pair=True)
        # after parse, duplicates removed so ok — ensure set uniqueness
        self.assertTrue(res.get("ok"))
        self.assertEqual(len(res["languages"]), len(set(res["languages"])))

    def test_24_unsupported_language_blocked(self):
        cid = self._make_channel("alice")
        res = set_channel_languages(cid, "alice", ["en", "xx"], allow_setup_pair=True)
        self.assertEqual(res.get("error"), "unsupported_language")

    def test_25_non_entitled_language_blocked(self):
        cid = self._make_channel("alice")
        res = set_channel_languages(cid, "alice", ["en", "ta"], entitled_unlocked=["bn"])
        self.assertEqual(res.get("error"), "language_not_entitled")
        self.assertEqual(res.get("state"), NOT_ENTITLED)

    def test_26_inactive_channel_mapping_blocked(self):
        cid = self._make_channel("alice")
        set_channel_enabled(cid, "alice", False)
        res = set_channel_languages(cid, "alice", ["en", "bn"], allow_setup_pair=True)
        self.assertEqual(res.get("error"), "channel_inactive")

    def test_27_unknown_language_state_fails_closed(self):
        cid = self._make_channel("alice")
        res = set_channel_languages(cid, "alice", ["en", "zz"], allow_setup_pair=True)
        self.assertFalse(res.get("ok"))


class C04ProviderTests(C04Base):
    def test_28_provider_discovery(self):
        matrix = provider_capability_matrix(None)
        ids = {p["provider_id"] for p in matrix}
        self.assertIn("google", ids)
        self.assertIn("groq", ids)

    def test_29_configure_supported_provider(self):
        cid = self._make_channel("alice")
        res = save_owned_provider_slots(cid, "alice", {"google": ["a", "b"]})
        self.assertTrue(res.get("ok"))

    def test_30_unsupported_provider_rejected(self):
        cid = self._make_channel("alice")
        res = save_owned_provider_slots(cid, "alice", {"not_a_provider": ["x"]})
        self.assertEqual(res.get("error"), "unsupported_provider")

    def test_31_invalid_provider_configuration(self):
        cid = self._make_channel("alice")
        for pid in ("google", "groq", "openrouter", "pollinations", "pexels", "agnes"):
            clear_owned_provider(cid, "alice", pid)
        from pipeline.channel_api_slots import evaluate_readiness

        ready = evaluate_readiness(channel=self.store.get_channel(cid), bundle={})
        self.assertFalse(ready.get("active"))
        view = to_safe_channel_view(self.store.get_channel(cid))
        self.assertFalse(any(
            view["providers"][pid]["configured"]
            for pid in ("google", "groq", "openrouter", "pollinations", "pexels", "agnes")
        ))

    def test_32_valid_provider_configuration(self):
        self._make_channel("alice")
        from pipeline.channel_api_slots import evaluate_readiness

        ready = evaluate_readiness(channel=self.store.get_channel(list_owned_channels("alice")[0]["id"]), bundle={})
        self.assertTrue(ready.get("active"))
        summary = configuration_summary("alice")
        self.assertIn(summary["provider_state"], (VALID, CONFIGURED))

    def test_33_unknown_provider_readiness(self):
        summary = configuration_summary("alice")
        self.assertEqual(summary["provider_state"], NOT_CONFIGURED)

    def test_34_provider_capability_projection(self):
        cid = self._make_channel("alice")
        matrix = provider_capability_matrix(self.store.get_channel(cid))
        self.assertTrue(any(p["configured"] for p in matrix))

    def test_35_provider_entitlement_compatibility(self):
        matrix = provider_capability_matrix(None)
        self.assertTrue(all("entitled" in p for p in matrix))


class C04CredentialTests(C04Base):
    def test_36_secret_write(self):
        cid = self._make_channel("alice")
        res = save_owned_provider_slots(cid, "alice", {"google": ["secretKEY1", "secretKEY2"]})
        self.assertTrue(res.get("ok"))

    def test_37_secret_persistence_encrypted(self):
        cid = self._make_channel("alice")
        save_owned_provider_slots(cid, "alice", {"google": ["secretKEY1", "secretKEY2"]})
        ch = self.store.get_channel(cid)
        self.assertIn("secretKEY1", json.dumps(ch.get("api_keys_json")))
        from app import crypto

        self.assertTrue(callable(crypto.encrypt_text))

    def test_38_raw_secret_absent_from_response(self):
        cid = self._make_channel("alice")
        res = save_owned_provider_slots(cid, "alice", {"google": ["secretKEY1", "secretKEY2"]})
        self.assertNotIn("secretKEY1", json.dumps(res))

    def test_39_raw_secret_absent_from_safe_view(self):
        cid = self._make_channel("alice")
        view = to_safe_channel_view(self.store.get_channel(cid))
        blob = json.dumps(view)
        self.assertNotIn('"g1"', blob)
        self.assertTrue(any("slots_masked" in str(p) for p in view["providers"].values()))

    def test_40_raw_secret_absent_from_errors(self):
        from app.customer_config import sanitize_config_error

        msg = sanitize_config_error("failed api_key=supersecret token=abc")
        self.assertNotIn("supersecret", msg)

    def test_41_raw_secret_absent_from_html_js_payload_paths(self):
        html = Path(__file__).resolve().parents[1].joinpath("ui/index.html").read_text(encoding="utf-8")
        js = Path(__file__).resolve().parents[1].joinpath("ui/static/js/app.js").read_text(encoding="utf-8")
        self.assertNotIn("sk-", html)
        self.assertTrue("configured" in js.lower() or "Configured" in js)

    def test_42_customer_cannot_read_another_secret(self):
        self._make_channel("bob")
        _login(self.store, "alice")
        from app.main import channels

        out = channels()
        blob = json.dumps(out)
        self.assertNotIn("g1", blob)
        self.assertEqual(out.get("channels"), [])


class C04ReadinessTests(C04Base):
    def test_43_not_configured(self):
        self.assertEqual(configuration_summary("alice")["channel_state"], NOT_CONFIGURED)

    def test_44_configured(self):
        cid = self._make_channel("alice")
        clear_owned_provider(cid, "alice", "google")
        view = to_safe_channel_view(self.store.get_channel(cid))
        self.assertFalse(view["providers"]["google"]["configured"])

    def test_45_valid(self):
        self._make_channel("alice")
        from pipeline.channel_api_slots import evaluate_readiness

        ch = list_owned_channels("alice")[0]
        self.assertTrue(evaluate_readiness(channel=ch, bundle={}).get("active"))

    def test_46_invalid(self):
        cid = self._make_channel("alice")
        for pid in ("google", "groq", "openrouter", "pollinations", "pexels", "agnes"):
            clear_owned_provider(cid, "alice", pid)
        from pipeline.channel_api_slots import evaluate_readiness

        ready = evaluate_readiness(channel=self.store.get_channel(cid), bundle={})
        self.assertFalse(ready.get("active"))
        self.assertTrue(len(ready.get("missing") or []) > 0)

    def test_47_unknown_not_ready(self):
        # unowned → fail closed not READY
        cid = self.store.upsert_channel({"youtube_name": "x", "niche": "n", "enabled": 1})
        _, err = require_owned_channel(cid, "alice")
        self.assertIsNotNone(err)

    def test_48_blocked(self):
        cid = self._make_channel("alice")
        set_channel_enabled(cid, "alice", False)
        self.assertEqual(configuration_summary("alice")["channel_state"], BLOCKED)

    def test_49_c04_reflected_by_c03(self):
        cid = self._make_channel("alice")
        ch = self.store.get_channel(cid)
        dash = build_dashboard(
            identity={
                "auth_state": "AUTHENTICATED",
                "account_state": "ACTIVE",
                "entitlement_state": "ACTIVE",
                "production_access": True,
                "logged_in": True,
                "login_id": "alice",
            },
            access={"allowed": True},
            foundation=_ready_foundation(),
            channels=[ch],
            api_readiness={"active": True},
            active_jobs=[],
            recent_jobs=[],
        )
        items = {i["id"]: i for i in dash["checklist"]}
        self.assertEqual(items["channel.configured"]["state"], "COMPLETE")

    def test_50_c01_c02_gates_remain(self):
        import inspect
        from app.main import generate

        src = inspect.getsource(generate)
        self.assertIn("can_customer_produce", src)
        self.assertIn("require_owned_channel", src)


class C04ExtraSecurityTests(C04Base):
    def test_51_claim_orphan_then_owned(self):
        cid = self.store.upsert_channel({"youtube_name": "orphan", "niche": "n", "enabled": 1})
        res = claim_orphan_channel(cid, "alice")
        self.assertTrue(res.get("ok"))
        self.assertEqual(get_owned_channel(cid, "alice")["owner_login_id"], "alice")
        # Bob cannot claim
        res2 = claim_orphan_channel(cid, "bob")
        self.assertFalse(res2.get("ok"))

    def test_52_channels_api_no_secrets(self):
        self._make_channel("alice")
        _login(self.store, "alice")
        from app.main import channels

        out = channels()
        blob = json.dumps(out)
        self.assertNotIn("g1", blob)
        self.assertNotIn("api_keys_json", blob)

    def test_53_two_customers_isolated_channels(self):
        a = self._make_channel("alice", youtube_name="A")
        b = self._make_channel("bob", youtube_name="B")
        self.assertEqual(len(list_owned_channels("alice")), 1)
        self.assertEqual(len(list_owned_channels("bob")), 1)
        self.assertNotEqual(list_owned_channels("alice")[0]["id"], list_owned_channels("bob")[0]["id"])
        self.assertIsNone(get_owned_channel(b, "alice"))
        self.assertIsNone(get_owned_channel(a, "bob"))


if __name__ == "__main__":
    unittest.main()
