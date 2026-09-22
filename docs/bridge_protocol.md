# PC-board simulation bridge

The bridge is for mock processor-in-the-loop work only. The PC endpoint owns the
independent plant and synthetic sensor. The board endpoint runs the native C++ control
core and returns a command that the PC plant actually applies.

Packets contain protocol version, strictly increasing sequence, sender-monotonic timestamp,
health, numeric payload, a per-session token, and a SHA-256 integrity checksum. The
receiver rejects bad versions/tokens/checksums, duplicate or old sequences, stale packets,
unhealthy packets, and non-finite values. This is a research loopback protocol, not a
cryptographic actuator protocol. It never maps to GPIO/serial/propulsion output.

Monotonic epochs are host-local. For two hosts the bridge logs the sender timestamp but uses
the receiver's local monotonic arrival time for freshness/alignment; it does not subtract two
unrelated monotonic clocks. Network delay and clock synchronization must be measured and
calibrated before interpreting HIL timing.

Both endpoints default to loopback. Non-loopback PC binding requires `--allow-remote`
and an exact `--peer` address. Use a private isolated network and a fresh token file.

PC:

```sh
PYTHONPATH=python python3 tools/hil_pc.py --token-file bridge-token.txt --cycles 20
```

Board (or a second local shell):

```sh
PYTHONPATH=python COCOMMAND_NATIVE_LIB=build/libcocommand_c.so \
  python3 tools/hil_board.py --token-file bridge-token.txt --cycles 20
```
