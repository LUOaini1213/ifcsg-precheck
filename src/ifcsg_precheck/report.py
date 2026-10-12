"""HTML report for designers and reviewers: what fails, for which agency, on which elements."""
import html
from collections import Counter, defaultdict


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render(report, enrichment_rows=None, title="IFC+SG pre-submission check", enrichment_pending=None):
    s = report.summary()
    f = report.findings
    by_agency = Counter((x.agency or "Unspecified mapping agency") if x.origin == "mapping" else "model" for x in f)
    by_pset = Counter((x.ifc_class, x.message.split(" (needs")[0]) for x in f if x.origin == "mapping")
    model = [x for x in f if x.origin == "model"]
    model_groups = Counter((x.rule, x.severity, x.message) for x in model)
    if model:
        model_summary = _table(["Rule", "Severity", "Message", "Findings"],
                               [(r, s, m, n) for (r, s, m), n in model_groups.most_common()])
        model_details = _table(["Rule", "Severity", "Message", "GlobalId", "Class", "Name"],
                               [(x.rule, x.severity, x.message, x.guid, x.ifc_class, x.name) for x in model])
        model_html = (f'<div class=w>{model_summary}</div><details><summary>Show all {len(model):,} '
                      f'model-level findings</summary><div class=w>{model_details}</div></details>')
    else:
        model_html = "<p>None.</p>"
    per_el = defaultdict(list)
    for x in f:
        if x.guid:
            per_el[(x.guid, x.ifc_class, x.name)].append(x.message)
    worst = sorted(per_el.items(), key=lambda kv: -len(kv[1]))[:50]
    filled = Counter((r["pset"], r["property"], r["source"]) for r in (enrichment_rows or []))
    pr = "n/a" if s["pass_rate"] is None else f"{s['pass_rate']:.1%}"
    unit_html = ""
    if report.unit_results:
        unit_html = ("<h2>Property-unit evidence</h2><p>Unverified units do not count as passed. "
                     "Label qualifiers retain their lexical values; these checks do not establish regulatory approval.</p><div class=w>" +
                     _table(["GlobalId", "Property", "Raw value", "IFC measure", "Source unit", "Target unit", "Normalized", "Status / reason"],
                            [(r["guid"], r["pset"] + "." + r["property"], r.get("raw_value", ""), r.get("measure_type", ""),
                              r.get("source_unit", ""), r.get("target_unit", ""), r.get("normalized_value", ""),
                              r["status"] + (": " + r["reason"] if r.get("reason") else "")) for r in report.unit_results]) + "</div>")
    deferred_html = ""
    if enrichment_pending:
        deferred_html = ("<h2>Derivations deferred for review</h2><div class=w>" +
                         _table(["GlobalId", "Property", "Reason"],
                                [(r["guid"], r["pset"] + "." + r["property"], r["reason"]) for r in enrichment_pending]) + "</div>")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font:14px/1.5 Segoe UI,Helvetica,Arial,sans-serif;color:#1f2933;background:#f5f7fa;margin:0}} main{{max-width:1100px;margin:0 auto;padding:20px 16px}}
.k{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}} .k div{{background:#fff;border:1px solid #e4e7eb;border-radius:8px;padding:10px}}
.k b{{display:block;font-size:22px;color:#1f5fa8}} table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px;margin:8px 0 18px}}
th,td{{border-bottom:1px solid #e4e7eb;padding:5px 8px;text-align:left;vertical-align:top}} h2{{font-size:17px;margin-top:26px}} .w{{overflow-x:auto}}
h1{{overflow-wrap:anywhere}} details{{margin:8px 0 18px}} summary{{cursor:pointer;color:#1f5fa8;padding:8px 0}} summary:focus-visible{{outline:2px solid #1f5fa8;outline-offset:2px}}
</style></head><body><main><h1>{html.escape(title)}</h1><p>{html.escape(s['file'])} &middot; {html.escape(s['schema'])} &middot; {s['elements']} elements</p>
<div class=k><div><b>{pr}</b>element-rule checks passed</div><div><b>{s['errors']:,}</b>errors</div><div><b>{s['warnings']}</b>warnings</div>
<div><b>{s['rules_applied']}</b>mapping rules applied</div><div><b>{len(enrichment_rows or []):,}</b>values auto-filled</div></div>
<h2>Model-level findings</h2>{model_html}
<h2>Findings by agency</h2><div class=w>{_table(["Agency", "Findings"], by_agency.most_common())}</div>
<h2>Most common gaps</h2><p>Counts are findings, not distinct elements. One element can fail several property rules.</p><div class=w>{_table(["IFC class", "Gap", "Findings"], [(c, g, n) for (c, g), n in by_pset.most_common(25)])}</div>
<h2>Auto-filled from existing model data</h2><div class=w>{_table(["Property set", "Property", "Source", "Values"], [(a, b, c, n) for (a, b, c), n in filled.most_common()]) if filled else "<p>Nothing could be derived.</p>"}</div>
{unit_html}{deferred_html}
<h2>Elements with the most gaps (top 50)</h2><div class=w>{_table(["GlobalId", "Class", "Name", "Gaps", "First gaps"], [(g, c, n, len(m), "; ".join(m[:3])) for (g, c, n), m in worst])}</div>
</main></body></html>"""
