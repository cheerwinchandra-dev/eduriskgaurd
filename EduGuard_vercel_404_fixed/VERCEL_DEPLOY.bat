@echo off
setlocal
cd /d "%~dp0"

echo ================================
echo EduGuard - Vercel Production Deploy
echo ================================
echo.

where node >nul 2>nul || (echo Node.js is required.& exit /b 1)
where npx >nul 2>nul || (echo npx is required.& exit /b 1)

echo Installing frontend dependencies...
call npm install --prefix frontend --no-audit --no-fund
if errorlevel 1 exit /b 1

echo Building frontend...
call npm run build --prefix frontend
if errorlevel 1 exit /b 1

echo.
echo IMPORTANT: run this file from the repository root.
echo The Vercel project must use this repository root, not frontend/ or backend/.
echo.
call npx vercel@latest --prod
exit /b %errorlevel%
