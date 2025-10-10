@echo off
setlocal EnableDelayedExpansion
cd /d %~dp0

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "ACTIVATE_BAT=%VENV_DIR%\Scripts\activate.bat"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
rem Shared loopback default so dashboards and IB prompts stay aligned.
set "DEFAULT_LOOPBACK_HOST=127.0.0.1"

call :ensure_venv
if errorlevel 1 goto :finalize

call "%ACTIVATE_BAT%"
if errorlevel 1 (
  echo Failed to activate the virtual environment.
  goto :finalize
)

:menu
cls
echo ==========================================
echo   Dronebot Windows Toolkit
echo ==========================================
echo   [1] Launch live trading bot (new window)
echo   [2] Launch entry dashboard (new window)
echo   [3] Pre-session anchors and fill review
echo   [4] Describe fills for a symbol
echo   [Q] Quit
set "CHOICE="
set /p "CHOICE=Select an option: "
if /I "!CHOICE!"=="1" call :launch_live & goto :menu
if /I "!CHOICE!"=="2" call :launch_dashboard & goto :menu
if /I "!CHOICE!"=="3" call :pre_session_tools & goto :menu
if /I "!CHOICE!"=="4" call :describe_fills & goto :menu
if /I "!CHOICE!"=="Q" goto :finalize
echo.
echo Invalid selection. Press any key to try again.
pause >nul
goto :menu

:launch_live
setlocal
  set "DEFAULT_IB_HOST=%DEFAULT_LOOPBACK_HOST%"
set "DEFAULT_IB_PORT=7497"
set "DEFAULT_IB_CID=21"
set "DEFAULT_EQUITY=150000"
set "DEFAULT_HARD_STOP=5"
set "DEFAULT_TRAIL=2.5"
set "DEFAULT_LOOP_SLEEP=1"

echo === Dronebot connection parameters ===
set "IB_HOST="
set /p "IB_HOST=IB host [%DEFAULT_IB_HOST%]: "
if "!IB_HOST!"=="" set "IB_HOST=%DEFAULT_IB_HOST%"
set "IB_PORT="
set /p "IB_PORT=IB port [%DEFAULT_IB_PORT%]: "
if "!IB_PORT!"=="" set "IB_PORT=%DEFAULT_IB_PORT%"
set "IB_CID="
set /p "IB_CID=IB client ID [%DEFAULT_IB_CID%]: "
if "!IB_CID!"=="" set "IB_CID=%DEFAULT_IB_CID%"
set "LIVE_EQUITY="
set /p "LIVE_EQUITY=Live equity budget USD [%DEFAULT_EQUITY%]: "
if "!LIVE_EQUITY!"=="" set "LIVE_EQUITY=%DEFAULT_EQUITY%"
set "HARD_STOP="
set /p "HARD_STOP=Hard stop %% [%DEFAULT_HARD_STOP%]: "
if "!HARD_STOP!"=="" set "HARD_STOP=%DEFAULT_HARD_STOP%"
set "TRAIL_PCT="
set /p "TRAIL_PCT=Trail stop %% [%DEFAULT_TRAIL%]: "
if "!TRAIL_PCT!"=="" set "TRAIL_PCT=%DEFAULT_TRAIL%"
set "LOOP_SLEEP="
set /p "LOOP_SLEEP=Loop sleep seconds [%DEFAULT_LOOP_SLEEP%]: "
if "!LOOP_SLEEP!"=="" set "LOOP_SLEEP=%DEFAULT_LOOP_SLEEP%"

echo.
echo Launching dronebot in a new window...
start "Dronebot" cmd /k "cd /d "!SCRIPT_DIR!" ^&^& call "!ACTIVATE_BAT!" ^&^& set PYTHONUNBUFFERED=1 ^&^& set IB_HOST=!IB_HOST! ^&^& set IB_PORT=!IB_PORT! ^&^& set IB_CID=!IB_CID! ^&^& set LIVE_EQUITY=!LIVE_EQUITY! ^&^& set HARD_STOP_PCT=!HARD_STOP! ^&^& set TRAIL_PCT=!TRAIL_PCT! ^&^& set LOOP_SLEEP_SEC=!LOOP_SLEEP! ^&^& "!PYTHON_EXE!" "!SCRIPT_DIR!dronebot.py" ^&^& echo. ^&^& echo Dronebot exited with code %%ERRORLEVEL%% ^&^& if NOT "%%ERRORLEVEL%%"=="0" (echo Showing tail of bot_errors.log & powershell -NoProfile -Command "if (Test-Path '.\bot_errors.log') { Get-Content .\bot_errors.log -Tail 50 }") ^&^& echo. ^&^& pause"
endlocal
exit /b 0

:launch_dashboard
setlocal
  set "DEFAULT_DASH_HOST=%DEFAULT_LOOPBACK_HOST%"
set "DEFAULT_DASH_PORT=8765"
set "DEFAULT_SNAPSHOT=dashboard_snapshot.json"

echo === Entry dashboard settings ===
set "DASH_HOST="
set /p "DASH_HOST=Bind host [%DEFAULT_DASH_HOST%]: "
if "!DASH_HOST!"=="" set "DASH_HOST=%DEFAULT_DASH_HOST%"
set "DASH_PORT="
set /p "DASH_PORT=Port [%DEFAULT_DASH_PORT%]: "
if "!DASH_PORT!"=="" set "DASH_PORT=%DEFAULT_DASH_PORT%"
set "SNAPSHOT_PATH="
set /p "SNAPSHOT_PATH=Snapshot path [%DEFAULT_SNAPSHOT%]: "
if "!SNAPSHOT_PATH!"=="" set "SNAPSHOT_PATH=%DEFAULT_SNAPSHOT%"

echo.
echo Launching entry dashboard in a new window...
start "Entry Dashboard" cmd /k "cd /d "!SCRIPT_DIR!" ^&^& call "!ACTIVATE_BAT!" ^&^& set PYTHONUNBUFFERED=1 ^&^& "!PYTHON_EXE!" "!SCRIPT_DIR!entry_dashboard.py" --host "!DASH_HOST!" --port !DASH_PORT! --snapshot "!SNAPSHOT_PATH!" ^&^& echo. ^&^& pause"
endlocal
exit /b 0

:pre_session_tools
setlocal
set "PRE_ARGS="
set "DATE_INPUT="
set /p "DATE_INPUT=Run pre-session anchors for date (YYYY-MM-DD, blank for today): "
if not "!DATE_INPUT!"=="" set "PRE_ARGS=--date !DATE_INPUT!"

echo.
set PYTHONUNBUFFERED=1
"%PYTHON_EXE%" "%SCRIPT_DIR%pre_session_anchors.py" !PRE_ARGS!
set "PRE_RET=%ERRORLEVEL%"
echo === pre_session_anchors exited with code !PRE_RET! ===

echo.
set "RUN_ANALYSIS=Y"
set /p "RUN_ANALYSIS=Run fill analysis helper? [Y/n]: "
if /I "!RUN_ANALYSIS!"=="N" goto :pre_session_done

set "DEFAULT_CSV=fills_live.csv"
:prompt_csv
set "FILLS_CSV="
set /p "FILLS_CSV=Path to fills CSV [%DEFAULT_CSV%]: "
if "!FILLS_CSV!"=="" set "FILLS_CSV=%DEFAULT_CSV%"
if not exist "!FILLS_CSV!" (
  echo Could not find "!FILLS_CSV!". Try again.
  goto :prompt_csv
)
for %%I in ("!FILLS_CSV!") do set "FILLS_CSV=%%~fI"

set "SYMBOL_INPUT="
set /p "SYMBOL_INPUT=Symbol to describe immediately (blank to skip): "

echo.
set "SYMBOL_ARG="
if not "!SYMBOL_INPUT!"=="" set "SYMBOL_ARG=--symbol ""!SYMBOL_INPUT!"""
"%PYTHON_EXE%" "%SCRIPT_DIR%fill_analysis.py" "!FILLS_CSV!" --summary --interactive !SYMBOL_ARG!
set "ANALYSIS_RET=%ERRORLEVEL%"
echo === fill_analysis exited with code !ANALYSIS_RET! ===

echo.
:pre_session_done
echo Review the output above. Press any key to return to the menu.
pause >nul
endlocal
exit /b 0

:describe_fills
setlocal
set "DEFAULT_CSV=fills_live.csv"
set "FILLS_CSV="
set /p "FILLS_CSV=Path to fills CSV [%DEFAULT_CSV%]: "
if "!FILLS_CSV!"=="" set "FILLS_CSV=%DEFAULT_CSV%"
if not exist "!FILLS_CSV!" (
  echo Could not find "!FILLS_CSV!".
  pause
  endlocal
  exit /b 0
)
set "SYMBOL="
set /p "SYMBOL=Symbol to describe: "
if "!SYMBOL!"=="" (
  echo Symbol is required.
  pause
  endlocal
  exit /b 0
)

"%PYTHON_EXE%" "%SCRIPT_DIR%describe_fills.py" "!FILLS_CSV!" "!SYMBOL!"
echo === describe_fills exited with code !ERRORLEVEL! ===

echo.
pause
endlocal
exit /b 0

:ensure_venv
if exist "%PYTHON_EXE%" exit /b 0
if not exist "%SCRIPT_DIR%init_venv.bat" (
  echo Missing init_venv.bat; cannot create virtual environment.
  exit /b 1
)
call "%SCRIPT_DIR%init_venv.bat"
if errorlevel 1 (
  echo init_venv.bat reported an error.
  exit /b 1
)
if not exist "%PYTHON_EXE%" (
  echo Virtual environment creation appears to have failed.
  exit /b 1
)
exit /b 0

:finalize
endlocal
exit /b 0
