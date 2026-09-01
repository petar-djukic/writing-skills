#!/usr/bin/env python3
"""Pin verify()'s citation check to identity, not shape (GH-159).

The behavior predates GH-159 — this pins it, because the failure it prevents
was observed live: a rewrite replaced [@park2024] with [@key], the example
from the prompt's own rule. A gate that only checked for something
citation-shaped would have passed it.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import verify  # noqa: E402


def _citation_details(result):
    return [f["detail"] for f in result["findings"] if f["check"] == "citations"]


def test_swapped_key_is_two_fatal_findings():
    r = verify.verify("Park showed the distortion [@park2024].",
                      "Park showed the distortion [@key].", None)
    det = _citation_details(r)
    assert any("'park2024' lost" in d for d in det), det
    assert any("'key' invented" in d for d in det), det
    assert not r["clean"]
    print("  swapped_key_is_two_fatal_findings: ok")


def test_identical_keys_pass():
    r = verify.verify("Shown in [@a2020] twice [@a2020].",
                      "Twice [@a2020] it was shown [@a2020].", None)
    assert not _citation_details(r), _citation_details(r)
    print("  identical_keys_pass: ok")


def test_prompt_rule_carries_no_copyable_key():
    """The prompt must not hand the model a literal it can emit in place of a
    real key. [@park2024] -> [@key] happened because rule 1 showed [@key]."""
    import rewrite
    prompt = rewrite.build_prompt("A paragraph.", "ANCHOR text.")
    assert "[@key]" not in prompt, "rule 1 shows a copyable citation literal"
    assert "citep{key}" not in prompt.replace("\\", ""), \
        "rule 1 shows a copyable latex citation literal"
    print("  prompt_rule_carries_no_copyable_key: ok")


def test_tighten_prompt_carries_no_copyable_key():
    import os, sys
    ts = os.path.normpath(os.path.join(HERE, "..", "..", "..",
                                       "tighten-style", "scripts"))
    sys.path.insert(0, ts)
    import tighten
    assert "[@key]" not in tighten.PROMPT
    assert "[3]" not in tighten.PROMPT, "numbered literal is copyable too"
    print("  tighten_prompt_carries_no_copyable_key: ok")


def test_burstiness_prompts_carry_no_copyable_key():
    import burstiness
    for name in ("BURSTINESS_SYSTEM", "CONTROL_SYSTEM"):
        text = getattr(burstiness, name)
        assert "[@key]" not in text, f"{name} shows a copyable citation literal"
    print("  burstiness_prompts_carry_no_copyable_key: ok")


def main():
    test_swapped_key_is_two_fatal_findings()
    test_identical_keys_pass()
    test_prompt_rule_carries_no_copyable_key()
    test_tighten_prompt_carries_no_copyable_key()
    test_burstiness_prompts_carry_no_copyable_key()
    print("test_citation_identity: all assertions passed")


if __name__ == "__main__":
    main()
