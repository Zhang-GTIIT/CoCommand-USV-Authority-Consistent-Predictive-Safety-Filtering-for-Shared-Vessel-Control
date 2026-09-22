#include "cocommand/perception.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace cocommand {
namespace {

double cross(Vec2 a, Vec2 b) { return a.x * b.y - a.y * b.x; }

Vec2 rotate(Vec2 p, double angle) {
  const double c = std::cos(angle);
  const double s = std::sin(angle);
  return {c * p.x - s * p.y, s * p.x + c * p.y};
}

std::optional<double> ray_circle(Vec2 origin, Vec2 direction,
                                 Vec2 center, double radius) {
  const Vec2 q = origin - center;
  const double b = 2.0 * dot(q, direction);
  const double c = dot(q, q) - radius * radius;
  const double disc = b * b - 4.0 * c;
  if (disc < 0.0) return std::nullopt;
  const double root = std::sqrt(disc);
  const double t0 = (-b - root) * 0.5;
  const double t1 = (-b + root) * 0.5;
  if (t0 >= 0.0) return t0;
  if (t1 >= 0.0) return t1;
  return std::nullopt;
}

std::optional<double> ray_segment(Vec2 origin, Vec2 direction,
                                  Vec2 a, Vec2 b) {
  const Vec2 edge = b - a;
  const double denominator = cross(direction, edge);
  if (std::abs(denominator) < 1e-12) return std::nullopt;
  const Vec2 offset = a - origin;
  const double t = cross(offset, edge) / denominator;
  const double u = cross(offset, direction) / denominator;
  if (t >= 0.0 && u >= 0.0 && u <= 1.0) return t;
  return std::nullopt;
}

std::optional<double> ray_rectangle(Vec2 origin, Vec2 direction,
                                    const WorldShape& shape) {
  const Vec2 local_origin = rotate(origin - shape.center, -shape.heading_rad);
  const Vec2 local_direction = rotate(direction, -shape.heading_rad);
  const double half_x = 0.5 * shape.length_m;
  const double half_y = 0.5 * shape.width_m;
  double t_min = 0.0;
  double t_max = std::numeric_limits<double>::infinity();
  const double origins[2]{local_origin.x, local_origin.y};
  const double directions[2]{local_direction.x, local_direction.y};
  const double halves[2]{half_x, half_y};
  for (int axis = 0; axis < 2; ++axis) {
    if (std::abs(directions[axis]) < 1e-12) {
      if (origins[axis] < -halves[axis] || origins[axis] > halves[axis]) {
        return std::nullopt;
      }
      continue;
    }
    double t0 = (-halves[axis] - origins[axis]) / directions[axis];
    double t1 = (halves[axis] - origins[axis]) / directions[axis];
    if (t0 > t1) std::swap(t0, t1);
    t_min = std::max(t_min, t0);
    t_max = std::min(t_max, t1);
    if (t_min > t_max) return std::nullopt;
  }
  return t_min >= 0.0 ? std::optional<double>(t_min) : std::optional<double>(t_max);
}

std::optional<double> intersect_shape(Vec2 origin, Vec2 direction,
                                      const WorldShape& shape) {
  if (shape.type == ShapeType::Circle) {
    return ray_circle(origin, direction, shape.center, shape.radius_m);
  }
  if (shape.type == ShapeType::Rectangle) {
    return ray_rectangle(origin, direction, shape);
  }
  if (shape.type == ShapeType::Segment && shape.vertices.size() >= 2) {
    return ray_segment(origin, direction, shape.vertices[0], shape.vertices[1]);
  }
  if (shape.type == ShapeType::Polygon && shape.vertices.size() >= 2) {
    std::optional<double> best;
    for (std::size_t i = 0; i < shape.vertices.size(); ++i) {
      const auto hit = ray_segment(origin, direction, shape.vertices[i],
                                   shape.vertices[(i + 1) % shape.vertices.size()]);
      if (hit && (!best || *hit < *best)) best = hit;
    }
    return best;
  }
  return std::nullopt;
}

bool solve3(std::array<std::array<double, 4>, 3>& a,
            std::array<double, 3>& x) {
  for (int col = 0; col < 3; ++col) {
    int pivot = col;
    for (int row = col + 1; row < 3; ++row) {
      if (std::abs(a[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)]) >
          std::abs(a[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)])) {
        pivot = row;
      }
    }
    if (std::abs(a[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)]) < 1e-10) {
      return false;
    }
    if (pivot != col) std::swap(a[static_cast<std::size_t>(pivot)],
                                a[static_cast<std::size_t>(col)]);
    const double divisor = a[static_cast<std::size_t>(col)][static_cast<std::size_t>(col)];
    for (int j = col; j < 4; ++j) {
      a[static_cast<std::size_t>(col)][static_cast<std::size_t>(j)] /= divisor;
    }
    for (int row = 0; row < 3; ++row) {
      if (row == col) continue;
      const double factor = a[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)];
      for (int j = col; j < 4; ++j) {
        a[static_cast<std::size_t>(row)][static_cast<std::size_t>(j)] -=
            factor * a[static_cast<std::size_t>(col)][static_cast<std::size_t>(j)];
      }
    }
  }
  for (int i = 0; i < 3; ++i) x[static_cast<std::size_t>(i)] = a[static_cast<std::size_t>(i)][3];
  return true;
}

Detection cluster_to_detection(const std::vector<Vec2>& points, double timestamp_s) {
  Vec2 centroid{};
  for (Vec2 p : points) centroid = centroid + p;
  centroid = centroid * (1.0 / static_cast<double>(points.size()));
  if (points.size() < 3) return {centroid, 0.6, timestamp_s, true};

  std::array<std::array<double, 4>, 3> normal{};
  for (Vec2 p : points) {
    const std::array<double, 3> row{{p.x, p.y, 1.0}};
    const double rhs = -(p.x * p.x + p.y * p.y);
    for (int i = 0; i < 3; ++i) {
      for (int j = 0; j < 3; ++j) {
        normal[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] +=
            row[static_cast<std::size_t>(i)] * row[static_cast<std::size_t>(j)];
      }
      normal[static_cast<std::size_t>(i)][3] += row[static_cast<std::size_t>(i)] * rhs;
    }
  }
  std::array<double, 3> solution{};
  bool accepted = solve3(normal, solution);
  Vec2 center{-0.5 * solution[0], -0.5 * solution[1]};
  const double radius_squared = center.x * center.x + center.y * center.y - solution[2];
  const double radius = radius_squared > 0.0 ? std::sqrt(radius_squared) : -1.0;
  double residual = 0.0;
  if (accepted) {
    for (Vec2 p : points) residual = std::max(residual, std::abs(norm(p - center) - radius));
  }
  accepted = accepted && radius >= 0.2 && radius <= 12.0 && residual < 0.12;
  if (accepted) return {center, radius, timestamp_s, false};

  double max_distance = 0.0;
  for (Vec2 p : points) max_distance = std::max(max_distance, norm(p - centroid));
  return {centroid, max_distance + 0.6, timestamp_s, true};
}

}  // namespace

TimedScan simulate_radar(const VesselState& vessel,
                         const std::vector<WorldShape>& world,
                         double timestamp_s, std::size_t beam_count,
                         double max_range_m) {
  TimedScan scan;
  scan.sensor_position = {vessel.n, vessel.e};
  scan.sensor_heading_rad = vessel.psi;
  scan.sensor_timestamp_s = timestamp_s;
  scan.receive_timestamp_s = timestamp_s;
  scan.max_range_m = max_range_m;
  scan.beams.reserve(beam_count);
  for (std::size_t i = 0; i < beam_count; ++i) {
    const double bearing = -kPi + 2.0 * kPi * static_cast<double>(i) /
                                      static_cast<double>(beam_count);
    const double world_angle = vessel.psi + bearing;
    const Vec2 direction{std::cos(world_angle), std::sin(world_angle)};
    double closest = max_range_m;
    bool hit_any = false;
    for (const auto& shape : world) {
      const auto hit = intersect_shape(scan.sensor_position, direction, shape);
      if (hit && *hit >= 0.0 && *hit <= closest && *hit <= max_range_m + 1e-12) {
        closest = *hit;
        hit_any = true;
      }
    }
    scan.beams.push_back({bearing, closest, hit_any, timestamp_s});
  }
  return scan;
}

std::vector<Detection> reconstruct_detections(const TimedScan& scan,
                                              double cluster_gap_m) {
  std::vector<std::vector<Vec2>> clusters;
  std::vector<Vec2> current;
  std::vector<std::size_t> current_indices;
  std::vector<std::vector<std::size_t>> cluster_indices;
  for (std::size_t i = 0; i < scan.beams.size(); ++i) {
    const auto& beam = scan.beams[i];
    if (!beam.hit) {
      if (!current.empty()) {
        clusters.push_back(current);
        cluster_indices.push_back(current_indices);
        current.clear();
        current_indices.clear();
      }
      continue;
    }
    const double angle = scan.sensor_heading_rad + beam.bearing_rad;
    const Vec2 point = scan.sensor_position +
        Vec2{std::cos(angle), std::sin(angle)} * beam.range_m;
    if (!current.empty() && norm(point - current.back()) > cluster_gap_m) {
      clusters.push_back(current);
      cluster_indices.push_back(current_indices);
      current.clear();
      current_indices.clear();
    }
    current.push_back(point);
    current_indices.push_back(i);
  }
  if (!current.empty()) {
    clusters.push_back(current);
    cluster_indices.push_back(current_indices);
  }
  if (clusters.size() >= 2 && !scan.beams.empty() &&
      cluster_indices.front().front() == 0 &&
      cluster_indices.back().back() + 1 == scan.beams.size() &&
      norm(clusters.front().front() - clusters.back().back()) <= cluster_gap_m) {
    std::vector<Vec2> merged = clusters.back();
    merged.insert(merged.end(), clusters.front().begin(), clusters.front().end());
    clusters.front() = std::move(merged);
    clusters.pop_back();
  }
  std::vector<Detection> detections;
  detections.reserve(clusters.size());
  for (const auto& cluster : clusters) {
    detections.push_back(cluster_to_detection(cluster, scan.sensor_timestamp_s));
  }
  return detections;
}

}  // namespace cocommand
