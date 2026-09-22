@echo off
"%~dp0..\.tools\python\ziglang\zig.exe" c++ -target aarch64-linux-musl %*
