import ast
from collections import defaultdict
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
import numpy as np
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from cocommand2d.scan import Scan, transform, wrap
from cocommand2d.controller import Axis, Command, ControlGuard, RCSignal, SteeringAuthority
from cocommand2d.simulation import World, Boat, VirtualLidar
from cocommand2d.slam import LidarSlam, OccupancyGrid
from cocommand2d.recording import Recorder, replay, save_result
from cocommand2d.app import Session, Observation, main
from cocommand2d.lidar.sdk import SDKSource, decode_line


def test_c1_clockwise_to_right_handed_coordinates():
    scan = Scan.from_c1(0, [0, 90, 180, 270], [1000]*4, [10]*4)
    np.testing.assert_allclose(scan.points(), [[1, 0], [0, -1], [-1, 0], [0, 1]], atol=1e-12)
    mounted = Scan.from_c1(0, [0], [1000], [1], np.pi/2)
    np.testing.assert_allclose(mounted.points(), [[0, 1]], atol=1e-12)


def test_bad_returns_not_treated_as_free_space():
    s = Scan.from_c1(0, [0, 10, 20, 30, 40, 50], [0, 10, 13000, np.nan, 1200, 2000], [1, 1, 1, 1, 0, 10])
    assert s.valid.tolist() == [False]*5 + [True]
    assert len(s.points()) == 1
    assert s.quality[-1] == 10
    json.dumps(s.to_dict(), allow_nan=False)


@pytest.mark.parametrize("change", [{"timestamp": float("nan")}, {"angles": [1, 2]}, {"range_min": -1}])
def test_bad_scan_rejected(change):
    data = dict(timestamp=1, angles=[0], ranges=[1], quality=[1], valid=[True])
    data.update(change)
    with pytest.raises(ValueError):
        Scan(**data)


def test_scan_immutable_copy():
    ranges = np.ones(2)
    scan = Scan(0, [0, 1], ranges, [1, 1], [True, True])
    ranges[0] = 10
    assert scan.ranges[0] == 1
    with pytest.raises(ValueError):
        scan.ranges[0] = 3


def test_stick_continuous_proportional_and_deadzone():
    a = Axis(deadzone=.1)
    values = [a.map(x) for x in np.linspace(.1, 1, 101)]
    assert len(set(values)) == 101
    assert a.map(.55) == pytest.approx(.5)
    assert a.map(-.55) == pytest.approx(-.5)
    assert a.map(.05) == 0
    assert a.map(3) == 1


def test_trigger_and_asymmetric_calibration():
    a = Axis(mode="trigger")
    assert a.map(-1) == 0 and a.map(1) == 1
    assert 0 < a.map(0) < 1
    b = Axis(minimum=-.8, center=.1, maximum=.9, deadzone=0)
    assert b.map(.5) == pytest.approx(.5)
    assert b.map(-.35) == pytest.approx(-.5)


def test_pwm_is_only_simulated_and_configurable():
    rc = RCSignal(1100, 1500, 1900).encode(Command(.5, -.25))
    assert rc == {"throttle_us": 1700, "steering_us": 1400, "physical_output": False}


def test_disconnect_stale_and_neutral_rearming():
    guard = ControlGuard()
    assert not guard.arm(Command(.5, 0))
    assert guard.arm(Command())
    assert guard.apply(Command(.3, .5), 1, 1.1) == Command(.3, .5)
    assert guard.apply(Command(.3, .5), 1, 1.4) == Command()
    assert not guard.armed
    assert guard.arm(Command())
    assert guard.apply(Command(1, 1), 2, 2, False) == Command()
    assert guard.apply(Command(1, 1), 3, 3, True) == Command()


def test_steering_hook_cannot_change_throttle():
    human = Command(.347, -.5)
    result = SteeringAuthority(lambda obs, cmd: .2).apply(human, {"scan": None})
    assert result.throttle == human.throttle and result.steering == .2


def test_pool_ray_geometry_and_no_return():
    world = World()
    np.testing.assert_allclose(world.raycast([3, 3], np.array([0, np.pi/2, np.pi, -np.pi/2])), [9, 5, 3, 3])
    assert world.raycast([3, 3], np.array([0]), 5)[0] == 0


def test_boat_free_motion_and_collision():
    world, boat = World(), Boat()
    initial = boat.pose.copy()
    for _ in range(30):
        boat.step(Command(.5, .5), .1, world)
    assert np.linalg.norm(boat.pose[:2]-initial[:2]) > 1
    assert boat.pose[2] > initial[2]
    boat = Boat(np.array([.3, 2, np.pi]), speed=1)
    boat.step(Command(1, 0), .2, world)
    assert boat.collided and boat.pose[0] >= .28


def test_occupancy_marks_obstacles_free_and_unknown():
    g = OccupancyGrid(extent=10, resolution=.1)
    for _ in range(5):
        g.update(np.array([[2., 0.]]), [0, 0, 0])
    cells = g.cells(np.array([[2, 0], [1, 0], [0, 3]]))
    assert g.log_odds[cells[0, 1], cells[0, 0]] > 2
    assert g.log_odds[cells[1, 1], cells[1, 0]] < -1
    assert not g.observed[cells[2, 1], cells[2, 0]]


@pytest.mark.parametrize("seed", [3, 17, 81])
def test_scan_only_translation_rotation_accuracy(seed):
    world, lidar, slam = World(), VirtualLidar(seed), LidarSlam()
    errors = []
    for i in range(100):
        truth = np.array([3+i*.016, 3+.35*np.sin(i*.015), i*.004])
        estimate = slam.update(lidar.scan(world, truth, i*.1))
        errors.append(np.linalg.norm(estimate[:2]-(truth[:2]-[3, 3])))
    assert max(errors) < .15
    assert abs(wrap(estimate[2]-truth[2])) < .025
    assert np.count_nonzero(slam.grid.observed) > 10000
    assert sum("LOST" in row[-1] for row in slam.trajectory) == 0


def test_slam_module_has_no_truth_imports_or_pose_input():
    import cocommand2d.slam.core as core
    tree = ast.parse(inspect.getsource(core))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(x and ("simulation" in x or "controller" in x or "app" in x) for x in imports)
    assert list(inspect.signature(LidarSlam.update).parameters) == ["self", "scan"]


def test_empty_scan_freezes_pose_and_map():
    slam, lidar, world = LidarSlam(), VirtualLidar(), World()
    slam.update(lidar.scan(world, [3, 3, 0], 0))
    before = slam.grid.log_odds.copy()
    slam.update(Scan(1, np.arange(500), np.zeros(500), np.zeros(500), np.zeros(500, bool)))
    assert slam.status.startswith("LOST")
    np.testing.assert_array_equal(before, slam.grid.log_odds)


def test_circular_geometry_is_degenerate_for_yaw():
    angles = np.linspace(-np.pi, np.pi, 500, endpoint=False)
    slam = LidarSlam()
    slam.update(Scan(0, angles, np.full(500, 5), np.ones(500), np.ones(500, bool)))
    before = slam.grid.log_odds.copy()
    slam.update(Scan(1, angles, np.full(500, 5), np.ones(500), np.ones(500, bool)))
    assert "DEGENERATE" in slam.status
    np.testing.assert_array_equal(slam.grid.log_odds, before)


def test_roundtrip_rebuilds_identical_map_and_trajectory(tmp_path):
    a, b = LidarSlam(), LidarSlam()
    lidar, world = VirtualLidar(10), World()
    path = tmp_path / "scan.jsonl"
    with Recorder(path) as recorder:
        for i in range(35):
            scan = lidar.scan(world, [3+i*.02, 3, i*.002], i*.1)
            recorder.write(scan)
            a.update(scan)
    for scan in replay(path):
        b.update(scan)
    np.testing.assert_array_equal(a.grid.log_odds, b.grid.log_odds)
    assert a.trajectory == b.trajectory
    save_result(b, tmp_path)
    assert (tmp_path / "map.pgm").read_bytes().startswith(b"P5")
    assert np.load(tmp_path / "map.npz")["observed"].any()
    with pytest.raises(FileExistsError):
        Recorder(path)


def test_corrupt_record_has_line_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"version": 99}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        list(replay(path))


def test_duplicate_timestamp_rejected(tmp_path):
    scan = VirtualLidar().scan(World(), [3, 3, 0], 1)
    path = tmp_path / "duplicate.jsonl"
    with Recorder(path) as recorder:
        recorder.write(scan)
        recorder.write(scan)
    with pytest.raises(ValueError, match="strictly increase"):
        list(replay(path))


def test_live_observation_expiry():
    obs = Observation(object(), (0, 0, 0), "TRACKING", 10, 12)
    assert obs.fresh(10.1)
    assert not obs.fresh(10.5)
    assert not obs.fresh(9)


def test_official_sdk_json_decoder():
    scan = decode_line(json.dumps({"type": "scan", "angles_cw_deg": [90], "distances_mm": [2000], "quality": [40]}))
    np.testing.assert_allclose(scan.points(), [[0, -2]], atol=1e-12)
    assert scan.source == "c1-sdk"


def test_missing_sdk_bridge_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Build native"):
        SDKSource(tmp_path / "missing.exe", "COM1")


def test_sdk_subprocess_reconnect_and_cleanup():
    real_popen = subprocess.Popen
    payload = json.dumps({"type": "scan", "angles_cw_deg": [0, 90], "distances_mm": [1000, 2000], "quality": [20, 20]})
    script = f"import time; print({payload!r}, flush=True); time.sleep(.35)"
    calls = []
    def launch(*args, **kwargs):
        process = real_popen([sys.executable, "-u", "-c", script], **kwargs)
        calls.append(process)
        return process
    with patch("cocommand2d.lidar.sdk.subprocess.Popen", side_effect=launch):
        source = SDKSource(sys.executable, "FAKE", stall_timeout=.5)
        received = []
        deadline = time.monotonic()+5
        try:
            while len(received) < 2 and time.monotonic() < deadline:
                scan = source.poll()
                if scan:
                    received.append(scan)
                time.sleep(.03)
        finally:
            source.close()
    assert len(received) == 2
    assert received[1].timestamp > received[0].timestamp
    assert len(calls) >= 2 and all(p.poll() is not None for p in calls)
    assert not source.thread.is_alive()


def test_keyboard_drives_vessel_without_hardware():
    import pygame
    from cocommand2d.controller.input import Inputs
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    with patch("pygame.joystick.get_count", return_value=0):
        inputs = Inputs()
    keys = defaultdict(bool, {pygame.K_w: True, pygame.K_a: True})
    samples = [inputs.read(.05, keys)[0] for _ in range(10)]
    assert 0 < samples[0].throttle < samples[-1].throttle < 1
    assert samples[-1].steering > 0
    boat = Boat()
    start = boat.pose.copy()
    for cmd in samples:
        boat.step(cmd, .05, World())
    assert np.linalg.norm(boat.pose[:2]-start[:2]) > .01
    pygame.quit()


def test_mock_gamepad_analog_and_disconnect():
    import pygame
    from cocommand2d.controller.input import Inputs
    class Pad:
        values = [0, 0]
        def init(self): pass
        def quit(self): pass
        def get_name(self): return "test pad"
        def get_instance_id(self): return 77
        def get_axis(self, index): return self.values[index]
    pad = Pad()
    with patch("pygame.joystick.get_count", return_value=1), patch("pygame.joystick.Joystick", return_value=pad):
        inputs = Inputs()
    inputs.toggle()
    pad.values = [-.3, -.5]
    first, connected = inputs.read(.1)
    pad.values = [-.6, -.8]
    second, _ = inputs.read(.1)
    assert connected and 0 < first.throttle < second.throttle < 1
    assert 0 < first.steering < second.steering
    assert inputs.event(pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=77)) == "lost"
    assert inputs.read(.1) == (Command(), False)


def test_gui_renders_and_saves(tmp_path):
    import pygame
    from cocommand2d.visualization.gui import Dashboard
    session = Session(output=tmp_path)
    for _ in range(5):
        session.simulate(Command(.3, .2))
    ui = Dashboard()
    ui.render(session, Command(.3, .2), "AUTOMATED RENDER TEST", "keyboard")
    ui.screenshot(tmp_path / "screen.png")
    assert (tmp_path / "screen.png").stat().st_size > 10000
    pygame.quit()
    session.close()


def test_cli_headless_and_replay(tmp_path):
    path = tmp_path / "raw.jsonl"
    assert main(["simulate", "--headless", "--demo", "--steps", "8", "--record", str(path), "--output", str(tmp_path / "a")]) == 0
    assert main(["replay", "--headless", "--file", str(path), "--output", str(tmp_path / "b")]) == 0
    a = np.load(tmp_path / "a/map.npz")["log_odds"]
    b = np.load(tmp_path / "b/map.npz")["log_odds"]
    np.testing.assert_array_equal(a, b)
