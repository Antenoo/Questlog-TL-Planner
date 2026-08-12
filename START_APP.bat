@echo off
setlocal
title Questlog TL Farm Planner - Launcher
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First-time setup has not been completed.
  echo Run SETUP_FIRST_TIME.bat first.
  pause
  exit /b 1
)

if not exist "launcher.py" (
  echo launcher.py is missing.
  pause
  exit /b 1
)

rem Start Python directly as the server process.
rem This avoids a nested cmd /c chain, which was unreliable when START_APP.bat
rem itself was invoked by the hidden live-update helper.
start "Questlog TL Farm Planner" /D "%~dp0" "%~dp0.venv\Scripts\python.exe" "%~dp0launcher.py"

endlocal
exit /b 0
