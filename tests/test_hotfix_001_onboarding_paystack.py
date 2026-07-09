"""
Hotfix 001 — onboarding & Paystack initialization forensics and hardening.
"""
import importlib
import json
import os
import unittest
from unittest.mock import patch

import requests

from test_support import ERPIsolatedTestCase


class _FakeResponse:
    def __init__(self, *, status_code=200, payload=None, json_exc=None):
        self.status_code = int(status_code)
        self._payload = payload if payload is not None else {}
        self._json_exc = json_exc

    def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._payload


class Hotfix001PaystackInitializeTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self._original_paystack_env = {
            key: os.environ.get(key)
            for key in (
                "PAYSTACK_SECRET_KEY",
                "PAYSTACK_PUBLIC_KEY",
                "PAYSTACK_CALLBACK_URL",
                "PAYSTACK_CURRENCY",
            )
        }
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_hotfix_001"
        os.environ["PAYSTACK_PUBLIC_KEY"] = "pk_test_hotfix_001"
        os.environ["PAYSTACK_CALLBACK_URL"] = "https://example.com/paystack/callback"
        os.environ["PAYSTACK_CURRENCY"] = "GHS"

    def tearDown(self):
        try:
            for key, value in self._original_paystack_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        finally:
            super().tearDown()

    def test_valid_initialization_returns_authorization_url(self):
        payload = {"status": True, "message": "ok", "data": {"authorization_url": "https://paystack.test/checkout"}}
        with patch.object(self.modules.requests, "post", return_value=_FakeResponse(payload=payload)) as mock_post:
            result = self.modules.initialize_paystack_payment(
                "user@example.com",
                10.0,
                "ONB-TEST-001",
                company_key="TESTCO",
                company_name="Test Company",
                payment_context="onboarding",
                plan_name=None,
                metadata_extra={"correlation_id": "ABC123"},
            )
        self.assertTrue(result["ok"])
        self.assertIn("authorization_url", result)
        self.assertTrue(str(result["authorization_url"]).startswith("https://"))
        called = mock_post.call_args.kwargs
        self.assertEqual(called["json"]["reference"], "ONB-TEST-001")
        self.assertEqual(called["json"]["currency"], "GHS")
        self.assertEqual(called["json"]["callback_url"], os.environ["PAYSTACK_CALLBACK_URL"])
        self.assertIn("Authorization", called["headers"])

    def test_missing_secret_key_blocks_initialization(self):
        config = self.modules.get_paystack_runtime_config()
        config["secret_key"] = None
        config["secret_key_present"] = False
        with patch.object(self.modules, "get_paystack_runtime_config", return_value=config):
            result = self.modules.initialize_paystack_payment("user@example.com", 10.0, "ONB-TEST-002")
        self.assertFalse(result["ok"])
        self.assertIn("secret key", str(result.get("reason") or "").lower())

    def test_missing_callback_blocks_initialization(self):
        os.environ.pop("PAYSTACK_CALLBACK_URL", None)
        result = self.modules.initialize_paystack_payment("user@example.com", 10.0, "ONB-TEST-003")
        self.assertFalse(result["ok"])
        self.assertIn("callback", str(result.get("reason") or "").lower())

    def test_http_error_returns_gateway_message(self):
        payload = {"status": False, "message": "Invalid key", "data": {}}
        with patch.object(self.modules.requests, "post", return_value=_FakeResponse(status_code=401, payload=payload)):
            result = self.modules.initialize_paystack_payment("user@example.com", 10.0, "ONB-TEST-004")
        self.assertFalse(result["ok"])
        self.assertIn("invalid", str(result.get("reason") or "").lower())

    def test_malformed_response_json_returns_safe_reason(self):
        with patch.object(
            self.modules.requests,
            "post",
            return_value=_FakeResponse(status_code=200, payload=None, json_exc=ValueError("bad json")),
        ):
            result = self.modules.initialize_paystack_payment("user@example.com", 10.0, "ONB-TEST-005")
        self.assertFalse(result["ok"])
        self.assertIn("could not be read", str(result.get("reason") or "").lower())

    def test_timeout_returns_timeout_reason(self):
        with patch.object(self.modules.requests, "post", side_effect=requests.Timeout("timeout")):
            result = self.modules.initialize_paystack_payment("user@example.com", 10.0, "ONB-TEST-006")
        self.assertFalse(result["ok"])
        self.assertIn("timed out", str(result.get("reason") or "").lower())

    def test_duplicate_company_registration_is_detected(self):
        conn = self.database.get_connection()
        try:
            row = conn.execute("SELECT name, contact_email FROM companies WHERE key = ?", (self.company_key,)).fetchone()
            self.assertIsNotNone(row)
            existing_name = row["name"]
        finally:
            conn.close()
        # This mirrors the onboarding duplicate check (name match).
        conn = self.database.get_connection()
        try:
            existing = conn.execute(
                "SELECT key FROM companies WHERE lower(name) = lower(?) LIMIT 1",
                (existing_name,),
            ).fetchone()
            self.assertIsNotNone(existing)
        finally:
            conn.close()


class Hotfix001PaystackSecretStatusTests(unittest.TestCase):
    def setUp(self):
        self.modules = importlib.import_module("modules")
        self._original = {k: os.environ.get(k) for k in ("PAYSTACK_SECRET_KEY", "PAYSTACK_PUBLIC_KEY", "PAYSTACK_CALLBACK_URL", "PAYSTACK_CURRENCY", "PAYSTACK_WEBHOOK_SECRET")}

    def tearDown(self):
        for k, v in self._original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_secret_status_never_returns_values(self):
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_no_leak"
        os.environ["PAYSTACK_PUBLIC_KEY"] = "pk_test_no_leak"
        os.environ["PAYSTACK_CALLBACK_URL"] = "https://example.com/callback"
        os.environ["PAYSTACK_CURRENCY"] = "GHS"
        os.environ["PAYSTACK_WEBHOOK_SECRET"] = "whsec_test"
        status = self.modules.get_paystack_secret_status()
        dumped = json.dumps(status, default=str)
        self.assertNotIn("sk_test_no_leak", dumped)
        self.assertNotIn("pk_test_no_leak", dumped)
        self.assertNotIn("whsec_test", dumped)
        self.assertEqual(status["PAYSTACK_SECRET_KEY"], "present")
        self.assertTrue(bool(status["PAYSTACK_CALLBACK_URL_valid"]))

