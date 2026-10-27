"""Create a portable Windows archive containing only the offline SLAM algorithm."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def stage(options):
    target = Path(options.destination).resolve() / "Lidar-SLAM-Algorithm"
    target.mkdir(parents=True, exist_ok=False)
    app = target / "app"
    sources = {
        "labs/lidar2d/src/cocommand2d/scan.py": "src/cocommand2d/scan.py",
        "labs/lidar2d/src/cocommand2d/slam/__init__.py": "src/cocommand2d/slam/__init__.py",
        "labs/lidar2d/src/cocommand2d/slam/core.py": "src/cocommand2d/slam/core.py",
        "labs/lidar2d/src/cocommand2d/recording/__init__.py": "src/cocommand2d/recording/__init__.py",
        "labs/lidar2d/src/cocommand2d/recording/io.py": "src/cocommand2d/recording/io.py",
        "labs/lidar2d/batch_slam.py": "src/cocommand2d/batch_slam.py",
        "labs/lidar2d/ALGORITHM_CN.md": "ALGORITHM_CN.md",
        "labs/lidar2d/ALGORITHM_REQUIREMENTS.txt": "requirements.txt",
    }
    for source, relative in sources.items():
        copy(ROOT / source, app / relative)
    (app / "src/cocommand2d/__init__.py").write_text(
        '"""Timestamped 2D lidar scan matching and occupancy mapping."""\n', encoding="utf-8")
    (app / "run_slam.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))\n"
        "from cocommand2d.batch_slam import main\n"
        "raise SystemExit(main())\n", encoding="utf-8")
    (target / "README_CN.md").write_text(
        "# 二维激光 SLAM 算法包\n\n"
        "输入时间顺序的二维雷达 JSONL 序列，输出地图与估计轨迹。\n\n"
        "1. 完整解压 ZIP。\n"
        "2. 双击 `RUN_EXAMPLE.cmd`，生成 `output/example-map/`。\n"
        "3. 处理自己的记录：在当前文件夹打开 PowerShell，运行：\n\n"
        "```powershell\n"
        ".\\.runtime\\python.exe -I .\\app\\run_slam.py --input \"你的扫描.jsonl\" --output \"output\\my-map\"\n"
        "```\n\n"
        "输入格式、输出文件、坐标系和限制见 `app/ALGORITHM_CN.md`。\n",
        encoding="utf-8")
    (target / "RUN_EXAMPLE.cmd").write_bytes(
        b"@echo off\r\nsetlocal\r\npushd \"%~dp0\"\r\n\".runtime\\python.exe\" -I \"app\\run_slam.py\" --input \"app\\example\\demo_scans.jsonl\" --output \"output\\example-map\"\r\nset \"RESULT=%ERRORLEVEL%\"\r\nif not \"%~1\"==\"--no-pause\" pause\r\npopd\r\nexit /b %RESULT%\r\n")
    example = app / "example"
    example.mkdir()
    copy(Path(options.sample), example / "demo_scans.jsonl")
    (example / "README.txt").write_text(
        "Synthetic 300-frame test input only; not physical lidar data.\n", encoding="utf-8")
    runtime = Path(options.runtime).resolve()
    if not (runtime / "python.exe").is_file() or (runtime / "pyvenv.cfg").exists():
        raise ValueError("--runtime must be a clean CPython distribution, not a venv")
    shutil.copytree(runtime, target / ".runtime", ignore=shutil.ignore_patterns("Scripts", "__pycache__", "*.pyc"))
    (app / "meta").mkdir()
    (app / "meta/NOTICE.txt").write_text(
        "Python license: see .runtime/LICENSE.txt.\n"
        "NumPy and SciPy license notices are retained in their .dist-info directories.\n"
        "No simulator, user interface, device driver, controller, vessel algorithm,\n"
        "research dataset, historical run, or third-party SDK is included.\n", encoding="utf-8")
    print(target)


def finalize(options):
    root = Path(options.destination).resolve()
    bundle = root / "Lidar-SLAM-Algorithm"
    archive = root / "Lidar-SLAM-Algorithm-Windows-x64.zip"
    if archive.exists() or not (bundle / ".runtime/python.exe").is_file():
        raise ValueError("New staged bundle required")
    files = [path for path in sorted(bundle.rglob("*")) if path.is_file()
             and "__pycache__" not in path.parts and path.suffix != ".pyc"
             and "output" not in path.relative_to(bundle).parts
             and not path.is_relative_to(bundle / ".runtime/Lib/site-packages/bin")]
    site_packages = bundle / ".runtime/Lib/site-packages"
    excluded_runtime_tools = {"pip", "setuptools", "_distutils_hack"}
    def retain(path):
        if not path.is_relative_to(site_packages):
            return True
        top_level = path.relative_to(site_packages).parts[0]
        return top_level.split("-")[0] not in excluded_runtime_tools and top_level != "distutils-precedence.pth"
    files = [path for path in files if retain(path)]
    allowed = {".runtime", "app", "README_CN.md", "RUN_EXAMPLE.cmd"}
    if {path.relative_to(bundle).parts[0] for path in files} - allowed:
        raise ValueError("Unexpected material in algorithm package")
    manifest = {path.relative_to(bundle).as_posix(): digest(path) for path in files}
    manifest_path = bundle / "app/meta/SHA256.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for path in [*files, manifest_path]:
            package.write(path, path.relative_to(root).as_posix())
        if package.testzip():
            raise ValueError("Archive CRC failure")
    checksum = digest(archive)
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size,
                      "files": len(files) + 1, "sha256": checksum}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stage", "finalize"))
    parser.add_argument("--destination", required=True)
    parser.add_argument("--runtime")
    parser.add_argument("--sample")
    args = parser.parse_args()
    if args.action == "stage":
        if not args.runtime or not args.sample:
            parser.error("stage requires --runtime and --sample")
        stage(args)
    else:
        finalize(args)
