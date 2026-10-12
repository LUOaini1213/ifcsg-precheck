"""Fill IFC+SG properties that can be derived from data already in the model, and log where each value came from.

Only values with a traceable source are written; everything else stays for the designer to fill:
  - dimensions (mm) from the element's body geometry, measured on an oriented bounding box (principal axes of the
    vertices), so skewed or curved members are measured along themselves rather than along the world axes:
      slab Thickness = smallest extent; beam Depth = extent square to the member axis nearest vertical, Width =
      the other short extent;
      column Width/Breadth = the two short extents; pile Length = longest extent; railing Height = upright extent square to its axis
  - Mark from the element's first non-blank Tag or Name, preserving the original value
  - MaterialGrade from Pset_ConcreteElementGeneral.StrengthClass, written as the EN 206 cylinder/cube pair ("C50" -> "C50/60")
  - ConstructionMethod from Pset_ConcreteElementGeneral.CastingMethod (INSITU -> CIS, PRECAST -> PC)
  - LoadBearing from the element's Pset_<Class>Common.LoadBearing
Existing non-empty values are preserved. Derived values are written only to the individual occurrence, never to a
type or a property set shared with another object. The CSV lists element, property, value and source for review.
"""
import csv
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import ifcopenshell.geom
import ifcopenshell.util.element as uel
import numpy as np
from .check import applies
from .units import LENGTH, TARGETS, UnitError, make_unit, property_entity, project_unit, read_unit, target_unit

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
    if len(v) < 4 or not np.isfinite(v).all():
        return None
    c = v - v.mean(axis=0)
    try:
        _, _, axes = np.linalg.svd(c, full_matrices=False)   # rows: principal axes, longest first
    except np.linalg.LinAlgError:
        return None
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


def derived(el, settings, geometry_allowed=True):
    """{(pset, property): (value, source)} that can be derived for this element."""
    out = {}
    psets = uel.get_psets(el)
    cls = el.is_a()
    mark, mark_source = None, None
    for candidate, source in ((el.Tag, "Tag"), (el.Name, "Name")):
        if isinstance(candidate, str) and candidate.strip():
            mark, mark_source = candidate, source
            break
    dim_pset = {"IfcSlab": "SGPset_SlabDimension", "IfcBeam": "SGPset_BeamDimension", "IfcColumn": "SGPset_ColumnDimension",
                "IfcPile": "SGPset_PileDimension", "IfcRailing": "SGPset_RailingDimension"}.get(cls)
    if dim_pset and mark and cls != "IfcRailing":
        out[(dim_pset, "Mark")] = (mark, mark_source)
    if dim_pset:
        e = extents_mm(settings, el) if geometry_allowed else None
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
    load_bearing = common.get("LoadBearing")
    if isinstance(load_bearing, bool) and own == "SGPset_Slab":
        out[(own, "LoadBearing")] = (load_bearing, f"Pset_{cls[3:]}Common.LoadBearing")
    return out


def enrich(src, dst, log_path, wanted=None, *, rules=None, pending=None):
    """wanted: set of (entity, pset, property) that the rules ask for; None = everything derivable."""
    m = ifcopenshell.open(str(src))
    settings = ifcopenshell.geom.settings()
    settings.set("convert-back-units", False)  # geometry engine returns SI metres
    deferred = []
    try:
        geometry_unit = project_unit(m, "LENGTHUNIT")
        geometry_error = None
    except UnitError as error:
        geometry_unit, geometry_error = None, str(error)
    rows = []
    target_cache = {}
    for el in m.by_type("IfcElement"):
        existing = uel.get_psets(el)
        todo = {}
        candidates = derived(el, settings, geometry_allowed=geometry_error is None)
        dimensions = {"IfcSlab": ("Thickness",), "IfcBeam": ("Depth", "Width"),
                      "IfcColumn": ("Width", "Breadth"), "IfcPile": ("Length",), "IfcRailing": ("Height",)}
        # Missing/unreliable geometry remains visible as deferred work. Never
        # let the geometry kernel's implicit unit fallback invent a scale.
        for prop in dimensions.get(el.is_a(), ()):
            key = ("SGPset_" + el.is_a()[3:] + "Dimension", prop)
            candidates.setdefault(key, (None, "geometry"))
        for (pset, prop), (value, source) in candidates.items():
            if rules is None:
                if wanted is not None and (el.is_a(), pset, prop) not in wanted:
                    continue
            matching = [r for r in rules if r["pset"] == pset and r["property"] == prop and applies(r, el)] if rules is not None else None
            if matching is not None and not matching:
                continue
            current = existing.get(pset, {}).get(prop)
            if current is not None and (not isinstance(current, str) or current.strip()):
                continue
            row = {"guid": el.GlobalId, "class": el.is_a(), "name": el.Name or "", "pset": pset, "property": prop,
                   "value": value, "source": source}
            written = value
            if source.startswith("geometry"):
                try:
                    if geometry_error:
                        raise UnitError("geometry source unit unverified: " + geometry_error)
                    if value is None or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                        raise UnitError("body geometry does not provide a reliable positive extent")
                    # The legacy Python API's documented dimensions profile is
                    # mm. CLI/evaluation always use the actual mapping rules.
                    targets = [target_unit(r.get("unit")) for r in matching] if matching is not None else [TARGETS["mm"]]
                    if matching is not None and any(r.get("value_type") != "number" for r in matching):
                        raise UnitError("dimension target is not a numeric mapping property")
                    if any(t is None or t.dimensions != LENGTH for t in targets):
                        raise UnitError("dimension target unit is missing or has incompatible dimensions")
                    # Existing legitimate explicit overrides are preserved.
                    # A blank property with an unknown Unit is not silently
                    # reinterpreted or repaired by the enrichment operation.
                    explicit = None
                    if prop in existing.get(pset, {}):
                        raw, _ = property_entity(el, pset, prop)
                        if not raw.is_a("IfcPropertySingleValue"):
                            raise UnitError("blank dimension is not a single-value property")
                        explicit = raw.Unit
                    if explicit is not None:
                        write_unit = read_unit(explicit)
                        if write_unit.dimensions != LENGTH:
                            raise UnitError("blank property unit has incompatible dimensions")
                        unit_entity = explicit
                    else:
                        write_unit = sorted(targets, key=lambda t: t.name)[0]
                        unit_entity = target_cache.get(write_unit.name)
                        if unit_entity is None:
                            unit_entity = make_unit(m, write_unit)
                            target_cache[write_unit.name] = unit_entity
                    si_value = float(value) * .001
                    value = si_value / write_unit.scale
                    if not np.isfinite(value):
                        raise UnitError("derived value is not finite in the output unit")
                    written = {"NominalValue": m.create_entity("IfcLengthMeasure", value), "Unit": unit_entity}
                    row.update(value=value, measure_type="IfcLengthMeasure", unit=write_unit.name,
                               geometry_project_unit=geometry_unit.name, source_unit="SI metre geometry",
                               source_value_si_m=si_value, conversion_factor=1 / write_unit.scale,
                               mapping_units=";".join(sorted({t.name for t in targets})))
                except UnitError as error:
                    deferred.append({"guid": el.GlobalId, "pset": pset, "property": prop,
                                     "status": "unverified", "reason": str(error)})
                    continue
            todo.setdefault(pset, {})[prop] = written
            rows.append(row)
        # The merged values above determine what is missing, but inherited IDs are never write targets.
        owned = uel.get_psets(el, should_inherit=False)
        for pset, props in todo.items():
            pid = owned.get(pset, {}).get("id")
            p = m.by_id(pid) if pid else api.run("pset.add_pset", m, product=el, name=pset)
            if uel.get_elements_by_pset(p) != {el}:
                p = api.run("pset.unshare_pset", m, products=[el], pset=p)[0]
            api.run("pset.edit_pset", m, pset=p, properties=props)
    m.write(str(dst))
    base_fields = ["guid", "class", "name", "pset", "property", "value", "source"]
    extra = sorted({k for r in rows for k in r} - set(base_fields))
    for row in rows:
        for key in extra:
            row.setdefault(key, "")
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=base_fields + extra)
        w.writeheader()
        w.writerows(rows)
    Path(str(log_path) + ".pending.json").write_text(json.dumps(deferred, ensure_ascii=False, indent=2), encoding="utf-8")
    if pending is not None:
        pending.extend(deferred)
    return rows
