@echo off
rem Abre parar.ps1 sin tener que cambiar la politica de scripts de Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0parar.ps1" %*
if errorlevel 1 pause
