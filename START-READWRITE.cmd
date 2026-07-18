@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0START-READWRITE.ps1"
if errorlevel 1 pause
