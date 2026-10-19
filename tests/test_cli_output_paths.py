"""CLI output aliases must never overwrite an input or leave partial artifacts."""
import json
import os
import sys
from pathlib import Path

import ifcopenshell
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck import cli  # noqa: E402
from ifcsg_precheck.sample import build  # noqa: E402


@pytest.fixture
def inputs(tmp_path):
    source = build(tmp_path / "source.ifc")
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([dict(id="mark", agency="Review", entity="IfcSlab",
        pset="SGPset_SlabDimension", property="Mark", value_type="text")]), encoding="utf-8")
    return source, rules


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def assert_rejected_unchanged(args, source, capsys):
    before = snapshot(source.parent)
    with pytest.raises(SystemExit) as exc:
        cli.main([str(arg) for arg in args])
    assert exc.value.code == 2
    assert "conflict" in capsys.readouterr().err
    assert snapshot(source.parent) == before
    assert ifcopenshell.open(str(source)).by_type("IfcProject")


def alias(target, kind, monkeypatch):
    if kind == "absolute":
        return target.resolve()
    if kind == "relative":
        monkeypatch.chdir(target.parent)
        (target.parent / "subdir").mkdir()
        return Path("subdir") / ".." / target.name
    linked = target.with_name("alias-" + target.name)
    try:
        if kind == "symlink":
            linked.symlink_to(target)
        else:
            os.link(target, linked)
    except OSError as exc:
        pytest.skip(f"{kind} unavailable on this filesystem: {exc}")
    return linked


@pytest.mark.parametrize("kind", ["absolute", "relative", "symlink", "hardlink"])
@pytest.mark.parametrize("collision", ["check-json", "check-html", "enrich-model", "enrich-html"])
def test_model_input_alias_is_rejected_before_any_output(inputs, kind, collision, monkeypatch, capsys):
    source, rules = inputs
    output = alias(source, kind, monkeypatch)
    if collision.startswith("check"):
        args = ["check", source, "--rules", rules,
                "--json", output if collision == "check-json" else source.parent / "safe.json",
                "--html", output if collision == "check-html" else source.parent / "safe.html"]
    else:
        args = ["enrich", source, output if collision == "enrich-model" else source.parent / "derived.ifc",
                "--rules", rules, "--html", output if collision == "enrich-html" else source.parent / "safe.html"]
    assert_rejected_unchanged(args, source, capsys)


@pytest.mark.parametrize("collision", ["check-json", "check-html", "enrich-model", "enrich-html",
                                        "enrich-log", "enrich-pending"])
def test_rule_inputs_are_protected_including_generated_sidecars(inputs, collision, capsys):
    source, rules = inputs
    output = source.parent / "derived.ifc"
    if collision in ("enrich-log", "enrich-pending"):
        destination = Path(str(output) + ".log.csv" + (".pending.json" if collision.endswith("pending") else ""))
        rules.rename(destination)
        rules = destination
    if collision.startswith("check"):
        args = ["check", source, "--rules", rules,
                "--json", rules if collision == "check-json" else source.parent / "safe.json",
                "--html", rules if collision == "check-html" else source.parent / "safe.html"]
    else:
        args = ["enrich", source, rules if collision == "enrich-model" else output,
                "--rules", rules, "--html", rules if collision == "enrich-html" else source.parent / "safe.html"]
    assert_rejected_unchanged(args, source, capsys)


def test_implicitly_loaded_rules_are_protected(inputs, monkeypatch, capsys):
    source, rules = inputs
    monkeypatch.setattr(cli, "RULES_DIR", source.parent)
    assert_rejected_unchanged(["check", source, "--json", rules], source, capsys)


@pytest.mark.parametrize("target", ["derived.ifc", "derived.ifc.log.csv", "derived.ifc.log.csv.pending.json"])
def test_enrich_report_cannot_replace_model_or_sidecars(inputs, target, capsys):
    source, rules = inputs
    assert_rejected_unchanged(["enrich", source, source.parent / "derived.ifc", "--rules", rules,
                              "--html", source.parent / target], source, capsys)


@pytest.mark.parametrize("kind", ["same", "relative", "symlink", "hardlink", "nested"])
def test_report_outputs_must_be_distinct(inputs, kind, monkeypatch, capsys):
    source, rules = inputs
    first = source.parent / "report.json"
    if kind == "same":
        second = first
    elif kind == "nested":
        second = first / "report.html"
    else:
        first.write_text("previous report", encoding="utf-8")
        second = alias(first, kind, monkeypatch)
    assert_rejected_unchanged(["check", source, "--rules", rules, "--json", first, "--html", second], source, capsys)


def test_mapping_conversion_cannot_overwrite_its_workbook(tmp_path, monkeypatch, capsys):
    import pandas as pd
    workbook = tmp_path / "authored.xlsx"
    pd.DataFrame({"authored": ["fixture"]}).to_excel(workbook, index=False)
    target = alias(workbook, "hardlink", monkeypatch)
    before = snapshot(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.main(["rules", str(workbook), "--out", str(target)])
    assert exc.value.code == 2 and "conflict" in capsys.readouterr().err
    assert snapshot(tmp_path) == before
    assert pd.read_excel(workbook).iloc[0, 0] == "fixture"


def test_distinct_existing_reports_can_be_replaced_and_model_remains_intact(inputs, capsys):
    source, rules = inputs
    original = source.read_bytes()
    html, report = source.parent / "report.html", source.parent / "report.json"
    for target in (html, report):
        target.write_text("old report", encoding="utf-8")
    cli.main(["check", str(source), "--rules", str(rules), "--html", str(html), "--json", str(report)])
    assert "<!doctype html>" in html.read_text(encoding="utf-8")
    assert json.loads(report.read_text(encoding="utf-8"))["summary"]["elements"] == 10
    output = source.parent / "derived.ifc"
    cli.main(["enrich", str(source), str(output), "--rules", str(rules), "--html", str(html)])
    assert ifcopenshell.open(str(output)).by_type("IfcProject")
    assert Path(str(output) + ".log.csv").is_file()
    assert Path(str(output) + ".log.csv.pending.json").is_file()
    assert source.read_bytes() == original
    assert ifcopenshell.open(str(source)).by_type("IfcProject")
