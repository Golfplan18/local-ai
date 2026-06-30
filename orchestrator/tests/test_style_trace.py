"""Slice C: style_id / style_register fields in the pipeline trace metadata."""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipeline_trace  # noqa: E402


def _meta(d):
    return json.load(open(os.path.join(d, "metadata.json")))


def test_style_fields_written():
    d = pipeline_trace.start_trace(
        "_style_test_conv", raw_input="hi",
        style_id="technical", style_register="written",
    )
    if d is None:
        print("  (tracing globally disabled — skipping)")
        return
    try:
        m = _meta(d)
        assert m["style_id"] == "technical"
        assert m["style_register"] == "written"
        assert m["ambiguity_mode"] == "assume"   # untouched
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


def test_style_fields_default_none():
    d = pipeline_trace.start_trace("_style_test_conv2", raw_input="hi")
    if d is None:
        return
    try:
        m = _meta(d)
        assert m["style_id"] is None and m["style_register"] is None
    finally:
        shutil.rmtree(os.path.dirname(d), ignore_errors=True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS  " + t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL  %s -> %r" % (t.__name__, exc))
    print("\n%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
