# Missing information and calibration requirements

## Manuscript / model

- `USV_Obstacle_Avoidance_and_Escape_Route_Algorithm_Report.docx` was not found.
- Identified rigid-body/added-mass matrices, damping/cross-flow details, hull dimensions,
  thrust/rudder maps, actuator constants/rate limits/delays, model-error bounds, estimator
  uncertainty, and a validated obstacle-speed interval bound are unavailable.
- The velocity-uncertainty update law and exact cross-step backup switching convention are
  not uniquely specified. Implemented rules are documented engineering assumptions.
- No manuscript simulation traces, participant data, field results, or quantitative Section 6
  results were supplied. The manuscript itself labels the figures/table as planned.

## Hardware

- Orange Pi model, RAM, OS image/kernel, scheduling policy, and power/thermal envelope.
- LiDAR model/protocol/timing/extrinsics; position/heading/velocity source and synchronization.
- Joystick model, HID axes, sign, calibration, dead zone, and disconnect behavior.
- Actuator transport/protocol, propulsion/steering feedback, neutral and rate limits, reversal
  ability and delay, mutually exclusive command rules, and valid fail action.
- External MCU/driver watchdog, independent stop path, arming procedure, bench safety plan,
  network topology, and authentication requirements.

Until these are supplied and reviewed, real hardware is `blocked_by_missing_hardware` and
the real actuator profile refuses to arm.

## Governance

- Repository authorship, copyright owner, and open-source license.
- Permission to redistribute any legacy source.
- Human-participant ethics approval, recruitment, sample size/power, instruments, consent,
  retention, anonymization, and withdrawal procedure.

