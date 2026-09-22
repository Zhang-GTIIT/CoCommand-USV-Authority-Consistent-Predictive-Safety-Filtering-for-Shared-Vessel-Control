#pragma once

#include "cocommand/core.hpp"
#include "cocommand/perception.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace cocommand {

struct RuntimeHealth {
  bool healthy{false};
  bool input_fresh{false};
  bool actuator_feedback_available{false};
  bool external_watchdog_available{false};
  std::string detail{};
};

struct SequencedCommand {
  std::uint64_t sequence{0};
  double generated_monotonic_s{0.0};
  HumanCommand command{};
};

class JoystickSource {
 public:
  virtual ~JoystickSource() = default;
  virtual std::optional<HumanCommand> read(double monotonic_now_s) = 0;
};

class LidarSource {
 public:
  virtual ~LidarSource() = default;
  virtual std::optional<TimedScan> read(double monotonic_now_s) = 0;
};

class VesselStateSource {
 public:
  virtual ~VesselStateSource() = default;
  virtual std::optional<VesselState> read(double monotonic_now_s) = 0;
};

class ActuatorSink {
 public:
  virtual ~ActuatorSink() = default;
  virtual bool arm(const std::string& manual_token) = 0;
  virtual bool send(const SequencedCommand& command, double monotonic_now_s) = 0;
  virtual void disarm() = 0;
};

class HealthMonitor {
 public:
  virtual ~HealthMonitor() = default;
  virtual RuntimeHealth status(double monotonic_now_s) const = 0;
};

class MockActuatorSink final : public ActuatorSink {
 public:
  bool arm(const std::string& manual_token) override;
  bool send(const SequencedCommand& command, double monotonic_now_s) override;
  void disarm() override;
  bool armed() const { return armed_; }
  std::optional<SequencedCommand> last_command() const { return last_command_; }
 private:
  bool armed_{false};
  std::optional<SequencedCommand> last_command_{};
};

class UnknownHardwareActuatorSink final : public ActuatorSink {
 public:
  bool arm(const std::string& manual_token) override;
  bool send(const SequencedCommand& command, double monotonic_now_s) override;
  void disarm() override {}
  const std::string& refusal_reason() const { return refusal_reason_; }
 private:
  std::string refusal_reason_{"hardware profile/protocol/watchdog/fail action are unverified"};
};

}  // namespace cocommand

