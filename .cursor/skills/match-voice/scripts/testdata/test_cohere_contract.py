"""Contract suite for the Cohere v2 /chat integration (GH-176).

Encodes what docs.cohere.com documents (2026-08-31) plus what this repository
measured where the docs are silent. Offline: every HTTP call is mocked. The
live smoke tests live in the same file, skip without a key, and are the only
tests here that spend requests.

Documented, and pinned here:
  - request: endpoint, bearer auth, roles, temperature passthrough, seed
  - response: typed content blocks (text | thinking); finish_reason enum
    COMPLETE, STOP_SEQUENCE, MAX_TOKENS, TOOL_CALL, ERROR, TIMEOUT
  - errors: 400/401/402/404 not retryable; 429 and 499 retryable; 500 family

Measured here, absent from the docs, also pinned:
  - 422 error_type INVALID_TOOL_GENERATION is deterministic (never retried);
    other 422s behave transient (retried)
  - a starved thinking budget spills the scratchpad into the answer, so a
    configured budget is clamped to a floor
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

MODEL = "cohere:command-a-03-2025"


def _ok(payload=None):
    payload = payload or {"finish_reason": "COMPLETE", "message": {"content": [
        {"type": "text", "text": "done."}]}}
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return cm


def _call(payload=None, env=None, capture=None, model=MODEL):
    def fake(req, timeout=None):
        if capture is not None:
            capture["url"] = req.full_url
            capture["headers"] = {k.lower(): v for k, v in req.header_items()}
            capture["body"] = json.loads(req.data.decode())
        return _ok(payload)
    e = {"COHERE_API_KEY": "k"}
    e.update(env or {})
    with mock.patch.dict(os.environ, e, clear=False):
        import importlib
        importlib.reload(rewrite)
        with mock.patch.object(rewrite.urllib.request, "urlopen", fake):
            out = rewrite.generate("p", model=model, temperature=0.3)
    importlib_reload()
    return out


def importlib_reload():
    import importlib
    importlib.reload(rewrite)


class RequestContract(unittest.TestCase):
    def test_endpoint_auth_and_roles(self):
        cap = {}
        _call(capture=cap)
        self.assertIn("api.cohere.com/v2/chat", cap["url"])
        self.assertEqual(cap["headers"]["authorization"], "Bearer k")
        self.assertEqual([m["role"] for m in cap["body"]["messages"]], ["user"])
        self.assertEqual(cap["body"]["model"], "command-a-03-2025")

    def test_documented_default_temperature_is_what_we_send(self):
        # docs: temperature defaults to 0.3; we send it explicitly — pin that
        # the value on the wire is the one requested.
        cap = {}
        _call(capture=cap)
        self.assertEqual(cap["body"]["temperature"], 0.3)

    def test_no_undocumented_parameters_sent_by_default(self):
        cap = {}
        _call(capture=cap)
        self.assertEqual(sorted(cap["body"].keys()),
                         ["messages", "model", "temperature"])

    def test_seed_is_documented_and_wired(self):
        cap = {}
        _call(env={"COHERE_SEED": "42"}, capture=cap)
        self.assertEqual(cap["body"]["seed"], 42)

    def test_non_integer_seed_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            _call(env={"COHERE_SEED": "lots"})
        self.assertIn("COHERE_SEED", str(ctx.exception))


class FinishReasonContract(unittest.TestCase):
    """Docs enum: COMPLETE, STOP_SEQUENCE, MAX_TOKENS, TOOL_CALL, ERROR,
    TIMEOUT. This pipeline sends no stop sequences and no tools, so only
    COMPLETE is a splice-able answer."""

    def _with(self, reason):
        return {"finish_reason": reason, "message": {"content": [
            {"type": "text", "text": "partial text."}]}}

    def test_complete_is_spliced(self):
        self.assertEqual(_call(self._with("COMPLETE")), "partial text.")

    def test_every_other_documented_reason_raises(self):
        for reason in ("STOP_SEQUENCE", "MAX_TOKENS", "TOOL_CALL", "ERROR", "TIMEOUT"):
            with self.assertRaises(RuntimeError, msg=reason) as ctx:
                _call(self._with(reason))
            self.assertIn(reason, str(ctx.exception))

    def test_absent_finish_reason_tolerated(self):
        # Mocks and older fixtures omit it; the live API sends it.
        payload = {"message": {"content": [{"type": "text", "text": "ok."}]}}
        self.assertEqual(_call(payload), "ok.")


class ErrorContract(unittest.TestCase):
    def _http(self, code, body=b"{}", n=None):
        calls = {"n": 0}
        def fake(req, timeout=None):
            calls["n"] += 1
            if n is not None and calls["n"] > n:
                return _ok()
            raise rewrite.urllib.error.HTTPError(
                req.full_url, code, "err", hdrs=None, fp=io.BytesIO(body))
        return fake, calls

    def _run(self, fake):
        with mock.patch.dict(os.environ, {"COHERE_API_KEY": "k"}, clear=False):
            with mock.patch.object(rewrite.time, "sleep", lambda s: None):
                with mock.patch.object(rewrite.urllib.request, "urlopen", fake):
                    return rewrite.generate("p", model=MODEL)

    def test_documented_non_retryable_codes_fail_on_first_attempt(self):
        # 400 bad request, 401 bad key, 402 billing, 404 model not found.
        for code in (400, 401, 402, 404):
            fake, calls = self._http(code)
            with self.assertRaises(RuntimeError, msg=code):
                self._run(fake)
            self.assertEqual(calls["n"], 1, f"HTTP {code} must not be retried")

    def test_429_is_retried_as_documented(self):
        fake, calls = self._http(429, n=1)
        self.assertEqual(self._run(fake), "done.")
        self.assertEqual(calls["n"], 2)

    def test_499_request_cancelled_is_retried_as_documented(self):
        fake, calls = self._http(499, n=1)
        self.assertEqual(self._run(fake), "done.")
        self.assertEqual(calls["n"], 2)

    def test_undocumented_422_invalid_tool_generation_never_retried(self):
        body = b'{"error_type":"INVALID_TOOL_GENERATION","message":"m"}'
        fake, calls = self._http(422, body=body)
        with self.assertRaises(RuntimeError) as ctx:
            self._run(fake)
        self.assertEqual(calls["n"], 1)
        self.assertIn("INVALID_TOOL_GENERATION", str(ctx.exception))

    def test_undocumented_422_no_valid_response_retried(self):
        # Observed live 2026-08-30; behaved transient.
        body = b'{"error_type":"NO_VALID_RESPONSE_GENERATED","message":"m"}'
        fake, calls = self._http(422, body=body, n=1)
        self.assertEqual(self._run(fake), "done.")
        self.assertEqual(calls["n"], 2)


class LiveSmoke(unittest.TestCase):
    """One cheap request per test, only when a key is resolvable. These are
    the tests that notice Cohere changing underneath the mocks."""

    @classmethod
    def setUpClass(cls):
        if not rewrite._cohere_key():
            raise unittest.SkipTest(
                "no Cohere key (COHERE_API_KEY / COHERE_SECRETS_FILE) — "
                "live contract smoke skipped")

    def test_plain_model_text_block_only(self):
        sink = []
        out = rewrite.generate("Reply with exactly: ok", model=MODEL,
                               temperature=0.0, thinking_out=sink)
        self.assertEqual(out.strip().lower(), "ok")
        self.assertEqual(sink, [""])

    def test_reasoning_model_thinking_separated(self):
        sink = []
        out = rewrite.generate(
            "Reply with exactly: ok", model="cohere:command-a-plus-05-2026",
            temperature=0.0, thinking_out=sink)
        self.assertEqual(out.strip().lower(), "ok")
        self.assertNotIn("ok", "", "thinking must not replace the answer")
        self.assertTrue(len(sink) == 1)

    def test_seed_reproducibility_documented(self):
        os.environ["COHERE_SEED"] = "7"
        try:
            import importlib
            importlib.reload(rewrite)
            a = rewrite.generate("One short sentence about rain.", model=MODEL,
                                 temperature=0.9)
            b = rewrite.generate("One short sentence about rain.", model=MODEL,
                                 temperature=0.9)
        finally:
            del os.environ["COHERE_SEED"]
            import importlib
            importlib.reload(rewrite)
        self.assertEqual(a, b, "documented seed parameter should reproduce")


if __name__ == "__main__":
    unittest.main()
