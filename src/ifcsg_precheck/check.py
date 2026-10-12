"""Pre-submission checks for IFC-SG models (CORENET X).

Two layers:
1. This project's building-submission profile: schema, project units, site / building and named storeys,
   elements placed in a storey, map georeferencing, no duplicate GlobalIds. These are not universal IFC constraints.
2. Property rules from rules/*.json. Each rule says: for elements of an IFC class (optionally a predefined type), a
   property set must carry a property, optionally of a data type and within allowed values. The rules are transcribed
   from BCA's public IFC-SG Industry Mapping and cite the row they came from.

Every finding carries the element's GlobalId, class and name so it can be found in the authoring tool.
"""
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element as uel
import ifcopenshell.util.placement as upl
from .units import audit

RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


@dataclass
class Finding:
    rule: str
    severity: str            # error | warning
    message: str
    guid: str = ""
    ifc_class: str = ""
    name: str = ""
    agency: str = ""
    origin: str | None = None  # model | mapping; None supports older manually constructed findings.

    def __post_init__(self):
        if self.origin is None:
            self.origin = "mapping" if self.rule.startswith("CX") else "model"


@dataclass
class Report:
    file: str
    schema: str
    elements: int
    findings: list = field(default_factory=list)
    rules_applied: int = 0
    element_rule_pairs: int = 0      # (element, rule) combinations checked
    passed_pairs: int = 0
    unit_unverified_pairs: int = 0
    unit_results: list = field(default_factory=list)

    def summary(self):
        by_rule = Counter(f.rule for f in self.findings)
        return {"file": self.file, "schema": self.schema, "elements": self.elements,
                "errors": sum(f.severity == "error" for f in self.findings),
                "warnings": sum(f.severity == "warning" for f in self.findings),
                "rules_applied": self.rules_applied, "element_rule_pairs": self.element_rule_pairs,
                "unit_unverified_pairs": self.unit_unverified_pairs,
                "pass_rate": (self.passed_pairs / self.element_rule_pairs) if self.element_rule_pairs else None,
                "top_rules": by_rule.most_common(10)}

    def to_json(self):
        return {"summary": self.summary(), "findings": [asdict(f) for f in self.findings],
                "unit_results": self.unit_results}


def _f(el, rule, severity, message, agency="", origin="model"):
    return Finding(rule, severity, message, getattr(el, "GlobalId", "") or "", el.is_a() if el else "",
                   (getattr(el, "Name", "") or "") if el else "", agency, origin)


def _of_type(m, cls):
    """by_type that returns nothing for a class the file's schema does not have (IfcMapConversion in IFC2X3)."""
    try:
        return m.by_type(cls)
    except RuntimeError:
        return []


# ---------------- model checks ----------------
def model_checks(m):
    out = []
    if m.schema.startswith("IFC4X3"):
        out.append(Finding("schema", "warning", f"schema {m.schema}; IFC+SG submissions use IFC4, so the model needs "
                                                 "exporting as IFC4 (IFC4X3 classes such as IfcBearing have no IFC4 equivalent)"))
    elif m.schema != "IFC4":
        out.append(Finding("schema", "error", f"schema {m.schema}; IFC+SG submissions use IFC4 (Reference View)"))
    projects = m.by_type("IfcProject")
    if len(projects) != 1:
        out.append(Finding("project", "error", f"{len(projects)} IfcProject entities; exactly one expected"))
    units = {u.UnitType: u for p in projects for u in (p.UnitsInContext.Units if p.UnitsInContext else [])
             if u.is_a("IfcSIUnit") or u.is_a("IfcConversionBasedUnit")}
    lu = units.get("LENGTHUNIT")
    if lu is None:
        out.append(Finding("units", "error", "no project length unit"))
    elif not (lu.is_a("IfcSIUnit") and lu.Name == "METRE" and lu.Prefix in (None, "MILLI")):
        out.append(Finding("units", "error", "length unit is not metre or millimetre"))
    for kind in ("IfcSite", "IfcBuilding"):
        n = len(m.by_type(kind))
        if n == 0:
            out.append(Finding("spatial_structure", "error", f"no {kind}"))
    storeys = m.by_type("IfcBuildingStorey")
    if m.by_type("IfcBuilding") and not storeys:
        out.append(Finding("spatial_structure", "error", "building has no IfcBuildingStorey"))
    names = Counter(s.Name for s in storeys)
    for s in storeys:
        if not s.Name:
            out.append(_f(s, "storey_naming", "error", "storey without a name"))
        elif names[s.Name] > 1:
            out.append(_f(s, "storey_naming", "error", f"storey name '{s.Name}' used {names[s.Name]} times"))
        if s.Elevation is None:
            out.append(_f(s, "storey_elevation", "warning", "storey elevation not set"))
    if not _of_type(m, "IfcMapConversion"):
        out.append(Finding("georeference", "warning", "no IfcMapConversion: the model is not tied to SVY21 map coordinates"))
    guids = Counter(e.GlobalId for e in m.by_type("IfcRoot"))
    for g, c in guids.items():
        if c > 1:
            out.append(Finding("guid", "error", f"GlobalId {g} used {c} times", guid=g))
    for el in m.by_type("IfcElement"):
        if el.is_a("IfcFeatureElement") or el.is_a("IfcOpeningElement"):
            continue
        if uel.get_container(el, ifc_class="IfcBuildingStorey") is None:
            out.append(_f(el, "containment", "error", "element is not contained in a storey (or aggregated into one)"))
    return out


# ---------------- property rules ----------------
def load_rules(paths=None):
    paths = paths or sorted(RULES_DIR.glob("*.json"))
    rules = []
    for p in paths:
        rules += json.loads(Path(p).read_text(encoding="utf-8"))
    return rules


def applies(rule, el):
    if not el.is_a(rule["entity"]):
        return False
    want = rule.get("predefined_type")
    if not want:
        return True
    # Type-level PredefinedType takes precedence; an undefined type leaves the occurrence in charge.
    source = uel.get_type(el)
    if source is None or getattr(source, "PredefinedType", None) in (None, "NOTDEFINED"):
        source = el
    predefined = getattr(source, "PredefinedType", None)
    if rule.get("userdefined"):
        # Keep the USERDEFINED marker: a custom label "DOOR" is not the DOOR enum.
        label = getattr(source, "ElementType" if source.is_a("IfcTypeObject") else "ObjectType", None)
        return predefined == "USERDEFINED" and (label or "").upper() == want.upper()
    return (predefined or "").upper() == want.upper()


def value_problem(rule, value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return "is empty"
    kind = rule.get("value_type")
    if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return f"should be a number, found {type(value).__name__}"
    if kind == "number" and isinstance(value, float) and not math.isfinite(value):
        return "should be a finite number"
    if kind == "boolean" and not isinstance(value, bool):
        return f"should be true/false, found {type(value).__name__}"
    if kind == "text" and not isinstance(value, str):
        return f"should be text, found {type(value).__name__}"
    allowed = rule.get("allowed_values")
    if allowed and str(value) not in allowed:
        return f"value '{value}' is not one of the allowed values"
    lo, hi = rule.get("min"), rule.get("max")
    if isinstance(value, (int, float)) and ((lo is not None and value < lo) or (hi is not None and value > hi)):
        return f"value {value} outside the expected range [{lo}, {hi}]"
    return None


def property_checks(m, rules, report):
    out = []
    elements = m.by_type("IfcElement") + _of_type(m, "IfcSpatialElement")
    for rule in rules:
        targets = [e for e in elements if applies(rule, e)]
        if targets:
            report.rules_applied += 1
        for el in targets:
            report.element_rule_pairs += 1
            psets = uel.get_psets(el)
            pset = psets.get(rule["pset"])
            if pset is None:
                out.append(_f(el, rule["id"], rule.get("severity", "error"),
                              f"missing property set {rule['pset']} (needs {rule['property']})", rule.get("agency", ""),
                              origin="mapping"))
                continue
            if rule["property"] not in pset:
                out.append(_f(el, rule["id"], rule.get("severity", "error"),
                              f"{rule['pset']} has no {rule['property']}", rule.get("agency", ""), origin="mapping"))
                continue
            value = pset[rule["property"]]
            # Validate primitive type before converting. Bounds refer to the
            # target mapping unit, so do not apply them to an unnormalized value.
            problem = value_problem(dict(rule, min=None, max=None), value)
            if problem:
                out.append(_f(el, rule["id"], rule.get("severity", "error"),
                              f"{rule['pset']}.{rule['property']} {problem}", rule.get("agency", ""), origin="mapping"))
                continue
            if rule.get("unit"):
                evidence = audit(m, el, rule)
                report.unit_results.append(evidence)
                if evidence["status"] == "unverified":
                    report.unit_unverified_pairs += 1
                    out.append(_f(el, rule["id"], "warning",
                                  f"{rule['pset']}.{rule['property']} unit unverified: {evidence['reason']}",
                                  rule.get("agency", ""), origin="mapping"))
                    continue
                if evidence["status"] == "verified":
                    value = evidence["normalized_value"]
            problem = value_problem(rule, value)
            if problem:
                out.append(_f(el, rule["id"], rule.get("severity", "error"),
                              f"{rule['pset']}.{rule['property']} {problem}", rule.get("agency", ""), origin="mapping"))
                continue
            report.passed_pairs += 1
    return out


def check(path, rules=None):
    m = ifcopenshell.open(str(path))
    rep = Report(file=Path(path).name, schema=m.schema, elements=len(m.by_type("IfcElement")))
    rep.findings += model_checks(m)
    rep.findings += property_checks(m, load_rules() if rules is None else rules, rep)
    return rep
