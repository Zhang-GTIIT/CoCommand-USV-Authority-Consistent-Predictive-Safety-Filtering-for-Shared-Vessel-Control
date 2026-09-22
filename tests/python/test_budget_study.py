from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from cocommand.budget_study import diagnose_case, fresh_cases, make_task, variants
from cocommand.config import load_json_yaml
from cocommand.depth_study import stress_cases
from cocommand.focused_study import cases
from cocommand.native import NativeController
from cocommand.simulation import run_trial


class BudgetStudyTests(unittest.TestCase):
    def setUp(self):
        self.protocol = load_json_yaml("configs/studies/budget_allocation_v1.yaml")

    def test_fresh_cases_are_disjoint_and_study_is_bounded(self):
        new = fresh_cases(self.protocol)
        self.assertEqual(new, fresh_cases(self.protocol))
        self.assertEqual(len(new), 60)
        self.assertEqual(len(variants(self.protocol)) * len(new), 540)
        self.assertEqual(len(self.protocol["feedback_variants"]) * len(new), 300)
        old = cases(load_json_yaml(self.protocol["source_protocol"]), "evaluation")
        old += stress_cases(load_json_yaml("configs/studies/depth_validation_v1.yaml"))
        self.assertFalse({c["seed"] for c in new} & {c["seed"] for c in old})
        self.assertEqual(len({c["seed"] for c in new}), 60)

    def test_primary_pair_changes_only_sampling_and_identity(self):
        case = fresh_cases(self.protocol)[0]
        left, right = [make_task(case, name, self.protocol, "R08_open", "test")
                       for name in self.protocol["primary_contrast"]]
        self.assertNotEqual(left["task_hash"], right["task_hash"])
        self.assertEqual(left["overrides"].pop("sampling_mode"), 1)
        self.assertEqual(right["overrides"].pop("sampling_mode"), 0)
        for key in set(left) - {"variant", "task_hash"}:
            self.assertEqual(left[key], right[key])

    def test_coarse_sampling_preserves_exact_human_input(self):
        spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"]["steering_hold_contract"]
        for sampling in [0, 1]:
            with NativeController(spec, {"sampling_mode": sampling, "first_complete_witness": True,
                                         "deadline_aware": False, "max_integration_steps": 512}) as controller:
                controller.process_scan([0.0] * 8, [65.0] * 360, [False] * 360, 65, 0, 0)
                result = controller.filter([0.0] * 8, [0.61, 0.1234567], True, 0, 0, 0, 0, 0)
            self.assertEqual(result["outcome"], "witness_found")
            self.assertEqual(result["applied_throttle"], 0.61)
            self.assertEqual(result["applied_steering_rad"], 0.1234567)
            self.assertEqual(result["complete_witness_samples"], 52)
            self.assertEqual(result["integration_steps"], 51)

    def test_diagnostic_reproduces_source_commands(self):
        task = make_task(fresh_cases(self.protocol)[0], "u2_first_b512", self.protocol, "R08_open", "test")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_trial(task, root / "source", 0.2)
            result = diagnose_case(root / "source", root / "diagnosis")
            self.assertEqual(result["calls"], 2)
            self.assertEqual(result["reproduction_mismatches"], 0)
            self.assertEqual(result["invalid_reference_witnesses"], 0)


if __name__ == "__main__":
    unittest.main()
