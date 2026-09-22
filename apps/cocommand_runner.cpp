#include "cocommand/core.hpp"
#include "cocommand/perception.hpp"

#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

using namespace cocommand;

namespace {

int selftest() {
  const auto grid = paper_time_grid();
  if (grid.size() != 52 || std::abs(grid.front()) > 1e-12 ||
      std::abs(grid.back() - 10.1) > 1e-12) return 2;
  Snapshot snapshot;
  snapshot.vessel = {-12.0, 0.0, 0.0, 1.0, 0.0, 0.0, 10.0, 0.0};
  snapshot.sensor_timestamp_s = 1.0;
  snapshot.receive_timestamp_s = 1.0;
  snapshot.aligned_timestamp_s = 1.0;
  snapshot.expected_apply_timestamp_s = 1.0;
  SafetyFilter filter;
  const auto result = filter.filter(snapshot, {0.5, deg2rad(3.7)}, 1.0);
  if (result.outcome != SearchOutcome::WitnessFound || result.paper_status != 0 ||
      std::abs(result.applied_command.steering_rad - deg2rad(3.7)) > 1e-12) return 3;
  std::cout << "{\"ok\":true,\"version\":\"0.1.0\","
            << "\"paper_grid_points\":" << grid.size() << ","
            << "\"exact_steering_deg\":" << std::setprecision(12)
            << rad2deg(result.applied_command.steering_rad) << "}\n";
  return 0;
}

int mock_runtime(int cycles) {
  Snapshot snapshot;
  snapshot.vessel = {-12.0, 0.0, 0.0, 1.0, 0.0, 0.0, 10.0, 0.0};
  SafetyFilter filter;
  for (int i = 0; cycles < 0 || i < cycles; ++i) {
    const auto cycle_start = std::chrono::steady_clock::now();
    const double now = 0.1 * i;
    snapshot.sensor_timestamp_s = now;
    snapshot.receive_timestamp_s = now;
    snapshot.aligned_timestamp_s = now;
    snapshot.expected_apply_timestamp_s = now + 0.1;
    const HumanCommand requested{0.5, deg2rad(3.7)};
    const auto result = filter.filter(snapshot, requested, now);
    snapshot.vessel = rk4_step(snapshot.vessel, result.applied_command, 0.1, {});
    std::cout << "{\"cycle\":" << i << ",\"outcome\":\""
              << to_string(result.outcome) << "\",\"paper_status\":"
              << result.paper_status << ",\"applied_throttle\":"
              << result.applied_command.throttle << ",\"applied_steering_rad\":"
              << result.applied_command.steering_rad << "}\n";
    std::this_thread::sleep_until(cycle_start + std::chrono::milliseconds(100));
  }
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  const std::string command = argc > 1 ? argv[1] : "doctor";
  if (command == "doctor") {
    std::cout << "{\"component\":\"cocommand_runner\",\"version\":\"0.1.0\","
                 "\"headless\":true,\"neural_dependencies\":false,"
                 "\"real_hardware_enabled\":false}\n";
    return 0;
  }
  if (command == "selftest") return selftest();
  if (command == "mock") {
    const int requested = argc > 2 ? std::atoi(argv[2]) : 3;
    const int cycles = requested == 0 ? -1 : std::max(1, requested);
    return mock_runtime(cycles);
  }
  std::cerr << "usage: cocommand_runner {doctor|selftest|mock [cycles]}\n";
  return 64;
}
