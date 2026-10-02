"""Enrichment preserves inherited/shared properties while filling individual occurrences."""
import csv
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.api as api
import ifcopenshell.util.element as uel
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ifcsg_precheck.enrich import enrich

PSET = "SGPset_SlabDimension"
WANTED = {("IfcSlab", PSET, "Mark")}


def model_pair():
    model = api.run("project.create_file", version="IFC4")
    slab_type = api.run("root.create_entity", model, ifc_class="IfcSlabType", name="Shared slab type")
    first = api.run("root.create_entity", model, ifc_class="IfcSlab", name="Slab A")
    first.Tag = "TAG-A"
    second = api.run("root.create_entity", model, ifc_class="IfcSlab", name="Slab B")
    api.run("type.assign_type", model, related_objects=[first, second], relating_type=slab_type)
    return model, slab_type, first, second


def mark_pset(model, product, value):
    pset = api.run("pset.add_pset", model, product=product, name=PSET)
    api.run("pset.edit_pset", model, pset=pset,
            properties={"Mark": value, "DesignNote": "Keep this design note"}, should_purge=False)
    return pset


def roundtrip(model, tmp_path):
    source, output, log = tmp_path / "input.ifc", tmp_path / "output.ifc", tmp_path / "changes.csv"
    model.write(str(source))
    before = source.read_bytes()
    rows = enrich(source, output, log, WANTED)
    assert source.read_bytes() == before
    with log.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{key: str(value) for key, value in row.items()} for row in rows]
    return ifcopenshell.open(str(output)), rows, output


def expected_row(element, value, source):
    return {"guid": element.GlobalId, "class": "IfcSlab", "name": element.Name,
            "pset": PSET, "property": "Mark", "value": value, "source": source}


def assert_idempotent(output, model, tmp_path):
    again, log = tmp_path / "again.ifc", tmp_path / "again.csv"
    assert enrich(output, again, log, WANTED) == []
    with log.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == []
    repeated = ifcopenshell.open(str(again))
    assert len(list(repeated)) == len(list(model))
    for product in model.by_type("IfcElement") + model.by_type("IfcTypeObject"):
        assert uel.get_psets(repeated.by_guid(product.GlobalId), should_inherit=False) == \
            uel.get_psets(product, should_inherit=False)


@pytest.mark.parametrize("empty", [None, "", " \t "])
def test_empty_inherited_mark_is_filled_per_instance_without_changing_type(tmp_path, empty):
    model, slab_type, first, second = model_pair()
    type_pset = mark_pset(model, slab_type, empty)
    before = uel.get_psets(slab_type)

    result, rows, output = roundtrip(model, tmp_path)

    assert sorted(rows, key=lambda row: row["guid"]) == sorted(
        [expected_row(first, "TAG-A", "Tag"), expected_row(second, "Slab B", "Name")],
        key=lambda row: row["guid"])
    assert uel.get_psets(result.by_guid(slab_type.GlobalId)) == before
    instance_ids = set()
    for element, expected in ((first, "TAG-A"), (second, "Slab B")):
        kept = result.by_guid(element.GlobalId)
        own = uel.get_psets(kept, should_inherit=False)[PSET]
        assert own["Mark"] == expected
        assert own["id"] != type_pset.id()
        instance_ids.add(own["id"])
        assert uel.get_psets(kept)[PSET]["DesignNote"] == "Keep this design note"
        assert uel.get_elements_by_pset(result.by_id(own["id"])) == {kept}
    assert len(instance_ids) == 2
    assert_idempotent(output, result, tmp_path)


def test_filling_mark_preserves_future_inheritance_of_other_type_properties(tmp_path):
    model, slab_type, first, second = model_pair()
    type_pset = mark_pset(model, slab_type, None)
    api.run("pset.edit_pset", model, pset=type_pset, properties={"Thickness": 175})

    result, rows, output = roundtrip(model, tmp_path)

    assert sorted(rows, key=lambda row: row["guid"]) == sorted(
        [expected_row(first, "TAG-A", "Tag"), expected_row(second, "Slab B", "Name")],
        key=lambda row: row["guid"])
    for element in (first, second):
        assert uel.get_psets(result.by_guid(element.GlobalId))[PSET]["Thickness"] == 175

    # A later type-level design revision must still reach occurrences after Mark enrichment.
    type_values = uel.get_psets(result.by_guid(slab_type.GlobalId), should_inherit=False)[PSET]
    api.run("pset.edit_pset", result, pset=result.by_id(type_values["id"]), properties={"Thickness": 225})
    updated = tmp_path / "updated-type.ifc"
    result.write(str(updated))
    revised = ifcopenshell.open(str(updated))
    for element, mark in ((first, "TAG-A"), (second, "Slab B")):
        effective = uel.get_psets(revised.by_guid(element.GlobalId))[PSET]
        assert effective["Thickness"] == 225
        assert effective["Mark"] == mark
    assert_idempotent(updated, revised, tmp_path)


@pytest.mark.parametrize("with_instance_pset", [False, True])
def test_effective_inherited_value_is_kept_even_when_instance_has_other_properties(tmp_path, with_instance_pset):
    model, slab_type, first, second = model_pair()
    mark_pset(model, slab_type, "TYPE-MARK")
    if with_instance_pset:
        own = api.run("pset.add_pset", model, product=first, name=PSET)
        api.run("pset.edit_pset", model, pset=own, properties={"Thickness": 175})
    count = len(list(model))
    before = {product.GlobalId: uel.get_psets(product, should_inherit=False)
              for product in (slab_type, first, second)}

    result, rows, output = roundtrip(model, tmp_path)

    assert rows == []
    assert len(list(result)) == count
    for guid, values in before.items():
        assert uel.get_psets(result.by_guid(guid), should_inherit=False) == values
    assert_idempotent(output, result, tmp_path)


@pytest.mark.parametrize("value", ["DESIGNER-MARK", 0, False])
def test_effective_instance_value_is_not_overwritten(tmp_path, value):
    model, slab_type, first, second = model_pair()
    mark_pset(model, slab_type, "TYPE-MARK")
    mark_pset(model, first, value)
    count = len(list(model))

    result, rows, output = roundtrip(model, tmp_path)

    assert rows == []
    assert len(list(result)) == count
    kept = uel.get_psets(result.by_guid(first.GlobalId), should_inherit=False)[PSET]["Mark"]
    assert kept == value and type(kept) is type(value)
    assert uel.get_psets(result.by_guid(second.GlobalId))[PSET]["Mark"] == "TYPE-MARK"
    assert_idempotent(output, result, tmp_path)


@pytest.mark.parametrize("empty", [None, "", " \t "])
def test_empty_instance_override_is_fillable_without_touching_valid_type(tmp_path, empty):
    model, slab_type, first, second = model_pair()
    mark_pset(model, slab_type, "TYPE-MARK")
    own = mark_pset(model, first, empty)
    type_before = uel.get_psets(slab_type)

    result, rows, output = roundtrip(model, tmp_path)

    assert rows == [expected_row(first, "TAG-A", "Tag")]
    own_after = uel.get_psets(result.by_guid(first.GlobalId), should_inherit=False)[PSET]
    assert own_after["id"] == own.id()
    assert own_after["Mark"] == "TAG-A"
    assert own_after["DesignNote"] == "Keep this design note"
    assert uel.get_psets(result.by_guid(slab_type.GlobalId)) == type_before
    assert uel.get_psets(result.by_guid(second.GlobalId))[PSET]["Mark"] == "TYPE-MARK"
    assert_idempotent(output, result, tmp_path)


@pytest.mark.parametrize("share_with_type", [False, True])
def test_directly_shared_pset_is_unshared_before_writing_each_occurrence(tmp_path, share_with_type):
    model, slab_type, first, second = model_pair()
    shared = mark_pset(model, first, None)
    api.run("pset.assign_pset", model, products=[second], pset=shared)
    if share_with_type:
        api.run("pset.assign_pset", model, products=[slab_type], pset=shared)
    type_before = uel.get_psets(slab_type)

    result, rows, output = roundtrip(model, tmp_path)

    assert sorted(rows, key=lambda row: row["guid"]) == sorted(
        [expected_row(first, "TAG-A", "Tag"), expected_row(second, "Slab B", "Name")],
        key=lambda row: row["guid"])
    pset_ids = set()
    for element, expected in ((first, "TAG-A"), (second, "Slab B")):
        kept = result.by_guid(element.GlobalId)
        own = uel.get_psets(kept, should_inherit=False)[PSET]
        assert own["Mark"] == expected
        assert own["DesignNote"] == "Keep this design note"
        pset_ids.add(own["id"])
        assert uel.get_elements_by_pset(result.by_id(own["id"])) == {kept}
    assert len(pset_ids) == 2
    assert uel.get_psets(result.by_guid(slab_type.GlobalId)) == type_before
    assert_idempotent(output, result, tmp_path)


@pytest.mark.parametrize("inherited", [False, True], ids=["occurrence", "type"])
@pytest.mark.parametrize("value", [None, "", "False", 0, 1, True, False],
                         ids=["unknown", "empty", "text-false", "zero", "one", "true", "false"])
def test_load_bearing_requires_a_boolean_source_and_logs_only_verified_values(tmp_path, inherited, value):
    model, slab_type, first, second = model_pair()
    owner = slab_type if inherited else first
    source_pset = api.run("pset.add_pset", model, product=owner, name="Pset_SlabCommon")
    # Preserve malformed input types exactly, without the API's standard-property template coercion.
    if value is None:
        nominal = None
    else:
        ifc_type = "IfcBoolean" if isinstance(value, bool) else "IfcInteger" if isinstance(value, int) else "IfcLabel"
        nominal = model.create_entity(ifc_type, value)
    source_pset.HasProperties = [model.create_entity("IfcPropertySingleValue", Name="LoadBearing", NominalValue=nominal)]
    source, output, log = tmp_path / "input.ifc", tmp_path / "output.ifc", tmp_path / "changes.csv"
    model.write(str(source))
    original_bytes = source.read_bytes()
    loaded = ifcopenshell.open(str(source))
    actual = uel.get_psets(loaded.by_guid(first.GlobalId))["Pset_SlabCommon"]["LoadBearing"]
    assert actual == value and type(actual) is type(value)
    before = uel.get_psets(loaded.by_guid(owner.GlobalId), should_inherit=False)
    wanted = {("IfcSlab", "SGPset_Slab", "LoadBearing")}

    rows = enrich(source, output, log, wanted)

    assert source.read_bytes() == original_bytes
    result = ifcopenshell.open(str(output))
    assert uel.get_psets(result.by_guid(owner.GlobalId), should_inherit=False).get("Pset_SlabCommon") == before["Pset_SlabCommon"]
    expected = []
    for element in (first, second):
        own = uel.get_psets(result.by_guid(element.GlobalId), should_inherit=False)
        if isinstance(value, bool) and (inherited or element == first):
            assert own["SGPset_Slab"]["LoadBearing"] is value
            expected.append({"guid": element.GlobalId, "class": "IfcSlab", "name": element.Name,
                             "pset": "SGPset_Slab", "property": "LoadBearing", "value": value,
                             "source": "Pset_SlabCommon.LoadBearing"})
        else:
            assert "SGPset_Slab" not in own
    assert sorted(rows, key=lambda row: row["guid"]) == sorted(expected, key=lambda row: row["guid"])
    assert all(type(row["value"]) is bool for row in rows)
    with log.open(encoding="utf-8", newline="") as handle:
        logged = list(csv.DictReader(handle))
    assert sorted(logged, key=lambda row: row["guid"]) == sorted(
        [{key: str(item) for key, item in row.items()} for row in expected], key=lambda row: row["guid"])
    again_log = tmp_path / "again.csv"
    assert enrich(output, tmp_path / "again.ifc", again_log, wanted) == []
    with again_log.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == []


@pytest.mark.parametrize("tag,name,expected,source", [
    (" \t ", "Slab A", "Slab A", "Name"),
    (" \t ", " \t ", None, None),
    (" TAG-A ", "Slab A", " TAG-A ", "Tag"),
    ("\t", " Slab A ", " Slab A ", "Name"),
], ids=["blank-tag-falls-back", "both-blank", "tag-preserved", "name-preserved"])
def test_mark_uses_first_nonblank_source_and_does_not_repeat_empty_writes(tmp_path, tag, name, expected, source):
    model = api.run("project.create_file", version="IFC4")
    slab = api.run("root.create_entity", model, ifc_class="IfcSlab", name=name)
    slab.Tag = tag

    result, rows, output = roundtrip(model, tmp_path)

    kept = result.by_guid(slab.GlobalId)
    assert kept.Tag == tag and kept.Name == name
    own = uel.get_psets(kept, should_inherit=False)
    if expected is None:
        assert rows == []
        assert PSET not in own
    else:
        assert rows == [expected_row(slab, expected, source)]
        assert own[PSET]["Mark"] == expected
    assert_idempotent(output, result, tmp_path)
