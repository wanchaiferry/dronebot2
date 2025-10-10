@echo off
REM init_venv.bat — run once inside D:\dronebot
setlocal
cd /d %~dp0
set PY_EXE=python

where py >nul 2>nul
if %errorlevel%==0 (
  for /f "usebackq tokens=*" %%p in (`py -0p ^| findstr /i "3.13"`) do set PY_EXE=py -3.13
)

echo Using %PY_EXE%
%PY_EXE% -m venv .venv
if errorlevel 1 (
  echo Failed to create venv with %PY_EXE%. Trying with 'python'...
  python -m venv .venv
)

call .venv\Scripts\activate
python -m pip --version >nul 2>nul || python -m ensurepip --upgrade
python -m pip install --upgrade pip
python -m pip install ib_insync pandas numpy python-dateutil
echo.
echo VENV READY. To use later:  call .venv\Scripts\activate
endlocal
