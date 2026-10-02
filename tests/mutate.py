"""Mutation check: compilable defects must cause real pytest test failures.

Run without arguments for the full clean baseline and mutation suite, or use --self-test
to check the harness in temporary toy projects without touching repository sources.
Collection/setup errors, missing reports, crashes and timeouts are infrastructure errors,
not mutation kills. Each subprocess gets a fresh bytecode location and every source write
is covered by restoration, including compilation and test-launch failures.
"""
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = str(ROOT / "tests")
TEST_TIMEOUT_S = 300
MUTANTS = [('src/ifcsg_precheck/check.py', 'elif m.schema != "IFC4":', 'elif False:'),
 ('src/ifcsg_precheck/check.py', 'lu.Prefix in (None, "MILLI")', 'lu.Prefix in (None, "MILLI", "CENTI")'),
 ('src/ifcsg_precheck/check.py', '        if n == 0:\n', '        if n < 0:\n'),
 ('src/ifcsg_precheck/check.py', 'elif names[s.Name] > 1:', 'elif names[s.Name] > 2:'),
 ('src/ifcsg_precheck/check.py', 'if not _of_type(m, "IfcMapConversion"):', 'if False:'),
 ('src/ifcsg_precheck/check.py', '        if c > 1:\n', '        if c > 2:\n'),
 ('src/ifcsg_precheck/check.py',
  'if uel.get_container(el, ifc_class="IfcBuildingStorey") is None:',
  'if False:'),
 ('src/ifcsg_precheck/check.py', 'if rule.get("userdefined"):', 'if False:'),
 ('src/ifcsg_precheck/check.py', 'return (predefined or "").upper() == want.upper()', 'return True'),
 ('src/ifcsg_precheck/check.py',
  'if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):',
  'if False:'),
 ('src/ifcsg_precheck/check.py', 'if allowed and str(value) not in allowed:', 'if False:'),
 ('src/ifcsg_precheck/check.py',
  '(lo is not None and value < lo) or (hi is not None and value > hi)',
  'False'),
 ('src/ifcsg_precheck/check.py', '            report.passed_pairs += 1\n', '            pass\n'),
 ('src/ifcsg_precheck/enrich.py',
  'if current is not None and (not isinstance(current, str) or current.strip()):',
  'if False:'),
 ('src/ifcsg_precheck/enrich.py', 'upright = max(cross, key=lambda i: abs(axes[i][2]))', 'upright = 0'),
 ('src/ifcsg_precheck/enrich.py', '    return EN206.get(s)\n', '    return s or None\n'),
 ('src/ifcsg_precheck/enrich.py',
  'if wanted is not None and (el.is_a(), pset, prop) not in wanted:',
  'if False:'),
 ('src/ifcsg_precheck/mapping.py',
  'if not re.match(r"^(SGPset_|Pset_|Qto_)\\w+$", pset) or not re.match(r"^\\w+$", prop):',
  'if False:'),
 ('src/ifcsg_precheck/mapping.py',
  '"userdefined": bool(sub and sub.startswith("*")),',
  '"userdefined": False,'),
 ('src/ifcsg_precheck/mapping.py', 'AGENCY = {"NPARKS": "NParks"}', 'AGENCY = {}'),
 ('src/ifcsg_precheck/mapping.py',
  'any(re.search(r"\\bto\\b|e\\.g\\.|refer|etc", x, re.I) for x in items)',
  'False'),
 ('src/ifcsg_precheck/report.py', 'html.escape(str(c))', 'str(c)'),
 ('src/ifcsg_precheck/cli.py', 'rules = [x for x in rules if x["agency"] in (a.agency, "All")]', 'pass'),
 ('src/ifcsg_precheck/check.py', 'source = uel.get_type(el)', 'source = None'),
 ('src/ifcsg_precheck/check.py',
  'getattr(source, "PredefinedType", None) in (None, "NOTDEFINED")',
  'getattr(source, "PredefinedType", None) is None'),
 ('src/ifcsg_precheck/check.py',
  'return predefined == "USERDEFINED" and (label or "").upper() == want.upper()',
  'return (label or "").upper() == want.upper()'),
 ('src/ifcsg_precheck/check.py',
  'if uel.get_container(el, ifc_class="IfcBuildingStorey") is None:',
  'if uel.get_container(el) is None and uel.get_aggregate(el) is None:'),
 ('src/ifcsg_precheck/check.py',
  'isinstance(value, bool) or not isinstance(value, (int, float))',
  'not isinstance(value, (int, float))'),
 ('src/ifcsg_precheck/check.py',
  'if kind == "number" and isinstance(value, float) and not math.isfinite(value):',
  'if False:'),
 ('src/ifcsg_precheck/enrich.py',
  'owned = uel.get_psets(el, should_inherit=False)',
  'owned = uel.get_psets(el)'),
 ('src/ifcsg_precheck/enrich.py', 'if uel.get_elements_by_pset(p) != {el}:', 'if False:'),
 ('src/ifcsg_precheck/enrich.py',
  'if current is not None and (not isinstance(current, str) or current.strip()):',
  'if current:'),
 ('src/ifcsg_precheck/enrich.py',
  'if isinstance(load_bearing, bool) and own == "SGPset_Slab":',
  'if "LoadBearing" in common and own == "SGPset_Slab":'),
 ('src/ifcsg_precheck/check.py', 'agency, origin)', 'agency)'),
 ('src/ifcsg_precheck/report.py', '["IFC class", "Gap", "Findings"]', '["IFC class", "Gap", "Elements"]'),
 ('src/ifcsg_precheck/report.py',
  '(x.rule, x.severity, x.message, x.guid, x.ifc_class, x.name)',
  '(x.rule, x.severity, x.message, "", x.ifc_class, x.name)'),
 ('src/ifcsg_precheck/report.py',
  'for x in f if x.origin == "mapping")',
  'for x in f if x.rule.startswith("CX"))'),
 ('scripts/evaluate.py',
  'if f.origin == "model"',
  'if not f.rule.startswith("CX")'),
 ('src/ifcsg_precheck/report.py',
  'Counter((x.agency or "Unspecified mapping agency") if x.origin == "mapping" else "model" for x in f)',
  'Counter(x.agency or "model" for x in f)'),
 ('src/ifcsg_precheck/enrich.py',
  'if isinstance(candidate, str) and candidate.strip():',
  'if isinstance(candidate, str) and candidate:')]

class HarnessError(RuntimeError):
    """The run supplies no valid evidence about a mutant."""


def replacement(root, mutant):
    fname, old, new = mutant
    path = root / fname
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    # LF-authored anchors also work in Windows CRLF checkouts; restoration still uses raw bytes.
    newline = "\r\n" if "\r\n" in text else "\n"
    old = old.replace("\r\n", "\n").replace("\n", newline)
    new = new.replace("\r\n", "\n").replace("\n", newline)
    if text.count(old) != 1 or old == new:
        raise HarnessError(f"mutation target must occur once and change: {fname}: {old[:70]}")
    return path, raw, text.replace(old, new).encode("utf-8")


def compile_source(raw, path):
    # Compile without importing the module or creating a .pyc next to product sources.
    try:
        compile(raw, str(path), "exec")
    except (SyntaxError, ValueError) as exc:
        raise HarnessError(f"mutant does not compile; not a kill: {path}: {exc}") from exc


def run_tests(root, tests, output_dir, *, fail_fast=False, timeout=TEST_TIMEOUT_S):
    output_dir.mkdir(parents=True)
    report = output_dir / "pytest.xml"
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)  # always run the declared suite, not a shell's -k filter
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root / "src"), str(root), env.get("PYTHONPATH")]))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = str(output_dir / "pycache")
    cmd = [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
           f"--junitxml={report}", str(tests)]
    if fail_fast:
        cmd.append("-x")
    try:
        result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"pytest timed out after {timeout}s; not a kill") from exc
    except OSError as exc:
        raise HarnessError(f"pytest could not start; not a kill: {exc}") from exc
    output = result.stdout + result.stderr
    (output_dir / "pytest.log").write_text(output, encoding="utf-8")
    try:
        document = ET.parse(report)
    except (OSError, ET.ParseError) as exc:
        raise HarnessError(f"pytest exited {result.returncode} without a valid report; not a kill:\n"
                           + output[-3000:]) from exc
    cases = document.findall(".//testcase")
    errors = document.findall(".//error")
    skipped = sum(case.find("skipped") is not None for case in cases)
    failures = []
    for case in cases:
        failure = case.find("failure")
        if failure is not None:
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            message = " ".join((failure.get("message") or failure.text or "test failure").split())
            failures.append(f"{name}: {message[:180]}")
    if errors or not cases or len(cases) == skipped or result.returncode not in (0, 1):
        raise HarnessError(f"pytest exited {result.returncode}, {len(errors)} errors, "
                           f"{len(cases)} cases/{skipped} skipped; not a kill:\n" + output[-3000:])
    if (result.returncode == 1) != bool(failures):
        raise HarnessError(f"pytest exit/report disagree; not a kill:\n" + output[-3000:])
    return {"killed": bool(failures), "tests": len(cases), "skipped": skipped, "failures": failures}


def run_mutant(root, tests, mutant, output_dir, *, timeout=TEST_TIMEOUT_S):
    path, raw, changed = replacement(root, mutant)
    try:
        path.write_bytes(changed)
        compile_source(path.read_bytes(), path)
        return run_tests(root, tests, output_dir, fail_fast=True, timeout=timeout)
    finally:
        path.write_bytes(raw)
        if path.read_bytes() != raw:
            raise HarnessError(f"source restoration failed: {path}")


def main():
    # Check every anchor and the syntax of every proposed mutant before any source write.
    originals = {}
    for mutant in MUTANTS:
        path, raw, changed = replacement(ROOT, mutant)
        originals[path] = raw
        compile_source(changed, path)
    started = time.monotonic()
    escaped = 0
    try:
        with tempfile.TemporaryDirectory(prefix="ifcsg-mutation-") as scratch:
            output_dir = Path(scratch)
            base = run_tests(ROOT, TESTS, output_dir / "baseline")
            if base["killed"]:
                raise HarnessError("unmodified tests fail; fix the baseline first:\n" + "\n".join(base["failures"]))
            print(f"baseline: {base['tests']} cases, {base['skipped']} skipped, "
                  f"{time.monotonic() - started:.1f}s", flush=True)
            for i, mutant in enumerate(MUTANTS, 1):
                result = run_mutant(ROOT, TESTS, mutant, output_dir / f"mutant-{i:03d}")
                escaped += not result["killed"]
                evidence = result["failures"][0] if result["killed"] else "no test failed"
                anchor = " ".join(mutant[1].split())[:70]
                print(f"{'killed ' if result['killed'] else 'ESCAPED'} [{i}/{len(MUTANTS)}] "
                      f"{mutant[0]}: {anchor} -- {evidence}", flush=True)
                if not result["killed"]:
                    raise HarnessError(f"mutant {i}/{len(MUTANTS)} escaped; stopped for review after restoring source")
    finally:
        unexpected = [path for path, raw in originals.items() if not path.exists() or path.read_bytes() != raw]
        for path in unexpected:
            path.write_bytes(originals[path])
        if unexpected:
            raise HarnessError("unexpected source changes restored: " + ", ".join(map(str, unexpected)))
    print(f"{len(MUTANTS) - escaped}/{len(MUTANTS)} mutants killed "
          f"({time.monotonic() - started:.1f}s); all source bytes restored", flush=True)
    return 1 if escaped else 0


def self_test():
    """Exercise failure classification/restoration without importing product code."""
    import py_compile
    import unittest
    from unittest.mock import patch

    class HarnessTests(unittest.TestCase):
        def setUp(self):
            self.scratch = tempfile.TemporaryDirectory(prefix="ifcsg-harness-test-")
            self.addCleanup(self.scratch.cleanup)
            self.root = Path(self.scratch.name)
            self.source = self.root / "subject.py"
            self.original = b"VALUE = 1\n"
            self.source.write_bytes(self.original)
            self.tests = self.root / "test_subject.py"
            self.tests.write_text("from subject import VALUE\ndef test_value():\n    assert VALUE == 1\n")

        def mutate(self, new, **kwargs):
            try:
                return run_mutant(self.root, self.tests, ("subject.py", "VALUE = 1", new),
                                  self.root / "run", **kwargs)
            finally:
                self.assertEqual(self.source.read_bytes(), self.original)

        def test_assertion_failure_ignores_stale_bytecode(self):
            py_compile.compile(str(self.source), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            result = self.mutate("VALUE = 2")
            self.assertTrue(result["killed"])
            self.assertIn("test_value", result["failures"][0])

        def test_multiline_anchor_preserves_windows_line_endings(self):
            raw = b"VALUE = 1\r\nUNUSED = 0\r\n"
            self.source.write_bytes(raw)
            path, original, changed = replacement(self.root,
                ("subject.py", "VALUE = 1\nUNUSED = 0", "VALUE = 2\nUNUSED = 0"))
            self.assertEqual(original, raw)
            self.assertEqual(changed, b"VALUE = 2\r\nUNUSED = 0\r\n")
            self.assertEqual(path.read_bytes(), raw)

        def test_survivor_is_not_a_kill(self):
            self.assertFalse(self.mutate("VALUE = 1 # unchanged behavior")["killed"])

        def test_compile_failure_restores_source(self):
            with self.assertRaisesRegex(HarnessError, "does not compile"):
                self.mutate("VALUE = (")

        def test_collection_failure_is_not_a_kill(self):
            with self.assertRaisesRegex(HarnessError, "not a kill"):
                self.mutate("raise ImportError('synthetic collection failure')")

        def test_setup_failure_is_not_a_kill(self):
            self.tests.write_text("import pytest\n@pytest.fixture(autouse=True)\n"
                                  "def broken():\n    raise RuntimeError('synthetic fixture failure')\n"
                                  "def test_value():\n    assert False\n")
            with self.assertRaisesRegex(HarnessError, "not a kill"):
                self.mutate("VALUE = 2")

        def test_timeout_is_not_a_kill_and_restores_source(self):
            with self.assertRaisesRegex(HarnessError, "timed out"):
                self.mutate("import time; time.sleep(10); VALUE = 1", timeout=1)

        def test_launch_failure_is_not_a_kill_and_restores_source(self):
            with patch.object(subprocess, "run", side_effect=OSError("synthetic launch failure")):
                with self.assertRaisesRegex(HarnessError, "could not start; not a kill"):
                    self.mutate("VALUE = 2")

        def test_crash_without_report_is_not_a_kill(self):
            with self.assertRaisesRegex(HarnessError, "without a valid report; not a kill"):
                self.mutate("import os; os._exit(3)")

        def test_all_skipped_is_not_a_kill(self):
            self.tests.write_text("import pytest\n@pytest.mark.skip(reason='synthetic skip')\n"
                                  "def test_value():\n    assert False\n")
            with self.assertRaisesRegex(HarnessError, "not a kill"):
                self.mutate("VALUE = 2")

        def test_exit_and_failure_report_must_agree(self):
            def fake_run(*args, **kwargs):
                (self.root / "run" / "pytest.xml").write_text(
                    '<testsuites><testsuite><testcase name="fake">'
                    '<failure message="synthetic"/></testcase></testsuite></testsuites>')
                return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

            with patch.object(subprocess, "run", side_effect=fake_run):
                with self.assertRaisesRegex(HarnessError, "exit/report disagree; not a kill"):
                    self.mutate("VALUE = 2")

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HarnessTests))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    if sys.argv[1:]:
        sys.exit("usage: python tests/mutate.py [--self-test]")
    try:
        sys.exit(main())
    except HarnessError as exc:
        sys.exit(f"MUTATION ERROR: {exc}")
