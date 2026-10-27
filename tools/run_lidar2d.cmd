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
"%PYTHON_EXE%" -I "%~dp0..\launch_lidar2d.py" %*
exit /b %ERRORLEVEL%
