@echo off
title Gemini Web2API Manager
color 0B

:menu
cls
echo ===================================================
echo          GEMINI WEB2API CONTROL PANEL
echo ===================================================
echo.
echo   1. First-time Setup (Install requirements)
echo   2. Import / Refresh Cookies (from 'cookies' folder)
echo   3. Show Active API Keys
echo   4. Start Server and Web Dashboard
echo   5. Run Diagnostic Self-Check
echo   6. Exit
echo.
echo ===================================================
set /p choice="Select an option (1-6): "

if "%choice%"=="1" goto setup
if "%choice%"=="2" goto import
if "%choice%"=="3" goto show
if "%choice%"=="4" goto run
if "%choice%"=="5" goto test
if "%choice%"=="6" goto eof

:setup
cls
echo [Status] Installing Python dependencies (FastAPI, curl_cffi, playwright)...
pip install -r requirements.txt
echo [Status] Installing Playwright browsers (for optional automated cookie extractor)...
playwright install chromium
echo [Success] Setup complete!
pause
goto menu

:import
cls
echo [Status] Importing new cookies from 'cookies' folder...
if not exist "cookies" mkdir cookies
python -m gemini_web2api --import-cookies cookies
pause
goto menu

:show
cls
echo [Status] Fetching active API keys...
python -m gemini_web2api --show-apis
pause
goto menu

:run
cls
echo [Status] Starting Gemini Web2API Server...
echo [Info] Web Dashboard is live at: http://localhost:10012
echo.
python -m gemini_web2api --port 10012
pause
goto menu

:test
cls
echo [Status] Running Gateway Diagnostic Self-Check...
python -m gemini_web2api --test
pause
goto menu

:eof
exit
