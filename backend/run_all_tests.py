"""Master Test Runner for Fraud & Risk Detection Platform.

Orchestrates the entire software testing pyramid:
1. Component-Level (Unit) Tests
2. Whitebox Internal Code Path Tests
3. Blackbox REST API & RBAC Tests
4. Regression Suites (Smoke Test & AI Layer Verification)

Outputs a consolidated quality and verification audit summary table.
"""
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent


def run_command_suite(name: str, cmd: list[str]) -> dict:
    print(f"\n{'='*70}")
    print(f"RUNNING SUITE: {name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*70}\n")
    start = time.time()
    res = subprocess.run(cmd, cwd=BACKEND_DIR, capture_output=True, text=True)
    duration = time.time() - start

    # Print output in real-time
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)

    passed = res.returncode == 0
    return {
        "name": name,
        "passed": passed,
        "duration": duration,
        "returncode": res.returncode,
    }


def main():
    print("\n" + "#" * 70)
    print("# CODECELIX FRAUD & RISK DETECTION PLATFORM — MASTER TEST RUNNER")
    print("#" * 70)

    suites = [
        ("1. Component-Level (Unit) Suite", [sys.executable, "-m", "pytest", "tests/test_components_unit.py", "-v"]),
        ("2. Whitebox (Internal Logic) Suite", [sys.executable, "-m", "pytest", "tests/test_whitebox_paths.py", "-v"]),
        ("3. Blackbox (REST API & RBAC) Suite", [sys.executable, "-m", "pytest", "tests/test_blackbox_api.py", "-v"]),
        ("4. Regression Suite (CRUD & Auth Smoke Test)", [sys.executable, "smoke_test.py"]),
        ("5. Regression Suite (AI Layer E2E Test)", [sys.executable, "test_ai_layer.py"]),
    ]

    results = []
    for name, cmd in suites:
        res = run_command_suite(name, cmd)
        results.append(res)

    print("\n" + "=" * 75)
    print("                      CONSOLIDATED TEST AUDIT REPORT")
    print("=" * 75)
    print(f"{'Test Suite':<45} | {'Duration':<10} | {'Status'}")
    print("-" * 75)

    all_passed = True
    total_time = 0.0

    for r in results:
        status_str = "[PASS] PASSED" if r["passed"] else "[FAIL] FAILED"
        dur_str = f"{r['duration']:.2f}s"
        total_time += r["duration"]
        if not r["passed"]:
            all_passed = False
        print(f"{r['name']:<45} | {dur_str:<10} | {status_str}")

    print("-" * 75)
    print(f"{'Total Execution Time':<45} | {total_time:.2f}s")
    print("=" * 75)

    if all_passed:
        print("\n[SUCCESS] ALL TEST SUITES PASSED WITH 100% SUCCESS RATE!\n")
        sys.exit(0)
    else:
        print("\n[FAILURE] ONE OR MORE TEST SUITES FAILED.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
