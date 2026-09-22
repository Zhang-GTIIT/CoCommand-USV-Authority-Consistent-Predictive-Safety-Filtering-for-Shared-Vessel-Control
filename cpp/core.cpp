#include "cocommand/core.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <set>
#include <sstream>
#include <tuple>

namespace cocommand {
namespace {

double clamp_value(double value, double lo, double hi) {
  return std::max(lo, std::min(hi, value));
}

bool finite(double value) { return std::isfinite(value); }

bool finite_state(const VesselState& x) {
  return finite(x.n) && finite(x.e) && finite(x.psi) && finite(x.u) &&
         finite(x.v) && finite(x.r) && finite(x.thrust_n) &&
         finite(x.delta_rad);
}

VesselState add_scaled(const VesselState& x, const DynamicsDerivative& k,
                       double scale) {
  VesselState y = x;
  y.n += scale * k.dx[0];
  y.e += scale * k.dx[1];
  y.psi += scale * k.dx[2];
  y.u += scale * k.dx[3];
  y.v += scale * k.dx[4];
  y.r += scale * k.dx[5];
  y.thrust_n += scale * k.dx[6];
  y.delta_rad += scale * k.dx[7];
  return y;
}

using Matrix4 = std::array<double, 16>;

double& m(Matrix4& a, int row, int col) { return a[static_cast<std::size_t>(row * 4 + col)]; }
double m(const Matrix4& a, int row, int col) { return a[static_cast<std::size_t>(row * 4 + col)]; }

Matrix4 transpose(const Matrix4& a) {
  Matrix4 out{};
  for (int i = 0; i < 4; ++i) {
    for (int j = 0; j < 4; ++j) m(out, i, j) = m(a, j, i);
  }
  return out;
}

Matrix4 multiply(const Matrix4& a, const Matrix4& b) {
  Matrix4 out{};
  for (int i = 0; i < 4; ++i) {
    for (int j = 0; j < 4; ++j) {
      for (int k = 0; k < 4; ++k) m(out, i, j) += m(a, i, k) * m(b, k, j);
    }
  }
  return out;
}

Matrix4 identity4() {
  Matrix4 out{};
  for (int i = 0; i < 4; ++i) m(out, i, i) = 1.0;
  return out;
}

Matrix4 predict_covariance(const Matrix4& p, double dt, double q) {
  Matrix4 f = identity4();
  m(f, 0, 2) = dt;
  m(f, 1, 3) = dt;
  Matrix4 out = multiply(multiply(f, p), transpose(f));
  const double dt2 = dt * dt;
  const double dt3 = dt2 * dt;
  const double dt4 = dt2 * dt2;
  const std::array<double, 4> q1{{0.25 * dt4 * q, 0.5 * dt3 * q,
                                  dt2 * q, dt2 * q}};
  m(out, 0, 0) += q1[0];
  m(out, 1, 1) += q1[0];
  m(out, 0, 2) += q1[1];
  m(out, 2, 0) += q1[1];
  m(out, 1, 3) += q1[1];
  m(out, 3, 1) += q1[1];
  m(out, 2, 2) += q1[2];
  m(out, 3, 3) += q1[3];
  return out;
}

void joseph_position_update(ObstacleTrack& track, Vec2 measurement,
                            double measurement_variance) {
  Matrix4 p = track.covariance;
  const double s00 = m(p, 0, 0) + measurement_variance;
  const double s01 = m(p, 0, 1);
  const double s10 = m(p, 1, 0);
  const double s11 = m(p, 1, 1) + measurement_variance;
  const double det = s00 * s11 - s01 * s10;
  if (!(det > 1e-14) || !finite(det)) {
    track.low_confidence = true;
    return;
  }
  const double inv00 = s11 / det;
  const double inv01 = -s01 / det;
  const double inv10 = -s10 / det;
  const double inv11 = s00 / det;
  double k[4][2]{};
  for (int i = 0; i < 4; ++i) {
    k[i][0] = m(p, i, 0) * inv00 + m(p, i, 1) * inv10;
    k[i][1] = m(p, i, 0) * inv01 + m(p, i, 1) * inv11;
  }
  const double innovation[2]{measurement.x - track.center.x,
                             measurement.y - track.center.y};
  std::array<double, 4> state{{track.center.x, track.center.y,
                               track.velocity.x, track.velocity.y}};
  for (int i = 0; i < 4; ++i) {
    state[static_cast<std::size_t>(i)] +=
        k[i][0] * innovation[0] + k[i][1] * innovation[1];
  }
  track.center = {state[0], state[1]};
  track.velocity = {state[2], state[3]};

  Matrix4 a = identity4();
  for (int i = 0; i < 4; ++i) {
    m(a, i, 0) -= k[i][0];
    m(a, i, 1) -= k[i][1];
  }
  Matrix4 updated = multiply(multiply(a, p), transpose(a));
  for (int i = 0; i < 4; ++i) {
    for (int j = 0; j < 4; ++j) {
      m(updated, i, j) += measurement_variance *
          (k[i][0] * k[j][0] + k[i][1] * k[j][1]);
    }
  }
  for (int i = 0; i < 4; ++i) {
    for (int j = i + 1; j < 4; ++j) {
      const double symmetric = 0.5 * (m(updated, i, j) + m(updated, j, i));
      m(updated, i, j) = symmetric;
      m(updated, j, i) = symmetric;
    }
    m(updated, i, i) = std::max(m(updated, i, i), 1e-12);
  }
  track.covariance = updated;
}

Vec2 world_velocity(const VesselState& state) {
  const double c = std::cos(state.psi);
  const double s = std::sin(state.psi);
  return {c * state.u - s * state.v, s * state.u + c * state.v};
}

double track_radius(const ObstacleTrack& track, double s,
                    const std::array<double, 16>& own_covariance,
                    const ControlConfig& config) {
  double radius = track.radius_m;
  if (!config.radius_inflation_enabled) return radius;
  const bool moving = norm(track.velocity) > 0.1 || track.sigma_velocity_mps > 0.3;
  if (config.margin_mode == MarginMode::PaperInflation) {
    radius += track.sigma_velocity_mps * (s + track.age_since_observation_s);
    if (moving) radius += 0.5 * config.acceleration_allowance_mps2 * s * s;
  } else if (config.margin_mode == MarginMode::Covariance) {
    const Matrix4 obstacle = predict_covariance(track.covariance, std::max(0.0, s),
                                                config.covariance_process_noise);
    const bool own_available = std::any_of(own_covariance.begin(), own_covariance.end(),
                                           [](double value) { return std::abs(value) > 0.0; });
    const Matrix4 own = own_available
        ? predict_covariance(own_covariance, std::max(0.0, s),
                             config.covariance_process_noise)
        : Matrix4{};
    const double a = m(obstacle, 0, 0) + m(own, 0, 0);
    const double b = 0.5 * (m(obstacle, 0, 1) + m(obstacle, 1, 0) +
                            m(own, 0, 1) + m(own, 1, 0));
    const double d = m(obstacle, 1, 1) + m(own, 1, 1);
    const double lambda = std::max(0.0, 0.5 * (a + d +
        std::sqrt(std::max(0.0, (a - d) * (a - d) + 4.0 * b * b))));
    const double quantile = -2.0 * std::log(
        clamp_value(config.covariance_alpha, 1e-12, 1.0 - 1e-12));
    radius += std::sqrt(quantile * lambda);
    if (moving) radius += 0.5 * config.acceleration_allowance_mps2 * s * s;
  }
  return radius;
}

double clearance_at(const VesselState& vessel,
                    const std::vector<ObstacleTrack>& tracks,
                    const std::array<double, 16>& own_covariance,
                    double prediction_time_s, double propagation_step_s,
                    bool initial, const ControlConfig& config,
                    const VesselParams& params) {
  if (tracks.empty()) return std::numeric_limits<double>::infinity();
  double best = std::numeric_limits<double>::infinity();
  for (const auto& track : tracks) {
    const auto centers = predicted_centers(track, prediction_time_s, config.predictor);
    for (const Vec2 center : centers) {
      const double radius = track_radius(track, prediction_time_s, own_covariance, config);
      double gap = rectangle_circle_signed_distance(
          vessel, params.length_m, params.beam_m, center, radius);
      gap -= config.base_margin_m + config.fixed_extra_margin_m;
      if (!initial && config.sweep_margin_enabled) {
        const double corner = 0.5 * std::hypot(params.length_m, params.beam_m);
        const double obstacle_speed = norm(track.velocity) +
            track.sigma_velocity_mps +
            config.acceleration_allowance_mps2 * prediction_time_s;
        const double sweep = 0.5 * propagation_step_s *
            (std::hypot(vessel.u, vessel.v) + std::abs(vessel.r) * corner +
             obstacle_speed);
        gap -= sweep;
      }
      best = std::min(best, gap);
    }
  }
  return best;
}

enum class PolicyThrottle { Hold, FullAhead, Brake };

struct BackupPolicy {
  std::string name;
  double steering_rad{0.0};
  PolicyThrottle throttle{PolicyThrottle::Hold};
  double straighten_after_s{-1.0};
  double progressive_duration_s{0.0};
};

HumanCommand policy_command(const BackupPolicy& policy, double s,
                            const HumanCommand& human,
                            const VesselState& predicted,
                            const ControlConfig& config) {
  HumanCommand out{human.throttle, policy.steering_rad};
  if (policy.throttle == PolicyThrottle::FullAhead) out.throttle = 1.0;
  if (policy.throttle == PolicyThrottle::Brake) {
    if (predicted.u > 0.15) out.throttle = config.reverse_available ? -1.0 : 0.0;
    else if (predicted.u < -0.15) out.throttle = 1.0;
    else out.throttle = 0.0;
  }
  if (policy.straighten_after_s >= 0.0 && s > policy.straighten_after_s) {
    if (policy.progressive_duration_s <= 0.0) {
      out.steering_rad = 0.0;
    } else {
      const double fraction = clamp_value(
          1.0 - (s - policy.straighten_after_s) / policy.progressive_duration_s,
          0.0, 1.0);
      out.steering_rad = policy.steering_rad * fraction;
    }
  }
  return out;
}

std::vector<BackupPolicy> policies_for(double candidate_rad,
                                       const HumanCommand& human,
                                       const ControlConfig& config,
                                       bool emergency_phase) {
  (void)human;
  if (config.backup_library == BackupLibraryMode::FrozenCandidate) {
    return {{"frozen_candidate", candidate_rad, PolicyThrottle::Hold, -1.0, 0.0}};
  }
  const std::array<double, 6> angles{{deg2rad(-30.0), deg2rad(-15.0), 0.0,
                                      deg2rad(15.0), deg2rad(30.0), candidate_rad}};
  std::vector<BackupPolicy> policies;
  auto add = [&policies](std::string name, double angle, PolicyThrottle throttle,
                         double straight = -1.0, double progressive = 0.0) {
    policies.push_back({std::move(name), angle, throttle, straight, progressive});
  };
  for (double angle : angles) {
    if (config.authority == AuthorityMode::PaperHypothetical ||
        config.authority == AuthorityMode::FullCommandWeighted || emergency_phase) {
      add("hold", angle, PolicyThrottle::Hold);
      add("full_ahead", angle, PolicyThrottle::FullAhead);
      add("brake", angle, PolicyThrottle::Brake);
      add("turn_then_straighten_2s", angle, PolicyThrottle::Hold, 2.0);
    } else {
      add("hold", angle, PolicyThrottle::Hold);
      add("turn_then_straighten_2s", angle, PolicyThrottle::Hold, 2.0);
    }
    if (config.backup_library == BackupLibraryMode::Extended) {
      for (double switch_time : {0.5, 1.0, 3.0}) {
        std::ostringstream label;
        label << "turn_then_straighten_" << switch_time << "s";
        add(label.str(), angle, PolicyThrottle::Hold, switch_time);
      }
      add("progressive_return_0.5s", angle, PolicyThrottle::Hold, 1.0, 0.5);
      add("progressive_return_1.0s", angle, PolicyThrottle::Hold, 1.0, 1.0);
      if (emergency_phase || config.authority == AuthorityMode::FullCommandWeighted) {
        add("authorized_brake_progressive", angle, PolicyThrottle::Brake, 1.0, 1.0);
      }
    }
    if (config.backup_library == BackupLibraryMode::PredictiveSegmentsAdapted) {
      add("optimized_switch_0.5s", angle, PolicyThrottle::Hold, 0.5, 0.5);
      add("optimized_switch_1.0s", angle, PolicyThrottle::Hold, 1.0, 0.5);
      if (emergency_phase || config.authority == AuthorityMode::FullCommandWeighted) {
        add("optimized_brake_0.5s", angle, PolicyThrottle::Brake, 0.5, 0.5);
      }
    }
    if (config.backup_library == BackupLibraryMode::GoalAgnosticSamplingAdapted) {
      add("sampled_hold", angle, PolicyThrottle::Hold);
      add("sampled_switch_0.5s", angle, PolicyThrottle::Hold, 0.5);
      add("sampled_switch_1.5s", angle, PolicyThrottle::Hold, 1.5);
      add("sampled_switch_3.0s", angle, PolicyThrottle::Hold, 3.0);
    }
  }
  if (config.deduplicate_branches ||
      config.backup_library == BackupLibraryMode::Deduplicated) {
    std::vector<BackupPolicy> unique;
    std::set<std::tuple<long long, int, long long, long long>> keys;
    for (const auto& p : policies) {
      const auto key = std::make_tuple(
          std::llround(p.steering_rad * 1e12), static_cast<int>(p.throttle),
          std::llround(p.straighten_after_s * 1e9),
          std::llround(p.progressive_duration_s * 1e9));
      if (keys.insert(key).second) unique.push_back(p);
    }
    return unique;
  }
  return policies;
}

struct BranchEvaluation {
  bool witness{false};
  bool complete{false};
  bool numerical_failure{false};
  double minimum_gap{std::numeric_limits<double>::infinity()};
  double survival_time_s{0.0};
  double score{-std::numeric_limits<double>::infinity()};
  Witness witness_data{};
};

struct CandidateEvaluation {
  bool accepted{false};
  bool complete{true};
  bool numerical_failure{false};
  double best_gap{-std::numeric_limits<double>::infinity()};
  double fallback_score{-std::numeric_limits<double>::infinity()};
  Witness best_witness{};
  std::size_t nominal_branches{0};
  std::size_t unique_branches{0};
  std::size_t evaluated_branches{0};
};

struct SearchClock {
  std::chrono::steady_clock::time_point start{std::chrono::steady_clock::now()};
  double budget_ms{80.0};
  bool deadline_aware{true};
  std::size_t steps{0};
  std::size_t max_steps{std::numeric_limits<std::size_t>::max()};

  bool expired() const {
    if (steps >= max_steps) return true;
    if (!deadline_aware) return false;
    const double elapsed = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - start).count();
    return elapsed >= budget_ms;
  }
};

CandidateEvaluation evaluate_candidate(
    const Snapshot& snapshot, const HumanCommand& human,
    const HumanCommand& candidate_command,
    double horizon_s, const ControlConfig& config, const VesselParams& params,
    SearchClock& clock, bool emergency_phase) {
  CandidateEvaluation result;
  const HumanCommand first = candidate_command;
  const double initial_gap = clearance_at(snapshot.vessel, snapshot.tracks,
                                          snapshot.own_state_covariance, 0.0,
                                          0.0, true, config, params);
  if (!finite(initial_gap) && initial_gap != std::numeric_limits<double>::infinity()) {
    result.numerical_failure = true;
    return result;
  }
  VesselState first_state = rk4_step(snapshot.vessel, first, 0.1, params);
  ++clock.steps;
  if (!finite_state(first_state)) {
    result.numerical_failure = true;
    return result;
  }
  const double first_gap = clearance_at(first_state, snapshot.tracks,
                                        snapshot.own_state_covariance, 0.1, 0.1,
                                        false, config, params);
  auto policies = policies_for(candidate_command.steering_rad, candidate_command,
                               config, emergency_phase);
  result.nominal_branches = (config.backup_library == BackupLibraryMode::Paper24 &&
      (config.authority == AuthorityMode::PaperHypothetical || emergency_phase ||
       config.authority == AuthorityMode::FullCommandWeighted)) ? 24u : policies.size();
  result.unique_branches = policies.size();
  const auto grid = (config.horizon_mode == HorizonMode::PaperExact &&
                     std::abs(horizon_s - 10.1) < 1e-9)
                        ? paper_time_grid() : horizon_time_grid(horizon_s);

  for (const auto& policy : policies) {
    if (clock.expired()) {
      result.complete = false;
      break;
    }
    ++result.evaluated_branches;
    BranchEvaluation branch;
    branch.minimum_gap = std::min(initial_gap, first_gap);
    branch.survival_time_s = initial_gap > 0.0 ? 0.0 : 0.0;
    branch.witness_data.policy_name = policy.name;
    branch.witness_data.required_throttle = human.throttle;
    branch.witness_data.generated_at_s = snapshot.aligned_timestamp_s;
    branch.witness_data.samples.push_back({0.0, snapshot.vessel, first, initial_gap});
    branch.witness_data.samples.push_back({0.1, first_state, first, first_gap});

    if (!(initial_gap > 0.0) || !(first_gap > 0.0)) {
      branch.complete = true;
      branch.score = 0.001 * clamp_value(branch.minimum_gap, -100.0, 100.0);
    } else {
      branch.survival_time_s = 0.1;
      VesselState predicted = first_state;
      double previous_time = 0.1;
      bool failed = false;
      for (std::size_t index = 2; index < grid.size(); ++index) {
        if (clock.expired()) {
          branch.complete = false;
          break;
        }
        const double time = grid[index];
        const double dt = time - previous_time;
        const HumanCommand command = policy_command(policy, previous_time,
                                                     candidate_command,
                                                     predicted, config);
        if (command.throttle < 0.0 && !config.reverse_available) {
          branch.complete = true;
          failed = true;
          branch.minimum_gap = -std::numeric_limits<double>::infinity();
          break;
        }
        predicted = rk4_step(predicted, command, dt, params);
        ++clock.steps;
        if (!finite_state(predicted)) {
          branch.numerical_failure = true;
          branch.complete = true;
          failed = true;
          break;
        }
        const double gap = clearance_at(predicted, snapshot.tracks,
                                        snapshot.own_state_covariance, time, dt,
                                        false, config, params);
        if (!finite(gap) && gap != std::numeric_limits<double>::infinity()) {
          branch.numerical_failure = true;
          branch.complete = true;
          failed = true;
          break;
        }
        branch.minimum_gap = std::min(branch.minimum_gap, gap);
        branch.witness_data.samples.push_back({time, predicted, command, gap});
        if (command.throttle != human.throttle) {
          branch.witness_data.required_throttle = command.throttle;
          if (branch.witness_data.latest_throttle_effect_s <= 0.0) {
            branch.witness_data.latest_throttle_effect_s = time;
          }
        }
        if (!(gap > 0.0)) {
          branch.complete = true;
          failed = true;
          break;
        }
        branch.survival_time_s = time;
        previous_time = time;
      }
      if (!failed && branch.witness_data.samples.size() == grid.size()) {
        branch.complete = true;
        branch.witness = true;
        branch.witness_data.complete = true;
        branch.witness_data.minimum_clearance_m = branch.minimum_gap;
      }
      branch.score = branch.survival_time_s +
          0.001 * clamp_value(branch.minimum_gap, -100.0, 100.0);
    }

    if (branch.numerical_failure) result.numerical_failure = true;
    if (!branch.complete) {
      result.complete = false;
      break;
    }
    result.fallback_score = std::max(result.fallback_score, branch.score);
    if (branch.witness && (!result.accepted || branch.minimum_gap > result.best_gap)) {
      result.accepted = true;
      result.best_gap = branch.minimum_gap;
      result.best_witness = std::move(branch.witness_data);
      // Acceptance is existential: a complete positive-clearance backup suffices.
      // Preserve exhaustive checking for rejection/fallback and largest-clearance modes.
      // Do not use this in emergency authority, where the chosen backup is committed.
      if (config.first_complete_witness &&
          config.authority == AuthorityMode::SteeringHoldContract &&
          config.selection_policy == SelectionPolicy::MinimumModification) {
        return result;
      }
    }
  }
  return result;
}

}  // namespace

Vec2 operator+(Vec2 a, Vec2 b) { return {a.x + b.x, a.y + b.y}; }
Vec2 operator-(Vec2 a, Vec2 b) { return {a.x - b.x, a.y - b.y}; }
Vec2 operator*(Vec2 a, double s) { return {a.x * s, a.y * s}; }
double dot(Vec2 a, Vec2 b) { return a.x * b.x + a.y * b.y; }
double norm(Vec2 a) { return std::hypot(a.x, a.y); }

DynamicsDerivative vessel_derivative(const VesselState& state,
                                     const HumanCommand& command,
                                     const VesselParams& params) {
  DynamicsDerivative out;
  const double c = std::cos(state.psi);
  const double s = std::sin(state.psi);
  out.dx[0] = c * state.u - s * state.v;
  out.dx[1] = s * state.u + c * state.v;
  out.dx[2] = state.r;

  const double cnu1 = -params.m22_kg * state.v * state.r;
  const double cnu2 = params.m11_kg * state.u * state.r;
  const double cnu3 = (params.m22_kg - params.m11_kg) * state.u * state.v;
  double cross_y = 0.0;
  double cross_n = 0.0;
  const int strips = std::max(3, params.crossflow_strips);
  const double dx = params.length_m / static_cast<double>(strips);
  for (int i = 0; i < strips; ++i) {
    const double x = -0.5 * params.length_m + (static_cast<double>(i) + 0.5) * dx;
    const double local = state.v + x * state.r;
    const double force = 0.5 * params.water_density * params.crossflow_cd *
                         params.draft_m * local * std::abs(local) * dx;
    cross_y += force;
    cross_n += x * force;
  }
  const double d1 = params.surge_linear * state.u +
                    params.surge_quadratic * std::abs(state.u) * state.u;
  const double d2 = params.sway_linear * state.v + cross_y;
  const double d3 = params.yaw_linear * state.r + cross_n;
  const double tau1 = state.thrust_n * std::cos(state.delta_rad);
  const double tau2 = -state.thrust_n * std::sin(state.delta_rad);
  const double tau3 = 0.5 * state.thrust_n * std::sin(state.delta_rad);
  out.dx[3] = (tau1 - cnu1 - d1) / params.m11_kg;
  out.dx[4] = (tau2 - cnu2 - d2) / params.m22_kg;
  out.dx[5] = (tau3 - cnu3 - d3) / params.m33_kg_m2;

  double h = clamp_value(command.throttle, -1.0, 1.0);
  if (!params.reverse_available && h < 0.0) h = 0.0;
  const double thrust_command = h >= 0.0 ? params.thrust_forward_n * h
                                         : params.thrust_reverse_n * h;
  out.dx[6] = (thrust_command - state.thrust_n) / params.tau_thrust_s;
  const double delta_command = clamp_value(command.steering_rad,
                                           -params.delta_max_rad,
                                           params.delta_max_rad);
  out.dx[7] = clamp_value((delta_command - state.delta_rad) / params.tau_delta_s,
                          -params.delta_rate_max_rad_s,
                          params.delta_rate_max_rad_s);
  if (state.delta_rad >= params.delta_max_rad && out.dx[7] > 0.0) out.dx[7] = 0.0;
  if (state.delta_rad <= -params.delta_max_rad && out.dx[7] < 0.0) out.dx[7] = 0.0;
  return out;
}

VesselState rk4_step(const VesselState& state, const HumanCommand& command,
                     double dt_s, const VesselParams& params) {
  const auto k1 = vessel_derivative(state, command, params);
  const auto k2 = vessel_derivative(add_scaled(state, k1, 0.5 * dt_s), command, params);
  const auto k3 = vessel_derivative(add_scaled(state, k2, 0.5 * dt_s), command, params);
  const auto k4 = vessel_derivative(add_scaled(state, k3, dt_s), command, params);
  VesselState out = state;
  double* values[8]{&out.n, &out.e, &out.psi, &out.u, &out.v, &out.r,
                    &out.thrust_n, &out.delta_rad};
  for (int i = 0; i < 8; ++i) {
    *values[i] += dt_s * (k1.dx[static_cast<std::size_t>(i)] +
                           2.0 * k2.dx[static_cast<std::size_t>(i)] +
                           2.0 * k3.dx[static_cast<std::size_t>(i)] +
                           k4.dx[static_cast<std::size_t>(i)]) / 6.0;
  }
  out.delta_rad = clamp_value(out.delta_rad, -params.delta_max_rad,
                              params.delta_max_rad);
  return out;
}

double coriolis_power(const VesselState& state, const VesselParams& params) {
  const double c1 = -params.m22_kg * state.v * state.r;
  const double c2 = params.m11_kg * state.u * state.r;
  const double c3 = (params.m22_kg - params.m11_kg) * state.u * state.v;
  return state.u * c1 + state.v * c2 + state.r * c3;
}

double damping_power(const VesselState& state, const VesselParams& params) {
  const auto derivative = vessel_derivative(state, {0.0, state.delta_rad}, params);
  (void)derivative;
  double cross_y = 0.0;
  double cross_n = 0.0;
  const int strips = std::max(3, params.crossflow_strips);
  const double dx = params.length_m / static_cast<double>(strips);
  for (int i = 0; i < strips; ++i) {
    const double x = -0.5 * params.length_m + (static_cast<double>(i) + 0.5) * dx;
    const double local = state.v + x * state.r;
    const double force = 0.5 * params.water_density * params.crossflow_cd *
                         params.draft_m * local * std::abs(local) * dx;
    cross_y += force;
    cross_n += x * force;
  }
  const double d1 = params.surge_linear * state.u +
                    params.surge_quadratic * std::abs(state.u) * state.u;
  const double d2 = params.sway_linear * state.v + cross_y;
  const double d3 = params.yaw_linear * state.r + cross_n;
  return state.u * d1 + state.v * d2 + state.r * d3;
}

std::vector<double> paper_time_grid() {
  std::vector<double> grid;
  grid.reserve(52);
  grid.push_back(0.0);
  grid.push_back(0.1);
  for (int ell = 1; ell <= 50; ++ell) grid.push_back(0.1 + 0.2 * ell);
  return grid;
}

std::vector<double> horizon_time_grid(double horizon_s) {
  if (!(horizon_s > 0.0) || !finite(horizon_s)) return {};
  std::vector<double> grid{0.0};
  const double first = std::min(0.1, horizon_s);
  grid.push_back(first);
  double time = first;
  while (time + 0.2 < horizon_s - 1e-12) {
    time += 0.2;
    grid.push_back(time);
  }
  if (grid.back() < horizon_s - 1e-12) grid.push_back(horizon_s);
  return grid;
}

Tracker::Tracker(PredictorMode mode, double memory_s)
    : mode_(mode), memory_s_(std::max(0.0, memory_s)) {}

const std::vector<ObstacleTrack>& Tracker::update(
    const std::vector<Detection>& detections, double timestamp_s) {
  if (!finite(timestamp_s)) return tracks_;
  std::vector<bool> used(detections.size(), false);
  std::vector<ObstacleTrack> updated;
  updated.reserve(tracks_.size() + detections.size());
  for (auto track : tracks_) {
    const double dt = std::max(0.0, timestamp_s - track.aligned_time_s);
    const Vec2 old_center = track.center;
    const Vec2 predicted = track.center + track.velocity * dt;
    std::size_t best = detections.size();
    double best_distance = 2.0;
    for (std::size_t i = 0; i < detections.size(); ++i) {
      if (used[i]) continue;
      const double distance = norm(detections[i].center - predicted) +
                              std::abs(detections[i].radius_m - track.radius_m);
      if (distance < best_distance) {
        best_distance = distance;
        best = i;
      }
    }
    track.center = predicted;
    track.covariance = predict_covariance(track.covariance, dt, 0.05);
    if (best < detections.size()) {
      const Detection& detection = detections[best];
      used[best] = true;
      const Vec2 measured_velocity = dt > 1e-6
          ? (detection.center - old_center) * (1.0 / dt)
          : track.velocity;
      const Vec2 old_velocity = track.velocity;
      if (mode_ == PredictorMode::PaperCvSmoothing) {
        track.center = detection.center;
        if (dt > 1e-6) {
          track.velocity = old_velocity * 0.5 + measured_velocity * 0.5;
        }
      } else {
        joseph_position_update(track, detection.center, 0.0225);
        if (dt > 1e-6 &&
            (mode_ == PredictorMode::CaKalman || mode_ == PredictorMode::Imm)) {
          const Vec2 measured_acceleration = (track.velocity - old_velocity) * (1.0 / dt);
          track.acceleration = track.acceleration * 0.7 + measured_acceleration * 0.3;
        }
        if (dt > 1e-6 && mode_ == PredictorMode::Imm) {
          const double speed = std::max(norm(old_velocity), 1e-6);
          const double cross = old_velocity.x * track.velocity.y -
                               old_velocity.y * track.velocity.x;
          track.turn_rate_rad_s = std::atan2(cross, dot(old_velocity, track.velocity)) / dt;
          const double accel_score = std::min(1.0, norm(track.acceleration) / 0.2);
          const double turn_score = std::min(1.0, std::abs(track.turn_rate_rad_s) / deg2rad(10.0));
          const double cv = std::max(0.05, 1.0 - 0.6 * accel_score - 0.6 * turn_score);
          const double ca = 0.1 + 0.8 * accel_score;
          const double ct = 0.1 + 0.8 * turn_score;
          const double sum = cv + ca + ct;
          track.mode_probability = {cv / sum, ca / sum, ct / sum};
          (void)speed;
        }
      }
      track.radius_m = detection.radius_m;
      track.observed_time_s = timestamp_s;
      track.aligned_time_s = timestamp_s;
      track.age_since_observation_s = 0.0;
      const double innovation_speed = norm(measured_velocity - old_velocity);
      track.sigma_velocity_mps = std::max(0.12,
          0.5 * track.sigma_velocity_mps + 0.5 * innovation_speed);
      track.low_confidence = false;
      updated.push_back(track);
    } else {
      track.aligned_time_s = timestamp_s;
      track.age_since_observation_s += dt;
      track.sigma_velocity_mps = std::max(0.12,
          track.sigma_velocity_mps + 0.025 * dt);
      track.low_confidence = track.age_since_observation_s > 2.0;
      if (track.age_since_observation_s <= memory_s_) updated.push_back(track);
    }
  }
  for (std::size_t i = 0; i < detections.size(); ++i) {
    if (used[i]) continue;
    ObstacleTrack track;
    track.id = next_id_++;
    track.center = detections[i].center;
    track.radius_m = detections[i].radius_m;
    track.observed_time_s = timestamp_s;
    track.aligned_time_s = timestamp_s;
    updated.push_back(track);
  }
  tracks_ = std::move(updated);
  return tracks_;
}

void Tracker::clear() {
  tracks_.clear();
  next_id_ = 1;
}

std::vector<Vec2> predicted_centers(const ObstacleTrack& track, double s,
                                    PredictorMode mode) {
  const Vec2 cv = track.center + track.velocity * s;
  if (mode == PredictorMode::PaperCvSmoothing || mode == PredictorMode::CvKalman) {
    return {cv};
  }
  const Vec2 ca = cv + track.acceleration * (0.5 * s * s);
  if (mode == PredictorMode::CaKalman) return {ca};
  Vec2 ct = cv;
  const double omega = track.turn_rate_rad_s;
  if (std::abs(omega) > 1e-7) {
    const double sw = std::sin(omega * s);
    const double cw = std::cos(omega * s);
    ct.x = track.center.x + (sw * track.velocity.x - (1.0 - cw) * track.velocity.y) / omega;
    ct.y = track.center.y + ((1.0 - cw) * track.velocity.x + sw * track.velocity.y) / omega;
  }
  return {cv, ca, ct};
}

double propagated_position_lambda_max(const ObstacleTrack& track, double s,
                                      double process_noise) {
  const Matrix4 p = predict_covariance(track.covariance, std::max(0.0, s),
                                       std::max(0.0, process_noise));
  const double a = m(p, 0, 0);
  const double b = 0.5 * (m(p, 0, 1) + m(p, 1, 0));
  const double d = m(p, 1, 1);
  const double trace = a + d;
  const double disc = std::sqrt(std::max(0.0, (a - d) * (a - d) + 4.0 * b * b));
  return std::max(0.0, 0.5 * (trace + disc));
}

double covariance_margin(const ObstacleTrack& track, double s, double alpha,
                         double process_noise) {
  const double safe_alpha = clamp_value(alpha, 1e-12, 1.0 - 1e-12);
  const double quantile = -2.0 * std::log(safe_alpha);
  return std::sqrt(quantile * propagated_position_lambda_max(
      track, s, process_noise));
}

double rectangle_circle_signed_distance(const VesselState& vessel,
                                        double length_m, double beam_m,
                                        Vec2 circle_center, double radius_m) {
  const double dx = circle_center.x - vessel.n;
  const double dy = circle_center.y - vessel.e;
  const double c = std::cos(vessel.psi);
  const double s = std::sin(vessel.psi);
  const double qx = c * dx + s * dy;
  const double qy = -s * dx + c * dy;
  const double ox = std::abs(qx) - 0.5 * length_m;
  const double oy = std::abs(qy) - 0.5 * beam_m;
  const double outside = std::hypot(std::max(ox, 0.0), std::max(oy, 0.0));
  const double inside = std::min(std::max(ox, oy), 0.0);
  return outside + inside - radius_m;
}

ClosestApproach tcpa_dcpa(Vec2 relative_position, Vec2 relative_velocity) {
  const double speed2 = dot(relative_velocity, relative_velocity);
  if (speed2 <= 1e-14) return {std::numeric_limits<double>::infinity(), norm(relative_position)};
  const double tcpa = std::max(0.0, -dot(relative_position, relative_velocity) / speed2);
  return {tcpa, norm(relative_position + relative_velocity * tcpa)};
}

std::optional<double> circle_ttc(Vec2 p, Vec2 v, double radius) {
  const double a = dot(v, v);
  const double c = dot(p, p) - radius * radius;
  if (c <= 0.0) return 0.0;
  if (a <= 1e-14) return std::nullopt;
  const double b = 2.0 * dot(p, v);
  const double discriminant = b * b - 4.0 * a * c;
  if (discriminant < 0.0) return std::nullopt;
  const double root = (-b - std::sqrt(discriminant)) / (2.0 * a);
  if (root < 0.0) return std::nullopt;
  return root;
}

double choose_horizon(const Snapshot& snapshot, const ControlConfig& config,
                      const VesselParams& params) {
  if (config.horizon_mode == HorizonMode::PaperExact) return 10.1;
  if (config.horizon_mode == HorizonMode::Fixed) return config.fixed_horizon_s;
  double requested = 4.0;
  const Vec2 own_velocity = world_velocity(snapshot.vessel);
  for (const auto& track : snapshot.tracks) {
    const Vec2 p = track.center - Vec2{snapshot.vessel.n, snapshot.vessel.e};
    const Vec2 v = track.velocity - own_velocity;
    const auto closest = tcpa_dcpa(p, v);
    const double combined = track.radius_m + 0.5 * std::hypot(params.length_m, params.beam_m) +
                            config.base_margin_m;
    const auto ttc = circle_ttc(p, v, combined);
    if ((ttc && *ttc < 6.0) || (closest.tcpa_s < 6.0 && closest.dcpa_m < combined + 1.0)) {
      requested = 10.1;
    } else if (closest.tcpa_s < 10.0 && closest.dcpa_m < combined + 3.0) {
      requested = std::max(requested, 8.0);
    } else if (norm(p) < 25.0) {
      requested = std::max(requested, 6.0);
    }
  }
  if (!snapshot.perception_healthy) requested = std::max(requested, 8.0);
  const double rate_limited_low = std::max(2.0, config.previous_horizon_s - 2.0);
  const double rate_limited_high = std::min(10.1, config.previous_horizon_s + 2.0);
  return clamp_value(requested, rate_limited_low, rate_limited_high);
}

std::vector<double> steering_candidates(double exact_human_rad,
                                        SamplingMode mode, double max_rad) {
  const double exact = clamp_value(exact_human_rad, -max_rad, max_rad);
  std::vector<double> candidates{exact};
  std::set<long long> seen{std::llround(exact * 1e12)};
  auto append_grid = [&](double spacing_deg) {
    const int count = static_cast<int>(std::ceil(rad2deg(max_rad) / spacing_deg));
    for (int i = -count; i <= count; ++i) {
      const double value = clamp_value(deg2rad(spacing_deg * i), -max_rad, max_rad);
      const long long key = std::llround(value * 1e12);
      if (seen.insert(key).second) candidates.push_back(value);
    }
  };
  if (mode == SamplingMode::Uniform4) append_grid(4.0);
  if (mode == SamplingMode::Uniform2) append_grid(2.0);
  if (mode == SamplingMode::Uniform1) append_grid(1.0);
  if (mode == SamplingMode::Uniform05) append_grid(0.5);
  if (mode == SamplingMode::NestedAdaptive) {
    append_grid(4.0);
    append_grid(2.0);
    append_grid(1.0);
    append_grid(0.5);
  }
  std::stable_sort(candidates.begin() + 1, candidates.end(),
                   [exact](double a, double b) {
                     const double da = std::abs(a - exact);
                     const double db = std::abs(b - exact);
                     if (std::abs(da - db) < 1e-14) return a < b;
                     return da < db;
                   });
  return candidates;
}

void RecoveryCommitment::commit(const Witness& witness, double absolute_now_s) {
  witness_ = witness;
  committed_at_s_ = absolute_now_s;
  absolute_throttle_deadline_s_ = absolute_now_s + witness.latest_throttle_effect_s;
  active_ = witness.complete && !witness.samples.empty();
  requires_revalidation_ = true;
}

void RecoveryCommitment::clear() {
  active_ = false;
  requires_revalidation_ = true;
  committed_at_s_ = 0.0;
  absolute_throttle_deadline_s_ = 0.0;
  witness_ = Witness{};
}

HumanCommand RecoveryCommitment::command_at(double absolute_now_s) const {
  if (!active_ || witness_.samples.empty()) return {};
  const double relative = std::max(0.0, absolute_now_s - committed_at_s_);
  HumanCommand command = witness_.samples.front().command;
  for (const auto& sample : witness_.samples) {
    if (sample.relative_time_s > relative + 1e-12) break;
    command = sample.command;
  }
  return command;
}

void RecoveryCommitment::note_replan(double absolute_now_s) {
  (void)absolute_now_s;
  requires_revalidation_ = true;
  // Intentionally does not move absolute_throttle_deadline_s_.
}

SafetyFilter::SafetyFilter(VesselParams params, ControlConfig config)
    : params_(std::move(params)), config_(std::move(config)) {}

FilterResult SafetyFilter::filter(const Snapshot& snapshot, HumanCommand command,
                                  double monotonic_now_s) {
  const auto wall_start = std::chrono::steady_clock::now();
  FilterResult result;
  result.raw_command = command;
  result.perception_healthy = snapshot.perception_healthy;
  if (!finite(command.throttle) || !finite(command.steering_rad) ||
      !finite_state(snapshot.vessel)) {
    result.outcome = SearchOutcome::InvalidInput;
    result.acceptance_basis = "non-finite input";
    result.latency_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - wall_start).count();
    return result;
  }
  result.admissible_command.throttle = clamp_value(command.throttle, -1.0, 1.0);
  result.admissible_command.steering_rad = clamp_value(
      command.steering_rad, -params_.delta_max_rad, params_.delta_max_rad);
  if (result.admissible_command.throttle < 0.0 &&
      (!params_.reverse_available || !config_.reverse_available)) {
    result.admissible_command.throttle = 0.0;
    result.warnings.push_back("reverse request clamped because reverse is unavailable");
  }
  // Failure handling is subject to the same physical authority as nominal search.
  // PaperHypothetical only grants hypothetical throttle in prediction, not at output.
  const bool steering_only = config_.authority == AuthorityMode::SteeringHoldContract ||
                             config_.authority == AuthorityMode::PaperHypothetical;
  const HumanCommand degraded_command{
      steering_only ? result.admissible_command.throttle : 0.0,
      snapshot.vessel.delta_rad};
  if (!snapshot.perception_healthy ||
      monotonic_now_s - snapshot.sensor_timestamp_s > config_.max_input_age_s) {
    result.outcome = SearchOutcome::StaleInput;
    result.applied_command = degraded_command;
    result.acceptance_basis = "perception unhealthy or stale";
    result.warnings.push_back("degraded command is not a certified safe action");
    result.latency_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - wall_start).count();
    return result;
  }

  HumanCommand requested = result.admissible_command;
  if (recovery_.active()) {
    recovery_.note_replan(monotonic_now_s);
    requested = recovery_.command_at(monotonic_now_s);
    result.recovery_active = true;
    result.warnings.push_back("committed recovery command revalidated against current snapshot");
  }

  const double horizon = choose_horizon(snapshot, config_, params_);
  result.requested_horizon_s = horizon;
  result.actual_horizon_s = horizon;
  const auto steering_values = steering_candidates(
      requested.steering_rad, config_.sampling, params_.delta_max_rad);
  std::vector<HumanCommand> candidates;
  if (config_.authority == AuthorityMode::FullCommandWeighted) {
    std::set<std::pair<long long, long long>> seen;
    auto add_candidate = [&](HumanCommand value) {
      const auto key = std::make_pair(std::llround(value.throttle * 1e12),
                                      std::llround(value.steering_rad * 1e12));
      if (seen.insert(key).second) candidates.push_back(value);
    };
    add_candidate(requested);
    for (double throttle : {requested.throttle, -1.0, -0.5, 0.0, 0.5, 1.0}) {
      if (throttle < 0.0 && (!params_.reverse_available || !config_.reverse_available)) continue;
      for (double steering : steering_values) add_candidate({throttle, steering});
    }
    std::stable_sort(candidates.begin() + 1, candidates.end(),
        [&](const HumanCommand& a, const HumanCommand& b) {
          const auto distance = [&](const HumanCommand& value) {
            const double dt = value.throttle - requested.throttle;
            const double ds = (value.steering_rad - requested.steering_rad) /
                              params_.delta_max_rad;
            return std::sqrt(config_.full_command_throttle_weight * dt * dt +
                             config_.full_command_steering_weight * ds * ds);
          };
          const double da = distance(a);
          const double db = distance(b);
          if (std::abs(da - db) < 1e-14) {
            return std::tie(a.throttle, a.steering_rad) <
                   std::tie(b.throttle, b.steering_rad);
          }
          return da < db;
        });
  } else {
    for (double steering : steering_values) candidates.push_back({requested.throttle, steering});
  }
  result.nominal_candidate_count = candidates.size();
  SearchClock clock;
  clock.start = wall_start;
  clock.budget_ms = config_.planning_budget_ms;
  clock.deadline_aware = config_.deadline_aware;
  clock.max_steps = config_.max_integration_steps;

  double best_fallback_score = -std::numeric_limits<double>::infinity();
  HumanCommand best_fallback = requested;
  bool any_numerical_failure = false;
  bool pure_steering_exhausted = true;

  auto run_search = [&](bool emergency_phase) -> bool {
    bool retained_largest = false;
    HumanCommand largest_command{};
    CandidateEvaluation largest_evaluation{};
    for (std::size_t index = 0; index < candidates.size(); ++index) {
      if (clock.expired()) {
        pure_steering_exhausted = false;
        return false;
      }
      const HumanCommand candidate = candidates[index];
      ++result.evaluated_candidate_count;
      auto evaluation = evaluate_candidate(snapshot, requested, candidate, horizon,
                                           config_, params_, clock, emergency_phase);
      result.nominal_branch_count += evaluation.nominal_branches;
      result.unique_branch_count += evaluation.unique_branches;
      result.evaluated_branch_count += evaluation.evaluated_branches;
      any_numerical_failure = any_numerical_failure || evaluation.numerical_failure;
      if (evaluation.fallback_score > best_fallback_score) {
        best_fallback_score = evaluation.fallback_score;
        best_fallback = candidate;
      }
      if (!evaluation.complete) {
        pure_steering_exhausted = false;
        return false;
      }
      if (evaluation.accepted) {
        if (index > 0 && config_.selection_policy == SelectionPolicy::LargestClearance) {
          if (!retained_largest || evaluation.best_gap > largest_evaluation.best_gap) {
            retained_largest = true;
            largest_command = candidate;
            largest_evaluation = evaluation;
          }
          continue;
        }
        result.outcome = SearchOutcome::WitnessFound;
        result.paper_status = index == 0 ? 0 : 1;
        result.applied_command = candidate;
        result.acceptance_basis = index == 0 ? "exact admissible human command has complete witness"
                                              : "nearest evaluated steering candidate has complete witness";
        result.predicted_minimum_clearance_m = evaluation.best_gap;
        result.witness = std::move(evaluation.best_witness);
        result.minimality_established = true;
        result.search_complete = true;
        result.used_hypothetical_throttle = std::any_of(
            result.witness.samples.begin(), result.witness.samples.end(),
            [&](const WitnessSample& sample) {
              return std::abs(sample.command.throttle - requested.throttle) > 1e-12;
            });
        if (emergency_phase && result.used_hypothetical_throttle &&
            config_.authority == AuthorityMode::EmergencyAuthority) {
          recovery_.commit(result.witness, monotonic_now_s);
          recovery_.mark_revalidated();
          result.recovery_active = true;
        }
        return true;
      }
    }
    if (retained_largest) {
      result.outcome = SearchOutcome::WitnessFound;
      result.paper_status = 1;
      result.applied_command = largest_command;
      result.acceptance_basis = "largest-clearance accepted candidate after exact human rejection";
      result.predicted_minimum_clearance_m = largest_evaluation.best_gap;
      result.witness = std::move(largest_evaluation.best_witness);
      result.minimality_established = false;
      result.search_complete = true;
      result.used_hypothetical_throttle = std::any_of(
          result.witness.samples.begin(), result.witness.samples.end(),
          [&](const WitnessSample& sample) {
            return std::abs(sample.command.throttle - requested.throttle) > 1e-12;
          });
      return true;
    }
    return false;
  };

  if (run_search(false)) {
    result.integration_steps = clock.steps;
  } else if (config_.authority == AuthorityMode::EmergencyAuthority &&
             pure_steering_exhausted && !clock.expired()) {
    result.evaluated_candidate_count = 0;
    if (!run_search(true)) {
      result.warnings.push_back("authorized thrust phase found no complete witness");
    }
    result.integration_steps = clock.steps;
  } else {
    result.integration_steps = clock.steps;
  }

  if (result.outcome != SearchOutcome::WitnessFound) {
    if (clock.expired() || !pure_steering_exhausted) {
      result.outcome = SearchOutcome::BudgetExhaustedUnknown;
      result.paper_status = -1;
      result.applied_command = degraded_command;
      result.acceptance_basis = "search incomplete; no partial branch accepted";
      result.search_complete = false;
      result.minimality_established = false;
    } else if (any_numerical_failure) {
      result.outcome = SearchOutcome::NumericalFailure;
      result.paper_status = -1;
      result.applied_command = degraded_command;
      result.acceptance_basis = "numerical failure during exhaustive search";
    } else {
      result.outcome = SearchOutcome::ExhaustedNoWitness;
      result.paper_status = 2;
      result.applied_command = best_fallback;
      result.acceptance_basis = "full declared library exhausted; best-effort survival score";
      result.search_complete = true;
      result.minimality_established = false;
    }
  }
  result.latency_ms = std::chrono::duration<double, std::milli>(
      std::chrono::steady_clock::now() - wall_start).count();
  return result;
}

void SafetyFilter::reset() { recovery_.clear(); }

const char* to_string(SearchOutcome outcome) {
  switch (outcome) {
    case SearchOutcome::WitnessFound: return "witness_found";
    case SearchOutcome::ExhaustedNoWitness: return "exhausted_no_witness";
    case SearchOutcome::BudgetExhaustedUnknown: return "budget_exhausted_unknown";
    case SearchOutcome::InvalidInput: return "invalid_input";
    case SearchOutcome::StaleInput: return "stale_input";
    case SearchOutcome::NumericalFailure: return "numerical_failure";
  }
  return "unknown";
}

}  // namespace cocommand
