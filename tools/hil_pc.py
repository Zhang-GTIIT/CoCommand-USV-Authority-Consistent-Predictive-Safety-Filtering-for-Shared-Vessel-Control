#!/usr/bin/env python3
"""PC-side plant/sensor endpoint for processor-in-the-loop simulation.

This endpoint never writes to a real actuator. The received command is applied only to
the independent Python plant. Default binding is loopback; remote binding is explicit.
"""
from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path

from cocommand.hardware import BridgeGuard, make_packet
from cocommand.simulation import MovingObstacle, plant_step, simulate_scan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=49001)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--peer")
    args = parser.parse_args()
    if args.bind not in {"127.0.0.1", "::1"} and not args.allow_remote:
        parser.error("non-loopback bind requires --allow-remote and --peer")
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    if len(token) < 16:
        parser.error("token file must contain at least 16 non-newline characters")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    sock.settimeout(5.0)
    hello_data, peer = sock.recvfrom(65535)
    if args.peer and peer[0] != args.peer:
        raise RuntimeError(f"unexpected peer {peer[0]}")
    command_guard = BridgeGuard(token, shared_clock_domain=False)
    if not command_guard.accept(json.loads(hello_data), time.monotonic()):
        raise RuntimeError("invalid board hello")
    state = [-12.0, 0.0, 0.0, 1.0, 0.0, 0.0, 10.0, 0.0]
    obstacles = [MovingObstacle("circle", [0.0, 0.0], [0.0, 0.0], 0.8)]
    scenario: dict[str, object] = {}
    for sequence in range(1, args.cycles + 1):
        sensor_time = time.monotonic()
        ranges, hits, healthy = simulate_scan(
            state, obstacles, seed=0, time_index=sequence, time_s=sequence * 0.1,
            scenario=scenario,
        )
        payload = list(state) + ranges + [1.0 if value else 0.0 for value in hits] + [1.0 if healthy else 0.0]
        packet = make_packet(sequence, sensor_time, payload, token)
        sock.sendto(json.dumps(packet, separators=(",", ":")).encode(), peer)
        response_data, response_peer = sock.recvfrom(65535)
        if response_peer != peer:
            raise RuntimeError("peer changed during session")
        response = json.loads(response_data)
        if not command_guard.accept(response, time.monotonic()) or len(response["payload"]) != 2:
            raise RuntimeError("invalid/replayed/stale command")
        command = response["payload"]
        for _ in range(5):
            state = plant_step(state, command, 0.02)
        print(json.dumps({"cycle": sequence, "state": state, "applied": command}))
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
