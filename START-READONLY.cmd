@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0START-READONLY.ps1"
if errorlevel 1 pause
