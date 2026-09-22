#pragma once

#include "cocommand/core.hpp"

#include <cstdint>
#include <vector>

namespace cocommand {

enum class ShapeType { Circle, Rectangle, Segment, Polygon };

struct WorldShape {
  ShapeType type{ShapeType::Circle};
  Vec2 center{};
  double radius_m{0.0};
  double length_m{0.0};
  double width_m{0.0};
  double heading_rad{0.0};
  std::vector<Vec2> vertices{};
};

struct ScanBeam {
  double bearing_rad{0.0};
  double range_m{0.0};
  bool hit{false};
  double sensor_timestamp_s{0.0};
};

struct TimedScan {
  Vec2 sensor_position{};
  double sensor_heading_rad{0.0};
  double sensor_timestamp_s{0.0};
  double receive_timestamp_s{0.0};
  double max_range_m{65.0};
  std::vector<ScanBeam> beams{};
};

TimedScan simulate_radar(const VesselState& vessel,
                         const std::vector<WorldShape>& world,
                         double timestamp_s, std::size_t beam_count = 360,
                         double max_range_m = 65.0);
std::vector<Detection> reconstruct_detections(const TimedScan& scan,
                                              double cluster_gap_m = 1.5);

}  // namespace cocommand

