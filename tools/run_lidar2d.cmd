@echo off
setlocal
set "PYTHON_EXE=%~dp0..\.runtime\python.exe"
if exist "%PYTHON_EXE%" goto run
set "PYTHON_EXE=%~dp0..\.venv311\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto run
set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" goto run
echo Python runtime not found. Extract the complete portable ZIP first.
echo Source checkout users: follow labs\lidar2d\README_CN.md to install Python dependencies.
exit /b 2
:run
set "ENTRY_POINT=%~dp0launch_lidar2d.py"
if not exist "%ENTRY_POINT%" set "ENTRY_POINT=%~dp0..\launch_lidar2d.py"
"%PYTHON_EXE%" -I "%ENTRY_POINT%" %*
exit /b %ERRORLEVEL%
