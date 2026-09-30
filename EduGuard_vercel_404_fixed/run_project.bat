@echo off
title EduGuard
cd /d "%~dp0"

if not exist "backend\venv\Scripts\python.exe" (
  echo EduGuard has not been set up yet. Run setup.bat first.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo The interface has not been built yet. Run setup.bat first.
  pause
  exit /b 1
)

REM Electron starts the Python backend itself and stops it when the window closes.
call npm start
