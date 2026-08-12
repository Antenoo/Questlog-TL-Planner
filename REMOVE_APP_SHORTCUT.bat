@echo off
setlocal
title Questlog TL Farm Planner - Remove App Shortcut
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$shell=New-Object -ComObject WScript.Shell;" ^
  "$desktop=$shell.SpecialFolders.Item('Desktop');" ^
  "$startMenu=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs';" ^
  "$paths=@((Join-Path $desktop 'Questlog TL Farm Planner.lnk'),(Join-Path $startMenu 'Questlog TL Farm Planner.lnk'));" ^
  "foreach($p in $paths){ if(Test-Path -LiteralPath $p){ Remove-Item -LiteralPath $p -Force } }"

echo.
echo Questlog TL Farm Planner shortcuts removed.
echo The local app, data, optional EXE, and cache were not deleted.
echo.
pause
exit /b 0
