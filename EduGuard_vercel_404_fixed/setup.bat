@echo off
setlocal EnableDelayedExpansion
title EduGuard setup
cd /d "%~dp0"

echo ============================================================
echo   EduGuard setup
echo ============================================================
echo.

REM ---- 1. Node.js -------------------------------------------------
echo [1/9] Checking Node.js...
where node >nul 2>nul
if errorlevel 1 (
  echo   Node.js was not found. Install the LTS version from https://nodejs.org and run setup.bat again.
  goto :fail
)
for /f "delims=" %%v in ('node --version') do echo   Found Node.js %%v

REM ---- 2. Python --------------------------------------------------
echo [2/9] Checking Python...
set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo   Python 3.10 or newer was not found. Install it from https://www.python.org/downloads
  echo   and tick "Add python.exe to PATH", then run setup.bat again.
  goto :fail
)
for /f "delims=" %%v in ('%PY% --version') do echo   Found %%v

REM ---- 3. Frontend packages ---------------------------------------
echo [3/9] Installing desktop and web packages...
call npm install --no-audit --no-fund
if errorlevel 1 ( echo   Root npm install failed. Check your internet connection and try again. & goto :fail )
call npm --prefix frontend install --no-audit --no-fund
if errorlevel 1 ( echo   Frontend npm install failed. Check your internet connection and try again. & goto :fail )

REM ---- 4. Virtual environment -------------------------------------
echo [4/9] Creating the Python virtual environment...
if not exist "backend\venv\Scripts\python.exe" (
  %PY% -m venv backend\venv
  if errorlevel 1 ( echo   Could not create the virtual environment. & goto :fail )
) else (
  echo   Already exists, reusing it.
)

REM ---- 5. Python requirements -------------------------------------
echo [5/9] Installing Python packages (this can take a few minutes)...
"backend\venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
"backend\venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 ( echo   pip install failed. Check your internet connection and try again. & goto :fail )

REM ---- 6. Verify imports ------------------------------------------
echo [6/9] Verifying the installation...
"backend\venv\Scripts\python.exe" -c "import fastapi, uvicorn, pandas, numpy, sklearn, joblib, requests; print('  All Python packages import correctly.')"
if errorlevel 1 ( echo   A package failed to import. & goto :fail )

REM ---- 7. Models and demo data ------------------------------------
echo [7/9] Preparing demo data and training the risk model...
"backend\venv\Scripts\python.exe" -m backend.utilities.bootstrap
if errorlevel 1 ( echo   Model preparation failed. See logs\app.log. & goto :fail )

REM ---- 8. Optional AI engine (Ollama) -----------------------------
echo [8/9] Checking the optional AI writing assistant (Ollama)...
where ollama >nul 2>nul
if errorlevel 1 (
  echo   Ollama is not installed. That is fine: the assistant will use safe message templates.
  echo   To enable the AI assistant later, install Ollama from https://ollama.com and run setup.bat again.
) else (
  ollama list 2>nul | findstr /i "llama3.2:1b" >nul
  if errorlevel 1 (
    choice /c YN /m "  Download the small assistant model (about 1.3 GB)"
    if not errorlevel 2 ( ollama pull llama3.2:1b )
  ) else (
    echo   Assistant model is already available.
  )
)

REM ---- 9. Build the interface -------------------------------------
echo [9/9] Building the interface...
call npm --prefix frontend run build
if errorlevel 1 ( echo   The interface build failed. & goto :fail )

echo.
echo ============================================================
echo   Setup complete. Start EduGuard with run_project.bat
echo ============================================================
pause
exit /b 0

:fail
echo.
echo Setup did not finish. Fix the problem above and run setup.bat again.
pause
exit /b 1
