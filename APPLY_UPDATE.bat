@echo off
title Questlog TL Farm Planner - Apply Update
cd /d "%~dp0"

echo.
echo Questlog TL Farm Planner updater
echo.
echo The planner server should be closed before applying the update.
echo Keep the existing browser tab open.
echo.

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" update_manager.py apply
) else (
  python update_manager.py apply
)

if errorlevel 1 (
  echo.
  echo Update failed. The planner was NOT restarted.
  echo Check the message above, then try again.
  echo.
  pause
  exit /b 1
)

echo.
echo Update applied successfully.
echo Restarting the planner server now...
echo Your existing 127.0.0.1:8765 tab should refresh itself automatically.
echo.

start "" "%~dp0START_APP.bat"

timeout /t 2 /nobreak >nul
exit /b 0
