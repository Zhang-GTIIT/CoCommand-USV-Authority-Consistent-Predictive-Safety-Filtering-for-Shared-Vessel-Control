import csv
import json
from pathlib import Path
import numpy as np
from ..scan import Scan


class Recorder:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("x", encoding="utf-8")
        self.count = 0

    def write(self, scan):
        self.stream.write(json.dumps(scan.to_dict(), allow_nan=False, separators=(",", ":")) + "\n")
        self.stream.flush()
        self.count += 1

    def close(self):
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def replay(path):
    previous = -1.0
    with Path(path).open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                scan = Scan.from_dict(json.loads(line))
                if scan.timestamp <= previous:
                    raise ValueError("Timestamps must strictly increase")
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"Recording line {line_no}: {exc}") from exc
            previous = scan.timestamp
            yield scan


def save_result(slam, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    grid = slam.grid
    np.savez_compressed(directory / "map.npz", log_odds=grid.log_odds,
                        observed=grid.observed, origin=grid.origin, resolution=grid.resolution)
    pixels = grid.image()
    # PGM row 0 is the top; npz row 0 is minimum map y.
    with (directory / "map.pgm").open("wb") as f:
        f.write(f"P5\n{grid.size} {grid.size}\n255\n".encode())
        f.write(np.flipud(pixels).tobytes())
    meta = {"resolution": grid.resolution, "origin": grid.origin.tolist(),
            "frame": "initial_scan_x_forward_y_left_ccw", "unknown_gray": 127,
            "image": "map.pgm", "trajectory_columns": ["timestamp", "x", "y", "yaw", "status"]}
    (directory / "map.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    with (directory / "trajectory.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(meta["trajectory_columns"])
        writer.writerows(slam.trajectory)
