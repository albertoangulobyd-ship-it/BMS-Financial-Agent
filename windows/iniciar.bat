@echo off
rem Abre iniciar.ps1 sin tener que cambiar la politica de scripts de Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1" %*
if errorlevel 1 pause
