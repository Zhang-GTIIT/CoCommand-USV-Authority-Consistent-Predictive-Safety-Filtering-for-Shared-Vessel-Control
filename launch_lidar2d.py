"""Relocatable entry point for the Windows ZIP and source checkout.

Use python -I launch_lidar2d.py simulate; only this repository's source is added.
No machine-specific virtualenv paths or hardware actuation are involved.
"""
from datetime import datetime
from pathlib import Path
import os
import sys


def main(argv=None):
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.path.insert(0, str(root / "labs" / "lidar2d" / "src"))
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args.pop(0) if args else "simulate"
    output = root / "output" / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + mode)
    def has_option(name):
        return any(arg == name or arg.startswith(name + "=") for arg in args)
    for index, arg in enumerate(args):
        if arg.startswith("--output="):
            output = Path(arg.split("=", 1)[1])
        elif arg == "--output" and index + 1 < len(args):
            output = Path(args[index + 1])
    base = []
    if mode == "demo":
        mode, base = "simulate", ["--demo"]
    elif mode == "example":
        mode = "replay"
        sample = root / "examples" / "lidar2d" / "demo_scans.jsonl"
        if not sample.is_file():
            print("Example recording is included in the portable ZIP. See START_HERE_CN.md.")
            return 2
        base = ["--file", str(sample)]
    elif mode == "lidar":
        bridge = root / "bin" / "cocommand_c1.exe"
        if not has_option("--bridge") and not bridge.is_file():
            print("C1 SDK bridge is missing. See labs/lidar2d/README_CN.md to build it.")
            return 2
        if not has_option("--bridge"):
            base += ["--bridge", str(bridge)]
        if not has_option("--port"):
            from cocommand2d.lidar.sdk import ports
            devices = ports()
            print("Available serial ports:")
            for item in devices:
                print("  " + item["device"] + "  " + item["description"])
            if not devices:
                print("No serial ports detected. Connect the C1 USB adapter first.")
                return 2
            port = input("C1 port (for example COM5; blank cancels): ").strip()
            if not port:
                return 0
            base += ["--port", port]
    if mode in ("simulate", "lidar") and not has_option("--record"):
        base += ["--record", str(output / "scans.jsonl")]
    if not has_option("--output"):
        base += ["--output", str(output)]
    from cocommand2d.app import main as run
    return run([mode, *base, *args])


if __name__ == "__main__":
    raise SystemExit(main())
