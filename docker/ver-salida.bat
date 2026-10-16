@echo off
rem Abre ver-salida.ps1 sin tener que cambiar la politica de scripts de Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ver-salida.ps1" %*
if errorlevel 1 pause
