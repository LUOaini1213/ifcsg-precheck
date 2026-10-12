"""Report controls expose all evidence without altering checker metrics or source identities."""
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from ifcsg_precheck.check import Finding, Report
from ifcsg_precheck.report import render, review_rows
from report_demo import generate, stable_file
from verify_report_demo import verify
from build_report_pages import PUBLIC_FILES, stage


class ReviewHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.controls, self.scripts = [], {}, []
        self.data = ""
        self.in_data = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and "data-kind" in attrs:
            self.rows.append(attrs)
        if attrs.get("id", "").startswith("filter-"):
            self.controls[attrs["id"]] = attrs
        if tag == "script":
            self.scripts.append(attrs)
            self.in_data = attrs.get("id") == "review-data"

    def handle_data(self, value):
        if self.in_data: self.data += value

    def handle_endtag(self, tag):
        if tag == "script": self.in_data = False


def test_complete_findings_beyond_top50_and_global_metrics_are_preserved():
    report = Report("model.ifc", "IFC4", 120,
                    [Finding("custom", "error", "Pset has no Width", f"g-{i}", "IfcBeam", "Beam", "Demo", "mapping") for i in range(120)],
                    rules_applied=1, element_rule_pairs=120, passed_pairs=0)
    original = report.to_json()
    rules = [dict(id="custom", pset="Pset", property="Width", agency="Demo")]
    page = render(report, rules=rules)
    parsed = ReviewHTML(); parsed.feed(page)
    data = json.loads(parsed.data)
    assert report.to_json() == original
    assert data["report"] == json.loads(json.dumps(original))
    assert len(parsed.rows) == len(data["review_records"]) == 120
    assert {r["data-guid"] for r in parsed.rows} == {f"g-{i}" for i in range(120)}
    assert all(r["data-property"] == "Pset.Width" for r in parsed.rows)
    assert set(parsed.controls) == {"filter-agency", "filter-severity", "filter-status", "filter-guid", "filter-property"}
    assert 'aria-live="polite"' in page and 'type="reset"' in page and 'scope="col"' in page


def test_hostile_ifc_text_cannot_escape_attributes_tables_or_json_script():
    hostile = '\" onfocus=\"alert(1)\"><img src=x onerror=alert(1)></script><script>alert(2)</script>&\u2028'
    report = Report(hostile, "IFC4", 1, [Finding("rule", "error", hostile, hostile, "IfcBeam", hostile, hostile, "mapping")])
    parsed = ReviewHTML(); page = render(report, title=hostile); parsed.feed(page)
    assert len(parsed.scripts) == 2
    assert all("onfocus" not in attrs for attrs in parsed.rows)
    assert '<img src=x' not in page and '</script><script>alert' not in page
    assert json.loads(parsed.data)["report"] == json.loads(json.dumps(report.to_json()))
    assert parsed.rows[0]["data-guid"] == hostile


def test_unit_derivation_and_deferred_evidence_keep_full_trace_and_single_count():
    report = Report("model.ifc", "IFC4", 1, unit_results=[dict(guid="g", pset="P", property="Width", status="verified",
                      raw_value=250., measure_type="IfcLengthMeasure", source_unit="MILLI METRE", target_unit="m", normalized_value=.25)])
    rules = [dict(id="a", pset="P", property="Width", agency="Demo A"), dict(id="b", pset="P", property="Width", agency="Demo B")]
    written = dict(guid="g", pset="P", property="Width", source="geometry", value=.25, source_value_si_m=.25, conversion_factor=1.)
    pending = dict(guid="h", pset="P", property="Width", reason="unknown unit")
    rows = review_rows(report, [written], [pending], rules)
    assert len(rows) == 3
    assert [r["kind"] for r in rows] == ["unit", "derived", "deferred"]
    assert rows[0]["agency"] == "Demo A; Demo B"
    assert rows[1]["evidence"] == written and rows[2]["evidence"] == pending
    assert [r["status"] for r in rows] == ["verified", "auto-filled", "deferred"]


def test_unverified_finding_and_unit_share_review_status_without_changing_raw_evidence():
    raw = dict(guid="g", pset="P", property="Width", status="unverified", reason="generic scalar has no unit",
               raw_value=.8, measure_type="IfcReal", source_unit="", target_unit="m", normalized_value=None)
    report = Report("model.ifc", "IFC4", 1,
                    [Finding("width", "warning", "P.Width unit unverified: generic scalar has no unit", "g", "IfcSlab", "S", "Demo", "mapping")],
                    unit_results=[raw])
    original = report.to_json()
    rows = review_rows(report, rules=[dict(id="width", pset="P", property="Width", agency="Demo")])
    assert [r["status"] for r in rows] == ["unit-unverified", "unit-unverified"]
    assert rows[1]["evidence"]["status"] == "unverified"
    assert report.to_json() == original and report.unit_results[0]["status"] == "unverified"


def test_real_authored_demo_pipeline_and_independent_export_readback(tmp_path):
    summaries = generate(tmp_path / "demo")
    assert [s["passed_pairs"] for s in summaries.values()] == [3, 12, 18]
    assert all(s["element_rule_pairs"] == 18 for s in summaries.values())
    assert [s["unit_unverified_pairs"] for s in summaries.values()] == [1, 1, 0]
    assert summaries["Authored review"]["warnings"] == 1  # georeference still needs review
    manifest = json.loads((tmp_path / "demo/manifest.json").read_text(encoding="utf-8"))
    assert manifest["derivations"] == 9 and manifest["deferred"] == 1
    verification = manifest["independent_reopen"]
    assert verification["verified_geometry_writes"][0]["physical_si_m"] == .25
    assert verification["preserved_explicit_mm_override"] and verification["authored_review_typed_values_verified"]
    assert "src/ifcsg_precheck/report_assets/review.js" in manifest["source_sha256"]
    assert "scripts/verify_report_demo.py" in manifest["source_sha256"]
    files = stage(tmp_path / "demo", tmp_path / "public")
    assert set(files) == PUBLIC_FILES | {".nojekyll"}
    assert all((tmp_path / "public" / name).is_file() for name in files)
    assert not (tmp_path / "public/src").exists()
    # Fresh STEP readback rejects a real typed-write regression, even if the
    # nominal numeric value still looks correct in a report.
    import ifcopenshell
    from ifcsg_precheck.units import property_entity
    original_input = (tmp_path / "demo/before.ifc").read_bytes()
    assert b"\r\n" not in original_input
    unordered = ifcopenshell.open(str(tmp_path / "demo/before.ifc"))
    for relation in unordered.by_type("IfcRelContainedInSpatialStructure"):
        relation.RelatedElements = tuple(reversed(relation.RelatedElements))
    stable_file(unordered, tmp_path / "demo/before.ifc")
    assert (tmp_path / "demo/before.ifc").read_bytes() == original_input
    parsed = ReviewHTML(); parsed.feed((tmp_path / "demo/index.html").read_text(encoding="utf-8"))
    written = json.loads(parsed.data)["derived"]
    exported = ifcopenshell.open(str(tmp_path / "demo/derived.ifc"))
    element = next(e for e in exported.by_type("IfcSlab") if e.Name == "S-derive")
    prop, _ = property_entity(element, "SGPset_SlabDimension", "Thickness")
    prop.NominalValue = exported.create_entity("IfcReal", .25)
    exported.write(str(tmp_path / "demo/derived.ifc"))
    with pytest.raises(ValueError, match="IFC measure type"):
        verify(tmp_path / "demo", written)
    # A forged index/body and an unexpected private file cannot be published.
    (tmp_path / "demo/index.html").write_text("tampered")
    with pytest.raises(ValueError, match="fingerprints"):
        stage(tmp_path / "demo", tmp_path / "other")
    (tmp_path / "demo/private.xlsx").write_bytes(b"private")
    with pytest.raises(ValueError, match="allowlist"):
        stage(tmp_path / "demo", tmp_path / "other")


def test_staging_never_overwrites_existing_directory(tmp_path):
    output = tmp_path / "public"; output.mkdir()
    (output / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="empty"):
        stage(tmp_path / "source", output)
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"
