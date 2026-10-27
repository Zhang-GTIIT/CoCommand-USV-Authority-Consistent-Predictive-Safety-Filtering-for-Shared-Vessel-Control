import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import math
from pathlib import Path
import time
import numpy as np
from .controller import Command, ControlGuard, RCSignal, SteeringAuthority
from .recording import Recorder, replay, save_result
from .scan import wrap
from .slam import LidarSlam


@dataclass(frozen=True)
class Observation:
    """Future avoidance input; a historical map is never a freshness guarantee."""
    scan: object
    estimated_pose: tuple
    tracking_status: str
    received_monotonic: float
    processing_ms: float
    live: bool = True

    def fresh(self, now=None, max_age=.35):
        age = (time.monotonic() if now is None else now) - self.received_monotonic
        return self.live and self.scan is not None and 0 <= age <= max_age

    def localized(self, now=None):
        return self.fresh(now) and self.tracking_status in ("INITIALIZED", "TRACKING")


class Session:
    def __init__(self, mode="simulate", seed=7, output="output", record=None):
        self.mode, self.output = mode, Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.slam = LidarSlam()
        self.scan = None
        self.count = 0
        self.truth = []
        self.errors = []
        self.processing_times = []
        self.received = 0.0
        self.processing_ms = 0.0
        self.recorder = Recorder(record) if record else None
        self.signal = RCSignal()
        self.rc = self.signal.encode(Command())
        self.source_status = "WAITING FOR SCAN"
        self.sim_time = 0.0
        self.collision_steps = 0
        if mode == "simulate":
            from .simulation import World, Boat, VirtualLidar
            self.world, self.boat, self.lidar = World(), Boat(), VirtualLidar(seed)
            self.initial_truth = self.boat.pose.copy()

    def observation(self):
        return Observation(self.scan, tuple(self.slam.pose), self.slam.status, self.received,
                           self.processing_ms, self.mode != "replay")

    def consume(self, scan):
        self.received = scan.timestamp if self.mode == "lidar" else time.monotonic()
        start = time.perf_counter()
        self.scan = scan
        if self.recorder and self.mode != "lidar":
            self.recorder.write(scan)
        self.slam.update(scan)
        self.processing_ms = (time.perf_counter()-start)*1000
        self.processing_times.append(self.processing_ms)
        self.count += 1

    def simulate(self, command, dt=.1, scan=True):
        self.boat.step(command, dt, self.world)
        self.collision_steps += int(self.boat.collided)
        self.sim_time += dt
        self.truth.append(self.boat.pose.copy())
        self.rc = self.signal.encode(command)
        if scan:
            # Only this scan crosses the SLAM boundary. Truth is used below by the scorer.
            if self.count == 0:
                self.initial_truth = self.boat.pose.copy()
            self.consume(self.lidar.scan(self.world, self.boat.pose, self.sim_time))
            d = self.boat.pose[:2]-self.initial_truth[:2]
            c, s = np.cos(self.initial_truth[2]), np.sin(self.initial_truth[2])
            aligned = np.array([c*d[0]+s*d[1], -s*d[0]+c*d[1], wrap(self.boat.pose[2]-self.initial_truth[2])])
            self.errors.append([np.linalg.norm(aligned[:2]-self.slam.pose[:2]), abs(wrap(aligned[2]-self.slam.pose[2]))])

    def save(self):
        save_result(self.slam, self.output)
        summary = {"mode": self.mode, "scans": self.count, "slam_status": self.slam.status,
                   "observed_cells": int(np.count_nonzero(self.slam.grid.observed)),
                   "physical_actuator_output": False, "hardware_validated": False,
                   "processing_ms_p50": float(np.median(self.processing_times)) if self.processing_times else 0,
                   "processing_ms_p95": float(np.percentile(self.processing_times, 95)) if self.processing_times else 0,
                   "recorded_frames": self.recorder.count if self.recorder else 0}
        summary["rejected_scan_matches"] = sum(p[-1].startswith(("LOST", "DEGENERATE")) for p in self.slam.trajectory)
        if self.mode == "simulate":
            summary["collision_steps"] = self.collision_steps
        if self.errors:
            e = np.asarray(self.errors)
            summary.update(position_rmse_m=float(np.sqrt(np.mean(e[:, 0]**2))),
                           final_position_error_m=float(e[-1, 0]),
                           yaw_rmse_deg=float(np.rad2deg(np.sqrt(np.mean(e[:, 1]**2)))))
            np.savetxt(self.output / "truth_evaluation.csv", np.asarray(self.truth), delimiter=",", header="x,y,yaw")
        (self.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    def close(self):
        if self.recorder:
            self.recorder.close()


def demo_command(t):
    """Reproducible open-loop test inputs, used only with explicit --demo."""
    return Command(.42, .75)


def run_gui(args, session):
    import pygame
    from .controller.input import Inputs
    from .visualization.gui import Dashboard
    ui = Dashboard()
    inputs = Inputs(args.controller_config)
    session.signal = inputs.rc
    guard, authority = ControlGuard(), SteeringAuthority()
    clock = pygame.time.Clock()
    source = None
    iterator = iter(replay(args.file)) if args.mode == "replay" else None
    next_scan = next(iterator, None) if iterator else None
    replay_start = next_scan.timestamp if next_scan else 0.0
    wall_start = time.monotonic()
    scan_accum = 0.0
    frames, running, message = 0, True, ""
    if args.mode == "lidar":
        from .lidar.sdk import SDKSource
        source = SDKSource(args.bridge, args.port, args.baud, math.radians(args.mount_yaw), recorder=session.recorder)
    try:
        while running and (not args.frames or frames < args.frames):
            dt = min(clock.tick(60)/1000, .1)
            request_arm = False
            for event in pygame.event.get():
                action = inputs.event(event)
                if action in ("changed", "lost", "stop"):
                    guard.disarm("INPUT CHANGED / STOPPED")
                request_arm |= action == "arm"
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.WINDOWFOCUSLOST:
                    guard.disarm("WINDOW UNFOCUSED: neutral")
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_RETURN:
                        request_arm = True
                    elif event.key == pygame.K_SPACE:
                        guard.disarm("STOPPED: release controls then Enter")
                    elif event.key == pygame.K_j:
                        inputs.toggle()
                        guard.disarm("INPUT SWITCHED: neutral then Enter")
                    elif event.key == pygame.K_c:
                        guard.disarm("CALIBRATING")
                        inputs.calibrate()
                    elif event.key == pygame.K_F5:
                        session.save()
                        message = "Saved map, trajectory and summary"
                    elif event.key == pygame.K_r:
                        session.slam = LidarSlam()
                        session.errors.clear()
                        session.count = 0
                        guard.disarm("SLAM RESET: new local frame")
            human, connected = inputs.read(dt)
            if request_arm:
                guard.arm(human, connected)
            now = time.monotonic()
            command = guard.apply(authority.apply(human, session.observation()), now, now, connected)
            if args.mode == "simulate":
                if args.demo:
                    command = demo_command(session.sim_time)
                scan_accum += dt
                make_scan = scan_accum >= .1
                if make_scan:
                    scan_accum %= .1
                session.simulate(command, max(dt, .001), make_scan)
            elif source:
                packet = source.poll()
                if packet:
                    session.consume(packet)
                session.source_status = source.status
            elif next_scan and now-wall_start >= (next_scan.timestamp-replay_start)/args.speed:
                session.consume(next_scan)
                next_scan = next(iterator, None)
                session.source_status = "REPLAY" if next_scan else "REPLAY COMPLETE"
            now = time.monotonic()
            age = now-session.received if session.scan else float("inf")
            timing = f"scan age {max(0, age)*1000:.0f} ms / processing {session.processing_ms:.1f} ms"
            state = "LIVE" if session.observation().fresh(now) else "STALE / NOT FOR AVOIDANCE"
            if args.mode == "replay":
                state = "REPLAY / OFFLINE"
            status = ("SCRIPTED DEMO" if args.demo else guard.reason) + " | " + state + " | " + timing
            if session.slam.grid.clipped:
                status = "MAP BOUNDARY: some rays clipped | " + status
            ui.render(session, command, status, inputs.mode, message or inputs.message)
            frames += 1
        ui.screenshot(session.output / "screenshot.png")
    finally:
        if source:
            source.close()
        pygame.quit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="CoCommand standalone 2D lidar laboratory")
    parser.add_argument("mode", choices=["simulate", "replay", "lidar", "ports"])
    parser.add_argument("--file", help="JSONL recording for replay")
    parser.add_argument("--output", default="output/"+datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--record", help="New JSONL file (existing files are never overwritten)")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Scripted software-test input, simulation only")
    parser.add_argument("--steps", type=int, default=300, help="Headless simulation scan count")
    parser.add_argument("--frames", type=int, default=0, help="Close GUI after N frames; 0 runs until closed")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--speed", type=float, default=1.0, help="Replay playback speed")
    parser.add_argument("--controller-config", default="output/controller.json")
    parser.add_argument("--bridge", help="Path to compiled cocommand_c1 bridge")
    parser.add_argument("--port", help="Explicit COM port or /dev/ttyUSB device")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--mount-yaw", type=float, default=0.0, help="Lidar forward-axis mounting yaw, degrees CCW")
    args = parser.parse_args(argv)
    if args.steps <= 0 or args.frames < 0 or not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("steps and speed must be positive; frames must be nonnegative")
    if args.demo and args.mode != "simulate":
        parser.error("--demo is simulation only")
    if args.mode == "replay" and not args.file:
        parser.error("replay requires --file")
    if args.mode == "lidar" and (not args.port or not args.bridge or args.headless):
        parser.error("lidar requires --port and --bridge, and currently uses the live GUI")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.mode == "ports":
        from .lidar.sdk import ports
        devices = ports()
        print(json.dumps(devices, ensure_ascii=False, indent=2))
        if not devices:
            print("No serial ports detected. Connect the C1 USB adapter and check its driver.")
        return 0
    session = None
    try:
        session = Session(args.mode, args.seed, args.output, args.record)
        handler = logging.FileHandler(session.output / "session.log", encoding="utf-8")
        logging.getLogger().addHandler(handler)
        if args.headless:
            if args.mode == "simulate":
                for _ in range(args.steps):
                    session.simulate(demo_command(session.sim_time) if args.demo else Command())
            else:
                for scan in replay(args.file):
                    session.consume(scan)
        else:
            run_gui(args, session)
        print(json.dumps(session.save(), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        logging.error("%s", exc)
        return 2
    finally:
        if session:
            session.close()
        if "handler" in locals():
            logging.getLogger().removeHandler(handler)
            handler.close()
