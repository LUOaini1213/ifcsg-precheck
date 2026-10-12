# A designer's IFC review loop

The [authored demonstration](../demos/report-review/index.html) uses three small slabs and six independently written acceptance rules. `Demo structures` and `Demo coordination` are illustrative review groups. None of its rules were copied from BCA's workbook. It is separate from the official production mapping profile and every historical model/report in `reports/` and `samples/`.

The static report replay does not upload or process visitor IFC files. To review a real model, run the CLI locally with the mapping you are entitled to use. Reports and downloaded evidence may contain model identities; publish only inputs you own and intend to disclose.

1. Open **Check input**: 3 of 18 property checks pass. Search a GlobalId or property, combine agency, severity and status, then locate that element in the authoring tool. The full finding table retains every finding, including those outside the top-50 priority snapshot.
2. Open **Derive and recheck**: 9 traceable writes raise passing checks to 12 of 18. Inspect `S-derive`'s `Thickness`: the actual geometry is 0.25 m; its exported property is an `IfcLengthMeasure` of 0.25 with an explicit metre unit. `S-ready`'s existing 250 mm explicit override remains untouched. Source values, conversion factors and output values are in the fill trace.
3. Inspect **deferred** and **unit-unverified** evidence for `S-deferred`. A blank property with an unknown explicit unit is not auto-filled; a generic `IfcReal` clearance with no explicit unit is not credited as a physical length. Neither is silently repaired or counted as passed.

   The unverified pair remains in the full 18-pair denominator. Filtering never excludes it from that denominator. The final 18/18 describes only illustrative property checks; model-level warnings have a separate count and do not disappear into the property rate.
4. Open **Authored review and recheck**: scripted decisions for this fictional fixture supply typed physical values and the missing review reference/boolean. All 18 illustrative property checks pass, while the georeference warning remains. These decisions are authored demonstration inputs, not independent human annotations, official agency approval or evidence of complete code compliance.
5. Download complete JSON evidence or a CSV of the currently filtered review records. The global totals never change when filtering; the visible count is separate. JSON preserves original evidence and identities. CSV quotes fields and prefixes spreadsheet formula-like cells for safe review; this does not alter the JSON or IFC.

The report is self-contained, works when opened locally, and uses native labelled controls with keyboard focus indicators, live visible-count announcements, a clear-filter button and horizontally scrollable evidence tables. If JavaScript is disabled, every record remains visible. Filters and downloaded CSV/JSON are session-local; they do not write decisions back into an IFC.

## Reproduce and verify

```bash
pip install -r requirements-ci.txt numpy==2.4.6
python scripts/report_demo.py --output-dir demos/report-review
python scripts/report_demo.py --check
python scripts/build_report_pages.py --output _site
node --test tests/test_report_review.cjs
```

The builder calls the real `check → enrich → check` implementation. It then writes a separate scripted review IFC and checks it. `verify_report_demo.py` freshly reopens all three STEP files, checks instance-owned values and explicit units, independently reads the written slab's geometry, verifies `source_value_si_m × conversion_factor == exported value`, and confirms both preserved and unresolved source properties. A report is not accepted as proof of its own output.

`manifest.json` records raw input/output SHA-256 hashes, the checker/enrichment/unit code, report generator, CSS/JavaScript, fixture builder and independent verifier fingerprints. Source text hashes normalize CRLF to LF so the same checkout content is verifiable on Windows and Linux; IFC/output hashes use raw bytes. Fixed authored GUIDs and timestamps, canonical ordering of the unordered IFC containment SET and canonical LF in these authored STEP files keep this small fixture reproducible. CSV retains its generated CRLF. The scoped Git attributes preserve every demo output byte on Windows and Linux without changing historical files. The report demo uses Python 3.11, IfcOpenShell 0.8.5 and NumPy 2.4.6. `--check` independently generates into a temporary directory and rejects any changed byte, stale source hash, omitted or unexpected output.

Historical official-corpus reports, hashes, raw models and published measurements are retained unchanged. The authored example's 3/18 → 12/18 → 18/18 counts describe only its six illustrative rules and three slabs; they do not replace the historical results.

## Prepare publication

The [Pages workflow](../.github/workflows/report-pages.yml) builds and checks the demo on PRs and pushes. It stages exactly the allowlisted public authored files and `.nojekyll`; it does not upload the repository root, official workbook/generated rules, private models, dependencies or credentials. Staging rejects a changed inventory, stale source/output fingerprints, links and nonempty output directories.

Publication is a separate maintainer action after merge and exact-head checks:

```bash
# Maintainer release only, after reviewing the merged main commit:
gh api --method POST repos/LUOaini1213/ifcsg-precheck/pages -f build_type=workflow
gh variable set IFCSG_PAGES_ENABLED --body true --repo LUOaini1213/ifcsg-precheck
gh workflow run report-pages.yml --ref main -f publish=true --repo LUOaini1213/ifcsg-precheck
```

If Pages is already configured, update its build type instead of creating it again. Build jobs receive read permission; only the gated main/manual deploy job receives `pages: write` and `id-token: write` in the `github-pages` environment. The planned URL is `https://luoaini1213.github.io/ifcsg-precheck/`. This branch prepares a reviewed artifact and does not itself enable Pages or publish a site. A successful build is not a deployment receipt.

The workflow follows [GitHub's custom Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), using `configure-pages@v5`, `upload-pages-artifact@v4` and `deploy-pages@v4`.
