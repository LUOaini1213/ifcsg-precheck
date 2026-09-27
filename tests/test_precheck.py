import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.check import applies, check, value_problem  # noqa: E402
from ifcsg_precheck.enrich import concrete_grade, enrich  # noqa: E402
from ifcsg_precheck.mapping import allowed, convert, value_type  # noqa: E402
from ifcsg_precheck.sample import build  # noqa: E402

# Rules written for the tests (the real rules are generated locally from BCA's mapping, which is not redistributed).
RULES = [
    {"id": "T1", "agency": "SCDF", "entity": "IfcDoor", "predefined_type": "DOOR", "userdefined": False,
     "pset": "SGPset_DoorDimension", "property": "ClearWidth", "value_type": "number", "allowed_values": None, "severity": "error"},
    {"id": "T2", "agency": "SCDF", "entity": "IfcDoor", "predefined_type": "DOOR", "userdefined": False,
     "pset": "Pset_DoorCommon", "property": "FireRating", "value_type": "text",
     "allowed_values": ["0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4"], "severity": "error"},
    {"id": "T3", "agency": "BCA", "entity": "IfcSlab", "predefined_type": None, "userdefined": False,
     "pset": "SGPset_SlabDimension", "property": "Thickness", "value_type": "number", "allowed_values": None, "severity": "error"},
    {"id": "T4", "agency": "BCA", "entity": "IfcSlab", "predefined_type": None, "userdefined": False,
     "pset": "SGPset_SlabDimension", "property": "Mark", "value_type": "text", "allowed_values": None, "severity": "error"},
]


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    return build(tmp_path_factory.mktemp("s") / "sample.ifc")


def by(rep):
    return {(f.name, f.rule): f.message for f in rep.findings}


def test_planted_defects_are_found_and_nothing_else_on_doors(sample):
    rep = check(sample, RULES)
    f = by(rep)
    assert ("D-03", "T1") in f and "no ClearWidth" in f[("D-03", "T1")]
    assert ("D-04", "T1") in f and "number" in f[("D-04", "T1")]
    assert ("D-02", "T2") in f and "allowed" in f[("D-02", "T2")]
    assert ("D-01", "T1") not in f and ("D-01", "T2") not in f        # the correct door passes
    assert ("W-X", "containment") in f
    assert any(x.rule == "georeference" for x in rep.findings)


def test_counts_and_pass_rate(sample):
    rep = check(sample, RULES)
    # 4 doors x 2 rules + 1 slab x 2 rules = 10 pairs; failures: D-02 T2, D-03 T1, D-04 T1, slab T4 (no Mark)
    assert rep.element_rule_pairs == 10 and rep.passed_pairs == 6
    assert rep.summary()["pass_rate"] == pytest.approx(0.6)


def test_model_checks_on_a_clean_structure(sample):
    rep = check(sample, [])
    rules = {f.rule for f in rep.findings}
    assert rules == {"containment", "georeference"}                    # units, storeys, site, building all fine


@pytest.mark.parametrize("rule, value, problem", [
    ({"value_type": "number"}, 1000.0, None),
    ({"value_type": "number"}, "1000 mm", "number"),
    ({"value_type": "boolean"}, "yes", "true/false"),
    ({"value_type": "text", "allowed_values": ["0.5", "1"]}, "1", None),
    ({"value_type": "text", "allowed_values": ["0.5", "1"]}, "1 hr", "allowed"),
    ({"value_type": "text"}, "  ", "empty"),
    ({"value_type": "number", "min": 0, "max": 10}, 12, "outside"),
])
def test_value_problem(rule, value, problem):
    got = value_problem(rule, value)
    assert (got is None) if problem is None else (problem in got)


def test_userdefined_subtype_matches_object_type(sample):
    import ifcopenshell
    m = ifcopenshell.open(str(sample))
    door = m.by_type("IfcDoor")[0]
    rule = {"entity": "IfcDoor", "predefined_type": "BLASTDOOR", "userdefined": True}
    assert not applies(rule, door)
    door.PredefinedType, door.ObjectType = "USERDEFINED", "BLASTDOOR"
    assert applies(rule, door)
    assert not applies({"entity": "IfcDoor", "predefined_type": "DOOR", "userdefined": False}, door)
    other = m.by_type("IfcDoor")[1]                                   # PredefinedType DOOR, not user-defined
    assert applies({"entity": "IfcDoor", "predefined_type": "DOOR", "userdefined": False}, other)
    assert not applies({"entity": "IfcDoor", "predefined_type": "DOOR", "userdefined": True}, other)


def test_enrich_fills_only_derivable_values_and_logs_them(sample, tmp_path):
    out, log = tmp_path / "e.ifc", tmp_path / "e.csv"
    rows = enrich(sample, out, log, {("IfcSlab", "SGPset_SlabDimension", "Mark"),
                                     ("IfcSlab", "SGPset_SlabDimension", "Thickness")})
    filled = {(r["name"], r["property"]) for r in rows}
    assert filled == {("S-2", "Mark")}          # Thickness already present (150) is not overwritten; no geometry
    assert list(csv.DictReader(open(log, encoding="utf-8")))[0]["source"] == "Name"
    rep = check(out, RULES)
    assert ("S-2", "T4") not in by(rep)
    # only what the rules ask for is written
    assert enrich(sample, tmp_path / "n.ifc", tmp_path / "n.csv", {("IfcSlab", "SGPset_SlabDimension", "Thickness")}) == []


@pytest.mark.parametrize("given, expected", [("C50", "C50/60"), ("c32", "C32/40"), ("C40/50", "C40/50"),
                                             ("", None), ("Grade 40", None)])
def test_concrete_grade(given, expected):
    assert concrete_grade(given) == expected


def test_enrich_measures_members_square_to_their_axis(tmp_path):
    """A 10 m beam, 0.6 m deep and 0.3 m wide, pitched at 5 degrees: the depth must be 600 mm, not the rise."""
    import ifcopenshell
    import ifcopenshell.api as api
    import numpy as np
    f = api.run("project.create_file", version="IFC4")
    api.run("root.create_entity", f, ifc_class="IfcProject", name="p")
    api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    ctx = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    beam = api.run("root.create_entity", f, ifc_class="IfcBeam", name="B1")
    rep = api.run("geometry.add_wall_representation", f, context=body, length=10.0, height=0.6, thickness=0.3)
    api.run("geometry.assign_representation", f, product=beam, representation=rep)
    a = np.radians(5)
    m = np.eye(4); m[0, 0], m[0, 2], m[2, 0], m[2, 2] = np.cos(a), -np.sin(a), np.sin(a), np.cos(a)
    api.run("geometry.edit_object_placement", f, product=beam, matrix=m)
    src = tmp_path / "b.ifc"; f.write(str(src))
    rows = enrich(src, tmp_path / "o.ifc", tmp_path / "o.csv", None)
    got = {r["property"]: r["value"] for r in rows}
    assert got["Depth"] == 600 and got["Width"] == 300
    # a value the designer already entered is kept, even when the geometry says otherwise
    p = api.run("pset.add_pset", f, product=beam, name="SGPset_BeamDimension")
    api.run("pset.edit_pset", f, pset=p, properties={"Depth": 650.0})
    f.write(str(src))
    rows = enrich(src, tmp_path / "o2.ifc", tmp_path / "o2.csv", None)
    assert "Depth" not in {r["property"] for r in rows} and "Width" in {r["property"] for r in rows}
    import ifcopenshell.util.element as uel
    kept = ifcopenshell.open(str(tmp_path / "o2.ifc")).by_type("IfcBeam")[0]
    assert uel.get_psets(kept)["SGPset_BeamDimension"]["Depth"] == 650.0


# ---------- mapping conversion ----------
def test_value_type_and_allowed():
    assert value_type("Boolean") == "boolean" and value_type("Length") == "number" and value_type("Label") == "text"
    assert allowed("0.5, 1, 1.5", "text") == ["0.5", "1", "1.5"]
    assert allowed("Refer to Table 2, etc", "text") is None          # descriptive, not enforced
    assert allowed("TRUE/FALSE", "boolean") is None


def test_convert_small_mapping(tmp_path):
    df = pd.DataFrame([
        {"S/N": 1, "Agency": "NPARKS", "Identified Component": "Door", "IFC4\n Entities": "IfcDoor",
         "IFC Sub Types\n(* = USERDEFINED)": "DOOR, *BLASTDOOR", "Property Set": "Pset_DoorCommon", "Property Name": "FireRating",
         "Property Type": "Label", "Property Unit": "hr", "Accepted Values \n(for parameters with Input Limitations)": "0.5, 1, 2"},
        {"S/N": 2, "Agency": "BCA", "Identified Component": "Door", "IFC4\n Entities": "IfcDoor",
         "IFC Sub Types\n(* = USERDEFINED)": "N.A", "Property Set": "Please refer to property sets below",
         "Property Name": "Please refer to properties below", "Property Type": "N.A", "Property Unit": "N.A",
         "Accepted Values \n(for parameters with Input Limitations)": "N.A"},
    ])
    x = tmp_path / "m.xlsx"
    with pd.ExcelWriter(x) as w:
        df.to_excel(w, sheet_name="CX Pilot Mapping", index=False)
    rules = convert(x)
    assert len(rules) == 2                                       # header row dropped; two sub types
    assert {r["predefined_type"] for r in rules} == {"DOOR", "BLASTDOOR"}
    assert [r["userdefined"] for r in rules] == [False, True]
    assert rules[0]["agency"] == "NParks" and rules[0]["allowed_values"] == ["0.5", "1", "2"]


# ---------- model-level checks ----------
def _variant(sample, tmp_path, change):
    import ifcopenshell
    m = ifcopenshell.open(str(sample))
    change(m)
    out = tmp_path / "v.ifc"
    m.write(str(out))
    return {f.rule: f.message for f in check(out, []).findings}


def test_duplicate_storey_names_and_guids_are_flagged(sample, tmp_path):
    def change(m):
        a, b = m.by_type("IfcBuildingStorey")
        b.Name = a.Name
        w1, w2 = m.by_type("IfcWall")[:2]
        w2.GlobalId = w1.GlobalId
    got = _variant(sample, tmp_path, change)
    assert "used 2 times" in got["storey_naming"] and "used 2 times" in got["guid"]


def test_units_and_spatial_structure(sample, tmp_path):
    def change(m):
        for u in m.by_type("IfcSIUnit"):
            if u.UnitType == "LENGTHUNIT":
                u.Prefix = "CENTI"
        for b in m.by_type("IfcBuilding"):
            for rel in list(b.Decomposes):
                m.remove(rel)
            for rel in list(b.IsDecomposedBy):
                m.remove(rel)
            m.remove(b)
    got = _variant(sample, tmp_path, change)
    assert "metre or millimetre" in got["units"] and got["spatial_structure"] == "no IfcBuilding"


def test_schema_other_than_ifc4_is_an_error(tmp_path):
    import ifcopenshell
    import ifcopenshell.guid
    f = ifcopenshell.file(schema="IFC2X3")
    f.createIfcProject(ifcopenshell.guid.new(), Name="old")
    src = tmp_path / "old.ifc"; f.write(str(src))
    finding = next(x for x in check(src, []).findings if x.rule == "schema")
    assert finding.severity == "error"


# ---------- report and command line ----------
def test_report_lists_findings_and_escapes(sample, tmp_path):
    from ifcsg_precheck.report import render
    rep = check(sample, RULES)
    rep.findings[0].message = "<script>x</script>"
    page = render(rep, [{"pset": "SGPset_SlabDimension", "property": "Mark", "source": "Name"}])
    assert "<script>x" not in page and "&lt;script&gt;" in page
    assert "D-03" in page and "SGPset_SlabDimension" in page


def test_cli_sample_check_enrich(tmp_path, capsys):
    from ifcsg_precheck.cli import main
    rules = tmp_path / "r.json"
    rules.write_text(json.dumps(RULES), encoding="utf-8")
    model = tmp_path / "m.ifc"
    main(["sample", str(model)])
    main(["check", str(model), "--rules", str(rules), "--agency", "SCDF", "--json", str(tmp_path / "c.json"),
          "--html", str(tmp_path / "c.html")])
    out = capsys.readouterr().out
    summary = json.loads(out[out.index("{"):])
    assert summary["element_rule_pairs"] == 8                          # SCDF only: 4 doors x 2 rules
    assert json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    main(["enrich", str(model), str(tmp_path / "e.ifc"), "--rules", str(rules)])
    assert "1 values filled" in capsys.readouterr().out and (tmp_path / "e.ifc.log.csv").exists()
