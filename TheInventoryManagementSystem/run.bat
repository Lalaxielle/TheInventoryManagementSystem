@echo off
cd /d "%~dp0"
echo Starting TheInventoryManagementSystem...
py app.py
if errorlevel 1 pause
