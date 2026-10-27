"""Stage/finalize a relocatable Windows x64 archive; never packages a venv.

Only the independent SLAM application, its runtime, selected synthetic example
and C1 bridge are copied. The research repository is excluded by an allowlist.
Destinations must be new; existing archives are never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ("01_START_SIMULATION.cmd", "02_START_DEMO.cmd",
           "03_REPLAY_EXAMPLE.cmd", "04_C1_LIVE.cmd")


def source_mapping():
    indexed = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    selected = {}
    for name in filter(None, indexed):
        prefix = "labs/lidar2d/"
        if name.startswith(prefix):
            relative = name[len(prefix):]
            if relative.split("/")[0] in {"src", "configs", "native", "tests"} or relative == "pyproject.toml":
                selected[name] = "app/" + relative
    selected.update({name: name for name in ENTRIES})
    selected.update({"launch_lidar2d.py": "app/launch_lidar2d.py",
                     "tools/run_lidar2d.cmd": "app/run.cmd",
                     "labs/lidar2d/PORTABLE_CN.md": "README_CN.md"})
    return selected


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(args):
    destination = Path(args.destination).resolve()
    bundle = destination / "CoCommand-SLAM"
    bundle.mkdir(parents=True, exist_ok=False)
    selected = source_mapping()
    for name, output_name in selected.items():
        source = ROOT / name
        target = bundle / output_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Only regular source files are allowed: {name}")
        shutil.copy2(source, target)
        if target.suffix == ".cmd":
            data = target.read_bytes().replace(b"tools\\run_lidar2d.cmd", b"app\\run.cmd")
            target.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    clean_runtime = Path(args.python_runtime).resolve()
    if not (clean_runtime / "python.exe").is_file() or (clean_runtime / "pyvenv.cfg").exists():
        raise ValueError("Supply a clean, relocatable Windows CPython distribution, not a venv")
    shutil.copytree(clean_runtime, bundle / ".runtime",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "Scripts"))
    app = bundle / "app"
    (app / "bin").mkdir()
    shutil.copy2(args.bridge, app / "bin" / "cocommand_c1.exe")
    sdk = Path(args.sdk_root)
    meta = app / "meta"
    meta.mkdir()
    shutil.copy2(sdk / "LICENSE", meta / "SLAMTEC-SDK-LICENSE.txt")
    sample = app / "examples"
    sample.mkdir(parents=True)
    shutil.copy2(args.sample, sample / "demo_scans.jsonl")
    (sample / "README.txt").write_text(
        "Synthetic software-test recording only. 300 scans at 10 Hz, 500 rays, seed 7.\n"
        "No physical C1 or vessel measurements; no true pose is supplied to SLAM.\n", encoding="utf-8")
    provenance = {"source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
                  "platform": "Windows x86_64", "python": "3.11.18",
                  "scope": "independent SLAM platform only",
                  "source_files": selected,
                  "runtime_kind": "relocatable CPython distribution; not a copied venv",
                  "sdk_commit": "99478e5fb90de3b4a6db0080acacd373f8b36869",
                  "included_example": "synthetic only", "physical_hardware_validated": False}
    (meta / "PACKAGE_INFO.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (meta / "THIRD_PARTY_NOTICES.txt").write_text(
        "CoCommand-USV project: repository license terms remain unconfirmed; no new license is asserted.\n"
        "CPython runtime: see .runtime/LICENSE.txt; bundled library license notices are retained.\n"
        "NumPy/SciPy/pygame-ce/pyserial and test dependencies: see .runtime/Lib/site-packages/*.dist-info,\n"
        "including their licenses directories and bundled-library notices.\n"
        "SLAMTEC official SDK: BSD-2-Clause; app/meta/SLAMTEC-SDK-LICENSE.txt.\n"
        "Only the compiled bridge and its own source are included, not the SDK demos/library source.\n", encoding="utf-8")
    print(bundle)


def finalize(args):
    destination = Path(args.destination).resolve()
    bundle = destination / "CoCommand-SLAM"
    archive = destination / "CoCommand-SLAM-Windows-x64.zip"
    if archive.exists():
        raise FileExistsError(f"Archive already exists: {archive}")
    if not (bundle / ".runtime" / "python.exe").exists():
        raise ValueError("Stage the bundle first")
    info_file = bundle / "app" / "meta" / "PACKAGE_INFO.json"
    info = json.loads(info_file.read_text(encoding="utf-8"))
    info["dependencies"] = json.loads(subprocess.check_output([
        str(bundle / ".runtime" / "python.exe"), "-I", "-c",
        "import importlib.metadata as m,json;print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()}))"
    ], text=True))
    info_file.write_text(json.dumps(info, indent=2), encoding="utf-8")
    files = [p for p in sorted(bundle.rglob("*")) if p.is_file()
             and "__pycache__" not in p.parts and p.suffix != ".pyc"
             and "output" not in p.relative_to(bundle).parts
             and ".pytest_cache" not in p.parts and p.name != "PACKAGE_SHA256.json"
             # uv --target entrypoint wrappers can embed the build interpreter path.
             # The archive uses python.exe -I launch_lidar2d.py, never these wrappers.
             and not p.is_relative_to(bundle / ".runtime" / "Lib" / "site-packages" / "bin")]
    if any(".git" in p.parts or p.name == "pyvenv.cfg" for p in files):
        raise ValueError("Unexpected Git metadata or venv in bundle")
    allowed = {"app", ".runtime", "README_CN.md", *ENTRIES}
    if any(p.relative_to(bundle).parts[0] not in allowed for p in files):
        raise ValueError("Unrelated top-level content found in SLAM distribution")
    manifest = {p.relative_to(bundle).as_posix(): sha256(p) for p in files}
    manifest_file = bundle / "app" / "meta" / "PACKAGE_SHA256.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in [*files, manifest_file]:
            z.write(path, path.relative_to(destination).as_posix())
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failed: {bad}")
    digest = sha256(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size,
                      "files": len(files)+1, "sha256": digest}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["stage", "finalize"])
    parser.add_argument("--destination", required=True)
    parser.add_argument("--python-runtime")
    parser.add_argument("--bridge")
    parser.add_argument("--sdk-root")
    parser.add_argument("--sample")
    options = parser.parse_args()
    if options.phase == "stage":
        if not all([options.python_runtime, options.bridge, options.sdk_root, options.sample]):
            parser.error("stage requires runtime, bridge, sdk-root and sample")
        stage(options)
    else:
        finalize(options)
