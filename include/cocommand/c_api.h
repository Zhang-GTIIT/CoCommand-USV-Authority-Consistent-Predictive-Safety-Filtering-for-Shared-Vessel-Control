#pragma once

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#  if defined(COCOMMAND_C_EXPORTS)
#    define CC_API __declspec(dllexport)
#  else
#    define CC_API __declspec(dllimport)
#  endif
#else
#  define CC_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct CCHandle CCHandle;

typedef struct {
  int authority_mode;
  int sampling_mode;
  int horizon_mode;
  int margin_mode;
  int predictor_mode;
  int backup_library_mode;
  int selection_policy;
  double fixed_horizon_s;
  double planning_budget_ms;
  double base_margin_m;
  double covariance_alpha;
  int deadline_aware;
  int reverse_available;
  int sweep_margin_enabled;
  int radius_inflation_enabled;
  double track_memory_s;
  uint64_t max_integration_steps;
} CCConfig;

typedef struct {
  double applied_throttle;
  double applied_steering_rad;
  int outcome;
  int paper_status;
  double predicted_minimum_clearance_m;
  double requested_horizon_s;
  double actual_horizon_s;
  double latency_ms;
  uint64_t evaluated_candidates;
  uint64_t evaluated_branches;
  uint64_t integration_steps;
  int search_complete;
  int minimality_established;
  int recovery_active;
  int used_hypothetical_throttle;
  double witness_required_throttle;
} CCFilterResult;

CC_API CCHandle* cc_create(const CCConfig* config);
CC_API void cc_destroy(CCHandle* handle);
CC_API int cc_reset(CCHandle* handle);
/* Set before feeding observations. Preserves the existing CCConfig ABI. */
CC_API int cc_set_first_complete_witness(CCHandle* handle, int enabled);
/* Zero unless the last result contains a complete witness. */
CC_API size_t cc_last_complete_witness_samples(CCHandle* handle);
CC_API int cc_process_scan(CCHandle* handle, const double vessel_state[8],
                           const double* ranges_m, const uint8_t* hits,
                           size_t beam_count, double max_range_m,
                           double sensor_timestamp_s,
                           double receive_timestamp_s);
CC_API int cc_filter(CCHandle* handle, const double vessel_state[8],
                     const double human_command[2], int perception_healthy,
                     double sensor_timestamp_s, double receive_timestamp_s,
                     double aligned_timestamp_s,
                     double expected_apply_timestamp_s,
                     double monotonic_now_s, CCFilterResult* result);
CC_API const char* cc_version(void);

#ifdef __cplusplus
}
#endif
