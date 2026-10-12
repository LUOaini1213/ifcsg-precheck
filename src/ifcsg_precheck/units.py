"""Read IFC measure/Unit semantics without guessing units from property names.

Physical targets cover the observed 4-Dec-2025 mapping catalogue. SHD is a
height datum, not a scale conversion; contextual/offset/unknown units stay
unverified. Label qualifiers keep their lexical contract, never become floats.
"""
import math
from dataclasses import dataclass

import ifcopenshell.util.element as uel

LENGTH = (1, 0, 0, 0, 0, 0, 0)
AREA = (2, 0, 0, 0, 0, 0, 0)
VOLUME = (3, 0, 0, 0, 0, 0, 0)
MASS = (0, 1, 0, 0, 0, 0, 0)
TIME = (0, 0, 1, 0, 0, 0, 0)
FORCE = (1, 1, -2, 0, 0, 0, 0)
PRESSURE = (-1, 1, -2, 0, 0, 0, 0)
FLOW = (3, 0, -1, 0, 0, 0, 0)
DIMENSIONS = dict(LENGTHUNIT=LENGTH, AREAUNIT=AREA, VOLUMEUNIT=VOLUME,
                  MASSUNIT=MASS, TIMEUNIT=TIME, FORCEUNIT=FORCE,
                  PRESSUREUNIT=PRESSURE, VOLUMETRICFLOWRATEUNIT=FLOW)
SI = {"METRE": ("LENGTHUNIT", 1.0, 1), "SQUARE_METRE": ("AREAUNIT", 1.0, 2),
      "CUBIC_METRE": ("VOLUMEUNIT", 1.0, 3), "GRAM": ("MASSUNIT", .001, 1),
      "SECOND": ("TIMEUNIT", 1.0, 1), "NEWTON": ("FORCEUNIT", 1.0, 1),
      "PASCAL": ("PRESSUREUNIT", 1.0, 1)}
PREFIX = {None: 1.0, "EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9,
          "MEGA": 1e6, "KILO": 1e3, "HECTO": 1e2, "DECA": 1e1, "DECI": 1e-1,
          "CENTI": 1e-2, "MILLI": 1e-3, "MICRO": 1e-6, "NANO": 1e-9,
          "PICO": 1e-12, "FEMTO": 1e-15, "ATTO": 1e-18}
MEASURES = {"IfcLengthMeasure": "LENGTHUNIT", "IfcPositiveLengthMeasure": "LENGTHUNIT",
            "IfcNonNegativeLengthMeasure": "LENGTHUNIT", "IfcAreaMeasure": "AREAUNIT",
            "IfcVolumeMeasure": "VOLUMEUNIT", "IfcMassMeasure": "MASSUNIT",
            "IfcTimeMeasure": "TIMEUNIT", "IfcForceMeasure": "FORCEUNIT",
            "IfcPressureMeasure": "PRESSUREUNIT", "IfcVolumetricFlowRateMeasure": "VOLUMETRICFLOWRATEUNIT"}
QUANTITIES = {"IfcQuantityLength": ("LengthValue", "IfcLengthMeasure"),
              "IfcQuantityArea": ("AreaValue", "IfcAreaMeasure"),
              "IfcQuantityVolume": ("VolumeValue", "IfcVolumeMeasure"),
              "IfcQuantityWeight": ("WeightValue", "IfcMassMeasure"),
              "IfcQuantityTime": ("TimeValue", "IfcTimeMeasure")}


@dataclass(frozen=True)
class Unit:
    name: str
    kind: str
    scale: float

    @property
    def dimensions(self):
        return DIMENSIONS[self.kind]


TARGETS = {"mm": Unit("mm", "LENGTHUNIT", .001), "m": Unit("m", "LENGTHUNIT", 1),
           "m2": Unit("m2", "AREAUNIT", 1), "m3": Unit("m3", "VOLUMEUNIT", 1),
           "kN": Unit("kN", "FORCEUNIT", 1000), "kPa": Unit("kPa", "PRESSUREUNIT", 1000),
           "hr": Unit("hr", "TIMEUNIT", 3600), "L": Unit("L", "VOLUMEUNIT", .001),
           "L/s": Unit("L/s", "VOLUMETRICFLOWRATEUNIT", .001),
           "tonnes": Unit("tonnes", "MASSUNIT", 1000)}


class UnitError(ValueError):
    """No safe scale/dimension interpretation is available."""


def target_unit(name):
    if name is None or str(name).strip().upper() in ("", "N.A", "NA", "NAN", "-"):
        return None
    name = str(name).strip().replace("²", "2").replace("³", "3")
    if name == "SHD m":
        raise UnitError("SHD m requires verified height-datum information; scale conversion is insufficient")
    if name not in TARGETS:
        raise UnitError("unsupported mapping unit: " + name)
    return TARGETS[name]


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnitError("conversion scale is not numeric")
    try:
        value = float(value)
    except (ValueError, OverflowError):
        raise UnitError("conversion scale is not finite")
    if not math.isfinite(value) or value <= 0:
        raise UnitError("conversion scale is not positive and finite")
    return value


def read_unit(entity, seen=frozenset()):
    if entity is None:
        raise UnitError("unit is missing")
    identity = entity.id()
    if identity in seen:
        raise UnitError("cyclic unit conversion")
    seen = seen | {identity}
    kind = getattr(entity, "UnitType", None)
    if kind not in DIMENSIONS:
        raise UnitError("unsupported IFC unit dimension: " + str(kind))
    if entity.is_a("IfcSIUnit"):
        if entity.Name not in SI or entity.Prefix not in PREFIX:
            raise UnitError("unsupported SI unit or prefix")
        expected, base, power = SI[entity.Name]
        if kind != expected:
            raise UnitError("SI unit name and UnitType have incompatible dimensions")
        return Unit((entity.Prefix + " " if entity.Prefix else "") + entity.Name,
                    kind, _positive(base * PREFIX[entity.Prefix] ** power))
    if entity.is_a("IfcConversionBasedUnitWithOffset"):
        raise UnitError("offset units are outside the supported catalogue")
    if entity.is_a("IfcConversionBasedUnit"):
        factor = entity.ConversionFactor
        if factor is None or factor.ValueComponent is None:
            raise UnitError("conversion factor is missing")
        base = read_unit(factor.UnitComponent, seen)
        dims = tuple(entity.Dimensions) if entity.Dimensions else None
        if base.dimensions != DIMENSIONS[kind] or dims != DIMENSIONS[kind]:
            raise UnitError("conversion-based unit has incompatible dimensions")
        declared = MEASURES.get(factor.ValueComponent.is_a())
        if declared and DIMENSIONS[declared] != base.dimensions:
            raise UnitError("conversion factor measure and base unit have incompatible dimensions")
        return Unit(entity.Name, kind, _positive(_positive(factor.ValueComponent.wrappedValue) * base.scale))
    if entity.is_a("IfcDerivedUnit"):
        if not entity.Elements:
            raise UnitError("derived unit has no elements")
        dims, scale = [0] * 7, 1.0
        try:
            for item in entity.Elements:
                exponent = item.Exponent
                if isinstance(exponent, bool) or not isinstance(exponent, int):
                    raise UnitError("derived unit exponent is not an integer")
                child = read_unit(item.Unit, seen)
                dims = [a + exponent * b for a, b in zip(dims, child.dimensions)]
                scale *= child.scale ** exponent
        except (OverflowError, ZeroDivisionError):
            raise UnitError("derived unit scale is not finite")
        if tuple(dims) != DIMENSIONS[kind]:
            raise UnitError("derived unit elements and UnitType have incompatible dimensions")
        return Unit(kind, kind, _positive(scale))
    raise UnitError("context-dependent or unsupported IFC unit")


def project_unit(model, kind):
    projects = model.by_type("IfcProject")
    if len(projects) != 1 or projects[0].UnitsInContext is None:
        raise UnitError("project unit context is missing or ambiguous")
    matches = [u for u in projects[0].UnitsInContext.Units if getattr(u, "UnitType", None) == kind]
    if len(matches) != 1:
        raise UnitError("project " + kind + " is missing or ambiguous")
    return read_unit(matches[0])


def _properties(product, pset, name):
    if product.is_a("IfcTypeObject"):
        definitions = getattr(product, "HasPropertySets", ()) or ()
    else:
        definitions = [r.RelatingPropertyDefinition for r in getattr(product, "IsDefinedBy", ())
                       if r.is_a("IfcRelDefinesByProperties")]
    return [(p, d.id()) for d in definitions if getattr(d, "Name", None) == pset
            for p in (getattr(d, "HasProperties", ()) or getattr(d, "Quantities", ()) or ()) if p.Name == name]


def property_entity(element, pset, name):
    own = _properties(element, pset, name)
    if own:
        matches, origin = own, "instance"
    else:
        parent = uel.get_type(element)
        matches, origin = _properties(parent, pset, name) if parent is not None else [], "type"
    if len(matches) != 1:
        raise UnitError("raw property definition is missing or ambiguous")
    return matches[0][0], origin


def property_measure(prop):
    if prop.is_a("IfcPropertySingleValue"):
        nominal = prop.NominalValue
        return (nominal.wrappedValue, nominal.is_a()) if nominal is not None else (None, None)
    quantity = QUANTITIES.get(prop.is_a())
    if quantity:
        attr, measure = quantity
        return getattr(prop, attr), measure
    raise UnitError("unit interpretation requires a supported single value or simple quantity")


def audit(model, element, rule):
    """Return raw IFC evidence and normalized value; never mutate the model."""
    record = {"guid": element.GlobalId or "", "pset": rule["pset"], "property": rule["property"],
              "rule": rule["id"], "target_unit": rule.get("unit"), "status": "unverified"}
    try:
        prop, origin = property_entity(element, rule["pset"], rule["property"])
        value, measure = property_measure(prop)
        record.update(raw_value=value, measure_type=measure, property_origin=origin,
                      property_id=prop.id(), explicit_unit=prop.Unit is not None)
        if prop.Unit is not None:
            record["explicit_unit_definition"] = {
                "id": prop.Unit.id(), "ifc_class": prop.Unit.is_a(),
                **{key: getattr(prop.Unit, key, None) for key in ("UnitType", "Name", "Prefix")}}
        expected = target_unit(rule.get("unit"))
        if expected is None:
            record["status"] = "not_required"
            return record
        source = None
        if prop.Unit is not None:
            source = read_unit(prop.Unit)
            record["unit_origin"] = "explicit_property"
        elif measure in MEASURES:
            source = project_unit(model, MEASURES[measure])
            record["unit_origin"] = "project"
        if rule.get("value_type") == "text":
            if source is not None and source.dimensions != expected.dimensions:
                raise UnitError("text qualifier and explicit IFC unit have incompatible dimensions")
            record.update(status="qualifier", reason="mapping Label unit is a lexical qualifier; no numeric conversion")
            if source is not None:
                record["source_unit"] = source.name
            return record
        if source is None:
            raise UnitError("generic scalar has no explicit physical unit; project length unit cannot be guessed")
        record["source_unit"] = source.name
        record.update(source_scale_si=source.scale, target_scale_si=expected.scale,
                      dimensions=source.dimensions)
        natural = MEASURES.get(measure)
        if natural is None and measure not in ("IfcReal", "IfcInteger", "IfcPositiveInteger"):
            raise UnitError("unsupported physical measure type: " + str(measure))
        if natural and DIMENSIONS[natural] != source.dimensions:
            raise UnitError("measure type and explicit IFC unit have incompatible dimensions")
        if source.dimensions != expected.dimensions:
            raise UnitError("source and mapping units have incompatible dimensions")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UnitError("physical property is not a numeric IFC value")
        factor = source.scale / expected.scale
        try:
            normalized = float(value) * factor
        except (OverflowError, ValueError):
            raise UnitError("normalized value is not finite")
        if not math.isfinite(normalized):
            raise UnitError("normalized value is not finite")
        record.update(status="verified", conversion_factor=factor, normalized_value=normalized)
    except UnitError as error:
        record["reason"] = str(error)
    return record


def make_unit(model, expected):
    """Create a property-local unit; leave project UnitsInContext unchanged."""
    name = expected.name
    simple = {"mm": ("LENGTHUNIT", "METRE", "MILLI"), "m": ("LENGTHUNIT", "METRE", None),
              "m2": ("AREAUNIT", "SQUARE_METRE", None), "m3": ("VOLUMEUNIT", "CUBIC_METRE", None),
              "kN": ("FORCEUNIT", "NEWTON", "KILO"), "kPa": ("PRESSUREUNIT", "PASCAL", "KILO")}
    if name in simple:
        kind, si_name, prefix = simple[name]
        return model.create_entity("IfcSIUnit", UnitType=kind, Name=si_name, Prefix=prefix)
    if name == "L/s":
        litre = make_unit(model, TARGETS["L"])
        second = model.create_entity("IfcSIUnit", UnitType="TIMEUNIT", Name="SECOND")
        elements = [model.create_entity("IfcDerivedUnitElement", Unit=litre, Exponent=1),
                    model.create_entity("IfcDerivedUnitElement", Unit=second, Exponent=-1)]
        return model.create_entity("IfcDerivedUnit", Elements=elements, UnitType="VOLUMETRICFLOWRATEUNIT")
    bases = {"L": ("VOLUMEUNIT", "CUBIC_METRE", None, "litre"),
             "hr": ("TIMEUNIT", "SECOND", None, "hour"),
             "tonnes": ("MASSUNIT", "GRAM", "KILO", "tonne")}
    kind, si_name, prefix, label = bases[name]
    base = model.create_entity("IfcSIUnit", UnitType=kind, Name=si_name, Prefix=prefix)
    factor = model.create_entity("IfcMeasureWithUnit", ValueComponent=model.create_entity("IfcReal", expected.scale),
                                 UnitComponent=base)
    return model.create_entity("IfcConversionBasedUnit", Dimensions=model.create_entity("IfcDimensionalExponents", *expected.dimensions),
                               UnitType=kind, Name=label, ConversionFactor=factor)
