@echo off
rem Abre restaurar.ps1 sin tener que cambiar la politica de scripts de Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restaurar.ps1" %*
if errorlevel 1 pause
