import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import queue
import subprocess
import sys
import time
from unittest.mock import patch
import numpy as np
import pytest
from cocommand2d.app import Session, Observation
from cocommand2d.scan import Scan
from cocommand2d.slam import LidarSlam
from cocommand2d.simulation import World, VirtualLidar
from cocommand2d.lidar.sdk import SDKSource
from cocommand2d.controller import Command, SteeringAuthority


def test_large_relocation_does_not_corrupt_map():
    slam, world, lidar = LidarSlam(), World(), VirtualLidar()
    slam.update(lidar.scan(world, [3, 3, 0], 0))
    before = slam.grid.log_odds.copy()
    slam.update(lidar.scan(world, [14, 7, 2], 1))
    assert slam.status.startswith(("LOST", "DEGENERATE"))
    np.testing.assert_array_equal(slam.grid.log_odds, before)


def test_parallel_corridor_degeneracy():
    a = np.linspace(-np.pi, np.pi, 500, endpoint=False)
    with np.errstate(divide="ignore"):
        r = 2 / np.abs(np.sin(a))
    valid = np.isfinite(r) & (r < 12)
    slam = LidarSlam()
    slam.update(Scan(0, a, r, np.ones(500), valid))
    slam.update(Scan(1, a, r, np.ones(500), valid))
    assert "DEGENERATE" in slam.status


def test_historical_replay_never_claims_live(tmp_path):
    session = Session("replay", output=tmp_path)
    session.consume(VirtualLidar().scan(World(), [3, 3, 0], 0))
    assert not session.observation().fresh()
    assert not session.observation().localized()
    session.close()


def test_lidar_queue_age_not_reset_during_processing(tmp_path):
    session = Session("lidar", output=tmp_path)
    scan = VirtualLidar().scan(World(), [3, 3, 0], time.monotonic()-1)
    session.consume(scan)
    assert not session.observation().fresh()
    session.close()


def test_fresh_scan_with_lost_localization_distinguished():
    observation = Observation(object(), (0, 0, 0), "LOST", 10, 2)
    assert observation.fresh(10.1) and not observation.localized(10.1)


def test_display_queue_returns_latest_only():
    source = SDKSource.__new__(SDKSource)
    source.scans = queue.Queue()
    source.dropped = 0
    for i in range(5):
        source.scans.put(i)
    assert source.poll() == 4
    assert source.dropped == 4
    assert source.poll() is None


def test_stalled_sdk_process_is_stopped():
    real_popen = subprocess.Popen
    children = []
    def launch(*args, **kwargs):
        proc = real_popen([sys.executable, "-u", "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(proc)
        return proc
    with patch("cocommand2d.lidar.sdk.subprocess.Popen", side_effect=launch):
        source = SDKSource(sys.executable, "FAKE", stall_timeout=.15)
        deadline = time.monotonic()+2
        while "DISCONNECTED" not in source.status and time.monotonic() < deadline:
            time.sleep(.02)
        assert "stalled" in source.status
        source.close()
    assert children and all(p.poll() is not None for p in children)
    assert not source.thread.is_alive()


def test_hook_nan_is_rejected():
    with pytest.raises(ValueError):
        SteeringAuthority(lambda obs, cmd: float("nan")).apply(Command(.3, .1))
