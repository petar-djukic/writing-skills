#!/usr/bin/env python3
"""OLLAMA_WAIT_SERVER rides out a supervisor restart (GH-173). Offline."""
import importlib
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, ".."))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import rewrite  # noqa: E402


def _ok(body=b'{"response":"ok"}'):
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = body
    return cm


class WaitServer(unittest.TestCase):
    def setUp(self):
        importlib.reload(rewrite)

    def tearDown(self):
        os.environ.pop("OLLAMA_WAIT_SERVER", None)
        importlib.reload(rewrite)

    def test_default_off_behavior_unchanged(self):
        calls = {"n": 0}

        def refused(req, timeout=None):
            calls["n"] += 1
            raise ConnectionRefusedError("refused")

        with mock.patch.object(rewrite.time, "sleep", lambda s: None):
            with mock.patch.object(rewrite.urllib.request, "urlopen", refused):
                with self.assertRaises(RuntimeError) as ctx:
                    rewrite.generate("p", model="gemma4:12b")
        self.assertEqual(calls["n"], rewrite.OLLAMA_MAX_RETRIES)
        self.assertIn("never came up", str(ctx.exception))
        self.assertIn("OLLAMA_WAIT_SERVER=600", str(ctx.exception))

    def test_wait_rides_out_a_restart_without_burning_attempts(self):
        os.environ["OLLAMA_WAIT_SERVER"] = "60"
        importlib.reload(rewrite)
        state = {"gen": 0, "poll": 0}

        def flapping(req, timeout=None):
            if req.full_url.endswith("/api/tags"):
                state["poll"] += 1
                if state["poll"] < 3:
                    raise ConnectionRefusedError("still down")
                return _ok(b"{}")
            state["gen"] += 1
            if state["gen"] == 1:
                raise ConnectionRefusedError("supervisor reaped it")
            return _ok()

        with mock.patch.object(rewrite.time, "sleep", lambda s: None):
            with mock.patch.object(rewrite.urllib.request, "urlopen", flapping):
                out = rewrite.generate("p", model="gemma4:12b")
        self.assertEqual(out, "ok")
        self.assertEqual(state["gen"], 2)
        self.assertGreaterEqual(state["poll"], 3)

    def test_vanished_mid_run_names_the_supervisor(self):
        os.environ["OLLAMA_WAIT_SERVER"] = "1"
        importlib.reload(rewrite)
        state = {"gen": 0}

        def up_then_gone(req, timeout=None):
            if req.full_url.endswith("/api/tags"):
                raise ConnectionRefusedError("gone")
            state["gen"] += 1
            if state["gen"] == 1:
                return _ok()
            raise ConnectionRefusedError("reaped")

        with mock.patch.object(rewrite.time, "sleep", lambda s: None):
            with mock.patch.object(rewrite.time, "time",
                                   side_effect=[i * 10.0 for i in range(100)]):
                with mock.patch.object(rewrite.urllib.request, "urlopen", up_then_gone):
                    rewrite.generate("p", model="gemma4:12b")
                    with self.assertRaises(RuntimeError) as ctx:
                        rewrite.generate("p", model="gemma4:12b")
        self.assertIn("vanished mid-run", str(ctx.exception))
        self.assertIn("writing-skills#173", str(ctx.exception))

    def test_cohere_path_untouched(self):
        os.environ["OLLAMA_WAIT_SERVER"] = "60"
        importlib.reload(rewrite)
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            payload = b'{"message":{"content":[{"type":"text","text":"c."}]}}'
            with mock.patch.object(rewrite.urllib.request, "urlopen",
                                   lambda req, timeout=None: _ok(payload)):
                self.assertEqual(
                    rewrite.generate("p", model="cohere:command-a-03-2025"), "c.")


if __name__ == "__main__":
    unittest.main()
