"""Truth lives here and in offline evaluation only; SLAM receives Scan objects."""
from dataclasses import dataclass, field
import numpy as np
from ..scan import Scan, wrap


class World:
    width, height = 18.0, 12.0

    def __init__(self):
        self.polygons = [np.array(p, dtype=float) for p in [
            [(0, 0), (18, 0), (18, 12), (0, 12)],
            [(7, 4.5), (9, 4.5), (9, 6.5), (7, 6.5)],
            [(12, 8), (14, 8), (13, 10)],
            [(2, 8), (4.5, 8), (4.5, 9), (2, 9)],
            [(12, 2), (13, 2), (13, 4), (12, 4)]]]
        self.a = np.concatenate(self.polygons)
        self.b = np.concatenate([np.roll(p, -1, axis=0) for p in self.polygons])

    def raycast(self, origin, angles, max_range=12.0):
        d = np.column_stack((np.cos(angles), np.sin(angles)))
        v = self.b - self.a
        q = self.a - origin
        cross = lambda a, b: a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]
        den = cross(d[:, None, :], v[None, :, :])
        with np.errstate(divide="ignore", invalid="ignore"):
            t = cross(q, v)[None, :] / den
            u = cross(q[None, :, :], d[:, None, :]) / den
        hits = (np.abs(den) > 1e-10) & (t >= 0) & (u >= 0) & (u <= 1)
        ranges = np.min(np.where(hits, t, np.inf), axis=1)
        return np.where(ranges <= max_range, ranges, 0.0)

    def collides(self, position, radius=0.28):
        if not (radius < position[0] < self.width - radius and
                radius < position[1] < self.height - radius):
            return True
        v = self.b - self.a
        t = np.clip(np.sum((position - self.a) * v, axis=1) / np.sum(v*v, axis=1), 0, 1)
        if np.min(np.linalg.norm(self.a + t[:, None]*v - position, axis=1)) < radius:
            return True
        # Convex obstacle interiors (all fixture polygons are counterclockwise).
        for p in self.polygons[1:]:
            e = np.roll(p, -1, axis=0) - p
            q = position - p
            if np.all(e[:, 0]*q[:, 1] - e[:, 1]*q[:, 0] >= 0):
                return True
        return False


@dataclass
class Boat:
    pose: np.ndarray = field(default_factory=lambda: np.array([3.0, 3.0, 0.25]))
    speed: float = 0.0
    yaw_rate: float = 0.0
    collided: bool = False

    def step(self, command, dt, world):
        if not 0 < dt <= 0.25:
            raise ValueError("Physics dt must be in (0, .25]")
        self.collided = False
        count = int(np.ceil(dt / 0.02))
        h = dt / count
        for _ in range(count):
            self.speed += (1.3 * command.throttle - self.speed) * (1-np.exp(-h/.45))
            target = 0.85 * command.steering * self.speed / 1.3
            self.yaw_rate += (target-self.yaw_rate) * (1-np.exp(-h/.25))
            candidate = self.pose.copy()
            candidate[2] = wrap(candidate[2] + self.yaw_rate*h)
            candidate[:2] += self.speed*h*np.array([np.cos(candidate[2]), np.sin(candidate[2])])
            if world.collides(candidate[:2]):
                self.speed = self.yaw_rate = 0.0
                self.collided = True
            else:
                self.pose = candidate


class VirtualLidar:
    def __init__(self, seed=7, samples=500, noise=0.01):
        self.rng = np.random.default_rng(seed)
        self.angles = np.linspace(-np.pi, np.pi, samples, endpoint=False)
        self.noise = noise

    def scan(self, world, pose, timestamp):
        ranges = world.raycast(pose[:2], self.angles + pose[2])
        valid = ranges > 0
        ranges[valid] += self.rng.normal(0, self.noise, np.count_nonzero(valid))
        return Scan(timestamp, self.angles, ranges, np.where(valid, 100, 0), valid, "simulation")
