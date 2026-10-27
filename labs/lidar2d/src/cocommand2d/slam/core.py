"""Local scan-to-submap point-to-line ICP and inverse-sensor occupancy mapping.

No simulation, controller, odometry or true-pose dependency. The first scan defines
the origin. No loop closure/global relocalization is claimed by this local SLAM.
"""
from collections import deque
import numpy as np
from scipy.spatial import cKDTree
from ..scan import transform, wrap


class OccupancyGrid:
    def __init__(self, extent=40.0, resolution=0.08):
        if extent <= 0 or resolution <= 0 or extent / resolution > 2000:
            raise ValueError("Invalid or excessive grid size")
        self.resolution = resolution
        self.size = int(np.ceil(extent / resolution))
        self.origin = np.array([-extent / 2, -extent / 2])
        self.log_odds = np.zeros((self.size, self.size), dtype=np.float32)
        self.observed = np.zeros_like(self.log_odds, dtype=bool)
        self.clipped = False

    def cells(self, points):
        return np.floor((points - self.origin) / self.resolution).astype(int)

    def inside(self, cells):
        return np.all((cells >= 0) & (cells < self.size), axis=-1)

    def update(self, points, pose):
        endpoints = transform(points, pose)
        start = np.asarray(pose[:2])
        free_cells = []
        end_cells = self.cells(endpoints)
        self.clipped = not bool(np.all(self.inside(end_cells)))
        for end in endpoints:
            steps = int(np.ceil(np.max(np.abs(end-start)) / self.resolution))
            if steps:
                ray = start + (end-start) * (np.arange(steps) / steps)[:, None]
                free_cells.append(self.cells(ray))
        if free_cells:
            free = np.unique(np.concatenate(free_cells), axis=0)
            free = free[self.inside(free)]
            self.log_odds[free[:, 1], free[:, 0]] -= 0.35
            self.observed[free[:, 1], free[:, 0]] = True
        hit = np.unique(end_cells[self.inside(end_cells)], axis=0)
        self.log_odds[hit[:, 1], hit[:, 0]] += 1.1
        self.observed[hit[:, 1], hit[:, 0]] = True
        np.clip(self.log_odds, -5, 5, out=self.log_odds)

    def image(self):
        p = 1 / (1 + np.exp(-self.log_odds))
        return np.where(self.observed, (1-p)*255, 127).astype(np.uint8)


def voxel(points, resolution=0.06):
    _, indices = np.unique(np.floor(points / resolution).astype(int), axis=0, return_index=True)
    return points[np.sort(indices)]


class LidarSlam:
    def __init__(self, resolution=0.08, extent=40.0):
        self.grid = OccupancyGrid(extent, resolution)
        self.pose = np.zeros(3)
        self.velocity = np.zeros(3)
        self.last_timestamp = None
        self.last_key_pose = np.zeros(3)
        self.keyframes = deque(maxlen=16)
        self.trajectory = []
        self.status = "WAITING"
        self.rmse = float("inf")
        self.inlier_ratio = 0.0
        self.tree = None

    def _reference(self, points):
        self.keyframes.append(transform(points, self.pose))
        self.reference = voxel(np.concatenate(self.keyframes))
        self.tree = cKDTree(self.reference)
        distances, neighbors = self.tree.query(self.reference, k=8)
        local = self.reference[neighbors]
        centered = local - np.mean(local, axis=1, keepdims=True)
        cov = np.einsum("nki,nkj->nij", centered, centered)
        eigen, vectors = np.linalg.eigh(cov)
        self.normals = vectors[:, :, 0]
        self.planar = (eigen[:, 0] / np.maximum(eigen[:, 1], 1e-9) < 0.15) & (distances[:, -1] < .65)
        self.last_key_pose = self.pose.copy()

    def _match(self, points, seed):
        pose = seed.copy()
        for _ in range(20):
            world = transform(points, pose)
            distance, ids = self.tree.query(world)
            mask = (distance < .65) & self.planar[ids]
            if np.count_nonzero(mask) < 40:
                return None, "LOST: insufficient overlap"
            n = self.normals[ids[mask]]
            delta = world[mask] - self.reference[ids[mask]]
            residual = np.sum(n*delta, axis=1)
            rotated = world[mask] - pose[:2]
            j = np.column_stack((n, -n[:, 0]*rotated[:, 1] + n[:, 1]*rotated[:, 0]))
            weights = np.minimum(1, .06 / np.maximum(np.abs(residual), 1e-9))
            # Normalized information matrix detects poorly observable directions.
            # Scale radians to displacement at the scan's characteristic range.
            # Per-column normalization would hide near-zero yaw information in a circle.
            scaled = j.copy()
            scaled[:, 2] /= max(1.0, np.sqrt(np.mean(np.sum(rotated**2, axis=1))))
            values = np.linalg.eigvalsh(scaled.T @ scaled / len(scaled))
            translation = np.linalg.eigvalsh(n.T @ n)
            if values[0] / max(values[-1], 1e-9) < .015 or translation[0] / max(translation[-1], 1e-9) < .025:
                return None, "DEGENERATE: weak geometry"
            step = np.linalg.lstsq(j * np.sqrt(weights[:, None]), -residual*np.sqrt(weights), rcond=None)[0]
            step[:2] = np.clip(step[:2], -.2, .2)
            step[2] = np.clip(step[2], -.08, .08)
            pose += step
            pose[2] = wrap(pose[2])
            if np.linalg.norm(step) < 1e-5:
                break
        world = transform(points, pose)
        distance, ids = self.tree.query(world)
        mask = (distance < .25) & self.planar[ids]
        self.inlier_ratio = float(np.mean(mask))
        residual = np.sum(self.normals[ids[mask]] * (world[mask]-self.reference[ids[mask]]), axis=1)
        self.rmse = float(np.sqrt(np.mean(residual**2))) if len(residual) else float("inf")
        if self.inlier_ratio < .5 or self.rmse > .09:
            return None, "LOST: matching rejected"
        if np.linalg.norm(pose[:2]-self.pose[:2]) > .8 or abs(wrap(pose[2]-self.pose[2])) > .35:
            return None, "LOST: excessive motion"
        return pose, "TRACKING"

    def update(self, scan):
        if self.last_timestamp is not None and scan.timestamp <= self.last_timestamp:
            raise ValueError("SLAM timestamps must strictly increase")
        dt = 0 if self.last_timestamp is None else scan.timestamp - self.last_timestamp
        self.last_timestamp = scan.timestamp
        points = voxel(scan.points())
        if len(points) < 60:
            self.status = "LOST: too few returns"
            self.velocity[:] = 0
        elif self.tree is None:
            self.status = "INITIALIZED"
            self._reference(points)
            self.grid.update(points, self.pose)
        else:
            seed = self.pose + self.velocity * min(dt, .2)
            estimate, self.status = self._match(points, seed)
            if estimate is not None:
                delta = estimate - self.pose
                delta[2] = wrap(delta[2])
                self.velocity = delta / max(dt, .01)
                self.pose = estimate
                self.grid.update(points, self.pose)
                if (np.linalg.norm(self.pose[:2]-self.last_key_pose[:2]) > .25 or
                        abs(wrap(self.pose[2]-self.last_key_pose[2])) > .08):
                    self._reference(points)
            else:
                self.velocity[:] = 0
        self.trajectory.append((scan.timestamp, *self.pose, self.status))
        return self.pose.copy()
