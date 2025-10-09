@echo off
setlocal
cd /d %~dp0

if not exist .venv (
  call init_venv.bat
)
call .venv\Scripts\activate

set PYTHONUNBUFFERED=1

echo === running pre-session anchors ===
python pre_session_anchors.py %*
set RET=%ERRORLEVEL%
echo === pre-session anchors finished with exit code %RET% ===

echo.
pause

endlocal
