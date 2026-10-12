"""Independently reopen the authored STEP files; never trust a report or fill log alone."""
import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np

from ifcsg_precheck.units import property_entity, read_unit


def require(condition, message):
    if not condition:
        raise ValueError("Independent export verification failed: " + message)


def verify(directory, rows):
    directory = Path(directory)
    before = ifcopenshell.open(str(directory / "before.ifc"))
    derived = ifcopenshell.open(str(directory / "derived.ifc"))
    reviewed = ifcopenshell.open(str(directory / "reviewed.ifc"))
    objects = {e.Name: e for e in derived.by_type("IfcSlab")}
    settings = ifcopenshell.geom.settings()
    settings.set("convert-back-units", False)
    evidence = []
    for row in rows:
        element = derived.by_guid(row["guid"])
        prop, owner = property_entity(element, row["pset"], row["property"])
        require(owner == "instance", "write is not instance-owned")
        require(prop.NominalValue.wrappedValue == row["value"], "logged value differs from exported IFC")
        if row["source"].startswith("geometry"):
            unit = read_unit(prop.Unit)
            require(prop.NominalValue.is_a() == "IfcLengthMeasure", "geometry write lost its IFC measure type")
            require(math.isclose(row["source_value_si_m"] * row["conversion_factor"], row["value"]), "source conversion differs from written value")
            require(math.isclose(float(prop.NominalValue.wrappedValue) * unit.scale, .25), "exported physical thickness differs from authored source")
            shape = ifcopenshell.geom.create_shape(settings, element)
            vertices = np.asarray(shape.geometry.verts).reshape(-1, 3)
            require(math.isclose(float(np.ptp(vertices, axis=0).min()), .25), "independent geometry thickness differs")
            evidence.append(dict(guid=element.GlobalId, property=row["pset"] + "." + row["property"],
                                 measure_type=prop.NominalValue.is_a(), explicit_unit=unit.name,
                                 exported_value=prop.NominalValue.wrappedValue, physical_si_m=.25,
                                 independent_geometry_si_m=float(np.ptp(vertices, axis=0).min())))
    ready, _ = property_entity(objects["S-ready"], "SGPset_SlabDimension", "Thickness")
    original, _ = property_entity(next(e for e in before.by_type("IfcSlab") if e.Name == "S-ready"),
                                  "SGPset_SlabDimension", "Thickness")
    require(ready.NominalValue.is_a() == original.NominalValue.is_a() == "IfcLengthMeasure", "existing typed value changed")
    require(ready.NominalValue.wrappedValue == original.NominalValue.wrappedValue == 250., "existing value changed")
    require(read_unit(ready.Unit).name == read_unit(original.Unit).name == "MILLI METRE", "existing explicit override changed")
    require(read_unit(ready.Unit).scale == .001, "existing explicit override scale changed")
    deferred, _ = property_entity(objects["S-deferred"], "SGPset_SlabDimension", "Thickness")
    require(deferred.NominalValue is None and deferred.Unit.is_a("IfcContextDependentUnit"), "deferred source was silently filled or reinterpreted")
    generic, _ = property_entity(objects["S-deferred"], "Demo_Review", "Clearance")
    require(generic.NominalValue.is_a() == "IfcReal" and generic.Unit is None, "uncertain scalar was silently reinterpreted")
    resolved = next(e for e in reviewed.by_type("IfcSlab") if e.Name == "S-deferred")
    for pset, name, expected in (("SGPset_SlabDimension", "Thickness", .25), ("Demo_Review", "Clearance", .8)):
        prop, _ = property_entity(resolved, pset, name)
        require(prop.NominalValue.is_a() == "IfcLengthMeasure" and read_unit(prop.Unit).name == "METRE", "authored reviewed property is not typed metre length")
        require(read_unit(prop.Unit).scale == 1., "authored reviewed property unit scale differs")
        require(math.isclose(prop.NominalValue.wrappedValue, expected), "authored reviewed property value differs")
    return dict(method="Fresh ifcopenshell.open of all three STEP outputs; property-local units and geometry read independently",
                verified_geometry_writes=evidence, preserved_explicit_mm_override=True,
                unresolved_sources_preserved_before_authored_review=True,
                authored_review_typed_values_verified=True)
