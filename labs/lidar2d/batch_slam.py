"""Batch entry point: JSONL scan sequence in, occupancy map and trajectory out."""
import argparse
import json
from pathlib import Path

from .recording import replay, save_result
from .slam import LidarSlam


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a 2D occupancy map from a timestamped JSONL lidar sequence.")
    parser.add_argument("--input", required=True, help="Input JSONL recording in Scan v1 format")
    parser.add_argument("--output", required=True, help="New directory for map and trajectory")
    parser.add_argument("--extent", type=float, default=40.0, help="Square map width in metres")
    parser.add_argument("--resolution", type=float, default=0.08, help="Grid resolution in metres")
    args = parser.parse_args(argv)

    destination = Path(args.output)
    if destination.exists():
        parser.error("--output must be a new directory; existing results are never overwritten")
    slam = LidarSlam(extent=args.extent, resolution=args.resolution)
    frames = 0
    for scan in replay(args.input):
        slam.update(scan)
        frames += 1
    if not frames:
        parser.error("Input contains no scans")
    save_result(slam, destination)
    summary = {
        "input": str(Path(args.input)),
        "frames": frames,
        "status": slam.status,
        "final_pose_x_y_yaw": slam.pose.tolist(),
        "observed_cells": int(slam.grid.observed.sum()),
        "extent_m": args.extent,
        "resolution_m": args.resolution,
        "coordinate_frame": "initial_scan_x_forward_y_left_ccw",
    }
    (destination / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
