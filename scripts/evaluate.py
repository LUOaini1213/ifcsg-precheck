"""Check, auto-fill and re-check models, recording input and implementation fingerprints.

  python scripts/evaluate.py facade=path/to/facade_bim.ifc bridge=path/to/bridge_bim.ifc sample=samples/sample_block.ifc
  python scripts/evaluate.py --output-dir reports/review facade=path/to/facade_bim.ifc

Needs rules/ifcsg_mapping.json (see README). The two real models are public:
  https://github.com/LUOaini1213/facade-bim/blob/main/model/facade_bim.ifc
  https://github.com/LUOaini1213/bridge-bim/blob/main/model/bridge_bim.ifc
"""
import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.check import check, load_rules  # noqa: E402
from ifcsg_precheck.enrich import enrich  # noqa: E402
from ifcsg_precheck.report import render  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"


def run(name, path, rules, out=OUT):
    t0 = time.time()
    before = check(path, rules)
    wanted = {(r["entity"], r["pset"], r["property"]) for r in rules}
    enriched = out / f"{name}_enriched.ifc"
    rows = enrich(path, enriched, out / f"{name}_enrichment_log.csv", wanted)
    after = check(enriched, rules)
    for tag, rep in (("before", before), ("after", after)):
        (out / f"{name}_{tag}.json").write_text(json.dumps(rep.to_json(), ensure_ascii=False), encoding="utf-8")
    (out / f"{name}_report.html").write_text(render(after, rows, f"IFC+SG check after auto-fill: {name}"), encoding="utf-8")
    gaps = Counter((f.ifc_class, f.message.split(" ")[3] if f.message.startswith("missing property set") else
                    f.message.split(" ")[0].split(".")[0]) for f in after.findings if f.origin == "mapping")
    s_before, s_after = before.summary(), after.summary()
    return {"schema": s_before["schema"], "elements": s_before["elements"], "rules_applied": s_before["rules_applied"],
            "element_rule_pairs": s_before["element_rule_pairs"], "pass_before": s_before["pass_rate"],
            "pass_after": s_after["pass_rate"], "auto_filled": len(rows), "errors_before": s_before["errors"],
            "errors_after": s_after["errors"],
            "model_level_findings": sorted({(f.rule, f.message) for f in after.findings if f.origin == "model"}),
            "top_remaining": gaps.most_common(8), "seconds": round(time.time() - t0, 1)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", metavar="NAME=PATH")
    parser.add_argument("--output-dir", type=Path, default=OUT,
                        help="Use a fresh directory to preserve a previous measurement.")
    parser.add_argument("--rules", type=Path, help="Local mapping rules; never redistributed with the reports.")
    args = parser.parse_args(argv)
    from ifcsg_precheck.check import RULES_DIR
    import ifcopenshell

    rule_paths = [args.rules] if args.rules else sorted(RULES_DIR.glob("*.json"))
    if not rule_paths:
        parser.error("no mapping rules found; generate them first or pass --rules")
    rules = load_rules(rule_paths)
    if not rules:
        parser.error("the selected mapping rules are empty")
    models = {}
    for arg in args.models:
        if "=" not in arg:
            parser.error(f"expected NAME=PATH: {arg}")
        name, path = arg.split("=", 1)
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
            parser.error("model names may contain only letters, digits, underscores and hyphens")
        if name in models:
            parser.error(f"duplicate model name: {name}")
        models[name] = Path(path)

    def fingerprint(path):
        return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    # Fingerprint inputs before processing; no absolute/private filesystem paths are published.
    provenance = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
                  "python": sys.version.split()[0], "ifcopenshell": ifcopenshell.version,
                  "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "openpyxl")},
                  "models": {name: fingerprint(path) for name, path in models.items()},
                  "rules": [fingerprint(path) for path in rule_paths], "rule_count": len(rules),
                  "source_sha256": {p.relative_to(ROOT).as_posix(): fingerprint(p)["sha256"] for p in
                                    sorted([*(ROOT / "src/ifcsg_precheck").glob("*.py"), Path(__file__).resolve()])}}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, path in models.items():
        summary[name] = run(name, path, rules, args.output_dir)
        print(name, json.dumps({k: v for k, v in summary[name].items() if k not in ("top_remaining", "model_level_findings")}))
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (args.output_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
