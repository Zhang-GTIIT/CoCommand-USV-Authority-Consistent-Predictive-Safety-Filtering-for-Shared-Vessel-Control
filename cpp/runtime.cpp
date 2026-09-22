#include "cocommand/runtime.hpp"

#include <cmath>

namespace cocommand {

bool MockActuatorSink::arm(const std::string& manual_token) {
  armed_ = manual_token == "MOCK_ONLY";
  if (!armed_) last_command_.reset();
  return armed_;
}

bool MockActuatorSink::send(const SequencedCommand& command, double monotonic_now_s) {
  if (!armed_ || !std::isfinite(command.generated_monotonic_s) ||
      !std::isfinite(command.command.throttle) ||
      !std::isfinite(command.command.steering_rad) ||
      command.command.throttle < -1.0 || command.command.throttle > 1.0 ||
      std::abs(command.command.steering_rad) > deg2rad(30.0) ||
      monotonic_now_s - command.generated_monotonic_s > 0.30 ||
      (last_command_ && command.sequence <= last_command_->sequence)) {
    return false;
  }
  last_command_ = command;
  return true;
}

void MockActuatorSink::disarm() {
  armed_ = false;
  last_command_.reset();
}

bool UnknownHardwareActuatorSink::arm(const std::string& manual_token) {
  (void)manual_token;
  return false;
}

bool UnknownHardwareActuatorSink::send(const SequencedCommand& command,
                                       double monotonic_now_s) {
  (void)command;
  (void)monotonic_now_s;
  return false;
}

}  // namespace cocommand
