@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  call init_venv.bat
)
call .venv\Scripts\activate

set PYTHONUNBUFFERED=1

set "DEFAULT_HOST=0.0.0.0"
set "DEFAULT_PORT=8765"
set /p DASH_HOST=Enter host to bind [%DEFAULT_HOST%]: 
if "%DASH_HOST%"=="" set "DASH_HOST=%DEFAULT_HOST%"
set /p DASH_PORT=Enter port [%DEFAULT_PORT%]: 
if "%DASH_PORT%"=="" set "DASH_PORT=%DEFAULT_PORT%"

echo === launching entry dashboard on %DASH_HOST%:%DASH_PORT% ===
python entry_dashboard.py --host "%DASH_HOST%" --port %DASH_PORT%
set RET=%ERRORLEVEL%
echo === entry dashboard exited with code %RET% ===

echo.
pause

endlocal
