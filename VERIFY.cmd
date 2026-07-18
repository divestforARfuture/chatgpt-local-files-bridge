@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0VERIFY.ps1"
pause
