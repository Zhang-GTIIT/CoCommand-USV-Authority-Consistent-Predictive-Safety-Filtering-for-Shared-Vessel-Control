from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Command:
    throttle: float = 0.0
    steering: float = 0.0  # +1 = left / CCW

    def __post_init__(self):
        if not all(math.isfinite(x) and -1 <= x <= 1 for x in (self.throttle, self.steering)):
            raise ValueError("Commands must be finite in [-1, 1]")


@dataclass
class Axis:
    index: int = 0
    minimum: float = -1.0
    center: float = 0.0
    maximum: float = 1.0
    invert: bool = False
    deadzone: float = 0.08
    mode: str = "signed"

    def __post_init__(self):
        if (self.index < 0 or not 0 <= self.deadzone < .8 or self.mode not in ("signed", "trigger")
                or not all(math.isfinite(x) for x in (self.minimum, self.center, self.maximum))
                or not self.minimum < self.maximum
                or (self.mode == "signed" and not self.minimum < self.center < self.maximum)):
            raise ValueError("Invalid axis calibration")

    def map(self, raw):
        if not math.isfinite(raw):
            raise ValueError("Nonfinite joystick input")
        if self.mode == "trigger":
            value = (raw-self.minimum)/(self.maximum-self.minimum)
            value = 1-value if self.invert else value
        else:
            value = (raw-self.center) / (self.maximum-self.center if raw >= self.center else self.center-self.minimum)
            value = -value if self.invert else value
        value = max(0 if self.mode == "trigger" else -1, min(1, value))
        return math.copysign(max(0, (abs(value)-self.deadzone)/(1-self.deadzone)), value)


class ControlGuard:
    def __init__(self, timeout=.3):
        self.armed = False
        self.timeout = timeout
        self.reason = "DISARMED: press Enter at neutral"

    def disarm(self, reason="STOPPED"):
        self.armed = False
        self.reason = reason

    def arm(self, command, connected=True):
        if connected and abs(command.throttle) < .02 and abs(command.steering) < .02:
            self.armed = True
            self.reason = "ARMED (simulation only)"
        return self.armed

    def apply(self, command, sample_time, now, connected=True):
        if not connected or now-sample_time > self.timeout or sample_time > now:
            self.disarm("INPUT LOST: neutral; reconnect and re-arm")
        return command if self.armed else Command()


@dataclass
class RCSignal:
    minimum_us: int = 1000
    neutral_us: int = 1500
    maximum_us: int = 2000

    def __post_init__(self):
        if not 500 <= self.minimum_us < self.neutral_us < self.maximum_us <= 2500:
            raise ValueError("Invalid simulated PWM configuration")

    def encode(self, command):
        def pulse(value):
            span = self.maximum_us-self.neutral_us if value >= 0 else self.neutral_us-self.minimum_us
            return round(self.neutral_us + value*span)
        return {"throttle_us": pulse(command.throttle), "steering_us": pulse(command.steering),
                "physical_output": False}


class SteeringAuthority:
    """Future CoCommand seam: hook(observation, human) -> steering only.

    The observation must be derived from scans/SLAM. No simulator truth is passed.
    This version has no safety filter or navigation controller installed.
    """
    def __init__(self, hook=None):
        self.hook = hook

    def apply(self, human, observation=None):
        steering = human.steering if self.hook is None else float(self.hook(observation, human))
        if not math.isfinite(steering):
            raise ValueError("Steering hook returned a nonfinite command")
        return Command(human.throttle, max(-1, min(1, steering)))
