"""Record aggregate unit/type coverage from a local mapping; do not copy its rows.

python scripts/unit_catalog.py mapping.xlsx --out reports/my-review/unit_catalog.json
The local workbook and generated rules remain git-ignored.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ifcsg_precheck.mapping import SHEET, convert  # noqa: E402
from ifcsg_precheck.units import UnitError, target_unit  # noqa: E402


def catalog(path):
    frame = pd.read_excel(path, sheet_name=SHEET)
    columns = {str(c).strip(): c for c in frame.columns}
    unit_col = next(c for label, c in columns.items() if label.startswith("Property Unit"))
    type_col = next(c for label, c in columns.items() if label.startswith("Property Type"))
    label = lambda value: "N.A" if pd.isna(value) else str(value).strip()
    counts = Counter((label(row[type_col]), label(row[unit_col])) for _, row in frame.iterrows())
    rules = convert(path)
    rule_counts = Counter()
    for rule in rules:
        try:
            expected = target_unit(rule["unit"])
            status = "no_physical_target" if expected is None else (
                "lexical_qualifier" if rule["value_type"] == "text" else "physical_target_supported")
        except UnitError:
            status = "target_requires_review"
        rule_counts[status] += 1
    return {"mapping": {"file": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                        "sheet": SHEET, "rows": len(frame)},
            "property_type_unit_counts": [{"property_type": typ, "unit": unit, "rows": n}
                                          for (typ, unit), n in sorted(counts.items())],
            "generated_rule_count": len(rules), "generated_rule_target_status_counts": dict(sorted(rule_counts.items())),
            "interpretation": "Target coverage is not proof of source-unit verification. Generic IfcInteger/IfcReal require an explicit Unit; Label qualifiers remain literal; SHD requires datum review.",
            "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              (Path(__file__).resolve(), ROOT / "src/ifcsg_precheck/mapping.py", ROOT / "src/ifcsg_precheck/units.py")}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    result = catalog(args.mapping)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("mapping", "generated_rule_count", "generated_rule_target_status_counts")}))


if __name__ == "__main__":
    main()
