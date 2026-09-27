"""Fill IFC+SG properties that can be derived from data already in the model, and log where each value came from.

Only values with a traceable source are written; everything else stays for the designer to fill:
  - dimensions (mm) from the element's body geometry, measured on an oriented bounding box (principal axes of the
    vertices), so skewed or curved members are measured along themselves rather than along the world axes:
      slab Thickness = smallest extent; beam Depth = extent square to the member axis nearest vertical, Width =
      the other short extent;
      column Width/Breadth = the two short extents; pile Length = longest extent; railing Height = upright extent square to its axis
  - Mark from the element's Tag, else its Name
  - MaterialGrade from Pset_ConcreteElementGeneral.StrengthClass, written as the EN 206 cylinder/cube pair ("C50" -> "C50/60")
  - ConstructionMethod from Pset_ConcreteElementGeneral.CastingMethod (INSITU -> CIS, PRECAST -> PC)
  - LoadBearing from the element's Pset_<Class>Common.LoadBearing
Existing values are never overwritten. The log (CSV) lists element, property, value and source for review.
"""
import csv
from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import ifcopenshell.geom
import ifcopenshell.util.element as uel
import numpy as np

EN206 = {"C12": "C12/15", "C16": "C16/20", "C20": "C20/25", "C25": "C25/30", "C30": "C30/37", "C32": "C32/40",
         "C35": "C35/45", "C40": "C40/50", "C45": "C45/55", "C50": "C50/60", "C55": "C55/67", "C60": "C60/75",
         "C70": "C70/85", "C80": "C80/95", "C90": "C90/105"}
CASTING = {"INSITU": "CIS", "IN_SITU": "CIS", "IN-SITU": "CIS", "PRECAST": "PC"}


def extents_mm(settings, el):
    """Oriented-bounding-box extents in mm along the principal axes of the body geometry, or None.

    Returns (extents sorted ascending, extent along the principal axis closest to vertical, excluding the longest
    axis). The second value is a member's depth measured square to its own axis, so a beam on a grade or with
    superelevation is not credited with the height difference between its ends (checked against bridge-bim's
    design girder depth of 2.00 m)."""
    try:
        shape = ifcopenshell.geom.create_shape(settings, el)
    except Exception:
        return None
    v = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
    if len(v) < 4:
        return None
    c = v - v.mean(axis=0)
    _, _, axes = np.linalg.svd(c, full_matrices=False)       # rows: principal axes, longest first
    proj = c @ axes.T
    ext = (proj.max(axis=0) - proj.min(axis=0)) * 1000.0
    cross = [1, 2]                                            # the two axes square to the longest one
    upright = max(cross, key=lambda i: abs(axes[i][2]))
    return np.sort(ext), ext[upright]


def concrete_grade(strength):
    s = str(strength or "").strip().upper().replace(" ", "")
    if "/" in s:
        return s if s.startswith("C") else None
    return EN206.get(s)


def derived(el, settings):
    """{(pset, property): (value, source)} that can be derived for this element."""
    out = {}
    psets = uel.get_psets(el)
    cls = el.is_a()
    mark = el.Tag or el.Name
    dim_pset = {"IfcSlab": "SGPset_SlabDimension", "IfcBeam": "SGPset_BeamDimension", "IfcColumn": "SGPset_ColumnDimension",
                "IfcPile": "SGPset_PileDimension", "IfcRailing": "SGPset_RailingDimension"}.get(cls)
    if dim_pset and mark and cls != "IfcRailing":
        out[(dim_pset, "Mark")] = (mark, "Tag" if el.Tag else "Name")
    if dim_pset:
        e = extents_mm(settings, el)
        if e:
            ext, upright = e
            if cls == "IfcSlab":
                out[(dim_pset, "Thickness")] = (round(ext[0]), "geometry: smallest extent")
            elif cls == "IfcBeam":
                out[(dim_pset, "Depth")] = (round(upright), "geometry: extent square to the member axis, nearest vertical")
                width = ext[0] + ext[1] - upright
                out[(dim_pset, "Width")] = (round(width), "geometry: other extent square to the member axis")
            elif cls == "IfcColumn":
                out[(dim_pset, "Width")] = (round(ext[1]), "geometry: middle extent")
                out[(dim_pset, "Breadth")] = (round(ext[0]), "geometry: smallest extent")
            elif cls == "IfcPile":
                out[(dim_pset, "Length")] = (round(ext[2]), "geometry: longest extent")
            elif cls == "IfcRailing":
                out[(dim_pset, "Height")] = (round(upright), "geometry: extent square to the railing axis, nearest vertical")
    concrete = psets.get("Pset_ConcreteElementGeneral", {})
    grade = concrete_grade(concrete.get("StrengthClass"))
    if grade and cls in ("IfcSlab", "IfcBeam", "IfcColumn", "IfcPile", "IfcWall"):
        out[("SGPset_Material", "MaterialGrade")] = (grade, "Pset_ConcreteElementGeneral.StrengthClass (EN 206 pair)")
    method = CASTING.get(str(concrete.get("CastingMethod", "")).upper())
    own = {"IfcSlab": "SGPset_Slab", "IfcBeam": "SGPset_Beam", "IfcColumn": "SGPset_Column", "IfcPile": "SGPset_Pile"}.get(cls)
    if method and own:
        out[(own, "ConstructionMethod")] = (method, "Pset_ConcreteElementGeneral.CastingMethod")
    common = psets.get(f"Pset_{cls[3:]}Common", {})
    if "LoadBearing" in common and own == "SGPset_Slab":
        out[(own, "LoadBearing")] = (bool(common["LoadBearing"]), f"Pset_{cls[3:]}Common.LoadBearing")
    return out


def enrich(src, dst, log_path, wanted=None):
    """wanted: set of (entity, pset, property) that the rules ask for; None = everything derivable."""
    m = ifcopenshell.open(str(src))
    settings = ifcopenshell.geom.settings()
    rows = []
    for el in m.by_type("IfcElement"):
        existing = uel.get_psets(el)
        todo = {}
        for (pset, prop), (value, source) in derived(el, settings).items():
            if wanted is not None and (el.is_a(), pset, prop) not in wanted:
                continue
            if prop in existing.get(pset, {}) and existing[pset][prop] not in (None, ""):
                continue
            todo.setdefault(pset, {})[prop] = value
            rows.append({"guid": el.GlobalId, "class": el.is_a(), "name": el.Name or "", "pset": pset, "property": prop,
                         "value": value, "source": source})
        for pset, props in todo.items():
            pid = existing.get(pset, {}).get("id")
            p = m.by_id(pid) if pid else api.run("pset.add_pset", m, product=el, name=pset)
            api.run("pset.edit_pset", m, pset=p, properties=props)
    m.write(str(dst))
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["guid", "class", "name", "pset", "property", "value", "source"])
        w.writeheader()
        w.writerows(rows)
    return rows
