# Unit-semantics review — 2026-10-12

This measurement is separate from the original and 2026-10-03 reports, which remain byte-for-byte unchanged. It checks the complete property-unit path: original measure type and explicit Unit, natural project-unit inheritance, target normalization, and typed dimensional writes. It does not establish regulatory compliance.

## Inputs and scope

[provenance.json](provenance.json) records exact input/rule/source SHA-256 values and Python/package versions. The public inputs are the model files at [facade commit 3c88e925](https://github.com/LUOaini1213/facade-bim/blob/3c88e925a67d443ef879dce15b9e1ee837354375/model/facade_bim.ifc) and [bridge commit b6456b34](https://github.com/LUOaini1213/bridge-bim/blob/b6456b344b09a92620cc5d4a4cfb2a3be963b147/model/bridge_bim.ifc), plus the unchanged repository sample. The real-model hashes differ from the older measurements; the facade now has 8,323 elements. These are not controlled before/after comparisons with the older corpus. Only each row's before/after columns below use the same input and rules.

The local official 4 December 2025 mapping has SHA-256 `f436aa273c366f04dcf6eef55e365081a8b76a2271520c188174a1c69f803114`. Its [aggregate catalogue](unit_catalog.json) records 833 rows and 1,456 expanded rules: 386 supported physical targets, 20 lexical qualifiers, 28 targets needing datum review, and 1,022 rules without a physical target. This is target coverage, not a count of source units proved valid. Neither workbook rows nor generated rules are redistributed.

The observed physical targets are mm, m, m2, m3, kN, kPa, hr, L, L/s and tonnes. Raw mapping `Integer` force/pressure and `Real` fields still require a physical source: a generic IFC scalar without an explicit Unit cannot inherit a physical project unit from the requested target. `Label` time/length qualifiers remain literal text. `SHD m` needs verified height-datum information. Context-dependent, offset, incompatible, ambiguous and unsupported units stay unverified.

## Measured results

[summary.json](summary.json) contains the actual evaluation results. Passing pairs count all applicable element/rule pairs; unit-unverified pairs remain in the denominator and are excluded from the numerator. They are review warnings, not assertions that a model violates regulations.

| Model | Elements | Applicable pairs | Passing before | Filled values | Passing after | Unit-unverified before/after |
|---|---:|---:|---:|---:|---:|---:|
| facade | 8,323 | 208 | 0 / 208 (0%) | 18 | 27 / 208 (13.0%) | 0 / 0 |
| bridge | 1,470 | 27,249 | 0 / 27,249 (0%) | 4,848 | 4,848 / 27,249 (17.8%) | 0 / 0 |
| planted sample | 10 | 191 | 7 / 191 (3.7%) | 1 | 8 / 191 (4.2%) | 12 / 12 |

Nine facade dimensions and 1,964 bridge dimensions are now written as `IfcLengthMeasure` with an explicit Unit. The resulting unit-evidence rows are 18 verified facade pairs and 1,964 verified bridge pairs (agency rules can reuse a property); no geometry fills were deferred in these runs. The sample retains its original data: 12 `IfcReal` length values have no explicit unit, so this review no longer counts them as physically verified. Three sample unit qualifiers remain literal. The changed sample passing rate is explained by these 12 exclusions, not by editing the sample or changing its intended defect labels. The real-model fill counts also use newer input files and must not be attributed solely to unit handling.

Open [facade report](facade_report.html), [bridge report](bridge_report.html), or [sample report](sample_report.html) to see mapping gaps, raw measure/unit evidence and model-level findings. A passing property pair does not clear the model-level building profile. The bridge remains an infrastructure example under a building profile.

[verification.json](verification.json) records the independent exported-file check: all 1,973 dimensional writes were reopened as STEP properties, their explicit SI unit definitions and measure types checked, and their nominal values compared with the CSV's source-value/factor product and metre/millimetre physical scale. The CSV's source value uses the derivation's existing nearest-millimetre rounding, represented in SI metres. It also records matching source/input/rule/catalog hashes and unchanged bytes for the ten historical assets under the original Windows checkout filters.

## Reproduce

Download the workbook yourself from the [official mapping page](https://info.corenet.gov.sg/ifc-sg/requirements---submission/ifc-sg-excel-mapping-file). Match the recorded model, workbook, generated-rule and source hashes plus dependency versions. Source fingerprints hash raw workspace bytes, including line endings; elapsed times are local measurements, not a speed comparison.

```bash
export PYTHONPATH=src
python -m ifcsg_precheck.cli rules industry-mapping-4-dec-2025.xlsx
python scripts/unit_catalog.py industry-mapping-4-dec-2025.xlsx --out reports/my-unit-review/unit_catalog.json
python scripts/evaluate.py --output-dir reports/my-unit-review --rules rules/ifcsg_mapping.json \
  facade=../facade-bim/model/facade_bim.ifc \
  bridge=../bridge-bim/model/bridge_bim.ifc sample=samples/sample_block.ifc
python -m pytest -q tests
python tests/mutate.py --self-test
python tests/mutate.py
```

The final offline gate passed 175 tests, all 11 harness self-checks and 55/55 deliberate mutations (original 40 plus 15 unit/trace defects). The full mutation run used a separate copy of all 19 source/test Python files with matching raw bytes; the final gate took 411.2 seconds and restored all source bytes. The restored copy was compared with the untouched implementation checkout. Known-value, real STEP round trips cover all ten physical targets; metre/millimetre equivalence; explicit override including missing/ambiguous project units; inherited units; generic scalar refusal; duplicate definitions; SI squared/cubed prefixes and mass; nested conversion and derived flow; quantity units; unknown/datum/dimension cases; typed geometry writes from metre, centimetre and foot projects; CLI/evaluation target units; source-value/factor arithmetic; and idempotency.

The mutation run exposed a missing case for a contradictory measure type when the explicit Unit and target share a dimension. An added regression now refuses an `IfcLengthMeasure` with a tonne Unit even when the target is tonnes; the final run detects bypassing this check. Generated IFCs, before/after JSON, fill logs, pending records and mapping rules remain local/ignored; published HTML and summary/provenance files expose the measured results. The offline gate does not claim an unrun remote CI result.
