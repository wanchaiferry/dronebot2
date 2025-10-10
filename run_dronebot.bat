@echo off
setlocal
cd /d %~dp0

REM Convenience wrapper to launch the live dronebot loop.
call "%~dp0run_live.bat" %*

endlocal
