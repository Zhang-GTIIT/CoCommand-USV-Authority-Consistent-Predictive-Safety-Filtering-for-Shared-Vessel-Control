@echo off
setlocal
pushd "%~dp0"
call tools\run_lidar2d.cmd example %*
set "RESULT=%ERRORLEVEL%"
if "%~1"=="" pause
popd
exit /b %RESULT%
