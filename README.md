# ifcsg-precheck

This tool checks an IFC model against Singapore's IFC+SG requirements for CORENET X **before** submission. It fills in the properties that can be derived from data already in the model, and writes a report of what is still missing, grouped by agency and element.

The rules are generated from BCA's IFC+SG Industry Mapping (4 Dec 2025, 833 rows), which yields 1,456 rules; a rule is one combination of entity, sub type, property set, property and agency.

On two independently built models it raised the share of passing element-rule checks from 0% to 13.0% and 17.8%. The derived beam and slab sizes match the design values.

[docs/WORKFLOW.md](docs/WORKFLOW.md) shows where this fits in the gateway process (as-is vs to-be) and how it could be rolled out.

## What it checks

| Level | Checks |
|---|---|
| Model | this project's building-submission profile: schema (IFC4; IFC4X3 is a warning, anything else an error), one IfcProject, length unit metre/millimetre, IfcSite + IfcBuilding + storeys, storey names unique and set, storey elevation, IfcMapConversion presence, duplicate GlobalIds, a storey ancestor for each element (except openings and other feature elements) |
| IFC+SG mapping | applicable entity + effective PredefinedType, property set and property presence, value type (finite number / text / boolean), accepted values where the mapping gives a short fixed list |

The storey requirement is a **building profile**, not a universal IFC validity rule. Containment through a space or an assembled/nested element is accepted when it reaches an actual IfcBuildingStorey; belonging only to a building, site or detached assembly is flagged. A type object's defined PredefinedType takes precedence; an absent or NOTDEFINED type falls back to the occurrence. `*` subtypes require USERDEFINED and match the type's ElementType or the occurrence's ObjectType, respectively. A custom label cannot masquerade as an ordinary enum value. Numeric properties reject booleans, NaN and infinity.

## What it fills in (and logs)

It fills a value only when the value can be traced to data already in the model. Existing non-empty values, including inherited values, zero and false, are preserved; null and blank/whitespace text are treated as missing. Writes go to instance-owned property sets, splitting a shared set before editing it, so deriving one element's Mark cannot change another element or its type. Every filled value is written to a CSV log with the element's GlobalId and where the value came from. Subsequent runs skip these existing non-empty values; the output IFC and CSV files are still written.

| Property | Derived from |
|---|---|
| Slab `Thickness`, beam `Depth`/`Width`, column `Width`/`Breadth`, pile `Length` | the body geometry, measured on an oriented bounding box (principal axes), so a beam on a grade or with superelevation is measured square to its own axis |
| `Mark` | the first non-blank Tag or Name, preserving the selected value and recording which field supplied it |
| `MaterialGrade` | `Pset_ConcreteElementGeneral.StrengthClass`, written as the EN 206 pair (`C50` → `C50/60`) |
| `ConstructionMethod` | `Pset_ConcreteElementGeneral.CastingMethod` (in situ → `CIS`, precast → `PC`) |
| Slab `LoadBearing` | a boolean in `Pset_SlabCommon.LoadBearing`; null, text and numeric stand-ins are not converted to true/false |

## Results

The current recheck is in [reports/review-20261003/summary.json](reports/review-20261003/summary.json), with model, rule and source hashes plus dependency versions in [provenance.json](reports/review-20261003/provenance.json). The [original measurement](reports/summary.json) remains unchanged. Reproduce into a fresh output directory using the command below.

For a comparable rerun, match the recorded model/rule hashes and dependency versions rather than assuming today's minimum-version installation is identical. Source hashes record raw workspace bytes, including Windows line endings; elapsed times are environment-specific measurements, not a controlled speed comparison.

| Model | Elements | Element-rule checks | Pass before | Values filled | Pass after |
|---|---|---|---|---|---|
| [facade-bim](https://github.com/LUOaini1213/facade-bim) (IFC4, unitized curtain wall) | 859 | 208 | 0% | 18 | 13.0% |
| [bridge-bim](https://github.com/LUOaini1213/bridge-bim) (IFC 4.3, 12-span T-girder bridge) | 1,470 | 27,249 | 0% | 5,136 | 17.8% |
| `samples/sample_block.ifc` (generated, defects planted) | 10 | 191 | 9.9% | 1 | 10.5% |

- **Original validation of the derived sizes.** On all 120 T-girders of bridge-bim, depth came out at 2,000–2,001 mm and width at 1,850 mm; the design section is 2.00 m × 1.85 m. Taking the vertical extent along the world axis instead gave 2,015–2,553 mm, because the girders sit on a grade with superelevation. The facade-bim slabs came out at 250 mm, as set in that model's export script. The current fill logs reproduce the derived dimensions; this recheck does not repeat the independent design/world-axis comparison.
- **Remaining property gaps need review.** For bridge-bim, the largest remaining gaps are `SGPset_BeamReinforcement`, `SGPset_Beam` and `SGPset_SteelConnection`. For facade-bim, they are `SGPset_Slab` and `SGPset_SlabReinforcement`. These properties are missing from the required locations and are not filled by the supported derivations; a designer must establish the values or locate another reliable source.
- **The planted defects are all found.** In the sample model:
  - D-02 has FireRating "1 hr", while the mapping's values are "0.5"…"4" with the unit held separately;
  - D-03 has no ClearWidth;
  - D-04 has ClearWidth stored as the text "1000 mm";
  - W-X is not contained in a storey;
  - there is no georeference.
- **Why both real models start at 0%.** Neither was authored for CORENET X, and bridge-bim is infrastructure (IFC 4.3, no IfcBuilding), so the checker flags its schema and spatial structure as well. They are used because they are real, independently built models, not models written to pass.
- **Passing property checks is not overall model compliance.** The current recheck retains the original property pass rates and fill counts. Correct storey ancestry additionally flags 4 facade members and all 1,470 bridge elements under this building profile; this does not establish a defect in the bridge's structural design. Model-level findings are counted separately from the element-rule pass rate. The bridge is a cross-domain example, not evidence that the profile is valid for infrastructure or that the model is submission-ready.
- **Report counts are findings.** A component can fail several property rules, so a gap count can exceed the number of elements. Repeated model-level findings are grouped, with every GlobalId available in an expandable detail table. Custom rule identifiers are classified by their recorded origin rather than requiring a `CX` prefix.

Open a current example: [facade report](reports/review-20261003/facade_report.html), [bridge report](reports/review-20261003/bridge_report.html), or [sample report](reports/review-20261003/sample_report.html).

## Use

```bash
pip install -r requirements.txt
export PYTHONPATH=src

# 1. Download BCA's Industry Mapping xlsx from info.corenet.gov.sg (IFC+SG > Templates, Apps and More > IFC-SG Excel Mapping File)
python -m ifcsg_precheck.cli rules industry-mapping.xlsx          # writes rules/ifcsg_mapping.json

# 2. Check a model; optionally one agency only
python -m ifcsg_precheck.cli check model.ifc --html report.html --json findings.json
python -m ifcsg_precheck.cli check model.ifc --agency SCDF

# 3. Fill derivable properties, re-check, and write the log next to the output
python -m ifcsg_precheck.cli enrich model.ifc model_enriched.ifc --html after.html

# Demonstration model with planted defects
python -m ifcsg_precheck.cli sample samples/sample_block.ifc

# Preserve previous measurements, and record exact input/source fingerprints
python scripts/evaluate.py --output-dir reports/my-review --rules rules/ifcsg_mapping.json \
  facade=../facade-bim/model/facade_bim.ifc \
  bridge=../bridge-bim/model/bridge_bim.ifc sample=samples/sample_block.ifc
```

## Tests

`python -m pytest -q tests` checks real IFC type inheritance, spatial ancestry, shared property ownership, source-value types, idempotency, report counts, evaluation provenance and the original pipeline. Fixtures and hand-written rules keep this suite independent of BCA's file.

The 2026-10-03 local gate passed **122 tests**, the harness's **11 self-checks**, and **40/40 deliberate mutations**. The ownership regression also verifies that, after filling an instance's Mark, later changes to an unrelated inherited type property still reach that instance. GitHub Actions runs the full test and mutation gates on each push and PR.

`python tests/mutate.py` plants deliberate bugs in the checker, enrichment, mapping converter, report and command line. It first verifies the unmodified suite and each replacement's unique anchor and syntax. Only an actual pytest test failure counts as detection: collection/setup errors, crashes, timeouts and missing reports stop the run. Source bytes are restored even after failures, and each test process uses isolated bytecode. `python tests/mutate.py --self-test` checks the harness's failure and restoration paths. Run mutation checks exclusively: do not edit, import, test or serve the same source checkout concurrently.

## Data and terms

BCA's terms of use do not allow the Industry Mapping to be republished. This repository therefore contains the converter but not the mapping or the rules generated from it; both are git-ignored. The reports contain property-set and property names and the counts measured on the two models above.

## Limits

- **Values are not checked against the codes.** Checks cover the presence, type and format of IFC+SG data. Whether a door is wide enough, for example, is a code-compliance question for the agencies' own checkers.
- **Georeferencing is a presence check.** Finding an IfcMapConversion does not verify its coordinate reference system, SVY21 parameters or survey accuracy.
- **Accepted values are enforced only for short fixed lists.** Where the mapping gives a range or a note, the rule checks presence and type only.
- **IFC4X3 models are checked as they are.** The mapping is written for IFC4, so IFC 4.3 classes such as IfcBearing or IfcCourse match no rule.
