# ifcsg-precheck

[![tests](https://github.com/LUOaini1213/ifcsg-precheck/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/LUOaini1213/ifcsg-precheck/actions/workflows/ci.yml) [![report-pages](https://github.com/LUOaini1213/ifcsg-precheck/actions/workflows/report-pages.yml/badge.svg?branch=main)](https://github.com/LUOaini1213/ifcsg-precheck/actions/workflows/report-pages.yml)

A Python/ifcopenshell tool that checks an IFC model against Singapore's IFC+SG requirements for CORENET X **before** submission, fills in properties that can be derived from data already in the model (each fill logged with its source), and reports what is still missing by agency and element.

- **Rules:** generated locally from BCA's IFC+SG Industry Mapping (4 Dec 2025): 833 rows expand to 1,456 rules (entity × sub type × property set × property × agency). The workbook and the generated rules are not redistributed.
- **Result:** on two independently built public models, auto-fill raised the share of passing element-rule checks from 0% to **13.0%** (facade-bim, 27 of 208) and **17.8%** (bridge-bim, 4,848 of 27,249) in the 2026-10-12 unit-aware run. Measured on their principal axes, the 120 bridge T-girders come out 2,000–2,001 mm deep (design 2.00 m); the world vertical extent would give 2,015–2,553 mm.
- **Limits:** presence, type, format and unit checks only, not code compliance; georeferencing is a presence check; the bridge is IFC 4.3 infrastructure checked under a building profile. A passing rate is not submission readiness.
- **Try it without the BCA workbook:** open the [live authored review demo](https://luoaini1213.github.io/ifcsg-precheck/), or run `python -m ifcsg_precheck.cli check samples/sample_block.ifc --rules demos/report-review/authored_rules.json --html out.html` (six illustrative rules, no official mapping data; see [Use](#use)).

[docs/WORKFLOW.md](docs/WORKFLOW.md) shows where this fits in the gateway process (as-is vs to-be) and how it could be rolled out. The [self-authored review demonstration](demos/report-review/index.html) shows **check → derive → recheck → authored review** on three small IFCs, with typed unit evidence, filters and JSON/CSV downloads; the [review guide](docs/REPORT_REVIEW.md) explains reproduction, static publication and the [2026-10-12 release receipt](docs/REPORT_REVIEW.md#2026-10-12-release). That example contains no official mapping rows; its illustrative groups and scripted decisions do not claim regulatory approval or independent human annotation.

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

The current measurement is the 2026-10-12 unit-aware run in [reports/review-20261012-units](reports/review-20261012-units/README.md) (checker commit `79ae5f9`; model, rule and source hashes plus dependency versions in its [provenance.json](reports/review-20261012-units/provenance.json)). Later code changes (PR #4 and the 2026-11-03 review fixes) touch only the command line's path and rule-presence guards, not the checks or derivations. A check is one applicable element × rule pair; it passes when the property is present with the expected type, value and verified unit.

| Model (commit) | Elements | Element-rule checks | Pass before | Values filled | Pass after |
|---|---:|---:|---:|---:|---:|
| [facade-bim](https://github.com/LUOaini1213/facade-bim/tree/3c88e925a67d443ef879dce15b9e1ee837354375) `3c88e925` (IFC4, unitized curtain wall) | 8,323 | 208 | 0 / 208 (0%) | 18 | 27 / 208 (13.0%) |
| [bridge-bim](https://github.com/LUOaini1213/bridge-bim/tree/b6456b344b09a92620cc5d4a4cfb2a3be963b147) `b6456b34` (IFC 4.3, 12-span T-girder bridge) | 1,470 | 27,249 | 0 / 27,249 (0%) | 4,848 | 4,848 / 27,249 (17.8%) |
| `samples/sample_block.ifc` (generated, defects planted) | 10 | 191 | 7 / 191 (3.7%) | 1 | 8 / 191 (4.2%) |

`tests/test_readme_numbers.py` pins every cell of this table, and of the history table below, to the cited `summary.json`. The sample's lower rate than in earlier runs comes from 12 `IfcReal` length values without an explicit unit, which the unit-aware checker no longer counts as verified; the sample file itself is unchanged.

- **Derived sizes match the design.** On all 120 T-girders of bridge-bim `b6456b34`, the principal-axis measurement used by the enrichment gives a depth of 2,000–2,001 mm and a width of 1,850 mm; the design section is 2.00 m × 1.85 m. The vertical extent along the world axis is 2,015–2,553 mm, because the girders sit on a grade with superelevation. These figures are in [girder_axes.json](reports/girder-axes-20261108/girder_axes.json), produced by `scripts/girder_axes.py` (re-measured 2026-11-08 on the pinned model, SHA-256 recorded; the original 2026-09-27 comparison kept no artifact or model hash). The mechanism is pinned by a pitched-beam regression test in `tests/test_precheck.py`. The nine facade-bim slab `Thickness` fills are all 250 mm (unit evidence in the facade report).
- **Remaining property gaps need review.** For bridge-bim, the largest remaining gaps are `SGPset_BeamReinforcement`, `SGPset_Beam` and `SGPset_SteelConnection`. For facade-bim, they are `SGPset_Slab` and `SGPset_SlabReinforcement`. These properties are missing from the required locations and are not filled by the supported derivations; a designer must establish the values or locate another reliable source.
- **The planted defects are all found.** In the sample model:
  - D-02 has FireRating "1 hr", while the mapping's values are "0.5"…"4" with the unit held separately;
  - D-03 has no ClearWidth;
  - D-04 has ClearWidth stored as the text "1000 mm";
  - W-X is not contained in a storey;
  - there is no georeference.
- **Why both real models start at 0%.** Neither was authored for CORENET X, and bridge-bim is infrastructure (IFC 4.3, no IfcBuilding), so the checker flags its schema and spatial structure as well. They are used because they are real, independently built models, not models written to pass.
- **Passing property checks is not overall model compliance.** Storey ancestry, added in the 2026-10-03 recheck, flags 4 facade members and all 1,470 bridge elements under this building profile; this does not establish a defect in the bridge's structural design. Model-level findings are counted separately from the element-rule pass rate. The bridge is a cross-domain example, not evidence that the profile is valid for infrastructure or that the model is submission-ready.
- **Report counts are findings.** A component can fail several property rules, so a gap count can exceed the number of elements. Repeated model-level findings are grouped, with every GlobalId available in an expandable detail table. Custom rule identifiers are classified by their recorded origin rather than requiring a `CX` prefix.

Open the current reports: [facade](reports/review-20261012-units/facade_report.html), [bridge](reports/review-20261012-units/bridge_report.html), [sample](reports/review-20261012-units/sample_report.html).

### History

Earlier runs are kept unchanged. The 2026-10-03 model hashes in its provenance differ from the pinned commits above, and the original run recorded no hashes, so neither is a before/after comparison with the current table. Source hashes record raw workspace bytes, including Windows line endings; elapsed times are local measurements, not a speed comparison.

| Run | Checker | facade-bim: elements, checks, filled, pass after | bridge-bim: elements, checks, filled, pass after | sample: pass before → after |
|---|---|---|---|---|
| [Original](reports/summary.json), 2026-09-27 | `edc69b2` | 859, 208, 18, 13.0% | 1,470, 27,249, 5,136, 17.8% | 9.9% → 10.5% |
| [Recheck](reports/review-20261003/summary.json), 2026-10-03 ([provenance](reports/review-20261003/provenance.json)) | `b06227f` | 859, 208, 18, 13.0% | 1,470, 27,249, 5,136, 17.8% | 9.9% → 10.5% |

The 2026-10-03 recheck kept the original property pass rates and fill counts and added the storey-ancestry findings. The 2026-10-12 bridge fill count (4,848 vs 5,136) also uses a newer model file and must not be attributed solely to unit handling.

## Use

Python 3.11 (the version CI and the recorded runs use). The commands use Git Bash/Linux syntax; in PowerShell set `$env:PYTHONPATH = "src"` instead of `export`.

```bash
pip install -r requirements.txt
export PYTHONPATH=src

# Try it without the BCA workbook: six illustrative rules on the planted-defect sample
python -m ifcsg_precheck.cli check samples/sample_block.ifc --rules demos/report-review/authored_rules.json --html out.html

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
```

`check` and `enrich` exit with status 2 if no rule file is found (`rules/` is empty until step 1), if the rule files are empty, or if `--agency` matches no rule, instead of reporting a near-clean model with zero rules applied.

To reproduce the measurements, clone the two public models next to this repository at the pinned commits (their `.gitattributes` keep the IFC bytes identical on Windows and Linux), then match the recorded hashes and dependency versions:

```bash
git clone https://github.com/LUOaini1213/facade-bim ../facade-bim
git -C ../facade-bim checkout 3c88e925a67d443ef879dce15b9e1ee837354375
git clone https://github.com/LUOaini1213/bridge-bim ../bridge-bim
git -C ../bridge-bim checkout b6456b344b09a92620cc5d4a4cfb2a3be963b147

# Needs rules/ifcsg_mapping.json from step 1; writes into a fresh directory
python scripts/evaluate.py --output-dir reports/my-review --rules rules/ifcsg_mapping.json \
  facade=../facade-bim/model/facade_bim.ifc \
  bridge=../bridge-bim/model/bridge_bim.ifc sample=samples/sample_block.ifc

# No workbook needed: principal-axis vs world-axis girder depth, compared with the committed file
python scripts/girder_axes.py ../bridge-bim/model/bridge_bim.ifc \
  --out reports/girder-axes-20261108/girder_axes.json --check
```

Use separate paths for source models, mapping/rule inputs, enriched models and reports.
The CLI rejects overlapping inputs and outputs (including symbolic and hard links)
before writing any output; enrichment logs and pending-review sidecars are checked too.
Existing reports at independent paths can still be replaced normally.

## Tests

```bash
pip install -r requirements-ci.txt
python -m pytest -q tests
PYTHONPATH=src python scripts/report_demo.py --check
python tests/mutate.py --self-test
python tests/mutate.py
```

The pytest suite checks real IFC type inheritance, spatial ancestry, shared property ownership, source-value types, units, idempotency, report counts, evaluation provenance, CLI path and rule guards, the README's result numbers and the original pipeline. Fixtures and hand-written rules keep it independent of BCA's file. On Windows without symlink privilege, the symlink-alias cases are skipped. `report_demo.py --check` regenerates the authored demo and compares every byte and fingerprint.

[GitHub Actions](https://github.com/LUOaini1213/ifcsg-precheck/actions/workflows/ci.yml) runs the full pytest suite, the demo check, the mutation harness self-test and every deliberate mutation in `tests/mutate.py` on each push and PR (Ubuntu), plus pytest and the demo check on Windows. Counts recorded at each dated review stay in that review's own record ([2026-10-12 units](reports/review-20261012-units/README.md), [2026-10-12 release](docs/REPORT_REVIEW.md#2026-10-12-release)); the latest run log has the current counts.

`python tests/mutate.py` plants deliberate bugs in the checker, enrichment, mapping converter, report and command line. It first verifies the unmodified suite and each replacement's unique anchor and syntax. Only an actual pytest test failure counts as detection: collection/setup errors, crashes, timeouts and missing reports stop the run. Source bytes are restored even after failures, and each test process uses isolated bytecode. `python tests/mutate.py --self-test` checks the harness's failure and restoration paths. Run mutation checks exclusively: do not edit, import, test or serve the same source checkout concurrently.

## Data and terms

BCA's terms of use do not allow the Industry Mapping to be republished. This repository therefore contains the converter but not the mapping or the rules generated from it; both are git-ignored. The reports contain property-set and property names and the counts measured on the two models above.

## Limits

- **Values are not checked against the codes.** Checks cover the presence, type and format of IFC+SG data. Whether a door is wide enough, for example, is a code-compliance question for the agencies' own checkers.
- **Georeferencing is a presence check.** Finding an IfcMapConversion does not verify its coordinate reference system, SVY21 parameters or survey accuracy.
- **Accepted values are enforced only for short fixed lists.** Where the mapping gives a range or a note, the rule checks presence and type only.
- **IFC4X3 models are checked as they are.** The mapping is written for IFC4, so IFC 4.3 classes such as IfcBearing or IfcCourse match no rule.
