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

call "%ACTIVATE_BAT%"
if errorlevel 1 (
  echo Failed to activate the virtual environment.
  set RET=%ERRORLEVEL%
  goto :finalize
)

set PYTHONUNBUFFERED=1

echo === running pre-session anchors ===
"%PYTHON_EXE%" "%SCRIPT_DIR%pre_session_anchors.py" !ORIG_ARGS!
set PRE_RET=%ERRORLEVEL%
echo === pre-session anchors exited with code !PRE_RET! ===

echo.
set "DEFAULT_CSV=fills_live.csv"
:prompt_csv
set /p FILLS_CSV=Enter path to fills CSV for fill reports [%DEFAULT_CSV%]:
if "!FILLS_CSV!"=="" set "FILLS_CSV=%DEFAULT_CSV%"
if not exist "!FILLS_CSV!" (
  echo Could not find "!FILLS_CSV!". Please try again.
  echo.
  goto :prompt_csv
)
for %%I in ("!FILLS_CSV!") do set "FILLS_CSV=%%~fI"

set /p SYMBOL=Enter symbol for describe_fills (leave blank to skip):
for /f "tokens=* delims=" %%S in ("!SYMBOL!") do set "SYMBOL=%%S"
set DESC_RET=0
if not "!SYMBOL!"=="" (
  echo === describing fills for !SYMBOL! from "!FILLS_CSV!" ===
  "%PYTHON_EXE%" "%SCRIPT_DIR%describe_fills.py" "!FILLS_CSV!" "!SYMBOL!"
  set DESC_RET=%ERRORLEVEL%
  echo === describe_fills exited with code !DESC_RET! ===
) else (
  echo === skipping describe_fills (no symbol provided) ===
)

echo.
echo === interactive fill analysis for "!FILLS_CSV!" ===
"%PYTHON_EXE%" -c "exec(\"\"\"import os\nfrom collections import Counter\nfrom pathlib import Path\n\nfrom fill_analysis import load_fills, describe_symbol_fills\n\ncsv_path = Path(os.environ['FILLS_CSV']).expanduser()\nprint(f'Loading fills from {csv_path}...')\nfills = load_fills(csv_path)\nprint(f'Loaded {len(fills)} fills from {csv_path}')\nprint()\nwhile True:\n    symbol = input('Enter symbol to describe (leave blank to finish): ').strip()\n    if not symbol:\n        break\n    print()\n    print(describe_symbol_fills(fills, symbol))\n    print()\nif fills:\n    counts = Counter(f.symbol for f in fills)\n    print('\nSymbols by fill count:')\n    for sym, count in counts.most_common():\n        print(f'  {sym}: {count}')\nelse:\n    print('\nNo fills found.')\n\"\"\")"
set ANALYSIS_RET=%ERRORLEVEL%
echo === fill analysis helper exited with code !ANALYSIS_RET! ===

echo.
echo All tasks finished. Review the output above for details.
echo.
set RET=0
if not "!PRE_RET!"=="0" set RET=!PRE_RET!
if not "!DESC_RET!"=="0" set RET=!DESC_RET!
if not "!ANALYSIS_RET!"=="0" set RET=!ANALYSIS_RET!
pause
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
