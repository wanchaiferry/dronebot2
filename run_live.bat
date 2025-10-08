@echo off
setlocal
cd /d %~dp0
set PYTHONUNBUFFERED=1

if not exist .venv ( call init_venv.bat )
call .venv\Scripts\activate

REM Optional env
set IB_HOST=127.0.0.1
set IB_PORT=7497
set IB_CID=21
set LIVE_EQUITY=150000
set HARD_STOP_PCT=5
set TRAIL_PCT=2.5
set LOOP_SLEEP_SEC=1

echo === starting dronebot ===
python dronebot.py
set RET=%ERRORLEVEL%
echo === dronebot exited with code %RET% ===
if NOT "%RET%"=="0" (
  echo (showing last 50 lines of bot_errors.log if present)
  powershell -NoProfile -Command "if (Test-Path '.\bot_errors.log') { Get-Content .\bot_errors.log -Tail 50 }"
  echo.
  pause
)
endlocal
