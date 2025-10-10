@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  call init_venv.bat
)
call .venv\Scripts\activate

set PYTHONUNBUFFERED=1

set "DEFAULT_CSV=fills_live.csv"
set /p FILLS_CSV=Enter path to fills CSV [%DEFAULT_CSV%]: 
if "%FILLS_CSV%"=="" set "FILLS_CSV=%DEFAULT_CSV%"

set /p SYMBOL=Enter symbol to describe: 
if "%SYMBOL%"=="" (
  echo Symbol is required.
  pause
  endlocal
  exit /b 1
)

echo === describing fills for %SYMBOL% ===
python describe_fills.py "%FILLS_CSV%" "%SYMBOL%"
set RET=%ERRORLEVEL%
echo === describe_fills finished with exit code %RET% ===

echo.
pause

endlocal
