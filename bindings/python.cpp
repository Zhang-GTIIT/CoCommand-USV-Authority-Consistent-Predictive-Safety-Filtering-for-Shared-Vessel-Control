#include "cocommand/core.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;
using namespace cocommand;

PYBIND11_MODULE(_cocommand, module) {
  module.doc() = "Optional direct binding to the CoCommand C++ core";
  module.def("paper_time_grid", &paper_time_grid);
  module.def("rectangle_circle_signed_distance",
             [](const std::vector<double>& state, double length, double beam,
                double cx, double cy, double radius) {
               if (state.size() != 8) throw py::value_error("state must have 8 values");
               VesselState x{state[0], state[1], state[2], state[3], state[4],
                             state[5], state[6], state[7]};
               return rectangle_circle_signed_distance(x, length, beam,
                                                        {cx, cy}, radius);
             });
}

