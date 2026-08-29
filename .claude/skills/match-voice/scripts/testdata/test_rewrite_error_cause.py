"""Unit tests for the rewrite-error cause classifier (GH-142)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, ".."))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import drive  # noqa: E402


class ClassifyRewriteError(unittest.TestCase):
    def test_empty_output(self):
        self.assertEqual(
            drive.classify_rewrite_error(
                "empty output (model returned nothing, or sanitized to empty)"),
            "empty/sanitized-to-empty")

    def test_api_error(self):
        self.assertEqual(
            drive.classify_rewrite_error(
                "Cohere request failed: HTTP 401 on 'command-a-03-2025'."),
            "api-error")

    def test_timeout(self):
        self.assertEqual(
            drive.classify_rewrite_error(
                "Cohere timed out after 600s on model 'command-a-03-2025'."),
            "timeout")

    def test_refused_model(self):
        self.assertEqual(
            drive.classify_rewrite_error(
                "refusing denylisted Cohere model 'command-a-plus-05-2026'."),
            "refused-model")

    def test_other_and_empty(self):
        self.assertEqual(drive.classify_rewrite_error("some unknown failure"), "other")
        self.assertEqual(drive.classify_rewrite_error(""), "other")
        self.assertEqual(drive.classify_rewrite_error(None), "other")

    def test_refusal_precedes_api(self):
        # a refusal message must not be miscounted as api-error
        self.assertEqual(
            drive.classify_rewrite_error("refusing reasoning model: HTTP-ish text"),
            "refused-model")


if __name__ == "__main__":
    unittest.main()
