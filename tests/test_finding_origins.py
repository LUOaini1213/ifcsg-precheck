"""Finding origin is explicit for checks, with compatibility for legacy constructors."""
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.check import Finding, Report, model_checks, property_checks  # noqa: E402


@pytest.mark.parametrize("state", ["missing-pset", "missing-property", "invalid-value"])
def test_property_checks_mark_all_failure_paths_as_mapping_even_for_model_rule_id(state):
    model = ifcopenshell.file(schema="IFC4")
    door = api.run("root.create_entity", model, ifc_class="IfcDoor")
    if state != "missing-pset":
        pset = api.run("pset.add_pset", model, product=door, name="SGPset_DoorDimension")
        properties = {"ClearWidth": "not a number"} if state == "invalid-value" else {"ClearHeight": 2100.0}
        api.run("pset.edit_pset", model, pset=pset, properties=properties)
    rule = {"id": "containment", "entity": "IfcDoor", "pset": "SGPset_DoorDimension",
            "property": "ClearWidth", "value_type": "number"}
    report = Report("memory.ifc", model.schema, 1)
    findings = property_checks(model, [rule], report)
    assert len(findings) == 1 and findings[0].origin == "mapping"
    report.findings = model_checks(model) + findings
    assert any(f.rule == "containment" and f.origin == "model" for f in report.findings)
    assert {f["origin"] for f in report.to_json()["findings"]} == {"model", "mapping"}


def test_legacy_finding_constructors_keep_their_prior_classification():
    assert Finding("CX1", "error", "mapping gap").origin == "mapping"
    assert Finding("containment", "error", "model gap").origin == "model"


def test_explicit_origin_takes_precedence_over_rule_name():
    assert Finding("T1", "error", "custom mapping", origin="mapping").origin == "mapping"
    assert Finding("CX-model", "warning", "explicit model check", origin="model").origin == "model"
