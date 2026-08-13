@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\stop_view_only_relay.ps1"
timeout /t 2 /nobreak >nul
endlocal
