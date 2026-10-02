"""Real IFC regressions for rule selection and this project's storey profile."""
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.check import Report, model_checks, property_checks  # noqa: E402


def door_model(type_enum=None, type_label=None, occurrence_enum=None, occurrence_label=None):
    model = ifcopenshell.file(schema="IFC4")
    door = api.run("root.create_entity", model, ifc_class="IfcDoor", name="Access door")
    if type_enum is not None:
        door_type = api.run("root.create_entity", model, ifc_class="IfcDoorType", predefined_type=type_enum)
        door_type.ElementType = type_label
        api.run("type.assign_type", model, related_objects=[door], relating_type=door_type)
    door.PredefinedType = occurrence_enum
    door.ObjectType = occurrence_label
    return model, door


def rule(rule_id, subtype, custom=False):
    return {"id": rule_id, "entity": "IfcDoor", "predefined_type": subtype, "userdefined": custom,
            "pset": "SGPset_DoorDimension", "property": "ClearWidth", "value_type": "number"}


@pytest.mark.parametrize("type_enum,type_label,occurrence_enum,occurrence_label,expected", [
    (None, None, "DOOR", None, {"enum-door"}),
    (None, None, "USERDEFINED", "ACCESSHATCH", {"custom-hatch"}),
    ("DOOR", None, None, None, {"enum-door"}),
    ("USERDEFINED", "accesshatch", None, None, {"custom-hatch"}),
    ("NOTDEFINED", None, "DOOR", None, {"enum-door"}),
    ("NOTDEFINED", None, "USERDEFINED", "ACCESSHATCH", {"custom-hatch"}),
    # The associated type wins even if an export also supplies conflicting occurrence fields.
    ("DOOR", None, "USERDEFINED", "ACCESSHATCH", {"enum-door"}),
    ("USERDEFINED", "ACCESSHATCH", "DOOR", None, {"custom-hatch"}),
    # A custom label with the spelling of an enum is still a custom label.
    ("USERDEFINED", "DOOR", None, None, {"custom-door"}),
    (None, None, "USERDEFINED", "DOOR", {"custom-door"}),
    (None, None, "DOOR", "ACCESSHATCH", {"enum-door"}),
    ("USERDEFINED", None, None, None, set()),
    ("USERDEFINED", "", "USERDEFINED", "ACCESSHATCH", set()),
    ("NOTDEFINED", None, None, None, set()),
    (None, None, None, "ACCESSHATCH", set()),
])
def test_rules_follow_effective_enum_and_custom_label(
        type_enum, type_label, occurrence_enum, occurrence_label, expected):
    model, _ = door_model(type_enum, type_label, occurrence_enum, occurrence_label)
    model = ifcopenshell.file.from_string(model.to_string())
    rules = [rule("enum-door", "DOOR"), rule("custom-door", "DOOR", True),
             rule("custom-hatch", "ACCESSHATCH", True)]
    report = Report("memory.ifc", model.schema, 1)
    findings = property_checks(model, rules, report)
    assert {finding.rule for finding in findings} == expected
    assert report.element_rule_pairs == report.rules_applied == len(expected)
    assert report.passed_pairs == 0  # Every applicable rule has a missing property set.


@pytest.mark.parametrize("override,expected_problem", [
    ("absent", None), (800.0, None), (None, "is empty"), ("", "is empty"), ("1000 mm", "number"),
])
def test_typed_custom_rule_checks_merged_properties_and_occurrence_override(override, expected_problem):
    model, door = door_model("USERDEFINED", "ACCESSHATCH")
    door_type = model.by_type("IfcDoorType")[0]
    pset = api.run("pset.add_pset", model, product=door_type, name="SGPset_DoorDimension")
    api.run("pset.edit_pset", model, pset=pset, properties={"ClearWidth": 1000.0})
    if override != "absent":
        pset = api.run("pset.add_pset", model, product=door, name="SGPset_DoorDimension")
        nominal = None if override is None else model.create_entity(
            "IfcReal" if isinstance(override, float) else "IfcLabel", override)
        pset.HasProperties = (model.create_entity("IfcPropertySingleValue", Name="ClearWidth", NominalValue=nominal),)
    report = Report("memory.ifc", model.schema, 1)
    findings = property_checks(model, [rule("custom-hatch", "ACCESSHATCH", True)], report)
    assert report.element_rule_pairs == 1
    if expected_problem is None:
        assert not findings and report.passed_pairs == 1
    else:
        assert len(findings) == 1 and expected_problem in findings[0].message
        assert report.passed_pairs == 0


@pytest.mark.parametrize("route,should_pass", [
    ("storey", True), ("space", True), ("assembly", True), ("nested-assembly", True),
    ("building", False), ("site", False), ("orphan-assembly", False), ("none", False),
])
def test_storey_profile_requires_an_actual_storey_ancestor(route, should_pass):
    model = ifcopenshell.file(schema="IFC4")
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1")
    api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    api.run("aggregate.assign_object", model, products=[storey], relating_object=building)
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
    if route in ("storey", "building", "site"):
        container = {"storey": storey, "building": building, "site": site}[route]
        api.run("spatial.assign_container", model, products=[wall], relating_structure=container)
    elif route == "space":
        space = api.run("root.create_entity", model, ifc_class="IfcSpace", name="Room")
        api.run("aggregate.assign_object", model, products=[space], relating_object=storey)
        api.run("spatial.assign_container", model, products=[wall], relating_structure=space)
    elif "assembly" in route:
        assembly = api.run("root.create_entity", model, ifc_class="IfcElementAssembly", name="Assembly")
        if route != "orphan-assembly":
            api.run("spatial.assign_container", model, products=[assembly], relating_structure=storey)
        if route == "nested-assembly":
            api.run("nest.assign_object", model, related_objects=[wall], relating_object=assembly)
        else:
            api.run("aggregate.assign_object", model, products=[wall], relating_object=assembly)
    findings = [f for f in model_checks(model) if f.rule == "containment" and f.guid == wall.GlobalId]
    assert (not findings) == should_pass


@pytest.mark.parametrize("ifc_class", ["IfcOpeningElement", "IfcProjectionElement"])
def test_storey_profile_keeps_feature_exemptions(ifc_class):
    model = ifcopenshell.file(schema="IFC4")
    feature = api.run("root.create_entity", model, ifc_class=ifc_class)
    assert not [f for f in model_checks(model) if f.rule == "containment" and f.guid == feature.GlobalId]
