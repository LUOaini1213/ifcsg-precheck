"""check/enrich must refuse to run with no mapping rules instead of reporting a near-clean model."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ifcsg_precheck import cli  # noqa: E402
from ifcsg_precheck.sample import build  # noqa: E402

AUTHORED_RULES = ROOT / "demos" / "report-review" / "authored_rules.json"


@pytest.fixture
def empty_rules_dir(tmp_path, monkeypatch):
    folder = tmp_path / "rules"
    folder.mkdir()
    monkeypatch.setattr(cli, "RULES_DIR", folder)
    return folder


@pytest.fixture
def sample(tmp_path):
    return build(tmp_path / "model" / "sample.ifc")


def run_rejected(args, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([str(x) for x in args])
    assert exc.value.code == 2
    return capsys.readouterr().err


@pytest.mark.parametrize("command", ["check", "enrich"])
def test_no_rule_files_exits_2_without_writing(command, sample, empty_rules_dir, tmp_path, capsys):
    out = tmp_path / "out"
    args = [command, sample, "--html", out / "r.html"]
    if command == "enrich":
        args = [command, sample, out / "e.ifc", "--html", out / "r.html"]
    err = run_rejected(args, capsys)
    assert "no rule files found" in err and "--rules" in err
    assert not out.exists()


def test_empty_rule_file_exits_2(sample, tmp_path, capsys):
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    assert "contain no rules" in run_rejected(["check", sample, "--rules", empty], capsys)


def test_unknown_agency_exits_2(sample, capsys):
    err = run_rejected(["check", sample, "--rules", AUTHORED_RULES, "--agency", "NO-SUCH-AGENCY"], capsys)
    assert "no rules for agency 'NO-SUCH-AGENCY'" in err and "Demo structures" in err


def test_known_agency_still_filters(sample, capsys):
    cli.main(["check", str(sample), "--rules", str(AUTHORED_RULES), "--agency", "Demo structures"])
    summary = json.loads(capsys.readouterr().out)
    agencies = {r["agency"] for r in json.loads(AUTHORED_RULES.read_text(encoding="utf-8"))}
    assert "Demo structures" in agencies and len(agencies) > 1
    assert 0 < summary["rules_applied"] < len(json.loads(AUTHORED_RULES.read_text(encoding="utf-8")))


def test_readme_workbook_free_trial_applies_rules(tmp_path, capsys, monkeypatch):
    """The README's 'Try it without the BCA workbook' command runs from a clean clone."""
    monkeypatch.chdir(ROOT)
    html = tmp_path / "out.html"
    cli.main(["check", "samples/sample_block.ifc", "--rules", "demos/report-review/authored_rules.json", "--html", str(html)])
    summary = json.loads(capsys.readouterr().out)
    assert summary["rules_applied"] > 0 and summary["element_rule_pairs"] > 0
    assert html.read_text(encoding="utf-8").strip()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert ("python -m ifcsg_precheck.cli check samples/sample_block.ifc "
            "--rules demos/report-review/authored_rules.json --html out.html") in readme
