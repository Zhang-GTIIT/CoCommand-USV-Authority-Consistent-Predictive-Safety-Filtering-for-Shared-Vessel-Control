#include "cocommand/c_api.h"

#include "cocommand/core.hpp"
#include "cocommand/perception.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <vector>

using namespace cocommand;

struct CCHandle {
  VesselParams params{};
  ControlConfig config{};
  Tracker tracker{};
  std::unique_ptr<SafetyFilter> filter{};
  double last_sensor_timestamp_s{0.0};
  double last_receive_timestamp_s{0.0};
  std::size_t complete_witness_samples{0};
};

namespace {

template <typename Enum>
Enum enum_or(int raw, int maximum, Enum fallback) {
  if (raw < 0 || raw > maximum) return fallback;
  return static_cast<Enum>(raw);
}

ControlConfig convert_config(const CCConfig* input) {
  ControlConfig config;
  if (!input) return config;
  config.authority = enum_or(input->authority_mode, 3,
                             AuthorityMode::SteeringHoldContract);
  config.sampling = enum_or(input->sampling_mode, 4, SamplingMode::Uniform2);
  config.horizon_mode = enum_or(input->horizon_mode, 2, HorizonMode::PaperExact);
  config.margin_mode = enum_or(input->margin_mode, 2, MarginMode::PaperInflation);
  config.predictor = enum_or(input->predictor_mode, 3,
                             PredictorMode::PaperCvSmoothing);
  config.backup_library = enum_or(input->backup_library_mode, 5,
                                  BackupLibraryMode::Paper24);
  config.selection_policy = enum_or(input->selection_policy, 1,
                                    SelectionPolicy::MinimumModification);
  if (std::isfinite(input->fixed_horizon_s) && input->fixed_horizon_s > 0.0) {
    config.fixed_horizon_s = input->fixed_horizon_s;
  }
  if (std::isfinite(input->planning_budget_ms) && input->planning_budget_ms >= 0.0) {
    config.planning_budget_ms = input->planning_budget_ms;
  }
  if (std::isfinite(input->base_margin_m) && input->base_margin_m >= 0.0) {
    config.base_margin_m = input->base_margin_m;
  }
  if (std::isfinite(input->covariance_alpha) && input->covariance_alpha > 0.0 &&
      input->covariance_alpha < 1.0) {
    config.covariance_alpha = input->covariance_alpha;
  }
  config.deadline_aware = input->deadline_aware != 0;
  config.reverse_available = input->reverse_available != 0;
  config.sweep_margin_enabled = input->sweep_margin_enabled != 0;
  config.radius_inflation_enabled = input->radius_inflation_enabled != 0;
  config.max_integration_steps = static_cast<std::size_t>(input->max_integration_steps);
  return config;
}

VesselState convert_state(const double state[8]) {
  return {state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7]};
}

}  // namespace

extern "C" {

CCHandle* cc_create(const CCConfig* config) {
  try {
    auto handle = std::make_unique<CCHandle>();
    handle->config = convert_config(config);
    handle->params.reverse_available = handle->config.reverse_available;
    const double memory_s = config && std::isfinite(config->track_memory_s)
        ? std::max(0.0, config->track_memory_s) : 3.0;
    handle->tracker = Tracker(handle->config.predictor, memory_s);
    handle->filter = std::make_unique<SafetyFilter>(handle->params, handle->config);
    return handle.release();
  } catch (...) {
    return nullptr;
  }
}

void cc_destroy(CCHandle* handle) { delete handle; }

int cc_set_first_complete_witness(CCHandle* handle, int enabled) {
  if (!handle) return -1;
  if (handle->config.authority != AuthorityMode::SteeringHoldContract ||
      handle->config.selection_policy != SelectionPolicy::MinimumModification) return -2;
  handle->config.first_complete_witness = enabled != 0;
  handle->filter = std::make_unique<SafetyFilter>(handle->params, handle->config);
  handle->complete_witness_samples = 0;
  return 0;
}

size_t cc_last_complete_witness_samples(CCHandle* handle) {
  return handle ? handle->complete_witness_samples : 0;
}

int cc_reset(CCHandle* handle) {
  if (!handle) return -1;
  handle->tracker.clear();
  handle->filter->reset();
  handle->last_sensor_timestamp_s = 0.0;
  handle->last_receive_timestamp_s = 0.0;
  handle->complete_witness_samples = 0;
  return 0;
}

int cc_process_scan(CCHandle* handle, const double vessel_state[8],
                    const double* ranges_m, const uint8_t* hits,
                    size_t beam_count, double max_range_m,
                    double sensor_timestamp_s, double receive_timestamp_s) {
  if (!handle || !vessel_state || !ranges_m || !hits || beam_count == 0 ||
      !std::isfinite(max_range_m) || max_range_m <= 0.0) return -1;
  TimedScan scan;
  const VesselState state = convert_state(vessel_state);
  scan.sensor_position = {state.n, state.e};
  scan.sensor_heading_rad = state.psi;
  scan.sensor_timestamp_s = sensor_timestamp_s;
  scan.receive_timestamp_s = receive_timestamp_s;
  scan.max_range_m = max_range_m;
  scan.beams.reserve(beam_count);
  for (size_t i = 0; i < beam_count; ++i) {
    const double bearing = -kPi + 2.0 * kPi * static_cast<double>(i) /
                                      static_cast<double>(beam_count);
    const bool hit = hits[i] != 0;
    const double range = ranges_m[i];
    if (!std::isfinite(range) || range < 0.0 || range > max_range_m + 1e-9) return -2;
    scan.beams.push_back({bearing, range, hit, sensor_timestamp_s});
  }
  const auto detections = reconstruct_detections(scan);
  handle->tracker.update(detections, sensor_timestamp_s);
  handle->last_sensor_timestamp_s = sensor_timestamp_s;
  handle->last_receive_timestamp_s = receive_timestamp_s;
  return static_cast<int>(handle->tracker.tracks().size());
}

int cc_filter(CCHandle* handle, const double vessel_state[8],
              const double human_command[2], int perception_healthy,
              double sensor_timestamp_s, double receive_timestamp_s,
              double aligned_timestamp_s, double expected_apply_timestamp_s,
              double monotonic_now_s, CCFilterResult* output) {
  if (!handle || !vessel_state || !human_command || !output) return -1;
  Snapshot snapshot;
  snapshot.vessel = convert_state(vessel_state);
  snapshot.tracks = handle->tracker.tracks();
  snapshot.perception_healthy = perception_healthy != 0;
  snapshot.sensor_timestamp_s = sensor_timestamp_s;
  snapshot.receive_timestamp_s = receive_timestamp_s;
  snapshot.aligned_timestamp_s = aligned_timestamp_s;
  snapshot.expected_apply_timestamp_s = expected_apply_timestamp_s;
  const auto result = handle->filter->filter(
      snapshot, {human_command[0], human_command[1]}, monotonic_now_s);
  handle->complete_witness_samples = result.witness.complete ? result.witness.samples.size() : 0;
  output->applied_throttle = result.applied_command.throttle;
  output->applied_steering_rad = result.applied_command.steering_rad;
  output->outcome = static_cast<int>(result.outcome);
  output->paper_status = result.paper_status;
  output->predicted_minimum_clearance_m = result.predicted_minimum_clearance_m;
  output->requested_horizon_s = result.requested_horizon_s;
  output->actual_horizon_s = result.actual_horizon_s;
  output->latency_ms = result.latency_ms;
  output->evaluated_candidates = static_cast<uint64_t>(result.evaluated_candidate_count);
  output->evaluated_branches = static_cast<uint64_t>(result.evaluated_branch_count);
  output->integration_steps = static_cast<uint64_t>(result.integration_steps);
  output->search_complete = result.search_complete ? 1 : 0;
  output->minimality_established = result.minimality_established ? 1 : 0;
  output->recovery_active = result.recovery_active ? 1 : 0;
  output->used_hypothetical_throttle = result.used_hypothetical_throttle ? 1 : 0;
  output->witness_required_throttle = result.witness.required_throttle;
  return 0;
}

const char* cc_version(void) { return "0.1.0"; }

}  // extern "C"
