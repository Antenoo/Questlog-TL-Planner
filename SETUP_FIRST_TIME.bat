@echo on
title Questlog TL Farm Planner - First Time Setup
cd /d "%~dp0"

echo ================================================================
echo Questlog TL Farm Planner - First Time Setup
echo ================================================================

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo Python not found.
    pause
    exit /b 1
  )
)

%PY% --version

echo [1/5] Creating virtual environment...
%PY% -m venv .venv
if errorlevel 1 goto :fail

echo [2/5] Creating safe local configuration when missing...
call ".venv\Scripts\python.exe" config_bootstrap.py
if errorlevel 1 goto :fail

echo [3/5] Upgrading pip...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo [4/5] Installing app dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [5/5] Installing Playwright Chromium...
call ".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :fail

echo.
echo SETUP COMPLETE
echo From now on, use START_APP.bat
pause
exit /b 0

:fail
echo.
echo SETUP FAILED
pause
exit /b 1
