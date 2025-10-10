@echo off
setlocal EnableDelayedExpansion
cd /d %~dp0

set "ORIG_ARGS=%*"

call :ensure_venv
if errorlevel 1 (
  set RET=%ERRORLEVEL%
  goto :finalize
)

set "SCRIPT_DIR=%~dp0"
set "VENV_SCRIPTS=%SCRIPT_DIR%.venv\Scripts"
set "ACTIVATE_BAT=%VENV_SCRIPTS%\activate.bat"
set "PYTHON_EXE=%VENV_SCRIPTS%\python.exe"
set "RUN_LIVE=%SCRIPT_DIR%run_live.bat"

if not exist "%ACTIVATE_BAT%" (
  echo Could not find %ACTIVATE_BAT%.
  set RET=1
  goto :finalize
)
if not exist "%PYTHON_EXE%" (
  echo Could not find %PYTHON_EXE%.
  set RET=1
  goto :finalize
)

set "DEFAULT_HOST=0.0.0.0"
set "DEFAULT_PORT=8765"
set /p DASH_HOST=Enter host to bind [%DEFAULT_HOST%]:
if "!DASH_HOST!"=="" set "DASH_HOST=%DEFAULT_HOST%"
set /p DASH_PORT=Enter port [%DEFAULT_PORT%]:
if "!DASH_PORT!"=="" set "DASH_PORT=%DEFAULT_PORT%"

echo === launching entry dashboard on !DASH_HOST!:!DASH_PORT! ===
start "Entry Dashboard" cmd /k "cd /d \"%SCRIPT_DIR%\" ^&^& call \"%ACTIVATE_BAT%\" ^&^& set PYTHONUNBUFFERED=1 ^&^& \"%PYTHON_EXE%\" \"%SCRIPT_DIR%entry_dashboard.py\" --host \"!DASH_HOST!\" --port !DASH_PORT! ^&^& echo. ^&^& pause"

if exist "%RUN_LIVE%" (
  echo === launching dronebot via run_live.bat ===
  start "Dronebot" cmd /k "cd /d \"%SCRIPT_DIR%\" ^&^& call \"%ACTIVATE_BAT%\" ^&^& call \"%RUN_LIVE%\" !ORIG_ARGS! ^&^& echo. ^&^& pause"
) else (
  echo === run_live.bat not found; launching dronebot.py directly ===
  start "Dronebot" cmd /k "cd /d \"%SCRIPT_DIR%\" ^&^& call \"%ACTIVATE_BAT%\" ^&^& set PYTHONUNBUFFERED=1 ^&^& \"%PYTHON_EXE%\" \"%SCRIPT_DIR%dronebot.py\" !ORIG_ARGS! ^&^& echo. ^&^& pause"
)

echo.
echo Both processes have been launched in their own windows.
echo You can return to them or close this window when finished.
echo.
pause
set RET=0
goto :finalize

:ensure_venv
if exist .venv\Scripts\python.exe goto :activate

echo === creating Python virtual environment via init_venv.bat ===
if not exist init_venv.bat (
  echo init_venv.bat is missing; cannot continue.
  exit /b 1
)
call "%~dp0init_venv.bat"
if errorlevel 1 (
  echo init_venv.bat reported an error; see messages above.
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Virtual environment creation appears to have failed (.venv\Scripts\python.exe missing).
  exit /b 1
)

:activate
if not exist .venv\Scripts\activate.bat (
  echo Could not find .venv\Scripts\activate.bat.
  exit /b 1
)
exit /b 0

:finalize
if not defined RET set RET=0
endlocal & exit /b %RET%
