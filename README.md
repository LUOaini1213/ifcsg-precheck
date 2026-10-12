# ifcsg-precheck

This tool checks an IFC model against Singapore's IFC+SG requirements for CORENET X **before** submission. It fills in the properties that can be derived from data already in the model, and writes a report of what is still missing, grouped by agency and element.

The rules are generated from BCA's IFC+SG Industry Mapping (4 Dec 2025, 833 rows), which yields 1,456 rules; a rule is one combination of entity, sub type, property set, property and agency.

The historical measurements on two independently built models raised the share of passing element-rule checks from 0% to 13.0% and 17.8%. The derived beam and slab sizes match the design values. A separate [unit-semantics review](reports/review-20261012-units/README.md) records the current checker and typed IFC writes; the historical reports remain unchanged.

[docs/WORKFLOW.md](docs/WORKFLOW.md) shows where this fits in the gateway process (as-is vs to-be) and how it could be rolled out.

## What it checks

| Level | Checks |
|---|---|
| Model | this project's building-submission profile: schema (IFC4; IFC4X3 is a warning, anything else an error), one IfcProject, length unit metre/millimetre, IfcSite + IfcBuilding + storeys, storey names unique and set, storey elevation, IfcMapConversion presence, duplicate GlobalIds, a storey ancestor for each element (except openings and other feature elements) |
| IFC+SG mapping | applicable entity + effective PredefinedType, property set and property presence, value type (finite number / text / boolean), accepted values where the mapping gives a short fixed list, physical unit dimensions and normalization where the source is verifiable |

The storey requirement is a **building profile**, not a universal IFC validity rule. Containment through a space or an assembled/nested element is accepted when it reaches an actual IfcBuildingStorey; belonging only to a building, site or detached assembly is flagged. A type object's defined PredefinedType takes precedence; an absent or NOTDEFINED type falls back to the occurrence. `*` subtypes require USERDEFINED and match the type's ElementType or the occurrence's ObjectType, respectively. A custom label cannot masquerade as an ordinary enum value. Numeric properties reject booleans, NaN and infinity.

Unit checks retain the original IFC measure type and explicit property `Unit`, including inherited properties. An explicit unit legally overrides the project unit. Without one, only the measure type's natural physical dimension selects a project unit: an `IfcInteger` or `IfcReal` does not acquire a length/force/pressure unit merely because the mapping requests it. Values are normalized to the mapping target before numeric bounds are applied. Missing, ambiguous, unknown or incompatible source units produce a **unit-unverified warning** and are excluded from the passed pairs; this is a review state, not a finding of regulatory noncompliance.

The observed catalogue supports `mm`, `m`, `m2`, `m3`, `kN`, `kPa`, `hr`, `L`, `L/s` and `tonnes`, using declared SI prefixes, conversion factors and derived-unit exponents. Mapping `Label` fields with unit qualifiers such as `hr` remain literal strings; `"0.5"` is not converted into a floating-point time. `SHD m` requires verified datum information and is left unverified. Context-dependent, offset and other unsupported units require review. The [aggregate catalogue](reports/review-20261012-units/unit_catalog.json) records the local official workbook's SHA and type/unit counts, without publishing its rows or generated rules.

These semantics follow the [IFC4 single-value property definition](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcpropertyresource/lexical/ifcpropertysinglevalue.htm), [SI units](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcmeasureresource/lexical/ifcsiunit.htm), [conversion-based units](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcmeasureresource/lexical/ifcconversionbasedunit.htm) and [derived units](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/ADD2_TC1/HTML/schema/ifcmeasureresource/lexical/ifcderivedunit.htm). The [official mapping page](https://info.corenet.gov.sg/ifc-sg/requirements---submission/ifc-sg-excel-mapping-file) identifies the 4 December 2025 workbook and its companion references; this tool does not implement a complete regulatory check.

## What it fills in (and logs)

It fills a value only when the value can be traced to data already in the model. Existing non-empty values, including inherited values, zero and false, are preserved; null and blank/whitespace text are treated as missing. Writes go to instance-owned property sets, splitting a shared set before editing it, so deriving one element's Mark cannot change another element or its type. Every filled value is written to a CSV log with the element's GlobalId and where the value came from. Subsequent runs skip these existing non-empty values; the output IFC and CSV files are still written.

| Property | Derived from |
|---|---|
| Slab `Thickness`, beam `Depth`/`Width`, column `Width`/`Breadth`, pile `Length` | the body geometry, measured on an oriented bounding box (principal axes), so a beam on a grade or with superelevation is measured square to its own axis |
| `Mark` | the first non-blank Tag or Name, preserving the selected value and recording which field supplied it |
| `MaterialGrade` | `Pset_ConcreteElementGeneral.StrengthClass`, written as the EN 206 pair (`C50` → `C50/60`) |
| `ConstructionMethod` | `Pset_ConcreteElementGeneral.CastingMethod` (in situ → `CIS`, precast → `PC`) |
| Slab `LoadBearing` | a boolean in `Pset_SlabCommon.LoadBearing`; null, text and numeric stand-ins are not converted to true/false |

Geometry is interpreted in SI metres only after its project length unit is verified. Dimensional fills use the mapping's length target, writing an `IfcLengthMeasure` with an explicit property-local unit and recording it in the CSV. The derivation retains its existing nearest-millimetre rounding; the CSV records that source value in metres, with `source_value_si_m * conversion_factor == value`. A valid unit on an existing blank property is preserved. Unknown source/target units, incompatible dimensions or unreliable geometry are not filled; their reasons are written to `<log>.pending.json` and the HTML report. Project units are not rewritten. The direct Python API without `rules=` retains its documented millimetre profile; CLI and evaluation use the supplied mapping rules.

## Results

The 2026-10-03 recheck is in [reports/review-20261003/summary.json](reports/review-20261003/summary.json), with model, rule and source hashes plus dependency versions in [provenance.json](reports/review-20261003/provenance.json). These and the [original measurement](reports/summary.json) remain unchanged. The new unit-aware evaluation is published separately in [reports/review-20261012-units](reports/review-20261012-units/README.md). Reproduce into a fresh output directory using the command below.

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
- **Passing property checks is not overall model compliance.** The 2026-10-03 recheck retained the original property pass rates and fill counts. Correct storey ancestry additionally flagged 4 facade members and all 1,470 bridge elements under this building profile; this does not establish a defect in the bridge's structural design. Model-level findings are counted separately from the element-rule pass rate. The bridge is a cross-domain example, not evidence that the profile is valid for infrastructure or that the model is submission-ready. The separate unit-aware review reports its actual results and exclusions.
- **Report counts are findings.** A component can fail several property rules, so a gap count can exceed the number of elements. Repeated model-level findings are grouped, with every GlobalId available in an expandable detail table. Custom rule identifiers are classified by their recorded origin rather than requiring a `CX` prefix.

Open a current example: [facade report](reports/review-20261003/facade_report.html), [bridge report](reports/review-20261003/bridge_report.html), or [sample report](reports/review-20261003/sample_report.html).

## Use

```bash
pip install -r requirements.txt
export PYTHONPATH=src

# 1. Download BCA's Industry Mapping xlsx from info.corenet.gov.sg (IFC+SG > Templates, Apps and More > IFC-SG Excel Mapping File)
python -m ifcsg_precheck.cli rules industry-mapping.xlsx          # writes rules/ifcsg_mapping.json
python scripts/unit_catalog.py industry-mapping.xlsx --out reports/my-review/unit_catalog.json

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

The 2026-10-12 unit-semantics offline gate passed **175 tests**, **11 harness self-checks**, and **55/55 mutations** (the original 40 plus 15 unit/trace defects). Its separate report records the exact new inputs and exported-file verification; no historical measurement was overwritten.

`python tests/mutate.py` plants deliberate bugs in the checker, enrichment, mapping converter, report and command line. It first verifies the unmodified suite and each replacement's unique anchor and syntax. Only an actual pytest test failure counts as detection: collection/setup errors, crashes, timeouts and missing reports stop the run. Source bytes are restored even after failures, and each test process uses isolated bytecode. `python tests/mutate.py --self-test` checks the harness's failure and restoration paths. Run mutation checks exclusively: do not edit, import, test or serve the same source checkout concurrently.

## Data and terms

BCA's terms of use do not allow the Industry Mapping to be republished. This repository therefore contains the converter but not the mapping or the rules generated from it; both are git-ignored. The reports contain property-set and property names and the counts measured on the two models above.

## Limits

- **Values are not checked against the codes.** Checks cover the presence, type and format of IFC+SG data. Whether a door is wide enough, for example, is a code-compliance question for the agencies' own checkers.
- **Georeferencing is a presence check.** Finding an IfcMapConversion does not verify its coordinate reference system, SVY21 parameters or survey accuracy.
- **Accepted values are enforced only for short fixed lists.** Where the mapping gives a range or a note, the rule checks presence and type only.
- **IFC4X3 models are checked as they are.** The mapping is written for IFC4, so IFC 4.3 classes such as IfcBearing or IfcCourse match no rule.
