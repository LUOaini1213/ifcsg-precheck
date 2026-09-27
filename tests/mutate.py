"""Mutation check: each deliberate bug below must make at least one unit test fail."""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "ifcsg_precheck"
TESTS = str(SRC.parents[1] / "tests" / "test_precheck.py")
MUTANTS = [
    ("check.py", 'elif m.schema != "IFC4":', 'elif False:'),
    ("check.py", 'lu.Prefix in (None, "MILLI")', 'lu.Prefix in (None, "MILLI", "CENTI")'),
    ("check.py", "        if n == 0:\n", "        if n < 0:\n"),
    ("check.py", "elif names[s.Name] > 1:", "elif names[s.Name] > 2:"),
    ("check.py", "if not _of_type(m, \"IfcMapConversion\"):", "if False:"),
    ("check.py", "        if c > 1:\n", "        if c > 2:\n"),
    ("check.py", "if uel.get_container(el) is None and uel.get_aggregate(el) is None:", "if False:"),
    ("check.py", "if rule.get(\"userdefined\"):", "if False:"),
    ("check.py", "return (uel.get_predefined_type(el) or \"\").upper() == want.upper()", "return True"),
    ("check.py", "if kind == \"number\" and not isinstance(value, (int, float)):", "if False:"),
    ("check.py", "if allowed and str(value) not in allowed:", "if False:"),
    ("check.py", "(lo is not None and value < lo) or (hi is not None and value > hi)", "False"),
    ("check.py", "            report.passed_pairs += 1\n", "            pass\n"),
    ("enrich.py", "if prop in existing.get(pset, {}) and existing[pset][prop] not in (None, \"\"):", "if False:"),
    ("enrich.py", "upright = max(cross, key=lambda i: abs(axes[i][2]))", "upright = 0"),
    ("enrich.py", "    return EN206.get(s)\n", "    return s or None\n"),
    ("enrich.py", "if wanted is not None and (el.is_a(), pset, prop) not in wanted:", "if False:"),
    ("mapping.py", 'if not re.match(r"^(SGPset_|Pset_|Qto_)\w+$", pset) or not re.match(r"^\w+$", prop):', "if False:"),
    ("mapping.py", '"userdefined": bool(sub and sub.startswith("*")),', '"userdefined": False,'),
    ("mapping.py", 'AGENCY = {"NPARKS": "NParks"}', "AGENCY = {}"),
    ("mapping.py", r'any(re.search(r"\bto\b|e\.g\.|refer|etc", x, re.I) for x in items)', "False"),
    ("report.py", "html.escape(str(c))", "str(c)"),
    ("cli.py", 'rules = [x for x in rules if x["agency"] in (a.agency, "All")]', "pass"),
]

# The unmutated code must pass, otherwise every mutant would look "killed".
base = subprocess.run([sys.executable, "-m", "pytest", "-q", TESTS], capture_output=True)
assert base.returncode == 0, "tests fail on the unmutated code; fix them before running the mutation check"

escaped = 0
for fname, old, new in MUTANTS:
    f = SRC / fname
    text = f.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutation target not unique in {fname}: {old[:70]}"
    f.write_text(text.replace(old, new), encoding="utf-8")
    compiled = subprocess.run([sys.executable, "-m", "py_compile", str(f)], capture_output=True)
    assert compiled.returncode == 0, f"mutant does not compile, so it proves nothing: {old[:70]}"
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", TESTS],
                           capture_output=True, text=True)
    finally:
        f.write_text(text, encoding="utf-8")
    killed = r.returncode != 0
    escaped += not killed
    print(f"{'killed ' if killed else 'ESCAPED'}  {fname}: {old[:70]}", flush=True)
print(f"{len(MUTANTS) - escaped}/{len(MUTANTS)} mutants killed")
sys.exit(1 if escaped else 0)
