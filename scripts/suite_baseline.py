#!/usr/bin/env python3
"""Compare a suite run against a recorded baseline of known failures.

The suite is deterministic — three consecutive runs on the same tree produce a
byte-identical failure set — but it is heavily order-dependent: files pass alone
and fail in company, because tests share process state. That combination makes
raw pass/fail counts useless for judging a change. A refactor can shuffle which
order-dependent failures surface and look catastrophic while breaking nothing,
which is exactly what happened to the server/app.py rename attempt on
2026-08-01: 63 failures became 201, yet every "new" failure passed in isolation.

So compare *sets*, not counts. Record the exact failing node ids once, then a
change is judged only on what entered or left that set.

    scripts/suite_baseline.py --record    # write tests/suite-baseline.txt
    scripts/suite_baseline.py --check     # diff against it; exit 1 on regression

--check exits non-zero only for regressions. Fixed tests are reported and are
not a failure, but they do mean the baseline should be re-recorded so it keeps
shrinking rather than silently permitting a re-break.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO / "orchestrator" / "tests" / "suite-baseline.txt"
TESTS = "orchestrator/tests/"


def run_suite() -> set[str]:
    """Run the suite and return the set of failing/erroring node ids.

    --continue-on-collection-errors is required: import-time failures otherwise
    abort collection and hide every result behind them.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-p", "no:warnings", "-q",
         "--continue-on-collection-errors"],
        cwd=REPO, capture_output=True, text=True,
    )
    found = set()
    for line in proc.stdout.splitlines():
        if line.startswith(("FAILED ", "ERROR ")):
            # "FAILED path::Class::test - AssertionError: ..." — keep the node
            # id only, so a changed assertion message is not a false regression.
            found.add(line.split(" - ", 1)[0].strip())
    if not found and "passed" not in proc.stdout:
        sys.stderr.write(proc.stdout[-3000:])
        raise SystemExit("suite produced no parseable result")
    return found


def read_baseline() -> set[str]:
    if not BASELINE.exists():
        raise SystemExit(f"no baseline at {BASELINE}; run --record first")
    return {
        line.strip() for line in BASELINE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", action="store_true",
                       help="record the current failure set as the baseline")
    group.add_argument("--check", action="store_true",
                       help="compare against the baseline; exit 1 on regression")
    args = ap.parse_args()

    current = run_suite()

    if args.record:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            "# Known-failing suite entries. Regenerate with:\n"
            "#   scripts/suite_baseline.py --record\n"
            "# A change is judged on what enters or leaves this set, never on\n"
            "# the raw count — the suite is order-dependent and a refactor can\n"
            "# shuffle which failures surface without breaking anything.\n"
            + "".join(f"{n}\n" for n in sorted(current))
        )
        print(f"recorded {len(current)} known failures -> "
              f"{BASELINE.relative_to(REPO)}")
        return 0

    baseline = read_baseline()
    regressions = sorted(current - baseline)
    fixed = sorted(baseline - current)

    print(f"baseline {len(baseline)}  current {len(current)}")
    for node in fixed:
        print(f"  FIXED       {node}")
    for node in regressions:
        print(f"  REGRESSION  {node}")

    if regressions:
        print(f"\n{len(regressions)} regression(s).")
        return 1
    if fixed:
        print(f"\nNo regressions. {len(fixed)} fixed — re-record the baseline.")
    else:
        print("\nNo change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
