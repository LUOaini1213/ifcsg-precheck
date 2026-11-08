"""Compare principal-axis and world-axis depth of bridge-bim's T-girders.

The enrichment derives a beam's Depth on its principal axes (src/ifcsg_precheck/enrich.py,
``extents_mm``). This script measures the same girders both ways and writes a small aggregate,
so the README's world-axis comparison traces to a committed file.

    python scripts/girder_axes.py ../bridge-bim/model/bridge_bim.ifc \
        --out reports/girder-axes-20261108/girder_axes.json
    python scripts/girder_axes.py ../bridge-bim/model/bridge_bim.ifc \
        --out reports/girder-axes-20261108/girder_axes.json --check

The input is bridge-bim commit b6456b34 (the 2026-10-12 unit-review model; SHA-256 recorded
in the output). No BCA mapping data is needed.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ifcopenshell  # noqa: E402
import ifcopenshell.geom  # noqa: E402
import ifcopenshell.util.shape  # noqa: E402
import numpy as np  # noqa: E402
from ifcsg_precheck.enrich import extents_mm  # noqa: E402

PREDEFINED = "T_BEAM"
PINNED_SHA256 = "139931fd19950fad2c879d74f5859b78272bdeb6f1dce9903e5ec533872fabf2"
PINNED_SOURCE = ("https://github.com/LUOaini1213/bridge-bim/blob/"
                 "b6456b344b09a92620cc5d4a4cfb2a3be963b147/model/bridge_bim.ifc")


def measure(path):
    model = ifcopenshell.open(str(path))
    local = ifcopenshell.geom.settings()
    local.set("convert-back-units", False)        # same settings as enrich(): SI metres
    girders = [b for b in model.by_type("IfcBeam") if b.PredefinedType == PREDEFINED]
    depth, width, vertical, skipped = [], [], [], 0
    for beam in sorted(girders, key=lambda b: b.GlobalId):
        e = extents_mm(local, beam)
        if not e:
            skipped += 1
            continue
        ext, upright = e
        depth.append(round(float(upright)))
        width.append(round(float(ext[0] + ext[1] - upright)))
        # World-axis extent: the same body vertices placed by the shape's world transformation.
        shape = ifcopenshell.geom.create_shape(local, beam)
        verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
        placed = np.c_[verts, np.ones(len(verts))] @ ifcopenshell.util.shape.get_shape_matrix(shape).T
        vertical.append(round(float(placed[:, 2].max() - placed[:, 2].min()) * 1000.0))

    def span(values):
        return {"min": min(values), "max": max(values)} if values else None

    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {
        "model": {"file": Path(path).name, "sha256": sha, "source": PINNED_SOURCE if sha == PINNED_SHA256 else None},
        "selection": f"IfcBeam with PredefinedType {PREDEFINED}",
        "girders": len(girders),
        "measured": len(depth),
        "skipped_no_geometry": skipped,
        "principal_axis_depth_mm": span(depth),
        "principal_axis_width_mm": span(width),
        "world_vertical_extent_mm": span(vertical),
        "rounding": "nearest millimetre, as in enrich()",
        "environment": {"ifcopenshell": ifcopenshell.version, "numpy": np.__version__,
                        "python": ".".join(map(str, sys.version_info[:2]))},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("model", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="recompute and compare with the committed --out file")
    args = parser.parse_args(argv)
    result = measure(args.model)
    if args.check:
        stored = json.loads(args.out.read_text(encoding="utf-8"))
        keys = [k for k in result if k != "environment"]
        changed = [k for k in keys if stored.get(k) != result[k]]
        if changed:
            raise SystemExit("girder measurement differs from " + str(args.out) + ": " + ", ".join(changed))
        print("PASS:", args.out, "reproduced")
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
