@echo off
title Questlog TL Farm Planner - Rollback
cd /d "%~dp0"
echo.
echo Close the web app before rolling back.
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" update_manager.py rollback
) else (
  python update_manager.py rollback
)
echo.
pause
