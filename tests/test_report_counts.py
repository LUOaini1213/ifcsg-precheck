"""Large reports remain readable without losing component identities or misstating counts."""
from html.parser import HTMLParser

from ifcsg_precheck.check import Finding, Report
from ifcsg_precheck.report import render


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.cell = None
        self.detail_attributes = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self.tables[-1].append([])
        elif tag in ("th", "td"):
            self.cell = ""
        elif tag == "details":
            self.detail_attributes.append(dict(attrs))

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in ("th", "td"):
            self.tables[-1][-1].append(self.cell)
            self.cell = None


def test_repeated_model_findings_are_grouped_with_all_identities_retained():
    findings = [Finding("containment", "error", "no storey", f"guid-{i}", "IfcBeam", "same name")
                for i in range(120)]
    findings.append(Finding("schema", "warning", "unsupported <schema>"))
    page = render(Report("model.ifc", "IFC4", 120, findings))
    parsed = Tables()
    parsed.feed(page)
    summary, details = parsed.tables[:2]
    assert summary[1:] == [["containment", "error", "no storey", "120"],
                           ["schema", "warning", "unsupported <schema>", "1"]]
    assert parsed.detail_attributes == [{}]  # collapsed, native keyboard-accessible control
    assert len(details[1:]) == 121
    guid_column = details[0].index("GlobalId")
    assert {r[guid_column] for r in details[1:]} == {"", *(f"guid-{i}" for i in range(120))}
    assert "unsupported &lt;schema&gt;" in page


def test_gap_counts_are_property_findings_not_distinct_elements():
    findings = [Finding(f"CX{i}", "error", f"missing property set SGPset_Beam (needs P{i})",
                        "same-guid", "IfcBeam", "Beam", "BCA") for i in range(3)]
    parsed = Tables()
    parsed.feed(render(Report("model.ifc", "IFC4", 1, findings)))
    gap_table = next(t for t in parsed.tables if t[0][:2] == ["IFC class", "Gap"])
    assert gap_table == [["IFC class", "Gap", "Findings"],
                         ["IfcBeam", "missing property set SGPset_Beam", "3"]]


def test_custom_mapping_id_is_not_a_model_finding():
    findings = [Finding("T1", "error", "missing property set Custom", "beam-guid", "IfcBeam",
                        "Beam", origin="mapping")]
    page = render(Report("model.ifc", "IFC4", 1, findings))
    parsed = Tables()
    parsed.feed(page)
    assert not parsed.detail_attributes
    assert parsed.tables[0] == [["Agency", "Findings"], ["Unspecified mapping agency", "1"]]
    gap_table = next(t for t in parsed.tables if t[0][:2] == ["IFC class", "Gap"])
    assert gap_table[1:] == [["IfcBeam", "missing property set Custom", "1"]]
