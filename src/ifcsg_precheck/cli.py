"""Command line.

  python -m ifcsg_precheck.cli rules <industry-mapping.xlsx>          convert BCA's mapping into rules/ifcsg_mapping.json
  python -m ifcsg_precheck.cli check <model.ifc> [--agency SCDF] [--html out.html] [--json out.json] [--rules r.json ...]
  python -m ifcsg_precheck.cli enrich <model.ifc> <out.ifc>           fill derivable properties, write <out>.log.csv, re-check
  python -m ifcsg_precheck.cli sample <out.ifc>                        write the demonstration building
"""
import argparse
import json
from pathlib import Path

from .check import check, load_rules
from .report import render


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ifcsg_precheck")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rules"); r.add_argument("xlsx"); r.add_argument("--out", default="rules/ifcsg_mapping.json")
    c = sub.add_parser("check"); c.add_argument("ifc"); c.add_argument("--agency"); c.add_argument("--html"); c.add_argument("--json")
    c.add_argument("--rules", nargs="+", help="rule files (default: rules/*.json)")
    e = sub.add_parser("enrich"); e.add_argument("ifc"); e.add_argument("out"); e.add_argument("--html")
    e.add_argument("--rules", nargs="+")
    s = sub.add_parser("sample"); s.add_argument("out")
    a = ap.parse_args(argv)
    if a.cmd == "rules":
        from .mapping import convert
        print(len(convert(a.xlsx, a.out)), "rules written to", a.out)
    elif a.cmd == "sample":
        from .sample import build
        print("written", build(a.out))
    else:
        rules = load_rules(a.rules)
        if getattr(a, "agency", None):
            rules = [x for x in rules if x["agency"] in (a.agency, "All")]
        if a.cmd == "check":
            rep = check(a.ifc, rules)
            print(json.dumps(rep.summary(), indent=1, default=float))
            if a.json:
                Path(a.json).write_text(json.dumps(rep.to_json(), ensure_ascii=False), encoding="utf-8")
            if a.html:
                Path(a.html).write_text(render(rep), encoding="utf-8")
        else:
            from .enrich import enrich
            wanted = {(x["entity"], x["pset"], x["property"]) for x in rules}
            pending = []
            rows = enrich(a.ifc, a.out, str(a.out) + ".log.csv", wanted, rules=rules, pending=pending)
            rep = check(a.out, rules)
            print(f"{len(rows)} values filled; {len(pending)} derivations deferred;", json.dumps(rep.summary(), default=float))
            if a.html:
                Path(a.html).write_text(render(rep, rows, "IFC+SG check after auto-fill", pending), encoding="utf-8")


if __name__ == "__main__":
    main()
