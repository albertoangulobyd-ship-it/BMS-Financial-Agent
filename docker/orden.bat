@echo off
rem Abre orden.ps1 sin tener que cambiar la politica de scripts de Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0orden.ps1" %*
if errorlevel 1 pause
