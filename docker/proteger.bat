@echo off
rem Abre proteger.ps1 sin tener que cambiar la politica de scripts de Windows (pide administrador).
rem PowerShell por su ruta completa: cmd busca los programas primero en la carpeta actual.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0proteger.ps1" %*
if errorlevel 1 pause
