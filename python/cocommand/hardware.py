from __future__ import annotations

import hashlib
import json
import math
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_json_yaml


class HardwareRefused(RuntimeError):
    pass


def validate_hardware_profile(path: str | Path, enable_real: bool = False) -> dict[str, Any]:
    profile = load_json_yaml(path)
    required = {"schema_version", "id", "real_output"}
    if missing := required - profile.keys():
        raise HardwareRefused(f"hardware profile missing {sorted(missing)}")
    if enable_real:
        missing_values = [field for field in profile.get("required_before_enable", [])
                          if profile.get(field) in (None, "", False)]
        if not profile.get("enabled") or not profile.get("real_output") or missing_values:
            raise HardwareRefused(
                "real hardware enable refused; profile is disabled/incomplete: " +
                ", ".join(missing_values or ["enabled", "real_output"])
            )
    return profile


@dataclass
class BridgeGuard:
    token: str
    last_sequence: int = -1
    max_age_s: float = 0.5
    shared_clock_domain: bool = True

    def accept(self, packet: dict[str, Any], now: float) -> bool:
        required = {"version", "sequence", "timestamp", "healthy", "payload", "token", "checksum"}
        if set(packet) != required or packet["token"] != self.token or packet["version"] != 1:
            return False
        body = {key: packet[key] for key in packet if key != "checksum"}
        expected = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if packet["checksum"] != expected or packet["sequence"] <= self.last_sequence:
            return False
        if not math.isfinite(float(packet["timestamp"])) or not packet["healthy"]:
            return False
        if self.shared_clock_domain and now - float(packet["timestamp"]) > self.max_age_s:
            return False
        if not all(math.isfinite(float(value)) for value in packet["payload"]):
            return False
        self.last_sequence = int(packet["sequence"])
        return True


def make_packet(sequence: int, timestamp: float, payload: list[float], token: str) -> dict[str, Any]:
    packet: dict[str, Any] = {"version": 1, "sequence": sequence, "timestamp": timestamp,
                              "healthy": True, "payload": payload, "token": token}
    packet["checksum"] = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return packet


def udp_loopback_check() -> dict[str, Any]:
    token = "test-session-token-not-for-real-hardware"
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(1.0)
    address = receiver.getsockname()
    now = time.monotonic()
    packet = make_packet(1, now, [0.5, 0.0], token)
    sender.sendto(json.dumps(packet).encode(), address)
    data, source = receiver.recvfrom(4096)
    decoded = json.loads(data)
    guard = BridgeGuard(token)
    accepted = source[0] == "127.0.0.1" and guard.accept(decoded, time.monotonic())
    duplicate_rejected = not guard.accept(decoded, time.monotonic())
    corrupted = dict(decoded)
    corrupted["sequence"] = 2
    corrupted_rejected = not guard.accept(corrupted, time.monotonic())
    receiver.close()
    sender.close()
    return {"bound_loopback_only": True, "accepted_valid": accepted,
            "rejected_duplicate": duplicate_rejected, "rejected_corruption": corrupted_rejected,
            "real_actuator_connected": False}
