"""Check, auto-fill and re-check models, and write reports/summary.json.

  python scripts/evaluate.py facade=path/to/facade_bim.ifc bridge=path/to/bridge_bim.ifc sample=samples/sample_block.ifc

Needs rules/ifcsg_mapping.json (see README). The two real models are public:
  https://github.com/LUOaini1213/facade-bim/blob/main/model/facade_bim.ifc
  https://github.com/LUOaini1213/bridge-bim/blob/main/model/bridge_bim.ifc
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.check import check, load_rules  # noqa: E402
from ifcsg_precheck.enrich import enrich  # noqa: E402
from ifcsg_precheck.report import render  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "reports"


def run(name, path, rules):
    t0 = time.time()
    before = check(path, rules)
    wanted = {(r["entity"], r["pset"], r["property"]) for r in rules}
    enriched = OUT / f"{name}_enriched.ifc"
    rows = enrich(path, enriched, OUT / f"{name}_enrichment_log.csv", wanted)
    after = check(enriched, rules)
    for tag, rep in (("before", before), ("after", after)):
        (OUT / f"{name}_{tag}.json").write_text(json.dumps(rep.to_json(), ensure_ascii=False), encoding="utf-8")
    (OUT / f"{name}_report.html").write_text(render(after, rows, f"IFC+SG check after auto-fill: {name}"), encoding="utf-8")
    gaps = Counter((f.ifc_class, f.message.split(" ")[3] if f.message.startswith("missing property set") else
                    f.message.split(" ")[0].split(".")[0]) for f in after.findings if f.rule.startswith("CX"))
    s_before, s_after = before.summary(), after.summary()
    return {"schema": s_before["schema"], "elements": s_before["elements"], "rules_applied": s_before["rules_applied"],
            "element_rule_pairs": s_before["element_rule_pairs"], "pass_before": s_before["pass_rate"],
            "pass_after": s_after["pass_rate"], "auto_filled": len(rows), "errors_before": s_before["errors"],
            "errors_after": s_after["errors"],
            "model_level_findings": sorted({(f.rule, f.message) for f in after.findings if not f.rule.startswith("CX")}),
            "top_remaining": gaps.most_common(8), "seconds": round(time.time() - t0, 1)}


if __name__ == "__main__":
    rules = load_rules()
    OUT.mkdir(exist_ok=True)
    summary = {}
    for arg in sys.argv[1:]:
        name, path = arg.split("=", 1)
        summary[name] = run(name, path, rules)
        print(name, json.dumps({k: v for k, v in summary[name].items() if k not in ("top_remaining", "model_level_findings")}))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
