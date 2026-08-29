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


class CohereContentBlocks(unittest.TestCase):
    """Cohere v2 returns typed content blocks; only `text` is prose (GH-154).

    Shapes here are copied from a live probe on 2026-08-29: command-a-plus-05-2026
    answered with a 6541-character thinking block beside a 195-character text
    block.
    """

    def test_split_separates_thinking_from_text(self):
        parts = [{"type": "thinking", "thinking": "We need to preserve [2]."},
                 {"type": "text", "text": "The scheduler runs once per frame."}]
        text, thinking, other = rewrite._cohere_blocks(parts)
        self.assertEqual(text, "The scheduler runs once per frame.")
        self.assertEqual(thinking, "We need to preserve [2].")
        self.assertEqual(other, [])

    def test_thinking_never_reaches_the_returned_prose(self):
        payload = {"message": {"content": [
            {"type": "thinking", "thinking": "Let me check the citation first."},
            {"type": "text", "text": "The validator runs first."}]}}
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.urllib.request, "urlopen",
                                   lambda req, timeout=None: _fake_response(payload)):
                out = rewrite.generate("p", model="cohere:command-a-03-2025")
        self.assertEqual(out, "The validator runs first.")
        self.assertNotIn("Let me", out)

    def test_thinking_out_receives_the_scratchpad(self):
        payload = {"message": {"content": [
            {"type": "thinking", "thinking": "Deliberating."},
            {"type": "text", "text": "The engine reads the table."}]}}
        sink = []
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.urllib.request, "urlopen",
                                   lambda req, timeout=None: _fake_response(payload)):
                out = rewrite.generate("p", model="cohere:command-a-03-2025",
                                       thinking_out=sink)
        self.assertEqual(out, "The engine reads the table.")
        self.assertEqual(sink, ["Deliberating."])

    def test_unknown_block_type_is_ignored_not_fatal(self):
        # Forward compatibility: a block kind added after this code was written
        # must not join the prose and must not kill the call.
        parts = [{"type": "tool_call", "tool_call": {"name": "search"}},
                 {"type": "text", "text": "The queue drains in order."}]
        text, thinking, other = rewrite._cohere_blocks(parts)
        self.assertEqual(text, "The queue drains in order.")
        self.assertEqual(thinking, "")
        self.assertEqual(other, ["tool_call"])

    def test_malformed_block_counted_not_raised(self):
        text, thinking, other = rewrite._cohere_blocks(["not a dict", None])
        self.assertEqual(text, "")
        self.assertEqual(other, ["str", "NoneType"])

    def test_text_key_on_a_thinking_block_is_not_read(self):
        # The old parser read `text` off every block regardless of type. If a
        # future thinking block ever carries one, it stays out of the prose.
        text, _, _ = rewrite._cohere_blocks(
            [{"type": "thinking", "thinking": "scratch", "text": "leaked"}])
        self.assertEqual(text, "")


class CohereEmptyOutput(unittest.TestCase):
    """Empty output is a failed rewrite; the message says which kind.

    Every message keeps the phrase "empty output" so drive.py's
    classify_rewrite_error() still buckets it as empty/sanitized-to-empty.
    """

    def _raise_on(self, payload):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.urllib.request, "urlopen",
                                   lambda req, timeout=None: _fake_response(payload)):
                with self.assertRaises(RuntimeError) as ctx:
                    rewrite.generate("p", model="cohere:command-a-03-2025")
        return str(ctx.exception)

    def test_reasoned_but_answered_nothing(self):
        msg = self._raise_on({"message": {"content": [
            {"type": "thinking", "thinking": "x" * 4000}]}})
        self.assertIn("empty output", msg)
        self.assertIn("4000 characters of reasoning", msg)
        self.assertIn("token_budget", msg)

    def test_meta_only_answer_sanitized_to_nothing(self):
        msg = self._raise_on({"message": {"content": [
            {"type": "text", "text": "Let me rewrite this.\nWe need to keep [2]."}]}})
        self.assertIn("empty output", msg)
        self.assertIn("meta-commentary", msg)

    def test_no_text_blocks_at_all(self):
        msg = self._raise_on({"message": {"content": []}})
        self.assertIn("empty output", msg)
        self.assertIn("no text blocks", msg)

    def test_unread_block_types_named_in_the_error(self):
        msg = self._raise_on({"message": {"content": [
            {"type": "tool_call", "tool_call": {}}]}})
        self.assertIn("unread block types: tool_call", msg)

    def test_messages_stay_in_the_existing_error_bucket(self):
        sys.path.insert(0, os.path.normpath(os.path.join(SCRIPTS)))
        import drive as mv_drive
        for payload in (
                {"message": {"content": [{"type": "thinking", "thinking": "z" * 50}]}},
                {"message": {"content": [{"type": "text", "text": "Let me try."}]}},
                {"message": {"content": []}}):
            self.assertEqual(
                mv_drive.classify_rewrite_error(self._raise_on(payload)),
                "empty/sanitized-to-empty")


if __name__ == "__main__":
    unittest.main()
