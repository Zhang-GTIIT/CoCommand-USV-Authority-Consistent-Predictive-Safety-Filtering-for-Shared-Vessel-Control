"""Only observation interface accepted by SLAM: metres, radians, x-forward/y-left."""
from dataclasses import dataclass
import math
import numpy as np


def wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


def transform(points, pose):
    c, s = np.cos(pose[2]), np.sin(pose[2])
    return points @ np.array([[c, s], [-s, c]]) + np.asarray(pose[:2])


@dataclass(frozen=True)
class Scan:
    timestamp: float
    angles: np.ndarray
    ranges: np.ndarray
    quality: np.ndarray
    valid: np.ndarray
    source: str = "unknown"
    range_min: float = 0.05
    range_max: float = 12.0

    def __post_init__(self):
        if not math.isfinite(self.timestamp) or self.timestamp < 0:
            raise ValueError("Scan timestamp must be finite and nonnegative")
        if not 0 < self.range_min < self.range_max or not math.isfinite(self.range_max):
            raise ValueError("Invalid range limits")
        arrays = [np.array(a, dtype=d, copy=True) for a, d in zip(
            (self.angles, self.ranges, self.quality, self.valid), (float, float, float, bool))]
        if any(a.ndim != 1 for a in arrays) or len({len(a) for a in arrays}) != 1:
            raise ValueError("Scan arrays must be equally sized vectors")
        if not 1 <= len(arrays[0]) <= 16384:
            raise ValueError("Scan must contain 1..16384 samples")
        a, r, q, v = arrays
        v &= np.isfinite(a) & np.isfinite(r) & np.isfinite(q)
        v &= (r >= self.range_min) & (r <= self.range_max) & (q >= 0)
        a[:] = wrap(np.nan_to_num(a))
        r[~v] = 0.0
        q[~np.isfinite(q)] = 0.0
        for key, val in zip(("angles", "ranges", "quality", "valid"), arrays):
            val.setflags(write=False)
            object.__setattr__(self, key, val)

    def points(self):
        a, r = self.angles[self.valid], self.ranges[self.valid]
        return np.column_stack((r * np.cos(a), r * np.sin(a)))

    def to_dict(self):
        return {"version": 1, "frame": "x_forward_y_left_ccw", "timestamp": self.timestamp,
                "angles": self.angles.tolist(), "ranges": self.ranges.tolist(),
                "quality": self.quality.tolist(), "valid": self.valid.tolist(),
                "source": self.source, "range_min": self.range_min, "range_max": self.range_max}

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        if data.pop("version", None) != 1 or data.pop("frame", None) != "x_forward_y_left_ccw":
            raise ValueError("Unsupported scan version or coordinate frame")
        return cls(**data)

    @classmethod
    def from_c1(cls, timestamp, angles_cw_deg, distances_mm, quality, mount_yaw=0.0):
        angles = wrap(mount_yaw - np.deg2rad(angles_cw_deg))
        ranges = np.asarray(distances_mm, dtype=float) / 1000.0
        q = np.asarray(quality, dtype=float)
        # SDK quality is retained as-is, not claimed to be calibrated reflectivity.
        return cls(timestamp, angles, ranges, q, (ranges > 0) & (q > 0), "c1-sdk")
