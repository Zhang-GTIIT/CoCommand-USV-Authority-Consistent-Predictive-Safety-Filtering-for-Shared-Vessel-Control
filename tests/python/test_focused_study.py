from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from cocommand.config import load_json_yaml
from cocommand.focused_study import cases, make_task, same_decision
from cocommand.native import NativeController
from cocommand.simulation import run_trial


class FocusedStudyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_json_yaml("configs/studies/resume_evidence_v1.yaml")

    def test_distinct_reproducible_cases_and_disjoint_pilot(self):
        evaluation = cases(self.config, "evaluation")
        self.assertEqual(evaluation, cases(self.config, "evaluation"))
        self.assertEqual(len(evaluation), 90)
        self.assertEqual(len({tuple(c["scenario_config"]["initial_state"]) for c in evaluation}), 90)
        self.assertFalse({c["seed"] for c in evaluation} & {c["seed"] for c in cases(self.config, "pilot")})

    def test_pairing_changes_only_controller(self):
        case = cases(self.config, "pilot")[0]
        a, b = [make_task(case, name, self.config, "pilot") for name in self.config["controllers"]]
        for key in set(a) - {"controller", "task_hash"}:
            self.assertEqual(a[key], b[key])

    def test_trial_uses_resolved_scenario_and_pipeline_timestamps(self):
        task = make_task(cases(self.config, "pilot")[0], "steering_hold_contract", self.config, "pilot")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metrics = run_trial(task, root, 0.2)
            self.assertEqual(metrics["label"], "synthetic_controlled_evaluation")
            self.assertEqual(metrics["applied_throttle_violation_cycles"], 0)
            with (root / "control.csv").open(newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertAlmostEqual(float(row["state_timestamp_s"]), 0.1)
            self.assertAlmostEqual(float(row["apply_timestamp_s"]), 0.0)
            self.assertGreaterEqual(float(row["end_to_end_latency_ms"]), float(row["planning_latency_ms"]))

    def test_dedup_matches_original_on_observed_scene(self):
        spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]["steering_hold_contract"]
        outputs = []
        for mode in [0, 1]:
            with NativeController(spec, {**self.config["common_overrides"], "backup_library_mode": mode}) as controller:
                controller.process_scan([0.0] * 8, [65.0] * 360, [False] * 360, 65.0, 1.0, 1.0)
                outputs.append(controller.filter([0.0] * 8, [0.5, 0.0], True, 1.0, 1.0, 1.0, 1.0, 1.0))
        self.assertTrue(same_decision(*outputs))
        self.assertLess(outputs[1]["integration_steps"], outputs[0]["integration_steps"])

    def test_short_circuit_preserves_exact_input_and_complete_witness(self):
        spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]["steering_hold_contract"]
        with NativeController(spec, {"deadline_aware": False, "first_complete_witness": True}) as controller:
            controller.process_scan([0.0] * 8, [65.0] * 360, [False] * 360, 65.0, 1.0, 1.0)
            result = controller.filter([0.0] * 8, [0.5, 0.123], True, 1.0, 1.0, 1.0, 1.0, 1.0)
        self.assertEqual(result["applied_steering_rad"], 0.123)
        self.assertEqual(result["complete_witness_samples"], 52)
        self.assertEqual(result["evaluated_branches"], 1)

    def test_short_circuit_rejects_emergency_authority(self):
        with self.assertRaises(ValueError):
            NativeController({"authority_mode": 2, "first_complete_witness": True})


if __name__ == "__main__":
    unittest.main()
