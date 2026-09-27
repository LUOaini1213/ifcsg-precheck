"""Turn BCA's IFC+SG Excel mapping (the "Industry Mapping") into check rules.

The mapping is published at https://info.corenet.gov.sg/ifc-sg/templates--apps-and-more/ifc-sg-excel-mapping-file .
BCA's terms of use do not allow it to be republished, so this repository ships the converter, not the mapping:
`python -m ifcsg_precheck.cli rules <mapping.xlsx>` writes rules/ifcsg_mapping.json locally (git-ignored).

One rule per (entity, sub type, property set, property, agency). Sub types marked "*" in the mapping are
USERDEFINED types, matched on the element's ObjectType; plain sub types are PredefinedType values; "N.A" means any.
Accepted values become an allowed-values check only when they are a short list (for example "Single, End, Interior");
descriptive entries such as ranges or notes are kept as text for the report but not enforced.
"""
import json
import re
from pathlib import Path

import pandas as pd

SHEET = "CX Pilot Mapping"
AGENCY = {"NPARKS": "NParks"}  # the mapping spells NParks two ways
NUMBER_TYPES = {"length", "area", "volume", "real", "integer", "count", "number", "positive length", "ratio",
                "thermal transmittance", "force", "pressure", "angle", "plane angle", "mass", "power", "time"}


def _cells(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    parts = re.split(r"[\n,;/]+", str(value))
    return [p.strip() for p in parts if p.strip() and p.strip().upper() not in ("N.A", "NA", "-")]


def value_type(prop_type):
    t = str(prop_type or "").strip().lower()
    if t == "boolean":
        return "boolean"
    if t in NUMBER_TYPES:
        return "number"
    if t in ("label", "text", "identifier"):
        return "text"
    return None


def allowed(accepted, vtype):
    if vtype != "text" or accepted is None or (isinstance(accepted, float) and pd.isna(accepted)):
        return None
    items = [x.strip() for x in re.split(r"[,;\n]+", str(accepted)) if x.strip()]
    if len(items) < 2 or any(len(x) > 40 for x in items) or any(re.search(r"\bto\b|e\.g\.|refer|etc", x, re.I) for x in items):
        return None
    return items


def convert(xlsx, out=None):
    df = pd.read_excel(xlsx, sheet_name=SHEET)
    cols = {c: re.sub(r"\s+", " ", str(c)).strip() for c in df.columns}
    df = df.rename(columns=cols)
    pick = lambda *names: next(c for c in df.columns if any(c.lower().startswith(n.lower()) for n in names))
    c_sn, c_ag, c_comp = pick("S/N"), pick("Agency"), pick("Identified Component")
    c_ent, c_sub, c_pset = pick("IFC4 Entities"), pick("IFC Sub Types"), pick("Property Set")
    c_prop, c_type, c_unit, c_acc = pick("Property Name"), pick("Property Type"), pick("Property Unit"), pick("Accepted Values")
    rules, seen = [], set()
    for r in df.itertuples(index=False):
        row = dict(zip(df.columns, r))
        pset, prop = str(row[c_pset]).strip(), str(row[c_prop]).strip()
        # Group header rows read "Please refer to property sets below"; only real property sets become rules.
        if not re.match(r"^(SGPset_|Pset_|Qto_)\w+$", pset) or not re.match(r"^\w+$", prop):
            continue
        entities = [e for e in _cells(row[c_ent]) if e.startswith("Ifc")]
        subs = _cells(row[c_sub]) or [None]
        vtype = value_type(row[c_type])
        for ent in entities:
            for sub in subs:
                key = (ent, sub, pset, prop, str(row[c_ag]).strip())
                if key in seen:
                    continue
                seen.add(key)
                rules.append({
                    "id": f"CX{int(row[c_sn]) if str(row[c_sn]).isdigit() else row[c_sn]}",
                    "agency": AGENCY.get(str(row[c_ag]).strip().upper(), str(row[c_ag]).strip()),
                    "component": str(row[c_comp]).strip(),
                    "entity": ent,
                    "predefined_type": sub.lstrip("*") if sub else None,
                    "userdefined": bool(sub and sub.startswith("*")),
                    "pset": pset, "property": prop, "value_type": vtype,
                    "unit": None if str(row[c_unit]).upper() in ("N.A", "NAN") else str(row[c_unit]),
                    "allowed_values": allowed(row[c_acc], vtype),
                    "severity": "error"})
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(rules, indent=1), encoding="utf-8")
    return rules
