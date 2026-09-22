#include "cocommand/core.hpp"
#include "cocommand/perception.hpp"
#include "cocommand/runtime.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <set>
#include <string>
#include <vector>

using namespace cocommand;

namespace {
int failures = 0;

#define CHECK(condition) do { \
  if (!(condition)) { \
    std::cerr << __FILE__ << ':' << __LINE__ << " CHECK failed: " #condition "\n"; \
    ++failures; \
  } \
} while (false)

bool near(double a, double b, double tolerance = 1e-9) {
  return std::abs(a - b) <= tolerance;
}

void test_time_grids_and_rk4_switch_boundary() {
  const auto grid = paper_time_grid();
  CHECK(grid.size() == 52);
  CHECK(near(grid[0], 0.0));
  CHECK(near(grid[1], 0.1));
  CHECK(near(grid[2], 0.3));
  CHECK(near(grid.back(), 10.1));
  const auto short_grid = horizon_time_grid(2.05);
  CHECK(near(short_grid.back(), 2.05));
  CHECK(short_grid[1] == 0.1);

  VesselState initial{};
  const auto one_segment = rk4_step(initial, {1.0, 0.0}, 0.1, {});
  CHECK(one_segment.thrust_n > 0.0);
  CHECK(one_segment.thrust_n < 20.0);
  const auto candidate_entire_segment = rk4_step(initial, {1.0, 0.0}, 0.1, {});
  CHECK(near(one_segment.thrust_n, candidate_entire_segment.thrust_n, 1e-12));
}

void test_dynamics_energy_actuators_and_reverse() {
  VesselParams params;
  VesselState state{0.0, 0.0, 0.3, 1.2, -0.4, 0.2, 0.0, 0.0};
  CHECK(std::abs(coriolis_power(state, params)) < 1e-10);
  CHECK(damping_power(state, params) >= 0.0);
  const auto next = rk4_step(state, {0.5, deg2rad(30.0)}, 0.1, params);
  CHECK(next.delta_rad > 0.0);
  CHECK(next.delta_rad <= deg2rad(6.0) + 1e-10);
  CHECK(next.thrust_n > 0.0 && next.thrust_n < 10.0);

  params.reverse_available = false;
  VesselState reverse{};
  const auto derivative = vessel_derivative(reverse, {-1.0, 0.0}, params);
  CHECK(near(derivative.dx[6], 0.0));
}

void test_geometry_strict_boundary() {
  VesselState vessel{};
  CHECK(near(rectangle_circle_signed_distance(vessel, 2.0, 1.0,
                                              {2.0, 0.0}, 1.0), 0.0));
  CHECK(rectangle_circle_signed_distance(vessel, 2.0, 1.0,
                                         {0.0, 0.0}, 0.2) < 0.0);
  vessel.psi = deg2rad(90.0);
  CHECK(near(rectangle_circle_signed_distance(vessel, 2.0, 1.0,
                                              {0.0, 2.0}, 1.0), 0.0, 1e-9));

  ControlConfig config;
  config.horizon_mode = HorizonMode::Fixed;
  config.fixed_horizon_s = 0.3;
  config.deadline_aware = false;
  config.sampling = SamplingMode::Uniform4;
  Snapshot snapshot;
  snapshot.perception_healthy = true;
  snapshot.sensor_timestamp_s = 1.0;
  snapshot.aligned_timestamp_s = 1.0;
  ObstacleTrack touching;
  touching.center = {1.9, 0.0};  // hull front 0.6 + radius 0.6 + m0 0.7
  touching.radius_m = 0.6;
  touching.aligned_time_s = 1.0;
  snapshot.tracks.push_back(touching);
  SafetyFilter filter({}, config);
  const auto result = filter.filter(snapshot, {0.0, 0.0}, 1.0);
  CHECK(result.outcome == SearchOutcome::ExhaustedNoWitness);
  CHECK(result.paper_status == 2);
}

void test_radar_first_hit_boundary_and_wrap_cluster() {
  VesselState vessel{};
  WorldShape near_circle;
  near_circle.type = ShapeType::Circle;
  near_circle.center = {5.0, 0.0};
  near_circle.radius_m = 1.0;
  WorldShape far_circle = near_circle;
  far_circle.center = {10.0, 0.0};
  auto scan = simulate_radar(vessel, {far_circle, near_circle}, 2.0, 360, 65.0);
  const auto& forward = scan.beams[180];
  CHECK(forward.hit);
  CHECK(near(forward.range_m, 4.0, 1e-8));
  const auto& backward = scan.beams[0];
  CHECK(!backward.hit);
  CHECK(near(backward.range_m, 65.0));

  WorldShape boundary;
  boundary.type = ShapeType::Circle;
  boundary.center = {66.0, 0.0};
  boundary.radius_m = 1.0;
  scan = simulate_radar(vessel, {boundary}, 2.0, 360, 65.0);
  CHECK(scan.beams[180].hit);
  CHECK(near(scan.beams[180].range_m, 65.0, 1e-8));

  TimedScan seam;
  seam.sensor_timestamp_s = 3.0;
  seam.max_range_m = 65.0;
  seam.beams = {{-3.13, 5.0, true, 3.0}, {-1.0, 65.0, false, 3.0},
                {1.0, 65.0, false, 3.0}, {3.13, 5.0, true, 3.0}};
  const auto detections = reconstruct_detections(seam);
  CHECK(detections.size() == 1);
  CHECK(detections[0].used_fallback);
}

void test_tracker_duplicate_time_memory_and_covariance() {
  Tracker tracker(PredictorMode::CvKalman);
  CHECK(tracker.update({{{1.0, 2.0}, 0.6, 0.0, false}}, 0.0).size() == 1);
  CHECK(tracker.update({{{1.1, 2.0}, 0.6, 0.0, false}}, 0.0).size() == 1);
  CHECK(tracker.update({}, 2.9).size() == 1);
  CHECK(tracker.update({}, 3.1).empty());

  ObstacleTrack track;
  const double now = propagated_position_lambda_max(track, 0.0, 0.05);
  const double future = propagated_position_lambda_max(track, 3.0, 0.05);
  CHECK(future > now);
  CHECK(covariance_margin(track, 3.0, 0.05, 0.05) > 0.0);

  Tracker imm(PredictorMode::Imm);
  imm.update({{{0.0, 0.0}, 0.6, 0.0, false}}, 0.0);
  imm.update({{{1.0, 0.0}, 0.6, 1.0, false}}, 1.0);
  imm.update({{{2.0, 0.3}, 0.6, 2.0, false}}, 2.0);
  CHECK(predicted_centers(imm.tracks().front(), 2.0, PredictorMode::Imm).size() == 3);
}

void test_tcpa_ttc_cases() {
  const auto crossing = tcpa_dcpa({10.0, 2.0}, {-1.0, 0.0});
  CHECK(near(crossing.tcpa_s, 10.0));
  CHECK(near(crossing.dcpa_m, 2.0));
  CHECK(!circle_ttc({10.0, 2.0}, {-1.0, 0.0}, 1.0));
  const auto collision = circle_ttc({10.0, 0.0}, {-1.0, 0.0}, 1.0);
  CHECK(collision.has_value() && near(*collision, 9.0));
  CHECK(!circle_ttc({10.0, 0.0}, {1.0, 0.0}, 1.0));
  CHECK(circle_ttc({0.5, 0.0}, {0.0, 0.0}, 1.0).value() == 0.0);
}

void test_candidates_exact_nested_and_disconnected_domain_coverage() {
  const double exact = deg2rad(3.7);
  const auto candidates = steering_candidates(exact, SamplingMode::NestedAdaptive);
  CHECK(near(candidates.front(), exact, 1e-14));
  auto contains = [&candidates](double deg) {
    return std::any_of(candidates.begin(), candidates.end(), [deg](double x) {
      return near(rad2deg(x), deg, 1e-9);
    });
  };
  CHECK(contains(-30.0) && contains(30.0));
  CHECK(contains(-7.5) && contains(7.5));  // interior islands are not pruned by endpoints
  const auto coarse = steering_candidates(exact, SamplingMode::Uniform4);
  for (double value : coarse) {
    CHECK(std::any_of(candidates.begin(), candidates.end(), [value](double x) {
      return near(x, value, 1e-12);
    }));
  }
}

void test_exact_human_pass_and_timeout_unknown() {
  Snapshot snapshot;
  snapshot.perception_healthy = true;
  snapshot.sensor_timestamp_s = 4.0;
  snapshot.aligned_timestamp_s = 4.0;
  ControlConfig short_config;
  short_config.horizon_mode = HorizonMode::Fixed;
  short_config.fixed_horizon_s = 0.3;
  short_config.deadline_aware = false;
  SafetyFilter filter({}, short_config);
  const double exact = deg2rad(3.7);
  const auto pass = filter.filter(snapshot, {0.5, exact}, 4.0);
  CHECK(pass.outcome == SearchOutcome::WitnessFound);
  CHECK(pass.paper_status == 0);
  CHECK(near(pass.applied_command.steering_rad, exact, 1e-14));

  ControlConfig limited = short_config;
  limited.max_integration_steps = 1;
  SafetyFilter timeout_filter({}, limited);
  const auto timeout = timeout_filter.filter(snapshot, {0.5, exact}, 4.0);
  CHECK(timeout.outcome == SearchOutcome::BudgetExhaustedUnknown);
  CHECK(timeout.paper_status == -1);
  CHECK(!timeout.search_complete);
  CHECK(timeout.witness.samples.empty());
  CHECK(near(timeout.applied_command.throttle, 0.5));
  snapshot.perception_healthy = false;
  const auto stale = filter.filter(snapshot, {0.7, exact}, 4.0);
  CHECK(stale.outcome == SearchOutcome::StaleInput);
  CHECK(near(stale.applied_command.throttle, 0.7));
  snapshot.perception_healthy = true;
  limited.authority = AuthorityMode::PaperHypothetical;
  SafetyFilter hypothetical_limited({}, limited);
  CHECK(near(hypothetical_limited.filter(snapshot, {0.8, exact}, 4.0)
                 .applied_command.throttle, 0.8));
}

void test_recovery_deadline_not_postponed_and_old_witness_revalidation() {
  Witness witness;
  witness.complete = true;
  witness.latest_throttle_effect_s = 0.5;
  witness.samples = {{0.0, {}, {0.8, 0.1}, 1.0},
                     {0.5, {}, {-1.0, 0.1}, 1.0}};
  RecoveryCommitment recovery;
  recovery.commit(witness, 10.0);
  CHECK(recovery.active());
  CHECK(recovery.requires_revalidation());
  const double deadline = recovery.absolute_throttle_deadline_s();
  recovery.mark_revalidated();
  recovery.note_replan(10.1);
  CHECK(recovery.requires_revalidation());
  CHECK(near(recovery.absolute_throttle_deadline_s(), deadline));
  CHECK(recovery.command_at(10.6).throttle < 0.0);
}

void test_runtime_authority_and_unknown_hardware_fail_closed() {
  MockActuatorSink mock;
  CHECK(!mock.arm("wrong"));
  CHECK(mock.arm("MOCK_ONLY"));
  CHECK(mock.send({1, 10.0, {0.5, 0.0}}, 10.1));
  CHECK(!mock.send({1, 10.1, {0.5, 0.0}}, 10.2));  // replayed sequence
  CHECK(!mock.send({2, 9.0, {0.5, 0.0}}, 10.2));   // stale
  CHECK(!mock.send({2, 10.2, {2.0, 0.0}}, 10.2));  // out of range
  mock.disarm();
  CHECK(!mock.send({2, 10.2, {0.0, 0.0}}, 10.2));

  UnknownHardwareActuatorSink unknown;
  CHECK(!unknown.arm("anything"));
  CHECK(!unknown.send({1, 10.0, {0.0, 0.0}}, 10.0));
  CHECK(!unknown.refusal_reason().empty());
}

void test_complete_witness_short_circuit() {
  ControlConfig exhaustive;
  exhaustive.deadline_aware = false;
  ControlConfig early = exhaustive;
  early.first_complete_witness = true;
  Snapshot snapshot;
  snapshot.perception_healthy = true;
  snapshot.sensor_timestamp_s = 1.0;
  snapshot.aligned_timestamp_s = 1.0;
  for (double x : {0.0, 2.0, 4.0, 8.0, 15.0, 40.0}) {
    for (double y : {-2.0, 0.0, 2.0}) {
      ObstacleTrack obstacle;
      obstacle.center = {x, y};
      obstacle.radius_m = 0.7;
      snapshot.tracks = {obstacle};
      snapshot.vessel.u = 1.0;
      snapshot.vessel.thrust_n = 10.0;
      SafetyFilter baseline({}, exhaustive), optimized({}, early);
      const auto a = baseline.filter(snapshot, {0.5, deg2rad(3.7)}, 1.0);
      const auto b = optimized.filter(snapshot, {0.5, deg2rad(3.7)}, 1.0);
      CHECK(a.outcome == b.outcome);
      CHECK(near(a.applied_command.throttle, b.applied_command.throttle));
      CHECK(near(a.applied_command.steering_rad, b.applied_command.steering_rad));
      CHECK(b.integration_steps <= a.integration_steps);
      if (b.outcome == SearchOutcome::WitnessFound) {
        CHECK(b.witness.complete);
        CHECK(b.witness.samples.size() == 52);
        CHECK(near(b.witness.samples.back().relative_time_s, 10.1));
        CHECK(b.witness.minimum_clearance_m > 0.0);
      }
    }
  }
  early.max_integration_steps = 1;
  SafetyFilter interrupted({}, early);
  const auto partial = interrupted.filter(snapshot, {0.5, 0.0}, 1.0);
  CHECK(partial.outcome == SearchOutcome::BudgetExhaustedUnknown);
  CHECK(!partial.witness.complete);
}

}  // namespace

int main() {
  test_time_grids_and_rk4_switch_boundary();
  test_dynamics_energy_actuators_and_reverse();
  test_geometry_strict_boundary();
  test_radar_first_hit_boundary_and_wrap_cluster();
  test_tracker_duplicate_time_memory_and_covariance();
  test_tcpa_ttc_cases();
  test_candidates_exact_nested_and_disconnected_domain_coverage();
  test_exact_human_pass_and_timeout_unknown();
  test_recovery_deadline_not_postponed_and_old_witness_revalidation();
  test_runtime_authority_and_unknown_hardware_fail_closed();
  test_complete_witness_short_circuit();
  if (failures != 0) {
    std::cerr << failures << " test checks failed\n";
    return 1;
  }
  std::cout << "all native unit/property/regression checks passed\n";
  return 0;
}
