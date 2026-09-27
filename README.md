# ifcsg-precheck

This tool checks an IFC model against Singapore's IFC+SG requirements for CORENET X **before** submission. It fills in the properties that can be derived from data already in the model, and writes a report of what is still missing, grouped by agency and element.

The rules are generated from BCA's IFC+SG Industry Mapping (4 Dec 2025, 833 rows), which yields 1,456 rules; a rule is one combination of entity, sub type, property set, property and agency.

On two independently built models it raised the share of passing element-rule checks from 0% to 13.0% and 17.8%. The derived beam and slab sizes match the design values.

[docs/WORKFLOW.md](docs/WORKFLOW.md) shows where this fits in the gateway process (as-is vs to-be) and how it could be rolled out.

## What it checks

| Level | Checks |
|---|---|
| Model | schema (IFC4; IFC4X3 is a warning, anything else an error), one IfcProject, length unit metre/millimetre, IfcSite + IfcBuilding + storeys, storey names unique and set, storey elevation, IfcMapConversion (SVY21 georeference), duplicate GlobalIds, every element contained in a storey |
| IFC+SG mapping | for every element the rule applies to (entity + PredefinedType; `*` sub types are USERDEFINED matched on ObjectType): property set present, property present, value type (number / text / boolean), accepted values where the mapping gives a short fixed list |

## What it fills in (and logs)

It fills a value only when the value can be traced to data already in the model, and it never overwrites a value that is already there. Every filled value is written to a CSV log with the element's GlobalId and where the value came from.

| Property | Derived from |
|---|---|
| Slab `Thickness`, beam `Depth`/`Width`, column `Width`/`Breadth`, pile `Length` | the body geometry, measured on an oriented bounding box (principal axes), so a beam on a grade or with superelevation is measured square to its own axis |
| `Mark` | the element's Tag, else its Name |
| `MaterialGrade` | `Pset_ConcreteElementGeneral.StrengthClass`, written as the EN 206 pair (`C50` → `C50/60`) |
| `ConstructionMethod` | `Pset_ConcreteElementGeneral.CastingMethod` (in situ → `CIS`, precast → `PC`) |

## Results

The numbers come from [reports/summary.json](reports/summary.json) and can be reproduced with `scripts/evaluate.py`.

| Model | Elements | Element-rule checks | Pass before | Values filled | Pass after |
|---|---|---|---|---|---|
| [facade-bim](https://github.com/LUOaini1213/facade-bim) (IFC4, unitized curtain wall) | 859 | 208 | 0% | 18 | 13.0% |
| [bridge-bim](https://github.com/LUOaini1213/bridge-bim) (IFC 4.3, 12-span T-girder bridge) | 1,470 | 27,249 | 0% | 5,136 | 17.8% |
| `samples/sample_block.ifc` (generated, defects planted) | 10 | 191 | 9.9% | 1 | 10.5% |

- **Accuracy of the derived sizes.** On all 120 T-girders of bridge-bim, depth comes out at 2,000–2,001 mm and width at 1,850 mm; the design section is 2.00 m × 1.85 m. Taking the vertical extent along the world axis instead gives 2,015–2,553 mm, because the girders sit on a grade with superelevation. The facade-bim slabs come out at 250 mm, as set in that model's export script.
- **What is left is information a model does not hold.** For bridge-bim, the largest remaining gaps are `SGPset_BeamReinforcement`, `SGPset_Beam` and `SGPset_SteelConnection`. For facade-bim, they are `SGPset_Slab` and `SGPset_SlabReinforcement`.
- **The planted defects are all found.** In the sample model:
  - D-02 has FireRating "1 hr", while the mapping's values are "0.5"…"4" with the unit held separately;
  - D-03 has no ClearWidth;
  - D-04 has ClearWidth stored as the text "1000 mm";
  - W-X is not contained in a storey;
  - there is no georeference.
- **Why both real models start at 0%.** Neither was authored for CORENET X, and bridge-bim is infrastructure (IFC 4.3, no IfcBuilding), so the checker flags its schema and spatial structure as well. They are used because they are real, independently built models, not models written to pass.

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
```

## Tests

`python -m pytest -q tests` runs 25 tests. They use the generated sample model and a handful of hand-written rules, so they do not need BCA's file.

`python tests/mutate.py` plants 23 deliberate bugs in the checker, the enrichment, the mapping converter, the report and the command line, and confirms that each one makes a test fail (currently 23/23). Before it starts, it confirms that the unmodified code passes and that every mutant compiles.

## Data and terms

BCA's terms of use do not allow the Industry Mapping to be republished. This repository therefore contains the converter but not the mapping or the rules generated from it; both are git-ignored. The reports contain property-set and property names and the counts measured on the two models above.

## Limits

- **Values are not checked against the codes.** Checks cover the presence, type and format of IFC+SG data. Whether a door is wide enough, for example, is a code-compliance question for the agencies' own checkers.
- **Accepted values are enforced only for short fixed lists.** Where the mapping gives a range or a note, the rule checks presence and type only.
- **IFC4X3 models are checked as they are.** The mapping is written for IFC4, so IFC 4.3 classes such as IfcBearing or IfcCourse match no rule.
