"""A new measurement must be separable from the previously published report."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts import evaluate
from ifcsg_precheck.sample import build


def test_real_sample_run_preserves_previous_report_and_records_inputs(tmp_path, monkeypatch):
    historical = tmp_path / "published"
    historical.mkdir()
    sentinel = historical / "summary.json"
    sentinel.write_bytes(b"historical measurement")
    monkeypatch.setattr(evaluate, "OUT", historical)
    model = build(tmp_path / "sample.ifc")
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{"id": "T1", "entity": "IfcSlab", "pset": "SGPset_SlabDimension",
                                  "property": "Mark", "value_type": "text"}]))
    out = tmp_path / "new" / "review"
    evaluate.main(["--rules", str(rules), "--output-dir", str(out), f"sample={model}"])
    assert sentinel.read_bytes() == b"historical measurement"
    summary = json.loads((out / "summary.json").read_text())
    assert summary["sample"]["auto_filled"] == 1
    assert summary["sample"]["pass_before"] == 0
    assert summary["sample"]["pass_after"] == 1
    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["models"]["sample"] == {"file": model.name,
        "sha256": hashlib.sha256(model.read_bytes()).hexdigest()}
    assert provenance["rule_count"] == 1
    assert str(tmp_path) not in (out / "provenance.json").read_text()
    assert (out / "sample_enriched.ifc").is_file()
    assert (out / "sample_report.html").is_file()


def test_empty_rules_cannot_publish_a_successful_evaluation(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text("[]")
    out = tmp_path / "review"
    with pytest.raises(SystemExit) as error:
        evaluate.main(["--rules", str(rules), "--output-dir", str(out), "sample=unused.ifc"])
    assert error.value.code == 2
    assert not out.exists()


def test_custom_rule_still_missing_after_enrichment_remains_a_mapping_gap(tmp_path):
    model = build(tmp_path / "sample.ifc")
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([{"id": "T1", "entity": "IfcSlab", "pset": "SGPset_SlabDimension",
                                  "property": "DesignReference", "value_type": "text"}]))
    out = tmp_path / "review"
    evaluate.main(["--rules", str(rules), "--output-dir", str(out), f"sample={model}"])
    summary = json.loads((out / "summary.json").read_text())["sample"]
    assert summary["pass_after"] == 0 and summary["auto_filled"] == 0
    assert not any(rule == "T1" for rule, message in summary["model_level_findings"])
    assert [["IfcSlab", "SGPset_SlabDimension"], 1] in summary["top_remaining"]
    findings = json.loads((out / "sample_after.json").read_text())["findings"]
    assert next(f for f in findings if f["rule"] == "T1")["origin"] == "mapping"
