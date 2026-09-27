"""Generate a small IFC4 building for demonstration and tests, with known defects.

Two storeys, walls, a slab, spaces and four doors. Door properties follow the IFC+SG names; the defects are planted
on purpose so the checker's output can be compared with a known answer:
  D-03  has no SGPset_DoorDimension.ClearWidth
  D-04  stores SGPset_DoorDimension.ClearWidth as text ("1000 mm") instead of a number
  D-02  has FireRating "1 hr"; the mapping's accepted values are "0.5", "1", ... "4" with the unit kept separately
  W-X   is not contained in any storey
  no IfcMapConversion (georeference warning)
"""
import ifcopenshell
import ifcopenshell.api as api

PLANTED = {"D-02": "FireRating format", "D-03": "missing ClearWidth", "D-04": "ClearWidth type", "W-X": "not contained",
           "map": "no georeference"}


def build(path):
    f = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name="Sample block")
    api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETERS"})
    api.run("context.add_context", f, context_type="Model")
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Block A")
    api.run("aggregate.assign_object", f, products=[site], relating_object=project)
    api.run("aggregate.assign_object", f, products=[building], relating_object=site)
    storeys = []
    for name, elev in (("L1", 0.0), ("L2", 3500.0)):
        s = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=name)
        s.Elevation = elev
        api.run("aggregate.assign_object", f, products=[s], relating_object=building)
        storeys.append(s)

    def element(cls, name, storey, predefined=None):
        e = api.run("root.create_entity", f, ifc_class=cls, name=name, predefined_type=predefined)
        if storey is not None:
            api.run("spatial.assign_container", f, products=[e], relating_structure=storey)
        return e

    def pset(e, name, props):
        p = api.run("pset.add_pset", f, product=e, name=name)
        api.run("pset.edit_pset", f, pset=p, properties=props)

    for i, st in enumerate(storeys, start=1):
        for j in range(2):
            w = element("IfcWall", f"W-{i}{j}", st, "SOLIDWALL")
            pset(w, "SGPset_WallDimension", {"Thickness": 200.0})
        sp = element("IfcSpace", f"SP-{i}", None, "INTERNAL")
        api.run("aggregate.assign_object", f, products=[sp], relating_object=st)
        pset(sp, "SGPset_Space", {"SpaceName": "OFFICE"})
        pset(sp, "SGPset_SpaceDimension", {"Area": 120.0})
    slab = element("IfcSlab", "S-2", storeys[1], "FLOOR")
    pset(slab, "SGPset_SlabDimension", {"Thickness": 150.0})

    doors = {"D-01": (1000.0, 2100.0, "1"), "D-02": (900.0, 2100.0, "1 hr"), "D-03": (None, 2100.0, "1"),
             "D-04": ("1000 mm", 2100.0, "0.5")}
    for k, (name, (width, height, rating)) in enumerate(doors.items()):
        d = element("IfcDoor", name, storeys[k % 2], "DOOR")
        dims = {"ClearHeight": height}
        if width is not None:
            dims["ClearWidth"] = width
        pset(d, "SGPset_DoorDimension", dims)
        pset(d, "Pset_DoorCommon", {"FireRating": rating, "FireExit": k == 0})
    element("IfcWall", "W-X", None, "SOLIDWALL")   # planted: not contained in a storey
    f.write(str(path))
    return path
