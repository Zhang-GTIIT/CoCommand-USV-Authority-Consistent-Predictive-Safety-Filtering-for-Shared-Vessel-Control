from __future__ import annotations

import csv
import inspect
import math
import tempfile
import unittest
from pathlib import Path

from cocommand.config import load_json_yaml
from cocommand.depth_study import source_subset, stress_cases, trial_task
from cocommand.focused_study import cases
from cocommand.native import NativeController
from cocommand.simulation import profile_command, run_trial


class DepthStudyTests(unittest.TestCase):
    def setUp(self):
        self.protocol = load_json_yaml("configs/studies/depth_validation_v1.yaml")
        self.source = load_json_yaml("configs/studies/resume_evidence_v1.yaml")

    def test_stress_is_reproducible_distinct_and_disjoint(self):
        stress = stress_cases(self.protocol)
        self.assertEqual(stress, stress_cases(self.protocol))
        self.assertEqual(len(stress), 100)
        self.assertEqual(len({c["seed"] for c in stress}), 100)
        self.assertEqual(len({tuple(c["scenario_config"]["initial_state"]) for c in stress}), 100)
        self.assertFalse({c["seed"] for c in stress} & {c["seed"] for c in cases(self.source, "evaluation")})
        self.assertEqual(len(source_subset(cases(self.source, "evaluation"), 10)), 30)
        self.assertEqual(len(source_subset(cases(self.source, "evaluation"), 20)), 60)

    def test_paired_optimization_changes_only_flag_and_identity(self):
        case = stress_cases(self.protocol)[0]
        a, b = [trial_task(case, name, self.source, self.protocol, "R06", "test")
                for name in ["constrained", "constrained_short"]]
        self.assertNotEqual(a["task_hash"], b["task_hash"])
        self.assertTrue(b["overrides"].pop("first_complete_witness"))
        for key in set(a) - {"variant", "task_hash"}:
            self.assertEqual(a[key], b[key])

    def test_open_loop_formula_unchanged(self):
        profile = {"throttle": 0.63, "steering_bias_deg": 0.2,
                   "steering_amplitude_deg": 0.7, "frequency_rad_s": 0.3}
        self.assertEqual(profile_command(profile, 1.7, [0.0] * 8),
                         [0.63, math.radians(0.2 + 0.7 * math.sin(0.3 * 1.7))])

    def test_heading_feedback_wrap_damping_and_no_truth_argument(self):
        profile = {"mode": "heading_feedback", "throttle": 0.6, "goal_position": [-10, -0.01],
                   "heading_gain": 1.6, "yaw_rate_gain": 1.8, "max_steering_deg": 30}
        state = [0.0, 0.0, math.pi - 0.01, 1.0, 0.0, 0.0, 10.0, 0.0]
        command = profile_command(profile, 0.0, state)
        self.assertGreater(command[1], 0.0)
        self.assertLess(command[1], 0.02)
        state[5] = 1.0
        self.assertAlmostEqual(profile_command(profile, 0, state)[1], -math.pi / 6)
        self.assertEqual(set(inspect.signature(profile_command).parameters), {"profile", "time_s", "state"})
        with self.assertRaises(ValueError):
            profile_command({"mode": "unknown", "throttle": 0.6}, 0, state)

    def test_goal_stops_at_physics_substep_and_collision_has_priority(self):
        task = trial_task(stress_cases(self.protocol)[0], "open_constrained", self.source,
                          self.protocol, "R07", "test")
        task["controller"] = "unfiltered_human"
        task["scenario_config"]["initial_state"] = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 10.0, 0.0]
        task["scenario_config"]["obstacles"] = []
        task["command_profile"] = {"throttle": 0.5}
        task["goal"] = {"position": [0.04, 0.0], "radius_m": 0.005}
        with tempfile.TemporaryDirectory() as directory:
            metrics = run_trial(task, Path(directory), 0.3)
            self.assertEqual(metrics["mission_outcome"], "goal")
            self.assertAlmostEqual(metrics["goal_time_s"], 0.04)
            self.assertAlmostEqual(metrics["observed_duration_s"], 0.04)
            self.assertGreater(metrics["path_length_m"], 0)
            task["goal"]["radius_m"] = 0.1
            task["scenario_config"]["obstacles"] = [
                {"shape": "circle", "center": [0.04, 0], "velocity": [0, 0], "radius_m": 0.3}]
            collision = run_trial(task, Path(directory), 0.3)
            self.assertEqual(collision["mission_outcome"], "collision")
            self.assertFalse(collision["goal_reached"])

    def test_too_small_budget_never_accepts_partial_witness(self):
        spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]["steering_hold_contract"]
        for optimized in [False, True]:
            with NativeController(spec, {**self.source["common_overrides"], "max_integration_steps": 32,
                                         "first_complete_witness": optimized}) as controller:
                controller.process_scan([0.0] * 8, [65.0] * 360, [False] * 360, 65.0, 1.0, 1.0)
                result = controller.filter([0.0] * 8, [0.7, 0.123], True, 1, 1, 1, 1, 1)
            self.assertEqual(result["outcome"], "budget_exhausted_unknown")
            self.assertEqual(result["complete_witness_samples"], 0)
            self.assertEqual(result["applied_throttle"], 0.7)
            self.assertLessEqual(result["integration_steps"], 32)


if __name__ == "__main__":
    unittest.main()
