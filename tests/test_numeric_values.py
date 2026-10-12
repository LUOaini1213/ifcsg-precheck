"""Numeric property checks must reject booleans and non-finite IFC values."""
import math
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import ifcopenshell.util.element as uel
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.check import Report, property_checks, value_problem  # noqa: E402


NUMBER_RULE = {"id": "width", "entity": "IfcDoor", "pset": "SGPset_DoorDimension",
               "property": "ClearWidth", "value_type": "number"}


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("bounds", [{}, {"min": 0, "max": 2000}])
def test_numeric_rules_reject_boolean_and_nonfinite_values(value, bounds):
    assert value_problem(dict(NUMBER_RULE, **bounds), value) is not None


@pytest.mark.parametrize("value", [0, 0.0, 1000, 1000.5, -1, 10 ** 400])
def test_finite_numbers_keep_existing_type_contract(value):
    assert value_problem(NUMBER_RULE, value) is None


@pytest.mark.parametrize("value", [True, False])
def test_boolean_properties_remain_valid_for_boolean_rules(value):
    assert value_problem({"value_type": "boolean"}, value) is None


@pytest.mark.parametrize("token,expected_kind", [
    ("IFCBOOLEAN(.T.)", "boolean"), ("IFCBOOLEAN(.F.)", "boolean"),
    ("IFCREAL(1.E+400)", "nonfinite"), ("IFCREAL(-1.E+400)", "nonfinite"),
    ("IFCREAL(NAN)", "nonfinite"), ("IFCREAL(INF)", "nonfinite"),
])
def test_ifc_parser_values_do_not_count_as_passing_numeric_properties(token, expected_kind):
    model = ifcopenshell.file(schema="IFC4")
    door = api.run("root.create_entity", model, ifc_class="IfcDoor", name="D")
    pset = api.run("pset.add_pset", model, product=door, name=NUMBER_RULE["pset"])
    api.run("pset.edit_pset", model, pset=pset, properties={"ClearWidth": 1234.0})
    # The writer rejects non-finite floats, but the STEP reader accepts these inputs.
    step = model.to_string()
    assert step.count("IFCREAL(1234.)") == 1
    model = ifcopenshell.file.from_string(step.replace("IFCREAL(1234.)", token))
    actual = uel.get_psets(model.by_type("IfcDoor")[0])[NUMBER_RULE["pset"]]["ClearWidth"]
    assert isinstance(actual, bool) if expected_kind == "boolean" else not math.isfinite(actual)
    report = Report("memory.ifc", model.schema, 1)
    findings = property_checks(model, [NUMBER_RULE], report)
    assert report.element_rule_pairs == 1 and report.passed_pairs == 0
    assert len(findings) == 1 and findings[0].rule == "width"
