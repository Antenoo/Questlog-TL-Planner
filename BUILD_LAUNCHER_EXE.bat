@echo off
setlocal
title Questlog TL Farm Planner - Build Windows Launcher
cd /d "%~dp0"

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"

if not exist "%CSC%" (
  echo.
  echo Windows .NET Framework C# compiler was not found.
  echo The desktop shortcut can still use the included custom icon and hidden PowerShell launcher.
  echo.
  exit /b 2
)

if not exist "assets\Questlog_TL_Farm_Planner.ico" (
  echo Icon file is missing.
  exit /b 1
)

if not exist "windows_launcher\QuestlogLauncher.cs" (
  echo Launcher source is missing.
  exit /b 1
)

echo Building Questlog TL Farm Planner.exe...
"%CSC%" /nologo /target:winexe /optimize+ ^
  /reference:System.Windows.Forms.dll ^
  /win32icon:"assets\Questlog_TL_Farm_Planner.ico" ^
  /out:"Questlog TL Farm Planner.exe" ^
  "windows_launcher\QuestlogLauncher.cs"

if errorlevel 1 (
  echo.
  echo Could not build the optional EXE.
  echo The icon shortcut installer can still use the PowerShell launcher.
  exit /b 1
)

echo.
echo Created:
echo   "%CD%\Questlog TL Farm Planner.exe"
echo.
exit /b 0
