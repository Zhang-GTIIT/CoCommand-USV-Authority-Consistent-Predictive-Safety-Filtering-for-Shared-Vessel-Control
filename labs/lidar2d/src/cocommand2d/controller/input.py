from dataclasses import asdict
import json
from pathlib import Path
import pygame
from .signals import Axis, Command, RCSignal


class Inputs:
    def __init__(self, config=None):
        pygame.joystick.init()
        self.config_path = Path(config) if config else None
        data = json.loads(self.config_path.read_text(encoding="utf-8")) if self.config_path and self.config_path.exists() else {}
        self.throttle = Axis(**data.get("throttle", {"index": 1, "invert": True}))
        self.steering = Axis(**data.get("steering", {"index": 0, "invert": True}))
        self.buttons = data.get("buttons", {"arm": 0, "stop": 1})
        self.rc = RCSignal(**data.get("rc", {}))
        self.joystick = None
        self.mode = "keyboard"
        self.keyboard = Command()
        self.message = "Keyboard ready"
        self.calibration = None
        self.detect()

    def detect(self):
        if self.joystick is None and pygame.joystick.get_count():
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.message = f"Detected {self.joystick.get_name()}; J selects gamepad"

    def event(self, event):
        if event.type == pygame.JOYDEVICEADDED:
            self.detect()
            return "changed"
        if event.type == pygame.JOYDEVICEREMOVED and self.joystick and event.instance_id == self.joystick.get_instance_id():
            self.joystick.quit()
            self.joystick = None
            self.message = "Gamepad disconnected"
            return "lost"
        if (event.type == pygame.JOYBUTTONDOWN and self.mode == "gamepad" and self.joystick
                and event.instance_id == self.joystick.get_instance_id()):
            return next((name for name, button in self.buttons.items() if button == event.button), None)
        return None

    def toggle(self):
        self.mode = "gamepad" if self.mode == "keyboard" else "keyboard"
        self.keyboard = Command()

    def calibrate(self):
        if not self.joystick:
            self.message = "Calibration needs a connected gamepad"
            return
        if self.calibration is None:
            self.calibration = [[float("inf"), float("-inf")] for _ in range(self.joystick.get_numaxes())]
            self.message = "Sweep sticks/triggers fully; release to neutral; press C again"
        else:
            try:
                calibrated = []
                for axis in (self.throttle, self.steering):
                    lo, hi = self.calibration[axis.index]
                    center = self.joystick.get_axis(axis.index)
                    if hi-lo < .5:
                        raise ValueError("Axis travel too small; sweep full range")
                    calibrated.append(Axis(axis.index, lo, center, hi, axis.invert, axis.deadzone, axis.mode))
                self.throttle, self.steering = calibrated
                if self.config_path:
                    self.config_path.parent.mkdir(parents=True, exist_ok=True)
                    self.config_path.write_text(json.dumps({"throttle": asdict(self.throttle),
                        "steering": asdict(self.steering), "buttons": self.buttons,
                        "rc": asdict(self.rc)}, indent=2), encoding="utf-8")
                self.message = "Calibration saved; neutral then Enter to arm"
            except (ValueError, IndexError) as exc:
                self.message = str(exc)
            finally:
                self.calibration = None

    def read(self, dt, keys=None):
        if self.calibration is not None and self.joystick:
            for i, limits in enumerate(self.calibration):
                v = self.joystick.get_axis(i)
                limits[0], limits[1] = min(limits[0], v), max(limits[1], v)
            return Command(), False
        if self.mode == "gamepad":
            if not self.joystick:
                return Command(), False
            try:
                return Command(self.throttle.map(self.joystick.get_axis(self.throttle.index)),
                               self.steering.map(self.joystick.get_axis(self.steering.index))), True
            except (pygame.error, ValueError, IndexError) as exc:
                self.message = f"Gamepad input error: {exc}"
                return Command(), False
        keys = pygame.key.get_pressed() if keys is None else keys
        target_t = int(bool(keys[pygame.K_w] or keys[pygame.K_UP])) - int(bool(keys[pygame.K_s] or keys[pygame.K_DOWN]))
        target_s = int(bool(keys[pygame.K_a] or keys[pygame.K_LEFT])) - int(bool(keys[pygame.K_d] or keys[pygame.K_RIGHT]))
        def ramp(current, target, rate):
            return current + max(-rate*dt, min(rate*dt, target-current))
        self.keyboard = Command(ramp(self.keyboard.throttle, target_t, 1.2), ramp(self.keyboard.steering, target_s, 2.5))
        return self.keyboard, True
