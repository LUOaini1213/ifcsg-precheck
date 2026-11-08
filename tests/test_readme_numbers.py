"""Every result number in the README must trace to a committed artifact."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CURRENT = ROOT / "reports/review-20261012-units"
HISTORY = {"Original": ROOT / "reports/summary.json", "Recheck": ROOT / "reports/review-20261003/summary.json"}
ROW_KEYS = {"facade-bim": "facade", "bridge-bim": "bridge", "sample_block.ifc": "sample"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pct(rate):
    return "0%" if rate == 0 else f"{100 * rate:.1f}%"


def passed(s, key):
    return round(s[key] * s["element_rule_pairs"])


def ratio(s, key):
    return f"{passed(s, key):,} / {s['element_rule_pairs']:,} ({pct(s[key])})"


def section(start, end):
    body = README.split(start, 1)[1]
    return body.split(end, 1)[0]


def table_rows(text):
    rows = [line for line in text.splitlines() if line.startswith("|") and not line.startswith("|---")]
    return [[c.strip() for c in line.strip("|").split("|")] for line in rows[1:]]


def test_current_results_table_matches_summary():
    summary = load(CURRENT / "summary.json")
    rows = table_rows(section("## Results", "### History"))
    assert len(rows) == 3
    seen = set()
    for cells in rows:
        key = next(v for k, v in ROW_KEYS.items() if k in cells[0])
        seen.add(key)
        s = summary[key]
        expected = [f"{s['elements']:,}", f"{s['element_rule_pairs']:,}", ratio(s, "pass_before"),
                    f"{s['auto_filled']:,}", ratio(s, "pass_after")]
        assert cells[1:] == expected, (key, cells)
    assert seen == {"facade", "bridge", "sample"}


def test_current_table_names_the_provenance_models():
    provenance = load(CURRENT / "provenance.json")
    text = (CURRENT / "README.md").read_text(encoding="utf-8")
    for commit in ("3c88e925a67d443ef879dce15b9e1ee837354375", "b6456b344b09a92620cc5d4a4cfb2a3be963b147"):
        assert commit in text and commit in README
    assert provenance["rule_count"] == load(CURRENT / "unit_catalog.json")["generated_rule_count"]


def test_history_table_matches_summaries():
    rows = table_rows(section("### History", "## Use"))
    assert [r[0].split("]")[0].lstrip("[") for r in rows] == list(HISTORY)
    for cells in rows:
        s = load(HISTORY[cells[0].split("]")[0].lstrip("[")])
        f, b, x = s["facade"], s["bridge"], s["sample"]
        assert cells[2] == f"{f['elements']:,}, {f['element_rule_pairs']:,}, {f['auto_filled']:,}, {pct(f['pass_after'])}"
        assert cells[3] == f"{b['elements']:,}, {b['element_rule_pairs']:,}, {b['auto_filled']:,}, {pct(b['pass_after'])}"
        assert cells[4] == f"{pct(x['pass_before'])} → {pct(x['pass_after'])}"


def first_screen():
    return README.split("## What it checks", 1)[0]


def test_first_screen_numbers_trace_to_artifacts():
    head = first_screen()
    catalog = load(CURRENT / "unit_catalog.json")
    s = load(CURRENT / "summary.json")
    assert f"{catalog['mapping']['rows']} rows expand to {catalog['generated_rule_count']:,} rules" in head
    for name, key in (("facade-bim", "facade"), ("bridge-bim", "bridge")):
        m = s[key]
        assert m["pass_before"] == 0 and "from 0% to" in head
        assert f"**{pct(m['pass_after'])}** ({name}, {passed(m, 'pass_after'):,} of {m['element_rule_pairs']:,})" in head
    found = sorted({float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", head)})
    assert found == sorted({0.0, round(100 * s["facade"]["pass_after"], 1), round(100 * s["bridge"]["pass_after"], 1)})


@pytest.fixture(scope="module")
def girders():
    return load(ROOT / "reports/girder-axes-20261108/girder_axes.json")


def mm_range(span):
    return f"{span['min']:,}–{span['max']:,} mm" if span["min"] != span["max"] else f"{span['min']:,} mm"


def test_girder_artifact_is_the_pinned_bridge_model(girders):
    assert girders["model"]["sha256"] == load(CURRENT / "provenance.json")["models"]["bridge"]["sha256"]
    assert "b6456b344b09a92620cc5d4a4cfb2a3be963b147" in girders["model"]["source"]
    assert girders["girders"] == girders["measured"] == 120 and girders["skipped_no_geometry"] == 0


def test_girder_numbers_in_readme_match_artifact(girders):
    depth, width, world = (mm_range(girders[k]) for k in
                           ("principal_axis_depth_mm", "principal_axis_width_mm", "world_vertical_extent_mm"))
    results = section("## Results", "### History")
    assert f"all {girders['measured']} T-girders" in results
    assert f"depth of {depth} and a width of {width}" in results
    assert f"world axis is {world}" in results
    head = first_screen()
    assert f"the {girders['measured']} bridge T-girders come out {depth.replace(' mm', '')} mm deep" in head
    assert f"would give {world}" in head
