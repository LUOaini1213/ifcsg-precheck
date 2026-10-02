# Where a pre-check fits in the CORENET X submission process

CORENET X groups building-plan approvals into gateways:

- **G1 Design**
- **G1.5 Piling**
- **G2 Construction**
- **G3 Completion**

At each gateway, one coordinated IFC+SG model goes to all the regulatory agencies together. The IFC+SG data each agency needs is set out in BCA's Industry Mapping; the version used here is dated 4 December 2025.

## As-is: gaps are found by the reviewer

```mermaid
flowchart LR
  A[Designer models in Revit / Archicad / Tekla] --> B[Export IFC+SG]
  B --> C[Submit at gateway]
  C --> D{Agency review}
  D -- missing or malformed IFC+SG data --> E[Query to QP]
  E --> A
  D -- complete --> F[Approval]
```

The pain points are:

- **Missing data is found late.** A missing `SGPset_DoorDimension.ClearWidth` or a wrongly formatted `FireRating` is found only after submission, at the agency's review. Each finding costs a query-and-resubmit cycle.
- **The requirements live in a spreadsheet.** They are in an Excel mapping of 833 rows (entity, sub type, property set, property, accepted values, agency), and the designer has to cross-check by hand.
- **Existing data is typed twice.** Values the model already holds are often re-entered by hand: sizes in the geometry, concrete class in a standard property set.

## To-be (proposed): check and auto-fill before submission

```mermaid
flowchart LR
  A[Designer models] --> B[Export IFC]
  B --> P[Pre-check: model rules + IFC+SG mapping rules]
  P --> X[Auto-fill derivable properties, with a source log]
  X --> R[Report: gaps by agency, component and element]
  R -- gaps left --> A
  R -- clean --> C[Submit at gateway]
  C --> D{Agency review: design content, not data format}
```

The steps are:

1. **Pre-check.** Run the checker on the exported IFC. This project's building profile checks one project, units, site/building presence, named storeys, an actual storey ancestor, georeference presence and IFC4, plus every applicable mapping rule; it can filter by agency. It does not require exactly one site or building, and its building profile is not a universal IFC schema validator.
2. **Auto-fill.** Fill only what can be derived with a traceable source:
   - dimensions from geometry, measured square to the member axis;
   - marks from the tag or name;
   - concrete grade (EN 206 pair) and construction method from `Pset_ConcreteElementGeneral`.

   Every value goes into a CSV log so the designer can review it. Existing non-empty values are preserved, including inherited values, zero and false. Missing values are written to an instance-owned property set; shared sets are split before editing. Unknown source booleans stay unknown rather than becoming false.
3. **Report.** The designer gets findings grouped by agency and component, with the elements that have the most gaps. Counts refer to findings, not distinct elements. Repeated model-level findings have a compact summary and expandable details retaining every GlobalId. The designer fixes what is left and re-runs the check.
4. **Submit.** The model goes to the gateway after the supported data checks. Agency review remains necessary for design content, regulatory compliance and unsupported data checks; a clean report does not guarantee approval.

## What was measured on real models

The rules come from BCA's IFC+SG mapping of 4 December 2025. The table below records the original `reports/summary.json` measurement. The separate [2026-10-03 recheck](../reports/review-20261003/summary.json) preserves property pass rates and fill counts and records exact inputs and implementation hashes in [provenance.json](../reports/review-20261003/provenance.json).

| Model | Elements | Element-rule checks | Pass before | Values auto-filled | Pass after | Time |
|---|---|---|---|---|---|---|
| facade-bim (IFC4, unitised curtain wall) | 859 | 208 | 0% | 18 | 13.0% | 13 s |
| bridge-bim (IFC 4.3, 12-span T-girder bridge) | 1,470 | 27,249 | 0% | 5,136 | 17.8% | 60 s |

- **The auto-filled sizes match the design values.** On all 120 T-girders, beam depth and width come out at 2,000–2,001 mm and 1,850 mm; bridge-bim's design section is 2.00 m by 1.85 m. The facade slabs come out at 250 mm, as in the model's export script.
- **Both models start at 0% by design.** Neither was authored for CORENET X, and the bridge is not a CORENET X building submission. They are used because they are real, independently built models.
- **What remains needs the designer.** Properties such as reinforcement details, connection types and slab type remain missing from the required locations after the supported derivations. The report lists them for review; it does not prove the information is absent from every other part of the model. Model-level findings also remain and are reported separately.
- **Time.** On a laptop, checking, auto-filling and re-checking the bridge model took about a minute.
- **Profile boundary.** The corrected storey ancestry check flags all 1,470 bridge elements because the bridge is not contained in building storeys. Those findings are separate from mapping pass rates and do not establish structural defects. Geometry-validation statements above describe the original measurement, not a new independent design validation.

## Rolling this out (change management)

- **Start where the rules are settled.** Begin with the property sets whose accepted values are fixed lists, such as `FireRating`, `ConstructionMethod` and `MaterialGrade`. The mapping itself says it is a work in progress, so rules should follow its version, and the change log sheet shows what moved.
- **Put the check in the designer's loop, not the agency's.** A report grouped by element GlobalId can be opened next to the authoring tool.
- **Keep auto-fill conservative and logged.** A derived value that is wrong is worse than a gap, so each derivation is validated against design values before it is enabled, as the girder depths above were.
