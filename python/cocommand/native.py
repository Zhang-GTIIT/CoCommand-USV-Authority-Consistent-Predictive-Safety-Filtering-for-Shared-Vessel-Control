from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any, Sequence

from .config import REPO_ROOT


class NativeUnavailable(RuntimeError):
    pass


class CCConfig(ctypes.Structure):
    _fields_ = [
        ("authority_mode", ctypes.c_int),
        ("sampling_mode", ctypes.c_int),
        ("horizon_mode", ctypes.c_int),
        ("margin_mode", ctypes.c_int),
        ("predictor_mode", ctypes.c_int),
        ("backup_library_mode", ctypes.c_int),
        ("selection_policy", ctypes.c_int),
        ("fixed_horizon_s", ctypes.c_double),
        ("planning_budget_ms", ctypes.c_double),
        ("base_margin_m", ctypes.c_double),
        ("covariance_alpha", ctypes.c_double),
        ("deadline_aware", ctypes.c_int),
        ("reverse_available", ctypes.c_int),
        ("sweep_margin_enabled", ctypes.c_int),
        ("radius_inflation_enabled", ctypes.c_int),
        ("track_memory_s", ctypes.c_double),
        ("max_integration_steps", ctypes.c_uint64),
    ]


class CCFilterResult(ctypes.Structure):
    _fields_ = [
        ("applied_throttle", ctypes.c_double),
        ("applied_steering_rad", ctypes.c_double),
        ("outcome", ctypes.c_int),
        ("paper_status", ctypes.c_int),
        ("predicted_minimum_clearance_m", ctypes.c_double),
        ("requested_horizon_s", ctypes.c_double),
        ("actual_horizon_s", ctypes.c_double),
        ("latency_ms", ctypes.c_double),
        ("evaluated_candidates", ctypes.c_uint64),
        ("evaluated_branches", ctypes.c_uint64),
        ("integration_steps", ctypes.c_uint64),
        ("search_complete", ctypes.c_int),
        ("minimality_established", ctypes.c_int),
        ("recovery_active", ctypes.c_int),
        ("used_hypothetical_throttle", ctypes.c_int),
        ("witness_required_throttle", ctypes.c_double),
    ]


OUTCOMES = {
    0: "witness_found", 1: "exhausted_no_witness", 2: "budget_exhausted_unknown",
    3: "invalid_input", 4: "stale_input", 5: "numerical_failure",
}


def native_library_candidates() -> list[Path]:
    names = ["cocommand_c.dll", "libcocommand_c.dll", "libcocommand_c.so", "libcocommand_c.dylib"]
    directories = [REPO_ROOT / "build", REPO_ROOT / "build" / "Release",
                   REPO_ROOT / "build-zig", REPO_ROOT / "build-arm64"]
    candidates: list[Path] = []
    if os.environ.get("COCOMMAND_NATIVE_LIB"):
        candidates.append(Path(os.environ["COCOMMAND_NATIVE_LIB"]))
    for directory in directories:
        candidates.extend(directory / name for name in names)
    return candidates


def find_native_library() -> Path:
    for candidate in native_library_candidates():
        if candidate.is_file():
            return candidate.resolve()
    raise NativeUnavailable("native core not found; configure/build CMake first or set COCOMMAND_NATIVE_LIB")


class NativeController:
    def __init__(self, controller_config: dict[str, Any], overrides: dict[str, Any] | None = None):
        self.path = find_native_library()
        self.lib = ctypes.CDLL(str(self.path))
        self._bind()
        values = dict(controller_config)
        values.update(_translate_overrides(overrides or {}))
        self.config = CCConfig(
            int(values.get("authority_mode", 1)), int(values.get("sampling_mode", 1)),
            int(values.get("horizon_mode", 1)), int(values.get("margin_mode", 1)),
            int(values.get("predictor_mode", 0)), int(values.get("backup_library_mode", 0)),
            int(values.get("selection_policy", 0)), float(values.get("fixed_horizon_s", 10.1)),
            float(values.get("planning_budget_ms", 80.0)), float(values.get("base_margin_m", 0.7)),
            float(values.get("covariance_alpha", 0.05)), int(bool(values.get("deadline_aware", True))),
            int(bool(values.get("reverse_available", True))),
            int(bool(values.get("sweep_margin_enabled", True))),
            int(bool(values.get("radius_inflation_enabled", True))),
            float(values.get("track_memory_s", 3.0)),
            int(values.get("max_integration_steps", 2**63 - 1)),
        )
        self.handle = self.lib.cc_create(ctypes.byref(self.config))
        if not self.handle:
            raise NativeUnavailable("cc_create failed")
        if values.get("first_complete_witness", False):
            if not hasattr(self.lib, "cc_set_first_complete_witness"):
                self.close()
                raise NativeUnavailable("native library lacks first-complete-witness support; rebuild")
            self.lib.cc_set_first_complete_witness.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.lib.cc_set_first_complete_witness.restype = ctypes.c_int
            if self.lib.cc_set_first_complete_witness(self.handle, 1) != 0:
                self.close()
                raise ValueError("first-complete-witness requires steering-only minimum-modification control")

    def _bind(self) -> None:
        self.lib.cc_create.argtypes = [ctypes.POINTER(CCConfig)]
        self.lib.cc_create.restype = ctypes.c_void_p
        self.lib.cc_destroy.argtypes = [ctypes.c_void_p]
        self.lib.cc_process_scan.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_double,
            ctypes.c_double, ctypes.c_double,
        ]
        self.lib.cc_process_scan.restype = ctypes.c_int
        self.lib.cc_filter.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.c_int, ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.c_double, ctypes.c_double, ctypes.POINTER(CCFilterResult),
        ]
        self.lib.cc_filter.restype = ctypes.c_int
        self.has_witness_summary = hasattr(self.lib, "cc_last_complete_witness_samples")
        if self.has_witness_summary:
            self.lib.cc_last_complete_witness_samples.argtypes = [ctypes.c_void_p]
            self.lib.cc_last_complete_witness_samples.restype = ctypes.c_size_t

    def close(self) -> None:
        if getattr(self, "handle", None):
            self.lib.cc_destroy(self.handle)
            self.handle = None

    def __enter__(self) -> "NativeController":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def process_scan(self, state: Sequence[float], ranges: Sequence[float], hits: Sequence[bool],
                     max_range_m: float, sensor_time: float, receive_time: float) -> int:
        if len(state) != 8 or len(ranges) != len(hits):
            raise ValueError("state must have 8 values and scan arrays must have equal length")
        state_array = (ctypes.c_double * 8)(*state)
        range_array = (ctypes.c_double * len(ranges))(*ranges)
        hit_array = (ctypes.c_uint8 * len(hits))(*(1 if value else 0 for value in hits))
        result = self.lib.cc_process_scan(self.handle, state_array, range_array, hit_array,
                                          len(ranges), max_range_m, sensor_time, receive_time)
        if result < 0:
            raise ValueError(f"native scan rejected with code {result}")
        return result

    def filter(self, state: Sequence[float], human: Sequence[float], healthy: bool,
               sensor_time: float, receive_time: float, aligned_time: float,
               apply_time: float, now: float) -> dict[str, Any]:
        state_array = (ctypes.c_double * 8)(*state)
        command_array = (ctypes.c_double * 2)(*human)
        output = CCFilterResult()
        code = self.lib.cc_filter(self.handle, state_array, command_array, int(healthy),
                                  sensor_time, receive_time, aligned_time, apply_time,
                                  now, ctypes.byref(output))
        if code != 0:
            raise NativeUnavailable(f"cc_filter failed with code {code}")
        return {
            "applied_throttle": output.applied_throttle,
            "applied_steering_rad": output.applied_steering_rad,
            "outcome": OUTCOMES.get(output.outcome, f"unknown_{output.outcome}"),
            "paper_status": output.paper_status,
            "predicted_minimum_clearance_m": output.predicted_minimum_clearance_m,
            "requested_horizon_s": output.requested_horizon_s,
            "actual_horizon_s": output.actual_horizon_s,
            "latency_ms": output.latency_ms,
            "evaluated_candidates": output.evaluated_candidates,
            "evaluated_branches": output.evaluated_branches,
            "integration_steps": output.integration_steps,
            "search_complete": bool(output.search_complete),
            "minimality_established": bool(output.minimality_established),
            "recovery_active": bool(output.recovery_active),
            "used_hypothetical_throttle": bool(output.used_hypothetical_throttle),
            "witness_required_throttle": output.witness_required_throttle,
            "complete_witness_samples": (int(self.lib.cc_last_complete_witness_samples(self.handle))
                                         if self.has_witness_summary else None),
        }


def _translate_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    values = dict(overrides)
    if values.get("horizon_s") == "adaptive_guarded":
        values["horizon_mode"] = 2
    elif isinstance(values.get("horizon_s"), (int, float)):
        values["horizon_mode"] = 0
        values["fixed_horizon_s"] = float(values["horizon_s"])
    margin_names = {"fixed": 0, "paper": 1, "covariance": 2}
    if values.get("margin_mode") in margin_names:
        values["margin_mode"] = margin_names[values["margin_mode"]]
    if "alpha" in values:
        values["covariance_alpha"] = values["alpha"]
    if values.get("ablation") == "no_track_memory":
        values["track_memory_s"] = 0.0
    if values.get("ablation") == "no_uncertainty_radius":
        values["radius_inflation_enabled"] = False
    if values.get("ablation") == "no_sweep_margin":
        values["sweep_margin_enabled"] = False
    return values
