"""Tests for Workspace Research & Script Endpoint Mock Default Resolution (C-01).

Validates that:
1. Workspace endpoints default to LIVE mode (use_mock=False).
2. Mock mode is only enabled when explicitly requested via payload or env var.
3. Responses clearly report `execution_mode` ("LIVE" vs "MOCK") and `use_mock` (False vs True).
4. Default parameters in customer_trs_workflow.py are production-safe (use_mock=False).
"""

from __future__ import annotations

import inspect
from unittest import TestCase, mock
from fastapi.testclient import TestClient

from app.main import app, _resolve_workspace_mock_flag
import app.customer_trs_workflow as trs_workflow


class TestWorkspaceMockDefault(TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_resolve_workspace_mock_flag_defaults(self):
        """Without any flag or env override, default is False (Live mode)."""
        self.assertFalse(_resolve_workspace_mock_flag({}))
        self.assertFalse(_resolve_workspace_mock_flag({"channel_id": 1}))

    def test_02_resolve_workspace_mock_flag_explicit_payload(self):
        """Explicit payload flags take precedence."""
        self.assertTrue(_resolve_workspace_mock_flag({"use_mock": True}))
        self.assertFalse(_resolve_workspace_mock_flag({"use_mock": False}))
        self.assertTrue(_resolve_workspace_mock_flag({"mode": "mock"}))
        self.assertTrue(_resolve_workspace_mock_flag({"execution_mode": "mock_deterministic"}))
        self.assertFalse(_resolve_workspace_mock_flag({"mode": "live"}))
        self.assertFalse(_resolve_workspace_mock_flag({"mode": "production"}))

    def test_03_resolve_workspace_mock_flag_env_override(self):
        """Environment variable override works when payload does not specify."""
        with mock.patch.dict("os.environ", {"AUTOMOVIE_WORKSPACE_MOCK": "1"}):
            self.assertTrue(_resolve_workspace_mock_flag({}))
        with mock.patch.dict("os.environ", {"AUTOMOVIE_WORKSPACE_MOCK": "0"}):
            self.assertFalse(_resolve_workspace_mock_flag({}))
        # Explicit payload still overrides env var
        with mock.patch.dict("os.environ", {"AUTOMOVIE_WORKSPACE_MOCK": "1"}):
            self.assertFalse(_resolve_workspace_mock_flag({"use_mock": False}))

    def test_04_customer_trs_workflow_signatures_default_to_false(self):
        """Direct function defaults in customer_trs_workflow must be use_mock=False."""
        sig_r = inspect.signature(trs_workflow.run_research)
        self.assertEqual(sig_r.parameters["use_mock"].default, False)

        sig_s = inspect.signature(trs_workflow.generate_script)
        self.assertEqual(sig_s.parameters["use_mock"].default, False)

    @mock.patch("app.main._require_session", return_value=True)
    @mock.patch("app.main._session_login_id", return_value="test_owner")
    @mock.patch("app.main._owned_channel_or_err", return_value=({"id": 101, "owner_login_id": "test_owner"}, None))
    @mock.patch("app.customer_trs_workflow.run_research")
    def test_05_workspace_research_endpoint_live_default(
        self, mock_run_research, mock_owned, mock_session_id, mock_req_session
    ):
        """POST /api/workspace/research with no use_mock defaults to live mode (use_mock=False)."""
        mock_run_research.return_value = {"ok": True, "fact_pack": {}}

        response = self.client.post("/api/workspace/research", json={"channel_id": 101})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check call arguments
        mock_run_research.assert_called_once_with("test_owner", {"id": 101, "owner_login_id": "test_owner"}, use_mock=False)
        # Check response metadata
        self.assertEqual(data["execution_mode"], "LIVE")
        self.assertEqual(data["use_mock"], False)

    @mock.patch("app.main._require_session", return_value=True)
    @mock.patch("app.main._session_login_id", return_value="test_owner")
    @mock.patch("app.main._owned_channel_or_err", return_value=({"id": 101, "owner_login_id": "test_owner"}, None))
    @mock.patch("app.customer_trs_workflow.run_research")
    def test_06_workspace_research_endpoint_explicit_mock(
        self, mock_run_research, mock_owned, mock_session_id, mock_req_session
    ):
        """POST /api/workspace/research with use_mock=True enables mock mode."""
        mock_run_research.return_value = {"ok": True, "fact_pack": {}}

        response = self.client.post("/api/workspace/research", json={"channel_id": 101, "use_mock": True})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        mock_run_research.assert_called_once_with("test_owner", {"id": 101, "owner_login_id": "test_owner"}, use_mock=True)
        self.assertEqual(data["execution_mode"], "MOCK")
        self.assertEqual(data["use_mock"], True)

    @mock.patch("app.main._require_session", return_value=True)
    @mock.patch("app.main._session_login_id", return_value="test_owner")
    @mock.patch("app.main._owned_channel_or_err", return_value=({"id": 101, "owner_login_id": "test_owner"}, None))
    @mock.patch("app.customer_trs_workflow.generate_script")
    def test_07_workspace_script_endpoint_live_default(
        self, mock_gen_script, mock_owned, mock_session_id, mock_req_session
    ):
        """POST /api/workspace/script with no use_mock defaults to live mode (use_mock=False)."""
        mock_gen_script.return_value = {"ok": True, "plan": {}}

        response = self.client.post("/api/workspace/script", json={"channel_id": 101, "video_type": "short"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check call arguments
        _, kwargs = mock_gen_script.call_args
        self.assertEqual(kwargs["use_mock"], False)
        # Check response metadata
        self.assertEqual(data["execution_mode"], "LIVE")
        self.assertEqual(data["use_mock"], False)

    @mock.patch("app.main._require_session", return_value=True)
    @mock.patch("app.main._session_login_id", return_value="test_owner")
    @mock.patch("app.main._owned_channel_or_err", return_value=({"id": 101, "owner_login_id": "test_owner"}, None))
    @mock.patch("app.customer_trs_workflow.generate_script")
    def test_08_workspace_script_endpoint_explicit_mock(
        self, mock_gen_script, mock_owned, mock_session_id, mock_req_session
    ):
        """POST /api/workspace/script with use_mock=True enables mock mode."""
        mock_gen_script.return_value = {"ok": True, "plan": {}}

        response = self.client.post("/api/workspace/script", json={"channel_id": 101, "video_type": "short", "use_mock": True})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        _, kwargs = mock_gen_script.call_args
        self.assertEqual(kwargs["use_mock"], True)
        self.assertEqual(data["execution_mode"], "MOCK")
        self.assertEqual(data["use_mock"], True)
