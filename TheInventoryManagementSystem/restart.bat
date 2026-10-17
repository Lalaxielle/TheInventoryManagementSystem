@echo off
cd /d "%~dp0"
echo ============================================
echo  TheInventoryManagementSystem - restart
echo ============================================
echo Stopping any server already using port 5000...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%p >nul 2>&1
)
echo Starting the app...
echo.
py app.py
echo.
echo The app has stopped. Press any key to close.
pause >nul
