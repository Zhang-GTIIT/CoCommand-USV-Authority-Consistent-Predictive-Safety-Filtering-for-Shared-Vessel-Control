#!/usr/bin/env python3
"""Board-side controller endpoint for processor-in-the-loop simulation."""
from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path

from cocommand.config import load_json_yaml
from cocommand.hardware import BridgeGuard, make_packet
from cocommand.native import NativeController


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=49001)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--controller", default="enhanced_steering")
    args = parser.parse_args()
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    if len(token) < 16:
        parser.error("token file must contain at least 16 non-newline characters")
    server = (args.server, args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(5.0)
    hello = make_packet(0, time.monotonic(), [0.0], token)
    sock.sendto(json.dumps(hello, separators=(",", ":")).encode(), server)
    receive_guard = BridgeGuard(token, shared_clock_domain=False)
    controller_spec = load_json_yaml("configs/controllers/catalog.yaml")["controllers"][args.controller]
    with NativeController(controller_spec) as controller:
        for sequence in range(1, args.cycles + 1):
            data, source = sock.recvfrom(65535)
            if source[0] != socket.gethostbyname(args.server):
                raise RuntimeError("unexpected simulator source")
            packet = json.loads(data)
            if not receive_guard.accept(packet, time.monotonic()):
                raise RuntimeError("invalid/replayed/stale simulator packet")
            payload = packet["payload"]
            if len(payload) != 8 + 360 + 360 + 1:
                raise RuntimeError("unexpected simulator payload length")
            state = payload[:8]
            ranges = payload[8:368]
            hits = [bool(value) for value in payload[368:728]]
            healthy = bool(payload[-1])
            now = time.monotonic()
            # Sender monotonic time is retained in the packet for audit, but it is not
            # numerically comparable across hosts. Safety freshness uses local receive time.
            controller.process_scan(state, ranges, hits, 65.0, now, now)
            decision = controller.filter(state, [0.5, 0.0], healthy, now,
                                         now, now, now + 0.1, now)
            response = make_packet(sequence, time.monotonic(),
                                   [decision["applied_throttle"], decision["applied_steering_rad"]], token)
            sock.sendto(json.dumps(response, separators=(",", ":")).encode(), server)
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
