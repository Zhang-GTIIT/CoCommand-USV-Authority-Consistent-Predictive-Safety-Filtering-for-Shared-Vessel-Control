from __future__ import annotations

import inspect
import json
import math
import tempfile
import unittest
from pathlib import Path

from cocommand.cli import main
from cocommand.config import (ConfigError, expand_experiment, parse_seed_expression,
                              validate_catalogs, validate_experiment_config)
from cocommand.experiments import execute_tasks
from cocommand.hardware import (HardwareRefused, BridgeGuard, make_packet,
                                udp_loopback_check, validate_hardware_profile)
from cocommand.native import NativeController
from cocommand.reporting import bootstrap_mean_interval, wilson_interval
from cocommand.simulation import MovingObstacle, physical_minimum_gap, run_trial


class ConfigurationTests(unittest.TestCase):
    def test_catalogs_and_all_experiment_ids(self) -> None:
        counts = validate_catalogs()
        self.assertEqual(counts, {"experiments": 14, "controllers": 10, "scenarios": 12})
        config = validate_experiment_config("configs/experiments/E02_authority.yaml")
        self.assertEqual(config["id"], "E02")

    def test_seed_range_is_left_closed_right_open(self) -> None:
        self.assertEqual(parse_seed_expression("0:2"), [0, 1])
        self.assertEqual(parse_seed_expression("7"), [7])

    def test_smoke_expansion_is_bounded_and_deterministic(self) -> None:
        first = expand_experiment("E01", "smoke", [0])
        second = expand_experiment("E01", "smoke", [0])
        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)

    def test_unknown_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.yaml"
            path.write_text(json.dumps({"schema_version": 1, "id": "E02",
                                        "manifest": "configs/experiment_manifest_v1.yaml",
                                        "formal_results": False, "typo_budget": 80}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                validate_experiment_config(path)

    def test_trial_level_intervals(self) -> None:
        interval = wilson_interval(0, 4)
        self.assertIsNotNone(interval)
        self.assertGreater(interval[1], 0.0)
        bootstrap = bootstrap_mean_interval([0.0, 1.0], resamples=100, seed=1)
        self.assertIsNotNone(bootstrap)
        self.assertLessEqual(bootstrap[0], bootstrap[1])


class NativeAndIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = {
            "authority_mode": 1, "sampling_mode": 1, "horizon_mode": 0,
            "margin_mode": 1, "predictor_mode": 0, "backup_library_mode": 0,
            "selection_policy": 0, "fixed_horizon_s": 0.3,
            "planning_budget_ms": 80.0,
        }

    def test_exact_human_command_not_quantized_through_c_api(self) -> None:
        exact = math.radians(3.7)
        with NativeController(self.spec) as controller:
            controller.process_scan([0.0] * 8, [65.0] * 360, [False] * 360, 65.0, 1.0, 1.0)
            result = controller.filter([0.0] * 8, [0.2, exact], True, 1.0, 1.0, 1.0, 1.1, 1.0)
        self.assertEqual(result["outcome"], "witness_found")
        self.assertEqual(result["paper_status"], 0)
        self.assertAlmostEqual(result["applied_steering_rad"], exact, places=13)

    def test_controller_api_has_no_obstacle_truth_argument(self) -> None:
        parameters = set(inspect.signature(NativeController.filter).parameters)
        self.assertFalse({"obstacles", "truth", "future_motion"} & parameters)
        self.assertIn("state", parameters)

    def test_fine_physical_scorer_detects_intermediate_overlap(self) -> None:
        obstacle = MovingObstacle("circle", [0.0, 0.0], [0.0, 0.0], 0.3)
        coarse_before = [-2.0, 0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0]
        coarse_after = [2.0, 0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0]
        midpoint = [0.0, 0.0, 0.0, 20.0, 0.0, 0.0, 0.0, 0.0]
        self.assertGreater(physical_minimum_gap(coarse_before, [obstacle]), 0.0)
        self.assertGreater(physical_minimum_gap(coarse_after, [obstacle]), 0.0)
        self.assertLessEqual(physical_minimum_gap(midpoint, [obstacle]), 0.0)


class HardwareBoundaryTests(unittest.TestCase):
    def test_unknown_real_hardware_is_refused(self) -> None:
        with self.assertRaises(HardwareRefused):
            validate_hardware_profile("configs/hardware/real_unknown_disabled.yaml", enable_real=True)

    def test_bridge_rejects_duplicate_stale_corrupt_and_nonfinite(self) -> None:
        guard = BridgeGuard("token")
        packet = make_packet(1, 10.0, [0.5, 0.0], "token")
        self.assertTrue(guard.accept(packet, 10.1))
        self.assertFalse(guard.accept(packet, 10.1))
        corrupt = make_packet(2, 10.0, [0.5, 0.0], "token")
        corrupt["payload"] = [0.9, 0.0]
        self.assertFalse(guard.accept(corrupt, 10.1))
        self.assertFalse(BridgeGuard("token").accept(make_packet(1, 1.0, [0.0, 0.0], "token"), 2.0))
        self.assertFalse(BridgeGuard("token").accept(make_packet(1, 10.0, [math.nan, 0.0], "token"), 10.1))

    def test_udp_loopback(self) -> None:
        result = udp_loopback_check()
        self.assertTrue(result["bound_loopback_only"])
        self.assertTrue(result["accepted_valid"])
        self.assertTrue(result["rejected_duplicate"])
        self.assertTrue(result["rejected_corruption"])
        self.assertFalse(result["real_actuator_connected"])


class IntegrationTests(unittest.TestCase):
    def test_dry_run_and_small_headless_trial(self) -> None:
        self.assertEqual(main(["experiment", "--id", "E02", "--tier", "main", "--dry-run",
                              "--seeds", "1000:1001"]), 0)
        task = expand_experiment("E00", "smoke", [0])[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "trial"
            metrics = run_trial(task, destination, 0.2)
            self.assertEqual(metrics["label"], "software_smoke_synthetic_simulation")
            self.assertFalse(metrics["formal_evidence"])
            for name in ("manifest.json", "resolved_config.yaml", "metrics.json", "control.csv",
                         "observations.jsonl", "events.jsonl"):
                self.assertTrue((destination / name).is_file(), name)

    def test_resume_uses_config_and_code_fingerprint(self) -> None:
        task = expand_experiment("E00", "smoke", [1])[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = execute_tasks([task], run_root=root, resume=False, duration_s=0.1)
            second = execute_tasks([task], run_root=root, resume=True, duration_s=0.1)
            first_index = json.loads((first / "run_index.json").read_text())
            second_index = json.loads((second / "run_index.json").read_text())
            self.assertEqual(first_index[0]["status"], "completed")
            self.assertEqual(second_index[0]["status"], "resumed")


if __name__ == "__main__":
    unittest.main()
