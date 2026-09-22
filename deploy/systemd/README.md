# systemd template

`cocommand-mock.service` starts only the mock runtime. It does not arm real hardware.
Copying the unit does not enable it; an administrator must create the non-root service
account, install files under `/opt/cocommand`, create writable state/log directories,
inspect paths, and then explicitly enable the unit.

There is intentionally no real-actuator service template while the board, sensors,
actuator protocol, external watchdog, independent stop path, and fail action are unknown.

