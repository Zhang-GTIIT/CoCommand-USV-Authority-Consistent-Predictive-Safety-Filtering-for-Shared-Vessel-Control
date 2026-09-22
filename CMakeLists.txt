cmake_minimum_required(VERSION 3.20)
project(CoCommandUSV VERSION 0.1.0 LANGUAGES CXX)

option(COCOMMAND_BUILD_TESTS "Build native tests" ON)
option(COCOMMAND_BUILD_PYBIND "Build optional pybind11 module" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(MSVC)
  add_compile_options(/W4 /permissive- /EHsc)
else()
  add_compile_options(-Wall -Wextra -Wpedantic -Wconversion -Wshadow)
endif()

add_library(cocommand_core OBJECT
  cpp/core.cpp
  cpp/perception.cpp
  cpp/runtime.cpp
)
target_include_directories(cocommand_core PUBLIC include)

add_library(cocommand_c SHARED cpp/c_api.cpp)
target_link_libraries(cocommand_c PRIVATE cocommand_core)
target_include_directories(cocommand_c PUBLIC include)
target_compile_definitions(cocommand_c PRIVATE COCOMMAND_C_EXPORTS)
set_target_properties(cocommand_c PROPERTIES OUTPUT_NAME "cocommand_c")

add_executable(cocommand_runner apps/cocommand_runner.cpp)
target_link_libraries(cocommand_runner PRIVATE cocommand_core)

if(COCOMMAND_BUILD_PYBIND)
  set(PYBIND11_FINDPYTHON ON)
  find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
  find_package(pybind11 2.13 CONFIG REQUIRED)
  pybind11_add_module(_cocommand bindings/python.cpp)
  target_link_libraries(_cocommand PRIVATE cocommand_core)
endif()

include(GNUInstallDirs)
install(TARGETS cocommand_c cocommand_runner
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

if(COCOMMAND_BUILD_TESTS)
  enable_testing()
  add_executable(cocommand_core_tests tests/unit/test_core.cpp)
  target_link_libraries(cocommand_core_tests PRIVATE cocommand_core)
  add_test(NAME cocommand_core_tests COMMAND cocommand_core_tests)
endif()
