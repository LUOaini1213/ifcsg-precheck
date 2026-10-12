"""Reproduce a public, self-authored three-stage review example, without official mapping data."""
import argparse
import hashlib
import html
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ifcopenshell
import ifcopenshell.api as api
import numpy
from ifcsg_precheck.check import check
from ifcsg_precheck.enrich import enrich
from ifcsg_precheck.report import render
from ifcsg_precheck.units import TARGETS, make_unit, property_entity
from verify_report_demo import verify


def rules():
    # Independently authored acceptance examples, not rows from BCA's workbook.
    base = dict(entity="IfcSlab", predefined_type="FLOOR", severity="error")
    return [dict(base, id="DEMO-THICKNESS", agency="Demo structures", pset="SGPset_SlabDimension", property="Thickness", value_type="number", unit="m", min=.24, max=.26),
            dict(base, id="DEMO-MARK", agency="Demo coordination", pset="SGPset_SlabDimension", property="Mark", value_type="text"),
            dict(base, id="DEMO-METHOD", agency="Demo structures", pset="SGPset_Slab", property="ConstructionMethod", value_type="text", allowed_values=["CIS", "PC"]),
            dict(base, id="DEMO-LOAD", agency="Demo structures", pset="SGPset_Slab", property="LoadBearing", value_type="boolean"),
            dict(base, id="DEMO-REFERENCE", agency="Demo coordination", pset="Demo_Review", property="ReviewReference", value_type="text", severity="warning"),
            dict(base, id="DEMO-CLEARANCE", agency="Demo coordination", pset="Demo_Review", property="Clearance", value_type="number", unit="m")]


def stable_file(model, path):
    # Fixed authored identity and timestamps make the small demonstration byte-reproducible.
    # IfcOpenShell accumulates this IFC SET through a Python set. Its ordering
    # is semantically irrelevant but otherwise varies between fresh processes.
    for relation in model.by_type("IfcRelContainedInSpatialStructure"):
        relation.RelatedElements = sorted(relation.RelatedElements, key=lambda x: x.id())
    for item in sorted(model.by_type("IfcRoot"), key=lambda x: x.id()):
        item.GlobalId = ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL, f"ifcsg-authored-demo:{item.id()}").hex)
    model.header.file_name.name = Path(path).name
    model.header.file_name.time_stamp = "2026-10-12T00:00:00"
    model.header.file_name.author = ("ifcsg-precheck self-authored demonstration",)
    model.header.file_name.organization = ("Illustrative data only",)
    model.header.file_name.preprocessor_version = "IfcOpenShell 0.8.5"
    model.header.file_name.originating_system = "ifcsg-precheck report review demo"
    model.write(str(path))
    # The native STEP writer uses host line endings. Canonical LF applies only
    # to these new self-authored demo files, never to historical model assets.
    path = Path(path)
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def set_value(model, element, pset, name, value, measure="IfcLabel", unit=None):
    import ifcopenshell.util.element as uel
    existing = uel.get_psets(element, should_inherit=False).get(pset)
    ps = model.by_id(existing["id"]) if existing else api.run("pset.add_pset", model, product=element, name=pset)
    nominal = model.create_entity(measure, value) if value is not None else None
    api.run("pset.edit_pset", model, pset=ps, properties={name: {"NominalValue": nominal, "Unit": unit}}, should_purge=False)


def build_input(path):
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Authored review demonstration")
    project.UnitsInContext = model.create_entity("IfcUnitAssignment", Units=[make_unit(model, TARGETS["m"])])
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Demo site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Demo building")
    storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Demo L1")
    storey.Elevation = 0.
    for parent, child in ((project, site), (site, building), (building, storey)):
        api.run("aggregate.assign_object", model, products=[child], relating_object=parent)
    for index, name in enumerate(("S-ready", "S-derive", "S-deferred")):
        slab = api.run("root.create_entity", model, ifc_class="IfcSlab", name=name, predefined_type="FLOOR")
        slab.Tag = name
        api.run("spatial.assign_container", model, products=[slab], relating_structure=storey)
        representation = api.run("geometry.add_slab_representation", model, context=body, depth=.25,
                                 polyline=[(0., 0.), (2., 0.), (2., 3.), (0., 3.), (0., 0.)])
        api.run("geometry.assign_representation", model, product=slab, representation=representation)
        transform = numpy.eye(4); transform[0, 3] = index * 4.
        api.run("geometry.edit_object_placement", model, product=slab, matrix=transform)
        set_value(model, slab, "Pset_ConcreteElementGeneral", "CastingMethod", "INSITU")
        if name != "S-deferred":
            set_value(model, slab, "Pset_SlabCommon", "LoadBearing", True, "IfcBoolean")
        set_value(model, slab, "Demo_Review", "Clearance", .8,
                  "IfcReal" if name == "S-deferred" else "IfcLengthMeasure")
        if name == "S-ready":
            set_value(model, slab, "SGPset_SlabDimension", "Thickness", 250., "IfcLengthMeasure", make_unit(model, TARGETS["mm"]))
        elif name == "S-deferred":
            unknown = model.create_entity("IfcContextDependentUnit", Dimensions=model.create_entity("IfcDimensionalExponents", 1,0,0,0,0,0,0),
                                         UnitType="LENGTHUNIT", Name="Authored unknown scale")
            set_value(model, slab, "SGPset_SlabDimension", "Thickness", None, unit=unknown)
    stable_file(model, path)


def authored_review(src, dst):
    """Scripted decisions for illustrative inputs, never claimed as independent human labels."""
    model = ifcopenshell.open(str(src))
    decisions = []
    for element in model.by_type("IfcSlab"):
        set_value(model, element, "Demo_Review", "ReviewReference", "AUTHORED-DEMO-REVIEW")
        decisions.append(dict(guid=element.GlobalId, property="Demo_Review.ReviewReference",
                              decision="Authored reference supplied; not an official approval or a human annotation"))
        if element.Name == "S-deferred":
            set_value(model, element, "SGPset_SlabDimension", "Thickness", .25, "IfcLengthMeasure", make_unit(model, TARGETS["m"]))
            set_value(model, element, "Demo_Review", "Clearance", .8, "IfcLengthMeasure", make_unit(model, TARGETS["m"]))
            set_value(model, element, "SGPset_Slab", "LoadBearing", False, "IfcBoolean")
            decisions.append(dict(guid=element.GlobalId, property="Thickness / Clearance / LoadBearing",
                                  decision="Authored source confirms 0.25 m / 0.8 m / false; explicit typed values replace uncertain input"))
    stable_file(model, dst)
    return decisions


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def fingerprint(path, *, text=False):
    raw = path.read_bytes()
    if text: raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def source_hashes():
    paths = sorted((ROOT / "src/ifcsg_precheck").glob("*.py")) + sorted((ROOT / "src/ifcsg_precheck/report_assets").glob("*"))
    paths += [ROOT / "scripts/report_demo.py", ROOT / "scripts/verify_report_demo.py"]
    return {p.relative_to(ROOT).as_posix(): fingerprint(p, text=True) for p in paths}


def decorate(page, stage, summaries, decisions):
    nav = '<nav aria-label="Review stages"><a href="before.html">1 · Check input</a> <a href="index.html">2 · Derive and recheck</a> <a href="reviewed.html">3 · Authored review and recheck</a></nav>'
    links = " ".join(f'<a href="{name}" download>{label}</a>' for name, label in
                     (("before.ifc", "Input IFC"), ("derived.ifc", "Derived IFC"), ("reviewed.ifc", "Reviewed IFC"),
                      ("authored_rules.json", "Authored rules"), ("derivations.csv", "Fill log"), ("manifest.json", "Hashes and verification")))
    cells = "".join(f'<tr><th scope="row">{html.escape(label)}</th><td>{r["passed_pairs"]} / {r["element_rule_pairs"]}</td><td>{r["errors"]}</td><td>{r["warnings"]}</td><td>{r["unit_unverified_pairs"]}</td></tr>'
                    for label, r in summaries.items())
    introduction = (nav + '<section class="demo-intro"><h2>Self-authored IFC review example</h2>'
                   '<p>Three slabs and six illustrative rules. Agencies labelled Demo are fictional review groups. '
                   'This static replay uses no official mapping rows and processes no visitor files. The final review is a scripted authored example, not independent human annotation or regulatory approval.</p>'
                   f'<p><strong>Current stage: {html.escape(stage)}</strong> · <a href="#review">Review all findings ↓</a></p><div class="w"><table><thead><tr><th>Stage</th><th>Passing property checks</th><th>Errors</th><th>Warnings</th><th>Unit unverified</th></tr></thead><tbody>{cells}</tbody></table></div>'
                   '<p>1. Locate a finding by GlobalId. 2. Inspect the original typed value, explicit unit and fill trace. '
                   '3. Resolve uncertain sources in the authoring model, then export and recheck. Unit-unverified pairs stay in the 18-check denominator and are not passed. Even the final example retains a georeference warning.</p>'
                   '<p class="downloads">' + links + '</p><p><a href="https://github.com/LUOaini1213/ifcsg-precheck">Source repository</a> · '
                   '<a href="https://github.com/LUOaini1213/ifcsg-precheck/blob/main/docs/REPORT_REVIEW.md">Reproduction and boundaries</a></p></section>')
    if stage == "Authored review":
        introduction += '<h2>Scripted authored review decisions</h2><div class="w"><table><thead><tr><th>GlobalId</th><th>Property</th><th>Decision / source</th></tr></thead><tbody>'
        introduction += "".join('<tr>' + "".join('<td>' + html.escape(r[key]) + '</td>' for key in ("guid", "property", "decision")) + '</tr>' for r in decisions)
        introduction += '</tbody></table></div>'
    return page.replace('<main>', '<main>' + introduction, 1)


def generate(directory):
    directory.mkdir(parents=True, exist_ok=True)
    chosen = rules()
    write_json(directory / "authored_rules.json", chosen)
    build_input(directory / "before.ifc")
    before = check(directory / "before.ifc", chosen)
    pending = []
    rows = enrich(directory / "before.ifc", directory / "derived.ifc", directory / "derivations.csv", rules=chosen, pending=pending)
    stable_file(ifcopenshell.open(str(directory / "derived.ifc")), directory / "derived.ifc")
    derived = check(directory / "derived.ifc", chosen)
    decisions = authored_review(directory / "derived.ifc", directory / "reviewed.ifc")
    reviewed = check(directory / "reviewed.ifc", chosen)
    verification = verify(directory, rows)
    reports = {"Before": before, "Derived": derived, "Authored review": reviewed}
    summaries = {name: dict(rep.summary(), passed_pairs=rep.passed_pairs) for name, rep in reports.items()}
    source = source_hashes()
    inputs = {name: fingerprint(directory / name) for name in ("before.ifc", "authored_rules.json")}
    context = dict(profile="Self-authored illustrative rules; no official mapping data", input_sha256=inputs,
                   source_sha256=source, source_hash_policy="UTF-8 source CRLF normalized to LF; IFC and outputs raw bytes", independent_reopen=verification)
    for label, rep, filename in (("Before", before, "before.html"), ("Derived", derived, "index.html"), ("Authored review", reviewed, "reviewed.html")):
        writes = rows if label != "Before" else []
        deferred = pending if label == "Derived" else []
        stage_context = dict(context, stage=label, authored_review_decisions=decisions if label == "Authored review" else [])
        page = render(rep, writes, "IFC review · " + label, deferred, rules=chosen, context=stage_context)
        (directory / filename).write_text(decorate(page, label, summaries, decisions), encoding="utf-8", newline="\n")
        write_json(directory / ("before.json" if label == "Before" else "derived.json" if label == "Derived" else "reviewed.json"), rep.to_json())
    write_json(directory / "decisions.json", decisions)
    write_json(directory / "independent_reopen.json", verification)
    # Enrich writes the pending sidecar next to its actual log.
    write_json(directory / "manifest.json", dict(context, summaries=summaries, derivations=len(rows), deferred=len(pending),
               environment=dict(python="3.11", ifcopenshell=ifcopenshell.version, numpy=numpy.__version__),
               output_sha256={p.name: fingerprint(p) for p in sorted(directory.iterdir()) if p.is_file() and p.name != "manifest.json"}))
    return summaries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "demos/report-review")
    parser.add_argument("--check", action="store_true", help="Independently rerun and compare every published demo byte")
    args = parser.parse_args(argv)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="ifc-review-demo-") as scratch:
            fresh = Path(scratch)
            generate(fresh)
            expected = {p.name: p.read_bytes() for p in fresh.iterdir() if p.is_file()}
            actual = {p.name: p.read_bytes() for p in args.output_dir.iterdir() if p.is_file()}
            if actual != expected:
                changed = sorted(k for k in actual.keys() | expected.keys() if actual.get(k) != expected.get(k))
                raise SystemExit("Demo differs from current inputs/source: " + ", ".join(changed))
        print("PASS: authored demo independently reproduced; every file and source/input fingerprint matches")
    else:
        print(json.dumps(generate(args.output_dir), indent=2))


if __name__ == "__main__":
    main()
