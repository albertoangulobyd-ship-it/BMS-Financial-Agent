@echo off
rem Abre leer-facturas.ps1 sin tener que cambiar la politica de scripts de Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0leer-facturas.ps1" %*
if errorlevel 1 pause
