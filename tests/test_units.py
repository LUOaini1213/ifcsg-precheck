"""Known physical quantities round-trip through real IFC unit definitions."""
import csv
import json
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import ifcopenshell.util.element as uel
import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.check import Report, property_checks
from ifcsg_precheck.enrich import enrich
from ifcsg_precheck.report import render
from ifcsg_precheck.units import TARGETS, UnitError, audit, make_unit, project_unit, property_entity, read_unit

PSET = "SGPset_SlabDimension"


def rule(unit="mm", **kwargs):
    return dict(id="dimension", entity="IfcSlab", pset=PSET, property="Thickness",
                value_type="number", unit=unit, **kwargs)


def fixture(unit="m"):
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Small controlled fixture")
    if unit is not None:
        project.UnitsInContext = model.create_entity("IfcUnitAssignment", Units=[make_unit(model, TARGETS[unit])])
    element = api.run("root.create_entity", model, ifc_class="IfcSlab", name="S")
    return model, project, element


def property_value(model, product, value, measure="IfcLengthMeasure", explicit=None, pset=PSET, name="Thickness"):
    ps = api.run("pset.add_pset", model, product=product, name=pset)
    nominal = model.create_entity(measure, value) if value is not None else None
    api.run("pset.edit_pset", model, pset=ps,
            properties={name: {"NominalValue": nominal, "Unit": explicit} if explicit is not None else nominal},
            should_purge=False)
    return next(p for p in ps.HasProperties if p.Name == name)


def checked(model, element, selected):
    # Go through the STEP writer/reader rather than passing synthetic dicts.
    parsed = ifcopenshell.file.from_string(model.to_string())
    kept = parsed.by_guid(element.GlobalId)
    report = Report("fixture.ifc", parsed.schema, 1)
    findings = property_checks(parsed, [selected], report)
    return report, findings, parsed, kept


@pytest.mark.parametrize("project,value,explicit", [("m", .25, None), ("mm", 250., None), ("mm", .25, "m"), (None, .25, "m")])
def test_same_physical_length_and_explicit_override(project, value, explicit):
    model, _, element = fixture(project)
    property_value(model, element, value, explicit=make_unit(model, TARGETS[explicit]) if explicit else None)
    rep, findings, _, _ = checked(model, element, rule(min=249, max=251))
    assert findings == [] and rep.passed_pairs == 1 and rep.unit_unverified_pairs == 0
    evidence = rep.unit_results[0]
    assert evidence["normalized_value"] == pytest.approx(250)
    assert evidence["measure_type"] == "IfcLengthMeasure"
    assert evidence["unit_origin"] == ("explicit_property" if explicit else "project")


def test_bounds_use_normalized_target_values():
    model, _, element = fixture()
    property_value(model, element, .25)
    rep, findings, _, _ = checked(model, element, rule(min=300))
    assert rep.passed_pairs == 0 and rep.unit_unverified_pairs == 0
    assert "250.0" in findings[0].message and "expected range" in findings[0].message


@pytest.mark.parametrize("case", ["missing", "generic", "incompatible", "target_dimension", "unsupported", "datum", "ambiguous"])
def test_unverified_units_never_count_as_passed(case):
    model, project, element = fixture(None if case == "missing" else "m")
    explicit, measure, selected = None, "IfcLengthMeasure", rule()
    if case == "generic":
        measure = "IfcReal"
    elif case == "incompatible":
        explicit = make_unit(model, TARGETS["tonnes"])
    elif case == "target_dimension":
        selected = rule("m3")
    elif case == "unsupported":
        explicit = model.create_entity("IfcContextDependentUnit", Dimensions=model.create_entity("IfcDimensionalExponents", 1,0,0,0,0,0,0),
                                       UnitType="LENGTHUNIT", Name="designer's undefined unit")
    elif case == "datum":
        selected = rule("SHD m")
    elif case == "ambiguous":
        project.UnitsInContext.Units = [make_unit(model, TARGETS["m"]), make_unit(model, TARGETS["mm"])]
    property_value(model, element, .25, measure, explicit)
    rep, findings, _, _ = checked(model, element, selected)
    assert rep.passed_pairs == 0 and rep.unit_unverified_pairs == 1
    assert len(findings) == 1 and findings[0].severity == "warning"
    assert rep.unit_results[0]["status"] == "unverified"
    assert rep.unit_results[0]["measure_type"] == measure
    assert "unit unverified" in findings[0].message


@pytest.mark.parametrize("measure,target", [("IfcInteger", "kN"), ("IfcReal", "kPa")])
def test_generic_scalar_cannot_inherit_a_physical_project_unit(measure, target):
    model, project, element = fixture()
    project.UnitsInContext.Units = [*project.UnitsInContext.Units, make_unit(model, TARGETS[target])]
    prop = property_value(model, element, 2, measure)
    rep, findings, _, _ = checked(model, element, rule(target))
    assert rep.passed_pairs == 0 and rep.unit_unverified_pairs == 1
    assert "generic scalar" in findings[0].message
    prop.Unit = make_unit(model, TARGETS[target])
    rep, findings, _, _ = checked(model, element, rule(target))
    assert findings == [] and rep.passed_pairs == 1
    assert rep.unit_results[0]["normalized_value"] == 2


def test_explicit_unit_is_valid_even_with_ambiguous_project_units():
    model, project, element = fixture()
    project.UnitsInContext.Units = [make_unit(model, TARGETS["m"]), make_unit(model, TARGETS["mm"])]
    property_value(model, element, .25, explicit=make_unit(model, TARGETS["m"]))
    rep, findings, _, _ = checked(model, element, rule())
    assert findings == [] and rep.passed_pairs == 1
    assert rep.unit_results[0]["normalized_value"] == 250


def test_explicit_unit_cannot_change_the_measure_dimension_even_when_target_matches():
    model, _, element = fixture()
    property_value(model, element, 2., "IfcLengthMeasure", make_unit(model, TARGETS["tonnes"]))
    rep, findings, _, _ = checked(model, element, rule("tonnes"))
    assert rep.passed_pairs == 0 and rep.unit_unverified_pairs == 1
    assert "measure type and explicit IFC unit" in findings[0].message
    assert rep.unit_results[0]["measure_type"] == "IfcLengthMeasure"


def test_duplicate_raw_property_definitions_are_unverified():
    model, _, element = fixture()
    property_value(model, element, .25)
    duplicate = api.run("pset.add_pset", model, product=element, name="Other")
    api.run("pset.edit_pset", model, pset=duplicate, properties={"Thickness": model.create_entity("IfcLengthMeasure", .3)})
    duplicate.Name = PSET
    rep, findings, _, _ = checked(model, element, rule())
    assert rep.passed_pairs == 0 and rep.unit_unverified_pairs == 1
    assert "ambiguous" in findings[0].message


def test_inherited_measure_keeps_its_unit_when_an_instance_has_a_different_property():
    model, _, element = fixture("mm")
    parent = api.run("root.create_entity", model, ifc_class="IfcSlabType")
    api.run("type.assign_type", model, related_objects=[element], relating_type=parent)
    property_value(model, parent, .25, explicit=make_unit(model, TARGETS["m"]))
    property_value(model, element, "own tag", "IfcLabel", name="Mark")
    rep, findings, _, _ = checked(model, element, rule(min=249, max=251))
    assert findings == [] and rep.passed_pairs == 1
    assert rep.unit_results[0]["property_origin"] == "type"
    assert rep.unit_results[0]["normalized_value"] == 250
    property_value(model, element, 300., explicit=make_unit(model, TARGETS["mm"]))
    rep, findings, _, _ = checked(model, element, rule(min=299, max=301))
    assert findings == [] and rep.unit_results[0]["property_origin"] == "instance"


@pytest.mark.parametrize("unit,measure,value,expected", [
    ("m", "IfcLengthMeasure", .25, .25), ("mm", "IfcLengthMeasure", 250., 250.),
    ("m2", "IfcAreaMeasure", 2.5, 2.5), ("m3", "IfcVolumeMeasure", 3., 3.),
    ("kN", "IfcForceMeasure", 2., 2.), ("kPa", "IfcPressureMeasure", 5., 5.),
    ("hr", "IfcTimeMeasure", .5, .5), ("L", "IfcVolumeMeasure", 4., 4.),
    ("L/s", "IfcVolumetricFlowRateMeasure", 6., 6.), ("tonnes", "IfcMassMeasure", 1.25, 1.25),
])
def test_all_supported_observed_catalogue_units_roundtrip(unit, measure, value, expected):
    model, _, element = fixture()
    declared = make_unit(model, TARGETS[unit])
    property_value(model, element, value, measure, declared)
    rep, findings, _, _ = checked(model, element, rule(unit))
    assert findings == [] and rep.passed_pairs == 1
    assert rep.unit_results[0]["normalized_value"] == pytest.approx(expected)
    assert read_unit(declared).scale == pytest.approx(TARGETS[unit].scale)


@pytest.mark.parametrize("kind,name,prefix,measure,value,target,expected", [
    ("AREAUNIT", "SQUARE_METRE", "MILLI", "IfcAreaMeasure", 1000000., "m2", 1.),
    ("VOLUMEUNIT", "CUBIC_METRE", "MILLI", "IfcVolumeMeasure", 1000000000., "m3", 1.),
    ("MASSUNIT", "GRAM", None, "IfcMassMeasure", 1000000., "tonnes", 1.),
    ("FORCEUNIT", "NEWTON", None, "IfcForceMeasure", 2000., "kN", 2.),
    ("PRESSUREUNIT", "PASCAL", None, "IfcPressureMeasure", 5000., "kPa", 5.),
    ("TIMEUNIT", "SECOND", None, "IfcTimeMeasure", 1800., "hr", .5),
])
def test_known_si_values_normalize_without_name_guessing(kind,name,prefix,measure,value,target,expected):
    model, _, element = fixture()
    declared = model.create_entity("IfcSIUnit", UnitType=kind, Name=name, Prefix=prefix)
    property_value(model, element, value, measure, declared)
    rep, findings, _, _ = checked(model, element, rule(target))
    assert findings == [] and rep.unit_results[0]["normalized_value"] == pytest.approx(expected)


def test_conversion_based_chain_and_derived_flow_have_known_physical_values():
    model, _, element = fixture()
    inch = api.run("unit.add_conversion_based_unit", model, name="inch")
    foot = api.run("unit.add_conversion_based_unit", model, name="foot")
    foot.ConversionFactor.UnitComponent = inch
    foot.ConversionFactor.ValueComponent = model.create_entity("IfcReal", 12.)
    property_value(model, element, 1., explicit=foot)
    rep, findings, _, _ = checked(model, element, rule(min=304, max=305))
    assert findings == [] and rep.unit_results[0]["normalized_value"] == pytest.approx(304.8)
    metre = make_unit(model, TARGETS["m"])
    second = model.create_entity("IfcSIUnit", UnitType="TIMEUNIT", Name="SECOND")
    flow = model.create_entity("IfcDerivedUnit", Elements=[model.create_entity("IfcDerivedUnitElement", Unit=metre, Exponent=3),
                                                          model.create_entity("IfcDerivedUnitElement", Unit=second, Exponent=-1)],
                               UnitType="VOLUMETRICFLOWRATEUNIT")
    property_value(model, element, .002, "IfcVolumetricFlowRateMeasure", flow)
    rep, findings, _, _ = checked(model, element, rule("L/s"))
    assert findings == [] and rep.unit_results[0]["normalized_value"] == pytest.approx(2.)


@pytest.mark.parametrize("fault", ["cycle", "negative", "dimension", "offset", "derived"])
def test_invalid_ifc_unit_definitions_are_not_guessed(fault):
    model, _, _ = fixture()
    unit = api.run("unit.add_conversion_based_unit", model, name="foot")
    if fault == "cycle":
        unit.ConversionFactor.UnitComponent = unit
    elif fault == "negative":
        unit.ConversionFactor.ValueComponent = model.create_entity("IfcReal", -1.)
    elif fault == "dimension":
        unit.ConversionFactor.UnitComponent = make_unit(model, TARGETS["tonnes"])
    elif fault == "offset":
        unit = model.create_entity("IfcConversionBasedUnitWithOffset", Dimensions=unit.Dimensions,
                                   UnitType="LENGTHUNIT", Name="offset", ConversionFactor=unit.ConversionFactor, ConversionOffset=5.)
    else:
        unit = model.create_entity("IfcDerivedUnit", Elements=[model.create_entity("IfcDerivedUnitElement", Unit=make_unit(model,TARGETS["m"]), Exponent=2)],
                                   UnitType="VOLUMETRICFLOWRATEUNIT")
    with pytest.raises(UnitError):
        read_unit(unit)


def test_label_time_qualifier_is_not_converted_to_a_number():
    model, _, element = fixture()
    property_value(model, element, "0.5", "IfcLabel")
    selected = dict(rule("hr"), value_type="text", allowed_values=["0.5", "1"])
    rep, findings, _, _ = checked(model, element, selected)
    assert findings == [] and rep.unit_results[0]["status"] == "qualifier"
    assert rep.unit_results[0]["raw_value"] == "0.5"
    assert "normalized_value" not in rep.unit_results[0]


def test_actual_catalogue_type_spelling_and_aggregate_report(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ifcsg_precheck.mapping import convert
    from scripts.unit_catalog import catalog
    base = {"Agency": "BCA", "Identified Component": "Test", "IFC4 Entities": "IfcSlab",
            "IFC Sub Types": "N.A", "Property Set": PSET, "Accepted Values": "N.A"}
    frame = pd.DataFrame([dict(base, **{"S/N": n, "Property Name": name, "Property Type": typ, "Property Unit": unit})
                          for n, (name, typ, unit) in enumerate([
                              ("Flow", "VolumetricFlowRate", "L/s"), ("Text", "Label", "hr"),
                              ("Force", "Integer", "kN"), ("Datum", "Real", "SHD m")], 1)])
    source = tmp_path / "local.xlsx"
    with pd.ExcelWriter(source) as writer:
        frame.to_excel(writer, sheet_name="CX Pilot Mapping", index=False)
    rules = convert(source)
    assert rules[0]["value_type"] == "number" and rules[0]["property_type"] == "VolumetricFlowRate"
    assert rules[1]["value_type"] == "text" and rules[2]["value_type"] == "number"
    result = catalog(source)
    assert result["generated_rule_target_status_counts"] == {
        "lexical_qualifier": 1, "physical_target_supported": 2, "target_requires_review": 1}
    serialized = json.dumps(result)
    assert "SGPset_" not in serialized and "SHD m" in serialized
    assert str(tmp_path) not in serialized


def test_simple_quantity_retains_its_explicit_unit():
    model, _, element = fixture("mm")
    quantity = model.create_entity("IfcQuantityLength", Name="Thickness", LengthValue=.25, Unit=make_unit(model, TARGETS["m"]))
    definition = model.create_entity("IfcElementQuantity", GlobalId=ifcopenshell.guid.new(), Name=PSET, Quantities=[quantity])
    model.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[element], RelatingPropertyDefinition=definition)
    rep, findings, _, _ = checked(model, element, rule())
    assert findings == [] and rep.passed_pairs == 1
    assert rep.unit_results[0]["measure_type"] == "IfcLengthMeasure"
    assert rep.unit_results[0]["normalized_value"] == 250


def geometry_fixture(source_unit="m"):
    model, project, element = fixture()
    if source_unit == "cm":
        project.UnitsInContext.Units = [model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE", Prefix="CENTI")]
    elif source_unit == "foot":
        project.UnitsInContext.Units = [api.run("unit.add_conversion_based_unit", model, name="foot")]
    ctx = api.run("context.add_context", model, context_type="Model")
    body = api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    shape = api.run("geometry.add_wall_representation", model, context=body, length=4., height=2., thickness=.25)
    api.run("geometry.assign_representation", model, product=element, representation=shape)
    return model, project, element


@pytest.mark.parametrize("source_unit", ["cm", "foot"])
def test_geometry_source_si_prefix_and_conversion_units_roundtrip(tmp_path, source_unit):
    model, _, element = geometry_fixture(source_unit)
    source, output, log = (tmp_path / p for p in ("source.ifc", "out.ifc", "changes.csv"))
    model.write(str(source))
    rows = enrich(source, output, log, rules=[rule()])
    assert len(rows) == 1 and rows[0]["value"] == pytest.approx(250)
    assert rows[0]["source_value_si_m"] == pytest.approx(.25)
    assert rows[0]["source_value_si_m"] * rows[0]["conversion_factor"] == pytest.approx(rows[0]["value"])
    parsed = ifcopenshell.open(str(output))
    rep = Report("out.ifc", parsed.schema, 1)
    assert property_checks(parsed, [rule(min=249,max=251)], rep) == [] and rep.passed_pairs == 1
    prop, _ = property_entity(parsed.by_guid(element.GlobalId), PSET, "Thickness")
    assert prop.NominalValue.is_a() == "IfcLengthMeasure"
    assert prop.NominalValue.wrappedValue * read_unit(prop.Unit).scale == pytest.approx(.25)


@pytest.mark.parametrize("target,explicit,expected", [("mm", None, 250.), ("m", None, .25), ("mm", "m", .25)])
def test_enrich_writes_typed_measure_correct_unit_and_roundtrips_check(tmp_path,target,explicit,expected):
    model, _, element = geometry_fixture()
    if explicit:
        property_value(model, element, None, explicit=make_unit(model,TARGETS[explicit]))
    source, output, log = (tmp_path / p for p in ("source.ifc", "out.ifc", "changes.csv"))
    model.write(str(source)); original = source.read_bytes()
    pending = []
    rows = enrich(source, output, log, rules=[rule(target)], pending=pending)
    assert source.read_bytes() == original and pending == [] and len(rows) == 1
    parsed = ifcopenshell.open(str(output)); kept = parsed.by_guid(element.GlobalId)
    prop, _ = property_entity(kept, PSET, "Thickness")
    assert prop.NominalValue.is_a() == "IfcLengthMeasure"
    assert prop.NominalValue.wrappedValue == pytest.approx(expected)
    assert read_unit(prop.Unit).scale == pytest.approx(TARGETS[explicit or target].scale)
    rep = Report("out.ifc", parsed.schema, 1)
    assert property_checks(parsed, [rule(target)], rep) == [] and rep.passed_pairs == 1
    assert rep.unit_results[0]["normalized_value"] == pytest.approx(.25 / TARGETS[target].scale)
    assert rows[0]["mapping_units"] == target and rows[0]["geometry_project_unit"] == "METRE"
    assert rows[0]["source_value_si_m"] == pytest.approx(.25)
    assert rows[0]["source_value_si_m"] * rows[0]["conversion_factor"] == pytest.approx(expected)
    logged = next(csv.DictReader(log.open(encoding="utf-8")))
    assert float(logged["source_value_si_m"]) * float(logged["conversion_factor"]) == pytest.approx(float(logged["value"]))
    assert float(logged["value"]) == pytest.approx(prop.NominalValue.wrappedValue)
    assert enrich(output, tmp_path/"again.ifc", tmp_path/"again.csv", rules=[rule(target)]) == []


def test_cli_and_evaluation_use_the_mapping_target_not_legacy_millimetres(tmp_path, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts import evaluate
    from ifcsg_precheck.cli import main
    model, _, element = geometry_fixture()
    source = tmp_path / "source.ifc"; model.write(str(source))
    rules = tmp_path / "rules.json"; rules.write_text(json.dumps([rule("m")]))
    output = tmp_path / "cli.ifc"
    main(["enrich", str(source), str(output), "--rules", str(rules), "--html", str(tmp_path / "cli.html")])
    parsed = ifcopenshell.open(str(output))
    prop, _ = property_entity(parsed.by_guid(element.GlobalId), PSET, "Thickness")
    assert prop.NominalValue.wrappedValue == pytest.approx(.25)
    assert read_unit(prop.Unit).scale == 1
    assert "1 values filled; 0 derivations deferred" in capsys.readouterr().out
    folder = tmp_path / "new-review"
    evaluate.main(["--output-dir", str(folder), "--rules", str(rules), f"small={source}"])
    summary = json.loads((folder / "summary.json").read_text())["small"]
    after = json.loads((folder / "small_after.json").read_text())
    assert summary["auto_filled"] == 1 and summary["unit_unverified_after"] == 0
    assert after["unit_results"][0]["normalized_value"] == pytest.approx(.25)
    assert "src/ifcsg_precheck/units.py" in json.loads((folder / "provenance.json").read_text())["source_sha256"]


@pytest.mark.parametrize("fault", ["geometry_units", "target_units", "target_dimension", "blank_unit"])
def test_enrich_defers_unreliable_units_without_filling(tmp_path, fault):
    model, project, element = geometry_fixture()
    selected = rule()
    if fault == "geometry_units":
        project.UnitsInContext = None
    elif fault == "target_units":
        selected = rule("unknown")
    elif fault == "target_dimension":
        selected = rule("m3")
    else:
        property_value(model, element, None, explicit=make_unit(model,TARGETS["tonnes"]))
    source, output, log = (tmp_path / p for p in ("source.ifc", "out.ifc", "changes.csv"))
    model.write(str(source)); original = source.read_bytes(); pending=[]
    assert enrich(source, output, log, rules=[selected], pending=pending) == []
    assert source.read_bytes() == original and len(pending) == 1 and pending[0]["status"] == "unverified"
    assert json.loads(Path(str(log)+".pending.json").read_text()) == pending
    kept = ifcopenshell.open(str(output)).by_guid(element.GlobalId)
    assert uel.get_psets(kept).get(PSET, {}).get("Thickness") is None
    rep = Report("out.ifc", "IFC4", 1)
    html = render(rep, [], enrichment_pending=pending)
    assert "Derivations deferred for review" in html
