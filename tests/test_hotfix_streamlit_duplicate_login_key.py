"""
Hotfix — StreamlitDuplicateElementKey on Secure Login (DEF-PC-RA-002).

Cold-start process warmup previously did `import app` while Streamlit ran the
script as __main__, re-executing module-level login_ui() and registering
v3_final_access_key_field twice.
"""
import ast
import importlib
import inspect
import os
import re
import sys
import unittest
from collections import Counter
from unittest import mock


LOGIN_ACCESS_KEY = "v3_final_access_key_field"


def _app_source():
    app_path = os.path.join(os.getcwd(), "app.py")
    with open(app_path, encoding="utf-8-sig") as handle:
        return handle.read()


def _login_ui_block(source):
    return source.split("def login_ui():", 1)[1].split("\ndef ", 1)[0]


def _explicit_widget_keys(source_block):
    return re.findall(r"""\bkey\s*=\s*['\"]([^'\"]+)['\"]""", source_block)


class DuplicateLoginKeyHotfixTests(unittest.TestCase):
    def test_login_access_key_appears_once_in_app_source(self):
        source = _app_source()
        self.assertEqual(source.count(f'key="{LOGIN_ACCESS_KEY}"'), 1)
        self.assertEqual(source.count(f"key='{LOGIN_ACCESS_KEY}'"), 0)

    def test_login_ui_widget_keys_are_unique(self):
        login_block = _login_ui_block(_app_source())
        keys = _explicit_widget_keys(login_block)
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        self.assertEqual(duplicates, [], f"Duplicate widget keys in login_ui: {duplicates}")

    def test_streamlit_entrypoint_guarded_for_import(self):
        source = _app_source()
        marker = "# Main application flow"
        self.assertIn(marker, source)
        tail = source.split(marker, 1)[1]
        self.assertIn('if __name__ == "__main__":', tail)
        self.assertIn('elif __name__ == "__main__":', tail)
        self.assertRegex(
            tail,
            r'if __name__ == "__main__":\s*\n\s*main\(\)',
        )
        self.assertRegex(
            tail,
            r'if __name__ == "__main__" and \(not st\.session_state\.auth or not check_session_timeout\(\)\):\s*\n\s*login_ui\(\)',
        )
        # Unguarded top-level main()/login_ui() must not remain after the marker.
        tree = ast.parse(source)
        entry_calls = []
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id in {"main", "login_ui"}:
                    entry_calls.append(func.id)
        self.assertEqual(
            entry_calls,
            [],
            "Module-level main()/login_ui() calls must be under __main__ guard",
        )

    def test_warmup_prefers_main_module_over_import_app(self):
        modules = importlib.import_module("modules")
        modules.clear_process_startup_warmup_cache()
        fake_main = type(sys)("fake_main")
        fake_main.PRIMARY_NAV_ITEMS = (("Dashboard", "Dashboard"),)
        fake_main.SIDEBAR_NAV_GROUPS = ()

        real_import = __import__

        def _guarded_import(name, *args, **kwargs):
            if name == "app" or (isinstance(name, str) and name.startswith("app.")):
                raise AssertionError("warmup must not import app when __main__ has nav metadata")
            return real_import(name, *args, **kwargs)

        with mock.patch.dict(sys.modules, {"__main__": fake_main}):
            with mock.patch("database.get_startup_config_signature", return_value="sig-dup-key"):
                with mock.patch(
                    "database.run_canonical_startup_pipeline",
                    return_value={"startup_ok": True, "ok": True, "startup_route": "postgres_runtime", "elapsed_ms": 1.0},
                ):
                    with mock.patch("database.get_connection", return_value=mock.MagicMock()):
                        with mock.patch("builtins.__import__", side_effect=_guarded_import):
                            result = modules.run_process_startup_warmup(force=True)

        self.assertIn("menu_metadata", result.get("warmed_items", []))
        self.assertTrue(all(not str(err).startswith("menu_metadata:") for err in result.get("warmup_errors", [])))

    def test_warmup_source_documents_main_preference(self):
        modules = importlib.import_module("modules")
        source = inspect.getsource(modules.run_process_startup_warmup)
        self.assertIn('sys.modules.get("__main__")', source)
        self.assertIn("PRIMARY_NAV_ITEMS", source)
        self.assertIn("StreamlitDuplicateElementKey", source)


if __name__ == "__main__":
    unittest.main()
