import json
import logging
from pathlib import Path
import queue
import subprocess
import threading
import time
from ..scan import Scan

LOG = logging.getLogger(__name__)


def ports():
    from serial.tools import list_ports
    return [{"device": p.device, "description": p.description, "hwid": p.hwid} for p in list_ports.comports()]


def decode_line(line, mount_yaw=0.0, received=None):
    data = json.loads(line)
    if data.get("type") != "scan":
        raise ValueError("Expected SDK scan packet")
    # Host monotonic reception time remains increasing across bridge restarts.
    return Scan.from_c1(time.monotonic() if received is None else received, data["angles_cw_deg"], data["distances_mm"],
                        data["quality"], mount_yaw)


class SDKSource:
    def __init__(self, bridge, port, baud=460800, mount_yaw=0.0, stall_timeout=4.0, recorder=None):
        self.bridge = Path(bridge).resolve()
        if not self.bridge.is_file():
            raise FileNotFoundError(f"SDK bridge missing: {self.bridge}. Build native/ first.")
        if not port:
            raise ValueError("An explicit --port is required; use ports to list devices")
        self.args = [str(self.bridge), port, str(baud)]
        self.mount_yaw = mount_yaw
        self.stall_timeout = stall_timeout
        self.recorder = recorder
        self.scans = queue.Queue(maxsize=8)
        self.stop = threading.Event()
        self.status = "CONNECTING"
        self.process = None
        self.dropped = 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _stderr(self, process):
        for line in process.stderr:
            if line.strip():
                LOG.info("SDK: %s", line.strip())
                self.status = line.strip()[:180]

    def _stdout(self, process, packets):
        for line in process.stdout:
            try:
                packets.put_nowait((time.monotonic(), line))
            except queue.Full:
                self.dropped += 1

    def _run(self):
        delay = 1.0
        while not self.stop.is_set():
            process = None
            try:
                self.status = "CONNECTING: " + self.args[1]
                LOG.info(self.status)
                process = subprocess.Popen(self.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.process = process
                packets = queue.Queue(maxsize=16)
                readers = [threading.Thread(target=self._stderr, args=(process,), daemon=True),
                           threading.Thread(target=self._stdout, args=(process, packets), daemon=True)]
                for reader in readers:
                    reader.start()
                last = time.monotonic()
                while not self.stop.is_set():
                    if process.poll() is not None:
                        raise ConnectionError(f"SDK exited {process.returncode}; check port, power and permissions")
                    try:
                        received, line = packets.get(timeout=.1)
                    except queue.Empty:
                        if time.monotonic()-last > self.stall_timeout:
                            raise TimeoutError("No scan received; SDK stalled or lidar disconnected")
                        continue
                    scan = decode_line(line, self.mount_yaw, received)
                    if self.recorder:
                        self.recorder.write(scan)
                    last = time.monotonic()
                    delay = 1.0
                    if self.scans.full():
                        try:
                            self.scans.get_nowait()
                            self.dropped += 1
                        except queue.Empty:
                            pass
                    self.scans.put_nowait(scan)
                    self.status = f"SCANNING {self.args[1]} / dropped {self.dropped}"
            except (OSError, ValueError, TypeError, KeyError, ConnectionError, TimeoutError) as exc:
                self.status = f"DISCONNECTED: {exc}; retry in {delay:g}s"
                LOG.warning(self.status)
            finally:
                if process:
                    if process.poll() is None:
                        try:
                            process.stdin.write("stop\n")
                            process.stdin.flush()
                        except (OSError, ValueError):
                            pass
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    for reader in readers:
                        reader.join(timeout=1)
                    process.stdin.close()
                    process.stdout.close()
                    process.stderr.close()
                self.process = None
            self.stop.wait(delay)
            delay = min(delay*2, 8)

    def poll(self):
        # Drain backlog: the GUI/avoidance seam must receive the newest available scan.
        # Recording takes place before this bounded display queue.
        latest = None
        while True:
            try:
                packet = self.scans.get_nowait()
                self.dropped += int(latest is not None)
                latest = packet
            except queue.Empty:
                return latest

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
