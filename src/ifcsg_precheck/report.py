"""HTML report for designers and reviewers: what fails, for which agency, on which elements."""
import html
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def review_rows(report, enrichment_rows=None, enrichment_pending=None, rules=None):
    """Review records retain their evidence; filters never change the Report counts."""
    indexed = {r["id"]: r for r in (rules or [])}
    properties = defaultdict(set)
    for rule in rules or []:
        properties[(rule["pset"], rule["property"])].add(rule.get("agency") or "Unspecified mapping agency")

    def row(kind, raw, *, agency, severity, status, guid, prop, detail):
        return dict(kind=kind, agency=agency, severity=severity, status=status, guid=guid,
                    property=prop, detail=detail, evidence=raw)

    out = []
    for finding in report.findings:
        rule = indexed.get(finding.rule, {})
        prop = ".".join((rule.get("pset", ""), rule.get("property", ""))).strip(".")
        status = ("unit-unverified" if "unit unverified:" in finding.message else
                  "needs-correction" if finding.severity == "error" else "review-warning")
        out.append(row("finding", asdict(finding), agency=(finding.agency or "Unspecified mapping agency")
                       if finding.origin == "mapping" else "Model profile", severity=finding.severity,
                       status=status, guid=finding.guid, prop=prop,
                       detail=f"{finding.rule} · {finding.ifc_class} · {finding.name} · {finding.message}"))
    for kind, records in (("unit", report.unit_results), ("derived", enrichment_rows or []),
                          ("deferred", enrichment_pending or [])):
        for raw in records:
            key = (raw["pset"], raw["property"])
            # A property may be requested by several agencies. Keep one evidence
            # record with an agency list, rather than multiplying its count.
            agencies = sorted(properties.get(key) or {"Unspecified mapping agency"})
            status = raw["status"] if kind == "unit" else "auto-filled" if kind == "derived" else "deferred"
            if kind == "unit" and status == "unverified":
                status = "unit-unverified"  # One filter shows both finding and evidence; raw status stays unchanged.
            out.append(row(kind, dict(raw), agency="; ".join(agencies), severity="evidence",
                           status=status, guid=raw.get("guid", ""), prop=".".join(key),
                           detail=json.dumps(raw, ensure_ascii=False, sort_keys=True)))
    return out


def _review_html(records, report, enrichment_rows, enrichment_pending, context):
    def options(values):
        return "".join(f'<option value="{html.escape(v, quote=True)}">{html.escape(v)}</option>' for v in sorted(values))

    agency_options = options({a for r in records for a in r["agency"].split("; ")})
    status_options = options({r["status"] for r in records})
    tables = []
    for kind, heading in (("finding", "All findings"), ("unit", "Typed property-unit evidence"),
                          ("derived", "Written values and derivation trace"), ("deferred", "Derivations deferred for review")):
        rows = []
        for record in records:
            if record["kind"] != kind:
                continue
            attributes = " ".join(f'data-{key}="{html.escape(record[key], quote=True)}"'
                                  for key in ("kind", "agency", "severity", "status", "guid", "property"))
            cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in
                            (record["agency"], record["severity"], record["status"], record["guid"],
                             record["property"], record["detail"]))
            rows.append(f"<tr {attributes}>{cells}</tr>")
        tables.append(f'<section class="review-section"><h3>{heading} <span data-count="{kind}"></span></h3>'
                      '<div class="w" tabindex="0" role="region" aria-label="' + heading + '">'
                      '<table><thead><tr>' + "".join(f'<th scope="col">{h}</th>' for h in
                      ("Agency", "Severity", "Status", "GlobalId", "Property", "Complete evidence")) +
                      '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div></section>')
    payload = dict(report=report.to_json(), derived=enrichment_rows or [], deferred=enrichment_pending or [],
                   review_records=records, context=context or {})
    # A data script is still HTML: a hostile IFC name must not close its tag.
    data = json.dumps(payload, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    data = data.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return ('''<section id="review" aria-labelledby="review-title"><h2 id="review-title">Designer review workbench</h2>
<p>Locate the GlobalId in your authoring tool, inspect the full evidence, then correct or confirm the source and re-run the checker.
Filters change the visible review records only. Summary counts above always describe the complete model; an auto-fill is evidence to review, not approval.</p>
<form id="review-filters"><label>Agency<select id="filter-agency"><option value="">All agencies</option>''' + agency_options + '''</select></label>
<label>Severity<select id="filter-severity"><option value="">All severities</option><option value="error">Error</option><option value="warning">Warning</option><option value="evidence">Evidence</option></select></label>
<label>Status<select id="filter-status"><option value="">All statuses</option>''' + status_options + '''</select></label>
<label>GlobalId<input id="filter-guid" type="search" placeholder="Find an element" autocomplete="off"></label>
<label>Property or rule/message<input id="filter-property" type="search" placeholder="Thickness, rule or message" autocomplete="off"></label>
<button type="reset">Clear filters</button></form>
<p id="review-visible" role="status" aria-live="polite"></p>
<div class="downloads"><button id="download-json" type="button">Download complete evidence (JSON)</button>
<button id="download-csv" type="button">Download filtered review (CSV)</button></div>
<noscript><p>All evidence remains visible. Interactive filtering and browser downloads require JavaScript.</p></noscript>''' +
            "".join(tables) + '</section><script type="application/json" id="review-data">' + data + '</script>')


def render(report, enrichment_rows=None, title="IFC+SG pre-submission check", enrichment_pending=None, *, rules=None, context=None):
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
    records = review_rows(report, enrichment_rows, enrichment_pending, rules)
    assets = Path(__file__).with_name("report_assets")
    review_css = (assets / "review.css").read_text(encoding="utf-8")
    review_js = (assets / "review.js").read_text(encoding="utf-8")
    review = _review_html(records, report, enrichment_rows, enrichment_pending, context)
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
<style>{review_css}</style>{review}
</main><script>{review_js}</script></body></html>"""
