#pragma once

#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace cocommand {

constexpr double kPi = 3.1415926535897932384626433832795;
constexpr double deg2rad(double deg) { return deg * kPi / 180.0; }
constexpr double rad2deg(double rad) { return rad * 180.0 / kPi; }

struct Vec2 {
  double x{0.0};
  double y{0.0};
};

Vec2 operator+(Vec2 a, Vec2 b);
Vec2 operator-(Vec2 a, Vec2 b);
Vec2 operator*(Vec2 a, double s);
double dot(Vec2 a, Vec2 b);
double norm(Vec2 a);

struct VesselState {
  double n{0.0};
  double e{0.0};
  double psi{0.0};
  double u{0.0};
  double v{0.0};
  double r{0.0};
  double thrust_n{0.0};
  double delta_rad{0.0};
};

struct HumanCommand {
  double throttle{0.0};
  double steering_rad{0.0};
};

struct VesselParams {
  double length_m{1.2};
  double beam_m{0.45};
  double draft_m{0.07};
  double rigid_mass_kg{25.0};
  double m11_kg{30.0};
  double m22_kg{37.0};
  double m33_kg_m2{5.0};
  double surge_linear{4.0};
  double surge_quadratic{6.0};
  double sway_linear{12.0};
  double yaw_linear{3.0};
  double water_density{1000.0};
  double crossflow_cd{1.0};
  int crossflow_strips{21};
  double thrust_forward_n{20.0};
  double thrust_reverse_n{12.0};
  double tau_thrust_s{0.35};
  double tau_delta_s{0.25};
  double delta_max_rad{deg2rad(30.0)};
  double delta_rate_max_rad_s{deg2rad(60.0)};
  bool reverse_available{true};
};

struct DynamicsDerivative {
  std::array<double, 8> dx{};
};

DynamicsDerivative vessel_derivative(const VesselState& state,
                                     const HumanCommand& command,
                                     const VesselParams& params);
VesselState rk4_step(const VesselState& state, const HumanCommand& command,
                     double dt_s, const VesselParams& params);
double coriolis_power(const VesselState& state, const VesselParams& params);
double damping_power(const VesselState& state, const VesselParams& params);
std::vector<double> paper_time_grid();
std::vector<double> horizon_time_grid(double horizon_s);

struct Detection {
  Vec2 center{};
  double radius_m{0.6};
  double timestamp_s{0.0};
  bool used_fallback{false};
};

struct ObstacleTrack {
  std::uint64_t id{0};
  Vec2 center{};
  Vec2 velocity{};
  Vec2 acceleration{};
  double turn_rate_rad_s{0.0};
  double radius_m{0.6};
  double observed_time_s{0.0};
  double aligned_time_s{0.0};
  double age_since_observation_s{0.0};
  double sigma_velocity_mps{0.12};
  std::array<double, 16> covariance{{0.25,0,0,0, 0,0.25,0,0, 0,0,0.25,0, 0,0,0,0.25}};
  std::array<double, 3> mode_probability{{0.70, 0.20, 0.10}};
  bool low_confidence{false};
};

enum class PredictorMode { PaperCvSmoothing, CvKalman, CaKalman, Imm };

class Tracker {
 public:
  explicit Tracker(PredictorMode mode = PredictorMode::PaperCvSmoothing,
                   double memory_s = 3.0);
  const std::vector<ObstacleTrack>& update(const std::vector<Detection>& detections,
                                           double timestamp_s);
  const std::vector<ObstacleTrack>& tracks() const { return tracks_; }
  void clear();
 private:
  PredictorMode mode_;
  double memory_s_{3.0};
  std::vector<ObstacleTrack> tracks_;
  std::uint64_t next_id_{1};
};

struct PredictedObstacle {
  Vec2 center{};
  double inflated_radius_m{0.0};
  double speed_allowance_mps{0.0};
};

std::vector<Vec2> predicted_centers(const ObstacleTrack& track, double s,
                                    PredictorMode mode);
double propagated_position_lambda_max(const ObstacleTrack& track, double s,
                                      double process_noise);
double covariance_margin(const ObstacleTrack& track, double s, double alpha,
                         double process_noise);

double rectangle_circle_signed_distance(const VesselState& vessel,
                                        double length_m, double beam_m,
                                        Vec2 circle_center, double radius_m);

enum class AuthorityMode {
  PaperHypothetical,
  SteeringHoldContract,
  EmergencyAuthority,
  FullCommandWeighted
};
enum class SamplingMode { Uniform4, Uniform2, Uniform1, Uniform05, NestedAdaptive };
enum class HorizonMode { Fixed, PaperExact, AdaptiveGuarded };
enum class MarginMode { FixedOnly, PaperInflation, Covariance };
enum class BackupLibraryMode {
  Paper24,
  Deduplicated,
  Extended,
  FrozenCandidate,
  PredictiveSegmentsAdapted,
  GoalAgnosticSamplingAdapted
};
enum class SelectionPolicy { MinimumModification, LargestClearance };
enum class SearchOutcome {
  WitnessFound,
  ExhaustedNoWitness,
  BudgetExhaustedUnknown,
  InvalidInput,
  StaleInput,
  NumericalFailure
};

struct Snapshot {
  VesselState vessel{};
  std::array<double, 16> own_state_covariance{};  // [n,e,vn,ve], zero means unavailable/assumed exact
  std::vector<ObstacleTrack> tracks{};
  bool perception_healthy{true};
  double sensor_timestamp_s{0.0};
  double receive_timestamp_s{0.0};
  double aligned_timestamp_s{0.0};
  double expected_apply_timestamp_s{0.0};
};

struct ControlConfig {
  AuthorityMode authority{AuthorityMode::SteeringHoldContract};
  SamplingMode sampling{SamplingMode::Uniform2};
  HorizonMode horizon_mode{HorizonMode::PaperExact};
  MarginMode margin_mode{MarginMode::PaperInflation};
  PredictorMode predictor{PredictorMode::PaperCvSmoothing};
  BackupLibraryMode backup_library{BackupLibraryMode::Paper24};
  SelectionPolicy selection_policy{SelectionPolicy::MinimumModification};
  double fixed_horizon_s{10.1};
  double previous_horizon_s{10.1};
  double base_margin_m{0.7};
  double fixed_extra_margin_m{0.0};
  double acceleration_allowance_mps2{0.025};
  double covariance_alpha{0.05};
  double covariance_process_noise{0.05};
  double planning_budget_ms{80.0};
  double max_input_age_s{0.30};
  double full_command_throttle_weight{1.0};
  double full_command_steering_weight{1.0};
  bool sweep_margin_enabled{true};
  bool radius_inflation_enabled{true};
  bool deadline_aware{true};
  bool reverse_available{true};
  bool deduplicate_branches{false};
  bool first_complete_witness{false};  // steering-only minimum-modification search
  std::size_t max_integration_steps{std::numeric_limits<std::size_t>::max()};
};

struct WitnessSample {
  double relative_time_s{0.0};
  VesselState state{};
  HumanCommand command{};
  double clearance_m{std::numeric_limits<double>::infinity()};
};

struct Witness {
  std::string policy_name{};
  std::vector<WitnessSample> samples{};
  double minimum_clearance_m{-std::numeric_limits<double>::infinity()};
  double required_throttle{0.0};
  double generated_at_s{0.0};
  double latest_throttle_effect_s{0.0};
  bool complete{false};
};

struct FilterResult {
  HumanCommand raw_command{};
  HumanCommand admissible_command{};
  HumanCommand applied_command{};
  SearchOutcome outcome{SearchOutcome::InvalidInput};
  int paper_status{-1};
  std::string acceptance_basis{};
  double predicted_minimum_clearance_m{-std::numeric_limits<double>::infinity()};
  double requested_horizon_s{0.0};
  double actual_horizon_s{0.0};
  double latency_ms{0.0};
  std::size_t nominal_candidate_count{0};
  std::size_t evaluated_candidate_count{0};
  std::size_t nominal_branch_count{0};
  std::size_t unique_branch_count{0};
  std::size_t evaluated_branch_count{0};
  std::size_t integration_steps{0};
  bool search_complete{false};
  bool minimality_established{false};
  bool recovery_active{false};
  bool perception_healthy{true};
  bool used_hypothetical_throttle{false};
  Witness witness{};
  std::vector<std::string> warnings{};
};

struct ClosestApproach {
  double tcpa_s{std::numeric_limits<double>::infinity()};
  double dcpa_m{std::numeric_limits<double>::infinity()};
};
ClosestApproach tcpa_dcpa(Vec2 relative_position, Vec2 relative_velocity);
std::optional<double> circle_ttc(Vec2 relative_position, Vec2 relative_velocity,
                                 double radius_sum_m);
double choose_horizon(const Snapshot& snapshot, const ControlConfig& config,
                      const VesselParams& params);
std::vector<double> steering_candidates(double exact_human_rad,
                                        SamplingMode mode,
                                        double max_rad = deg2rad(30.0));

class RecoveryCommitment {
 public:
  void commit(const Witness& witness, double absolute_now_s);
  void clear();
  bool active() const { return active_; }
  bool requires_revalidation() const { return requires_revalidation_; }
  void mark_revalidated() { requires_revalidation_ = false; }
  HumanCommand command_at(double absolute_now_s) const;
  double absolute_throttle_deadline_s() const { return absolute_throttle_deadline_s_; }
  void note_replan(double absolute_now_s);
 private:
  bool active_{false};
  bool requires_revalidation_{true};
  double committed_at_s_{0.0};
  double absolute_throttle_deadline_s_{0.0};
  Witness witness_{};
};

class SafetyFilter {
 public:
  SafetyFilter(VesselParams params = {}, ControlConfig config = {});
  FilterResult filter(const Snapshot& snapshot, HumanCommand command,
                      double monotonic_now_s);
  void reset();
  const RecoveryCommitment& recovery() const { return recovery_; }
 private:
  VesselParams params_;
  ControlConfig config_;
  RecoveryCommitment recovery_;
};

const char* to_string(SearchOutcome outcome);

}  // namespace cocommand
