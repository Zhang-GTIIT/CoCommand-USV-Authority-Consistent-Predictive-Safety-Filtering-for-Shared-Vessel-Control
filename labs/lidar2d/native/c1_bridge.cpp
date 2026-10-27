// Independent adapter to the official SDK API; no demo application code is included.
#include "sl_lidar.h"
#include "sl_lidar_driver.h"
#include <atomic>
#include <csignal>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
std::atomic<bool> stop_requested{false};
volatile std::sig_atomic_t interrupted = 0;
void signal_stop(int) { interrupted = 1; }
void check(sl_result result, const char* operation) {
    if (SL_IS_FAIL(result)) {
        throw std::runtime_error(std::string(operation) + " failed (SDK code " + std::to_string(result) + ")");
    }
}
struct Connection {
    std::unique_ptr<sl::IChannel> channel;
    std::unique_ptr<sl::ILidarDriver> driver;
    bool connected = false;
    ~Connection() {
        if (driver && connected) {
            driver->stop(); // C1 motor follows scan state; no independent PWM.
            driver->disconnect();
        }
    }
};
}

int main(int argc, char** argv) {
    if (argc < 2 || argc > 3 || std::string(argv[1]) == "--help") {
        std::cerr << "Usage: cocommand_c1 COM5 [460800]\n"
                  << "stdout: scan JSONL; stderr: device/health diagnostics; stdin: stop + newline\n";
        return argc >= 2 ? 0 : 2;
    }
    try {
        const auto baud = argc == 3 ? std::stoul(argv[2]) : 460800UL;
        if (baud != 460800) throw std::runtime_error("C1 profile requires 460800 baud (8N1)");
        Connection device;
        std::string port = argv[1];
#ifdef _WIN32
        if (port.rfind("COM", 0) == 0 || port.rfind("com", 0) == 0) port = "\\\\.\\" + port;
#endif
        std::cerr << "CONNECTING " << port << " @ " << baud << " 8N1\n";
        auto channel = sl::createSerialPortChannel(port.c_str(), static_cast<int>(baud));
        auto driver = sl::createLidarDriver();
        if (!channel || !driver) throw std::runtime_error("SDK allocation failed");
        device.channel.reset(*channel);
        device.driver.reset(*driver);
        check(device.driver->connect(device.channel.get()), "Serial connection");
        device.connected = true;
        sl_lidar_response_device_info_t info{};
        check(device.driver->getDeviceInfo(info), "Device info");
        std::string model;
        check(device.driver->getModelNameDescriptionString(model, false, &info), "Model identification");
        std::cerr << "SDK " << SL_LIDAR_SDK_VERSION << " model=" << model
                  << " firmware=" << (info.firmware_version >> 8) << '.' << (info.firmware_version & 255)
                  << " hardware=" << static_cast<int>(info.hardware_version) << '\n';
        if (model != "C1M1") throw std::runtime_error("This hardware profile requires C1M1; detected " + model);
        sl_lidar_response_device_health_t health{};
        check(device.driver->getHealth(health), "Health query");
        std::cerr << "health=" << static_cast<int>(health.status) << " error=" << health.error_code << '\n';
        if (health.status == SL_LIDAR_STATUS_ERROR) throw std::runtime_error("Device health error; inspect power and scanner");
        std::vector<sl::LidarScanMode> modes;
        check(device.driver->getAllSupportedScanModes(modes), "Scan-mode query");
        for (const auto& mode : modes)
            std::cerr << "mode=" << mode.id << " " << mode.scan_mode << " us/sample=" << mode.us_per_sample << '\n';
        sl::LidarScanMode used{};
        check(device.driver->startScan(false, true, 0, &used), "Typical scan start");
        std::cerr << "SCANNING " << used.scan_mode << " (device typical scan; expected about 10 Hz)\n";
        std::signal(SIGINT, signal_stop);
        std::signal(SIGTERM, signal_stop);
        // The process owns stdin; detached reader ends with the process if scanning fails.
        std::thread([] { std::string line; std::getline(std::cin, line); stop_requested = true; }).detach();
        std::cout << std::fixed << std::setprecision(4);
        while (!stop_requested && !interrupted) {
            sl_lidar_response_measurement_node_hq_t nodes[8192];
            size_t count = 8192;
            check(device.driver->grabScanDataHq(nodes, count, 1500), "Scan read (disconnect/timeout)");
            if (!count) continue;
            // Preserve device sample order; Scan carries explicit angles, no uniform-bin assumption.
            std::cout << "{\"type\":\"scan\",\"angles_cw_deg\":[";
            for (size_t i = 0; i < count; ++i) {
                if (i) std::cout << ',';
                std::cout << nodes[i].angle_z_q14 * (90.0 / 16384.0);
            }
            std::cout << "],\"distances_mm\":[";
            for (size_t i = 0; i < count; ++i) {
                if (i) std::cout << ',';
                std::cout << nodes[i].dist_mm_q2 / 4.0;
            }
            std::cout << "],\"quality\":[";
            for (size_t i = 0; i < count; ++i) {
                if (i) std::cout << ',';
                std::cout << static_cast<unsigned>(nodes[i].quality);
            }
            std::cout << "]}\n" << std::flush;
            if (!std::cout) break;
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "ERROR: " << error.what() << '\n';
        return 2;
    }
}
