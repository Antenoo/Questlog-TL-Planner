@echo off
setlocal
title Questlog TL Planner - View-only relay
cd /d "%~dp0"

echo Starting the view-only screen relay...
echo This reads the primary monitor only. It does not send input or capture audio.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\view_only_relay.ps1"

echo.
echo The view-only relay has stopped.
pause
endlocal
