@echo off
setlocal
title Questlog TL Farm Planner - Install App Shortcut
cd /d "%~dp0"

echo.
echo Questlog TL Farm Planner - Windows launcher setup
echo.

call "%~dp0BUILD_LAUNCHER_EXE.bat" >nul 2>nul

set "ROOT=%~dp0"
set "EXE=%~dp0Questlog TL Farm Planner.exe"
set "ICON=%~dp0assets\Questlog_TL_Farm_Planner.ico"
set "PS1=%~dp0LAUNCH_PLANNER.ps1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root=$env:ROOT;" ^
  "$exe=$env:EXE;" ^
  "$icon=$env:ICON;" ^
  "$ps1=$env:PS1;" ^
  "$shell=New-Object -ComObject WScript.Shell;" ^
  "$desktop=$shell.SpecialFolders.Item('Desktop');" ^
  "$startMenu=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs';" ^
  "$targets=@((Join-Path $desktop 'Questlog TL Farm Planner.lnk'),(Join-Path $startMenu 'Questlog TL Farm Planner.lnk'));" ^
  "foreach($shortcutPath in $targets){" ^
  "  $s=$shell.CreateShortcut($shortcutPath);" ^
  "  if(Test-Path -LiteralPath $exe){" ^
  "    $s.TargetPath=$exe;" ^
  "    $s.Arguments='';" ^
  "    $s.IconLocation=$exe + ',0';" ^
  "  }else{" ^
  "    $s.TargetPath=(Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe');" ^
  "    $s.Arguments='-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"' + $ps1 + '\"';" ^
  "    $s.IconLocation=$icon + ',0';" ^
  "  }" ^
  "  $s.WorkingDirectory=$root.TrimEnd('\');" ^
  "  $s.Description='Questlog Throne and Liberty Farm Planner';" ^
  "  $s.Save();" ^
  "}"

if errorlevel 1 (
  echo.
  echo Could not create the Windows shortcuts.
  pause
  exit /b 1
)

echo.
if exist "Questlog TL Farm Planner.exe" (
  echo Installed a real Windows launcher EXE with the custom app icon.
) else (
  echo Installed a Windows shortcut with the custom app icon.
  echo Your PC did not expose the optional .NET compiler, so the shortcut uses the hidden launcher instead.
)
echo.
echo Added:
echo   - Desktop: Questlog TL Farm Planner
echo   - Start Menu: Questlog TL Farm Planner
echo.
echo You can now start the planner from the normal app icon.
echo.
pause
exit /b 0
