@echo off
setlocal
title EduGuard Vercel Deploy
cd /d "%~dp0"

echo ============================================================
echo   EduGuard Vercel deployment
echo ============================================================
echo.

where node >nul 2>nul
if errorlevel 1 ( echo Node.js is required. & exit /b 1 )
where npx >nul 2>nul
if errorlevel 1 ( echo npx is required. & exit /b 1 )

echo [1/3] Installing frontend dependencies...
call npm install --prefix frontend --no-audit --no-fund
if errorlevel 1 exit /b 1

echo [2/3] Building the Vercel frontend...
call npm run build --prefix frontend
if errorlevel 1 exit /b 1

echo [3/3] Starting Vercel deployment/link flow...
call npx vercel@latest
if errorlevel 1 exit /b 1

echo.
echo Deployment flow complete.
