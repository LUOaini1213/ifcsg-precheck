"""Stage only public authored-demo files; never upload a repository tree to Pages."""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report_demo import fingerprint, main as check_demo, source_hashes

PUBLIC_FILES = frozenset({"index.html", "before.html", "reviewed.html", "before.ifc", "derived.ifc", "reviewed.ifc",
                         "before.json", "derived.json", "reviewed.json", "authored_rules.json", "derivations.csv",
                         "derivations.csv.pending.json", "decisions.json", "independent_reopen.json", "manifest.json"})


def stage(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == ROOT.resolve() or output == source or source in output.parents or output in source.parents:
        raise ValueError("staging directory must be separate from the repository root and demo source")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("staging directory must be empty; no existing files are removed")
    entries = {p.name for p in source.iterdir()}
    if entries != PUBLIC_FILES:
        raise ValueError("demo inventory differs from public allowlist")
    for name in PUBLIC_FILES:
        path = source / name
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError("public demo must contain regular, unlinked files only: " + name)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest["source_sha256"] != source_hashes():
        raise ValueError("demo source fingerprint is stale")
    hashes = {name: fingerprint(source / name) for name in PUBLIC_FILES - {"manifest.json"}}
    if manifest["output_sha256"] != hashes:
        raise ValueError("demo output fingerprints differ")
    output.mkdir(parents=True, exist_ok=True)
    for name in sorted(PUBLIC_FILES):
        shutil.copyfile(source / name, output / name)
    (output / ".nojekyll").write_bytes(b"")
    return sorted(PUBLIC_FILES | {".nojekyll"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "demos/report-review")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    check_demo(["--output-dir", str(args.source), "--check"])
    files = stage(args.source, args.output)
    print("Staged only " + ", ".join(files))


if __name__ == "__main__":
    main()
