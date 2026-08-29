"""Offline tests for the opt-in Cohere backend in rewrite.py.

No network, no key required: the HTTP call is mocked, so these assert the
request shape and the guards, not Cohere's behavior.
"""
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, ".."))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import rewrite  # noqa: E402


def _fake_response(payload):
    """A context-manager stand-in for urlopen returning JSON bytes."""
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return cm


class CohereRouting(unittest.TestCase):
    def test_prefix_detection(self):
        self.assertTrue(rewrite._is_cohere("cohere:command-a-03-2025"))
        self.assertFalse(rewrite._is_cohere("gemma4:31b-cloud"))
        self.assertFalse(rewrite._is_cohere(None))

    def test_generate_routes_to_cohere_v2_chat(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["body"] = json.loads(req.data.decode())
            return _fake_response(
                {"message": {"content": [{"type": "text", "text": "rewritten."}]}})

        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "test-key"}, clear=False):
            with mock.patch.object(rewrite.urllib.request, "urlopen", fake_urlopen):
                out = rewrite.generate(
                    "one paragraph", model="cohere:command-a-03-2025",
                    temperature=0.2, system="be terse")
        self.assertEqual(out, "rewritten.")
        self.assertIn("api.cohere.com", captured["url"])
        self.assertEqual(captured["headers"]["authorization"], "Bearer test-key")
        self.assertEqual(captured["body"]["model"], "command-a-03-2025")
        # system + user messages, in order
        roles = [m["role"] for m in captured["body"]["messages"]]
        self.assertEqual(roles, ["system", "user"])

    def test_ollama_path_untouched_for_normal_model(self):
        def fake_urlopen(req, timeout=None):
            # an Ollama-shaped request must hit /api/generate, not Cohere
            self.assertIn("/api/generate", req.full_url)
            return _fake_response({"response": "ollama out"})

        with mock.patch.object(rewrite.urllib.request, "urlopen", fake_urlopen):
            out = rewrite.generate("p", model="gemma4:12b")
        self.assertEqual(out, "ollama out")

    def test_reasoning_variant_refused(self):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                rewrite.generate("p", model="cohere:command-a-reasoning-08-2025")
        self.assertIn("reasoning", str(ctx.exception).lower())

    def test_missing_key_raises_not_falls_back(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("COHERE_API_KEY", "COHERE_SECRETS_FILE")}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                rewrite.generate("p", model="cohere:command-a-03-2025")
        self.assertIn("Cohere API key", str(ctx.exception))

    def test_key_from_secrets_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"cohere": "file-key"}, fh)
            path = fh.name
        try:
            env = {k: v for k, v in os.environ.items() if k != "COHERE_API_KEY"}
            env["COHERE_SECRETS_FILE"] = path
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(rewrite._cohere_key(), "file-key")
        finally:
            os.unlink(path)

    def test_check_server_cohere_key_present(self):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            ok, msg = rewrite.check_server("http://unused", "cohere:command-a-03-2025")
        self.assertTrue(ok)

    def test_check_server_cohere_reasoning_refused(self):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            ok, msg = rewrite.check_server(
                "http://unused", "cohere:command-a-reasoning-08-2025")
        self.assertFalse(ok)


class OllamaRetry(unittest.TestCase):
    def test_retry_on_dropped_connection(self):
        # RemoteDisconnected is a ConnectionError subclass; a dropped Ollama
        # connection is transient and must be retried (GH-147).
        calls = {"n": 0}

        def flaky(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionResetError("Remote end closed connection")
            cm = mock.MagicMock()
            cm.__enter__.return_value.read.return_value = b'{"response":"ok"}'
            return cm

        with mock.patch.object(rewrite.time, "sleep", lambda s: None):
            with mock.patch.object(rewrite.urllib.request, "urlopen", flaky):
                out = rewrite.generate("p", model="gemma4:12b")
        self.assertEqual(out, "ok")
        self.assertEqual(calls["n"], 2)


class DefaultModel(unittest.TestCase):
    def test_default_is_cohere_command_a_03(self):
        # GH-145 flipped the match-voice default. MATCH_VOICE_MODEL still wins,
        # but the fallback is the bake-off winner.
        env = {k: v for k, v in os.environ.items() if k != "MATCH_VOICE_MODEL"}
        with mock.patch.dict(os.environ, env, clear=True):
            import importlib
            importlib.reload(rewrite)
            self.assertEqual(rewrite.DEFAULT_MODEL, "cohere:command-a-03-2025")
            self.assertTrue(rewrite._is_cohere(rewrite.DEFAULT_MODEL))
        importlib.reload(rewrite)  # restore ambient env


class CohereHardening(unittest.TestCase):
    def test_denylisted_plus_refused_in_generate(self):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                rewrite.generate("p", model="cohere:command-a-plus-05-2026")
        self.assertIn("denylist", str(ctx.exception).lower())

    def test_denylisted_plus_refused_in_check_server(self):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            ok, msg = rewrite.check_server(
                "http://unused", "cohere:command-a-plus-05-2026")
        self.assertFalse(ok)

    def test_command_a_03_still_allowed(self):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            ok, msg = rewrite.check_server("http://unused", "cohere:command-a-03-2025")
        self.assertTrue(ok)

    def test_sanitizer_strips_instruction_echo_and_reasoning(self):
        raw = (
            "The system checks input before it runs.\n"
            "is the rewritten paragraph. No preamble, no explanation.\n"
            "Now, we need to ensure we preserve the term \"four\".\n"
            "Let me verify the citation [1] is intact.\n"
            "It rejects a bad action at the boundary.")
        cleaned = rewrite._sanitize_cohere_output(raw)
        self.assertIn("The system checks input", cleaned)
        self.assertIn("rejects a bad action", cleaned)
        self.assertNotIn("rewritten paragraph", cleaned)
        self.assertNotIn("we need to", cleaned)
        self.assertNotIn("Let me", cleaned)

    def test_sanitizer_keeps_clean_output_untouched(self):
        clean = "The engine reads the table.\nIt dispatches tools by name."
        self.assertEqual(rewrite._sanitize_cohere_output(clean), clean)

    def test_generate_sanitizes_cohere_response(self):
        payload = {"message": {"content": [{"type": "text", "text":
            "Now, we should rewrite this.\nThe validator runs first."}]}}
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.urllib.request, "urlopen",
                                   lambda req, timeout=None: _fake_response(payload)):
                out = rewrite.generate("p", model="cohere:command-a-03-2025")
        self.assertEqual(out, "The validator runs first.")

    def test_retry_on_429_then_success(self):
        calls = {"n": 0}

        def flaky_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise rewrite.urllib.error.HTTPError(
                    req.full_url, 429, "rate", hdrs=None, fp=None)
            return _fake_response(
                {"message": {"content": [{"type": "text", "text": "done."}]}})

        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.time, "sleep", lambda s: None):
                with mock.patch.object(rewrite.urllib.request, "urlopen", flaky_urlopen):
                    out = rewrite.generate("p", model="cohere:command-a-03-2025")
        self.assertEqual(out, "done.")
        self.assertEqual(calls["n"], 2)

    def test_retry_on_422_then_success(self):
        # 422 is intermittent on the long match-voice prompt (GH-142); retrying
        # the identical request recovers it.
        calls = {"n": 0}

        def flaky_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise rewrite.urllib.error.HTTPError(
                    req.full_url, 422, "unprocessable", hdrs=None, fp=None)
            return _fake_response(
                {"message": {"content": [{"type": "text", "text": "ok."}]}})

        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.time, "sleep", lambda s: None):
                with mock.patch.object(rewrite.urllib.request, "urlopen", flaky_urlopen):
                    out = rewrite.generate("p", model="cohere:command-a-03-2025")
        self.assertEqual(out, "ok.")
        self.assertEqual(calls["n"], 2)

    def test_no_retry_on_400(self):
        def bad_urlopen(req, timeout=None):
            raise rewrite.urllib.error.HTTPError(
                req.full_url, 400, "bad", hdrs=None, fp=None)

        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.urllib.request, "urlopen", bad_urlopen):
                with self.assertRaises(RuntimeError) as ctx:
                    rewrite.generate("p", model="cohere:command-a-03-2025")
        self.assertIn("400", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
